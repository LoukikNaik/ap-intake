"""The deterministic orchestrator.

This is plain Python that SEQUENCES the agent stages and does the non-judgment work
(arithmetic validation, duplicate detection, persistence). It contains ZERO business
decisions — every judgment (classify, split, extract, GL-map, when-to-flag) is made by an
agent. Code is the plumbing; agents are the brain.

Flow:  triage/split → (fan out per segment) extract → GL-map → validate+dedup → route
"""

import asyncio
import json
import re

from agents import Runner, trace
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents.context import GLAccountView, PipelineContext
from app.agents.definitions import build_extract_agent, build_gl_agent, build_triage_agent
from app.agents.schemas import ExtractedInvoice, GLMappingResult, TriageResult
from app.config import get_settings
from app.db import SessionLocal
from app.models import AgentConfig, Bill, Document, GLAccount, Issue, LineItem
from app.pdf_utils import pdf_to_data_url, render_pdf_to_data_urls, slice_pdf

settings = get_settings()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_VENDOR_SUFFIXES = re.compile(r"\b(llc|inc|incorporated|co|corp|company|ltd|lp|llp)\b\.?", re.I)


def normalize_vendor(vendor: str | None) -> str:
    """Normalise a vendor name so 'ABC Lumber LLC' and 'ABC Lumber' match for dedup."""
    if not vendor:
        return ""
    v = vendor.lower()
    v = _VENDOR_SUFFIXES.sub("", v)
    v = re.sub(r"[^a-z0-9 ]", "", v)
    return re.sub(r"\s+", " ", v).strip()


def _pdf_message(text: str, pdf_bytes: bytes, pages: list[int] | None = None) -> list[dict]:
    """Build the user message that carries the document.

    Honours settings.pdf_input_mode:
      - "native": hand the PDF straight to the model (reads the embedded text layer).
      - "images": render the page(s) to PNGs and send as vision input (portable fallback).
    `pages` (1-based) restricts to a single invoice segment.
    """
    content: list[dict] = [{"type": "input_text", "text": text}]
    if settings.pdf_input_mode == "native":
        seg_bytes = slice_pdf(pdf_bytes, pages) if pages else pdf_bytes
        content.append(
            {"type": "input_file", "filename": "document.pdf", "file_data": pdf_to_data_url(seg_bytes)}
        )
    else:
        for url in render_pdf_to_data_urls(pdf_bytes, pages):
            content.append({"type": "input_image", "image_url": url})
    return [{"role": "user", "content": content}]


def _load_active_policy(db: Session) -> str:
    cfg = db.scalar(select(AgentConfig).where(AgentConfig.is_active.is_(True)))
    return cfg.instructions if cfg else ""


def _active_config_version(db: Session) -> int | None:
    cfg = db.scalar(select(AgentConfig).where(AgentConfig.is_active.is_(True)))
    return cfg.version if cfg else None


def _load_gl_context(db: Session) -> PipelineContext:
    rows = db.scalars(select(GLAccount).where(GLAccount.is_active.is_(True))).all()
    return PipelineContext(
        gl_accounts=[GLAccountView(code=r.code, name=r.name, description=r.description) for r in rows]
    )


def _valid_gl_codes(ctx: PipelineContext) -> set[str]:
    return {a.code for a in ctx.gl_accounts}


# ---------------------------------------------------------------------------
# Stage 4 — deterministic validation + flag decision (NOT an agent)
# ---------------------------------------------------------------------------


def _validate_and_flag(
    inv: ExtractedInvoice,
    mapping: GLMappingResult,
    valid_codes: set[str],
) -> list[str]:
    flags: list[str] = []

    # Arithmetic: do line items + tax + other charges reconcile with the stated total?
    line_sum = round(sum(li.amount for li in inv.line_items), 2)
    reconciled = round(line_sum + inv.tax + inv.other_charges, 2)
    if inv.line_items and abs(reconciled - round(inv.total, 2)) > 0.01:
        flags.append(
            f"Lines ({line_sum}) + tax ({inv.tax}) + other ({inv.other_charges}) = {reconciled}, "
            f"but total is {inv.total}"
        )

    # Per-line: quantity x unit price should equal the line amount (when both are present).
    for idx, li in enumerate(inv.line_items):
        if li.quantity not in (None, 0) and li.unit_price is not None:
            expected = round(li.quantity * li.unit_price, 2)
            if abs(expected - round(li.amount, 2)) > 0.01:
                flags.append(
                    f"Line {idx + 1}: qty {li.quantity} x unit {li.unit_price} = {expected}, "
                    f"but amount is {li.amount}"
                )

    # Sign sanity vs credit-memo flag.
    if inv.total < 0 and not inv.is_credit_memo:
        flags.append("Negative total but not marked as a credit memo")
    if inv.is_credit_memo and inv.total > 0:
        flags.append("Marked as credit memo but total is positive")

    # Required fields.
    if not inv.vendor:
        flags.append("Missing vendor")
    if not inv.invoice_number:
        flags.append("Missing invoice number")

    # GL mapping issues surfaced by the agent.
    for m in mapping.lines:
        if m.needs_review or m.gl_code is None:
            flags.append(f"Line {m.index + 1}: GL mapping needs review ({m.reasoning})")
        elif m.gl_code not in valid_codes:
            flags.append(f"Line {m.index + 1}: GL code {m.gl_code} is not a known account")

    # Low confidence (e.g. scanned/skewed).
    if inv.confidence < settings.review_confidence_threshold:
        flags.append(f"Low extraction confidence ({inv.confidence:.2f})")

    return flags


