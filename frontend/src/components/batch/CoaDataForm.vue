<script setup lang="ts">
import { computed, ref } from 'vue'

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
  confidence: number // as read by Claude; 1 for anything a person typed
  needsCheck: boolean // Claude wasn't sure: a person should compare it with the document
  checked: boolean // ticked "Matches the document"
  original: string // the row as loaded, to tell whether a person edited it
}

/** A row's editable fields as one comparable string. */
const snapshot = (r: { name_as_written: string; raw_value: string; unit: string | null }) =>
  [r.name_as_written, r.raw_value, r.unit ?? ''].join('\u0000')
/** Whether a person changed the row. */
const edited = (r: Row) => snapshot(r) !== r.original
/** Whether a low-confidence row is still unchecked. */
const doubtful = (r: Row) => r.needsCheck && !r.checked && !edited(r)

const readByClaude = computed(
  () => !!props.coa.extraction_model && props.coa.extraction_model !== 'manual',
)

const header = ref({
  issuer_name: props.coa.issuer_name ?? '',
  product_name: props.coa.product_name ?? props.spec?.product ?? '',
  cas_number: props.coa.cas_number ?? '',
  batch_number: props.coa.batch_number ?? props.batchNumber,
  po_reference: props.coa.po_reference ?? '',
  mfg_date: props.coa.mfg_date ?? '',
  test_date: props.coa.test_date ?? '',
  expiry_date: props.coa.expiry_date ?? '',
})

// The issuer is vouched for like a result row: by editing or ticking it.
const issuerChecked = ref(false)
const issuerDoubtful = computed(
  () =>
    props.coa.issuer_needs_check &&
    !issuerChecked.value &&
    header.value.issuer_name === (props.coa.issuer_name ?? ''),
)

// One row per spec parameter, filled from what is already on this COA.
const used = new Set<number>()
const specRows: Row[] = (props.spec?.parameters ?? []).map((p) => {
  const existing = props.coa.results.find((r) => r.matched_parameter_id === p.id)
  if (existing) used.add(existing.id)
  const row = {
    parameter_id: p.id,
    label: p.name,
    hint: p.spec_text,
    name_as_written: existing?.name_as_written ?? p.name,
    raw_value: existing?.raw_value ?? '',
    unit: existing?.unit ?? p.unit ?? '',
    confidence: existing?.confidence ?? 1,
    needsCheck: existing?.needs_check ?? false,
    checked: false,
  }
  return { ...row, original: snapshot(row) }
})
// Rows printed on the COA that the spec doesn't ask for.
const extraRows: Row[] = props.coa.results
  .filter((r) => !used.has(r.id))
  .map((r) => ({
    parameter_id: null,
    label: '',
    hint: '',
    name_as_written: r.name_as_written,
    raw_value: r.raw_value,
    unit: r.unit ?? '',
    confidence: r.confidence,
    needsCheck: r.needs_check,
    checked: false,
    original: snapshot(r),
  }))

const rows = ref<Row[]>(specRows)
const extras = ref<Row[]>(extraRows)
const saving = ref(false)
const error = ref<string | null>(null)

/** Add an empty row for a result the spec doesn't list. */
function addExtra() {
  extras.value.push({
    parameter_id: null,
    label: '',
    hint: '',
    name_as_written: '',
    raw_value: '',
    unit: '',
    confidence: 1,
    needsCheck: false,
    checked: false,
    original: '',
  })
}

/** Trim text, or null when empty. */
const blank = (s: string) => (s.trim() ? s.trim() : null)
// A date only known as printed text: show it so a person can decide.
const printedOnly = (value: string | null, printed: string | null) => !value && !!printed

