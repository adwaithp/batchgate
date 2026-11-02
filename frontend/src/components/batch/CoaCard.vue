<script setup lang="ts">
import { computed, ref, watch } from 'vue'

import { api } from '@/api/client'
import CoaDataForm from '@/components/batch/CoaDataForm.vue'
import { formatDateTime, SOURCE } from '@/labels'
import { useAuthStore } from '@/stores/auth'
import type { BatchDetail, Coa, CoaSource, Spec, SupplierRef } from '@/types'

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

async function upload(withFile: boolean) {
  error.value = null
  uploading.value = true
  try {
    const data = new FormData()
    data.append('source', props.source)
    if (props.source === 'lab' && labId.value) data.append('issuer_id', String(labId.value))
    if (withFile && file.value) data.append('file', file.value)
    const detail = await api.postMultipart<BatchDetail>(`/batches/${props.batchId}/coas`, data)
    replacing.value = false
    file.value = null
    emit('updated', detail)
    editing.value = true // values next
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Upload failed.'
  } finally {
    uploading.value = false
  }
}

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
        <dd>{{ coa.extraction_model === 'manual' ? 'Typed in by a person' : coa.extraction_model }}</dd>
      </div>
    </dl>
    <p v-else-if="!canEdit" class="muted">Not received yet.</p>

    <div v-if="canEdit && coa && !editing && !replacing" class="row-actions">
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
          {{ uploading ? 'Uploading…' : 'Upload COA' }}
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

.muted {
  font-size: var(--t-xs);
  color: var(--ink-3);
}

.error {
  color: var(--hold);
  font-size: var(--t-s);
}
</style>
