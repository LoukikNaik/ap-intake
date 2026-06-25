"""Function tools the agents can call.

Design note: duplicate detection and arithmetic validation are deterministic and live in
the orchestrator as plain code (see app/pipeline.py) — not everything needs an LLM. The
one judgment-relevant lookup the agent genuinely can't know on its own is the *current,
manager-edited* GL account list, so that's exposed as a tool here.
"""

from agents import RunContextWrapper, function_tool

from app.agents.context import PipelineContext


@function_tool
def lookup_gl_accounts(ctx: RunContextWrapper[PipelineContext]) -> str:
    """Return the current chart of GL accounts (code, name, description).

    Call this before assigning GL codes so you always map against the latest list the
    AP manager has configured. Map each line item to exactly one code based on its
    description. If a line fits two codes or none, do NOT guess — flag it for review.
    """
    accounts = ctx.context.gl_accounts
    if not accounts:
        return "No GL accounts are configured."
    return "\n".join(f"{a.code} — {a.name}: {a.description}" for a in accounts)
