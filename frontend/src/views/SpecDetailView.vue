<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatDate, formatQty, RULE, SPEC_STATUS } from '@/labels'
import type { SpecDetail, SpecParameterFull } from '@/types'

const props = defineProps<{ id: number }>()

const spec = ref<SpecDetail | null>(null)
const error = ref<string | null>(null)

/** Load the spec. */
async function load() {
  error.value = null
  try {
    spec.value = await api.get<SpecDetail>(`/specs/${props.id}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load the spec.'
  }
}

onMounted(load)
watch(() => props.id, load)

/** Allowed factory-vs-lab difference as text. */
function tolerance(p: SpecParameterFull): string {
  if (p.rule_type === 'text_match' || p.rule_type === 'complies') return '—'
  if (p.tolerance_abs !== null) return `± ${p.tolerance_abs}${p.unit ? ` ${p.unit}` : ''}`
  if (p.tolerance_pct !== null) return `± ${p.tolerance_pct}% of value`
  return 'Default (± 2%)'
}
</script>

<template>
  <div class="page">
    <RouterLink to="/specs" class="back">Specs</RouterLink>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <template v-else-if="spec">
      <header class="head">
        <div>
          <div class="title">
            <h1>{{ spec.product.name }} · {{ spec.grade }}</h1>
            <StatusBadge v-bind="SPEC_STATUS[spec.status]" />
          </div>
          <p class="sub">
            Version {{ spec.version }} for {{ spec.customer.name }}
            <template v-if="spec.product.cas_number"> · CAS {{ spec.product.cas_number }}</template>
            <template v-if="spec.created_by"> · set by {{ spec.created_by }}</template>
            · {{ formatDate(spec.effective_from ?? spec.created_at) }}
          </p>
        </div>
        <RouterLink v-if="spec.can_edit" :to="`/specs/${spec.id}/edit`" class="primary"
          >Change spec</RouterLink
        >
      </header>

      <p v-if="spec.current_version_id" class="notice">
        This version has been replaced. Orders placed with it are still checked against it.
        <RouterLink :to="`/specs/${spec.current_version_id}`">See the current version</RouterLink>
      </p>

      <div class="layout">
        <section class="card table-wrap">
          <table style="min-width: 40rem">
            <caption class="visually-hidden">
              Tests in this spec
            </caption>
            <thead>
              <tr>
                <th scope="col">Test</th>
                <th scope="col">Rule</th>
                <th scope="col">Limit</th>
                <th scope="col">Factory vs lab may differ by</th>
                <th scope="col">If it fails</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="p in spec.parameters" :key="p.id">
                <td>
                  <strong>{{ p.name }}</strong>
                  <span v-if="p.aliases.length" class="meta"
                    >Also written as: {{ p.aliases.join(', ') }}</span
                  >
                  <span v-if="p.method" class="meta">Method: {{ p.method }}</span>
                </td>
                <td class="nowrap">{{ RULE[p.rule_type].label }}</td>
                <td class="num limit">{{ p.spec_text }}</td>
                <td class="meta">{{ tolerance(p) }}</td>
                <td>
                  <span :class="p.critical ? 'crit' : 'meta'">{{
                    p.critical ? 'Hold' : 'Review'
                  }}</span>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-if="spec.notes" class="notes"><strong>Notes.</strong> {{ spec.notes }}</p>
        </section>

        <aside class="side">
          <section class="card pad">
            <h2>Order lines using it</h2>
            <p v-if="spec.used_by.length === 0" class="meta">
              No open orders use any version of this spec.
            </p>
            <ul v-else class="list">
              <li v-for="u in spec.used_by" :key="u.line_id">
                <RouterLink :to="`/orders/${u.order_id}`"
                  >{{ u.po_number }}, line {{ u.line_no }}</RouterLink
                >
                <span class="meta"
                  >{{ formatQty(u.quantity, u.unit) }} · v{{ u.spec_version }}</span
                >
              </li>
            </ul>
          </section>

          <section class="card pad">
            <h2>Versions</h2>
            <ol class="list">
              <li v-for="v in spec.versions" :key="v.id" :class="{ here: v.id === spec.id }">
                <RouterLink v-if="v.id !== spec.id" :to="`/specs/${v.id}`"
                  >Version {{ v.version }}</RouterLink
                >
                <strong v-else>Version {{ v.version }}</strong>
                <StatusBadge v-bind="SPEC_STATUS[v.status]" />
                <span class="meta">
                  {{ formatDate(v.effective_from ?? v.created_at)
                  }}<template v-if="v.created_by"> · {{ v.created_by }}</template>
                </span>
                <span v-if="v.notes" class="meta note">{{ v.notes }}</span>
              </li>
            </ol>
          </section>
        </aside>
      </div>
    </template>

    <p v-else class="meta">Loading…</p>
  </div>
</template>

<style scoped src="./catalog.css"></style>
<style scoped>
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 18rem;
  gap: 1.25rem;
  align-items: start;
}

.side {
  display: grid;
  gap: 1rem;
}

.side h2 {
  font-size: var(--t-m);
  margin-bottom: 0.6rem;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.7rem;
  font-size: var(--t-s);
}

.list li {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.2rem 0.5rem;
}

.list .meta {
  flex-basis: 100%;
}

.note {
  font-style: italic;
}

.limit {
  white-space: nowrap;
}

.crit {
  color: var(--hold);
  font-weight: 600;
}

.notes {
  border-top: 1px solid var(--line);
  padding: 0.8rem 1rem;
  font-size: var(--t-s);
  color: var(--ink-2);
  margin: 0;
}

@media (max-width: 900px) {
  .layout {
    grid-template-columns: 1fr;
  }
}
</style>
