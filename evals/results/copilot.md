# Review copilot eval

Model `claude-sonnet-5-5` on the seeded batches that need a person, with the demo knowledge base. Citations are judged by a separate Claude call.

| | Result |
|---|---|
| Briefs that cited a source a QC expert would expect | 2 / 2 |
| Citations the judge found supported | 14 / 15 |
| Knowledge searches per brief | 3, 4 |
| Briefs sent back for citing an unretrieved passage | 0 |

## FC-2611-07

Cited: Method note: insoluble matter in ferric chloride solution, 2 Common causes of high results; Method note: insoluble matter in ferric chloride solution, 4 Agreement between laboratories; Ridgeway Industrial Supply: quality agreement, 4.2 Retests; Ridgeway Industrial Supply: quality agreement, 4.3 Concessions; Ridgeway Industrial Supply: quality agreement, 5 Factory and laboratory results that disagree; SOP QC-07: handling out-of-specification and doubtful results, 4 Phase 3: retest; SOP QC-07: handling out-of-specification and doubtful results, 5 Decision and records; case:FC-2606-02

- Ask Kutch Coastal Chemicals how and where the lab sample was drawn (for example, the bottom of an IBC) and how the factory ran its insoluble matter test [K24, K26].
- Ask Northbridge Analytical Labs for one retest of the retained sample, mixed and diluted in dilute HCl [K20, K6].
- Do not average the original and the retest results. Release only if the retest is within spec and the cause is documented. If the retest is still above 0.1 % with no cause found, reject the batch, as with FC-2606-02 [K6, K28].
- Record the findings and decision in the batch note [K21]. Batch FC-2611-12 on the same PO line is still awaiting its COA.

## PO-2611-A

Cited: Lumora Personal Care: quality agreement, 2.1 (Certificates of analysis); Lumora Personal Care: quality agreement, 3.1 (Out-of-specification results); Lumora Personal Care: quality agreement, 3.2 (Out-of-specification results); Lumora Personal Care: quality agreement, 4 Factory and laboratory results that disagree; SOP QC-07: handling out-of-specification and doubtful results, 3 Phase 2: ask the factory (within 1 working day); SOP QC-07: handling out-of-specification and doubtful results, 4 Phase 3: retest; case:PO-2607-B

- Email the factory today for the assay raw data, the HPLC method, how the sample was drawn, whether a retained sample exists, and whether 99.6 % is on the as-is or the dried basis [K19, K11].
- Compare the basis of both assay results. In the earlier case PO-2607-B, a basis mismatch explained the gap [K29]. Here Loss on drying is only 0.21 % on both COAs, which looks too small to explain 1.3 %. That is my own reading, so check the factory's answer.
- Do not retest yet. A retest can only be done by the lab that produced the original result, and only after Lumora QA approves the plan in writing [K14]. Never average the original and a retest [K20].
- Once the basis is clear, send both results and the calculation basis to Lumora QA and keep the batch on hold until they confirm in writing [K15]. No concession is available for assay [K13].

Judge flagged: K29: The passage describes a case with the same factory (Dahej Specialty Organics) and customer (Lumora), but the claim says the same assay gap and the passage only gives a 1.3% gap with no indication it matches the current case, so identity of the gap cannot be confirmed from the passage alone.
