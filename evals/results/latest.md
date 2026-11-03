# BatchGate eval results

Model `claude-sonnet-5-5` · 9 documents · 2026-11-03

| Metric | Result |
|---|---|
| **False releases** (released when it should not) | **0** |
| Correct decision | 9 / 9 |
| Header fields read correctly | 100% |
| Result values read correctly | 100% |
| Misread values that Claude flagged as unsure | 0 of 0 |
| Misreads caught by the PDF text check | 0 |
| Right values the text check flagged anyway | 0 |
| Unneeded reviews (should have released) | 0 |
| Reads that failed (manual entry) | 0 |

| Document | Expected | BatchGate | Fields | Values | Notes |
|---|---|---|---|---|---|
| `01_factory_clean.pdf` (coas) | release | release ✅ | 8/8 | 7/7 |  |
| `02_lab_clean.pdf` (coas) | release | release ✅ | 8/8 | 7/7 |  |
| `03_lab_insolubles_out_of_spec.pdf` (coas) | hold | hold ✅ | 8/8 | 7/7 |  |
| `04_factory_scanned.pdf` (coas) | release | release ✅ | 8/8 | 7/7 |  |
| `05_factory_assay_w_v.pdf` (coas) | review | review ✅ | 8/8 | 7/7 |  |
| `06_factory_insolubles_below_detection.pdf` (coas) | review | review ✅ | 8/8 | 7/7 |  |
| `07_factory_wrong_batch.pdf` (coas) | review | review ✅ | 8/8 | 7/7 |  |
| `08_factory_missing_ferrous_iron.pdf` (coas) | review | review ✅ | 8/8 | 6/6 |  |
| `09_factory_phone_photo.jpg` (coas) | release | release ✅ | 8/8 | 7/7 |  |

Decisions are made by the rules engine on Claude's reading, never by Claude. A failed read falls back to manual entry and is never released on its own.

## Stress test: planted misreads

Each numeric value Claude read is replaced, one at a time, by a confident wrong value (its own printed limit, two digits swapped, or the other COA's value for the same test), then decided again. *Unseen* means the batch was released, so no person looked at the wrong value.

| Documents | Planted misreads | Unseen without the text check | Unseen with it | False releases without / with |
|---|---|---|---|---|
| PDFs with a text layer | 110 | 18 | **0** | 2 / **0** |
| Scans and photos (nothing to check) | 32 | 16 | 16 | 0 / 0 |
