<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import { DECISION, formatDate, formatQty, ORDER_STATUS, STATUS } from '@/labels'
import { useAuthStore } from '@/stores/auth'
import type { OrderDetail } from '@/types'

const props = defineProps<{ id: number }>()
const auth = useAuthStore()

const order = ref<OrderDetail | null>(null)
const error = ref<string | null>(null)

/** Load the order. */
async function load() {
  error.value = null
  try {
    order.value = await api.get<OrderDetail>(`/orders/${props.id}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load the order.'
  }
}

onMounted(load)
watch(() => props.id, load)

type Line = OrderDetail['lines'][number]

/** Label and tone for an order line's progress. */
function lineState(line: Line) {
  if (line.ready) return { label: 'Ready to ship', tone: 'release' as const }
  if (line.batches.length === 0) return { label: 'No batch yet', tone: 'idle' as const }
  if (line.batches.some((b) => b.status === 'on_hold'))
    return { label: 'Batch on hold', tone: 'hold' as const }
  return { label: 'In QC', tone: 'review' as const }
}

/** Released share of a line, in percent. */
const pct = (line: Line) =>
  line.quantity ? Math.min(100, (line.released_quantity / line.quantity) * 100) : 0
</script>

<template>
  <div class="page">
    <RouterLink to="/orders" class="back">Orders</RouterLink>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <template v-else-if="order">
      <header class="head">
        <div>
          <div class="title">
            <h1>{{ order.po_number }}</h1>
            <StatusBadge v-bind="ORDER_STATUS[order.status]" />
          </div>
          <p class="sub">
            {{ order.customer.name }} · {{ order.customer.country }} · ordered
            {{ formatDate(order.order_date) }}
          </p>
        </div>
        <RouterLink v-if="auth.can('coa:upload')" to="/batches/new" class="secondary"
          >Register batch</RouterLink
        >
      </header>

      <article v-for="line in order.lines" :key="line.id" class="card line">
        <header class="line-head">
          <div>
            <h2>Line {{ line.line_no }} · {{ line.product }}</h2>
            <p class="meta-row">
              <span class="pill">{{ line.grade }}</span>
              <RouterLink
                v-if="auth.can('specs:view')"
                :to="`/specs/${line.spec_id}`"
                class="spec-link"
              >
                Spec v{{ line.spec_version }}
              </RouterLink>
              <span v-else>Spec v{{ line.spec_version }}</span>
              <span
                v-if="!line.spec_current"
                class="newer"
                title="Batches for this line are still checked against the version agreed on the order."
              >
                A newer version exists; this line keeps v{{ line.spec_version }}
              </span>
            </p>
          </div>
          <div class="progress">
            <StatusBadge v-bind="lineState(line)" />
            <div class="bar"><span :style="{ width: `${pct(line)}%` }" /></div>
            <span class="meta num">
              {{ formatQty(line.released_quantity, line.unit) }} of
              {{ formatQty(line.quantity, line.unit) }} released
            </span>
          </div>
        </header>

        <div class="table-wrap">
          <table style="min-width: 36rem">
            <thead>
              <tr>
                <th scope="col">Batch</th>
                <th scope="col">Factory</th>
                <th scope="col" class="right">Quantity</th>
                <th scope="col">Last check</th>
                <th scope="col">Status</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="line.batches.length === 0">
                <td colspan="5" class="none">
                  No batch for this line yet. When a factory reports one, register it and choose
                  this line.
                </td>
              </tr>
              <tr v-for="b in line.batches" :key="b.id">
                <td>
                  <RouterLink :to="`/batches/${b.id}`" class="strong-link">{{
                    b.batch_number
                  }}</RouterLink>
                </td>
                <td>{{ b.factory ?? '—' }}</td>
                <td class="right num">{{ formatQty(b.quantity, b.unit) }}</td>
                <td>
                  <StatusBadge v-if="b.decision" v-bind="DECISION[b.decision]" />
                  <span v-else class="meta">Not checked yet</span>
                </td>
                <td><StatusBadge v-bind="STATUS[b.status]" /></td>
              </tr>
            </tbody>
          </table>
        </div>
      </article>
    </template>

    <p v-else class="meta">Loading…</p>
  </div>
</template>

<style scoped src="./catalog.css"></style>
<style scoped>
.line {
  overflow: hidden;
}

.line-head {
  display: flex;
  flex-wrap: wrap;
  justify-content: space-between;
  gap: 0.75rem 1.5rem;
  padding: 1rem 1.25rem 0.75rem;
}

.line-head h2 {
  font-size: var(--t-m);
}

.meta-row {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  margin-top: 0.35rem;
  font-size: var(--t-s);
}

.spec-link {
  color: var(--approval);
}

.newer {
  font-size: var(--t-xs);
  color: var(--review);
  font-weight: 600;
}

.progress {
  display: grid;
  gap: 0.35rem;
  justify-items: end;
  min-width: 12rem;
}

.progress .bar {
  width: 100%;
}

.none {
  color: var(--ink-2);
  padding: 1rem 1.25rem;
}

th:first-child,
td:first-child {
  padding-left: 1.25rem;
}
</style>
