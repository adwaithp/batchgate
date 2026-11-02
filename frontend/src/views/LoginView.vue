<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'

import { api, ApiError } from '@/api/client'
import { useAuthStore } from '@/stores/auth'
import type { DemoAccounts } from '@/types'

const auth = useAuthStore()
const router = useRouter()
const route = useRoute()

const email = ref('')
const password = ref('')
const error = ref<string | null>(null)
const submitting = ref<string | null>(null) // email being signed in, for button state
const demo = ref<DemoAccounts | null>(null)

onMounted(async () => {
  try {
    demo.value = await api.get<DemoAccounts>('/auth/demo-accounts')
  } catch {
    demo.value = null
  }
})

async function signIn(withEmail: string, withPassword: string) {
  error.value = null
  submitting.value = withEmail
  try {
    await auth.login(withEmail, withPassword)
    const next = typeof route.query.next === 'string' ? route.query.next : '/'
    await router.replace(next)
  } catch (e) {
    error.value =
      e instanceof ApiError && e.status === 401
        ? 'That email and password don’t match an account.'
        : e instanceof Error
          ? e.message
          : 'Sign-in failed.'
  } finally {
    submitting.value = null
  }
}

function onSubmit() {
  signIn(email.value.trim(), password.value)
}

// The sample sheet on the left: one value fails, so the batch is held.
const sample = [
  { name: 'Iron (as Fe)', limit: 'min 13.8 %', result: '13.9 %', ok: true },
  { name: 'Free acid (as HCl)', limit: 'max 0.5 %', result: '0.31 %', ok: true },
  { name: 'Insoluble matter', limit: 'max 0.10 %', result: '0.14 %', ok: false },
  { name: 'Specific gravity', limit: '1.40 – 1.45', result: '1.42', ok: true },
]
</script>

<template>
  <main class="login">
    <section class="story" aria-label="What BatchGate does">
      <div class="brand">
        <svg viewBox="0 0 32 32" width="28" height="28" aria-hidden="true">
          <path d="M9 7v18M23 7v18" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
          <path d="M9 16h14" stroke="var(--release)" stroke-width="3" stroke-linecap="round" />
        </svg>
        BatchGate
      </div>

      <h1>Every batch is checked against the customer’s spec before it ships.</h1>

      <figure class="sheet">
        <figcaption>
          <span>Ferric Chloride, batch <span class="nowrap">FC-2611-07</span></span>
          <span class="stamp" role="img" aria-label="Decision: hold">Hold</span>
        </figcaption>
        <table>
          <thead>
            <tr>
              <th scope="col">Test</th>
              <th scope="col">Spec</th>
              <th scope="col">Result</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in sample" :key="row.name" :class="{ fail: !row.ok }">
              <td>{{ row.name }}</td>
              <td class="num">{{ row.limit }}</td>
              <td class="num">
                {{ row.result }}
                <span class="visually-hidden">{{ row.ok ? 'passes' : 'fails' }}</span>
              </td>
            </tr>
          </tbody>
        </table>
        <p class="why">Insoluble matter is above the 0.10 % limit, so the batch stays in the warehouse.</p>
      </figure>
    </section>

    <section class="panel">
      <div class="panel-inner">
        <h2>Sign in</h2>

        <form @submit.prevent="onSubmit" novalidate>
          <label>
            Work email
            <input v-model="email" type="email" autocomplete="username" required />
          </label>
          <label>
            Password
            <input v-model="password" type="password" autocomplete="current-password" required />
          </label>
          <p v-if="error" class="error" role="alert">{{ error }}</p>
          <button class="primary" type="submit" :disabled="!!submitting || !email || !password">
            {{ submitting === email.trim() ? 'Signing in…' : 'Sign in' }}
          </button>
        </form>

        <div v-if="demo?.enabled && demo.accounts.length" class="demo">
          <h3>Try it as</h3>
          <p class="hint">Demo accounts. Each role sees a different view.</p>
          <ul>
            <li v-for="acc in demo.accounts" :key="acc.email">
              <button
                type="button"
                class="account"
                :disabled="!!submitting"
                @click="signIn(acc.email, demo!.password ?? '')"
              >
                <span class="who">
                  <strong>{{ acc.role_label }}</strong>
                  <span>{{ acc.full_name }}</span>
                </span>
                <span class="what">
                  {{ submitting === acc.email ? 'Signing in…' : acc.description }}
                </span>
              </button>
            </li>
          </ul>
        </div>
      </div>
    </section>
  </main>
