import type { BatchActionType, BatchStatus, CoaSource, Decision, ParamStatus } from '@/types'

export type Tone = 'idle' | 'review' | 'approval' | 'release' | 'hold'

export const STATUS: Record<BatchStatus, { label: string; tone: Tone }> = {
  awaiting_coa: { label: 'Awaiting COA', tone: 'idle' },
  pending_review: { label: 'Needs review', tone: 'review' },
  pending_approval: { label: 'Waiting approval', tone: 'approval' },
  on_hold: { label: 'On hold', tone: 'hold' },
  released: { label: 'Released', tone: 'release' },
  rejected: { label: 'Rejected', tone: 'hold' },
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
  propose_release: { label: 'Propose release', past: 'proposed release' },
  approve_release: { label: 'Approve release', past: 'approved release' },
  hold: { label: 'Put on hold', past: 'put the batch on hold' },
  reject: { label: 'Reject batch', past: 'rejected the batch' },
  assign_line: { label: 'Assign to order line', past: 'assigned the order line' },
  rerun_check: { label: 'Run check again', past: 'ran the check again' },
}

export function formatDateTime(iso: string): string {
  // The API stores UTC; SQLite returns it without a zone marker.
  const d = new Date(/[zZ]|[+-]\d\d:\d\d$/.test(iso) ? iso : `${iso}Z`)
  return d.toLocaleString(undefined, {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

export function formatQty(n: number | null, unit: string): string {
  if (n === null) return '—'
  return `${Number.isInteger(n) ? n : n.toFixed(1)} ${unit}`
}
