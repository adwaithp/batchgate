# BatchGate

An AI quality gate for specialty chemical batches.

A partner factory makes a batch, the factory and an independent lab each send a certificate of analysis (COA), and someone has to check every number against what the customer ordered before the batch ships. BatchGate reads those COAs, checks them against the customer's spec, and decides: **release**, **hold**, or **ask a human**.

> Status: the release engine and the batch workflow work end to end, with COA values typed in by hand. Next: Claude reads the COA PDFs and fills those values in.

## How it is built

| Part | Stack |
| --- | --- |
| API | FastAPI, SQLAlchemy 2, Pydantic, JWT auth |
| Web app | Vue 3, TypeScript, Vite, Pinia |
| Storage | SQLite (zero setup) |
| COA reading | Claude (vision) — *coming next* |

The rule the whole design follows: **AI reads, code decides.** The model turns messy PDFs into structured data; comparing values against limits and making the release decision is plain, tested code.

## What happens to a batch

```
COA arrives (upload today; email or ERP later)
      ↓
ingest_coa()            one entry point for every source
      ↓
values in               typed by a person now, read by Claude next
      ↓
rules engine            spec vs factory COA vs lab COA → release / hold / review, with reasons
      ↓
people decide           analyst proposes, a different QC manager approves (four eyes)
      ↓
order line ready        released quantity rolls up to the customer's order
```

The engine (`backend/app/services/rules/`) is plain Python with no database and no AI, so it is fast to test:

- **Hold** when a critical parameter is out of spec, the CAS number is wrong, or the batch has expired.
- **Review** when anything is uncertain: a missing or unreadable value, a unit that can't be converted (% w/v vs % w/w), a "< 20" reading against a limit of 10, a low-confidence read, factory and lab disagreeing beyond tolerance, a batch number that doesn't match, or a COA still to come.
- **Release** only when everything passed and nothing is uncertain. A QC manager still approves.

Units are converted in code (ppm ↔ %, mg/kg ↔ ppm), never by the model. Each parameter can set how far factory and lab may differ; the default is 2 % relative.

A batch that arrives without an order line is checked against every open line for that product, and BatchGate suggests the one it fits. A person confirms, because shipping the wrong grade is worse than waiting.

## Roles

Each role sees a different app. Routes check permissions, not role names, so the mapping lives in one file (`backend/app/core/permissions.py`).

| Role | Can |
| --- | --- |
| QC Analyst | Upload COAs, run checks, propose a release, put a batch on hold |
| QC Manager | Everything an analyst can, plus approve releases (second pair of eyes), edit specs, read the audit log |
| Sales | Read-only view of their own customers' orders |
| Admin | Everything |

## Run it locally

You need [uv](https://docs.astral.sh/uv/) and Node 20+.

```bash
# API  → http://localhost:8000/docs
cd backend
uv sync
uv run python -m app.seed        # demo users, customers, specs, orders
uv run uvicorn app.main:app --reload

# Web app → http://localhost:5173   (in a second terminal)
cd frontend
npm install
npm run dev
```

Sign in with one click as any demo account on the login page. All demo passwords are `demo1234`.

After pulling changes that touch the data model, rebuild the demo data:

```bash
cd backend && uv run python -m app.seed --reset
```

Run the tests:

```bash
cd backend && uv run pytest
```

## Demo data

All companies are fictional and all spec limits are illustrative. The seed creates five batches through the real workflow, so the engine decides each one:

| Batch | What the engine found |
| --- | --- |
| FC-2611-07 | **Hold.** The lab measured insoluble matter at 0.14 % against a max of 0.1 %. |
| FC-2611-12 | Registered, waiting for its COAs. |
| MT-2610-31 | **Release.** Clean on both COAs, waiting for a QC manager. |
| MT-2611-04 | No order line. It fits the 40 % grade on PO-1042 line 3 and fails the 78 % grade on line 2. |
| PO-2611-A | **Review.** Both COAs pass, but factory and lab disagree on assay by more than the 1 % allowed. |

PO-1042 is deliberately awkward: MEA Triazine appears on two lines at two different grades, so a batch must be checked against the spec of *its* line, not just its product name.