# ---------------------------------------------------------------------------
# Per-segment processing (extract -> GL map), runs in parallel across segments
# ---------------------------------------------------------------------------


async def _process_segment(
    segment,
    pdf_bytes: bytes,
    policy: str,
    gl_ctx: PipelineContext,
) -> tuple[ExtractedInvoice, GLMappingResult]:
    extract_agent = build_extract_agent(policy)
    extracted = await Runner.run(
        extract_agent,
        _pdf_message(
            "Extract this invoice's fields and line items.", pdf_bytes, segment.pages or None
        ),
        max_turns=settings.max_turns,
    )
    inv: ExtractedInvoice = extracted.final_output

    # GL mapping over the extracted lines (text, no images needed).
    gl_agent = build_gl_agent(policy)
    lines_text = "\n".join(
        f"{i}: {li.description} | amount={li.amount}" for i, li in enumerate(inv.line_items)
    )
    mapped = await Runner.run(
        gl_agent,
        f"Map each of these line items to a GL code:\n{lines_text}",
        context=gl_ctx,
        max_turns=settings.max_turns,
    )
    mapping: GLMappingResult = mapped.final_output
    return inv, mapping


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def process_document(document_id: int) -> None:
    """Run the full pipeline for one document. Updates DB rows in place."""
    db = SessionLocal()
    try:
        doc = db.get(Document, document_id)
        if doc is None:
            return
        doc.status = "processing"
        db.commit()

        policy = _load_active_policy(db)
        gl_ctx = _load_gl_context(db)
        valid_codes = _valid_gl_codes(gl_ctx)
        doc.config_version = _active_config_version(db)

        with trace(workflow_name="ap-intake", group_id=str(document_id)):
            # --- Stage 1: triage / split ---
            triage_agent = build_triage_agent(policy)
            triaged = await Runner.run(
                triage_agent,
                _pdf_message(
                    "Classify this document and split it into distinct invoices.", doc.raw
                ),
                max_turns=settings.max_turns,
            )
            result: TriageResult = triaged.final_output

            if result.document_type == "not_an_invoice" or not result.segments:
                db.add(
                    Issue(
                        document_id=doc.id,
                        kind="not_an_invoice",
                        reason=result.issue_reason or "Document is not an invoice.",
                    )
                )
                doc.status = "processed"
                db.commit()
                return

            # --- Stages 2+3: fan out per segment, in parallel ---
            seg_results = await asyncio.gather(
                *[_process_segment(seg, doc.raw, policy, gl_ctx) for seg in result.segments]
            )

        # --- Stage 4+5: validate, dedup, route, persist (deterministic) ---
        for seg, (inv, mapping) in zip(result.segments, seg_results):
            flags = _validate_and_flag(inv, mapping, valid_codes)

            vnorm = normalize_vendor(inv.vendor)
            dup = None
            if vnorm and inv.invoice_number:
                dup = db.scalar(
                    select(Bill).where(
                        Bill.vendor_normalized == vnorm,
                        Bill.invoice_number == inv.invoice_number,
                        Bill.status != "rejected",
                    )
                )
            is_duplicate = dup is not None
            if is_duplicate:
                flags.insert(0, f"Possible duplicate of bill #{dup.id}")

            if is_duplicate:
                status = "duplicate"
            elif flags:
                status = "needs_review"
            else:
                status = "ready_to_approve"

            bill = Bill(
                document_id=doc.id,
                vendor=inv.vendor,
                vendor_normalized=vnorm or None,
                invoice_number=inv.invoice_number,
                invoice_date=inv.invoice_date,
                due_date=inv.due_date,
                currency=inv.currency,
                is_credit_memo=inv.is_credit_memo,
                applies_to_invoice=inv.applies_to_invoice,
                subtotal=inv.subtotal,
                tax=inv.tax,
                other_charges=inv.other_charges,
                total=inv.total,
                status=status,
                is_duplicate=is_duplicate,
                duplicate_of_bill_id=dup.id if dup else None,
                confidence=inv.confidence,
                agent_reasoning=(inv.notes or "") + ("\n" + seg.reasoning if seg.reasoning else ""),
                review_flags=json.dumps(flags),
                pages=json.dumps(seg.pages),
                segment_index=seg.index,
            )
            db.add(bill)
            db.flush()  # get bill.id

            by_index = {m.index: m for m in mapping.lines}
            for i, li in enumerate(inv.line_items):
                m = by_index.get(i)
                db.add(
                    LineItem(
                        bill_id=bill.id,
                        description=li.description,
                        quantity=li.quantity,
                        unit_price=li.unit_price,
                        amount=li.amount,
                        gl_code=m.gl_code if m else None,
                        gl_confidence=m.gl_confidence if m else 0.0,
                        needs_review=(m.needs_review if m else True),
                        reasoning=m.reasoning if m else None,
                    )
                )

        doc.status = "processed"
        db.commit()

    except Exception as exc:  # noqa: BLE001 — record the failure, never lose the document
        db.rollback()
        doc = db.get(Document, document_id)
        if doc is not None:
            doc.status = "failed"
            doc.error = f"{type(exc).__name__}: {exc}"
            db.add(Issue(document_id=doc.id, kind="error", reason=doc.error))
            db.commit()
    finally:
        db.close()
