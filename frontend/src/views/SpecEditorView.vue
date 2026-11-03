<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import NewCustomerForm from '@/components/NewCustomerForm.vue'
import { RULE } from '@/labels'
import { useAuthStore } from '@/stores/auth'
import type { CustomerRef, ReferenceData, RuleType, SpecDetail, SpecParameterIn } from '@/types'

/** No id: a new spec. With an id: a new version of that spec. */
const props = defineProps<{ id?: number }>()
const router = useRouter()
const route = useRoute()
const auth = useAuthStore()
const addingCustomer = ref(false)

const editing = computed(() => props.id !== undefined)
const reference = ref<ReferenceData | null>(null)
const current = ref<SpecDetail | null>(null)
const error = ref<string | null>(null)
const saving = ref(false)

const head = ref({
  customer_id: null as number | null,
  product_id: null as number | null,
  grade: '',
})
const notes = ref('')

interface Row extends Omit<SpecParameterIn, 'aliases'> {
  key: number
  aliases: string // comma-separated in the form
  tolerance_mode: 'default' | 'abs' | 'pct'
}

let nextKey = 1
/** An empty test row. */
const blank = (): Row => ({
  key: nextKey++,
  name: '',
  rule_type: 'max',
  low: null,
  high: null,
  unit: '%',
  expected_text: null,
  aliases: '',
  method: null,
  critical: true,
  tolerance_pct: null,
  tolerance_abs: null,
  tolerance_mode: 'default',
})
const rows = ref<Row[]>([blank()])

const NUMERIC: RuleType[] = ['min', 'max', 'range']
/** Whether the rule needs a lower limit. */
const needsLow = (r: Row) => r.rule_type === 'min' || r.rule_type === 'range'
/** Whether the rule needs an upper limit. */
const needsHigh = (r: Row) => r.rule_type === 'max' || r.rule_type === 'range'

onMounted(async () => {
  try {
    if (props.id !== undefined) {
      const spec = await api.get<SpecDetail>(`/specs/${props.id}`)
      if (!spec.can_edit) {
        await router.replace(`/specs/${spec.id}`)
        return
      }
      current.value = spec
      rows.value = spec.parameters.map((p) => ({
        key: nextKey++,
        name: p.name,
        rule_type: p.rule_type,
        low: p.low,
        high: p.high,
        unit: p.unit,
        expected_text: p.expected_text,
        aliases: p.aliases.join(', '),
        method: p.method,
        critical: p.critical,
        tolerance_pct: p.tolerance_pct,
        tolerance_abs: p.tolerance_abs,
        tolerance_mode:
          p.tolerance_abs !== null ? 'abs' : p.tolerance_pct !== null ? 'pct' : 'default',
      }))
    } else {
      reference.value = await api.get<ReferenceData>('/reference')
      // Preselect the customer passed by the order form.
      const asked = Number(route.query.customer)
      if (reference.value.customers.some((c) => c.id === asked)) head.value.customer_id = asked
    }
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load the form.'
  }
})

/** Add the new customer to the list and select it. */
function customerAdded(customer: CustomerRef) {
  const list = reference.value!.customers
  list.push(customer)
  list.sort((a, b) => a.name.localeCompare(b.name))
  head.value.customer_id = customer.id
  addingCustomer.value = false
}

/** Move a test row up or down. */
function move(i: number, by: -1 | 1) {
  const j = i + by
  if (j < 0 || j >= rows.value.length) return
  const list = rows.value
  ;[list[i], list[j]] = [list[j]!, list[i]!]
}

/** Convert a form row to the API's parameter shape. */
function toPayload(r: Row): SpecParameterIn {
  const numeric = NUMERIC.includes(r.rule_type)
  const num = (v: number | null | string) =>
    v === '' || v === null || Number.isNaN(v) ? null : Number(v)
  return {
    name: r.name.trim(),
    rule_type: r.rule_type,
    low: needsLow(r) ? num(r.low) : null,
    high: needsHigh(r) ? num(r.high) : null,
    unit: numeric ? r.unit?.trim() || null : null,
    expected_text: r.rule_type === 'text_match' ? r.expected_text?.trim() || null : null,
    aliases: r.aliases
      .split(',')
      .map((a) => a.trim())
      .filter(Boolean),
    method: r.method?.trim() || null,
    critical: r.critical,
    tolerance_abs: numeric && r.tolerance_mode === 'abs' ? num(r.tolerance_abs) : null,
    tolerance_pct: numeric && r.tolerance_mode === 'pct' ? num(r.tolerance_pct) : null,
  }
}

const canSave = computed(
  () =>
    !saving.value &&
    rows.value.length > 0 &&
    (editing.value || (head.value.customer_id && head.value.product_id && head.value.grade.trim())),
)

