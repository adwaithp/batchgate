<script setup lang="ts">
import { computed } from 'vue'

import { ACTION, DECISION, formatDateTime } from '@/labels'
import type { BatchDetail } from '@/types'

const props = defineProps<{ batch: BatchDetail }>()

interface Entry {
  key: string
  at: string
  who: string
  what: string
  note: string | null
  tone: string
}

const entries = computed<Entry[]>(() => {
  const people: Entry[] = props.batch.actions
    .filter((a) => a.action !== 'rerun_check')
    .map((a) => ({
      key: `a${a.id}`,
      at: a.created_at,
      who: `${a.actor} (${a.actor_role})`,
      what: ACTION[a.action].past,
      note: a.note,
      tone:
        a.action === 'approve_release'
          ? 'release'
          : a.action === 'hold' || a.action === 'reject'
            ? 'hold'
            : 'approval',
    }))
  const checks: Entry[] = props.batch.history.map((v) => ({
    key: `v${v.id}`,
    at: v.created_at,
    who: 'BatchGate check',
    what: `recommended ${DECISION[v.decision].label.toLowerCase()}`,
    note: v.summary,
    tone: DECISION[v.decision].tone,
  }))
  return [...people, ...checks].sort((a, b) => (a.at < b.at ? 1 : a.at > b.at ? -1 : 0))
})
</script>

<template>
  <section aria-labelledby="history-title">
    <h2 id="history-title">History</h2>
    <p v-if="!entries.length" class="muted">No checks or decisions yet.</p>
    <ol v-else class="timeline">
      <li v-for="e in entries" :key="e.key" :class="`tone-${e.tone}`">
        <span class="when">{{ formatDateTime(e.at) }}</span>
        <p>
          <strong>{{ e.who }}</strong> {{ e.what }}
        </p>
        <p v-if="e.note" class="note">{{ e.note }}</p>
      </li>
    </ol>
  </section>
</template>

<style scoped>
h2 {
  font-size: var(--t-l);
  margin-bottom: 0.6rem;
}

.timeline {
  list-style: none;
  margin: 0;
  padding: 0 0 0 0.9rem;
  border-left: 2px solid var(--line);
  display: grid;
  gap: 0.9rem;
}

li {
  --c: var(--idle);
  position: relative;
  font-size: var(--t-s);
}

li::before {
  content: '';
  position: absolute;
  left: calc(-0.9rem - 6px);
  top: 0.3rem;
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--c);
  border: 2px solid var(--paper);
}

.tone-release {
  --c: var(--release);
}
.tone-review {
  --c: var(--review);
}
.tone-approval {
  --c: var(--approval);
}
.tone-hold {
  --c: var(--hold);
}

.when {
  font-size: var(--t-xs);
  color: var(--ink-3);
}

.note {
  margin-top: 0.15rem;
  font-size: var(--t-xs);
  color: var(--ink-2);
}

.muted {
  color: var(--ink-2);
  font-size: var(--t-s);
}
</style>
