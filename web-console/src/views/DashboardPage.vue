<template>
  <div class="dashboard-page">
    <van-nav-bar title="效期看板" left-arrow @click-left="router.push('/scene1')" />

    <!-- 统计卡片（横向滚动） -->
    <div class="stats-scroll">
      <div class="stat-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);" @click="filterExpire = ''">
        <div class="stat-num">{{ stats.total || 0 }}</div>
        <div class="stat-label">总证照数</div>
      </div>
      <div class="stat-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);" @click="filterExpire = 'valid'">
        <div class="stat-num">{{ stats.valid || 0 }}</div>
        <div class="stat-label">正常</div>
      </div>
      <div class="stat-card" style="background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);" @click="filterExpire = 'expiring'">
        <div class="stat-num">{{ stats.expiring || 0 }}</div>
        <div class="stat-label">临期</div>
      </div>
      <div class="stat-card" style="background: linear-gradient(135deg, #fa709a 0%, #fee140 100%);" @click="filterExpire = 'expired'">
        <div class="stat-num">{{ stats.expired || 0 }}</div>
        <div class="stat-label">已过期</div>
      </div>
      <div class="stat-card" style="background: linear-gradient(135deg, #969799 0%, #646566 100%);" @click="filterExpire = 'unknown'">
        <div class="stat-num">{{ stats.unknown || 0 }}</div>
        <div class="stat-label">未识别</div>
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

    <!-- 每日日报 -->
    <div class="section-title">每日日报</div>
    <div v-if="dailyReport" class="daily-report">
      <div class="report-header">
        <van-icon name="notes-o" size="20" color="#1989fa" />
        <span>证照效期日报</span>
        <span class="report-time">{{ dailyReport.date || todayStr }}</span>
      </div>

      <!-- 昨日新上传 -->
      <div class="report-section">
        <div class="section-label new">
          📦 昨日上传（{{ newUploads.total }} 条）
          <span v-if="newUploads.total > 0" class="sub-count">
            <span class="count-safe">{{ newUploads.valid.length }} 有效</span>
            <span class="count-warn">{{ newUploads.expiring.length }} 临期</span>
            <span class="count-danger">{{ newUploads.expired.length }} 过期</span>
          </span>
        </div>
        <div v-if="newUploads.expiring?.length && (!filterExpire || filterExpire === 'expiring')" class="sub-section">
          <div class="sub-label warning">⚠️ 临期 {{ newUploads.expiring.length }} 条</div>
          <div v-for="r in newUploads.expiring.slice(0, 5)" :key="r.id" class="report-item" @click="goToQuery(r.company_name)">
            <span class="item-name">{{ r.company_name }}</span>
            <span class="item-detail">{{ r.license_type }} · 到期 {{ r.expire_date || '未知' }}{{ r.expire_days_remaining !== null && r.expire_days_remaining !== undefined ? ' · 剩余 ' + r.expire_days_remaining + ' 天' : '' }}</span>
          </div>
        </div>
        <div v-if="newUploads.expired?.length && (!filterExpire || filterExpire === 'expired')" class="sub-section">
          <div class="sub-label danger">❌ 过期 {{ newUploads.expired.length }} 条</div>
          <div v-for="r in newUploads.expired.slice(0, 5)" :key="r.id" class="report-item" @click="goToQuery(r.company_name)">
            <span class="item-name">{{ r.company_name }}</span>
            <span class="item-detail">{{ r.license_type }} · {{ r.expire_date || '未知日期' }} 过期</span>
          </div>
        </div>
        <div v-if="!newUploads.expiring?.length && !newUploads.expired?.length" class="empty-hint">{{ newUploads.valid.length > 0 ? '✅ 昨日上传证照均有效' : '昨日无新增上传' }}</div>
      </div>

      <!-- 当前效期概览（所有记录） -->
      <div class="report-section">
        <div class="section-label overview">📊 当前效期概览（共 {{ stats.total }} 条）</div>
        <div v-if="overviewValid.length > 0 && (!filterExpire || filterExpire === 'valid')" class="sub-section">
          <div class="sub-label safe">✅ 有效 {{ overviewValid.length }} 条</div>
          <div v-for="r in overviewValid.slice(0, limitValid)" :key="r.id" class="report-item" @click="goToQuery(r.company_name)">
            <span class="item-name">{{ r.company_name }}</span>
            <span class="item-detail">{{ r.license_type }} · {{ r.expire_date ? '到期 ' + r.expire_date : '长期有效' }}</span>
          </div>
          <div v-if="overviewValid.length > 10" class="more-link" @click="limitValid = limitValid >= overviewValid.length ? 10 : overviewValid.length">
            {{ limitValid >= overviewValid.length ? '收起' : '还有 ' + (overviewValid.length - limitValid) + ' 条...' }}
          </div>
        </div>
        <div v-if="overviewExpiring.length > 0 && (!filterExpire || filterExpire === 'expiring')" class="sub-section">
          <div class="sub-label warning">⚠️ 临期 {{ overviewExpiring.length }} 条</div>
          <div v-for="r in overviewExpiring.slice(0, limitExpiring)" :key="r.id" class="report-item" @click="goToQuery(r.company_name)">
            <span class="item-name">{{ r.company_name }}</span>
            <span class="item-detail">{{ r.license_type }} · 到期 {{ r.expire_date || '未知' }}{{ r.expire_days_remaining !== null && r.expire_days_remaining !== undefined ? ' · 剩余 ' + r.expire_days_remaining + ' 天' : '' }}</span>
          </div>
          <div v-if="overviewExpiring.length > 10" class="more-link" @click="limitExpiring = limitExpiring >= overviewExpiring.length ? 10 : overviewExpiring.length">
            {{ limitExpiring >= overviewExpiring.length ? '收起' : '还有 ' + (overviewExpiring.length - limitExpiring) + ' 条...' }}
          </div>
        </div>
        <div v-if="overviewExpired.length > 0 && (!filterExpire || filterExpire === 'expired')" class="sub-section">
          <div class="sub-label danger">❌ 过期 {{ overviewExpired.length }} 条</div>
          <div v-for="r in overviewExpired.slice(0, 5)" :key="r.id" class="report-item" @click="goToQuery(r.company_name)">
            <span class="item-name">{{ r.company_name }}</span>
            <span class="item-detail">{{ r.license_type }} · {{ r.expire_date || '未知日期' }} 过期</span>
          </div>
        </div>
        <div v-if="overviewUnknown.length > 0 && (!filterExpire || filterExpire === 'unknown')" class="sub-section">
          <div class="sub-label unknown">❓ 未识别 {{ overviewUnknown.length }} 条（无附件）</div>
          <div v-for="r in overviewUnknown.slice(0, 10)" :key="r.id" class="report-item" @click="goToQuery(r.company_name)">
            <span class="item-name">{{ r.company_name }}</span>
            <span class="item-detail">{{ r.license_type }} · 未上传证照文件</span>
          </div>
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
const limitExpiring = ref(10)
const limitValid = ref(10)

