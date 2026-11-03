<script setup lang="ts">
import { computed, ref } from 'vue'

import { api } from '@/api/client'
import { ACTION } from '@/labels'
import type { BatchActionType, BatchDetail, CatalogOptions, LineOption } from '@/types'

const props = defineProps<{ batch: BatchDetail }>()
const emit = defineEmits<{ updated: [BatchDetail] }>()

type Decidable = 'approve_release' | 'propose_release' | 'hold' | 'reject'

// What each decision means, said plainly at the moment someone takes it.
const GUIDE: Record<Decidable, { hint: string; noteRequired: boolean; tone: string }> = {
  approve_release: {
    hint: 'The batch is cleared to ship. This is the second pair of eyes on the release.',
    noteRequired: false,
    tone: 'release',
  },
  propose_release: {
    hint: 'You are overriding the check. Say why, for example a retest result or a concession the customer agreed to. A QC manager then approves.',
    noteRequired: true,
    tone: 'approval',
  },
  hold: {
    hint: 'The batch stays in the warehouse until someone proposes release again.',
    noteRequired: true,
    tone: 'hold',
  },
  reject: {
    hint: 'Closes the batch for good. It cannot be released afterwards.',
    noteRequired: true,
    tone: 'hold',
  },
}

const order: Decidable[] = ['approve_release', 'propose_release', 'hold', 'reject']
const available = computed(() => order.filter((a) => props.batch.allowed_actions.includes(a)))
const canRecheck = computed(
  () =>
    props.batch.allowed_actions.includes('rerun_check') &&
    !!props.batch.line &&
    props.batch.coas.some((c) => !c.superseded && c.extraction_status === 'done'),
)

const chosen = ref<Decidable | null>(null)
const note = ref('')
const busy = ref(false)
const error = ref<string | null>(null)

/** Select or deselect a decision. */
function choose(a: Decidable) {
  chosen.value = chosen.value === a ? null : a
  note.value = ''
  error.value = null
}

/** Apply the chosen decision or tool. */
async function submit(action: BatchActionType, withNote = true, lineId: number | null = null) {
  busy.value = true
  error.value = null
  try {
    const detail = await api.post<BatchDetail>(`/batches/${props.batch.id}/actions`, {
      action,
      note: withNote ? note.value.trim() || null : null,
      line_id: lineId,
    })
    chosen.value = null
    tool.value = null
    note.value = ''
    emit('updated', detail)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'That did not work.'
  } finally {
    busy.value = false
  }
}

const closedText = computed(() => {
  if (props.batch.status === 'released') return 'Released. This batch is cleared to ship.'
  if (props.batch.status === 'rejected') return 'Rejected. This batch is closed.'
  if (props.batch.status === 'cancelled')
    return 'Cancelled. It was entered by mistake and is kept for the record.'
  return null
})

// Housekeeping actions, separate from the quality decisions.
const tool = ref<'line' | 'cancel' | null>(null)
const lines = ref<LineOption[] | null>(null)
const newLine = ref<number | null>(null)
const canMove = computed(
  () => props.batch.allowed_actions.includes('assign_line') && !!props.batch.line,
)
const canCancel = computed(() => props.batch.allowed_actions.includes('cancel'))

/** Open the change-line or cancel tool. */
async function openTool(t: 'line' | 'cancel') {
  tool.value = tool.value === t ? null : t
  chosen.value = null
  note.value = ''
  error.value = null
  if (t === 'line' && lines.value === null) {
    try {
      const opts = await api.get<CatalogOptions>('/catalog/options')
      lines.value = opts.open_lines.filter(
        (l) => l.product_id === props.batch.product.id && l.id !== props.batch.line?.id,
      )
      newLine.value = lines.value.length === 1 ? lines.value[0]!.id : null
    } catch (e) {
      error.value = e instanceof Error ? e.message : 'Could not load order lines.'
    }
  }
}
</script>

