# AP Intake Platform — Lonestar Commercial Construction

An agent-first accounts-payable intake platform. Vendors' invoice PDFs come in via an API or a
UI upload; an **OpenAI Agents SDK** workflow (running gpt-5-mini through LiteLLM) classifies,
splits, extracts, maps line items to GL accounts, and flags anything uncertain. Results land in a
**reviewable queue** where an AP clerk verifies, edits, and approves or rejects — and the AP
manager can retune the agent's behaviour from the UI **without an engineer**.

> Built as a take-home. The judgment is done by agents, not `if/else`. See
> [Design decisions](#design-decisions) for the *why*.

---

## Quick start (one command)

```bash
cp .env.example .env          # then put your OPENAI_API_KEY in .env
docker compose up --build
```

- UI:      http://localhost:5173
- API:     http://localhost:8000  (docs at `/docs`)
- Postgres: localhost:5432

That's it — Postgres, the FastAPI backend (auto-creates tables + seeds Lonestar's GL accounts and
the default agent policy), and the React UI all come up together.

### Smoke test with the provided curl commands

The provided `test-commands.sh` works **unchanged** — our endpoint is `POST /invoices` with a
multipart `file` field, which is exactly its default:

```bash
./ciridae-assets/ciridae-takehome-assets/test-commands.sh
# then watch the Review queue + Issues tabs in the UI
```

Ingestion is **async**: each POST returns `202` with a `document_id`; processing happens in the
background and the bill(s) appear in the queue a few seconds later.

---

## Architecture

```
  API POST /invoices ─┐
                      ├─► store PDF (sha256 idempotency) ─► async background processing
  UI upload ──────────┘
                                   │
        ┌──────────────────────────▼───────────────────────────────────┐
        │  ORCHESTRATOR — deterministic Python (app/pipeline.py)         │
        │  contains ZERO business decisions: it sequences + validates     │
        │                                                                │
        │  STAGE 1  Triage & Split   [agent]  -> doc type + N segments    │
        │             not an invoice -> issues queue (+ reasoning)        │
        │   ── fan out per segment, in parallel ──                        │
        │  STAGE 2  Extraction       [agent]  -> fields + line items      │
        │  STAGE 3  GL Mapping       [agent + lookup_gl_accounts tool]    │
        │  STAGE 4  Validate + Dedup [code]   -> math/sign checks, dup    │
        │  STAGE 5  Route            [code]   -> ready | review | dup      │
        └──────────────────────────┬───────────────────────────────────┘
                                   ▼
        Review queue (UI) ─► verify / edit / approve / reject
                          ─► every correction saved as labeled feedback
```

Each box is either an **[agent]** making a judgment or **[code]** doing sequencing/validation/
persistence. That split is the whole design — see below.

**Stack:** FastAPI · OpenAI Agents SDK · LiteLLM · Postgres + SQLAlchemy · React + TS + Vite +
Tailwind. PDFs are rendered to page images (PyMuPDF) and read natively by the vision model — no
OCR step.

---

## What the agent handles (edge cases)

| Sample PDF | Behaviour |
|---|---|
| `01_clean_invoice` | Extracts vendor/inv#/date/lines, maps each line to a GL code. |
| `02_multipage_invoice` | One bill across both pages (not two). |
| `03_two_invoices_one_pdf` | Triage splits into **two** bills (fan-out). |
| `04_not_an_invoice` | Routed to the **Issues** queue with the agent's reasoning. |
| `05_duplicate_of_01` | Flagged as a duplicate by vendor + invoice number (not file hash). |
| `06_credit_memo` | Recognised as a credit memo; total kept negative; linked to prior invoice. |
| `07_scanned_invoice` | Read natively; lower confidence → routed to review. |
| `08_ambiguous_lines` | Vague lines get `gl_code=null` + flagged, never guessed. |

---

## Prompt-as-configuration (the **Agent config** tab)

Everything that determines behaviour is editable by a non-engineer:

- **Agent policy** — the instructions prepended to every stage. Saving creates a **new version**;
  previous versions are listed and **revertible** (a bad edit can't permanently break intake).
- **Routing rules** — free-text policy for when to flag vs. auto-approve.
- **GL accounts** — add / rename / edit descriptions / deactivate. The **description is the
  agent's classification signal**, so editing it directly retunes GL mapping. Deactivation is a
  soft-delete so historical bills referencing a code stay valid.

Config is loaded from the DB **per run**, so the next invoice processed uses the new behaviour —
no redeploy.

---

## Design decisions

**Workflow of agents, not one autonomous agent.** Invoice intake is a known, repeatable process,
so the *shape* is fixed in deterministic code while each *step* is a bounded agent with the
minimum tools it needs. This buys determinism, auditability, per-stage evaluation, bounded cost,
and tight per-step guardrails — all things an unconstrained ReAct loop would cost us. "Agent-first"
means judgment by LLMs, not maximal autonomy.

**The orchestrator makes no business decisions.** It sequences stages, runs arithmetic/sign
validation, detects duplicates, and persists. Every judgment — classify, split, extract, map,
when-to-flag — lives in an agent's editable prompt/tools. Code is plumbing; agents are the brain.
The validation code is *verification* of the agent's work, not business logic.

**Duplicate detection & math live in code, not an agent.** They're deterministic; making them
agents would be over-engineering. Dedup matches on normalised vendor + invoice number (so
`ABC Lumber` == `ABC Lumber LLC`), which is why `05` is caught despite different bytes.

**Model is configuration.** Everything runs through LiteLLM; switch gpt-5-mini ↔ Claude by editing
`AGENT_MODEL` in `.env`, no code change.

**Honest uncertainty over guessing.** Low confidence (scans) and ambiguous GL lines are flagged
with reasons rather than guessed — the customer explicitly values this.

---

## What I'd do with more time

- **Evals + config test-bench:** a golden set of past invoices so a GL/policy edit can be checked
  for regressions *before* saving. Configurability without evals is a footgun; the feedback table
  already captures the labeled data to seed it.
- **Segmentation review UX:** let a clerk merge/split the agent's proposed segments in the UI
  (the API stores page ranges; the merge/split actions are the missing piece).
- **Model routing / escalation:** auto-retry low-confidence extractions on a stronger model
  (the `escalation_model` setting is wired but not yet invoked).
- **A durable queue** (RQ/Celery) instead of FastAPI background tasks, with retries + dead-letter.
- **Job assignment** (construction needs cost attributed to a job, not just a GL code).
- **Auth + multi-tenancy:** the schema is already config-driven, so multi-tenant is mostly adding
  `tenant_id` + scoping, not a rewrite.

---

## Project layout

```
backend/
  app/
    main.py            FastAPI routes (ingest, review, issues, config)
    pipeline.py        deterministic orchestrator (the workflow)
    agents/
      definitions.py   triage / extract / GL-map agents
      tools.py         lookup_gl_accounts (the one agent tool)
      schemas.py       structured outputs per stage
      model.py         LiteLLM model factory (swappable)
      context.py       run context (GL accounts injected to tools)
    models.py          SQLAlchemy tables
    schemas.py         API request/response models
    pdf_utils.py       PDF -> page images
    seed.py            seeds GL accounts + default policy
frontend/
  src/pages/           ReviewQueue, BillDetail, Issues, Config
docker-compose.yml     one-command bring-up
```

## Running the backend without Docker (optional)

```bash
cd backend
uv sync
export DATABASE_URL=postgresql+psycopg://ap:ap@localhost:5432/ap_intake
export OPENAI_API_KEY=sk-...
uvicorn app.main:app --reload
```
