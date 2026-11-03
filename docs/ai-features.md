# AI features

| Feature | Claude's job | What keeps it safe |
|---|---|---|
| COA reading | Transcribe the document into structured values | Confidence threshold, PDF text check, manual fallback |
| Review copilot | Explain a batch and draft a follow-up | Read-only tools, citations checked in code |
| Knowledge search | None: retrieval is code | Scoped to customer and product, explainable matches |
| MCP server | Answer questions in Claude Desktop or Claude Code | Acts as one user, no release, hold or reject tools |

## COA reading

`services/extraction/reader.py` sends the PDF or image to Claude with a transcription prompt and
asks for structured output (`schemas/extraction.py`): issuer, product, CAS number, batch number,
dates as printed, and every result row with its name, value, unit, method, printed limit and a
confidence. Claude only transcribes; it never converts units or compares values with limits.

- The spec's parameters are listed in the prompt so Claude can hint which parameter a row is.
  Hints only fill gaps that name matching leaves.
- Dates are kept as printed when they are not a full, unambiguous date.
- A read that fails (not a COA, unreadable, refused) falls back to typing the values in.
- When a person saves the entry form, only rows they edited or ticked count as checked;
  untouched low-confidence rows keep the batch in review.

### PDF text check

`services/extraction/verify.py` checks Claude's reading against the PDF's own text layer. Each
value must appear on the line naming its test, or the line after it, with the row's printed limit
set aside. A value that cannot be found has its confidence capped below the review threshold, so a
person checks it. This catches the dangerous misread: a confident wrong value that agrees with the
other COA, leaving the engine nothing to disagree about. Scans and photos have no text layer, so
Claude's confidence stands.

## Review copilot

`services/copilot.py` runs a tool-use loop for a batch that needs a person.

Read-only tools:

| Tool | Returns |
|---|---|
| `get_verdict` | The latest decision, findings, per-parameter results and identity checks |
| `get_spec` | The spec with limits, criticality and tolerances |
| `get_coa_readings` | What was read from each COA, with confidences and warnings |
| `get_order_line` | Customer, PO, grade, quantity and the line's other batches |
| `get_factory_history` | The factory's recent batches of the same product |
| `search_knowledge` | Knowledge base passages for the batch's customer and product |

The loop ends when Claude calls `submit_brief` with an explanation, next steps, an optional
history note, an optional email draft to the factory or lab, and the sources it relied on
(`schemas/copilot.py`). Guardrails:

- The brief is validated by Pydantic; an invalid brief is sent back with the error.
- Every cited ref (`[K12]`) must have been returned by a search in this conversation; otherwise
  the brief is sent back. Refs cited in the text but not listed are added to the sources.
- There are no write tools. The decision stays the engine's and the email is a draft.
- Each brief is recorded in the audit log.

## Knowledge base and case memory

`services/knowledge.py` holds two kinds of passage:

- **Documents**: quality agreements, SOPs and method notes (PDF or text). They are split into
  passages at numbered and all-caps headings; numbered clauses become their own passages, so a
  citation can point at "4.2 Retests". A document without a customer or product applies to all.
- **Cases**: when a batch is released or rejected after a person acted (a note on release anyway,
  hold or reject), it becomes a case recording what failed, what people did and how it ended.
  Clean engine releases and cancellations are not cases. Older cases can be imported.

Search is BM25 in Python over the passages that apply to the batch's customer and product:

- Heading words count double.
- The query is expanded, at half weight, with the other names the specs and products know for the
  same test or product ("FeCl3" also finds "ferric chloride").
- On a tie, a passage written for this customer or product beats a general one.
- Every result lists the words it matched.

The retrieval eval guards the ranking ([Evals](evals.md)).

## MCP server

`app/mcp_server.py` exposes BatchGate to MCP clients over stdio. It acts as the user named by
`BATCHGATE_MCP_USER` with exactly that user's permissions.

| Tool | Purpose |
|---|---|
| `batches_needing_attention` | Batches awaiting review, on hold or awaiting approval |
| `get_batch` | One batch in full |
| `get_spec` | Current specs for a product, optionally one grade or customer |
| `factory_history` | A factory's recent batches of one product |
| `search_knowledge` | Search the knowledge base |
| `rerun_check` | Re-run the rules engine on a batch's current COAs |

Claude Desktop configuration (`claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "batchgate": {
      "command": "uv",
      "args": ["run", "--directory", "/path/to/batchgate/backend", "python", "-m", "app.mcp_server"],
      "env": { "BATCHGATE_MCP_USER": "meera@batchgate.dev" }
    }
  }
}
```
