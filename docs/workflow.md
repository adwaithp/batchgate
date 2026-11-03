# Workflow and roles

## Batch lifecycle

```
awaiting_coa ──▶ (engine check) ──┬──▶ pending_approval ──▶ released
                                  ├──▶ pending_review ──┐
                                  └──▶ on_hold ─────────┤
                                                        ├──▶ pending_approval (release anyway)
                                                        └──▶ rejected
any open status ──▶ cancelled (entered by mistake)
```

| Status | Meaning |
|---|---|
| `awaiting_coa` | Registered; COA values or an order line are still missing |
| `pending_review` | The engine found something uncertain; an analyst must look |
| `on_hold` | The engine or a person held the batch |
| `pending_approval` | Proposed for release; a QC manager must approve |
| `released` | Approved to ship |
| `rejected` | Will not ship |
| `cancelled` | Entered by mistake; kept for the record, not a QC decision |

A clean engine result skips the analyst but still needs a QC manager's approval.

## Decisions

| Action | Permission | Allowed from | Result | Note required |
|---|---|---|---|---|
| Release anyway (propose release) | `batch:propose_release` | review, hold | pending approval | yes |
| Approve release | `batch:approve_release` | pending approval | released | no |
| Hold | `batch:hold` | awaiting COA, review, pending approval | on hold | yes |
| Reject | `batch:reject` | review, hold, pending approval | rejected | yes |
| Change order line | `check:run` | any open status | re-checked | no |
| Re-run check | `check:run` | any open status | re-checked | no |
| Cancel batch | `coa:upload` | any open status | cancelled | yes |

The person who proposed a release cannot approve it (four eyes). Released, rejected and cancelled
batches are closed.

## Roles and permissions

Routes check permissions, never role names (`app/core/permissions.py`).

| Role | Permissions |
|---|---|
| QC Analyst | view dashboard, orders, specs, batches and knowledge for all customers; upload COAs, run checks, propose releases, hold batches |
| QC Manager | everything an analyst can, plus edit specs and orders, add customers, approve releases, reject batches, read the audit log, edit the knowledge base |
| Sales | view the dashboard, orders and specs for their assigned customers; enter orders; add customers |
| Admin | every permission |

## Orders, specs and customers

- **Specs** belong to one customer, product and grade, with one active version at a time. Each
  test has a rule (`min`, `max`, `range`, `text_match` or `complies`), a unit, aliases suppliers
  use for it, whether it is critical, and an optional factory-vs-lab tolerance.
- **Orders** have lines; each line is one product grade, a quantity and the current spec for that
  customer. The same product can appear on two lines at different grades.
- **Order status** follows the released quantity on its lines: open, partially ready, ready.
  `shipped` exists in the data model but nothing sets it yet; shipped orders are read-only.
- **Customers** can be added by sales, QC managers and admins. A sales user is assigned to the
  customer they add. A new customer has no specs, so a QC manager creates their spec before an
  order can be entered.
- **Batches without an order line** get suggestions: each open line for the product, with how the
  batch measures up against that line's spec. A person confirms the line.

## Demo accounts

All demo accounts use the password `demo1234`.

| Email | Role |
|---|---|
| `meera@batchgate.dev` | QC Manager |
| `arjun@batchgate.dev` | QC Analyst |
| `sara@batchgate.dev` | Sales (Ridgeway Industrial Supply only) |
| `admin@batchgate.dev` | Admin |

The demo data contains five batches created through the real workflow:

| Batch | Outcome |
|---|---|
| FC-2611-07 | Hold: the lab measured insoluble matter at 0.14 % against a maximum of 0.1 % |
| FC-2611-12 | Registered, awaiting its COAs |
| MT-2610-31 | Release, awaiting a QC manager's approval |
| MT-2611-04 | No order line: fits the 40 % grade on PO-1042 line 3, fails the 78 % grade on line 2 |
| PO-2611-A | Review: factory and lab assay differ by more than the 1 % allowed |
