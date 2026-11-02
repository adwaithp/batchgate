<script setup lang="ts">
import { ref } from 'vue'

import { api } from '@/api/client'
import type { BatchDetail, Coa, Spec } from '@/types'

const props = defineProps<{ coa: Coa; spec: Spec | null; batchNumber: string }>()
const emit = defineEmits<{ saved: [BatchDetail]; cancel: [] }>()

interface Row {
  parameter_id: number | null
  label: string // spec name, shown as the row heading
  hint: string // spec limit, as a reminder
  name_as_written: string
  raw_value: string
  unit: string
}

const header = ref({
  product_name: props.coa.product_name ?? props.spec?.product ?? '',
  cas_number: props.coa.cas_number ?? '',
  batch_number: props.coa.batch_number ?? props.batchNumber,
  po_reference: props.coa.po_reference ?? '',
  mfg_date: props.coa.mfg_date ?? '',
  test_date: props.coa.test_date ?? '',
  expiry_date: props.coa.expiry_date ?? '',
})

// One row per spec parameter, filled from what is already on this COA.
const used = new Set<number>()
const specRows: Row[] = (props.spec?.parameters ?? []).map((p) => {
  const existing = props.coa.results.find((r) => r.matched_parameter_id === p.id)
  if (existing) used.add(existing.id)
  return {
    parameter_id: p.id,
    label: p.name,
    hint: p.spec_text,
    name_as_written: existing?.name_as_written ?? p.name,
    raw_value: existing?.raw_value ?? '',
    unit: existing?.unit ?? p.unit ?? '',
  }
})
// Anything else printed on the COA that the spec doesn't ask for.
const extraRows: Row[] = props.coa.results
  .filter((r) => !used.has(r.id))
  .map((r) => ({
    parameter_id: null,
    label: '',
    hint: '',
    name_as_written: r.name_as_written,
    raw_value: r.raw_value,
    unit: r.unit ?? '',
  }))

const rows = ref<Row[]>(specRows)
const extras = ref<Row[]>(extraRows)
const saving = ref(false)
const error = ref<string | null>(null)

function addExtra() {
  extras.value.push({ parameter_id: null, label: '', hint: '', name_as_written: '', raw_value: '', unit: '' })
}

const blank = (s: string) => (s.trim() ? s.trim() : null)

async function save() {
  error.value = null
  saving.value = true
  try {
    const results = [...rows.value, ...extras.value]
      .filter((r) => r.raw_value.trim() && r.name_as_written.trim())
      .map((r) => ({
        name_as_written: r.name_as_written.trim(),
        raw_value: r.raw_value.trim(),
        unit: blank(r.unit),
        parameter_id: r.parameter_id,
      }))
    const h = header.value
    const detail = await api.put<BatchDetail>(`/coas/${props.coa.id}/data`, {
      product_name: blank(h.product_name),
      cas_number: blank(h.cas_number),
      batch_number: blank(h.batch_number),
      po_reference: blank(h.po_reference),
      mfg_date: h.mfg_date || null,
      test_date: h.test_date || null,
      expiry_date: h.expiry_date || null,
      results,
    })
    emit('saved', detail)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not save the values.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <form class="entry" @submit.prevent="save">
    <p class="lead">
      Type the values exactly as printed on the COA, including signs like “&lt; 0.01” or words like
      “Complies”. BatchGate converts units and compares against the spec.
    </p>

    <fieldset class="header">
      <legend>As printed on the COA</legend>
      <label>Product name <input v-model="header.product_name" /></label>
      <label>CAS number <input v-model="header.cas_number" placeholder="e.g. 7705-08-0" /></label>
      <label>Batch number <input v-model="header.batch_number" /></label>
      <label>PO reference <input v-model="header.po_reference" placeholder="If printed" /></label>
      <label>Manufactured <input v-model="header.mfg_date" type="date" /></label>
      <label>Tested <input v-model="header.test_date" type="date" /></label>
      <label>Expires <input v-model="header.expiry_date" type="date" /></label>
    </fieldset>

    <table>
      <thead>
        <tr>
          <th scope="col">Test</th>
          <th scope="col">Name on COA</th>
          <th scope="col">Result</th>
          <th scope="col">Unit</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="r in rows" :key="`p${r.parameter_id}`">
          <th scope="row">
            {{ r.label }}
            <span class="hint">{{ r.hint }}</span>
          </th>
          <td><input v-model="r.name_as_written" :aria-label="`${r.label}: name on COA`" /></td>
          <td><input v-model="r.raw_value" class="value" :aria-label="`${r.label}: result`" /></td>
          <td><input v-model="r.unit" class="unit" :aria-label="`${r.label}: unit`" /></td>
        </tr>
        <tr v-for="(r, i) in extras" :key="`x${i}`">
          <th scope="row"><span class="hint">Not in spec</span></th>
          <td><input v-model="r.name_as_written" aria-label="Other result: name" placeholder="Test name" /></td>
          <td><input v-model="r.raw_value" class="value" aria-label="Other result: value" /></td>
          <td><input v-model="r.unit" class="unit" aria-label="Other result: unit" /></td>
        </tr>
      </tbody>
    </table>
    <button type="button" class="link" @click="addExtra">Add a result that isn’t in the spec</button>

    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="actions">
      <button type="submit" class="primary" :disabled="saving">
        {{ saving ? 'Saving…' : 'Save values and run check' }}
      </button>
      <button type="button" class="secondary" @click="emit('cancel')">Cancel</button>
    </div>
  </form>
</template>

<style scoped>
.entry {
  display: grid;
  gap: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--line);
}

.lead {
  font-size: var(--t-s);
  color: var(--ink-2);
  max-width: 70ch;
}

.header {
  border: 0;
  padding: 0;
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(10.5rem, 1fr));
  gap: 0.75rem;
}

legend {
  font-weight: 600;
  font-size: var(--t-s);
  margin-bottom: 0.5rem;
}

label {
  display: grid;
  gap: 0.25rem;
  font-size: var(--t-xs);
  color: var(--ink-2);
}

input {
  font: inherit;
  font-size: var(--t-s);
  color: var(--ink);
  padding: 0.4rem 0.55rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface);
  width: 100%;
  min-width: 0;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--t-s);
}

thead th {
  text-align: left;
  font-weight: 500;
  color: var(--ink-3);
  padding: 0 0.4rem 0.4rem;
}

tbody th,
td {
  padding: 0.3rem 0.4rem;
  text-align: left;
  vertical-align: middle;
}

tbody th {
  font-weight: 500;
  width: 30%;
}

.hint {
  display: block;
  font-size: var(--t-xs);
  font-weight: 400;
  color: var(--ink-3);
}

.value {
  font-variant-numeric: tabular-nums;
}

.unit {
  max-width: 6rem;
}

.link {
  justify-self: start;
  border: 0;
  background: none;
  padding: 0;
  color: var(--approval);
  font-size: var(--t-s);
  cursor: pointer;
}

.actions {
  display: flex;
  gap: 0.75rem;
}

.primary,
.secondary {
  padding: 0.55rem 1rem;
  border-radius: var(--radius-s);
  font-weight: 600;
  font-size: var(--t-s);
  cursor: pointer;
}

.primary {
  border: 0;
  background: var(--brand);
  color: var(--brand-ink);
}

.primary:disabled {
  opacity: 0.55;
}

.secondary {
  border: 1px solid var(--line);
  background: var(--surface);
}

.error {
  color: var(--hold);
  font-size: var(--t-s);
}
</style>
