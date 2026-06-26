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

      <!-- 演示入口：当企微未配置时显示 -->
      <van-button
        v-if="showDemo"
        size="large"
        round
        plain
        style="margin-top: 16px; color: #969799; border-color: #dcdee0;"
        @click="handleDemoLogin"
      >
        🔑 演示模式（跳过登录）
      </van-button>
    </div>

    <div class="login-footer">
      <p>首次使用需通过企业微信授权</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { useUserStore } from '@/store/user'
import { showToast } from 'vant'

const router = useRouter()
const route = useRoute()
const userStore = useUserStore()
const loading = ref(false)
const showDemo = ref(false)

onMounted(async () => {
  // 检测是否已配置企微，未配置则显示演示入口
  try {
    const http = (await import('@/api/http')).default
    const res = await http.get('/auth/corp-info')
    if (!res.corp_id) {
      showDemo.value = true
    }
  } catch {
    showDemo.value = true
  }

  // 从企微 OAuth 回调回来携带 code
  const code = route.query.code
  if (code) {
    loading.value = true
    try {
      await userStore.login(code)
      showToast('登录成功')
      router.push('/home')
    } catch (e) {
      showToast('登录失败: ' + e.message)
    } finally {
      loading.value = false
    }
  }
})

async function handleLogin() {
  // 从后端获取 CorpID，再做 OAuth 跳转
  loading.value = true
  try {
    const http = (await import('@/api/http')).default
    const res = await http.get('/auth/corp-info')
    const corpId = res.corp_id || ''
    if (!corpId) {
      showToast('企微未配置，请使用演示模式')
      return
    }
    const redirectUri = encodeURIComponent(window.location.href.split('?')[0].split('#')[0])
    window.location.href = `https://open.weixin.qq.com/connect/oauth2/authorize?appid=${corpId}&redirect_uri=${redirectUri}&response_type=code&scope=snsapi_base&state=STATE#wechat_redirect`
  } catch (e) {
    showToast('获取登录信息失败')
  } finally {
    loading.value = false
  }
}

function handleDemoLogin() {
  userStore.setDemoUser()
  showToast('演示模式')
  router.push('/home')
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
.login-footer {
  position: fixed;
  bottom: 40px;
  color: #969799;
  font-size: 12px;
}
</style>
