<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import GatePipeline from '@/components/GatePipeline.vue'
import OrdersList from '@/components/OrdersList.vue'
import { useAuthStore } from '@/stores/auth'
import type { BatchStatus, Dashboard } from '@/types'

const auth = useAuthStore()
const data = ref<Dashboard | null>(null)
const error = ref<string | null>(null)

/** Load the dashboard. */
async function load() {
  error.value = null
  try {
    data.value = await api.get<Dashboard>('/dashboard')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load the dashboard.'
  }
}

onMounted(load)

const firstName = computed(() => auth.user?.full_name.split(' ')[0] ?? '')

// Which pipeline stage this person acts on.
const focus = computed<BatchStatus | undefined>(() => {
  switch (auth.user?.role) {
    case 'qc_analyst':
      return 'pending_review'
    case 'qc_manager':
      return 'pending_approval'
    default:
      return undefined
  }
})

/** A count with its noun. */
function plural(n: number, one: string, many: string) {
  return `${n} ${n === 1 ? one : many}`
}

// One sentence that tells this person what needs them today.
const headline = computed(() => {
  const d = data.value
  if (!d) return ''
  const s = d.batches_by_status
  switch (auth.user?.role) {
    case 'qc_analyst':
      return s.pending_review
        ? `${plural(s.pending_review, 'batch needs', 'batches need')} your review.`
        : 'Nothing is waiting for your review.'
    case 'qc_manager':
      return s.pending_approval
        ? `${plural(s.pending_approval, 'release is', 'releases are')} waiting for your approval.`
        : 'No releases are waiting for your approval.'
    case 'sales': {
      const lines = d.recent_orders.flatMap((o) => o.lines)
      const ready = lines.filter((l) => l.ready).length
      return `${ready} of ${plural(lines.length, 'order line is', 'order lines are')} ready to ship.`
    }
    default:
      return `${plural(d.open_orders, 'open order', 'open orders')} across all customers.`
  }
})

const showsPipeline = computed(() => auth.can('batches:view'))
</script>

<template>
  <div class="dash">
    <header class="top">
      <p class="hello">Good to see you, {{ firstName }}</p>
      <h1 v-if="data">{{ headline }}</h1>
      <h1 v-else-if="!error" class="loading">Loading…</h1>
    </header>

    <div v-if="error" class="error" role="alert">
      <p>{{ error }}</p>
      <button type="button" @click="load">Try again</button>
    </div>

    <template v-if="data">
      <dl class="facts">
        <div>
          <dt>Open orders</dt>
          <dd class="num">{{ data.open_orders }}</dd>
        </div>
        <div>
          <dt>Order lines</dt>
          <dd class="num">{{ data.order_lines }}</dd>
        </div>
        <div>
          <dt>Active specs</dt>
          <dd class="num">{{ data.active_specs }}</dd>
        </div>
        <div>
          <dt>Customers</dt>
          <dd class="scope">{{ data.scope }}</dd>
        </div>
      </dl>

      <GatePipeline v-if="showsPipeline" :counts="data.batches_by_status" :focus="focus" />

      <OrdersList :orders="data.recent_orders" />
    </template>
  </div>
</template>

<style scoped>
.dash {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.75rem;
}

.hello {
  color: var(--ink-2);
  font-size: var(--t-s);
  margin-bottom: 0.3rem;
}

h1 {
  font-size: var(--t-2xl);
  max-width: 32ch;
}

.loading {
  color: var(--ink-3);
}

.facts {
  margin: 0;
  display: flex;
  flex-wrap: wrap;
  gap: 0.75rem 2.5rem;
}

.facts div {
  display: grid;
}

dt {
  font-size: var(--t-xs);
  color: var(--ink-2);
}

dd {
  margin: 0;
  font-size: var(--t-l);
  font-weight: 600;
}

dd.scope {
  font-size: var(--t-m);
  font-weight: 500;
  padding-top: 0.2rem;
}

.error {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.9rem 1rem;
  background: var(--hold-bg);
  color: var(--hold);
  border-radius: var(--radius-s);
}

.error button {
  border: 1px solid currentColor;
  background: none;
  border-radius: var(--radius-s);
  padding: 0.3rem 0.7rem;
  cursor: pointer;
}
</style>
