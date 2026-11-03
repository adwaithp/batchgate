<script setup lang="ts">
import { computed, nextTick, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api } from '@/api/client'
import { DOCUMENT_KIND, formatDate } from '@/labels'
import type { DocumentKind, KnowledgeHit, KnowledgeOverview, ReferenceData } from '@/types'

const route = useRoute()
const router = useRouter()

const data = ref<KnowledgeOverview | null>(null)
const reference = ref<ReferenceData | null>(null)
const error = ref<string | null>(null)

const tab = computed<'documents' | 'cases'>(() =>
  route.query.tab === 'cases' ? 'cases' : 'documents',
)
/** Switch between documents and past cases. */
function setTab(t: 'documents' | 'cases') {
  router.replace({ query: { ...route.query, tab: t }, hash: '' })
}

// Search
const q = ref('')
const scope = ref({ customer_id: null as number | null, product_id: null as number | null })
const hits = ref<KnowledgeHit[] | null>(null)
const searching = ref(false)

/** Search the knowledge base. */
async function search() {
  if (q.value.trim().length < 2) return
  searching.value = true
  try {
    const params = new URLSearchParams({ q: q.value.trim() })
    if (scope.value.customer_id) params.set('customer_id', String(scope.value.customer_id))
    if (scope.value.product_id) params.set('product_id', String(scope.value.product_id))
    hits.value = await api.get<KnowledgeHit[]>(`/knowledge/search?${params}`)
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Search failed.'
  } finally {
    searching.value = false
  }
}

