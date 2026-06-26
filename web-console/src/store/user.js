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

  const isLoggedIn = computed(() => !!token.value || isDemoMode.value)
  const isAdmin = computed(() => user.value?.is_admin || false)
  const isDemoMode = computed(() => localStorage.getItem('demo_mode') === 'true')
  const userId = computed(() => user.value?.user_id || '')
  const userName = computed(() => user.value?.name || '')

  async function login(code) {
    const res = await authApi.login(code)
    token.value = res.token
    user.value = res.user
    localStorage.setItem('auth_token', res.token)
    localStorage.setItem('user_info', JSON.stringify(res.user))
    return res
  }

  async function fetchProfile() {
    const res = await authApi.profile()
    user.value = res
    localStorage.setItem('user_info', JSON.stringify(res))
    return res
  }

  function setDemoUser() {
    const demoUser = {
      user_id: 'DemoUser',
      name: '演示用户',
      is_admin: true,
    }
    user.value = demoUser
    localStorage.setItem('auth_token', 'demo-token')
    localStorage.setItem('demo_mode', 'true')
    localStorage.setItem('user_info', JSON.stringify(demoUser))
  }

  function logout() {
    token.value = ''
    user.value = null
    localStorage.removeItem('auth_token')
    localStorage.removeItem('demo_mode')
    localStorage.removeItem('user_info')
  }

  return {
    user,
    token,
    isLoggedIn,
    isAdmin,
    isDemoMode,
    userId,
    userName,
    login,
    fetchProfile,
    setDemoUser,
    logout,
  }
})
