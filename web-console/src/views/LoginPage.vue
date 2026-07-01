<template>
  <div class="login-page">
    <div class="login-header">
      <van-icon name="certificate" size="64" color="#1989fa" />
      <h1>证照管理系统</h1>
      <p>企业微信工作台应用</p>
    </div>

    <div class="login-body">
      <van-form class="password-form" @submit="handlePasswordLogin">
        <van-field
          v-model="username"
          name="username"
          label="账号"
          placeholder="请输入账号"
          autocomplete="username"
          :rules="[{ required: true, message: '请输入账号' }]"
        />
        <van-field
          v-model="password"
          type="password"
          name="password"
          label="密码"
          placeholder="请输入密码"
          autocomplete="current-password"
          :rules="[{ required: true, message: '请输入密码' }]"
        />
        <van-button
          type="primary"
          size="large"
          block
          :loading="passwordLoading"
          native-type="submit"
        >
          账号密码登录
        </van-button>
      </van-form>

      <div class="login-divider">或</div>

      <van-button
        type="default"
        size="large"
        block
        :loading="ssoLoading"
        @click="handleSsoLogin"
      >
        企业微信登录
      </van-button>

      <p v-if="loginHint" class="login-hint">{{ loginHint }}</p>
    </div>

    <div class="login-footer">
      <p>首次使用需通过企业微信授权</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { authApi } from '@/api'
import { showToast } from 'vant'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const ssoLoading = ref(false)
const passwordLoading = ref(false)
const username = ref('reviewer')
const password = ref('')
const loginHint = ref('')

onMounted(async () => {
  userStore.logout()

  let wecomConfigured = false
  try {
    const providers = await authApi.providers()
    const wecom = providers.providers?.find((item) => item.id === 'wecom')
    wecomConfigured = !!wecom?.configured
    if (wecom && !wecom.configured) {
      loginHint.value = wecom.status || '企业微信登录未配置'
    }
  } catch (e) {
    loginHint.value = e.message || '获取登录配置失败'
  }

  if (route.query.error) {
    showToast(`登录失败: ${route.query.error}`)
    return
  }

  if (wecomConfigured && isWecomWorkbench() && !recentlyAttemptedAutoSso()) {
    await startWecomWorkbenchSso()
  }
})

async function handlePasswordLogin() {
  passwordLoading.value = true
  try {
    await userStore.login(username.value, password.value)
    const redirect = typeof route.query.redirect === 'string' ? route.query.redirect : '/home'
    await router.replace(redirect)
  } catch (e) {
    showToast(e.message || '账号或密码错误')
  } finally {
    passwordLoading.value = false
  }
}

async function handleSsoLogin() {
  ssoLoading.value = true
  try {
    const res = await authApi.startSso()
    window.location.href = res.redirect_url
  } catch (e) {
    showToast(e.message || '发起企业微信登录失败')
    ssoLoading.value = false
  }
}

async function startWecomWorkbenchSso() {
  ssoLoading.value = true
  markAutoSsoAttempted()
  try {
    const res = await authApi.startSso('work')
    window.location.href = res.redirect_url
  } catch (e) {
    loginHint.value = e.message || '发起企业微信自动登录失败'
    ssoLoading.value = false
  }
}

function isWecomWorkbench() {
  return /wxwork/i.test(navigator.userAgent || '')
}

function recentlyAttemptedAutoSso() {
  const attemptedAt = Number(sessionStorage.getItem('wecom_auto_sso_attempted_at') || 0)
  return attemptedAt > 0 && Date.now() - attemptedAt < 60_000
}

function markAutoSsoAttempted() {
  sessionStorage.setItem('wecom_auto_sso_attempted_at', String(Date.now()))
}
</script>

<style scoped>
.login-page {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 100vh;
  padding: 32px;
  background: #fff;
}
.login-header {
  text-align: center;
  margin-bottom: 48px;
}
.login-header h1 {
  font-size: 24px;
  margin: 16px 0 8px;
}
.login-header p {
  color: #969799;
  font-size: 14px;
}
.login-body {
  width: 100%;
  max-width: 360px;
}
.password-form {
  display: grid;
  gap: 12px;
}
.password-form :deep(.van-cell) {
  border: 1px solid #ebedf0;
  border-radius: 8px;
}
.login-divider {
  display: flex;
  align-items: center;
  gap: 12px;
  margin: 20px 0;
  color: #969799;
  font-size: 13px;
}
.login-divider::before,
.login-divider::after {
  content: "";
  flex: 1;
  height: 1px;
  background: #ebedf0;
}
.login-hint {
  margin: 16px 0 0;
  color: #969799;
  font-size: 13px;
  line-height: 1.5;
  text-align: center;
}
.login-footer {
  position: fixed;
  bottom: 40px;
  color: #969799;
  font-size: 12px;
}
</style>
