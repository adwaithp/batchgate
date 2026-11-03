<script setup lang="ts">
import { nextTick, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'

import { api, tokenStore } from '@/api/client'
import { DOCUMENT_KIND, formatDate } from '@/labels'
import type { KnowledgeDocumentDetail } from '@/types'

const props = defineProps<{ id: number }>()
const route = useRoute()

const doc = ref<KnowledgeDocumentDetail | null>(null)
const error = ref<string | null>(null)
const archiving = ref(false)

/** Load the document and its passages. */
async function load() {
  error.value = null
  try {
    doc.value = await api.get<KnowledgeDocumentDetail>(`/knowledge/documents/${props.id}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load the document.'
  }
}

/** Scroll to the passage named in the URL hash. */
async function focusHash() {
  if (!route.hash) return
  await nextTick()
  document.querySelector(route.hash)?.scrollIntoView({ block: 'center' })
}

/** Remove the document from search. */
async function archive() {
  if (!doc.value) return
  archiving.value = true
  try {
    await api.post(`/knowledge/documents/${doc.value.id}/archive`, {})
    await load()
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not archive it.'
  } finally {
    archiving.value = false
  }
}

/** Open the original file. */
async function openFile() {
  if (!doc.value) return
  // Fetch with the auth header, then open a local copy.
  const res = await fetch(`/api/knowledge/documents/${doc.value.id}/file`, {
    headers: { Authorization: `Bearer ${tokenStore.get() ?? ''}` },
  })
  if (!res.ok) return
  window.open(URL.createObjectURL(await res.blob()), '_blank')
}

onMounted(async () => {
  await load()
  focusHash()
})
watch(() => props.id, load)
watch(() => route.hash, focusHash)
</script>

<template>
  <div class="page doc">
    <RouterLink to="/knowledge" class="back">Knowledge</RouterLink>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <template v-if="doc">
      <header class="head">
        <div>
          <h1>{{ doc.title }}</h1>
          <p class="sub">
            {{ DOCUMENT_KIND[doc.kind] }} · {{ doc.customer ?? 'all customers' }} ·
            {{ doc.product ?? 'all products' }} · added {{ formatDate(doc.created_at) }}
            <template v-if="doc.added_by"> by {{ doc.added_by }}</template>
          </p>
        </div>
        <div class="tools">
          <button v-if="doc.has_file" type="button" class="secondary" @click="openFile">
            Open original
          </button>
          <button
            v-if="doc.can_edit"
            type="button"
            class="secondary"
            :disabled="archiving"
            @click="archive"
          >
            {{ archiving ? 'Archiving…' : 'Archive' }}
          </button>
        </div>
      </header>

      <article class="card text">
        <section
          v-for="p in doc.passages_list"
          :id="`p${p.id}`"
          :key="p.id"
          :class="['passage', { focus: route.hash === `#p${p.id}` }]"
        >
          <h2 v-if="p.section">
            {{ p.section }}
            <span class="ref" :title="`The copilot cites this section as ${p.ref}`">{{
              p.ref
            }}</span>
          </h2>
          <p>{{ p.text }}</p>
        </section>
      </article>
    </template>
  </div>
</template>

<style scoped src="./catalog.css"></style>
<style scoped>
.doc {
  max-width: 54rem;
}

.tools {
  display: flex;
  gap: 0.5rem;
}

.text {
  padding: 0.5rem 0;
}

.passage {
  padding: 0.75rem 1.4rem;
  border-left: 3px solid transparent;
  scroll-margin-top: 6rem;
}

.passage.focus {
  border-left-color: var(--approval);
  background: var(--approval-bg);
}

.passage h2 {
  font-size: var(--t-m);
  display: flex;
  align-items: baseline;
  gap: 0.6rem;
}

.passage p {
  margin: 0.3rem 0 0;
  white-space: pre-line;
  line-height: 1.6;
}

.ref {
  font-size: var(--t-xs);
  font-weight: 500;
  color: var(--ink-3);
  font-variant-numeric: tabular-nums;
}
</style>
