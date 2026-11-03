import { createRouter, createWebHistory } from 'vue-router'

import type { Permission } from '@/types'

declare module 'vue-router' {
  interface RouteMeta {
    public?: boolean
    permission?: Permission
  }
}

const router = createRouter({
  history: createWebHistory(),
  routes: [
    {
      path: '/login',
      name: 'login',
      component: () => import('@/views/LoginView.vue'),
      meta: { public: true },
    },
    {
      path: '/',
      component: () => import('@/layouts/AppShell.vue'),
      children: [
        {
          path: '',
          name: 'dashboard',
          component: () => import('@/views/DashboardView.vue'),
          meta: { permission: 'dashboard:view' },
        },
        {
          path: 'batches',
          name: 'batches',
          component: () => import('@/views/BatchesView.vue'),
          meta: { permission: 'batches:view' },
        },
        {
          path: 'batches/new',
          name: 'batch-new',
          component: () => import('@/views/NewBatchView.vue'),
          meta: { permission: 'coa:upload' },
        },
        {
          path: 'batches/:id(\\d+)',
          name: 'batch',
          component: () => import('@/views/BatchDetailView.vue'),
          meta: { permission: 'batches:view' },
          props: (route) => ({ id: Number(route.params.id) }),
        },
        {
          path: 'orders',
          name: 'orders',
          component: () => import('@/views/OrdersView.vue'),
          meta: { permission: 'orders:view' },
        },
        {
          path: 'orders/new',
          name: 'order-new',
          component: () => import('@/views/NewOrderView.vue'),
          meta: { permission: 'orders:edit' },
        },
        {
          path: 'orders/:id(\\d+)',
          name: 'order',
          component: () => import('@/views/OrderDetailView.vue'),
          meta: { permission: 'orders:view' },
          props: (route) => ({ id: Number(route.params.id) }),
        },
        {
          path: 'specs',
          name: 'specs',
          component: () => import('@/views/SpecsView.vue'),
          meta: { permission: 'specs:view' },
        },
        {
          path: 'specs/new',
          name: 'spec-new',
          component: () => import('@/views/SpecEditorView.vue'),
          meta: { permission: 'specs:edit' },
        },
        {
          path: 'specs/:id(\\d+)',
          name: 'spec',
          component: () => import('@/views/SpecDetailView.vue'),
          meta: { permission: 'specs:view' },
          props: (route) => ({ id: Number(route.params.id) }),
        },
        {
          path: 'specs/:id(\\d+)/edit',
          name: 'spec-edit',
          component: () => import('@/views/SpecEditorView.vue'),
          meta: { permission: 'specs:edit' },
          props: (route) => ({ id: Number(route.params.id) }),
        },
        {
          path: 'audit',
          name: 'audit',
          component: () => import('@/views/AuditView.vue'),
          meta: { permission: 'audit:view' },
        },
        {
          path: 'knowledge',
          name: 'knowledge',
          component: () => import('@/views/KnowledgeView.vue'),
          meta: { permission: 'knowledge:view' },
        },
        {
          path: 'knowledge/documents/:id(\\d+)',
          name: 'knowledge-document',
          component: () => import('@/views/KnowledgeDocumentView.vue'),
          meta: { permission: 'knowledge:view' },
          props: (route) => ({ id: Number(route.params.id) }),
        },
      ],
    },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})

router.beforeEach(async (to) => {
  // Imported lazily to avoid a circular import (the store uses the router for logout).
  const { useAuthStore } = await import('@/stores/auth')
  const auth = useAuthStore()
  await auth.restore()

  if (to.meta.public) {
    return auth.isAuthenticated && to.name === 'login' ? { name: 'dashboard' } : true
  }
  if (!auth.isAuthenticated) {
    return { name: 'login', query: to.fullPath !== '/' ? { next: to.fullPath } : {} }
  }
  if (to.meta.permission && !auth.can(to.meta.permission)) {
    return { name: 'dashboard' }
  }
  return true
})

export default router
