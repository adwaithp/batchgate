<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'

import { api } from '@/api/client'
import type { BatchDetail, CopilotBrief } from '@/types'

const props = defineProps<{ batch: BatchDetail }>()

const brief = ref<CopilotBrief | null>(null)
const busy = ref(false)
const error = ref<string | null>(null)
const copied = ref(false)
const elapsed = ref(0)
let timer: ReturnType<typeof setInterval> | undefined

/** Count the seconds while Claude works, so the wait is visible. */
function startTimer() {
  elapsed.value = 0
  timer = setInterval(() => (elapsed.value += 1), 1000)
}

/** Stop the wait counter. */
function stopTimer() {
  clearInterval(timer)
  timer = undefined
}

onBeforeUnmount(stopTimer)

// A new check makes an old brief stale.
watch(
  () => props.batch.verdict?.created_at,
  () => (brief.value = null),
)

const TOOL_NAMES: Record<string, string> = {
  get_verdict: 'the check result',
  get_spec: 'the spec',
  get_coa_readings: 'the COA readings',
  get_order_line: 'the order line',
  get_factory_history: 'the factory’s past batches',
  search_knowledge: 'the knowledge base',
}

/** Ask Claude for a brief on this batch. */
async function ask() {
  busy.value = true
  error.value = null
  startTimer()
  try {
    brief.value = await api.post<CopilotBrief>(`/batches/${props.batch.id}/copilot`, {})
  } catch (e) {
    error.value = e instanceof Error ? e.message : 'Claude couldn’t write the brief.'
  } finally {
    busy.value = false
    stopTimer()
  }
}

/** Copy the draft email to the clipboard. */
async function copyEmail() {
  if (!brief.value?.email) return
  const { subject, body } = brief.value.email
  try {
    await navigator.clipboard.writeText(`Subject: ${subject}\n\n${body}`)
    copied.value = true
    setTimeout(() => (copied.value = false), 2000)
  } catch {
    error.value = 'Couldn’t copy. Select the text instead.'
  }
}

// "[K12]" in Claude's text becomes a numbered link to that source.
function withCitations(text: string): { text: string; ref?: string; n?: number }[] {
  const refs = brief.value?.sources.map((src) => src.ref) ?? []
  return text.split(/(\[K\d+\])/).map((part) => {
    const m = part.match(/^\[(K\d+)\]$/)
    if (!m) return { text: part }
    const n = refs.indexOf(m[1]!) + 1
    return n ? { text: part, ref: m[1], n } : { text: '' }
  })
}

/** Link for a cited source. */
function linkFor(ref: string): string {
  return brief.value?.sources.find((src) => src.ref === ref)?.link ?? '/knowledge'
}

/** Readable list of the tools Claude used. */
function lookedAt(tools: string[]): string {
  return [...new Set(tools)].map((t) => TOOL_NAMES[t] ?? t).join(', ')
}
</script>

<template>
  <section class="copilot" aria-labelledby="copilot-title">
    <div class="head">
      <h2 id="copilot-title">Ask Claude</h2>
      <button v-if="!brief" type="button" class="ask" :disabled="busy" @click="ask">
        {{ busy ? 'Working…' : 'Explain this batch and draft the follow-up' }}
      </button>
    </div>
    <p v-if="!brief && !busy" class="intro">
      Claude reads the check, the spec, the COAs, this factory’s history and the knowledge base (the
      customer’s quality agreement, SOPs, past cases), then explains what needs doing, with sources,
      and drafts the email. It can’t change the batch.
    </p>
    <div v-if="busy" class="loading" role="status" aria-live="polite">
      <div class="loading-head">
        <span class="spinner" aria-hidden="true"></span>
        <span>
          <strong>Claude is looking into this batch</strong>
          <span class="loading-meta">
            {{ elapsed }}s ·
            {{
              elapsed < 45
                ? 'reading the check, the COAs and the knowledge base; usually under a minute'
                : 'still working; briefs that search more sources take longer'
            }}
          </span>
        </span>
      </div>
      <div class="skeleton" aria-hidden="true">
        <span style="width: 92%"></span>
        <span style="width: 78%"></span>
        <span style="width: 85%"></span>
        <span style="width: 55%"></span>
      </div>
    </div>
    <p v-if="error" class="error" role="alert">{{ error }}</p>

    <div v-if="brief" class="brief" :class="{ stale: busy }" :aria-busy="busy">
      <p class="explanation">
        <template v-for="(part, i) in withCitations(brief.explanation)" :key="i">
          <RouterLink v-if="part.ref" :to="linkFor(part.ref)" class="cite"
            >[{{ part.n }}]</RouterLink
          >
          <template v-else>{{ part.text }}</template>
        </template>
      </p>

      <h3>Next steps</h3>
      <ol class="steps">
        <li v-for="(step, i) in brief.next_steps" :key="i">
          <template v-for="(part, j) in withCitations(step)" :key="j">
            <RouterLink v-if="part.ref" :to="linkFor(part.ref)" class="cite"
              >[{{ part.n }}]</RouterLink
            >
            <template v-else>{{ part.text }}</template>
          </template>
        </li>
      </ol>

      <p v-if="brief.history_note" class="history">
        <strong>From this factory’s history:</strong>
        <template v-for="(part, i) in withCitations(brief.history_note)" :key="i">
          <RouterLink v-if="part.ref" :to="linkFor(part.ref)" class="cite"
            >[{{ part.n }}]</RouterLink
          >
          <template v-else>{{ part.text }}</template>
        </template>
      </p>

      <div v-if="brief.sources.length" class="sources">
        <h3>Sources</h3>
        <ol>
          <li v-for="src in brief.sources" :key="src.ref">
            <RouterLink :to="src.link">{{ src.title }}</RouterLink>
            <span class="supports">{{ src.supports }}</span>
          </li>
        </ol>
      </div>

      <div v-if="brief.email" class="email">
        <div class="email-head">
          <span> Draft email to the {{ brief.email.to }} · <em>read it before sending</em> </span>
          <button type="button" class="copy" @click="copyEmail">
            {{ copied ? 'Copied' : 'Copy' }}
          </button>
        </div>
        <p class="subject">{{ brief.email.subject }}</p>
        <pre class="body">{{ brief.email.body }}</pre>
      </div>

      <p class="foot">
        Claude looked at {{ lookedAt(brief.looked_at) }}. Every source was checked: Claude can only
        cite passages it actually found. The decision above is the rules engine’s; Claude only
        explains it.
        <button type="button" class="again" :disabled="busy" @click="ask">
          {{ busy ? 'Asking…' : 'Ask again' }}
        </button>
      </p>
    </div>
  </section>
