<script setup lang="ts">
import { computed } from 'vue'
import { useRoute } from 'vue-router'

import { useAuthStore } from '@/stores/auth'
import type { Permission } from '@/types'

const auth = useAuthStore()

interface NavItem {
  label: string
  to?: string // undefined = not built yet
  permission: Permission
}

// Each role only sees what it is allowed to use.
const items: NavItem[] = [
  { label: 'Dashboard', to: '/', permission: 'dashboard:view' },
  { label: 'Batches', to: '/batches', permission: 'batches:view' },
  { label: 'Orders', permission: 'orders:view' },
  { label: 'Specs', permission: 'specs:view' },
  { label: 'Audit log', permission: 'audit:view' },
  { label: 'Users', permission: 'users:manage' },
]

const nav = computed(() => items.filter((i) => auth.can(i.permission)))

const route = useRoute()
function isActive(to: string) {
  return to === '/' ? route.path === '/' : route.path.startsWith(to)
}

const initials = computed(() =>
  (auth.user?.full_name ?? '')
    .split(' ')
    .map((p) => p[0])
    .slice(0, 2)
    .join(''),
)
</script>

<template>
  <div class="shell">
    <aside class="side">
      <div class="brand">
        <svg viewBox="0 0 32 32" width="24" height="24" aria-hidden="true">
          <path d="M9 7v18M23 7v18" stroke="currentColor" stroke-width="3" stroke-linecap="round" />
          <path d="M9 16h14" stroke="var(--release)" stroke-width="3" stroke-linecap="round" />
        </svg>
        BatchGate
      </div>

      <nav aria-label="Main">
        <template v-for="item in nav" :key="item.label">
          <RouterLink
            v-if="item.to"
            :to="item.to"
            class="nav-item"
            :class="{ active: isActive(item.to) }"
          >
            {{ item.label }}
          </RouterLink>
          <span v-else class="nav-item soon" aria-disabled="true">
            {{ item.label }}
            <small>Soon</small>
          </span>
        </template>
      </nav>

      <div class="me">
        <span class="avatar" aria-hidden="true">{{ initials }}</span>
        <span class="me-text">
          <strong>{{ auth.user?.full_name }}</strong>
          <span>{{ auth.user?.role_label }}</span>
        </span>
        <button type="button" class="logout" @click="auth.logout()">Sign out</button>
      </div>
    </aside>

    <main class="content">
      <RouterView />
    </main>
  </div>
</template>

<style scoped>
.shell {
  display: grid;
  grid-template-columns: 15rem minmax(0, 1fr);
  min-height: 100vh;
}

.side {
  background: var(--brand);
  color: var(--brand-ink);
  display: flex;
  flex-direction: column;
  padding: 1.25rem 0.75rem;
  position: sticky;
  top: 0;
  height: 100vh;
}

.brand {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  font-size: var(--t-l);
  padding: 0 0.6rem 1.5rem;
}

nav {
  display: grid;
  gap: 0.15rem;
}

.nav-item {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem 0.6rem;
  border-radius: var(--radius-s);
  color: inherit;
  text-decoration: none;
  font-size: var(--t-s);
}

.nav-item:hover:not(.soon) {
  background: rgba(255, 255, 255, 0.08);
}

.nav-item.active {
  background: rgba(255, 255, 255, 0.14);
  font-weight: 600;
}

.nav-item.soon {
  opacity: 0.5;
}

.nav-item small {
  font-size: var(--t-xs);
}

.me {
  margin-top: auto;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 0.25rem 0.6rem;
  align-items: center;
  padding: 1rem 0.6rem 0;
  border-top: 1px solid rgba(255, 255, 255, 0.15);
}

.avatar {
  width: 2rem;
  height: 2rem;
  border-radius: 50%;
  display: grid;
  place-items: center;
  background: rgba(255, 255, 255, 0.16);
  font-size: var(--t-xs);
  font-weight: 600;
}

.me-text {
  display: grid;
  font-size: var(--t-s);
  line-height: 1.3;
}

.me-text span {
  font-size: var(--t-xs);
  opacity: 0.75;
}

.logout {
  grid-column: 1 / -1;
  margin-top: 0.5rem;
  background: none;
  border: 1px solid rgba(255, 255, 255, 0.25);
  border-radius: var(--radius-s);
  padding: 0.4rem;
  font-size: var(--t-s);
  cursor: pointer;
}

.logout:hover {
  background: rgba(255, 255, 255, 0.08);
}

.content {
  padding: 2.25rem clamp(1rem, 4vw, 3rem) 3rem;
  max-width: 76rem;
}

@media (max-width: 760px) {
  .shell {
    grid-template-columns: 1fr;
  }
  .side {
    position: static;
    height: auto;
  }
  nav {
    grid-auto-flow: column;
    overflow-x: auto;
  }
  .me {
    grid-template-columns: auto 1fr auto;
  }
  .logout {
    grid-column: auto;
    margin: 0;
    padding: 0.4rem 0.7rem;
  }
}
</style>
