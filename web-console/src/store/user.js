import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api'

export const useUserStore = defineStore('user', () => {
  // 从 localStorage 恢复用户信息
  const savedUser = (() => {
    try {
      return JSON.parse(localStorage.getItem('user_info') || 'null')
    } catch {
      return null
    }
  })()

  const user = ref(savedUser)
  const token = ref(localStorage.getItem('auth_token') || '')

  const isLoggedIn = computed(() => !!user.value)
  const isAdmin = computed(() => user.value?.is_admin || false)
  const userId = computed(() => user.value?.user_id || '')
  const userName = computed(() => user.value?.name || '')

  async function fetchProfile() {
    const res = await authApi.profile()
    user.value = res
    token.value = localStorage.getItem('auth_token') || ''
    localStorage.setItem('user_info', JSON.stringify(res))
    return res
  }

  async function login(username, password) {
    const res = await authApi.login(username, password)
    localStorage.setItem('auth_token', res.access_token)
    localStorage.setItem('user_info', JSON.stringify(res.user))
    token.value = res.access_token
    user.value = res.user
    return res.user
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('auth_token')
    localStorage.removeItem('user_info')
  }

  return {
    user,
    token,
    isLoggedIn,
    isAdmin,
    userId,
    userName,
    fetchProfile,
    login,
    logout,
  }
})
