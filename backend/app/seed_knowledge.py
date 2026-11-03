# ruff: noqa: E501  (document text reads better unwrapped)
"""Demo knowledge base: quality agreements, an SOP, a method note and past cases."""

from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Customer, KnowledgeDocument, Product, QCCase, User
from app.models.enums import CaseOutcome, DocumentKind
from app.services import knowledge

RIDGEWAY_QA = """1 Scope
This agreement covers ferric chloride and MEA triazine that the Supplier delivers to Ridgeway Industrial Supply under any purchase order.

2 Certificates of analysis
2.1 Every batch ships with a COA issued on the manufacturer's own letterhead, showing the batch number, manufacturing date and expiry date. A supplier catalogue sheet, a typical-values sheet or a COA issued in another company's name is not accepted as the COA for a batch.
2.2 Every batch of ferric chloride and MEA triazine also needs a COA from an independent laboratory approved by the Supplier.

3 Notification
The Supplier notifies Ridgeway's quality contact within 24 hours when a batch for a Ridgeway order is put on hold, with the reason and the expected date of a decision.

4 Out-of-specification results
4.1 No out-of-specification material is released to Ridgeway without a written concession under 4.3.
4.2 Retests. When an assignable cause is suspected (sampling, sample preparation, a calculation error), one retest by the independent laboratory on the retained sample is permitted. If the retest is within specification and the cause is documented, the batch may be released. The original and retest results must not be averaged.
4.3 Concessions. Ridgeway may grant a written concession for non-critical deviations only: appearance, or specific gravity within 0.01 of a limit. No concession is granted for assay, iron content, free acid or insoluble matter.

5 Factory and laboratory results that disagree
Where the factory and the independent laboratory differ by more than the agreed tolerance, the independent laboratory result prevails until the difference is explained.

6 Records
COAs, retest reports and concessions are kept for five years.
"""

LUMORA_QA = """1 Scope
This agreement covers cosmetic-grade piroctone olamine that the Supplier delivers to Lumora Personal Care.

2 Certificates of analysis
2.1 The assay is reported by HPLC and the COA states whether it is on the as-is or the dried basis, together with the loss on drying.
2.2 An independent laboratory COA is required for every batch.

3 Out-of-specification results
3.1 No concession is granted for assay, related substances or heavy metals.
3.2 A retest may only be done by the laboratory that produced the original result, and only after Lumora QA has approved the retest plan in writing.

4 Factory and laboratory results that disagree
If the factory and the independent laboratory assay differ by more than 1.0 %, both results and the basis of each calculation are sent to Lumora QA, and the batch is not released until Lumora QA confirms in writing.

5 Notification
The Supplier notifies Lumora QA within 48 hours of any batch for a Lumora order being put on hold.
"""

SOP_OOS = """1 Purpose
How the QC team handles a batch that BatchGate puts on hold or sends for review: an out-of-specification (OOS) result, a doubtful result, or a factory and laboratory that disagree.

2 Phase 1: check the data (same day)
Confirm the values on the COA match what was entered or read, including units and the batch number. For assays, check the calculation basis (as-is or dried) on both COAs before treating a difference as real. Check the COA is the manufacturer's own document for this batch.

3 Phase 2: ask the factory (within 1 working day)
Request the raw data, the test method, how and where the sample was drawn, and whether a retained sample exists. Use the copilot's draft email as a starting point and keep the reply in the batch notes.

4 Phase 3: retest
If an assignable cause is plausible, arrange one retest of the retained sample at the independent laboratory, unless the customer's quality agreement says otherwise. Never average the original and the retest.

5 Decision and records
Release only with a documented cause and within what the customer's quality agreement allows; otherwise reject. Write what was found and decided in the batch note: it becomes a case BatchGate remembers.

6 Factory trends
Two out-of-specification results for the same test from the same factory within 90 days trigger a supplier review with procurement.
"""

METHOD_INSOLUBLES = """1 Principle
A weighed sample is diluted in dilute hydrochloric acid, filtered through a sintered glass crucible (porosity 4) and the residue dried at 105 °C to constant mass. The result is reported as insoluble matter, % w/w.

2 Common causes of high results
The crucible was not dried to constant mass before weighing. The sample was diluted with water instead of dilute hydrochloric acid, so iron hydroxide precipitated and was counted as insoluble. The sample was drawn from the bottom of an IBC where sediment collects.

3 Common causes of low results
The sample was drawn from the top of an IBC after it had settled.

4 Agreement between laboratories
Two competent laboratories should agree within 0.02 % absolute. A larger difference usually points to sampling or sample preparation rather than the batch itself, which makes it an assignable cause worth one retest.
"""

