<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import { auditSentence, formatDateTime } from '@/labels'
import type { AuditEntry, AuditPage } from '@/types'

const kinds = [
  { key: '', label: 'Everything' },
  { key: 'batch', label: 'Batches and COAs' },
  { key: 'order', label: 'Orders and customers' },
  { key: 'spec', label: 'Specs' },
  { key: 'knowledge', label: 'Knowledge' },
  { key: 'user', label: 'Sign-ins' },
]

const kind = ref('')
const entries = ref<AuditEntry[]>([])
const nextBefore = ref<number | null>(null)
const loading = ref(false)
const error = ref<string | null>(null)

/** Load audit entries. */
async function load(more = false) {
  loading.value = true
  error.value = null
  try {
    const params = new URLSearchParams({ limit: '50' })
    if (kind.value) params.set('kind', kind.value)
    if (more && nextBefore.value) params.set('before', String(nextBefore.value))
    const page = await api.get<AuditPage>(`/audit?${params}`)
    entries.value = more ? [...entries.value, ...page.entries] : page.entries
    nextBefore.value = page.next_before
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load the audit log.'
  } finally {
    loading.value = false
  }
}

/** The note recorded with an entry, if any. */
function note(e: AuditEntry): string | null {
  const n = e.data.note
  return typeof n === 'string' && n ? n : null
}

onMounted(() => load())
watch(kind, () => load())
</script>

<template>
  <div class="page">
    <header>
      <h1>Audit log</h1>
      <p class="sub">
        Every change that matters, newest first: who did it and when. Nothing here can be edited or
        deleted. “BatchGate” means the rules engine or the COA reader did it on its own.
      </p>
    </header>

    <div class="tabs" role="tablist" aria-label="Show">
      <button
        v-for="k in kinds"
        :key="k.key"
        type="button"
        role="tab"
        :aria-selected="kind === k.key"
        :class="['tab', { on: kind === k.key }]"
        @click="kind = k.key"
      >
        {{ k.label }}
      </button>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div v-else class="card">
      <table>
        <thead>
          <tr>
            <th scope="col" class="when">When</th>
            <th scope="col">What happened</th>
            <th scope="col">Item</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading && !entries.length">
            <td colspan="3" class="empty">Loading…</td>
          </tr>
          <tr v-else-if="!entries.length">
            <td colspan="3" class="empty">Nothing recorded yet.</td>
          </tr>
          <tr v-for="e in entries" :key="e.id">
            <td class="when">{{ formatDateTime(e.at) }}</td>
            <td>
              <strong>{{ e.actor ?? 'BatchGate' }}</strong> {{ auditSentence(e) }}
              <span v-if="note(e)" class="note">“{{ note(e) }}”</span>
            </td>
            <td>
              <RouterLink v-if="e.link" :to="e.link">{{ e.entity_label }}</RouterLink>
              <span v-else>{{ e.entity_label ?? '—' }}</span>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="nextBefore" class="more">
        <button type="button" class="link" :disabled="loading" @click="load(true)">
          {{ loading ? 'Loading…' : 'Load older entries' }}
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: 1.25rem;
}

h1 {
  font-size: var(--t-2xl);
}

.sub {
  color: var(--ink-2);
  font-size: var(--t-s);
  margin-top: 0.25rem;
  max-width: 70ch;
}

.tabs {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  justify-self: start;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  padding: 0.25rem;
}

.tab {
  border: 0;
  background: none;
  padding: 0.4rem 0.75rem;
  border-radius: var(--radius-s);
  font: inherit;
  font-size: var(--t-s);
  color: var(--ink-2);
  cursor: pointer;
}

.tab.on {
  background: var(--brand);
  color: var(--brand-ink);
  font-weight: 600;
}

.card {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--t-s);
  min-width: 38rem;
}

th {
  text-align: left;
  font-weight: 500;
  color: var(--ink-3);
  padding: 0.6rem 1rem;
}

td {
  padding: 0.65rem 1rem;
  border-top: 1px solid var(--line);
  vertical-align: top;
}

.when {
  white-space: nowrap;
  color: var(--ink-3);
  width: 9rem;
}

.note {
  display: block;
  color: var(--ink-2);
  font-style: italic;
  margin-top: 0.15rem;
}

.empty {
  text-align: center;
  color: var(--ink-2);
  padding: 2.5rem 1rem;
}

.more {
  border-top: 1px solid var(--line);
  padding: 0.75rem 1rem;
}

.link {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  font-size: var(--t-s);
  color: var(--approval);
  cursor: pointer;
}

.error {
  color: var(--hold);
}
</style>
