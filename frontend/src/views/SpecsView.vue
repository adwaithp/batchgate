<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatDate, SPEC_STATUS } from '@/labels'
import { useAuthStore } from '@/stores/auth'
import type { SpecSummary } from '@/types'

const auth = useAuthStore()
const router = useRouter()

const specs = ref<SpecSummary[]>([])
const loading = ref(true)
const error = ref<string | null>(null)
const customer = ref<number | 'all'>('all')
const includeOld = ref(false)

const customers = computed(() => {
  const seen = new Map<number, string>()
  specs.value.forEach((s) => seen.set(s.customer.id, s.customer.name))
  return [...seen].map(([id, name]) => ({ id, name }))
})

const groups = computed(() => {
  const rows = specs.value.filter(
    (s) => customer.value === 'all' || s.customer.id === customer.value,
  )
  const byCustomer = new Map<string, SpecSummary[]>()
  rows.forEach((s) =>
    byCustomer.set(s.customer.name, [...(byCustomer.get(s.customer.name) ?? []), s]),
  )
  return [...byCustomer].map(([name, items]) => ({ name, items }))
})

/** Load the specs. */
async function load() {
  loading.value = true
  error.value = null
  try {
    specs.value = await api.get<SpecSummary[]>(
      `/specs${includeOld.value ? '?include_old=true' : ''}`,
    )
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load specs.'
  } finally {
    loading.value = false
  }
}

onMounted(load)
watch(includeOld, load)
</script>

<template>
  <div class="page">
    <header class="head">
      <div>
        <h1>Specs</h1>
        <p class="sub">
          The limits a customer has agreed for one product at one grade. BatchGate checks every COA
          against these. Changing a spec makes a new version; orders already placed keep theirs.
        </p>
      </div>
      <RouterLink v-if="auth.can('specs:edit')" to="/specs/new" class="primary"
        >New spec</RouterLink
      >
    </header>

    <div class="filters">
      <select v-model="customer" aria-label="Customer">
        <option value="all">All customers</option>
        <option v-for="c in customers" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
      <label class="check">
        <input v-model="includeOld" type="checkbox" />
        Show replaced versions
      </label>
    </div>

    <p v-if="error" class="error" role="alert">
      {{ error }} <button type="button" class="link-btn" @click="load">Try again</button>
    </p>
    <p v-else-if="loading" class="meta">Loading…</p>
    <p v-else-if="groups.length === 0" class="card empty">No specs yet.</p>

    <section v-for="g in groups" :key="g.name" class="card table-wrap">
      <h2 class="group">{{ g.name }}</h2>
      <table style="min-width: 44rem">
        <thead>
          <tr>
            <th scope="col">Product</th>
            <th scope="col">Grade</th>
            <th scope="col">Version</th>
            <th scope="col" class="right">Tests</th>
            <th scope="col" class="right">Open order lines</th>
            <th scope="col" class="right">Since</th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="s in g.items"
            :key="s.id"
            class="row"
            :class="{ old: s.status !== 'active' }"
            tabindex="0"
            @click="router.push(`/specs/${s.id}`)"
            @keydown.enter="router.push(`/specs/${s.id}`)"
          >
            <td>
              <RouterLink :to="`/specs/${s.id}`" class="strong-link" @click.stop>{{
                s.product.name
              }}</RouterLink>
              <span v-if="s.product.cas_number" class="meta">CAS {{ s.product.cas_number }}</span>
            </td>
            <td>
              <span class="pill">{{ s.grade }}</span>
            </td>
            <td class="nowrap">
              v{{ s.version }}
              <StatusBadge v-if="includeOld" v-bind="SPEC_STATUS[s.status]" />
            </td>
            <td class="right num">
              {{ s.tests }}
              <span class="meta">{{ s.critical_tests }} critical</span>
            </td>
            <td class="right num">{{ s.open_lines || '—' }}</td>
            <td class="right meta nowrap">{{ formatDate(s.effective_from ?? s.created_at) }}</td>
          </tr>
        </tbody>
      </table>
    </section>
  </div>
</template>

<style scoped src="./catalog.css"></style>
<style scoped>
.check {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  font-size: var(--t-s);
  color: var(--ink-2);
}

.group {
  font-size: var(--t-m);
  padding: 0.9rem 1rem 0.2rem;
}

.old td {
  color: var(--ink-3);
}
</style>
