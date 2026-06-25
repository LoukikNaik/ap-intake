"""Structured outputs for each agent stage.

Each agent is forced to return one of these via `output_type`, so the orchestrator gets
validated objects, never free text it has to parse.
"""

from typing import Literal, Optional

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# Stage 1 — Triage / Split
# ---------------------------------------------------------------------------


class Segment(BaseModel):
    index: int = Field(description="0-based index of this invoice within the PDF.")
    pages: list[int] = Field(description="1-based page numbers belonging to this invoice.")
    vendor_hint: Optional[str] = Field(default=None, description="Best guess at the vendor.")
    invoice_number_hint: Optional[str] = Field(default=None, description="Best guess at the invoice #.")
    is_credit_memo: bool = Field(default=False, description="True if this segment is a credit memo.")
    reasoning: str = Field(description="Why this is a distinct invoice / where the boundary is.")


class TriageResult(BaseModel):
    document_type: Literal["invoice", "credit_memo", "not_an_invoice"]
    segments: list[Segment] = Field(
        default_factory=list,
        description="One per distinct invoice/credit memo. Empty if not an invoice.",
    )
    issue_reason: Optional[str] = Field(
        default=None, description="If not an invoice, explain what the document actually is."
    )


# ---------------------------------------------------------------------------
# Stage 2 — Extraction (one invoice segment -> fields)
# ---------------------------------------------------------------------------


class ExtractedLine(BaseModel):
    description: str
    quantity: Optional[float] = None
    unit_price: Optional[float] = None
    amount: float = Field(description="Line total. NEGATIVE for credit-memo lines.")


class ExtractedInvoice(BaseModel):
    vendor: Optional[str] = None
    invoice_number: Optional[str] = None
    invoice_date: Optional[str] = None
    due_date: Optional[str] = None
    currency: str = "USD"
    is_credit_memo: bool = False
    applies_to_invoice: Optional[str] = Field(
        default=None, description="For a credit memo, the prior invoice number it applies to."
    )
    subtotal: float = Field(
        default=0.0, description="Sum of line items before tax (pre-tax subtotal). 0 if not shown."
    )
    tax: float = Field(
        default=0.0,
        description="Total sales tax on the invoice, captured separately (NOT as a line item). "
        "Negative for a credit memo. 0 if there is no tax.",
    )
    other_charges: float = Field(
        default=0.0,
        description="Bottom-line charges/adjustments not tied to a single line item — e.g. an "
        "invoice-level freight or discount. Line-attributable surcharges stay as line items. 0 if none.",
    )
    total: float = Field(description="Document grand total (lines + tax + other_charges). NEGATIVE for a credit memo.")
    line_items: list[ExtractedLine] = Field(default_factory=list)
    confidence: float = Field(description="0-1. Lower for scanned/skewed/low-quality documents.")
    notes: Optional[str] = Field(default=None, description="Anything a reviewer should know.")


# ---------------------------------------------------------------------------
# Stage 3 — GL mapping (line items -> GL codes / flags)
# ---------------------------------------------------------------------------


class MappedLine(BaseModel):
    index: int = Field(description="Index into the input line_items list.")
    gl_code: Optional[str] = Field(default=None, description="A GL code, or null if no clean match.")
    gl_confidence: float = Field(description="0-1 confidence in this mapping.")
    needs_review: bool = Field(description="True if ambiguous, fits 2+ codes, or fits none.")
    reasoning: str = Field(description="Why this code, or why it was flagged.")


class GLMappingResult(BaseModel):
    lines: list[MappedLine]
