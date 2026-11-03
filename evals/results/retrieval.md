# Knowledge search: retrieval eval

23 QC questions against the demo knowledge base (4 documents, 4 past cases), scoped to each question's customer and product like the copilot's search.

| | With spec-alias expansion | Without |
|---|---|---|
| Right passage first (hit@1) | **74%** | 74% |
| In the top 3 | **91%** | 87% |
| In the top 5 (what the copilot sees) | **100%** | 96% |
| Mean reciprocal rank | **0.83** | 0.81 |

| Question | Rank of first right passage | Top result |
|---|---|---|
| retest policy | 1 | Ridgeway Industrial Supply: quality agreement › 4.2 Retests |
| Can we retest when insoluble matter is above the limit? | 5 | Ridgeway Industrial Supply: quality agreement › 4.3 Concessions |
| concession insoluble matter | 1 | Ridgeway Industrial Supply: quality agreement › 4.3 Concessions |
| will Ridgeway accept a concession on appearance | 1 | Ridgeway Industrial Supply: quality agreement › 4.3 Concessions |
| notify customer when a batch is put on hold | 1 | Ridgeway Industrial Supply: quality agreement › 3 Notification |
| COA issued in another company's name or catalogue sheet | 1 | Ridgeway Industrial Supply: quality agreement › 2.1 (Certificates of analysis) |
| typical values sheet instead of batch COA | 1 | Ridgeway Industrial Supply: quality agreement › 2.1 (Certificates of analysis) |
| factory and lab results disagree which one counts | 1 | Ridgeway Industrial Supply: quality agreement › 5 Factory and laboratory results that disagree |
| lab insolubles higher than factory, sampling from IBC | 1 | case:FC-2608-15 |
| water insolubles failed before at Kutch Coastal | 2 | Method note: insoluble matter in ferric chloride solution › 2 Common causes of high results |
| what causes high insoluble matter results | 1 | Method note: insoluble matter in ferric chloride solution › 2 Common causes of high results |
| how close should two labs agree on insolubles | 1 | Method note: insoluble matter in ferric chloride solution › 4 Agreement between laboratories |
| can we average the original and retest result | 1 | SOP QC-07: handling out-of-specification and doubtful results › 4 Phase 3: retest |
| assay difference factory versus lab | 1 | case:PO-2607-B |
| as-is or dried basis assay | 1 | Lumora Personal Care: quality agreement › 2.1 (Certificates of analysis) |
| who may retest a Lumora batch | 1 | Lumora Personal Care: quality agreement › 3.2 (Out-of-specification results) |
| Lumora concession on assay | 1 | Lumora Personal Care: quality agreement › 3.1 (Out-of-specification results) |
| what to ask the factory when a result is out of spec | 1 | SOP QC-07: handling out-of-specification and doubtful results › 3 Phase 2: ask the factory (within 1 working day) |
| same factory failing the same test twice | 1 | SOP QC-07: handling out-of-specification and doubtful results › 6 Factory trends |
| how long do we keep COAs | 4 | SOP QC-07: handling out-of-specification and doubtful results › 3 Phase 2: ask the factory (within 1 working day) |
| free HCl above max, what does the customer allow? | 2 | SOP QC-07: handling out-of-specification and doubtful results › 5 Decision and records |
| density ratio slightly high, what does the customer allow? | 3 | SOP QC-07: handling out-of-specification and doubtful results › 5 Decision and records |
| total iron low, what does the customer allow? | 3 | SOP QC-07: handling out-of-specification and doubtful results › 5 Decision and records |
