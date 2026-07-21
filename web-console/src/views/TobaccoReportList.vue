<template>
  <div class="tobacco-page">
    <van-nav-bar title="烟草证一致性监控" left-arrow @click-left="router.push('/home')" />
    <main class="page-shell">
      <p class="page-desc">查看 OA 自动审核结果，处理异常记录。</p>
      <TobaccoReportCenter
        :records="records"
        :loading="loading"
        @reload="loadReports"
      />
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { tobaccoApi } from '@/api'
import TobaccoReportCenter from '@/features/tobacco/TobaccoReportCenter.vue'

const router = useRouter()
const records = ref([])
const loading = ref(false)

onMounted(loadReports)

async function loadReports() {
  loading.value = true
  try {
    const response = await tobaccoApi.list({ limit: 200 })
    records.value = response.records || []
  } catch (error) {
    records.value = []
    showToast(error.message || '无法加载比对报告')
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.tobacco-page { min-height: 100vh; background: #f7f8fa; }
.tobacco-page :deep(.van-nav-bar) { border-bottom: 1px solid #ebedf0; }
.page-shell { width: min(1120px, 100%); box-sizing: border-box; margin: 0 auto; padding: 20px 20px 56px; }
.page-desc { margin: 0 0 20px; color: #969799; font-size: 13px; }
</style>