DOCUMENTS = [
    (
        "Ridgeway Industrial Supply: quality agreement",
        DocumentKind.QUALITY_AGREEMENT,
        "Ridgeway Industrial Supply",
        None,
        RIDGEWAY_QA,
    ),
    (
        "Lumora Personal Care: quality agreement",
        DocumentKind.QUALITY_AGREEMENT,
        "Lumora Personal Care",
        "Piroctone Olamine",
        LUMORA_QA,
    ),
    (
        "SOP QC-07: handling out-of-specification and doubtful results",
        DocumentKind.SOP,
        None,
        None,
        SOP_OOS,
    ),
    (
        "Method note: insoluble matter in ferric chloride solution",
        DocumentKind.METHOD,
        None,
        "Ferric Chloride",
        METHOD_INSOLUBLES,
    ),
]

# Past cases imported from the QC deviation log.
CASES = [
    {
        "batch_number": "FC-2608-15",
        "customer": "Ridgeway Industrial Supply",
        "product": "Ferric Chloride",
        "factory_name": "Kutch Coastal Chemicals",
        "problem": "Independent lab measured insoluble matter at 0.13 % against a max of 0.10 %; the factory COA reported 0.05 %.",
        "actions": "The factory confirmed the lab sample had been drawn from the bottom of the IBC. The lab retested the retained sample, mixed and diluted in dilute HCl: 0.07 %. Assignable cause recorded as sampling; released under the quality agreement's one-retest rule (4.2).",
        "outcome": CaseOutcome.RELEASED,
        "closed_on": date(2026, 8, 21),
    },
    {
        "batch_number": "FC-2606-02",
        "customer": "Ridgeway Industrial Supply",
        "product": "Ferric Chloride",
        "factory_name": "Kutch Coastal Chemicals",
        "problem": "Independent lab measured insoluble matter at 0.18 % against a max of 0.10 %; the factory COA reported 0.06 %.",
        "actions": "The lab retested the retained sample: 0.17 %. No assignable cause found. Ridgeway does not grant concessions on insoluble matter, so the batch was rejected and the factory credited the order.",
        "outcome": CaseOutcome.REJECTED,
        "closed_on": date(2026, 6, 12),
    },
    {
        "batch_number": "PO-2607-B",
        "customer": "Lumora Personal Care",
        "product": "Piroctone Olamine",
        "factory_name": "Dahej Specialty Organics",
        "problem": "Factory assay (HPLC) 99.7 % and independent lab 98.4 %: a 1.3 % difference against a 1 % tolerance.",
        "actions": "The factory had reported the assay on the as-is basis and the lab on the dried basis (loss on drying 1.2 %). Recalculated on the same basis the difference was 0.1 %. Both results and calculations were sent to Lumora QA, who confirmed in writing; released.",
        "outcome": CaseOutcome.RELEASED,
        "closed_on": date(2026, 7, 30),
    },
    {
        "batch_number": "MT-2609-08",
        "customer": "Ridgeway Industrial Supply",
        "product": "MEA Triazine",
        "factory_name": "Ruwais Process Chemicals",
        "problem": "The COA was a typical-values sheet without batch-specific results or dates, issued for the product range rather than the batch.",
        "actions": "Sent back to the factory asking for the batch COA on their letterhead, as the Ridgeway quality agreement requires (2.1). The batch COA arrived two days later and passed; released.",
        "outcome": CaseOutcome.RELEASED,
        "closed_on": date(2026, 9, 18),
    },
]


def seed_knowledge(db: Session) -> None:
    """Add the demo documents and imported past cases if missing."""
    if db.scalar(select(KnowledgeDocument.id).limit(1)):
        return
    customers = {c.name: c for c in db.scalars(select(Customer))}
    products = {p.name: p for p in db.scalars(select(Product))}
    manager = db.scalar(select(User).where(User.email == "meera@batchgate.dev"))
    for title, kind, customer, product, text in DOCUMENTS:
        knowledge.add_document(
            db,
            title=title,
            kind=kind,
            customer_id=customers[customer].id if customer else None,
            product_id=products[product].id if product else None,
            filename="",
            content_type="text/plain",
            text=text,
            actor=manager,
        )
    for c in CASES:
        c = dict(c)
        knowledge.save_case(
            db,
            QCCase(
                customer_id=customers[c.pop("customer")].id,
                product_id=products[c.pop("product")].id,
                source="imported",
                **c,
            ),
        )
    db.commit()
