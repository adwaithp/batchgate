<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

import { api } from '@/api/client'
import type { BatchDetail, CatalogOptions } from '@/types'

const router = useRouter()
const options = ref<CatalogOptions | null>(null)
const error = ref<string | null>(null)
const saving = ref(false)

const form = ref({
  batch_number: '',
  product_id: null as number | null,
  factory_id: null as number | null,
  line_id: null as number | null,
  quantity: null as number | null,
})
const file = ref<File | null>(null)

onMounted(async () => {
  try {
    options.value = await api.get<CatalogOptions>('/catalog/options')
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load the form.'
  }
})

const lines = computed(
  () => options.value?.open_lines.filter((l) => l.product_id === form.value.product_id) ?? [],
)
watch(
  () => form.value.product_id,
  () => (form.value.line_id = lines.value.length === 1 ? lines.value[0]!.id : null),
)

const canSave = computed(
  () => form.value.batch_number.trim() && form.value.product_id && form.value.factory_id && !saving.value,
)

function onFile(e: Event) {
  file.value = (e.target as HTMLInputElement).files?.[0] ?? null
}

async function save() {
  error.value = null
  saving.value = true
  try {
    const batch = await api.post<BatchDetail>('/batches', {
      ...form.value,
      batch_number: form.value.batch_number.trim(),
    })
    if (file.value) {
      const data = new FormData()
      data.append('source', 'factory')
      data.append('file', file.value)
      await api.postMultipart(`/batches/${batch.id}/coas`, data)
    }
    await router.push(`/batches/${batch.id}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not register the batch.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div class="page">
    <RouterLink to="/batches" class="back">Batches</RouterLink>
    <h1>Register a batch</h1>
    <p class="sub">
      Use this when a partner factory tells you a batch is made. You can attach its COA now or when
      it arrives.
    </p>

    <form v-if="options" class="card" @submit.prevent="save">
      <div class="grid">
        <label>
          Product
          <select v-model="form.product_id" required>
            <option :value="null" disabled>Choose a product</option>
            <option v-for="p in options.products" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>

        <label>
          Made by
          <select v-model="form.factory_id" required>
            <option :value="null" disabled>Choose the partner factory</option>
            <option v-for="f in options.factories" :key="f.id" :value="f.id">
              {{ f.name }} ({{ f.city }}, {{ f.country }})
            </option>
          </select>
        </label>

        <label>
          Factory batch number
          <input v-model="form.batch_number" placeholder="e.g. FC-2611-14" required />
        </label>

        <label>
          Quantity (t)
          <input v-model.number="form.quantity" type="number" min="0" step="0.1" placeholder="e.g. 10" />
        </label>

        <label class="wide">
          Order line
          <select v-model="form.line_id" :disabled="!form.product_id">
            <option :value="null">Not known yet</option>
            <option v-for="l in lines" :key="l.id" :value="l.id">
              {{ l.label }} · {{ l.customer }} · {{ l.quantity }} {{ l.unit }}
            </option>
          </select>
          <span class="hint">
            The batch is checked against this line’s spec. If you leave it empty, BatchGate
            suggests a line once the COA values are in.
          </span>
        </label>

        <label class="wide">
          Factory COA (optional)
          <input type="file" accept="application/pdf,image/png,image/jpeg" @change="onFile" />
          <span class="hint">PDF, PNG or JPEG, up to 15 MB.</span>
        </label>
      </div>

      <p v-if="error" class="error" role="alert">{{ error }}</p>

      <div class="actions">
        <button class="primary" type="submit" :disabled="!canSave">
          {{ saving ? 'Registering…' : 'Register batch' }}
        </button>
        <RouterLink to="/batches" class="cancel">Cancel</RouterLink>
      </div>
    </form>
    <p v-else-if="error" class="error" role="alert">{{ error }}</p>
  </div>
</template>

<style scoped>
.page {
  display: grid;
  gap: 0.75rem;
  max-width: 46rem;
}

.back {
  font-size: var(--t-s);
  color: var(--ink-2);
  text-decoration: none;
}

.back::before {
  content: '‹ ';
}

h1 {
  font-size: var(--t-2xl);
}

.sub {
  color: var(--ink-2);
  font-size: var(--t-s);
  max-width: 60ch;
}

.card {
  margin-top: 0.75rem;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  padding: 1.25rem;
  display: grid;
  gap: 1.25rem;
}

.grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.wide {
  grid-column: 1 / -1;
}

label {
  display: grid;
  gap: 0.35rem;
  font-size: var(--t-s);
  font-weight: 500;
}

input,
select {
  font: inherit;
  font-weight: 400;
  padding: 0.55rem 0.7rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface);
}

input[type='file'] {
  padding: 0.45rem;
  background: var(--surface-2);
}

.hint {
  font-weight: 400;
  font-size: var(--t-xs);
  color: var(--ink-3);
}

.actions {
  display: flex;
  align-items: center;
  gap: 1rem;
}

.primary {
  padding: 0.6rem 1.1rem;
  border: 0;
  border-radius: var(--radius-s);
  background: var(--brand);
  color: var(--brand-ink);
  font-weight: 600;
  cursor: pointer;
}

.primary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.cancel {
  color: var(--ink-2);
  font-size: var(--t-s);
}

.error {
  color: var(--hold);
  font-size: var(--t-s);
}

@media (max-width: 640px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
