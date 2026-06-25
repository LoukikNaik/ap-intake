"""Seed the editable config: Lonestar's GL accounts + a default agent policy.

These are SEEDS for the editable config, not hardcoded behaviour — the AP manager can
change all of it from the UI afterwards.
"""

from sqlalchemy import select

from app.db import SessionLocal
from app.models import AgentConfig, GLAccount

GL_ACCOUNTS = [
    ("5100", "Materials — Lumber & Framing",
     "Dimensional lumber, sheathing, framing hardware, framing nails and fasteners. Structural wood."),
    ("5110", "Materials — Concrete & Masonry",
     "Ready-mix concrete, concrete delivery and pumping, rebar and mesh, masonry block, mortar, "
     "testing services tied to a pour."),
    ("5120", "Materials — Electrical Supplies",
     "Wire and cable, conduit, breakers and panels, junction boxes, electrical fittings and devices."),
    ("5130", "Materials — Plumbing Supplies",
     "Copper and PEX tubing, fittings, valves, fixtures, plumbing-specific hardware."),
    ("5200", "Subcontractor Labor",
     "Labor invoiced by subcontractors (electrical contractors, framers, concrete crews). "
     "Time and materials or fixed-fee labor charges."),
    ("5300", "Equipment Rental",
     "Rental of construction equipment — skid steers, lifts, excavators, compressors, generators. "
     "Includes delivery fees and rental-period surcharges."),
    ("5400", "Job Site Supplies",
     "Consumables and small tools used on-site that aren't structural materials — tarps, safety "
     "supplies, hand tools, signage, temporary fencing."),
    ("5500", "Site Services",
     "Site preparation services: excavation, grading, trenching, hauling, compaction testing, "
     "demolition. Distinct from materials in 5110."),
    ("6100", "Office Supplies",
     "Office consumables — paper, pens, printer supplies, small office equipment. Not job-site related."),
    ("6200", "Vehicle — Fuel & Maintenance",
     "Fuel, oil changes, repairs, and maintenance for the company vehicle fleet."),
    ("6400", "Professional Services",
     "Outside professionals — legal, accounting, consulting, engineering services not embedded in a "
     "subcontract."),
    ("7100", "Insurance",
     "Insurance premiums and related fees — general liability, builders risk, workers comp."),
]

DEFAULT_POLICY = """\
Lonestar Commercial Construction — AP intake agent policy.

This text steers the AGENT's judgment only. Duplicate detection, math/total reconciliation,
sign checks, and routing are handled deterministically in code — they are not the agent's job,
so don't restate them here.

- Accuracy on common cases, honest uncertainty on edge cases: when unsure, FLAG for human
  review and explain why — never guess.
- Classify each document: a normal invoice, a credit memo (negative — the vendor owes us),
  or not an invoice (e.g. a W-9, statement, or letter).
- A single PDF may contain several distinct invoices — produce one bill per invoice; a
  multi-page single invoice stays one bill.
- Map each line item to exactly one GL account based on its description. A line that could
  fit two accounts, or none, is a FLAG (leave the GL code empty) — not a guess.
- Recognise credit memos and keep their amounts negative.
- Set an honest confidence; lower it for scanned, skewed, or low-quality documents.
"""

# NOTE: routing is deterministic (see app/pipeline.py). This text documents that behaviour
# for the AP manager's transparency; it is not fed to the agent.
DEFAULT_ROUTING_RULES = """\
Handled automatically by the system (not by the agent):
- A bill with no flags and confidence >= the review threshold is 'ready to approve'.
- Any flag (math/total mismatch, qty x price mismatch, missing field, unmapped or ambiguous
  line, low confidence, or a suspected duplicate) sends the bill to the review queue.
- A document that is not an invoice goes to the issues queue with the agent's reasoning.
"""


def seed() -> None:
    db = SessionLocal()
    try:
        # GL accounts
        existing = {a.code for a in db.scalars(select(GLAccount)).all()}
        for code, name, desc in GL_ACCOUNTS:
            if code not in existing:
                db.add(GLAccount(code=code, name=name, description=desc, is_active=True))

        # Default agent config (version 1) if none exists
        if not db.scalar(select(AgentConfig)):
            db.add(
                AgentConfig(
                    version=1,
                    instructions=DEFAULT_POLICY,
                    routing_rules=DEFAULT_ROUTING_RULES,
                    is_active=True,
                    note="Seed default policy",
                    created_by="system",
                )
            )
        db.commit()
    finally:
        db.close()
