"""Pydantic schemas for the HTTP API (request/response serialization)."""

import json
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class LineItemOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    description: str
    quantity: float | None
    unit_price: float | None
    amount: float
    gl_code: str | None
    gl_confidence: float
    needs_review: bool
    reasoning: str | None


class BillOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: int
    vendor: str | None
    invoice_number: str | None
    invoice_date: str | None
    due_date: str | None
    currency: str
    is_credit_memo: bool
    applies_to_invoice: str | None
    subtotal: float
    tax: float
    other_charges: float
    total: float
    status: str
    is_duplicate: bool
    duplicate_of_bill_id: int | None
    confidence: float
    agent_reasoning: str | None
    review_flags: list[str]
    pages: str | None
    segment_index: int
    created_at: datetime
    locked_by: str | None
    locked_at: datetime | None
    line_items: list[LineItemOut]

    @field_validator("review_flags", mode="before")
    @classmethod
    def _parse_flags(cls, v):
        # review_flags is stored as a JSON string column; parse it into a list.
        if isinstance(v, str):
            return json.loads(v) if v else []
        return v or []


class IssueOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    document_id: int
    kind: str
    reason: str
    resolved: bool
    created_at: datetime


class DocumentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    filename: str
    source: str
    status: str
    error: str | None
    page_count: int
    created_at: datetime


class IngestResponse(BaseModel):
    document_id: int
    status: str
    message: str


# --- Config (prompt-as-configuration) ---


class GLAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    code: str
    name: str
    description: str
    is_active: bool


class GLAccountIn(BaseModel):
    code: str
    name: str
    description: str
    is_active: bool = True


class AgentConfigOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    version: int
    instructions: str
    routing_rules: str
    is_active: bool
    note: str | None
    created_at: datetime


class AgentConfigIn(BaseModel):
    instructions: str
    routing_rules: str
    note: str | None = None


# --- Review actions ---


class LineItemEdit(BaseModel):
    id: int
    gl_code: str | None = None
    description: str | None = None
    quantity: float | None = None
    unit_price: float | None = None
    amount: float | None = None
    needs_review: bool | None = None


class BillEdit(BaseModel):
    vendor: str | None = None
    invoice_number: str | None = None
    invoice_date: str | None = None
    due_date: str | None = None
    tax: float | None = None
    other_charges: float | None = None
    total: float | None = None
    is_credit_memo: bool | None = None
    line_items: list[LineItemEdit] = []
    reviewed_by: str | None = None
