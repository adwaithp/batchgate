# BatchGate

**An AI quality gate for specialty chemical batches.**

A partner factory makes a batch. The factory and an independent lab each send a certificate of
analysis (COA): a PDF, a scan, sometimes a phone photo. Before the batch ships, every number on
both must be checked against the spec the customer agreed. BatchGate does that check: Claude reads
the COAs, plain tested code compares them with the spec, and every batch comes out as **release**,
**hold** or **needs a person**, with the reasons spelled out.

When a batch needs a person, a review copilot explains why and what to do next, citing the
customer's quality agreement, the SOPs and how similar problems were resolved before.

The design rule everywhere: **AI reads, code decides.** Claude turns documents into values and
explains things to people. Whether a batch can ship is decided by a rules engine with no AI in it,
and when anything is uncertain the answer is "a person looks", never "release".

## Features

- **COA reading** with Claude vision and structured output, a confidence per value, and a code
  check of every value against the PDF's own text layer.
- **Rules engine** comparing the spec with the factory and lab COAs: limits, units, factory-vs-lab
  agreement, CAS number, product grade, issuer, batch number and dates.
- **Workflow with four-eyes approval**: analysts propose, a different QC manager approves; every
  change lands in an append-only audit log.
- **Orders, versioned specs and customers**: each order line is checked against the spec version
  agreed when the order was placed.
- **Review copilot**: a tool-using agent with read-only tools that cites its sources, with
  citations verified in code.
- **Knowledge base and case memory**: quality agreements, SOPs and method notes split into
  clauses, plus every batch a person resolved, searchable with BM25 scoped to customer and product.
- **MCP server** so QC staff can query BatchGate from Claude Desktop or Claude Code.
- **Evals** for COA reading, planted misreads, retrieval and copilot citations.

## Results

| Eval | Result |
|---|---|
| COAs read (9 fictional test COAs) | 9 / 9 correct decisions, **0 false releases**, 100 % of values read correctly |
| Planted confident misreads on text PDFs | 2 false releases without the PDF text check, **0 with it** |
| Knowledge search, 23 QC questions | right passage in the top 5 for **100 %**, first for 74 % |
| Copilot citations | expected sources cited in 2 / 2 briefs, 14 / 15 citations judged faithful |

Two real supplier COAs, scored locally and not published, were also held correctly.
Details and how to re-run them: [docs/evals.md](docs/evals.md).

## Quick start

Requirements: Python 3.12 with [uv](https://docs.astral.sh/uv/), Node 20+, PostgreSQL 16, and
optionally Redis and an Anthropic API key.

```bash
# Database
createuser --pwprompt batchgate
createdb --owner batchgate batchgate

# API → http://localhost:8000/docs
cd backend
cp .env.example .env            # database settings, ANTHROPIC_API_KEY
uv sync
uv run python -m app.seed       # applies migrations and adds demo data
uv run uvicorn app.main:app --reload

# Web app → http://localhost:5173
cd frontend
npm install
npm run dev
```

Sign in with one click as any demo account (password `demo1234`). Without an API key, COA values
are typed in by hand and the copilot is off. With Redis running, start the COA reader with
`uv run arq app.worker.WorkerSettings`; without it, the API reads COAs inside the upload request.

## Documentation

| Guide | Contents |
|---|---|
| [Architecture](docs/architecture.md) | Components, data model, request flows, project layout |
| [Workflow and roles](docs/workflow.md) | Batch lifecycle, decisions, roles and permissions, orders, specs and customers |
| [Rules engine](docs/rules-engine.md) | The release policy and every check it runs |
| [AI features](docs/ai-features.md) | COA reading, the text check, the review copilot, the knowledge base, the MCP server |
| [Evals](docs/evals.md) | What is measured, current results and how to re-run |
| [API](docs/api.md) | Authentication, endpoints and the COA reading event stream |
| [Development](docs/development.md) | Setup, configuration, migrations, tests, linting and conventions |
| [Deploying on AWS EC2](docs/deploy-ec2.md) | Five-service docker compose deployment |

## Tech stack

Python 3.12, FastAPI, SQLAlchemy 2, Pydantic v2, Alembic, PostgreSQL, Redis and arq; Vue 3,
TypeScript and Pinia; the Anthropic SDK (vision, structured output, tool use) and the MCP SDK.

All companies, specs and documents in the demo data are fictional.
