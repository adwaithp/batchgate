<script setup lang="ts">
import { ref } from 'vue'

import { api } from '@/api/client'
import StatusBadge from '@/components/StatusBadge.vue'
import { DECISION } from '@/labels'
import { useAuthStore } from '@/stores/auth'
import type { BatchDetail } from '@/types'

const props = defineProps<{ batch: BatchDetail }>()
const emit = defineEmits<{ updated: [BatchDetail] }>()

const auth = useAuthStore()
const busy = ref<number | null>(null)
const error = ref<string | null>(null)

async function assign(lineId: number) {
  busy.value = lineId
  error.value = null
  try {
    emit(
      'updated',
      await api.post<BatchDetail>(`/batches/${props.batch.id}/actions`, {
        action: 'assign_line',
        line_id: lineId,
      }),
    )
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not assign the line.'
  } finally {
    busy.value = null
  }
}
</script>

<template>
  <section class="suggest" aria-labelledby="suggest-title">
    <h2 id="suggest-title">Which order line is this batch for?</h2>
    <p class="lead">
      This batch arrived without an order line. Here is how it measures up against the spec of each
      open line for {{ batch.product.name }}. Confirm the right one. BatchGate won’t pick for you,
      because shipping the wrong grade is worse than waiting.
    </p>

    <p v-if="!batch.suggestions.length" class="muted">
      No suggestions yet. Enter the COA values first, or there is no open line for this product.
    </p>

    <ol v-else class="list">
      <li v-for="(s, i) in batch.suggestions" :key="s.line.id" :class="{ best: i === 0 && s.decision === 'release' }">
        <div class="what">
          <strong>{{ s.line.po_number }}, line {{ s.line.line_no }}: {{ s.line.grade }}</strong>
          <span class="meta">{{ s.line.customer }} · {{ s.line.quantity }} {{ s.line.unit }}</span>
          <span v-if="s.failing.length" class="fails">Out of spec: {{ s.failing.join(', ') }}</span>
          <span v-else-if="s.decision === 'release'" class="fits">Fits every parameter of this spec.</span>
          <span v-else class="meta">{{ s.summary }}</span>
        </div>
        <StatusBadge v-bind="DECISION[s.decision]" />
        <button
          v-if="auth.can('check:run')"
          type="button"
          :class="i === 0 && s.decision === 'release' ? 'primary' : 'secondary'"
          :disabled="busy !== null"
          @click="assign(s.line.id)"
        >
          {{ busy === s.line.id ? 'Assigning…' : 'Assign to this line' }}
        </button>
      </li>
    </ol>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
  </section>
</template>

<style scoped>
.suggest {
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 5px solid var(--review);
  border-radius: var(--radius-m);
  padding: 1.1rem 1.25rem;
  display: grid;
  gap: 0.75rem;
}

h2 {
  font-size: var(--t-l);
}

.lead {
  font-size: var(--t-s);
  color: var(--ink-2);
  max-width: 68ch;
}

.list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}

li {
  display: grid;
  grid-template-columns: 1fr auto auto;
  align-items: center;
  gap: 0.5rem 1rem;
  padding: 0.75rem 0.85rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
}

li.best {
  border-color: var(--release);
  background: var(--release-bg);
}

.what {
  display: grid;
  gap: 0.1rem;
  font-size: var(--t-s);
}

.meta {
  font-size: var(--t-xs);
  color: var(--ink-2);
}

.fails {
  font-size: var(--t-xs);
  color: var(--hold);
  font-weight: 600;
}

.fits {
  font-size: var(--t-xs);
  color: var(--release);
  font-weight: 600;
}

.primary,
.secondary {
  padding: 0.45rem 0.8rem;
  border-radius: var(--radius-s);
  font-weight: 600;
  font-size: var(--t-s);
  cursor: pointer;
  white-space: nowrap;
}

.primary {
  border: 0;
  background: var(--brand);
  color: var(--brand-ink);
}

.secondary {
  border: 1px solid var(--line);
  background: var(--surface);
}

.muted {
  font-size: var(--t-s);
  color: var(--ink-2);
}

.error {
  color: var(--hold);
  font-size: var(--t-s);
}

@media (max-width: 640px) {
  li {
    grid-template-columns: 1fr;
  }
}
</style>
