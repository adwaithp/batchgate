<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatDateTime, formatQty, SOURCE, STATUS } from '@/labels'
import { useAuthStore } from '@/stores/auth'
import type { BatchStatus, BatchSummary } from '@/types'

const auth = useAuthStore()
const route = useRoute()
const router = useRouter()

const all = ref<BatchSummary[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const search = ref('')

// Queues in the order work flows; "All" last.
const queues: { key: BatchStatus | 'all'; label: string }[] = [
  { key: 'pending_review', label: 'Needs review' },
  { key: 'pending_approval', label: 'Waiting approval' },
  { key: 'on_hold', label: 'On hold' },
  { key: 'awaiting_coa', label: 'Awaiting COA' },
  { key: 'released', label: 'Released' },
  { key: 'all', label: 'All' },
]

const defaultQueue = computed<BatchStatus | 'all'>(() =>
  auth.user?.role === 'qc_manager' ? 'pending_approval' : auth.user?.role === 'qc_analyst' ? 'pending_review' : 'all',
)

const active = computed<BatchStatus | 'all'>(() => {
  const q = route.query.status
  return typeof q === 'string' && queues.some((x) => x.key === q)
    ? (q as BatchStatus | 'all')
    : defaultQueue.value
})

function count(key: BatchStatus | 'all') {
  return key === 'all' ? all.value.length : all.value.filter((b) => b.status === key).length
}

const rows = computed(() => {
  const term = search.value.trim().toLowerCase()
  return all.value.filter((b) => {
    if (active.value !== 'all' && b.status !== active.value) return false
    if (!term) return true
    return [b.batch_number, b.product.name, b.factory?.name, b.line?.po_number, b.line?.customer]
      .filter(Boolean)
      .some((v) => v!.toLowerCase().includes(term))
  })
})

async function load() {
  loading.value = true
  error.value = null
  try {
    all.value = await api.get<BatchSummary[]>('/batches')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load batches.'
  } finally {
    loading.value = false
  }
}

function selectQueue(key: BatchStatus | 'all') {
  router.replace({ query: { ...route.query, status: key } })
}

onMounted(load)
watch(() => route.query.status, () => (search.value = ''))

const emptyText: Record<string, string> = {
  pending_review: 'Nothing needs review. Batches land here when the check finds something a person should look at.',
  pending_approval: 'No releases are waiting for approval.',
  on_hold: 'No batches are on hold.',
  awaiting_coa: 'Every registered batch has its COAs.',
  released: 'No batches released yet.',
  all: 'No batches yet. Register one to start.',
}
</script>

<template>
  <div class="page">
    <header class="head">
      <div>
        <h1>Batches</h1>
        <p class="sub">Every batch is checked against its order line’s spec before it can ship.</p>
      </div>
      <RouterLink v-if="auth.can('coa:upload')" to="/batches/new" class="primary">Register batch</RouterLink>
    </header>

    <div class="bar">
      <div class="queues" role="tablist" aria-label="Queues">
        <button
          v-for="q in queues"
          :key="q.key"
          type="button"
          role="tab"
          :aria-selected="active === q.key"
          :class="['queue', { on: active === q.key }]"
          @click="selectQueue(q.key)"
        >
          {{ q.label }}
          <span class="num n">{{ count(q.key) }}</span>
        </button>
      </div>
      <label class="search">
        <span class="visually-hidden">Search batches</span>
        <input v-model="search" type="search" placeholder="Search batch, product, PO, factory" />
      </label>
    </div>

    <p v-if="error" class="error" role="alert">
      {{ error }} <button type="button" @click="load">Try again</button>
    </p>

    <div v-else class="table-wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Batch</th>
            <th scope="col">Order line</th>
            <th scope="col">COAs</th>
            <th scope="col">Status</th>
            <th scope="col" class="why-col">Why</th>
            <th scope="col" class="right">Updated</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="6" class="empty">Loading…</td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td colspan="6" class="empty">{{ search ? 'No batches match your search.' : emptyText[active] }}</td>
          </tr>
          <tr
            v-for="b in rows"
            v-else
            :key="b.id"
            class="row"
            tabindex="0"
            @click="router.push(`/batches/${b.id}`)"
            @keydown.enter="router.push(`/batches/${b.id}`)"
          >
            <td>
              <RouterLink :to="`/batches/${b.id}`" class="batch-no" @click.stop>{{ b.batch_number }}</RouterLink>
              <span class="meta">{{ b.product.name }} · {{ formatQty(b.quantity, b.unit) }}</span>
              <span class="meta">{{ b.factory?.name }}</span>
            </td>
            <td>
              <template v-if="b.line">
                <span>{{ b.line.po_number }}, line {{ b.line.line_no }}</span>
                <span class="meta">{{ b.line.grade }} · {{ b.line.customer }}</span>
              </template>
              <span v-else class="unassigned">Not assigned</span>
            </td>
            <td>
              <span class="sources">
                <span
                  v-for="s in ['factory', 'lab'] as const"
                  :key="s"
                  :class="['src', { have: b.coa_sources.includes(s) }]"
                  :title="`${SOURCE[s]}: ${b.coa_sources.includes(s) ? 'received' : 'not yet'}`"
                >
                  {{ s === 'factory' ? 'F' : 'L' }}
                </span>
              </span>
            </td>
            <td><StatusBadge v-bind="STATUS[b.status]" /></td>
            <td class="why">{{ b.summary ?? (b.line ? '' : 'Choose which order line this batch is for.') }}</td>
            <td class="right meta-cell">{{ formatDateTime(b.updated_at) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: 1.25rem;
}

.head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  align-items: flex-end;
  gap: 1rem;
}

h1 {
  font-size: var(--t-2xl);
}

.sub {
  color: var(--ink-2);
  font-size: var(--t-s);
  margin-top: 0.25rem;
}

.primary {
  display: inline-block;
  padding: 0.6rem 1rem;
  border-radius: var(--radius-s);
  background: var(--brand);
  color: var(--brand-ink);
  font-weight: 600;
  font-size: var(--t-s);
  text-decoration: none;
}

.bar {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.75rem;
}

.queues {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  padding: 0.25rem;
}

.queue {
  border: 0;
  background: none;
  padding: 0.4rem 0.7rem;
  border-radius: var(--radius-s);
  font-size: var(--t-s);
  color: var(--ink-2);
  cursor: pointer;
  display: inline-flex;
  gap: 0.45rem;
  align-items: center;
}

.queue:hover {
  background: var(--surface-2);
}

.queue.on {
  background: var(--brand);
  color: var(--brand-ink);
  font-weight: 600;
}

.n {
  font-size: var(--t-xs);
  opacity: 0.8;
}

.search input {
  font: inherit;
  font-size: var(--t-s);
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface);
  width: min(22rem, 100%);
}