</template>

<style scoped>
.copilot {
  background: var(--surface);
  border: 1px solid var(--line);
  border-left: 4px solid var(--approval);
  border-radius: var(--radius-m);
  padding: 1rem 1.15rem;
  display: grid;
  gap: 0.6rem;
}

.head {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem 1rem;
}

h2 {
  font-size: var(--t-l);
}

h3 {
  font-size: var(--t-s);
  color: var(--ink-2);
  font-weight: 600;
}

.ask {
  padding: 0.5rem 0.9rem;
  border: 0;
  border-radius: var(--radius-s);
  background: var(--approval);
  color: #fff;
  font: inherit;
  font-weight: 600;
  font-size: var(--t-s);
  cursor: pointer;
}

.ask:disabled {
  opacity: 0.7;
  cursor: progress;
}

.loading {
  display: grid;
  gap: 0.75rem;
  padding: 0.75rem 0.85rem;
  border-radius: var(--radius-s);
  background: var(--surface-2);
}

.loading-head {
  display: flex;
  align-items: flex-start;
  gap: 0.65rem;
  font-size: var(--t-s);
}

.loading-head > span:last-child {
  display: grid;
  gap: 0.1rem;
}

.loading-meta {
  font-size: var(--t-xs);
  color: var(--ink-2);
  font-variant-numeric: tabular-nums;
}

.spinner {
  flex: none;
  width: 1.1rem;
  height: 1.1rem;
  margin-top: 0.1rem;
  border-radius: 50%;
  border: 2px solid color-mix(in srgb, var(--approval) 25%, transparent);
  border-top-color: var(--approval);
  animation: spin 0.8s linear infinite;
}

.skeleton {
  display: grid;
  gap: 0.45rem;
}

.skeleton span {
  display: block;
  height: 0.6rem;
  border-radius: 999px;
  background: linear-gradient(90deg, var(--line) 25%, var(--surface) 50%, var(--line) 75%);
  background-size: 200% 100%;
  animation: shimmer 1.4s ease-in-out infinite;
}

.brief {
  display: grid;
  gap: 0.6rem;
  transition: opacity 0.2s;
}

.brief.stale {
  opacity: 0.45;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

@keyframes shimmer {
  from {
    background-position: 100% 0;
  }
  to {
    background-position: -100% 0;
  }
}

@media (prefers-reduced-motion: reduce) {
  .spinner,
  .skeleton span {
    animation: none;
  }
}

.intro,
.foot {
  font-size: var(--t-xs);
  color: var(--ink-2);
}

.explanation {
  font-size: var(--t-m);
  line-height: 1.55;
}

.steps {
  margin: 0;
  padding-left: 1.25rem;
  display: grid;
  gap: 0.3rem;
  font-size: var(--t-s);
}

.cite {
  font-size: var(--t-xs);
  font-weight: 600;
  vertical-align: super;
  text-decoration: none;
  color: var(--approval);
  margin-left: 0.1rem;
}

.sources ol {
  margin: 0.3rem 0 0;
  padding-left: 1.25rem;
  display: grid;
  gap: 0.35rem;
  font-size: var(--t-s);
}

.supports {
  display: block;
  color: var(--ink-2);
  font-size: var(--t-xs);
}

.history {
  font-size: var(--t-s);
  background: var(--review-bg);
  border-radius: var(--radius-s);
  padding: 0.5rem 0.7rem;
}

.email {
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface-2);
  overflow: hidden;
}

.email-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
  padding: 0.45rem 0.7rem;
  border-bottom: 1px solid var(--line);
  font-size: var(--t-xs);
  color: var(--ink-2);
}

.copy,
.again {
  border: 0;
  background: none;
  padding: 0;
  font: inherit;
  font-size: var(--t-xs);
  color: var(--approval);
  font-weight: 600;
  cursor: pointer;
}

.again {
  margin-left: 0.4rem;
}

.subject {
  font-weight: 600;
  font-size: var(--t-s);
  padding: 0.55rem 0.7rem 0;
}

.body {
  margin: 0;
  padding: 0.4rem 0.7rem 0.7rem;
  font: inherit;
  font-size: var(--t-s);
  white-space: pre-wrap;
  color: var(--ink);
}

.error {
  color: var(--hold);
  font-size: var(--t-s);
}
</style>
