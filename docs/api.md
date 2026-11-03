# API

The API is served under `/api`. Interactive documentation with every schema is at `/docs`
(Swagger UI) and the OpenAPI document at `/openapi.json`.

## Authentication

1. `POST /api/auth/token` with form fields `username` (the email) and `password` returns
   `{"access_token": "...", "token_type": "bearer", "expires_in": ...}`.
2. Send `Authorization: Bearer <token>` on every other request.

Each endpoint requires a permission (see [Workflow and roles](workflow.md#roles-and-permissions)).
Sales users only see data for their assigned customers; records outside that scope return 404.

## Errors

Errors are JSON: `{"detail": "..."}`. Business-rule violations return a 4xx status with a message
written for the person using the app, for example `409` when a PO number already exists or `422`
when a release is proposed without a note.

## Endpoints

| Method | Path | Description |
|---|---|---|
| GET | `/api/health` | Report that the API is up |
| POST | `/api/auth/token` | Issue an access token |
| GET | `/api/auth/me` | The signed-in user with permissions |
| GET | `/api/auth/demo-accounts` | One-click demo accounts (demo mode only) |
| GET | `/api/dashboard` | Order, spec and batch counts for the user's customers |
| GET | `/api/catalog/options` | Products, factories, labs and open order lines for the batch forms |
| GET | `/api/batches` | List batches; filter with `status` (repeatable) and `q` |
| POST | `/api/batches` | Register a batch |
| GET | `/api/batches/{batch_id}` | A batch in full, including the actions the user may take |
| POST | `/api/batches/{batch_id}/actions` | Take a decision on a batch |
| POST | `/api/batches/{batch_id}/coas` | Upload a COA and stream its reading (see below) |
| GET | `/api/coas/{coa_id}/events` | Re-attach to a COA's reading progress |
| PUT | `/api/coas/{coa_id}/data` | Save COA values typed or corrected by a person, then re-check |
| GET | `/api/coas/{coa_id}/file` | The uploaded COA file |
| POST | `/api/batches/{batch_id}/copilot` | Ask the review copilot for a brief |
| GET | `/api/orders` | List orders |
| POST | `/api/orders` | Create an order |
| GET | `/api/orders/{order_id}` | An order with each line's batches |
| GET | `/api/reference` | Customers the user may see and all products |
| POST | `/api/customers` | Add a customer |
| GET | `/api/customers/{customer_id}/specs` | Current specs an order line for this customer can use |
| GET | `/api/specs` | List current specs; `include_old=true` adds replaced versions |
| POST | `/api/specs` | Create a spec |
| GET | `/api/specs/{spec_id}` | A spec version with its history and the lines using it |
| POST | `/api/specs/{spec_id}/versions` | Create the next version of a spec |
| GET | `/api/audit` | Audit entries, newest first; filter with `kind`, page with `before` |
| GET | `/api/knowledge` | Active documents and past cases |
| GET | `/api/knowledge/search` | Search documents and cases |
| GET | `/api/knowledge/documents/{doc_id}` | A document with its passages |
| GET | `/api/knowledge/documents/{doc_id}/file` | A document's original file |
| POST | `/api/knowledge/documents` | Upload a document (PDF or text) |
| POST | `/api/knowledge/documents/{doc_id}/archive` | Remove a document from search |

## COA reading events

`POST /api/batches/{batch_id}/coas` takes multipart form fields `source` (`factory` or `lab`), an
optional `issuer_id` (the lab) and an optional `file` (PDF, PNG or JPEG, up to 15 MB). It responds
with `201` and a `text/event-stream` body. Each event is a JSON object with a `stage`:

| Stage | Meaning |
|---|---|
| `received` | The COA is stored; includes `coa_id` and the updated `batch` |
| `queued` | Waiting for the worker |
| `reading` | Claude is reading the COA |
| `done` | Values saved and the check has run |
| `failed` | The reading failed; values can be typed in |
| `manual` | No file or no API key; values are typed in |
| `waiting` | Still reading after the stream's time limit; check back later |

The last four end the stream. Comment lines keep a quiet connection open. If the browser drops
off, `GET /api/coas/{coa_id}/events` resumes the same stream.