</template>

<style scoped>
.login {
  display: grid;
  grid-template-columns: minmax(0, 1.1fr) minmax(0, 1fr);
  min-height: 100vh;
}

/* Left: the product in one glance */
.story {
  background: var(--brand);
  color: var(--brand-ink);
  padding: 3rem clamp(1.5rem, 5vw, 4.5rem);
  display: flex;
  flex-direction: column;
  gap: 2.5rem;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.6rem;
  font-weight: 600;
  font-size: var(--t-l);
}

.story h1 {
  font-size: clamp(1.6rem, 2.6vw, 2.2rem);
  font-weight: 500;
  max-width: 22ch;
  margin-top: auto;
}

.sheet {
  margin: 0 0 auto;
  background: var(--surface);
  color: var(--ink);
  border-radius: var(--radius-m);
  padding: 1.25rem 1.25rem 1rem;
  max-width: 30rem;
  box-shadow: 0 18px 40px -20px rgba(0, 0, 0, 0.55);
}

.sheet figcaption {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 1rem;
  font-size: var(--t-s);
  color: var(--ink-2);
  margin-bottom: 0.75rem;
}

.nowrap {
  white-space: nowrap;
}

.stamp {
  color: var(--hold);
  border: 2px solid var(--hold);
  border-radius: var(--radius-s);
  padding: 0.1rem 0.6rem;
  font-weight: 700;
  font-size: var(--t-m);
  transform: rotate(-4deg);
}

.sheet table {
  width: 100%;
  border-collapse: collapse;
  font-size: var(--t-s);
}

.sheet th {
  text-align: left;
  font-weight: 500;
  color: var(--ink-3);
  padding: 0 0 0.4rem;
}

.sheet td {
  padding: 0.45rem 0;
  border-top: 1px solid var(--line);
}

.sheet th:not(:first-child),
.sheet td:not(:first-child) {
  text-align: right;
}

.sheet tr.fail td {
  color: var(--hold);
  font-weight: 600;
}

.sheet tr.fail td:last-child {
  background: var(--hold-bg);
  border-radius: var(--radius-s);
  padding-right: 0.4rem;
}

.why {
  margin-top: 0.75rem;
  font-size: var(--t-xs);
  color: var(--ink-2);
}

/* Right: the form */
.panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 3rem 1.5rem;
}

.panel-inner {
  width: 100%;
  max-width: 24rem;
}

.panel h2 {
  font-size: var(--t-xl);
  margin-bottom: 1.5rem;
}

form {
  display: grid;
  gap: 1rem;
}

label {
  display: grid;
  gap: 0.35rem;
  font-size: var(--t-s);
  font-weight: 500;
}

input {
  font: inherit;
  padding: 0.65rem 0.75rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface);
}

input:focus-visible {
  border-color: var(--approval);
}

.primary {
  margin-top: 0.25rem;
  padding: 0.7rem 1rem;
  border: 0;
  border-radius: var(--radius-s);
  background: var(--brand);
  color: var(--brand-ink);
  font-weight: 600;
  cursor: pointer;
}

.primary:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.error {
  color: var(--hold);
  font-size: var(--t-s);
}

.demo {
  margin-top: 2.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--line);
}

.demo h3 {
  font-size: var(--t-m);
}

.hint {
  font-size: var(--t-s);
  color: var(--ink-2);
  margin: 0.15rem 0 0.9rem;
}

.demo ul {
  list-style: none;
  margin: 0;
  padding: 0;
  display: grid;
  gap: 0.5rem;
}

.account {
  width: 100%;
  text-align: left;
  display: grid;
  gap: 0.15rem;
  padding: 0.7rem 0.85rem;
  border: 1px solid var(--line);
  border-radius: var(--radius-s);
  background: var(--surface);
  cursor: pointer;
}

.account:hover:not(:disabled) {
  border-color: var(--brand);
}

.account:disabled {
  cursor: wait;
}

.who {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  font-size: var(--t-s);
}

.who span {
  color: var(--ink-2);
}

.what {
  font-size: var(--t-xs);
  color: var(--ink-3);
}

@media (max-width: 860px) {
  .login {
    grid-template-columns: 1fr;
  }
  .story {
    gap: 1.5rem;
    padding-bottom: 2rem;
  }
  .story h1 {
    margin-top: 0;
  }
}
</style>
