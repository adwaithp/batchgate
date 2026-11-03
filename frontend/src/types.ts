export type Role = 'admin' | 'qc_manager' | 'qc_analyst' | 'sales'

export type Permission =
  | 'dashboard:view'
  | 'orders:view'
  | 'orders:edit'
  | 'customers:view_all'
  | 'customers:add'
  | 'specs:view'
  | 'specs:edit'
  | 'batches:view'
  | 'coa:upload'
  | 'check:run'
  | 'batch:propose_release'
  | 'batch:approve_release'
  | 'batch:hold'
  | 'batch:reject'
  | 'audit:view'
  | 'knowledge:view'
  | 'knowledge:edit'
  | 'users:manage'

export interface User {
  id: number
  email: string
  full_name: string
  role: Role
  role_label: string
  permissions: Permission[]
  customers: { id: number; name: string }[]
}

export interface DemoAccount {
  email: string
  full_name: string
  role: Role
  role_label: string
  description: string
}

export interface DemoAccounts {
  enabled: boolean
  password: string | null
  accounts: DemoAccount[]
}

export type BatchStatus =
  | 'awaiting_coa'
  | 'pending_review'
  | 'on_hold'
  | 'pending_approval'
  | 'released'
  | 'rejected'
  | 'cancelled'

export interface OrderLineSummary {
  line_no: number
  product: string
  grade: string
  quantity: number
  unit: string
  batches: number
  released: number
  released_quantity: number
  ready: boolean
}

export interface OrderSummary {
  id: number
  po_number: string
  customer: string
  order_date: string
  status: 'open' | 'partially_ready' | 'ready' | 'shipped'
  lines: OrderLineSummary[]
}

export interface Dashboard {
  scope: string
  open_orders: number
  order_lines: number
  active_specs: number
  batches_by_status: Record<BatchStatus, number>
  recent_orders: OrderSummary[]
}

// Batches

export type Decision = 'release' | 'hold' | 'review'
export type CoaSource = 'factory' | 'lab'
export type RuleType = 'min' | 'max' | 'range' | 'text_match' | 'complies'
export type BatchActionType =
  | 'propose_release'
  | 'approve_release'
  | 'hold'
  | 'reject'
  | 'assign_line'
  | 'rerun_check'
  | 'cancel'

export interface Ref {
  id: number
  name: string
}
export interface SupplierRef extends Ref {
  country: string
  city: string | null
}
export interface ProductRef extends Ref {
  cas_number: string | null
}

export interface SpecParameter {
  id: number
  name: string
  rule_type: RuleType
  low: number | null
  high: number | null
  unit: string | null
  expected_text: string | null
  critical: boolean
  spec_text: string
  aliases: string[]
}

export interface Spec {
  id: number
  grade: string
  version: number
  customer: string
  product: string
  parameters: SpecParameter[]
}

export interface Line {
  id: number
  order_id: number
  po_number: string
  line_no: number
  customer: string
  product: string
  grade: string
  quantity: number
  unit: string
  released_quantity: number
}

export interface CoaResult {
  id: number
  name_as_written: string
  raw_value: string
  unit: string | null
  method: string | null
  confidence: number
  needs_check: boolean
  matched_parameter_id: number | null
}

export interface Coa {
  id: number
  source: CoaSource
  issuer: SupplierRef | null
  origin: string
  superseded: boolean
  original_filename: string | null
  has_file: boolean
  uploaded_at: string
  uploaded_by: string | null
  extraction_status: 'pending' | 'done' | 'failed'
  extraction_model: string | null
  extraction_error: string | null
  warnings: string[]
  checked_by: string | null
  issuer_name: string | null // as printed; `issuer` is the supplier chosen in BatchGate
  issuer_confidence: number
  issuer_needs_check: boolean
  product_name: string | null
  cas_number: string | null
  batch_number: string | null
  po_reference: string | null
  mfg_date: string | null
  test_date: string | null
  expiry_date: string | null
  mfg_date_as_printed: string | null
  test_date_as_printed: string | null
  expiry_date_as_printed: string | null
  results: CoaResult[]
}

/** Progress of a COA being read, streamed from the upload or from /coas/{id}/events. */
export interface CoaEvent {
  stage: 'received' | 'queued' | 'reading' | 'done' | 'failed' | 'manual' | 'waiting'
  message?: string
  coa_id?: number
  batch?: BatchDetail
}

export type ParamStatus = 'pass' | 'fail' | 'unclear' | 'missing'

export interface Reading {
  source: CoaSource
  coa_id: number | null
  raw_value: string
  unit: string | null
  value: number | null
  status: ParamStatus
  note: string | null
  confidence: number
}

export interface ParameterCheck {
  parameter_id: number
  name: string
  spec_text: string
  critical: boolean
  status: ParamStatus
  readings: Reading[]
  discrepancy: string | null
  note: string | null
}

export interface IdentityCheck {
  code: string
  label: string
  status: 'pass' | 'fail' | 'warn' | 'missing'
  message: string
  source: CoaSource | null
}

export interface Finding {
  severity: 'hold' | 'review' | 'info'
  code: string
  message: string
  parameter_id: number | null
}

export interface VerdictDetails {
  decision: Decision
  summary: string
  parameters: ParameterCheck[]
  identity: IdentityCheck[]
  findings: Finding[]
  unmatched: {
    source: CoaSource
    name_as_written: string
    raw_value: string
    unit: string | null
  }[]
}

export interface Verdict {
  id: number
  decision: Decision
  summary: string
  details: VerdictDetails
  engine_version: string
  created_at: string
}

