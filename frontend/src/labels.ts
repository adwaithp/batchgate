import type {
  AuditEntry,
  BatchActionType,
  BatchStatus,
  CoaSource,
  Decision,
  OrderStatus,
  ParamStatus,
  RuleType,
  SpecStatus,
} from '@/types'

export type Tone = 'idle' | 'review' | 'approval' | 'release' | 'hold'

export const STATUS: Record<BatchStatus, { label: string; tone: Tone }> = {
  awaiting_coa: { label: 'Awaiting COA', tone: 'idle' },
  pending_review: { label: 'Needs review', tone: 'review' },
  pending_approval: { label: 'Waiting approval', tone: 'approval' },
  on_hold: { label: 'On hold', tone: 'hold' },
  released: { label: 'Released', tone: 'release' },
  rejected: { label: 'Rejected', tone: 'hold' },
  cancelled: { label: 'Cancelled', tone: 'idle' },
}

export const DECISION: Record<Decision, { label: string; tone: Tone }> = {
  release: { label: 'Release', tone: 'release' },
  review: { label: 'Review', tone: 'review' },
  hold: { label: 'Hold', tone: 'hold' },
}

export const PARAM: Record<ParamStatus, { label: string; tone: Tone }> = {
  pass: { label: 'Pass', tone: 'release' },
  fail: { label: 'Fail', tone: 'hold' },
  unclear: { label: 'Unclear', tone: 'review' },
  missing: { label: 'Missing', tone: 'idle' },
}

export const SOURCE: Record<CoaSource, string> = {
  factory: 'Factory COA',
  lab: 'Lab COA',
}

export const ACTION: Record<BatchActionType, { label: string; past: string }> = {
  // Always an override; a second QC manager approves.
  propose_release: { label: 'Release anyway', past: 'proposed releasing it anyway' },
  approve_release: { label: 'Approve release', past: 'approved release' },
  hold: { label: 'Put on hold', past: 'put the batch on hold' },
  reject: { label: 'Reject batch', past: 'rejected the batch' },
  assign_line: { label: 'Assign to order line', past: 'assigned the order line' },
  rerun_check: { label: 'Run check again', past: 'ran the check again' },
  cancel: { label: 'Cancel batch', past: 'cancelled the batch' },
}

/** Format a timestamp as a local date and time. */
export function formatDateTime(iso: string): string {
  // The API stores UTC; treat a timestamp without a zone marker as UTC.
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
  return d.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

/** Format a quantity. */
export function formatQty(n: number | null, unit: string): string {
  if (n === null) return '—'
  return `${Number.isInteger(n) ? n : n.toFixed(1)} ${unit}`
}

export const ORDER_STATUS: Record<OrderStatus, { label: string; tone: Tone }> = {
  open: { label: 'Open', tone: 'idle' },
  partially_ready: { label: 'Partly ready', tone: 'review' },
  ready: { label: 'Ready to ship', tone: 'release' },
  shipped: { label: 'Shipped', tone: 'approval' },
}

export const SPEC_STATUS: Record<SpecStatus, { label: string; tone: Tone }> = {
  draft: { label: 'Draft', tone: 'idle' },
  active: { label: 'Current', tone: 'release' },
  superseded: { label: 'Replaced', tone: 'idle' },
}

/** How each rule reads to a person, and what it needs. */
export const RULE: Record<RuleType, { label: string; hint: string }> = {
  min: { label: 'At least', hint: 'The result must be this value or higher.' },
  max: { label: 'At most', hint: 'The result must be this value or lower.' },
  range: { label: 'Between', hint: 'The result must fall inside both limits.' },
  text_match: { label: 'Matches description', hint: 'The result must read like this text.' },
  complies: { label: 'Pass / fail', hint: 'The COA must say the sample complies.' },
}

/** Format a date. */
export function formatDate(iso: string): string {
  return new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  })
}

const DECISION_WORD: Record<string, string> = { release: 'release', review: 'review', hold: 'hold' }

/** One audit entry as a plain sentence, without the actor ("ran the check: hold"). */
export function auditSentence(e: AuditEntry): string {
  const d = e.data as Record<string, string | number | null | undefined>
  const status = (v: unknown) =>
    typeof v === 'string' ? (STATUS[v as BatchStatus]?.label ?? v) : ''
  switch (e.action) {
    case 'login':
      return 'signed in'
    case 'batch_created':
      return 'registered the batch'
    case 'coa_received':
      return `received the ${d.source === 'lab' ? 'lab' : 'factory'} COA${d.filename ? ` (${d.filename})` : ''}`
    case 'coa_data_saved':
      return d.by && d.by !== 'manual'
        ? `read the COA with Claude (${d.rows ?? 0} values)`
        : `entered the COA values (${d.rows ?? 0} values)`
    case 'coa_extraction_failed':
      return `couldn’t read the COA${d.error ? `: ${d.error}` : ''}`
    case 'copilot_brief':
      return `asked Claude to explain the batch${d.email_to ? ` (draft email to the ${d.email_to})` : ''}`
    case 'check_run':
      if (!d.decision) return 'ran the check (no COA values yet)'
      return (
        `ran the check: ${DECISION_WORD[String(d.decision)] ?? d.decision}` +
        (d.status_from !== d.status_to
          ? ` (${status(d.status_from)} → ${status(d.status_to)})`
          : '')
      )
    case 'spec_created':
      return 'created the spec'
    case 'spec_new_version':
      return 'changed the spec (new version)'
    case 'order_created':
      return 'entered the order'
    case 'customer_added':
      return `added a new customer${d.country ? ` (${d.country})` : ''}`
    case 'knowledge_document_added':
      return `added a document to the knowledge base (${d.passages ?? 0} sections)`
    case 'knowledge_document_archived':
      return 'archived a knowledge base document'
  }
  if (e.action.startsWith('batch_')) {
    const action = e.action.slice(6) as BatchActionType
    return ACTION[action]?.past ?? action.replace(/_/g, ' ')
  }
  return e.action.replace(/_/g, ' ')
}

export const DOCUMENT_KIND: Record<string, string> = {
  quality_agreement: 'Quality agreement',
  sop: 'SOP',
  method: 'Test method',
  other: 'Other',
}
