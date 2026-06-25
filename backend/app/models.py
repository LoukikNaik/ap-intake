"""SQLAlchemy models.

Data model rationale:
- A `Document` is one uploaded PDF. ONE document can produce MANY `Bill`s (the
  "multiple invoices in one PDF" case) or ZERO (the "not an invoice" case).
- `Bill` -> many `LineItem`s. Each line item carries its own GL mapping + flags so the
  reviewer can act at line granularity.
- `GLAccount` and `AgentConfig` are EDITABLE CONFIG (the prompt-as-configuration surface).
  AgentConfig is versioned so a bad edit can be rolled back; bills snapshot the config
  version used so historical records stay explainable.
- `Issue` holds non-invoice documents (and hard failures) with the agent's reasoning.
"""

from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    LargeBinary,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(primary_key=True)
    filename: Mapped[str] = mapped_column(String(512))
    source: Mapped[str] = mapped_column(String(16), default="api")  # api | ui
    sha256: Mapped[str] = mapped_column(String(64), index=True)  # request idempotency
    raw: Mapped[bytes] = mapped_column(LargeBinary)  # original PDF, so we can reprocess
    page_count: Mapped[int] = mapped_column(Integer, default=0)
    # queued | processing | processed | failed
    status: Mapped[str] = mapped_column(String(16), default="queued", index=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    bills: Mapped[list["Bill"]] = relationship(back_populates="document", cascade="all, delete-orphan")
    issues: Mapped[list["Issue"]] = relationship(back_populates="document", cascade="all, delete-orphan")


class Bill(Base):
    __tablename__ = "bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))

    vendor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    vendor_normalized: Mapped[str | None] = mapped_column(String(512), index=True, nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(128), index=True, nullable=True)
    invoice_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    due_date: Mapped[str | None] = mapped_column(String(32), nullable=True)
    currency: Mapped[str] = mapped_column(String(8), default="USD")

    is_credit_memo: Mapped[bool] = mapped_column(Boolean, default=False)
    applies_to_invoice: Mapped[str | None] = mapped_column(String(128), nullable=True)
    subtotal: Mapped[float] = mapped_column(Float, default=0.0)
    tax: Mapped[float] = mapped_column(Float, default=0.0)
    other_charges: Mapped[float] = mapped_column(Float, default=0.0)
    total: Mapped[float] = mapped_column(Float, default=0.0)

    # needs_review | ready_to_approve | approved | rejected | duplicate
    status: Mapped[str] = mapped_column(String(24), default="needs_review", index=True)
    is_duplicate: Mapped[bool] = mapped_column(Boolean, default=False)
    duplicate_of_bill_id: Mapped[int | None] = mapped_column(ForeignKey("bills.id"), nullable=True)

    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    agent_reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)
    review_flags: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON list of strings
    pages: Mapped[str | None] = mapped_column(String(64), nullable=True)  # e.g. "[1,2]"
    segment_index: Mapped[int] = mapped_column(Integer, default=0)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(128), nullable=True)

    # Review lease: prevents two clerks from working the same bill simultaneously.
    locked_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
    locked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    document: Mapped["Document"] = relationship(back_populates="bills")
    line_items: Mapped[list["LineItem"]] = relationship(
        back_populates="bill", cascade="all, delete-orphan", order_by="LineItem.id"
    )


class LineItem(Base):
    __tablename__ = "line_items"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"))

    description: Mapped[str] = mapped_column(Text)
    quantity: Mapped[float | None] = mapped_column(Float, nullable=True)
    unit_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    amount: Mapped[float] = mapped_column(Float, default=0.0)

    gl_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    gl_confidence: Mapped[float] = mapped_column(Float, default=0.0)
    needs_review: Mapped[bool] = mapped_column(Boolean, default=False)
    reasoning: Mapped[str | None] = mapped_column(Text, nullable=True)

    bill: Mapped["Bill"] = relationship(back_populates="line_items")


class GLAccount(Base):
    """Editable chart of accounts. The DESCRIPTION is the agent's classification signal."""

    __tablename__ = "gl_accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(16), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(256))
    description: Mapped[str] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class AgentConfig(Base):
    """Versioned agent behaviour config. Only one row is `is_active`.

    Editing instructions / routing rules in the UI creates a NEW version; the previous
    one is retained so a bad edit can be reverted. Bills snapshot `version`.
    """

    __tablename__ = "agent_config"

    id: Mapped[int] = mapped_column(primary_key=True)
    version: Mapped[int] = mapped_column(Integer, index=True)
    instructions: Mapped[str] = mapped_column(Text)
    routing_rules: Mapped[str] = mapped_column(Text)  # human-editable policy text
    is_active: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    note: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)


class Issue(Base):
    """Non-invoice documents and hard failures, with the agent's reasoning attached."""

    __tablename__ = "issues"

    id: Mapped[int] = mapped_column(primary_key=True)
    document_id: Mapped[int] = mapped_column(ForeignKey("documents.id"))
    kind: Mapped[str] = mapped_column(String(32), default="not_an_invoice")  # not_an_invoice | error
    reason: Mapped[str] = mapped_column(Text)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    document: Mapped["Document"] = relationship(back_populates="issues")


class Feedback(Base):
    """Captures human corrections (agent value vs human value) as labeled data.

    This is the compounding asset: corrections feed prompt tuning + an eval golden set.
    """

    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("bills.id"))
    line_item_id: Mapped[int | None] = mapped_column(ForeignKey("line_items.id"), nullable=True)
    field: Mapped[str] = mapped_column(String(64))
    agent_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    human_value: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    created_by: Mapped[str | None] = mapped_column(String(128), nullable=True)