/** Save the values and re-check the batch. */
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
        // Edited or ticked rows count as checked; untouched doubtful rows stay in review.
        confidence: r.checked || edited(r) ? 1 : r.confidence,
        parameter_id: r.parameter_id,
      }))
    const h = header.value
    const detail = await api.put<BatchDetail>(`/coas/${props.coa.id}/data`, {
      issuer_name: blank(h.issuer_name),
      issuer_confidence: issuerDoubtful.value ? props.coa.issuer_confidence : 1,
      product_name: blank(h.product_name),
      cas_number: blank(h.cas_number),
      batch_number: blank(h.batch_number),
      po_reference: blank(h.po_reference),
      mfg_date: h.mfg_date || null,
      test_date: h.test_date || null,
      expiry_date: h.expiry_date || null,
      // kept so a month-only expiry is still checked after saving
      mfg_date_as_printed: props.coa.mfg_date_as_printed,
      test_date_as_printed: props.coa.test_date_as_printed,
      expiry_date_as_printed: props.coa.expiry_date_as_printed,
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
    <p v-if="readByClaude" class="lead">
      Claude read these values from the document. Compare them with the COA before saving,
      especially rows marked “Check this”: fix anything that’s wrong, or tick “Matches the
      document”. Rows left unchecked keep the batch in review.
    </p>
    <p v-else class="lead">
      Type the values exactly as printed on the COA, including signs like “&lt; 0.01” or words like
      “Complies”. BatchGate converts units and compares against the spec.
    </p>

    <div v-if="coa.warnings.length" class="warnings">
      <p>Claude noted:</p>
      <ul>
        <li v-for="w in coa.warnings" :key="w">{{ w }}</li>
      </ul>
    </div>

    <fieldset class="header">
      <legend>As printed on the COA</legend>
      <label :class="{ doubt: issuerDoubtful }">
        Issued by <input v-model="header.issuer_name" placeholder="Company on the letterhead" />
        <span v-if="coa.issuer_needs_check" class="check">
          <input v-model="issuerChecked" type="checkbox" aria-label="Issuer matches the document" />
          {{
            issuerDoubtful
              ? `Check this: Claude wasn’t sure (${Math.round(coa.issuer_confidence * 100)}%)`
              : 'Matches the document'
          }}
        </span>
      </label>
      <label>Product name <input v-model="header.product_name" /></label>
      <label>CAS number <input v-model="header.cas_number" placeholder="e.g. 7705-08-0" /></label>
      <label>Batch number <input v-model="header.batch_number" /></label>
      <label>PO reference <input v-model="header.po_reference" placeholder="If printed" /></label>
      <label>
        Manufactured <input v-model="header.mfg_date" type="date" />
        <span v-if="printedOnly(coa.mfg_date, coa.mfg_date_as_printed)" class="hint"
          >Printed as “{{ coa.mfg_date_as_printed }}”</span
        >
      </label>
      <label>
        Tested <input v-model="header.test_date" type="date" />
        <span v-if="printedOnly(coa.test_date, coa.test_date_as_printed)" class="hint"
          >Printed as “{{ coa.test_date_as_printed }}”</span
        >
      </label>
      <label>
        Expires <input v-model="header.expiry_date" type="date" />
        <span v-if="printedOnly(coa.expiry_date, coa.expiry_date_as_printed)" class="hint"
          >Printed as “{{ coa.expiry_date_as_printed }}”</span
        >
      </label>
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
        <tr v-for="r in rows" :key="`p${r.parameter_id}`" :class="{ doubt: doubtful(r) }">
          <th scope="row">
            {{ r.label }}
            <span class="hint">{{ r.hint }}</span>
            <label v-if="r.needsCheck" class="check">
              <input v-model="r.checked" type="checkbox" />
              {{
                doubtful(r)
                  ? `Check this: Claude wasn’t sure (${Math.round(r.confidence * 100)}%)`
                  : 'Matches the document'
              }}
            </label>
          </th>
          <td><input v-model="r.name_as_written" :aria-label="`${r.label}: name on COA`" /></td>
          <td><input v-model="r.raw_value" class="value" :aria-label="`${r.label}: result`" /></td>
          <td><input v-model="r.unit" class="unit" :aria-label="`${r.label}: unit`" /></td>
        </tr>
        <tr v-for="(r, i) in extras" :key="`x${i}`" :class="{ doubt: doubtful(r) }">
          <th scope="row">
            <span class="hint">Not in spec</span>
            <label v-if="r.needsCheck" class="check">
              <input v-model="r.checked" type="checkbox" />
              {{
                doubtful(r)
                  ? `Check this: Claude wasn’t sure (${Math.round(r.confidence * 100)}%)`
                  : 'Matches the document'
              }}
            </label>
          </th>
          <td>
            <input
              v-model="r.name_as_written"
              aria-label="Other result: name"
              placeholder="Test name"
            />
          </td>
          <td><input v-model="r.raw_value" class="value" aria-label="Other result: value" /></td>
          <td><input v-model="r.unit" class="unit" aria-label="Other result: unit" /></td>
        </tr>
      </tbody>
    </table>
    <button type="button" class="link" @click="addExtra">
      Add a result that isn’t in the spec
    </button>

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

tr.doubt,
label.doubt {
  background: var(--review-bg);
}

label.doubt {
  border-radius: var(--radius-s);
  padding: 0.25rem;
  margin: -0.25rem;
}

.check {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  margin-top: 0.25rem;
  font-size: var(--t-xs);
  font-weight: 500;
  color: var(--review);
}

.check input {
  width: auto;
}

.warnings {
  font-size: var(--t-s);
  background: var(--review-bg);
  border-radius: var(--radius-s);
  padding: 0.6rem 0.8rem;
}

.warnings ul {
  margin: 0.3rem 0 0;
  padding-left: 1.1rem;
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