<template>
  <section class="panel" aria-labelledby="decide-title">
    <h2 id="decide-title">Decision</h2>

    <p v-if="closedText" class="closed">{{ closedText }}</p>
    <p v-else-if="!available.length" class="muted">
      Nothing for you to decide on this batch right now.
    </p>

    <div v-else class="choices">
      <template v-for="a in available" :key="a">
        <button
          type="button"
          :class="['choice', `tone-${GUIDE[a].tone}`, { on: chosen === a }]"
          :aria-expanded="chosen === a"
          @click="choose(a)"
        >
          {{ ACTION[a].label }}
        </button>
        <div v-if="chosen === a" class="confirm">
          <p class="hint">{{ GUIDE[a].hint }}</p>
          <label>
            <span>Note{{ GUIDE[a].noteRequired ? '' : ' (optional)' }}</span>
            <textarea v-model="note" rows="3" :required="GUIDE[a].noteRequired" />
          </label>
          <button
            type="button"
            :class="['go', `tone-${GUIDE[a].tone}`]"
            :disabled="busy || (GUIDE[a].noteRequired && !note.trim())"
            @click="submit(a)"
          >
            {{ busy ? 'Saving…' : ACTION[a].label }}
          </button>
        </div>
      </template>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <button
      v-if="canRecheck"
      type="button"
      class="recheck"
      :disabled="busy"
      @click="submit('rerun_check', false)"
    >
      Run check again
    </button>

    <div v-if="canMove || canCancel" class="tools">
      <button
        v-if="canMove"
        type="button"
        class="recheck"
        :aria-expanded="tool === 'line'"
        @click="openTool('line')"
      >
        Change order line
      </button>
      <div v-if="tool === 'line'" class="confirm">
        <p class="hint">
          Moves the batch to another order line for the same product and checks it again against
          that line’s spec.
        </p>
        <p v-if="lines && !lines.length" class="hint">
          There is no other open order line for this product.
        </p>
        <label v-else-if="lines">
          <span>Order line</span>
          <select v-model="newLine">
            <option :value="null" disabled>Choose an order line</option>
            <option v-for="l in lines" :key="l.id" :value="l.id">
              {{ l.label }} · {{ l.customer }} · {{ l.quantity }} {{ l.unit }}
            </option>
          </select>
        </label>
        <label v-if="lines?.length">
          <span>Note (optional)</span>
          <textarea v-model="note" rows="2" />
        </label>
        <button
          v-if="lines?.length"
          type="button"
          class="go tone-approval"
          :disabled="busy || !newLine"
          @click="submit('assign_line', true, newLine)"
        >
          {{ busy ? 'Moving…' : 'Move and check again' }}
        </button>
      </div>

      <button
        v-if="canCancel"
        type="button"
        class="recheck subtle"
        :aria-expanded="tool === 'cancel'"
        @click="openTool('cancel')"
      >
        Cancel batch
      </button>
      <div v-if="tool === 'cancel'" class="confirm">
        <p class="hint">
          For a batch entered by mistake, such as a duplicate. It leaves the workflow but stays in
          the history. If the material itself is bad, reject it instead.
        </p>
        <label>
          <span>Why is it being cancelled?</span>
          <textarea v-model="note" rows="2" required />
        </label>
        <button
          type="button"
          class="go tone-hold"
          :disabled="busy || !note.trim()"
          @click="submit('cancel')"
        >
          {{ busy ? 'Cancelling…' : 'Cancel batch' }}
        </button>
      </div>
    </div>
  </section>
</template>

<style scoped>
.panel {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  padding: 1rem 1.1rem;
  display: grid;
  gap: 0.75rem;
}

h2 {
  font-size: var(--t-l);
}

.choices {
  display: grid;
  gap: 0.5rem;
}

.choice {
  --c: var(--brand);
  text-align: left;
  padding: 0.6rem 0.8rem;
  border: 1px solid var(--line);
  border-left: 4px solid var(--c);
  border-radius: var(--radius-s);
  background: var(--surface);
  font-weight: 600;
  font-size: var(--t-s);
  cursor: pointer;
}

.choice.on {
  background: var(--surface-2);
}

.tone-release {
  --c: var(--release);
}
.tone-approval {
  --c: var(--approval);
}
.tone-hold {
  --c: var(--hold);
}

.confirm {
  display: grid;
  gap: 0.6rem;
  padding: 0.25rem 0 0.5rem 0.5rem;
}

.hint {
  font-size: var(--t-xs);
  color: var(--ink-2);
}

label {
  display: grid;
  gap: 0.25rem;
  font-size: var(--t-xs);
  color: var(--ink-2);
}

textarea {
  font: inherit;
  font-size: var(--t-s);
  color: var(--ink);
  padding: 0.5rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  resize: vertical;
}

.go {
  justify-self: start;
  padding: 0.5rem 0.9rem;
  border: 0;
  border-radius: var(--radius-s);
  background: var(--c);
  color: #fff;
  font-weight: 600;
  font-size: var(--t-s);
  cursor: pointer;
}

.go:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

.recheck {
  justify-self: start;
  border: 0;
  background: none;
  padding: 0;
  color: var(--approval);
  font-size: var(--t-s);
  cursor: pointer;
}

.closed {
  font-weight: 600;
}

.tools {
  display: grid;
  gap: 0.4rem;
  padding-top: 0.6rem;
  border-top: 1px solid var(--line);
}

.subtle {
  color: var(--ink-2);
}

select {
  font: inherit;
  font-size: var(--t-s);
  padding: 0.45rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface);
  color: var(--ink);
}

.muted {
  color: var(--ink-2);
  font-size: var(--t-s);
}

.error {
  color: var(--hold);
  font-size: var(--t-s);
}
</style>
