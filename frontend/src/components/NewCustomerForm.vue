<script setup lang="ts">
import { nextTick, onMounted, ref } from 'vue'

import { api } from '@/api/client'
import type { CustomerRef } from '@/types'

/** Adds a customer inline. Not a <form>: it sits inside the order and spec forms. */
const emit = defineEmits<{ added: [customer: CustomerRef]; cancel: [] }>()

const draft = ref({ name: '', country: '', industry: '' })
const error = ref<string | null>(null)
const saving = ref(false)
const nameInput = ref<HTMLInputElement | null>(null)

onMounted(() => nextTick(() => nameInput.value?.focus()))

/** Add the customer and pass it to the form. */
async function add() {
  if (!draft.value.name.trim() || !draft.value.country.trim() || saving.value) return
  error.value = null
  saving.value = true
  try {
    const customer = await api.post<CustomerRef>('/customers', {
      name: draft.value.name.trim(),
      country: draft.value.country.trim(),
      industry: draft.value.industry.trim() || null,
    })
    emit('added', customer)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not add the customer.'
  } finally {
    saving.value = false
  }
}
</script>

<template>
  <div
    class="new-customer card pad"
    role="group"
    aria-labelledby="new-customer-title"
    @keydown.enter.prevent="add"
  >
    <p id="new-customer-title" class="title">New customer</p>
    <div class="grid">
      <label class="field">
        Name
        <input
          ref="nameInput"
          v-model="draft.name"
          placeholder="As on their purchase orders"
          maxlength="255"
        />
      </label>
      <label class="field">
        Country
        <input v-model="draft.country" placeholder="e.g. US" maxlength="64" />
      </label>
      <label class="field">
        <span>Industry <span class="hint">(optional)</span></span>
        <input v-model="draft.industry" placeholder="e.g. Water treatment" maxlength="64" />
      </label>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>
    <div class="actions">
      <button
        type="button"
        class="secondary"
        :disabled="saving || !draft.name.trim() || !draft.country.trim()"
        @click="add"
      >
        {{ saving ? 'Adding…' : 'Add customer' }}
      </button>
      <button type="button" class="link-btn cancel" @click="emit('cancel')">Cancel</button>
    </div>
  </div>
</template>

<style scoped src="../views/catalog.css"></style>
<style scoped>
.new-customer {
  display: grid;
  gap: 0.8rem;
  background: var(--surface-2);
}

.title {
  margin: 0;
  font-weight: 600;
}

.grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
  align-items: start;
}

@media (max-width: 640px) {
  .grid {
    grid-template-columns: 1fr;
  }
}
</style>
