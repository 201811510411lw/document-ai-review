<template>
  <div class="login-page">
    <div class="login-header">
      <van-icon name="certificate" size="64" color="#1989fa" />
      <h1>证照管理系统</h1>
      <p>企业微信工作台应用</p>
    </div>

    <div class="login-body">
      <van-button
        type="primary"
        size="large"
        round
        :loading="loading"
        @click="handleLogin"
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
import { useRoute } from 'vue-router'
import { useUserStore } from '@/store/user'
import { authApi } from '@/api'
import { showToast } from 'vant'

const route = useRoute()
const userStore = useUserStore()
const loading = ref(false)
const loginHint = ref('')

onMounted(async () => {
  userStore.logout()

  try {
    const providers = await authApi.providers()
    const wecom = providers.providers?.find((item) => item.id === 'wecom')
    if (wecom && !wecom.configured) {
      loginHint.value = wecom.status || '企业微信登录未配置'
    }
  } catch (e) {
    loginHint.value = e.message || '获取登录配置失败'
  }

  if (route.query.error) {
    showToast(`登录失败: ${route.query.error}`)
  }
})

async function handleLogin() {
  loading.value = true
  try {
    const res = await authApi.startSso('work')
    window.location.href = res.redirect_url
  } catch (e) {
    showToast(e.message || '发起企业微信登录失败')
    loading.value = false
  }
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
  max-width: 300px;
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
