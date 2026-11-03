<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'

import { api } from '@/api/client'
import ActionPanel from '@/components/batch/ActionPanel.vue'
import CopilotPanel from '@/components/batch/CopilotPanel.vue'
import BatchTimeline from '@/components/batch/BatchTimeline.vue'
import CoaCard from '@/components/batch/CoaCard.vue'
import LineSuggestions from '@/components/batch/LineSuggestions.vue'
import ParameterTable from '@/components/batch/ParameterTable.vue'
import VerdictPanel from '@/components/batch/VerdictPanel.vue'
import StatusBadge from '@/components/StatusBadge.vue'
import { formatQty, STATUS } from '@/labels'
import { useAuthStore } from '@/stores/auth'
import type { BatchDetail, CatalogOptions, CoaSource } from '@/types'

const props = defineProps<{ id: number }>()
const auth = useAuthStore()

const batch = ref<BatchDetail | null>(null)
const options = ref<CatalogOptions | null>(null)
const error = ref<string | null>(null)

/** Load the batch. */
async function load() {
  error.value = null
  try {
    batch.value = await api.get<BatchDetail>(`/batches/${props.id}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load this batch.'
  }
}

onMounted(async () => {
  await load()
  if (auth.can('coa:upload')) {
    try {
      options.value = await api.get<CatalogOptions>('/catalog/options')
    } catch {
      /* the lab list is only needed for uploads */
    }
  }
})
watch(() => props.id, load)

const closed = computed(
  () => batch.value?.status === 'released' || batch.value?.status === 'rejected',
)
const spec = computed(() => batch.value?.line_detail?.spec ?? null)

/** The current COA from a source. */
function activeCoa(source: CoaSource) {
  return batch.value?.coas.find((c) => c.source === source && !c.superseded)
}

const identity = computed(() => batch.value?.verdict?.details.identity ?? [])
const identityProblems = computed(() => identity.value.filter((c) => c.status !== 'pass'))
const identityLabels = computed(() =>
  [...new Set(identity.value.map((c) => c.label.toLowerCase()))].join(', '),
)
const showIdentity = ref(false)
// Only claim what was actually checked.
const identitySummary = computed(() => {
  const passed = new Set(identity.value.filter((c) => c.status === 'pass').map((c) => c.code))
  const parts = [
    passed.has('product') || passed.has('cas') ? 'Right product' : null,
    passed.has('grade') ? 'right grade' : null,
    passed.has('batch_number') ? 'right batch' : null,
    passed.has('issuer') ? 'from the right issuer' : null,
    passed.has('expiry') ? 'in date' : null,
  ].filter(Boolean)
  return parts.length ? `${parts.join(', ')} on every COA` : 'Identity checks passed'
})
// Copilot: for review and hold batches, for people who handle them.
const showCopilot = computed(
  () =>
    !!batch.value?.verdict &&
    auth.can('check:run') &&
    ['pending_review', 'on_hold'].includes(batch.value.status),
)
const unmatched = computed(() => batch.value?.verdict?.details.unmatched ?? [])

/** Show the batch returned by a child component. */
function onUpdated(detail: BatchDetail) {
  batch.value = detail
}
</script>

<template>
  <div v-if="batch" class="page">
    <RouterLink to="/batches" class="back">Batches</RouterLink>

    <header class="head">
      <div>
        <div class="title">
          <h1>{{ batch.batch_number }}</h1>
          <StatusBadge v-bind="STATUS[batch.status]" />
        </div>
        <p class="meta">
          {{ batch.product.name }} · {{ formatQty(batch.quantity, batch.unit) }} · made by
          {{ batch.factory?.name }} ({{ batch.factory?.city }}, {{ batch.factory?.country }})
        </p>
        <p v-if="batch.line_detail" class="meta">
          For
          <RouterLink :to="`/orders/${batch.line_detail.order_id}`">{{
            batch.line_detail.po_number
          }}</RouterLink
          >, line {{ batch.line_detail.line_no }}:
          <strong>{{ batch.line_detail.grade }}</strong> for {{ batch.line_detail.customer }},
          checked against
          <RouterLink v-if="auth.can('specs:view')" :to="`/specs/${batch.line_detail.spec.id}`">
            spec v{{ batch.line_detail.spec.version }}</RouterLink
          >
          <template v-else>spec v{{ batch.line_detail.spec.version }}</template>
        </p>
      </div>
    </header>

    <div class="layout">
      <div class="main">
        <LineSuggestions v-if="!batch.line" :batch="batch" @updated="onUpdated" />
        <VerdictPanel v-if="batch.line || batch.verdict" :batch="batch" />
        <CopilotPanel v-if="showCopilot" :key="batch.id" :batch="batch" />

        <ParameterTable
          v-if="spec || batch.verdict"
          :checks="batch.verdict?.details.parameters ?? null"
          :spec="spec"
        />

        <section v-if="identity.length" aria-labelledby="identity-title">
          <h2 id="identity-title">Identity and dates</h2>
          <p v-if="!identityProblems.length" class="id-ok">
            {{ identitySummary }}
            <span class="muted">({{ identityLabels }})</span>
          </p>
          <ul v-if="identityProblems.length || showIdentity" class="identity">
            <li
              v-for="(c, i) in showIdentity ? identity : identityProblems"
              :key="i"
              :class="`id-${c.status}`"
            >
              <span class="id-label"
                >{{ c.label
                }}<span v-if="c.source">
                  · {{ c.source === 'lab' ? 'lab COA' : 'factory COA' }}</span
                ></span
              >
              {{ c.message }}
            </li>
          </ul>
          <button type="button" class="link" @click="showIdentity = !showIdentity">
            {{ showIdentity ? 'Hide' : 'Show' }} every identity check
          </button>
        </section>

        <section aria-labelledby="docs-title">
          <h2 id="docs-title">Certificates of analysis</h2>
          <div class="docs">
            <CoaCard
              v-for="s in ['factory', 'lab'] as const"
              :key="s"
              :source="s"
              :coa="activeCoa(s)"
              :spec="spec"
              :batch-id="batch.id"
              :batch-number="batch.batch_number"
              :closed="closed"
              :labs="options?.labs ?? []"
              @updated="onUpdated"
            />
          </div>
          <p v-if="unmatched.length" class="unmatched">
            Also on the COAs, not in the spec:
            <span v-for="(u, i) in unmatched" :key="i"
              >{{ u.name_as_written }} {{ u.raw_value }}{{ u.unit ? ` ${u.unit}` : ''
              }}<template v-if="i < unmatched.length - 1">; </template></span
            >
          </p>
        </section>
      </div>

      <aside class="side">
        <ActionPanel :batch="batch" @updated="onUpdated" />
        <BatchTimeline :batch="batch" />
      </aside>
    </div>
  </div>

  <p v-else-if="error" class="error" role="alert">
    {{ error }} <RouterLink to="/batches">Back to batches</RouterLink>
  </p>
  <p v-else class="loading">Loading…</p>
</template>

<style scoped>
.page {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.25rem;
}

.back {
  font-size: var(--t-s);
  color: var(--ink-2);
  text-decoration: none;
}

.back::before {
  content: '‹ ';
}

.title {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.75rem;
}

h1 {
  font-size: var(--t-2xl);
}

.meta {
  color: var(--ink-2);
  font-size: var(--t-s);
  margin-top: 0.25rem;
}

.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 19rem;
  gap: 1.5rem;
  align-items: start;
}

.main,
.side {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 1.5rem;
}

.side {
  position: sticky;
  top: 1.5rem;
}

h2 {
  font-size: var(--t-l);
  margin-bottom: 0.6rem;
}

.identity {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(15rem, 1fr));
  gap: 0.5rem;
}

.identity li {
  --c: var(--release);
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 3px solid var(--c);
  border-radius: var(--radius-s);
  padding: 0.5rem 0.7rem;
  font-size: var(--t-s);
}

.identity .id-fail {
  --c: var(--hold);
}
.identity .id-warn,
.identity .id-missing {
  --c: var(--review);
}

.id-label {
  display: block;
  font-size: var(--t-xs);
  color: var(--ink-3);
}

.docs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
  align-items: start;
}

.docs :deep(.coa.editing) {
  grid-column: 1 / -1;
  order: -1;
}

.id-ok {
  font-size: var(--t-s);
  padding: 0.6rem 0.8rem;
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 3px solid var(--release);
  border-radius: var(--radius-s);
}

.muted {
  color: var(--ink-3);
}

.link {
  margin-top: 0.5rem;
  border: 0;
  background: none;
  padding: 0;
  color: var(--approval);
  font-size: var(--t-s);
  cursor: pointer;
}

.unmatched {
  margin-top: 0.75rem;
  font-size: var(--t-xs);
  color: var(--ink-2);
}

.error,
.loading {
  color: var(--ink-2);
}

@media (max-width: 1100px) {
  .layout {
    grid-template-columns: minmax(0, 1fr);
  }
  .side {
    position: static;
  }
}

@media (max-width: 760px) {
  .docs {
    grid-template-columns: 1fr;
  }
}
</style>
