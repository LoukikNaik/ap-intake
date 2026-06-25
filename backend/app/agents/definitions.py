"""Agent definitions for each stage of the workflow.

Each stage is a BOUNDED agent: narrow instructions, the minimum tools it needs, and a
strict structured output. The orchestrator (app/pipeline.py) sequences them in
deterministic Python — agency lives in the nodes, determinism lives between them.

The AP manager's editable `policy` text (from AgentConfig.instructions) is prepended to
every stage, so a non-engineer can steer behaviour across the whole pipeline from one
place. Stage-specific mechanics stay in code.
"""

from agents import Agent

from app.agents.model import get_model
from app.agents.schemas import ExtractedInvoice, GLMappingResult, TriageResult
from app.agents.tools import lookup_gl_accounts

# ---------------------------------------------------------------------------

TRIAGE_GUIDANCE = """
You are the TRIAGE & SPLIT stage of an accounts-payable intake pipeline for a commercial
construction company. You are given the page images of ONE uploaded PDF.

Your job is ONLY to classify and segment — do not extract line items here.

1. Decide the document type:
   - 'invoice'        — a normal vendor invoice (amount owed to the vendor).
   - 'credit_memo'    — a NEGATIVE document (vendor owes us; returned equipment, overage,
                        billing correction). Often references a prior invoice.
   - 'not_an_invoice' — anything else (a W-9 form, a statement, marketing, a letter).
                        Return empty segments and a clear issue_reason.

2. A single PDF may contain MULTIPLE distinct invoices. Produce one Segment per distinct
   invoice. A new invoice begins ONLY when the vendor OR the invoice number changes, or a
   fresh invoice header with its own totals starts. The SAME invoice continued across
   pages (same vendor + invoice number, continued line-item table) is ONE segment.

3. For each segment, record its 1-based page numbers, vendor/invoice-number hints, whether
   it is a credit memo, and your reasoning for the boundary (this is shown to reviewers).
"""

EXTRACT_GUIDANCE = """
You are the EXTRACTION stage. You are given the page images for ONE invoice (a single
vendor invoice or credit memo). Extract its fields faithfully.

- Capture vendor, invoice number, invoice date, due date, currency, and every line item
  (description, quantity, unit price, line amount) across ALL the pages provided.
- Capture SALES TAX in the `tax` field, NOT as a line item. Capture the pre-tax `subtotal` if
  shown. Put any invoice-level charge/adjustment that isn't tied to a specific line (e.g. a
  bottom-line freight or discount) in `other_charges`. A surcharge clearly attached to one line
  (delivery of a specific item, a Saturday surcharge on a delivery) STAYS a line item.
- The grand `total` should equal sum(line_items) + tax + other_charges. Make sure these reconcile.
- For a credit memo, set is_credit_memo=true, make the total, tax, and relevant line amounts
  NEGATIVE, and capture the prior invoice it applies to (applies_to_invoice).
- Do not invent values. If a field is genuinely absent, leave it null.
- Set an honest confidence (0-1). Lower it for scanned, skewed, or low-quality images, or
  when text is hard to read. When unsure, prefer a lower confidence over guessing.
"""

GL_GUIDANCE = """
You are the GL-MAPPING stage. You are given the line items extracted from one invoice.

- First call the lookup_gl_accounts tool to get the current chart of accounts.
- Map EACH line item to exactly one GL code based on its description.
- A line that could plausibly fit TWO codes, or fits NONE, is a FLAG — not a guess. For
  those, set gl_code=null, needs_review=true, and explain the ambiguity in reasoning.
- Sales tax is handled separately (not a line item here). A surcharge attached to a specific
  line follows the GL code of the line it relates to.
- Return one MappedLine per input line item, in order, referencing its index.
"""


def _compose(policy: str, guidance: str) -> str:
    policy = (policy or "").strip()
    if policy:
        return f"{guidance.strip()}\n\n--- AP MANAGER POLICY (editable) ---\n{policy}"
    return guidance.strip()


def build_triage_agent(policy: str) -> Agent:
    return Agent(
        name="Triage & Split",
        instructions=_compose(policy, TRIAGE_GUIDANCE),
        model=get_model(),
        output_type=TriageResult,
    )


def build_extract_agent(policy: str) -> Agent:
    return Agent(
        name="Extraction",
        instructions=_compose(policy, EXTRACT_GUIDANCE),
        model=get_model(),
        output_type=ExtractedInvoice,
    )


def build_gl_agent(policy: str) -> Agent:
    return Agent(
        name="GL Mapping",
        instructions=_compose(policy, GL_GUIDANCE),
        model=get_model(),
        tools=[lookup_gl_accounts],
        output_type=GLMappingResult,
    )