/** Create the spec or its next version, then open it. */
async function save() {
  error.value = null
  saving.value = true
  try {
    const parameters = rows.value.map(toPayload)
    const spec = editing.value
      ? await api.post<SpecDetail>(`/specs/${props.id}/versions`, {
          notes: notes.value || null,
          parameters,
        })
      : await api.post<SpecDetail>('/specs', {
          ...head.value,
          grade: head.value.grade.trim(),
          notes: notes.value || null,
          parameters,
        })
    await router.push(`/specs/${spec.id}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not save the spec.'
  } finally {
    saving.value = false
  }
}

const backTo = computed(() => (props.id !== undefined ? `/specs/${props.id}` : '/specs'))
</script>

<template>
  <div class="page">
    <RouterLink :to="backTo" class="back">{{ editing ? 'Back to the spec' : 'Specs' }}</RouterLink>

    <div>
      <h1 v-if="current">Change {{ current.product.name }} · {{ current.grade }}</h1>
      <h1 v-else>New spec</h1>
      <p v-if="current" class="sub">
        Saving creates version {{ current.version + 1 }} for {{ current.customer.name }}. New orders
        use it from then on.
        <template v-if="current.used_by.length">
          The {{ current.used_by.length }} open order line{{
            current.used_by.length === 1 ? '' : 's'
          }}
          already placed keep{{ current.used_by.length === 1 ? 's' : '' }} the version agreed at the
          time.
        </template>
      </p>
      <p v-else class="sub">
        Copy the limits from the customer’s specification sheet. Each test becomes a check BatchGate
        runs on every COA for this customer, product and grade.
      </p>
    </div>

    <p v-if="error && !reference && !current" class="error" role="alert">{{ error }}</p>

    <form v-if="reference || current" class="form" @submit.prevent="save">
      <section v-if="reference" class="card pad grid">
        <div class="customer-field">
          <label class="field">
            Customer
            <select v-model="head.customer_id" required>
              <option :value="null" disabled>Choose a customer</option>
              <option v-for="c in reference.customers" :key="c.id" :value="c.id">
                {{ c.name }}
              </option>
            </select>
          </label>
          <button
            v-if="auth.can('customers:add') && !addingCustomer"
            type="button"
            class="link-btn add-customer"
            @click="addingCustomer = true"
          >
            + New customer
          </button>
        </div>
        <label class="field">
          Product
          <select v-model="head.product_id" required>
            <option :value="null" disabled>Choose a product</option>
            <option v-for="p in reference.products" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>
        <label class="field">
          Grade
          <input v-model="head.grade" placeholder="e.g. Anhydrous 98%" maxlength="64" required />
          <span class="hint">How the customer names it on their PO.</span>
        </label>
      </section>

      <NewCustomerForm
        v-if="addingCustomer"
        @added="customerAdded"
        @cancel="addingCustomer = false"
      />

      <section class="card">
        <header class="tests-head">
          <h2>Tests</h2>
          <span class="meta">{{ rows.length }} test{{ rows.length === 1 ? '' : 's' }}</span>
        </header>

        <div v-for="(r, i) in rows" :key="r.key" class="test">
          <div class="order">
            <button
              type="button"
              class="icon"
              :disabled="i === 0"
              :aria-label="`Move ${r.name || 'test'} up`"
              @click="move(i, -1)"
            >
              ↑
            </button>
            <button
              type="button"
              class="icon"
              :disabled="i === rows.length - 1"
              :aria-label="`Move ${r.name || 'test'} down`"
              @click="move(i, 1)"
            >
              ↓
            </button>
          </div>

          <div class="test-body">
            <div class="test-row">
              <label class="field name">
                Test
                <input
                  v-model="r.name"
                  placeholder="e.g. Assay (as FeCl3)"
                  maxlength="128"
                  required
                />
              </label>
              <label class="field rule">
                Rule
                <select v-model="r.rule_type">
                  <option v-for="(v, k) in RULE" :key="k" :value="k">{{ v.label }}</option>
                </select>
              </label>

              <template v-if="NUMERIC.includes(r.rule_type)">
                <label v-if="needsLow(r)" class="field small">
                  {{ r.rule_type === 'range' ? 'From' : 'Minimum' }}
                  <input v-model.number="r.low" type="number" step="any" required />
                </label>
                <label v-if="needsHigh(r)" class="field small">
                  {{ r.rule_type === 'range' ? 'To' : 'Maximum' }}
                  <input v-model.number="r.high" type="number" step="any" required />
                </label>
                <label class="field small">
                  Unit
                  <input v-model="r.unit" placeholder="%, ppm, °C" maxlength="32" />
                </label>
              </template>
              <label v-else-if="r.rule_type === 'text_match'" class="field grow">
                Result should read
                <input
                  v-model="r.expected_text"
                  placeholder="e.g. Clear dark brown liquid"
                  maxlength="255"
                  required
                />
              </label>
              <p v-else class="hint grow complies">{{ RULE.complies.hint }}</p>
            </div>

            <div class="test-row second">
              <label class="field grow">
                Also written as
                <input
                  v-model="r.aliases"
                  placeholder="Other names factories use, separated by commas"
                />
              </label>
              <template v-if="NUMERIC.includes(r.rule_type)">
                <label class="field tol">
                  Factory vs lab may differ by
                  <select v-model="r.tolerance_mode">
                    <option value="default">Default (2% of value)</option>
                    <option value="abs">A fixed amount</option>
                    <option value="pct">A percentage</option>
                  </select>
                </label>
                <label v-if="r.tolerance_mode === 'abs'" class="field small">
                  Amount{{ r.unit ? ` (${r.unit})` : '' }}
                  <input v-model.number="r.tolerance_abs" type="number" min="0" step="any" />
                </label>
                <label v-if="r.tolerance_mode === 'pct'" class="field small">
                  Percent
                  <input v-model.number="r.tolerance_pct" type="number" min="0" step="any" />
                </label>
              </template>
              <label class="crit">
                <input v-model="r.critical" type="checkbox" />
                Critical
                <span class="hint">{{
                  r.critical ? 'A failure holds the batch.' : 'A failure sends it to review.'
                }}</span>
              </label>
            </div>
          </div>

          <button
            type="button"
            class="link-btn remove"
            :disabled="rows.length === 1"
            :aria-label="`Remove ${r.name || 'this test'}`"
            @click="rows.splice(i, 1)"
          >
            Remove
          </button>
        </div>

        <div class="add">
          <button type="button" class="link-btn" @click="rows.push(blank())">+ Add test</button>
        </div>
      </section>

      <section class="card pad">
        <label class="field">
          {{ editing ? 'What changed and why' : 'Notes' }}
          <textarea
            v-model="notes"
            rows="2"
            maxlength="2000"
            :placeholder="
              editing
                ? 'e.g. Customer tightened insolubles to 0.08% from their 2027 sheet.'
                : 'Optional'
            "
          />
          <span v-if="editing" class="hint">Shown in the version history.</span>
        </label>
      </section>

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <div class="actions">
        <button class="primary" type="submit" :disabled="!canSave">
          {{
            saving
              ? 'Saving…'
              : editing
                ? `Save as version ${(current?.version ?? 0) + 1}`
                : 'Create spec'
          }}
        </button>
        <RouterLink :to="backTo" class="cancel">Cancel</RouterLink>
      </div>
    </form>
  </div>
</template>

<style scoped src="./catalog.css"></style>
<style scoped>
.page {
  max-width: 64rem;
}

.form {
  display: grid;
  gap: 1rem;
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
  align-items: start;
}

.tests-head {
  display: flex;
  align-items: baseline;
  gap: 0.75rem;
  padding: 1rem 1.25rem 0.5rem;
}

.tests-head h2 {
  font-size: var(--t-m);
}

.test {
  display: flex;
  gap: 0.75rem;
  align-items: flex-start;
  padding: 0.9rem 1.25rem;
  border-top: 1px solid var(--line);
}

.order {
  display: grid;
  gap: 0.2rem;
  padding-top: 1.4rem;
}

.icon {
  border: 1px solid var(--line);
  background: var(--surface);
  border-radius: var(--radius-s);
  width: 1.6rem;
  height: 1.4rem;
  font-size: var(--t-xs);
  cursor: pointer;
  color: var(--ink-2);
}

.icon:disabled {
  opacity: 0.35;
  cursor: default;
}

.test-body {
  flex: 1;
  display: grid;
  gap: 0.6rem;
  min-width: 0;
}

.test-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
  align-items: flex-end;
}

.name {
  flex: 1 1 14rem;
}

.rule {
  flex: 0 0 11rem;
}

.small {
  flex: 0 0 6.5rem;
}

.tol {
  flex: 0 0 13rem;
}

.grow {
  flex: 1 1 12rem;
}

.complies {
  margin: 0 0 0.6rem;
}

.second .field {
  font-weight: 400;
  color: var(--ink-2);
}

.crit {
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  font-size: var(--t-s);
  padding-bottom: 0.5rem;
}

.crit .hint {
  margin-left: 0.25rem;
}

.remove {
  color: var(--ink-3);
  padding-top: 1.6rem;
}

.remove:disabled {
  visibility: hidden;
}

.add {
  padding: 0.8rem 1.25rem 1rem;
  border-top: 1px solid var(--line);
}

textarea {
  resize: vertical;
}

@media (max-width: 720px) {
  .grid {
    grid-template-columns: 1fr;
  }

  .order {
    display: none;
  }
}

.customer-field {
  display: grid;
  gap: 0.35rem;
  min-width: 0;
  align-content: start;
}

.add-customer {
  justify-self: start;
}
</style>
