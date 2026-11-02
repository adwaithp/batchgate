<script setup lang="ts">
import type { OrderLineSummary, OrderSummary } from '@/types'

defineProps<{ orders: OrderSummary[] }>()

function lineState(line: OrderLineSummary): { label: string; tone: string } {
  if (line.ready) return { label: 'Ready to ship', tone: 'release' }
  if (line.batches === 0) return { label: 'No batch yet', tone: 'idle' }
  if (line.released_quantity > 0)
    return { label: `${qty(line.released_quantity)} of ${qty(line.quantity)} ${line.unit} released`, tone: 'review' }
  return { label: `${line.batches} batch${line.batches === 1 ? '' : 'es'} in QC`, tone: 'review' }
}

function formatDate(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' })
}

function qty(n: number): string {
  return Number.isInteger(n) ? String(n) : n.toFixed(1)
}
</script>

<template>
  <section aria-labelledby="orders-title">
    <h2 id="orders-title">Recent orders</h2>

    <p v-if="orders.length === 0" class="empty">No orders for your customers yet.</p>

    <article v-for="order in orders" :key="order.id" class="order">
      <header>
        <h3>{{ order.po_number }}</h3>
        <span class="customer">{{ order.customer }}</span>
        <span class="date">Ordered {{ formatDate(order.order_date) }}</span>
      </header>

      <table>
        <caption class="visually-hidden">Lines on {{ order.po_number }}</caption>
        <colgroup>
          <col style="width: 4.5rem" />
          <col style="width: 26%" />
          <col style="width: 22%" />
          <col style="width: 7.5rem" />
          <col />
        </colgroup>
        <thead>
          <tr>
            <th scope="col">Line</th>
            <th scope="col">Product</th>
            <th scope="col">Grade</th>
            <th scope="col" class="right">Quantity</th>
            <th scope="col">Status</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="line in order.lines" :key="line.line_no">
            <td class="num">{{ line.line_no }}</td>
            <td>{{ line.product }}</td>
            <td><span class="grade">{{ line.grade }}</span></td>
            <td class="num right">{{ qty(line.quantity) }} {{ line.unit }}</td>
            <td>
              <span :class="['state', `tone-${lineState(line).tone}`]">
                {{ lineState(line).label }}
              </span>
            </td>
          </tr>
        </tbody>
      </table>
    </article>
  </section>
</template>

<style scoped>
h2 {
  font-size: var(--t-l);
  margin-bottom: 0.75rem;
}

.empty {
  color: var(--ink-2);
}

.order {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  margin-bottom: 1rem;
  overflow-x: auto;
}

.order header {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.25rem 1rem;
  padding: 0.9rem 1.1rem 0.6rem;
}

h3 {
  font-size: var(--t-m);
}

.customer {
  font-size: var(--t-s);
}

.date {
  font-size: var(--t-s);
  color: var(--ink-3);
  margin-left: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--t-s);
  min-width: 34rem;
  table-layout: fixed;
}

th {
  text-align: left;
  font-weight: 500;
  color: var(--ink-3);
  padding: 0.4rem 1.1rem;
  border-top: 1px solid var(--line);
}

td {
  padding: 0.6rem 1.1rem;
  border-top: 1px solid var(--line);
}

.right {
  text-align: right;
}

.grade {
  display: inline-block;
  padding: 0.05rem 0.5rem;
  border: 1px solid var(--line);
  border-radius: 999px;
  background: var(--surface-2);
  white-space: nowrap;
}

.state {
  --c: var(--idle);
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  color: var(--ink-2);
  white-space: nowrap;
}

.state::before {
  content: '';
  width: 0.5rem;
  height: 0.5rem;
  border-radius: 50%;
  background: var(--c);
}

.tone-release {
  --c: var(--release);
}
.tone-review {
  --c: var(--review);
}
</style>
