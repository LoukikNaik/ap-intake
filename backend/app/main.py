"""FastAPI app — ingestion, review queue, issues, and the editable config surface."""

import json
from datetime import datetime, timedelta, timezone

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import Base, engine, get_db
from app.models import AgentConfig, Bill, Document, Feedback, GLAccount, Issue, LineItem
from app.pdf_utils import page_count, render_page_png, sha256_bytes
from app.pipeline import normalize_vendor, process_document
from app.schemas import (
    AgentConfigIn,
    AgentConfigOut,
    BillEdit,
    BillOut,
    DocumentOut,
    GLAccountIn,
    GLAccountOut,
    IngestResponse,
    IssueOut,
)
from app.seed import seed

settings = get_settings()
app = FastAPI(title="AP Intake Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.cors_origins.split(",")],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def _startup() -> None:
    Base.metadata.create_all(bind=engine)
    seed()


# ---------------------------------------------------------------------------
# Serialization helpers
# ---------------------------------------------------------------------------


def _bill_out(bill: Bill) -> BillOut:
    # review_flags (a JSON string column) is parsed by BillOut's validator.
    return BillOut.model_validate(bill)


# ---------------------------------------------------------------------------
# Review lease (so two clerks don't review the same bill at once)
# ---------------------------------------------------------------------------

LEASE_TTL = timedelta(minutes=10)


def _lease_holder(bill: Bill) -> str | None:
    """Return the clerk currently holding a live lease, or None if free/expired."""
    if bill.locked_by and bill.locked_at:
        locked_at = bill.locked_at
        if locked_at.tzinfo is None:
            locked_at = locked_at.replace(tzinfo=timezone.utc)
        if datetime.now(timezone.utc) - locked_at < LEASE_TTL:
            return bill.locked_by
    return None


def _require_lease(bill: Bill, clerk: str) -> None:
    """Raise 409 if someone else holds the lease."""
    holder = _lease_holder(bill)
    if holder and holder != clerk:
        raise HTTPException(409, f"Bill is being reviewed by {holder}")


def _recheck_duplicate(db: Session, bill: Bill) -> None:
    """Re-run duplicate detection after a reviewer edits vendor/invoice number.

    Lets a clerk clear a FALSE duplicate by correcting the invoice number (or vendor),
    and conversely re-flag if an edit makes it collide with an existing bill.
    """
    bill.vendor_normalized = normalize_vendor(bill.vendor) or None
    dup = None
    if bill.vendor_normalized and bill.invoice_number:
        dup = db.scalar(
            select(Bill).where(
                Bill.vendor_normalized == bill.vendor_normalized,
                Bill.invoice_number == bill.invoice_number,
                Bill.id != bill.id,
                Bill.status != "rejected",
            )
        )
    bill.is_duplicate = dup is not None
    bill.duplicate_of_bill_id = dup.id if dup else None

    # Keep the duplicate flag in review_flags consistent with the new verdict.
    flags = [f for f in (json.loads(bill.review_flags) if bill.review_flags else [])
             if "duplicate of bill" not in f.lower()]
    if dup is not None:
        flags.insert(0, f"Possible duplicate of bill #{dup.id}")
    bill.review_flags = json.dumps(flags)

    # Re-route, but never override a final human decision.
    if bill.status not in ("approved", "rejected"):
        if bill.is_duplicate:
            bill.status = "duplicate"
        else:
            bill.status = "needs_review" if flags else "ready_to_approve"


# ---------------------------------------------------------------------------
# Ingestion
# ---------------------------------------------------------------------------


@app.post("/invoices", response_model=IngestResponse, status_code=202)
async def ingest(
    background: BackgroundTasks,
    file: UploadFile,
    source: str = "api",
    db: Session = Depends(get_db),
):
    """Accept a PDF, store it, and process it asynchronously. Returns immediately (202).

    Idempotent on file bytes (sha256): re-posting identical bytes returns the existing
    document instead of reprocessing.
    """
    raw = await file.read()
    if not raw:
        raise HTTPException(400, "Empty file")
    digest = sha256_bytes(raw)

    existing = db.scalar(select(Document).where(Document.sha256 == digest))
    if existing is not None:
        return IngestResponse(
            document_id=existing.id,
            status=existing.status,
            message="Identical file already ingested (idempotent).",
        )

    try:
        pages = page_count(raw)
    except Exception:  # noqa: BLE001
        raise HTTPException(400, "Could not read PDF") from None

    doc = Document(
        filename=file.filename or "upload.pdf",
        source=source,
        sha256=digest,
        raw=raw,
        page_count=pages,
        status="queued",
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)

    background.add_task(process_document, doc.id)
    return IngestResponse(document_id=doc.id, status="queued", message="Processing started.")


@app.get("/documents/{doc_id}", response_model=DocumentOut)
def get_document(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Not found")
    return doc


@app.get("/documents/{doc_id}/pdf")
def get_document_pdf(doc_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Not found")
    return Response(content=doc.raw, media_type="application/pdf")


@app.get("/documents/{doc_id}/page/{page}.png")
def get_document_page(doc_id: int, page: int, rotate: int = 0, db: Session = Depends(get_db)):
    """A single page rendered to PNG — used by the side-by-side (scroll-together) review view.

    `rotate` (0/90/180/270) lets the reviewer straighten a sideways scan.
    """
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Not found")
    return Response(content=render_page_png(doc.raw, page, rotate), media_type="image/png")


@app.post("/documents/{doc_id}/reprocess", response_model=IngestResponse, status_code=202)
def reprocess(doc_id: int, background: BackgroundTasks, db: Session = Depends(get_db)):
    """Re-run the pipeline (e.g. after editing config). Clears prior bills/issues."""
    doc = db.get(Document, doc_id)
    if not doc:
        raise HTTPException(404, "Not found")
    for b in list(doc.bills):
        db.delete(b)
    for i in list(doc.issues):
        db.delete(i)
    doc.status = "queued"
    doc.error = None
    db.commit()
    background.add_task(process_document, doc.id)
    return IngestResponse(document_id=doc.id, status="queued", message="Reprocessing started.")


# ---------------------------------------------------------------------------
# Review queue
# ---------------------------------------------------------------------------


@app.get("/bills", response_model=list[BillOut])
def list_bills(status: str | None = None, db: Session = Depends(get_db)):
    stmt = select(Bill).order_by(Bill.created_at.desc())
    if status:
        stmt = stmt.where(Bill.status == status)
    return [_bill_out(b) for b in db.scalars(stmt).all()]


@app.get("/bills/{bill_id}", response_model=BillOut)
def get_bill(bill_id: int, db: Session = Depends(get_db)):
    bill = db.get(Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Not found")
    return _bill_out(bill)


@app.post("/bills/{bill_id}/claim", response_model=BillOut)
def claim_bill(bill_id: int, clerk: str, db: Session = Depends(get_db)):
    """Acquire the review lease. 409 if another clerk holds a live lease."""
    bill = db.get(Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Not found")
    _require_lease(bill, clerk)
    bill.locked_by = clerk
    bill.locked_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


@app.post("/bills/{bill_id}/release", response_model=BillOut)
def release_bill(bill_id: int, clerk: str, db: Session = Depends(get_db)):
    """Release the lease if this clerk holds it."""
    bill = db.get(Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Not found")
    if bill.locked_by == clerk:
        bill.locked_by = None
        bill.locked_at = None
        db.commit()
        db.refresh(bill)
    return _bill_out(bill)


@app.patch("/bills/{bill_id}", response_model=BillOut)
def edit_bill(bill_id: int, edit: BillEdit, db: Session = Depends(get_db)):
    """Apply a reviewer's edits. Every change is recorded as Feedback (labeled data)."""
    bill = db.get(Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Not found")
    if edit.reviewed_by:
        _require_lease(bill, edit.reviewed_by)

    # Apply a field that was EXPLICITLY provided in the request (even if its value is null —
    # e.g. clearing a GL code to send a line back to "needs review"). We use Pydantic's
    # model_fields_set to distinguish "field omitted" from "field set to null", which a plain
    # `is not None` check cannot. Feedback is logged whenever the value actually changes.
    def apply(obj, field, new, line_item_id: int | None = None):
        old = getattr(obj, field)
        if str(old) != str(new):
            db.add(
                Feedback(
                    bill_id=bill.id,
                    line_item_id=line_item_id,
                    field=field,
                    agent_value=str(old),
                    human_value=str(new),
                    created_by=edit.reviewed_by,
                )
            )
        setattr(obj, field, new)

    hdr_set = edit.model_fields_set
    for field in (
        "vendor", "invoice_number", "invoice_date", "due_date", "tax", "other_charges",
        "total", "is_credit_memo",
    ):
        if field in hdr_set:
            apply(bill, field, getattr(edit, field))

    for le in edit.line_items:
        li = db.get(LineItem, le.id)
        if not li or li.bill_id != bill.id:
            continue
        le_set = le.model_fields_set
        for field in ("gl_code", "description", "quantity", "unit_price", "amount", "needs_review"):
            if field in le_set:
                apply(li, field, getattr(le, field), line_item_id=li.id)

    # If the vendor or invoice number was provided, re-evaluate duplicate status so a
    # corrected false-positive clears (and a new collision re-flags).
    if "vendor" in hdr_set or "invoice_number" in hdr_set:
        _recheck_duplicate(db, bill)

    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


@app.post("/bills/{bill_id}/approve", response_model=BillOut)
def approve_bill(bill_id: int, reviewed_by: str = "clerk", db: Session = Depends(get_db)):
    bill = db.get(Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Not found")
    _require_lease(bill, reviewed_by)
    bill.status = "approved"
    bill.reviewed_by = reviewed_by
    bill.reviewed_at = datetime.now(timezone.utc)
    bill.locked_by = None
    bill.locked_at = None
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


@app.post("/bills/{bill_id}/reject", response_model=BillOut)
def reject_bill(bill_id: int, reviewed_by: str = "clerk", db: Session = Depends(get_db)):
    bill = db.get(Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Not found")
    _require_lease(bill, reviewed_by)
    bill.status = "rejected"
    bill.reviewed_by = reviewed_by
    bill.reviewed_at = datetime.now(timezone.utc)
    bill.locked_by = None
    bill.locked_at = None
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


@app.post("/bills/{bill_id}/reopen", response_model=BillOut)
def reopen_bill(bill_id: int, reviewed_by: str = "clerk", db: Session = Depends(get_db)):
    """Undo an approve/reject — send the bill back into the review queue.

    Status is recomputed from its current flags/duplicate state, so a clean bill returns to
    'ready_to_approve' and a flagged one to 'needs_review'.
    """
    bill = db.get(Bill, bill_id)
    if not bill:
        raise HTTPException(404, "Not found")
    _require_lease(bill, reviewed_by)
    flags = json.loads(bill.review_flags) if bill.review_flags else []
    if bill.is_duplicate:
        bill.status = "duplicate"
    elif flags:
        bill.status = "needs_review"
    else:
        bill.status = "ready_to_approve"
    bill.reviewed_by = None
    bill.reviewed_at = None
    db.commit()
    db.refresh(bill)
    return _bill_out(bill)


# ---------------------------------------------------------------------------
# Issues queue
# ---------------------------------------------------------------------------


@app.get("/issues", response_model=list[IssueOut])
def list_issues(db: Session = Depends(get_db)):
    return db.scalars(select(Issue).order_by(Issue.created_at.desc())).all()


@app.post("/issues/{issue_id}/resolve", response_model=IssueOut)
def resolve_issue(issue_id: int, db: Session = Depends(get_db)):
    issue = db.get(Issue, issue_id)
    if not issue:
        raise HTTPException(404, "Not found")
    issue.resolved = True
    db.commit()
    db.refresh(issue)
    return issue


# ---------------------------------------------------------------------------
# Config — prompt-as-configuration (GL accounts + agent policy)
# ---------------------------------------------------------------------------


@app.get("/config/gl-accounts", response_model=list[GLAccountOut])
def list_gl(db: Session = Depends(get_db)):
    return db.scalars(select(GLAccount).order_by(GLAccount.code)).all()


@app.post("/config/gl-accounts", response_model=GLAccountOut)
def create_gl(acct: GLAccountIn, db: Session = Depends(get_db)):
    if db.scalar(select(GLAccount).where(GLAccount.code == acct.code)):
        raise HTTPException(409, "GL code already exists")
    row = GLAccount(**acct.model_dump())
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.put("/config/gl-accounts/{gl_id}", response_model=GLAccountOut)
def update_gl(gl_id: int, acct: GLAccountIn, db: Session = Depends(get_db)):
    row = db.get(GLAccount, gl_id)
    if not row:
        raise HTTPException(404, "Not found")
    for k, v in acct.model_dump().items():
        setattr(row, k, v)
    db.commit()
    db.refresh(row)
    return row


@app.delete("/config/gl-accounts/{gl_id}", status_code=204)
def delete_gl(gl_id: int, db: Session = Depends(get_db)):
    row = db.get(GLAccount, gl_id)
    if row:
        # Soft delete: deactivate so historical bills referencing the code stay valid.
        row.is_active = False
        db.commit()
    return Response(status_code=204)


@app.get("/config/agent", response_model=AgentConfigOut)
def get_agent_config(db: Session = Depends(get_db)):
    cfg = db.scalar(select(AgentConfig).where(AgentConfig.is_active.is_(True)))
    if not cfg:
        raise HTTPException(404, "No active config")
    return cfg


@app.get("/config/agent/versions", response_model=list[AgentConfigOut])
def list_agent_configs(db: Session = Depends(get_db)):
    return db.scalars(select(AgentConfig).order_by(AgentConfig.version.desc())).all()


@app.put("/config/agent", response_model=AgentConfigOut)
def update_agent_config(cfg_in: AgentConfigIn, db: Session = Depends(get_db)):
    """Save a NEW version and activate it (previous versions retained for revert)."""
    latest = db.scalar(select(AgentConfig).order_by(AgentConfig.version.desc()))
    next_version = (latest.version + 1) if latest else 1
    for c in db.scalars(select(AgentConfig).where(AgentConfig.is_active.is_(True))).all():
        c.is_active = False
    cfg = AgentConfig(
        version=next_version,
        instructions=cfg_in.instructions,
        routing_rules=cfg_in.routing_rules,
        is_active=True,
        note=cfg_in.note,
        created_by="ap_manager",
    )
    db.add(cfg)
    db.commit()
    db.refresh(cfg)
    return cfg


@app.post("/config/agent/{version}/activate", response_model=AgentConfigOut)
def activate_agent_config(version: int, db: Session = Depends(get_db)):
    """Revert to a previous version."""
    target = db.scalar(select(AgentConfig).where(AgentConfig.version == version))
    if not target:
        raise HTTPException(404, "Version not found")
    for c in db.scalars(select(AgentConfig).where(AgentConfig.is_active.is_(True))).all():
        c.is_active = False
    target.is_active = True
    db.commit()
    db.refresh(target)
    return target


@app.get("/health")
def health():
    return {"status": "ok", "model": settings.agent_model}
