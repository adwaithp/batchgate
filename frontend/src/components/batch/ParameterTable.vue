<script setup lang="ts">
import { computed } from 'vue'

import StatusBadge from '@/components/StatusBadge.vue'
import { PARAM } from '@/labels'
import type { CoaSource, ParameterCheck, Reading, Spec } from '@/types'

const props = defineProps<{ checks: ParameterCheck[] | null; spec: Spec | null }>()

// Without a verdict yet, still show what the spec asks for.
const rows = computed<ParameterCheck[]>(() => {
  if (props.checks) return props.checks
  return (props.spec?.parameters ?? []).map((p) => ({
    parameter_id: p.id,
    name: p.name,
    spec_text: p.spec_text,
    critical: p.critical,
    status: 'missing' as const,
    readings: [],
    discrepancy: null,
    note: null,
  }))
})

function reading(check: ParameterCheck, source: CoaSource): Reading | undefined {
  return check.readings.find((r) => r.source === source)
}

function shown(r: Reading): string {
  const raw = r.raw_value.trim()
  return r.unit && !/[a-zA-Z%°]/.test(raw) ? `${raw} ${r.unit}` : raw
}

const hasNotes = (c: ParameterCheck) => c.discrepancy || (c.note && c.status !== 'pass')
</script>

<template>
  <section aria-labelledby="params-title">
    <h2 id="params-title">Parameters</h2>
    <div class="wrap">
      <table>
        <thead>
          <tr>
            <th scope="col">Test</th>
            <th scope="col">Spec</th>
            <th scope="col" class="right">Factory COA</th>
            <th scope="col" class="right">Lab COA</th>
            <th scope="col">Result</th>
          </tr>
        </thead>
        <tbody>
          <template v-for="c in rows" :key="c.parameter_id">
            <tr :class="[`st-${c.status}`, { 'has-notes': hasNotes(c) }]">
              <th scope="row">
                {{ c.name }}
                <span v-if="!c.critical" class="optional">not critical</span>
              </th>
              <td class="num">{{ c.spec_text }}</td>
              <td v-for="s in ['factory', 'lab'] as const" :key="s" class="num right">
                <span v-if="reading(c, s)" :class="['val', `v-${reading(c, s)!.status}`]">
                  {{ shown(reading(c, s)!) }}
                </span>
                <span v-else class="none">—</span>
              </td>
              <td>
                <StatusBadge v-if="checks" v-bind="PARAM[c.status]" />
              </td>
            </tr>
            <tr v-if="hasNotes(c)" class="note-row">
              <td colspan="5">
                <p v-if="c.discrepancy" class="note disc">Factory and lab disagree. {{ c.discrepancy }}</p>
                <p v-if="c.note && c.status !== 'pass'" class="note">{{ c.note }}</p>
              </td>
            </tr>
          </template>
        </tbody>
      </table>
    </div>
  </section>
</template>

<style scoped>
h2 {
  font-size: var(--t-l);
  margin-bottom: 0.6rem;
}

.wrap {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--t-s);
  min-width: 40rem;
}

thead th {
  text-align: left;
  font-weight: 500;
  color: var(--ink-3);
  padding: 0.55rem 1rem;
}

tbody th,
td {
  padding: 0.6rem 1rem;
  border-top: 1px solid var(--line);
  text-align: left;
}

tbody th {
  font-weight: 500;
}

.has-notes th,
.has-notes td {
  padding-bottom: 0.35rem;
}

.note-row td {
  border-top: 0;
  padding-top: 0;
  padding-bottom: 0.65rem;
}

.right {
  text-align: right;
}

.optional {
  display: block;
  font-size: var(--t-xs);
  font-weight: 400;
  color: var(--ink-3);
}

.st-fail th,
.st-fail td {
  background: var(--hold-bg);
}
.st-fail + .note-row td {
  background: var(--hold-bg);
}
.st-fail th {
  color: var(--hold);
  font-weight: 600;
}

.val.v-fail {
  color: var(--hold);
  font-weight: 700;
}

.val.v-unclear {
  color: var(--review);
  font-weight: 600;
  text-decoration: underline dotted;
}

.none {
  color: var(--ink-3);
}

.note {
  font-size: var(--t-xs);
  color: var(--ink-2);
}

.note.disc {
  color: var(--review);
  font-weight: 500;
}
</style>
