<template>
  <div class="tobacco-page">
    <van-nav-bar title="烟草证审核" left-arrow @click-left="router.push('/home')" />
    <main class="page-shell">
      <nav class="view-switcher" aria-label="烟草证审核视图">
        <button :class="{ active: activeView === 'reports' }" type="button" @click="activeView = 'reports'">比对报告</button>
        <button :class="{ active: activeView === 'workbench' }" type="button" @click="activeView = 'workbench'">待办核对</button>
      </nav>

      <TobaccoReportCenter
        v-if="activeView === 'reports'"
        :records="records"
        :loading="loading"
        @reload="loadReports"
      />
      <TobaccoReviewWorkbench v-else @report-created="handleReportCreated" />
    </main>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { showToast } from 'vant'
import { tobaccoApi } from '@/api'
import TobaccoReportCenter from '@/features/tobacco/TobaccoReportCenter.vue'
import TobaccoReviewWorkbench from '@/features/tobacco/TobaccoReviewWorkbench.vue'

const router = useRouter()
const activeView = ref('reports')
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
    showToast(error.message || '无法加载烟草证比对报告')
  } finally {
    loading.value = false
  }
}

function handleReportCreated(report) {
  if (report?.id) {
    records.value = [report, ...records.value.filter((item) => item.id !== report.id)]
  }
  loadReports()
}
</script>

<style scoped>
.tobacco-page { --tobacco-ink: #162a3a; --tobacco-muted: #657887; --tobacco-accent: #176784; --tobacco-accent-soft: #edf6f8; --tobacco-line: #dce6eb; --tobacco-line-strong: #becfd7; --tobacco-surface: #ffffff; --tobacco-surface-muted: #f5f8f9; --tobacco-focus: #55a6c3; min-height: 100vh; background: #eef3f5; color: var(--tobacco-ink); font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif; }
.tobacco-page :deep(.van-nav-bar) { height: 58px; border-bottom: 1px solid var(--tobacco-line); background: var(--tobacco-surface); }.tobacco-page :deep(.van-nav-bar__title) { color: var(--tobacco-ink); font-size: 16px; font-weight: 650; }.tobacco-page :deep(.van-nav-bar .van-icon) { color: var(--tobacco-accent); }
.page-shell { width: min(1120px, 100%); box-sizing: border-box; margin: 0 auto; padding: 28px 20px 56px; }
.view-switcher { display: inline-flex; gap: 4px; margin: 0 0 28px; padding: 4px; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); }
.view-switcher button { min-width: 96px; padding: 8px 14px; border: 0; border-radius: 5px; background: transparent; color: var(--tobacco-muted); font-size: 14px; transition: background-color .16s ease, color .16s ease; }.view-switcher button:hover { color: var(--tobacco-accent); background: var(--tobacco-surface-muted); }.view-switcher button:active { transform: translateY(1px); }.view-switcher button.active { background: var(--tobacco-accent); color: #fff; font-weight: 600; }
@media (prefers-reduced-motion: reduce) { .tobacco-page *, .tobacco-page *::before, .tobacco-page *::after { transition: none !important; } }
@media (max-width: 600px) { .page-shell { padding: 18px 12px 40px; }.view-switcher { display: grid; width: 100%; box-sizing: border-box; grid-template-columns: 1fr 1fr; margin-bottom: 20px; }.view-switcher button { min-width: 0; } }
</style>