.table-wrap {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--t-s);
  min-width: 52rem;
}

th {
  text-align: left;
  font-weight: 500;
  color: var(--ink-3);
  padding: 0.6rem 1rem;
}

td {
  padding: 0.75rem 1rem;
  border-top: 1px solid var(--line);
  vertical-align: top;
}

td > span {
  display: block;
}

.row {
  cursor: pointer;
}

.row:hover,
.row:focus-visible {
  background: var(--surface-2);
}

.batch-no {
  font-weight: 600;
  color: var(--ink);
  text-decoration: none;
}

.meta,
.meta-cell {
  color: var(--ink-3);
  font-size: var(--t-xs);
}

.meta-cell {
  white-space: nowrap;
}

.unassigned {
  color: var(--review);
  font-weight: 600;
}

.sources {
  display: inline-flex !important;
  gap: 0.25rem;
}

.src {
  width: 1.4rem;
  height: 1.4rem;
  display: grid;
  place-items: center;
  border-radius: var(--radius-s);
  border: 1px dashed var(--line);
  color: var(--ink-3);
  font-size: var(--t-xs);
  font-weight: 600;
}

.src.have {
  border: 1px solid var(--brand);
  background: var(--brand);
  color: var(--brand-ink);
}

.why-col {
  width: 34%;
}

.why {
  color: var(--ink-2);
}

.right {
  text-align: right;
}

.empty {
  color: var(--ink-2);
  text-align: center;
  padding: 2.5rem 1rem;
}

.error {
  color: var(--hold);
}
</style>