/** Escape text and mark the matched words. */
function highlight(text: string, words: string[]): string {
  const esc = (s: string) =>
    s.replace(/[&<>"]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;' })[c]!)
  if (!words.length) return esc(text)
  const re = new RegExp(
    `\\b(${words.map((w) => w.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')).join('|')})\\w*`,
    'gi',
  )
  return esc(text).replace(re, '<mark>$&</mark>')
}

/** Shorten text at a word boundary. */
function snippet(text: string, max = 320) {
  return text.length > max ? `${text.slice(0, max).replace(/\s\S*$/, '')}…` : text
}

// Upload (QC managers)
const showUpload = ref(false)
const form = ref({
  title: '',
  kind: 'quality_agreement' as DocumentKind,
  customer_id: null as number | null,
  product_id: null as number | null,
})
const file = ref<File | null>(null)
const uploading = ref(false)
const uploadError = ref<string | null>(null)

/** Upload a document, then reload the list. */
async function upload() {
  if (!file.value || !form.value.title.trim()) return
  uploading.value = true
  uploadError.value = null
  const fd = new FormData()
  fd.append('title', form.value.title.trim())
  fd.append('kind', form.value.kind)
  if (form.value.customer_id) fd.append('customer_id', String(form.value.customer_id))
  if (form.value.product_id) fd.append('product_id', String(form.value.product_id))
  fd.append('file', file.value)
  try {
    const doc = await api.upload<{ id: number }>('/knowledge/documents', fd)
    await router.push(`/knowledge/documents/${doc.id}`)
  } catch (e) {
    uploadError.value = e instanceof Error ? e.message : 'Upload failed.'
  } finally {
    uploading.value = false
  }
}

/** Load documents and past cases. */
async function load() {
  try {
    ;[data.value, reference.value] = await Promise.all([
      api.get<KnowledgeOverview>('/knowledge'),
      api.get<ReferenceData>('/reference'),
    ])
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Could not load the knowledge base.'
  }
}

// Citations link to #case-12: scroll to it and mark it.
async function focusHash() {
  if (!route.hash) return
  await nextTick()
  document.querySelector(route.hash)?.scrollIntoView({ block: 'center' })
}

onMounted(async () => {
  await load()
  focusHash()
})
watch(() => route.hash, focusHash)
</script>

<template>
  <div class="page">
    <header class="head">
      <div>
        <h1>Knowledge</h1>
        <p class="sub">
          Customer quality agreements, SOPs, test methods, and how past problems were resolved. The
          copilot searches this and cites what it uses; so can you.
        </p>
      </div>
      <button v-if="data?.can_edit" type="button" class="primary" @click="showUpload = !showUpload">
        Add a document
      </button>
    </header>

    <form v-if="showUpload && reference" class="card pad upload" @submit.prevent="upload">
      <div class="grid">
        <label class="field wide">
          Title
          <input
            v-model="form.title"
            placeholder="e.g. Ridgeway Industrial Supply: quality agreement"
            maxlength="255"
            required
          />
        </label>
        <label class="field">
          Kind
          <select v-model="form.kind">
            <option v-for="(label, k) in DOCUMENT_KIND" :key="k" :value="k">{{ label }}</option>
          </select>
        </label>
        <label class="field">
          Customer
          <select v-model="form.customer_id">
            <option :value="null">All customers</option>
            <option v-for="c in reference.customers" :key="c.id" :value="c.id">{{ c.name }}</option>
          </select>
        </label>
        <label class="field">
          Product
          <select v-model="form.product_id">
            <option :value="null">All products</option>
            <option v-for="p in reference.products" :key="p.id" :value="p.id">{{ p.name }}</option>
          </select>
        </label>
        <label class="field wide">
          File
          <input
            type="file"
            accept="application/pdf,text/plain,.txt,.md"
            required
            @change="file = ($event.target as HTMLInputElement).files?.[0] ?? null"
          />
          <span class="hint"
            >A PDF with text, or a plain text file. It is split into sections so citations can point
            to a clause.</span
          >
        </label>
      </div>
      <p v-if="uploadError" class="error" role="alert">{{ uploadError }}</p>
      <div class="actions">
        <button class="primary" type="submit" :disabled="uploading || !file || !form.title.trim()">
          {{ uploading ? 'Adding…' : 'Add to knowledge base' }}
        </button>
        <button type="button" class="link-btn" @click="showUpload = false">Cancel</button>
      </div>
    </form>

    <form class="card pad searchbox" role="search" @submit.prevent="search">
      <input
        v-model="q"
        type="search"
        placeholder="Ask in a few words, e.g. “retest policy” or “insoluble matter high”"
        aria-label="Search the knowledge base"
      />
      <select v-if="reference" v-model="scope.customer_id" aria-label="Customer">
        <option :value="null">Any customer</option>
        <option v-for="c in reference.customers" :key="c.id" :value="c.id">{{ c.name }}</option>
      </select>
      <select v-if="reference" v-model="scope.product_id" aria-label="Product">
        <option :value="null">Any product</option>
        <option v-for="p in reference.products" :key="p.id" :value="p.id">{{ p.name }}</option>
      </select>
      <button class="primary" type="submit" :disabled="searching || q.trim().length < 2">
        {{ searching ? 'Searching…' : 'Search' }}
      </button>
    </form>

    <section v-if="hits" class="results" aria-label="Search results">
      <p v-if="!hits.length" class="meta">Nothing found. Try other words.</p>
      <article v-for="h in hits" :key="h.ref" class="card hit">
        <div class="hit-head">
          <RouterLink :to="h.link" class="strong-link">{{ h.source }}</RouterLink>
          <span class="pill">{{ h.kind === 'case' ? 'Past case' : 'Document' }}</span>
        </div>
        <!-- eslint-disable-next-line vue/no-v-html -->
        <p class="hit-text" v-html="highlight(snippet(h.text), h.matched)" />
        <p class="meta">Matched: {{ h.matched.join(', ') }}</p>
      </article>
    </section>

    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <template v-if="data">
      <div class="tabs" role="tablist">
        <button
          type="button"
          role="tab"
          :aria-selected="tab === 'documents'"
          :class="['tab', { on: tab === 'documents' }]"
          @click="setTab('documents')"
        >
          Documents <span class="n">{{ data.documents.length }}</span>
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="tab === 'cases'"
          :class="['tab', { on: tab === 'cases' }]"
          @click="setTab('cases')"
        >
          Past cases <span class="n">{{ data.cases.length }}</span>
        </button>
      </div>

      <div v-if="tab === 'documents'" class="card table-wrap">
        <table style="min-width: 40rem">
          <thead>
            <tr>
              <th scope="col">Document</th>
              <th scope="col">Kind</th>
              <th scope="col">Applies to</th>
              <th scope="col" class="right">Sections</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!data.documents.length">
              <td colspan="4" class="empty">No documents yet.</td>
            </tr>
            <tr v-for="d in data.documents" :key="d.id">
              <td>
                <RouterLink :to="`/knowledge/documents/${d.id}`" class="strong-link">{{
                  d.title
                }}</RouterLink>
                <span class="meta"
                  >Added {{ formatDate(d.created_at)
                  }}<template v-if="d.added_by"> by {{ d.added_by }}</template></span
                >
              </td>
              <td class="nowrap">{{ DOCUMENT_KIND[d.kind] }}</td>
              <td>{{ d.customer ?? 'All customers' }} · {{ d.product ?? 'all products' }}</td>
              <td class="right num">{{ d.passages }}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <div v-else class="cases">
        <p class="meta">
          BatchGate adds a case whenever a batch a person had to resolve is released or rejected,
          using the notes people wrote. Older cases were imported from the QC deviation log.
        </p>
        <article
          v-for="c in data.cases"
          :id="`case-${c.id}`"
          :key="c.id"
          :class="['card', 'pad', 'case', { focus: route.hash === `#case-${c.id}` }]"
        >
          <header class="case-head">
            <h2>
              <RouterLink v-if="c.batch_id" :to="`/batches/${c.batch_id}`">{{
                c.batch_number
              }}</RouterLink>
              <template v-else>{{ c.batch_number }}</template>
            </h2>
            <span :class="['outcome', c.outcome]">{{
              c.outcome === 'released' ? 'Released' : 'Rejected'
            }}</span>
            <span class="meta">
              {{ c.product }} · {{ c.factory }} · {{ c.customer }} · closed
              {{ formatDate(c.closed_on) }}
              <template v-if="c.source === 'imported'"> · from the QC log</template>
            </span>
          </header>
          <p><strong>Problem.</strong> {{ c.problem }}</p>
          <p><strong>What was done.</strong> {{ c.actions }}</p>
        </article>
      </div>
    </template>
  </div>
</template>

<style scoped src="./catalog.css"></style>
<style scoped>
.upload .grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
  margin-bottom: 1rem;
}

.wide {
  grid-column: 1 / -1;
}

.searchbox {
  display: flex;
  flex-wrap: wrap;
  gap: 0.6rem;
}

.searchbox input {
  flex: 1 1 18rem;
  font-size: var(--t-m);
}

.searchbox select {
  flex: 0 1 12rem;
}

.results {
  display: grid;
  gap: 0.6rem;
}

.hit {
  padding: 0.85rem 1.1rem;
  display: grid;
  gap: 0.35rem;
}

.hit-head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 0.5rem;
  justify-content: space-between;
}

