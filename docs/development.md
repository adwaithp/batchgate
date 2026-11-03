# Development

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- Node 20 or newer
- PostgreSQL 16
- Optional: Redis (background COA reading) and an Anthropic API key (COA reading and the copilot)

## Setup

```bash
createuser --pwprompt batchgate
createdb --owner batchgate batchgate

cd backend
cp .env.example .env          # fill in the database settings and ANTHROPIC_API_KEY
uv sync
uv run python -m app.seed     # apply migrations and add demo data

cd ../frontend
npm install
```

## Running

```bash
cd backend && uv run uvicorn app.main:app --reload    # API on :8000, docs at /docs
cd backend && uv run arq app.worker.WorkerSettings    # COA reader (needs Redis)
cd frontend && npm run dev                            # web app on :5173, proxies /api
```

## Configuration

Settings are read from the environment and from `backend/.env`. Variables use the `BATCHGATE_`
prefix, except `ANTHROPIC_API_KEY`.

| Variable | Default | Purpose |
|---|---|---|
| `BATCHGATE_DB_HOST` | `localhost` | PostgreSQL host |
| `BATCHGATE_DB_PORT` | `5432` | PostgreSQL port |
| `BATCHGATE_DB_NAME` | `batchgate` | Database name |
| `BATCHGATE_DB_USER` | `batchgate` | Database user |
| `BATCHGATE_DB_PASSWORD` | empty | Database password; special characters need no escaping |
| `BATCHGATE_DATABASE_URL` | unset | Full SQLAlchemy URL; overrides the parts above |
| `BATCHGATE_DB_SCHEMA` | unset | Schema to use instead of `public` |
| `BATCHGATE_CHECK_SCHEMA_ON_START` | `true` | Refuse to start unless migrations are current |
| `BATCHGATE_SECRET_KEY` | development value | JWT signing key; set a long random value in production |
| `BATCHGATE_ACCESS_TOKEN_EXPIRE_MINUTES` | `720` | Token lifetime |
| `BATCHGATE_DEMO_MODE` | `true` | Show one-click demo accounts on the sign-in page |
| `BATCHGATE_DEMO_PASSWORD` | `demo1234` | Password of the demo accounts |
| `BATCHGATE_CORS_ORIGINS` | `["http://localhost:5173"]` | Allowed browser origins |
| `ANTHROPIC_API_KEY` | unset | Enables COA reading and the copilot |
| `BATCHGATE_EXTRACTION_MODEL` | `claude-sonnet-5-5` | Model that reads COAs |
| `BATCHGATE_COPILOT_MODEL` | `claude-sonnet-5-5` | Model behind the copilot |
| `BATCHGATE_EXTRACTION_MODE` | `auto` | `queue` (worker), `inline` (in the request) or `auto` (queue when Redis answers) |
| `BATCHGATE_REDIS_URL` | `redis://localhost:6379` | Redis for the queue and progress events |
| `BATCHGATE_UPLOAD_DIR` | `./uploads` | Where uploaded files are stored |
| `BATCHGATE_MAX_UPLOAD_MB` | `15` | Upload size limit |
| `BATCHGATE_MCP_USER` | `arjun@batchgate.dev` | User the MCP server acts as |
| `BATCHGATE_REQUIRE_LAB_COA` | `true` | A batch needs an independent lab COA to release |
| `BATCHGATE_DEFAULT_TOLERANCE_PCT` | `2.0` | Default allowed factory-vs-lab difference, relative |
| `BATCHGATE_LOW_CONFIDENCE_THRESHOLD` | `0.8` | Readings below this confidence need a person |

## Database migrations

Tables are created only by Alembic migrations in `backend/migrations/`, never by `create_all`.

```bash
uv run alembic upgrade head                                # apply new migrations, keeps data
uv run alembic revision --autogenerate -m "what changed"   # after changing a model
uv run alembic current                                     # where the database is
uv run python -m app.seed --reset                          # drop everything, fresh demo data
```

Read every generated migration before applying it. Autogenerate sees a renamed column as a drop
and an add, which loses data; write `op.alter_column(..., new_column_name=...)` instead. A new
non-null column needs a `server_default` or a data step for existing rows. The API refuses to
start when the database is behind and prints the command to run.

## Tests

```bash
cd backend && uv run pytest
```

The suite runs on the configured database in its own `batchgate_test` schema, built by the
migrations and dropped at the end. Each test runs in a transaction that is rolled back, so real
data is never touched. No API key is needed: Claude and Redis are replaced by fakes. A test fails
if a model changes without a migration.

## Linting and formatting

Backend (PEP 8, line length 99):

```bash
cd backend
uv run ruff check .        # pycodestyle, pyflakes, naming, bugbear, complexity, imports and more
uv run ruff format .       # formatting
uv run flake8              # the same style rules through flake8
```

Frontend:

```bash
cd frontend
npm run typecheck          # vue-tsc
npm run format             # Prettier (npm run format:check to verify)
```

## Conventions

- **AI reads, code decides.** Decisions belong to the rules engine; when in doubt it answers
  REVIEW.
- Keep the rules engine pure: dataclasses in, dataclasses out, no database and no AI.
- Every COA enters through `ingest_coa()`; every check runs through `run_check()`.
- Routes check permissions, never role names.
- Business-rule violations raise `WorkflowError(message, status_code)`; the message is shown to
  the user, so write it in plain words.
- Pydantic request and response models live in `app/schemas/`, one module per area.
- Every class and function has a short docstring; comments explain only what the code cannot say.
- Every change comes with tests, and every model change with a migration.
- Demo data stays fictional.
