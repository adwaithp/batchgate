<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'

import { api } from '@/api/client'
import CoaDataForm from '@/components/batch/CoaDataForm.vue'
import { formatDateTime, SOURCE } from '@/labels'
import { useAuthStore } from '@/stores/auth'
import type { BatchDetail, Coa, CoaEvent, CoaSource, Spec, SupplierRef } from '@/types'

const props = defineProps<{
  source: CoaSource
  coa: Coa | undefined
  spec: Spec | null
  batchId: number
  batchNumber: string
  closed: boolean
  labs: SupplierRef[]
}>()
const emit = defineEmits<{ updated: [BatchDetail] }>()

const auth = useAuthStore()
const canEdit = computed(() => auth.can('coa:upload') && !props.closed)

const editing = ref(false)
const replacing = ref(false)
const uploading = ref(false)
const error = ref<string | null>(null)
const file = ref<File | null>(null)
const labId = ref<number | null>(props.labs[0]?.id ?? null)
watch(
  () => props.labs,
  (labs) => {
    if (labId.value === null && labs.length) labId.value = labs[0]!.id
  },
)

const needsValues = computed(() => props.coa && props.coa.extraction_status !== 'done')
const showUpload = computed(() => canEdit.value && (!props.coa || replacing.value))

const valuesFrom = computed(() => {
  const coa = props.coa
  if (!coa || coa.extraction_model === 'manual') return 'Typed in by a person'
  const read = `Read by Claude (${coa.extraction_model})`
  return coa.checked_by ? `${read}, checked by ${coa.checked_by}` : read
})

// While Claude reads the COA, the server streams progress; `progress` is its latest message.
const progress = ref<string | null>(null)
let following: AbortController | null = null

async function follow(path: string, init: RequestInit = {}): Promise<CoaEvent | null> {
  following?.abort()
  const ctrl = new AbortController()
  following = ctrl
  let last: CoaEvent | null = null
  try {
    await api.stream<CoaEvent>(path, { ...init, signal: ctrl.signal }, (e) => {
      last = e
      if (e.batch) emit('updated', e.batch)
      if (e.message) progress.value = e.message
    })
  } catch (e) {
    if (last === null) throw e // the request itself failed, e.g. a duplicate file
    // Otherwise the stream broke off (or the page closed it); the caller reloads the batch.
  } finally {
    if (following === ctrl) {
      following = null
      progress.value = null
    }
  }
  return last
}

async function reload() {
  emit('updated', await api.get<BatchDetail>(`/batches/${props.batchId}`))
}

async function upload(withFile: boolean) {
  error.value = null
  uploading.value = true
  try {
    const data = new FormData()
    data.append('source', props.source)
    if (props.source === 'lab' && labId.value) data.append('issuer_id', String(labId.value))
    if (withFile && file.value) data.append('file', file.value)
    progress.value = 'Uploading…'
    const last = await follow(`/batches/${props.batchId}/coas`, { method: 'POST', body: data })
    replacing.value = false
    file.value = null
    await reload()
    editing.value = last?.stage !== 'done' // Claude filled the values in, or a person types them
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Upload failed.'
  } finally {
    uploading.value = false
  }
}

