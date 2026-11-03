<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatDate, ORDER_STATUS } from '@/labels'
import { useAuthStore } from '@/stores/auth'
import type { OrderListItem } from '@/types'

const auth = useAuthStore()
const router = useRouter()

const orders = ref<OrderListItem[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const search = ref('')

const rows = computed(() => {
  const term = search.value.trim().toLowerCase()
  if (!term) return orders.value
  return orders.value.filter((o) =>
    [o.po_number, o.customer.name].some((v) => v.toLowerCase().includes(term)),
  )
})

/** Released share of an order, in percent. */
const pct = (o: OrderListItem) =>
  o.quantity ? Math.min(100, (o.released_quantity / o.quantity) * 100) : 0
/** Format a quantity. */
const qty = (n: number) => (Number.isInteger(n) ? String(n) : n.toFixed(1))

/** Load the orders. */
async function load() {
  loading.value = true
  error.value = null
  try {
    orders.value = await api.get<OrderListItem[]>('/orders')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load orders.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

<template>
  <div class="page">
    <header class="head">
      <div>
        <h1>Orders</h1>
        <p class="sub">
          A customer’s purchase order. Each line is one product at one grade, and every batch for
          that line is checked against the spec agreed for it.
        </p>
      </div>
      <RouterLink v-if="auth.can('orders:edit')" to="/orders/new" class="primary"
        >New order</RouterLink
      >
    </header>

    <div class="filters">
      <input
        v-model="search"
        type="search"
        placeholder="Search PO or customer"
        aria-label="Search orders"
      />
    </div>

    <p v-if="error" class="error" role="alert">
      {{ error }} <button type="button" class="link-btn" @click="load">Try again</button>
    </p>

    <div v-else class="card table-wrap">
      <table style="min-width: 48rem">
        <thead>
          <tr>
            <th scope="col">PO</th>
            <th scope="col">Customer</th>
            <th scope="col" class="right">Lines</th>
            <th scope="col">Released</th>
            <th scope="col">In QC</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-if="loading">
            <td colspan="6" class="empty">Loading…</td>
          </tr>
          <tr v-else-if="rows.length === 0">
            <td colspan="6" class="empty">
              {{ search ? 'No orders match your search.' : 'No orders yet.' }}
            </td>
          </tr>
          <tr
            v-for="o in rows"
            v-else
            :key="o.id"
            class="row"
            tabindex="0"
            @click="router.push(`/orders/${o.id}`)"
            @keydown.enter="router.push(`/orders/${o.id}`)"
          >
            <td>
              <RouterLink :to="`/orders/${o.id}`" class="strong-link" @click.stop>{{
                o.po_number
              }}</RouterLink>
              <span class="meta">Ordered {{ formatDate(o.order_date) }}</span>
            </td>
            <td>
              {{ o.customer.name }}
              <span class="meta">{{ o.customer.industry }} · {{ o.customer.country }}</span>
            </td>
            <td class="right num">{{ o.lines }}</td>
            <td>
              <div
                class="bar"
                role="img"
                :aria-label="`${qty(o.released_quantity)} of ${qty(o.quantity)} t released`"
              >
                <span :style="{ width: `${pct(o)}%` }" />
              </div>
              <span class="meta num"
                >{{ qty(o.released_quantity) }} of {{ qty(o.quantity) }} t</span
              >
            </td>
            <td>
              <span class="num"
                >{{ o.batches_in_qc }} batch{{ o.batches_in_qc === 1 ? '' : 'es' }}</span
              >
              <span v-if="o.on_hold" class="meta held">{{ o.on_hold }} on hold</span>
            </td>
            <td><StatusBadge v-bind="ORDER_STATUS[o.status]" /></td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped src="./catalog.css"></style>
<style scoped>
.filters input {
  width: min(22rem, 100%);
}

.held {
  color: var(--hold);
  font-weight: 600;
}
</style>
