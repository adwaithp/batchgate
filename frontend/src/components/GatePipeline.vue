<script setup lang="ts">
import { computed } from 'vue'

import type { BatchStatus } from '@/types'

const props = defineProps<{
  counts: Record<BatchStatus, number>
  focus?: BatchStatus // the stage this user acts on
}>()

// The path a batch takes through the gate, in order.
const stages: { key: BatchStatus; label: string; who: string; tone: string }[] = [
  { key: 'awaiting_coa', label: 'Awaiting COA', who: 'Factory and lab send reports', tone: 'idle' },
  {
    key: 'pending_review',
    label: 'Needs review',
    who: 'QC analyst checks flagged items',
    tone: 'review',
  },
  {
    key: 'pending_approval',
    label: 'Waiting approval',
    who: 'QC manager confirms release',
    tone: 'approval',
  },
  { key: 'released', label: 'Released', who: 'Cleared to ship', tone: 'release' },
]

const offPath: { key: BatchStatus; label: string; tone: string }[] = [
  { key: 'on_hold', label: 'On hold', tone: 'hold' },
  { key: 'rejected', label: 'Rejected', tone: 'hold' },
]

const total = computed(() => Object.values(props.counts).reduce((a, b) => a + b, 0))
</script>

<template>
  <section class="gate" aria-labelledby="gate-title">
    <header>
      <h2 id="gate-title">Batches at the gate</h2>
      <p v-if="total === 0" class="empty">
        No batches yet. A batch appears here as soon as its first COA is uploaded.
      </p>
    </header>

    <ol class="stages">
      <li
        v-for="(stage, i) in stages"
        :key="stage.key"
        :class="['stage', `tone-${stage.tone}`, { focus: focus === stage.key }]"
        :aria-current="focus === stage.key ? 'step' : undefined"
      >
        <RouterLink :to="{ path: '/batches', query: { status: stage.key } }" class="cover">
          <span class="visually-hidden">Open {{ stage.label }} queue</span>
        </RouterLink>
        <span class="step">{{ i + 1 }}</span>
        <span class="count num">{{ counts[stage.key] ?? 0 }}</span>
        <span class="label">{{ stage.label }}</span>
        <span class="who">{{ stage.who }}</span>
        <span v-if="focus === stage.key" class="yours">Your queue</span>
      </li>
    </ol>

    <ul class="off">
      <li v-for="s in offPath" :key="s.key" :class="`tone-${s.tone}`">
        <RouterLink :to="{ path: '/batches', query: { status: s.key } }">
          <span class="dot" aria-hidden="true" />
          {{ s.label }}
          <strong class="num">{{ counts[s.key] ?? 0 }}</strong>
        </RouterLink>
      </li>
    </ul>
  </section>
</template>

<style scoped>
.gate {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  padding: 1.25rem 1.25rem 1rem;
}

header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  justify-content: space-between;
  gap: 0.5rem 1rem;
  margin-bottom: 1rem;
}

h2 {
  font-size: var(--t-l);
}

.empty {
  font-size: var(--t-s);
  color: var(--ink-2);
}

.stages {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 0;
}

.stage {
  --c: var(--idle);
  --bg: var(--idle-bg);
  position: relative;
  display: grid;
  grid-template-columns: auto 1fr;
  grid-template-rows: auto auto auto;
  column-gap: 0.6rem;
  padding: 1rem 1.1rem 1rem 1rem;
  background: var(--surface-2);
  border-top: 4px solid var(--c);
  clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 50%, calc(100% - 14px) 100%, 0 100%, 14px 50%);
  margin-left: -10px;
}

.stage:first-child {
  margin-left: 0;
  clip-path: polygon(0 0, calc(100% - 14px) 0, 100% 50%, calc(100% - 14px) 100%, 0 100%);
}

.stage.focus {
  background: var(--bg);
}

.stage:hover {
  filter: brightness(0.98);
}

.cover {
  position: absolute;
  inset: 0;
  z-index: 1;
}

.cover:focus-visible {
  box-shadow: inset var(--focus);
}

.tone-review {
  --c: var(--review);
  --bg: var(--review-bg);
}
.tone-approval {
  --c: var(--approval);
  --bg: var(--approval-bg);
}
.tone-release {
  --c: var(--release);
  --bg: var(--release-bg);
}
.tone-hold {
  --c: var(--hold);
  --bg: var(--hold-bg);
}

.step {
  grid-row: 1 / span 3;
  align-self: start;
  margin-top: 0.35rem;
  margin-left: 0.6rem;
  width: 1.4rem;
  height: 1.4rem;
  border-radius: 50%;
  display: grid;
  place-items: center;
  font-size: var(--t-xs);
  font-weight: 600;
  color: var(--surface);
  background: var(--c);
}

.stage:first-child .step {
  margin-left: 0;
}

.count {
  font-size: var(--t-2xl);
  font-weight: 600;
  line-height: 1.1;
  color: var(--c);
}

.label {
  font-weight: 600;
  font-size: var(--t-s);
}

.who {
  font-size: var(--t-xs);
  color: var(--ink-2);
  padding-right: 0.5rem;
}

.yours {
  position: absolute;
  top: 0.6rem;
  right: 1.4rem;
  font-size: var(--t-xs);
  font-weight: 600;
  color: var(--c);
}

.off {
  list-style: none;
  margin: 0.9rem 0 0;
  padding: 0;
  display: flex;
  gap: 1.5rem;
  font-size: var(--t-s);
  color: var(--ink-2);
}

.off a {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  color: inherit;
  text-decoration: none;
}

.off a:hover {
  color: var(--ink);
}

.dot {
  width: 0.55rem;
  height: 0.55rem;
  border-radius: 50%;
  background: var(--c, var(--hold));
}

.off .tone-hold {
  --c: var(--hold);
}

.off strong {
  color: var(--ink);
}

@media (max-width: 900px) {
  .stages {
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 0.5rem;
  }
  .stage,
  .stage:first-child {
    clip-path: none;
    margin-left: 0;
    border-radius: var(--radius-s);
  }
  .step {
    margin-left: 0;
  }
}
</style>