const filterExpire = ref('')

const typeDistribution = computed(() => {
  const rows = stats.value.type_distribution || []
  const max = Math.max(...rows.map(i => i.count), 1)
  return rows.map(i => ({ ...i, percent: (i.count / max) * 100 }))
})

const newUploads = computed(() => {
  const d = dailyReport.value
  if (!d) return { total: 0, valid: [], expiring: [], expired: [], unknown: [] }
  return d.new_uploads || { total: 0, valid: [], expiring: [], expired: [], unknown: [] }
})

const overviewValid = computed(() => {
  const d = dailyReport.value
  if (!d || !d.all_records) return []
  return d.all_records.filter(r => r.expire_status === 'valid')
})

const overviewExpiring = computed(() => {
  const d = dailyReport.value
  if (!d || !d.all_records) return []
  return d.all_records.filter(r => r.expire_status === 'expiring_soon')
})

const overviewUnknown = computed(() => {
  const d = dailyReport.value
  if (!d || !d.all_records) return []
  return d.all_records.filter(r => r.expire_status === 'unknown')
})

const overviewExpired = computed(() => {
  const d = dailyReport.value
  if (!d || !d.all_records) return []
  return d.all_records.filter(r => r.expire_status === 'expired')
})

onMounted(async () => {
  try {
    const [dailyRes, statsRes] = await Promise.all([
      dashboardApi.daily(),
      dashboardApi.stats(),
    ])
    const dailyData = dailyRes.data || dailyRes
    dailyReport.value = dailyData

    const statsData = statsRes.data || statsRes
    stats.value = {
      total: statsData.total || 0,
      valid: statsData.valid || 0,
      expiring: statsData.expiring || 0,
      expired: statsData.expired || 0,
      unknown: statsData.unknown || 0,
      type_distribution: statsData.type_distribution || [],
    }
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
.dashboard-page { padding-bottom: 16px; }
.stats-scroll {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 16px;
}
.stat-card {
  flex: 1 1 calc(33.33% - 8px);
  min-width: 100px;
  border-radius: 10px;
  padding: 14px 8px;
  color: #fff;
  text-align: center;
  cursor: pointer;
}
@media (min-width: 768px) {
  .stat-card {
    flex: 1;
    min-width: 0;
  }
}
.stat-num { font-size: 28px; font-weight: 700; }
.stat-label { font-size: 12px; opacity: 0.9; margin-top: 4px; }
.section-title {
  font-size: 14px; font-weight: 600; color: #323233;
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
  font-size: 12px; color: #969799; font-weight: 400; margin-left: auto;
}
.report-section { margin-bottom: 12px; }
.section-label {
  font-size: 13px; font-weight: 600;
  margin-bottom: 8px; padding: 4px 8px; border-radius: 4px;
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
}
.section-label.new { background: #e8fae8; color: #07c160; }
.section-label.overview { background: #f0f0ff; color: #667eea; }
.sub-count { font-size: 11px; font-weight: 400; display: flex; gap: 6px; }
.count-safe { color: #07c160; }
.count-warn { color: #ff976a; }
.count-danger { color: #ee0a24; }
.sub-section { margin-bottom: 8px; padding-left: 8px; }
.sub-label { font-size: 12px; font-weight: 600; margin-bottom: 4px; padding: 2px 6px; border-radius: 3px; }
.sub-label.warning { background: #fff7e6; color: #ff976a; }
.sub-label.danger { background: #ffeeed; color: #ee0a24; }
.sub-label.safe { background: #e8fae8; color: #07c160; }
.empty-hint { font-size: 12px; color: #969799; padding: 8px; text-align: center; }
.report-item {
  padding: 6px 8px;
  border-bottom: 1px solid #f5f6f8;
  font-size: 13px;
  cursor: pointer;
}
.report-item:active { background: #f5f6f8; }
.item-name { font-weight: 500; display: block; }
.item-detail { font-size: 12px; color: #969799; }
.more-link { font-size: 12px; color: #1989fa; text-align: center; padding: 4px; cursor: pointer; }
.type-distribution {
  margin: 0 16px; background: #fff; border-radius: 8px; padding: 12px 16px;
}
.type-bar-item {
  display: flex; align-items: center; margin-bottom: 10px;
}
.type-name { font-size: 13px; width: 90px; flex-shrink: 0; }
.bar-bg {
  flex: 1; height: 16px; background: #f5f6f8;
  border-radius: 8px; margin: 0 8px; overflow: hidden;
}
.bar-fill {
  height: 100%; border-radius: 8px; transition: width 0.3s ease;
}
.type-count { font-size: 12px; color: #969799; width: 30px; text-align: right; }
</style>