export interface BatchActionRecord {
  id: number
  action: BatchActionType
  actor: string
  actor_role: string
  note: string | null
  created_at: string
}

export interface Suggestion {
  line: Line
  decision: Decision
  summary: string
  failing: string[]
}

export interface BatchSummary {
  id: number
  batch_number: string
  product: ProductRef
  factory: SupplierRef | null
  status: BatchStatus
  quantity: number | null
  unit: string
  line: { id: number; po_number: string; line_no: number; grade: string; customer: string } | null
  decision: Decision | null
  summary: string | null
  coa_sources: CoaSource[]
  updated_at: string
}

export interface BatchDetail extends BatchSummary {
  line_detail: (Line & { spec: Spec }) | null
  coas: Coa[]
  verdict: Verdict | null
  history: { id: number; decision: Decision; summary: string; created_at: string }[]
  actions: BatchActionRecord[]
  allowed_actions: BatchActionType[]
  suggestions: Suggestion[]
}

export interface LineOption {
  id: number
  product_id: number
  label: string
  po_number: string
  line_no: number
  grade: string
  customer: string
  quantity: number
  unit: string
}

export interface CatalogOptions {
  products: ProductRef[]
  factories: SupplierRef[]
  labs: SupplierRef[]
  open_lines: LineOption[]
}

// Orders and specs

export type SpecStatus = 'draft' | 'active' | 'superseded'
export type OrderStatus = OrderSummary['status']

export interface CustomerRef {
  id: number
  name: string
  country: string
  industry: string | null
}

export interface ProductRef {
  id: number
  name: string
  cas_number: string | null
}

export interface ReferenceData {
  customers: CustomerRef[]
  products: ProductRef[]
}

export interface SpecParameterFull {
  id: number
  name: string
  rule_type: RuleType
  low: number | null
  high: number | null
  unit: string | null
  expected_text: string | null
  aliases: string[]
  method: string | null
  critical: boolean
  tolerance_pct: number | null
  tolerance_abs: number | null
  spec_text: string
}

export interface SpecSummary {
  id: number
  customer: CustomerRef
  product: ProductRef
  grade: string
  version: number
  status: SpecStatus
  effective_from: string | null
  tests: number
  critical_tests: number
  open_lines: number
  created_at: string
}

export interface SpecDetail extends SpecSummary {
  notes: string | null
  created_by: string | null
  parameters: SpecParameterFull[]
  versions: {
    id: number
    version: number
    status: SpecStatus
    effective_from: string | null
    created_by: string | null
    created_at: string
    notes: string | null
  }[]
  current_version_id: number | null
  used_by: {
    line_id: number
    order_id: number
    po_number: string
    line_no: number
    quantity: number
    unit: string
    spec_version: number
  }[]
  can_edit: boolean
}

export interface SpecParameterIn {
  name: string
  rule_type: RuleType
  low: number | null
  high: number | null
  unit: string | null
  expected_text: string | null
  aliases: string[]
  method: string | null
  critical: boolean
  tolerance_pct: number | null
  tolerance_abs: number | null
}

export interface OrderListItem {
  id: number
  po_number: string
  customer: CustomerRef
  order_date: string
  status: OrderStatus
  lines: number
  quantity: number
  released_quantity: number
  batches_in_qc: number
  on_hold: number
}

export interface OrderDetail {
  id: number
  po_number: string
  customer: CustomerRef
  order_date: string
  status: OrderStatus
  created_at: string
  lines: {
    id: number
    line_no: number
    product: string
    spec_id: number
    grade: string
    spec_version: number
    spec_current: boolean
    quantity: number
    unit: string
    released_quantity: number
    ready: boolean
    batches: {
      id: number
      batch_number: string
      factory: string | null
      quantity: number | null
      unit: string
      status: BatchStatus
      decision: Decision | null
    }[]
  }[]
}

export interface CustomerSpecs {
  customer_id: number
  specs: { id: number; product_id: number; product: string; grade: string; version: number }[]
}

export interface AuditEntry {
  id: number
  at: string
  actor: string | null
  action: string
  entity_type: string
  entity_id: number | null
  entity_label: string | null
  link: string | null
  data: Record<string, unknown>
}

export interface AuditPage {
  entries: AuditEntry[]
  next_before: number | null
}

export interface CopilotBrief {
  explanation: string
  next_steps: string[]
  history_note: string | null
  email: { to: 'factory' | 'lab'; subject: string; body: string } | null
  sources: { ref: string; title: string; link: string; supports: string }[]
  looked_at: string[]
  model: string
}

// Knowledge base

export type DocumentKind = 'quality_agreement' | 'sop' | 'method' | 'other'

export interface KnowledgeDocumentSummary {
  id: number
  title: string
  kind: DocumentKind
  customer: string | null
  product: string | null
  passages: number
  has_file: boolean
  added_by: string | null
  created_at: string
}

export interface KnowledgeDocumentDetail extends KnowledgeDocumentSummary {
  passages_list: { id: number; ref: string; section: string | null; text: string }[]
  can_edit: boolean
}

export interface QCCaseOut {
  id: number
  batch_number: string
  batch_id: number | null
  customer: string | null
  product: string | null
  factory: string | null
  problem: string
  actions: string
  outcome: 'released' | 'rejected'
  closed_on: string
  source: string
}

export interface KnowledgeOverview {
  documents: KnowledgeDocumentSummary[]
  cases: QCCaseOut[]
  can_edit: boolean
}

export interface KnowledgeHit {
  ref: string
  score: number
  source: string
  kind: 'document' | 'case'
  section: string | null
  text: string
  link: string
  matched: string[]
}
