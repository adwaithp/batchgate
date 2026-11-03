# BatchGate: context for coding assistants

BatchGate is an AI quality gate for specialty chemical batches. Claude reads certificates of
analysis (COAs) from the factory and an independent lab; a rules engine compares them with the
customer's spec and decides **release**, **hold** or **review**; people approve releases with a
four-eyes rule. A review copilot explains batches that need a person, citing a knowledge base of
quality agreements, SOPs and past cases.

Full documentation is in `docs/`; start with `docs/architecture.md`.

## Core rule

**AI reads, code decides.** Claude only turns documents into values and explains things.
Comparing values with limits, converting units and deciding is plain, tested Python in
`backend/app/services/rules/`. When anything is uncertain the answer is REVIEW, never RELEASE.

## Where things are

| Area | Location |
|---|---|
| Routes | `backend/app/api/routes/`, one module per area |
| Request and response models | `backend/app/schemas/`, one module per area |
| Batch workflow | `backend/app/services/batches.py` (`ingest_coa`, `run_check`, `apply_action`) |
| Rules engine | `backend/app/services/rules/` (`engine.py`, `grade.py`, `matching.py`, `units.py`, `values.py`) |
| COA reading | `backend/app/services/extraction/` (`reader.py`, `verify.py`, `events.py`) |
| Review copilot | `backend/app/services/copilot.py` |
| Knowledge base and search | `backend/app/services/knowledge.py` |
| Permissions | `backend/app/core/permissions.py` |
| Settings | `backend/app/core/config.py` (`BATCHGATE_` prefix) |
| Migrations | `backend/migrations/` |
| Demo data | `backend/app/seed.py`, `backend/app/seed_knowledge.py` |
| Worker, MCP server | `backend/app/worker.py`, `backend/app/mcp_server.py` |
| Frontend | `frontend/src/` (`views/`, `components/`, `types.ts` mirrors the API) |
| Evals | `evals/` |
| Deployment | `docker-compose.yml`, `backend/Dockerfile`, `frontend/Dockerfile`, `docs/deploy-ec2.md` |

## Commands

```bash
cd backend && uv run python -m app.seed               # migrate and add demo data
cd backend && uv run uvicorn app.main:app --reload    # API on :8000
cd backend && uv run arq app.worker.WorkerSettings    # COA reader (needs Redis)
cd frontend && npm run dev                            # web app on :5173

cd backend && uv run pytest                           # tests (own schema, no API key)
cd backend && uv run ruff check . && uv run ruff format . && uv run flake8
cd frontend && npm run typecheck && npm run format
```

## Conventions

- PostgreSQL only. Tables come from Alembic migrations; every model change needs a migration
  (`uv run alembic revision --autogenerate -m "..."`), read and fixed before applying.
- Keep the rules engine pure: dataclasses in and out, no database, no AI.
- Every COA enters through `ingest_coa()`; every check runs through `run_check()`.
- Routes check permissions, never role names. Sales users are scoped to their customers.
- Business-rule violations raise `WorkflowError(message, status_code)` with a plain message.
- Specs are versioned and never edited in place; order lines keep the agreed version.
- PEP 8 with a 99-character line limit (ruff and flake8); Prettier for the frontend.
- Every class and function has a short docstring; comments only where code cannot explain itself.
- UI copy is plain, sentence case, and says what happens.
- Every change comes with tests. Demo data stays fictional.
