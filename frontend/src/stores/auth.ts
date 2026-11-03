import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { api, setUnauthorizedHandler, tokenStore } from '@/api/client'
import router from '@/router'
import type { Permission, User } from '@/types'

interface TokenResponse {
  access_token: string
  token_type: string
  expires_in: number
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<User | null>(null)
  const loaded = ref(false)

  const isAuthenticated = computed(() => user.value !== null)

  /** Whether the signed-in user holds a permission. */
  function can(permission: Permission): boolean {
    return user.value?.permissions.includes(permission) ?? false
  }

  /** Sign in and load the user. */
  async function login(email: string, password: string) {
    const token = await api.postForm<TokenResponse>('/auth/token', { username: email, password })
    tokenStore.set(token.access_token)
    user.value = await api.get<User>('/auth/me')
    loaded.value = true
  }

  /** Restore the session from a saved token, once per page load. */
  async function restore() {
    if (loaded.value) return
    loaded.value = true
    if (!tokenStore.get()) return
    try {
      user.value = await api.get<User>('/auth/me')
    } catch {
      tokenStore.clear()
      user.value = null
    }
  }

  /** Forget the session and return to the sign-in page. */
  function logout() {
    tokenStore.clear()
    user.value = null
    router.push({ name: 'login' })
  }

  setUnauthorizedHandler(() => {
    if (user.value) logout()
  })

  return { user, isAuthenticated, can, login, restore, logout }
})
