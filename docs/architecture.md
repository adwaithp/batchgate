# Architecture

## Components

```
            browser
               │
     ┌─────────▼─────────┐
     │ frontend (Vue 3)  │  served by Caddy in production; Vite in development
     └─────────┬─────────┘
               │ /api
     ┌─────────▼─────────┐        ┌────────────┐
     │ api (FastAPI)     │───────▶│ PostgreSQL │
     └───┬───────────▲───┘        └─────▲──────┘
  enqueue│           │progress          │
     ┌───▼───────────┴───┐              │
     │ Redis             │              │
     └───┬───────────▲───┘              │
         │           │publish           │
     ┌───▼───────────┴───┐              │
     │ worker (arq)      │──────────────┘
     └─────────┬─────────┘
               │ reads COAs
           Claude API
```

- **api**: REST endpoints, authentication, the workflow, the copilot, and server-sent events that
  stream COA reading progress.
- **worker**: reads uploaded COAs with Claude outside the upload request, saves the values and
  runs the check.
- **Redis**: the job queue and live progress events. Optional: without it the API reads COAs
  inside the upload request and the event stream polls the database.
- **PostgreSQL**: all data. Tables are created only by Alembic migrations.
- **MCP server**: a separate stdio process (`python -m app.mcp_server`) for Claude Desktop or
  Claude Code, using the same services and database.

## The core rule: AI reads, code decides

| Concern | Who does it |
|---|---|
| Turning a COA into values | Claude (structured output) |
| Checking those values against the PDF text | Code (`extraction/verify.py`) |
| Comparing values with limits, converting units, deciding | Code (`rules/engine.py`) |
| Explaining a decision, drafting a follow-up | Claude (copilot), with no write tools |
| Finding relevant knowledge | Code (BM25 search) |

When anything is uncertain the engine answers REVIEW, never RELEASE.

## Data model

```
Customer ─< Order ─< OrderLine >─ Spec (versioned, per customer + product + grade)
                         │
                         └─< Batch ─< COADocument (factory or lab) ─< COAResult
                               ├─< Verdict      (one per engine check)
                               └─< BatchAction  (decisions people take)

Product, Supplier (factory or lab), User ─< customers (sales scope)
KnowledgeDocument ─< KnowledgePassage >─ QCCase
AuditLog (append-only)
```

- A **spec** is never edited in place: a change creates the next version and retires the old one.
  Order lines keep the version agreed when the order was placed.
- A **batch** may arrive before anyone knows its order line; a person then assigns it.
- Uploading a new COA from the same source supersedes the previous one; old COAs are kept.
- A **verdict** stores the full engine result (per-parameter readings, identity checks, findings),
  so every past decision can be explained.

## Request flows

### COA upload

1. `POST /api/batches/{id}/coas` calls `ingest_coa()`, the single entry point for every COA source.
2. The file is stored by its SHA-256 digest, and a job is queued for the worker.
3. The response is a server-sent event stream: `received`, `queued`, `reading`, then a final
   `done`, `failed`, `manual` or `waiting` event.
4. The worker calls `read_coa()`, checks each value against the PDF text, saves the values with
   `save_coa_data()` and runs `run_check()`.
5. The engine's verdict moves the batch to `pending_approval`, `pending_review` or `on_hold`.

### Decision

`POST /api/batches/{id}/actions` validates the action against the batch status, the user's
permission and the four-eyes rule (`blocked_reason()`), records a `BatchAction` and an audit entry,
and updates the batch and its order's status.

### Copilot

`POST /api/batches/{id}/copilot` runs a tool-use loop of up to 10 turns. Claude calls read-only
tools, then submits a brief through `submit_brief`. The brief is validated with Pydantic and its
citations are checked against the passages searches returned. Nothing is written except an audit
entry.

## Project layout

```
backend/
  app/
    api/            FastAPI dependencies and routes, one module per area
    core/           settings, database, migrations helpers, security, permissions
    models/         SQLAlchemy models
    schemas/        Pydantic request and response models, one module per area
    services/       business logic
      batches.py    the batch workflow: ingest, check, decide
      rules/        the rules engine (no database, no AI)
      extraction/   COA reading, the PDF text check, progress events
      copilot.py    the review copilot
      knowledge.py  documents, cases and search
    main.py         application factory
    worker.py       arq worker
    mcp_server.py   MCP server
    seed.py         demo data
  migrations/       Alembic migrations
  tests/
frontend/
  src/
    api/            API client
    components/     shared and batch components
    layouts/        application shell
    stores/         Pinia stores
    views/          one component per page
    labels.ts       status labels and formatting
    types.ts        TypeScript mirrors of the API schemas
evals/              eval scripts, inputs and results
docs/               documentation
```
