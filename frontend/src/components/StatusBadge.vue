<script setup lang="ts">
import type { Tone } from '@/labels'

defineProps<{ label: string; tone: Tone }>()
</script>

<template>
  <span :class="['badge', `tone-${tone}`]">{{ label }}</span>
</template>

<style scoped>
.badge {
  --c: var(--idle);
  --bg: var(--idle-bg);
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  padding: 0.1rem 0.55rem 0.1rem 0.45rem;
  border-radius: 999px;
  background: var(--bg);
  color: var(--c);
  font-size: var(--t-xs);
  font-weight: 600;
  white-space: nowrap;
}

.badge::before {
  content: '';
  width: 0.45rem;
  height: 0.45rem;
  border-radius: 50%;
  background: currentColor;
}

.tone-review {
  --c: var(--review);
  --bg: var(--review-bg);
}
.tone-approval {
  --c: var(--approval);
  --bg: var(--approval-bg);
}
.tone-release {
  --c: var(--release);
  --bg: var(--release-bg);
}
.tone-hold {
  --c: var(--hold);
  --bg: var(--hold-bg);
}
.tone-idle {
  --c: #5f6d77;
}
</style>
