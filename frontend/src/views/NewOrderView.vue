<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '@/api/client'
import NewCustomerForm from '@/components/NewCustomerForm.vue'
import { useAuthStore } from '@/stores/auth'
import type { CustomerRef, CustomerSpecs, OrderDetail, ReferenceData } from '@/types'

const router = useRouter()
const auth = useAuthStore()
const addingCustomer = ref(false)

const reference = ref<ReferenceData | null>(null)
const specs = ref<CustomerSpecs['specs']>([])
const error = ref<string | null>(null)
const saving = ref(false)

interface LineRow {
  spec_id: number | null
  quantity: number | null
  unit: string
}

const now = new Date()
const today = new Date(now.getTime() - now.getTimezoneOffset() * 60_000).toISOString().slice(0, 10)
const form = ref({
  po_number: '',
  customer_id: null as number | null,
  order_date: today,
})
const lines = ref<LineRow[]>([{ spec_id: null, quantity: null, unit: 't' }])

onMounted(async () => {
  try {
    reference.value = await api.get<ReferenceData>('/reference')
    if (reference.value.customers.length === 1)
      form.value.customer_id = reference.value.customers[0]!.id
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load the form.'
  }
})

watch(
  () => form.value.customer_id,
  async (id) => {
    specs.value = []
    lines.value = [{ spec_id: null, quantity: null, unit: 't' }]
    if (!id) return
    try {
      specs.value = (await api.get<CustomerSpecs>(`/customers/${id}/specs`)).specs
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Could not load this customer’s specs.'
    }
  },
)

const customerName = computed(
  () => reference.value?.customers.find((c) => c.id === form.value.customer_id)?.name,
)

const canSave = computed(
  () =>
    !saving.value &&
    form.value.po_number.trim() &&
    form.value.customer_id &&
    form.value.order_date &&
    lines.value.length > 0 &&
    lines.value.every((l) => l.spec_id && l.quantity && l.quantity > 0),
)

/** Add the new customer to the list and select it. */
function customerAdded(customer: CustomerRef) {
  const list = reference.value!.customers
  list.push(customer)
  list.sort((a, b) => a.name.localeCompare(b.name))
  form.value.customer_id = customer.id
  addingCustomer.value = false
}

/** Add an empty order line. */
function addLine() {
  lines.value.push({ spec_id: null, quantity: null, unit: 't' })
}

/** Remove an order line. */
function removeLine(i: number) {
  lines.value.splice(i, 1)
}

/** Create the order, then open it. */
async function save() {
  error.value = null
  saving.value = true
  try {
    const order = await api.post<OrderDetail>('/orders', {
      ...form.value,
      po_number: form.value.po_number.trim(),
      lines: lines.value.map((l) => ({
        spec_id: l.spec_id,
        quantity: l.quantity,
        unit: l.unit || 't',
      })),
    })
    await router.push(`/orders/${order.id}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not save the order.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page narrow">
    <RouterLink to="/orders" class="back">Orders</RouterLink>
    <div>
      <h1>New order</h1>
      <p class="sub">
        Enter the customer’s purchase order. Each line uses the spec currently agreed with that
        customer for the product and grade; later spec changes don’t change this order.
      </p>
    </div>

    <form v-if="reference" class="card pad form" @submit.prevent="save">
      <div class="grid">
        <div class="customer-field">
          <label class="field">
            Customer
            <select v-model="form.customer_id" required>
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
          Customer PO number
          <input v-model="form.po_number" placeholder="e.g. PO-1077" required />
        </label>
        <label class="field">
          Order date
          <input v-model="form.order_date" type="date" required />
        </label>
      </div>

      <NewCustomerForm
        v-if="addingCustomer"
        @added="customerAdded"
        @cancel="addingCustomer = false"
      />

      <fieldset>
        <legend>Lines</legend>

        <p v-if="form.customer_id && specs.length === 0" class="notice">
          {{ customerName }} has no specs yet. Each order line is checked against the customer’s
          spec, so the spec comes first.
          <RouterLink v-if="auth.can('specs:edit')" :to="`/specs/new?customer=${form.customer_id}`">
            Create their spec
          </RouterLink>
          <template v-else>Ask a QC manager to add it, then come back to enter the order.</template>
        </p>

        <div v-for="(line, i) in lines" :key="i" class="line-row">
          <span class="line-no num">{{ i + 1 }}</span>
          <label class="field grow">
            <span class="visually-hidden">Product and grade for line {{ i + 1 }}</span>
            <select
              v-model="line.spec_id"
              :disabled="!form.customer_id || specs.length === 0"
              required
            >
              <option :value="null" disabled>
                {{ form.customer_id ? 'Choose product and grade' : 'Choose a customer first' }}
              </option>
              <option v-for="s in specs" :key="s.id" :value="s.id">
                {{ s.product }} · {{ s.grade }} (spec v{{ s.version }})
              </option>
            </select>
          </label>
          <label class="field qty">
            <span class="visually-hidden">Quantity for line {{ i + 1 }}</span>
            <input
              v-model.number="line.quantity"
              type="number"
              min="0"
              step="0.1"
              placeholder="Quantity"
              required
            />
          </label>
          <label class="field unit">
            <span class="visually-hidden">Unit for line {{ i + 1 }}</span>
            <select v-model="line.unit">
              <option value="t">t</option>
              <option value="kg">kg</option>
            </select>
          </label>
          <button
            type="button"
            class="link-btn remove"
            :disabled="lines.length === 1"
            :aria-label="`Remove line ${i + 1}`"
            @click="removeLine(i)"
          >
            Remove
          </button>
        </div>

        <button
          type="button"
          class="link-btn"
          :disabled="!form.customer_id || specs.length === 0"
          @click="addLine"
        >
          + Add line
        </button>
        <p class="hint">
          The same product can appear on two lines at different grades, for example MEA Triazine at
          78% and at 40%. Each is checked against its own spec.
        </p>
      </fieldset>

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <div class="actions">
        <button class="primary" type="submit" :disabled="!canSave">
          {{ saving ? 'Saving…' : 'Create order' }}
        </button>
        <RouterLink to="/orders" class="cancel">Cancel</RouterLink>
      </div>
    </form>
    <p v-else-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped src="./catalog.css"></style>
<style scoped>
.narrow {
  max-width: 50rem;
  gap: 0.9rem;
}

.form {
  display: grid;
  gap: 1.4rem;
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
  align-items: start;
}

.customer-field {
  display: grid;
  gap: 0.35rem;
  min-width: 0;
}

.add-customer {
  justify-self: start;
}

fieldset {
  border: 0;
  padding: 0;
  margin: 0;
  display: grid;
  gap: 0.6rem;
  justify-items: start;
}

legend {
  font-weight: 600;
  font-size: var(--t-m);
  margin-bottom: 0.4rem;
}

.line-row {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  width: 100%;
}

.line-no {
  width: 1.5rem;
  color: var(--ink-3);
  font-size: var(--t-s);
}

.grow {
  flex: 1;
}

.qty {
  width: 8rem;
}

.unit {
  width: 4.5rem;
}

.remove {
  color: var(--ink-3);
  flex: none;
}

.remove:disabled {
  visibility: hidden;
}

@media (max-width: 640px) {
  .grid {
    grid-template-columns: 1fr;
  }

  .line-row {
    flex-wrap: wrap;
  }

  .grow {
    flex-basis: calc(100% - 2.1rem);
  }
}
</style>
