export type Role = 'admin' | 'qc_manager' | 'qc_analyst' | 'sales'

export type Permission =
  | 'dashboard:view'
  | 'orders:view'
  | 'customers:view_all'
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

// ---- Batches -----------------------------------------------------------------------------

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
  product_name: string | null
  cas_number: string | null
  batch_number: string | null
  po_reference: string | null
  mfg_date: string | null
  test_date: string | null
  expiry_date: string | null
  results: CoaResult[]
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
  unmatched: { source: CoaSource; name_as_written: string; raw_value: string; unit: string | null }[]
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
