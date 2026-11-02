<script setup lang="ts">
import { computed, ref } from 'vue'

import { DECISION, formatDateTime } from '@/labels'
import type { BatchDetail } from '@/types'

const props = defineProps<{ batch: BatchDetail }>()

const verdict = computed(() => props.batch.verdict)
const blocking = computed(() => {
  const list = verdict.value?.details.findings.filter((f) => f.severity !== 'info') ?? []
  // One reason that is already the headline doesn't need repeating.
  return list.length === 1 && verdict.value!.summary.endsWith(list[0]!.message) ? [] : list
})

// For a closed batch, the people's decision comes first; the check's advice second.
const final = computed(() => {
  const b = props.batch
  if (b.status !== 'released' && b.status !== 'rejected') return null
  const action = [...b.actions]
    .reverse()
    .find((a) => a.action === (b.status === 'released' ? 'approve_release' : 'reject'))
  const overridden = verdict.value && verdict.value.decision !== (b.status === 'released' ? 'release' : 'hold')
  return { action, released: b.status === 'released', overridden }
})
const notes = computed(() => verdict.value?.details.findings.filter((f) => f.severity === 'info') ?? [])
const notesLabel = computed(() =>
  notes.value.length === 1 ? '1 note that doesn’t' : `${notes.value.length} notes that don’t`,
)
const showNotes = ref(false)

// When there is no verdict, say what is missing instead.
const waiting = computed(() => {
  const b = props.batch
  if (b.status === 'released' || b.status === 'rejected') return null
  if (!b.coas.some((c) => !c.superseded && c.extraction_status === 'done')) {
    return b.coas.length
      ? 'COA received. Enter its values to run the check.'
      : 'Waiting for the factory and lab COAs.'
  }
  if (!b.line) return 'Choose which order line this batch is for, so it can be checked against that spec.'
  return null
})
</script>

<template>
  <section
    class="verdict"
    :class="final ? (final.released ? 'tone-release' : 'tone-hold') : verdict ? `tone-${DECISION[verdict.decision].tone}` : 'tone-idle'"
    aria-labelledby="verdict-title"
  >
    <h2 id="verdict-title" class="visually-hidden">Check result</h2>

    <div v-if="final" class="top">
      <span class="stamp" role="img" :aria-label="final.released ? 'Released' : 'Rejected'">
        {{ final.released ? 'Released' : 'Rejected' }}
      </span>
      <div>
        <p class="summary">
          <template v-if="final.action">
            {{ final.action.actor }} ({{ final.action.actor_role }})
            {{ final.released ? 'approved the release' : 'rejected the batch' }}
            on {{ formatDateTime(final.action.created_at) }}.
          </template>
          <template v-else>{{ final.released ? 'Released.' : 'Rejected.' }}</template>
        </p>
        <p v-if="final.overridden" class="override">
          This overrides the check, which recommended
          {{ DECISION[verdict!.decision].label.toLowerCase() }}. The reasons are kept below and in
          the history.
        </p>
      </div>
    </div>

    <template v-if="verdict">
      <div v-if="!final" class="top">
        <span class="stamp" role="img" :aria-label="`Decision: ${DECISION[verdict.decision].label}`">
          {{ DECISION[verdict.decision].label }}
        </span>
        <p class="summary">{{ verdict.summary }}</p>
      </div>

      <p v-if="final" class="was">The check said: {{ verdict.summary }}</p>
      <ul v-if="blocking.length" class="reasons">
        <li v-for="(f, i) in blocking" :key="i" :class="`sev-${f.severity}`">
          <span class="sev">{{ f.severity === 'hold' ? 'Blocks release' : 'Check' }}</span>
          {{ f.message }}
        </li>
      </ul>

      <div v-if="notes.length" class="notes">
        <button type="button" class="link" :aria-expanded="showNotes" @click="showNotes = !showNotes">
          {{ showNotes ? 'Hide' : 'Show' }} {{ notesLabel }} affect the decision
        </button>
        <ul v-if="showNotes">
          <li v-for="(f, i) in notes" :key="i">{{ f.message }}</li>
        </ul>
      </div>

      <p class="foot">
        Checked {{ formatDateTime(verdict.created_at) }} by the rules engine ({{ verdict.engine_version }}).
        The decision is made by code, not by AI.
      </p>
    </template>

    <p v-else-if="waiting" class="waiting">{{ waiting }}</p>
  </section>
</template>

<style scoped>
.verdict {
  --c: var(--idle);
  --bg: var(--surface);
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 5px solid var(--c);
  border-radius: var(--radius-m);
  padding: 1.1rem 1.25rem;
  display: grid;
  gap: 0.9rem;
}

.tone-hold {
  --c: var(--hold);
  --bg: var(--hold-bg);
}
.tone-review {
  --c: var(--review);
  --bg: var(--review-bg);
}
.tone-release {
  --c: var(--release);
  --bg: var(--release-bg);
}

.top {
  display: flex;
  align-items: flex-start;
  gap: 1.1rem;
}

.stamp {
  flex: none;
  color: var(--c);
  border: 2.5px solid var(--c);
  border-radius: var(--radius-s);
  padding: 0.15rem 0.75rem;
  font-weight: 700;
  font-size: var(--t-l);
  transform: rotate(-4deg);
  margin-top: 0.1rem;
}

.summary {
  font-size: var(--t-l);
  font-weight: 500;
  line-height: 1.35;
  max-width: 60ch;
}

.override {
  margin-top: 0.3rem;
  font-size: var(--t-s);
  color: var(--ink-2);
}

.was {
  font-size: var(--t-s);
  color: var(--ink-2);
  padding-top: 0.75rem;
  border-top: 1px solid var(--line);
}

.reasons {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.4rem;
}

.reasons li {
  font-size: var(--t-s);
  padding: 0.5rem 0.7rem;
  border-radius: var(--radius-s);
  background: var(--review-bg);
}

.reasons li.sev-hold {
  background: var(--hold-bg);
}

.sev {
  display: block;
  font-size: var(--t-xs);
  font-weight: 600;
  color: var(--review);
}

.sev-hold .sev {
  color: var(--hold);
}

.notes ul {
  margin: 0.4rem 0 0;
  padding-left: 1.1rem;
  font-size: var(--t-s);
  color: var(--ink-2);
}

.link {
  border: 0;
  background: none;
  padding: 0;
  color: var(--approval);
  font-size: var(--t-s);
  cursor: pointer;
}

.foot {
  font-size: var(--t-xs);
  color: var(--ink-3);
}

.waiting {
  color: var(--ink-2);
}
</style>
