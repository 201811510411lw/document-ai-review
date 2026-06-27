<template>
  <div class="dashboard-page">
    <van-nav-bar title="效期看板" left-arrow @click-left="router.push('/scene1')" />

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);">
        <div class="stat-num">{{ stats.total || 0 }}</div>
        <div class="stat-label">总证照数</div>
      </div>
      <div class="stat-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);">
        <div class="stat-num">{{ stats.expiring || 0 }}</div>
        <div class="stat-label">临期</div>
      </div>
      <div class="stat-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);">
        <div class="stat-num">{{ stats.valid || 0 }}</div>
        <div class="stat-label">正常</div>
      </div>
      <div class="stat-card" style="background: linear-gradient(135deg, #a18cd1 0%, #fbc2eb 100%);">
        <div class="stat-num">{{ stats.expired || 0 }}</div>
        <div class="stat-label">已过期</div>
      </div>
    </div>

    <!-- 权限提示 -->
    <van-notice-bar
      v-if="!isAdmin"
      text="仅管理员可接收每日日报推送"
      left-icon="info-o"
      color="#1989fa"
      background="#ecf5ff"
    />

    <!-- 今日日报 -->
    <div class="section-title">今日日报</div>
    <div v-if="dailyReport" class="daily-report">
      <div class="report-header">
        <van-icon name="notes-o" size="20" color="#1989fa" />
        <span>证照效期日报</span>
        <span class="report-time">{{ dailyReport.date || todayStr }}</span>
      </div>

      <div v-if="dailyReport.expiring?.length" class="report-section">
        <div class="section-label warning">⚠️ 即将过期（{{ dailyReport.expiring.length }} 条）</div>
        <div v-for="r in dailyReport.expiring.slice(0, 10)" :key="r.id" class="report-item" @click="goToQuery(r.company_name)">
          <span class="item-name">{{ r.company_name }}</span>
          <span class="item-detail">{{ r.license_type }} · 到期 {{ r.expire_date }} · 剩余 {{ r.expire_days_remaining }} 天</span>
        </div>
        <div v-if="dailyReport.expiring.length > 10" class="more-link">还有 {{ dailyReport.expiring.length - 10 }} 条...</div>
      </div>

      <div v-if="dailyReport.expired?.length" class="report-section">
        <div class="section-label danger">❌ 已过期（{{ dailyReport.expired.length }} 条）</div>
        <div v-for="r in dailyReport.expired.slice(0, 5)" :key="r.id" class="report-item" @click="goToQuery(r.company_name)">
          <span class="item-name">{{ r.company_name }}</span>
          <span class="item-detail">{{ r.license_type }} · {{ r.expire_date }} 过期</span>
        </div>
      </div>
    </div>
    <van-empty v-else-if="!loading" description="暂无日报数据" />

    <!-- 证照类型分布 -->
    <div class="section-title">证照类型分布</div>
    <div class="type-distribution">
      <div v-if="typeDistribution.length">
      <div v-for="item in typeDistribution" :key="item.type" class="type-bar-item">
        <span class="type-name">{{ item.type }}</span>
        <div class="bar-bg">
          <div
            class="bar-fill"
            :style="{ width: item.percent + '%', background: item.color }"
          />
        </div>
        <span class="type-count">{{ item.count }}</span>
      </div>
      </div>
      <van-empty v-else description="暂无证照类型统计" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { dashboardApi } from '@/api'
import { useUserStore } from '@/store/user'
import { showToast } from 'vant'

const userStore = useUserStore()
const router = useRouter()
const isAdmin = computed(() => userStore.isAdmin)
const stats = ref({})
const dailyReport = ref(null)
const loading = ref(true)
const todayStr = new Date().toISOString().slice(0, 10)

const typeDistribution = computed(() => {
  const rows = stats.value.type_distribution || []
  const max = Math.max(...rows.map(i => i.count), 1)
  return rows.map(i => ({ ...i, percent: (i.count / max) * 100 }))
})

onMounted(async () => {
  try {
    const [statsRes, dailyRes] = await Promise.all([
      dashboardApi.stats(),
      dashboardApi.daily(),
    ])
    stats.value = statsRes.data || statsRes
    dailyReport.value = dailyRes.data || dailyRes
  } catch (e) {
    showToast('加载失败: ' + e.message)
  } finally {
    loading.value = false
  }
})

function goToQuery(companyName) {
  router.push({ path: '/query', query: { keyword: companyName } })
}
</script>

<style scoped>
.dashboard-page {
  padding-bottom: 16px;
}
.stats-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 12px 16px;
}
.stat-card {
  border-radius: 8px;
  padding: 16px;
  color: #fff;
  text-align: center;
}
.stat-num {
  font-size: 28px;
  font-weight: 700;
}
.stat-label {
  font-size: 12px;
  opacity: 0.9;
  margin-top: 4px;
}
.section-title {
  font-size: 14px;
  font-weight: 600;
  color: #323233;
  padding: 16px 16px 8px;
}
.daily-report {
  margin: 0 16px;
  background: #fff;
  border-radius: 8px;
  padding: 16px;
}
.report-header {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 12px;
}
.report-time {
  font-size: 12px;
  color: #969799;
  font-weight: 400;
  margin-left: auto;
}
.report-section {
  margin-bottom: 12px;
}
.section-label {
  font-size: 13px;
  font-weight: 600;
  margin-bottom: 6px;
  padding: 4px 8px;
  border-radius: 4px;
}
.section-label.warning { background: #fff7e6; color: #ff976a; }
.section-label.danger { background: #ffeeed; color: #ee0a24; }
.report-item {
  padding: 6px 8px;
  border-bottom: 1px solid #f5f6f8;
  font-size: 13px;
  cursor: pointer;
}
.report-item:active { background: #f5f6f8; }
.item-name { font-weight: 500; display: block; }
.item-detail { font-size: 12px; color: #969799; }
.more-link { font-size: 12px; color: #1989fa; text-align: center; padding: 4px; }
.type-distribution {
  margin: 0 16px;
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
}
.type-bar-item {
  display: flex;
  align-items: center;
  margin-bottom: 10px;
}
.type-name { font-size: 13px; width: 90px; flex-shrink: 0; }
.bar-bg {
  flex: 1;
  height: 16px;
  background: #f5f6f8;
  border-radius: 8px;
  margin: 0 8px;
  overflow: hidden;
}
.bar-fill {
  height: 100%;
  border-radius: 8px;
  transition: width 0.3s ease;
}
.type-count {
  font-size: 12px;
  color: #969799;
  width: 30px;
  text-align: right;
}
</style>