// After a page reload (or an upload from the register-batch form), pick the reading up again.
watch(
  () => props.coa?.id,
  async () => {
    const coa = props.coa
    if (!coa || !coa.has_file || coa.extraction_status !== 'pending' || uploading.value) return
    try {
      await follow(`/coas/${coa.id}/events`)
      await reload()
    } catch {
      /* could not reach the server: the card keeps showing the saved state */
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => following?.abort())

async function openFile() {
  if (!props.coa) return
  try {
    await api.openFile(`/coas/${props.coa.id}/file`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not open the file.'
  }
}

function onSaved(detail: BatchDetail) {
  editing.value = false
  emit('updated', detail)
}
</script>

<template>
  <article class="coa" :class="{ empty: !coa, editing }">
    <header>
      <h3>{{ SOURCE[source] }}</h3>
      <span v-if="coa && !needsValues" class="state ok">Values in</span>
      <span v-else-if="progress" class="state wait">Reading…</span>
      <span v-else-if="coa?.extraction_status === 'failed'" class="state wait">Not read automatically</span>
      <span v-else-if="needsValues" class="state wait">Values not entered</span>
      <span v-else class="state none">Not received</span>
    </header>

    <dl v-if="coa" class="facts">
      <div>
        <dt>Issued by</dt>
        <dd>{{ coa.issuer?.name ?? '—' }}</dd>
      </div>
      <div>
        <dt>Received</dt>
        <dd>{{ formatDateTime(coa.uploaded_at) }}<template v-if="coa.uploaded_by">, {{ coa.uploaded_by }}</template></dd>
      </div>
      <div>
        <dt>Document</dt>
        <dd>
          <button v-if="coa.has_file" type="button" class="link" @click="openFile">{{ coa.original_filename }}</button>
          <span v-else>Values typed in, no file</span>
        </dd>
      </div>
      <div v-if="coa.extraction_status === 'done'">
        <dt>Values from</dt>
        <dd>{{ valuesFrom }}</dd>
      </div>
    </dl>
    <p v-if="progress" class="progress" role="status">{{ progress }}</p>
    <p v-else-if="coa?.extraction_status === 'failed'" class="notice" role="status">
      {{ coa.extraction_error }} Enter the values by hand.
    </p>
    <p v-else-if="!canEdit" class="muted">Not received yet.</p>

    <div v-if="canEdit && coa && !editing && !replacing && !progress" class="row-actions">
      <button type="button" :class="needsValues ? 'primary' : 'secondary'" @click="editing = true">
        {{ needsValues ? 'Enter values' : 'Edit values' }}
      </button>
      <button type="button" class="link" @click="replacing = true">Replace with a newer COA</button>
    </div>

    <div v-if="showUpload" class="upload">
      <label v-if="source === 'lab'">
        Lab
        <select v-model="labId">
          <option v-for="l in labs" :key="l.id" :value="l.id">{{ l.name }}</option>
        </select>
      </label>
      <label>
        COA file
        <input type="file" accept="application/pdf,image/png,image/jpeg" @change="file = ($event.target as HTMLInputElement).files?.[0] ?? null" />
      </label>
      <div class="row-actions">
        <button type="button" class="primary" :disabled="!file || uploading" @click="upload(true)">
          {{ uploading ? 'Uploading…' : 'Upload and read COA' }}
        </button>
        <button type="button" class="link" :disabled="uploading" @click="upload(false)">
          No file? Type the values in instead
        </button>
        <button v-if="replacing" type="button" class="link" @click="replacing = false">Cancel</button>
      </div>
      <p v-if="replacing" class="muted">The current {{ SOURCE[source] }} is kept on record but stops counting.</p>
    </div>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <CoaDataForm
      v-if="editing && coa"
      :key="coa.id"
      :coa="coa"
      :spec="spec"
      :batch-number="batchNumber"
      @saved="onSaved"
      @cancel="editing = false"
    />
  </article>
</template>

<style scoped>
.coa {
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  padding: 1rem 1.1rem;
  display: grid;
  gap: 0.85rem;
  align-content: start;
}

.coa.empty {
  border-style: dashed;
  background: var(--surface-2);
}

header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  gap: 1rem;
}

h3 {
  font-size: var(--t-m);
}

.state {
  font-size: var(--t-xs);
  font-weight: 600;
}
.state.ok {
  color: var(--release);
}
.state.wait {
  color: var(--review);
}
.state.none {
  color: var(--ink-3);
}

.facts {
  margin: 0;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(11rem, 1fr));
  gap: 0.6rem 1rem;
}

dt {
  font-size: var(--t-xs);
  color: var(--ink-3);
}

dd {
  margin: 0;
  font-size: var(--t-s);
  overflow-wrap: anywhere;
}

.upload {
  display: grid;
  gap: 0.7rem;
}

label {
  display: grid;
  gap: 0.25rem;
  font-size: var(--t-xs);
  color: var(--ink-2);
}

select,
input[type='file'] {
  font: inherit;
  font-size: var(--t-s);
  padding: 0.4rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface);
}

.row-actions {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem 1rem;
}

.primary,
.secondary {
  padding: 0.5rem 0.9rem;
  border-radius: var(--radius-s);
  font-weight: 600;
  font-size: var(--t-s);
  cursor: pointer;
}

.primary {
  border: 0;
  background: var(--brand);
  color: var(--brand-ink);
}

.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.secondary {
  border: 1px solid var(--line);
  background: var(--surface);
}

.link {
  border: 0;
  background: none;
  padding: 0;
  color: var(--approval);
  font-size: var(--t-s);
  cursor: pointer;
  text-align: left;
}

.progress,
.notice {
  font-size: var(--t-s);
  padding: 0.55rem 0.75rem;
  border-radius: var(--radius-s);
}

.progress {
  background: var(--approval-bg);
  color: var(--approval);
}

.progress::before {
  content: '';
  display: inline-block;
  width: 0.5rem;
  height: 0.5rem;
  margin-right: 0.5rem;
  border-radius: 50%;
  background: currentColor;
  animation: pulse 1.2s ease-in-out infinite;
}

@keyframes pulse {
  50% {
    opacity: 0.25;
  }
}

@media (prefers-reduced-motion: reduce) {
  .progress::before {
    animation: none;
  }
}

.notice {
  background: var(--review-bg);
  color: var(--ink);
}

.muted {
  font-size: var(--t-xs);
  color: var(--ink-3);
}

.error {
  color: var(--hold);
  font-size: var(--t-s);
}
</style>