.hit-text {
  font-size: var(--t-s);
  color: var(--ink-2);
  margin: 0;
}

.hit-text :deep(mark) {
  background: var(--review-bg);
  color: var(--ink);
  border-radius: 2px;
  padding: 0 1px;
}

.tabs {
  display: flex;
  gap: 0.25rem;
  justify-self: start;
  background: var(--surface);
  border: 1px solid var(--line);
  border-radius: var(--radius-m);
  padding: 0.25rem;
}

.tab {
  border: 0;
  background: none;
  padding: 0.4rem 0.75rem;
  border-radius: var(--radius-s);
  font: inherit;
  font-size: var(--t-s);
  color: var(--ink-2);
  cursor: pointer;
}

.tab.on {
  background: var(--brand);
  color: var(--brand-ink);
  font-weight: 600;
}

.n {
  opacity: 0.75;
  margin-left: 0.25rem;
}

.cases {
  display: grid;
  gap: 0.75rem;
}

.case {
  display: grid;
  gap: 0.4rem;
  font-size: var(--t-s);
}

.case.focus {
  outline: 3px solid var(--approval);
}

.case p {
  margin: 0;
}

.case-head {
  display: flex;
  flex-wrap: wrap;
  align-items: baseline;
  gap: 0.25rem 0.75rem;
}

.case-head h2 {
  font-size: var(--t-m);
}

.outcome {
  font-size: var(--t-xs);
  font-weight: 600;
  padding: 0.05rem 0.5rem;
  border-radius: 999px;
}

.outcome.released {
  background: var(--release-bg);
  color: var(--release);
}

.outcome.rejected {
  background: var(--hold-bg);
  color: var(--hold);
}

@media (max-width: 720px) {
  .upload .grid {
    grid-template-columns: 1fr;
  }
}
</style>
