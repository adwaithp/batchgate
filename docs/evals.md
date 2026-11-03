# Evals

Run every eval from `backend/`. Results are written to `evals/results/`.

| Eval | Command | Needs an API key |
|---|---|---|
| COA reading and decisions | `uv run python ../evals/run_evals.py` | yes (`--cached` re-scores saved readings without it) |
| Knowledge search | `uv run python ../evals/run_retrieval.py` | no |
| Review copilot | `uv run python ../evals/run_copilot.py` | yes |
| Regenerate the test COAs | `uv run python ../evals/generate_coas.py` | no |

The evals use their own schemas in the configured database and drop them afterwards.

## COA reading and decisions

`evals/run_evals.py` reads every COA in `evals/coas/manifest.json` with the same `read_coa()` the
app uses, plus any real COAs in the git-ignored `evals/real/`. For each document it scores the
header fields and result values against the known answers, then runs the PDF text check and the
rules engine as the app would, and compares the decision with the expected one.

The test COAs (`evals/generate_coas.py`) are fictional and cover: clean factory and lab COAs, a
scanned PDF, a phone photo, an out-of-spec result, % w/v against % w/w, a value below detection
limit, a wrong batch number and a missing test.

Latest results for the fictional COAs ([`latest.md`](../evals/results/latest.md)); results
for real COAs stay local:

| Metric | Result |
|---|---|
| False releases | **0** |
| Correct decisions | 9 / 9 |
| Header fields read correctly | 100 % |
| Result values read correctly | 100 % |
| Unneeded reviews | 0 |

### Stress test: planted misreads

Each numeric value Claude read is replaced, one at a time, by a confident wrong value (its own
printed limit, two digits swapped, or the other COA's value for the same test), and the batch is
decided again.

| Documents | Planted misreads | Released unseen without the text check | With it | False releases without / with |
|---|---|---|---|---|
| PDFs with a text layer | 110 | 18 | **0** | 2 / **0** |
| Scans and photos | 32 | 16 | 16 | 0 / 0 |

Scans and photos have no text layer, so a confident misread there is caught only when the factory
and lab disagree.

## Knowledge search

`evals/run_retrieval.py` runs the 23 questions in `evals/retrieval/questions.json` against the
demo knowledge base, scoped to each question's customer and product like the copilot's search. A
question counts as answered at rank k when an accepted passage is in the top k.

| | With spec-alias expansion | Without |
|---|---|---|
| Right passage first (hit@1) | 74 % | 74 % |
| In the top 3 | 91 % | 87 % |
| In the top 5 (what the copilot sees) | **100 %** | 96 % |
| Mean reciprocal rank | 0.83 | 0.81 |

`tests/test_knowledge.py` fails if every answer is no longer in the top 5.

## Review copilot

`evals/run_copilot.py` runs the copilot on the seeded batches that need a person and checks that
each brief cites the sources a QC expert would expect. A separate Claude call judges whether each
cited passage supports the claim made for it.

| | Result |
|---|---|
| Briefs citing an expected source | 2 / 2 |
| Citations judged supported | 14 / 15 |
| Briefs sent back for citing an unretrieved passage | 0 |
