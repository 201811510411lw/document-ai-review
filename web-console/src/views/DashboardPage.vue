<template>
  <div class="dashboard-page">
    <van-nav-bar title="效期看板" left-arrow @click-left="router.push('/scene1')" />

    <!-- 统计筛选卡片 -->
    <div class="stats-scroll">
      <div class="stat-card" style="background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);"
           :class="{ active: filterExpire === '' }"
           @click="filterExpire = ''; currentPage = 1">
        <div class="stat-num">{{ stats.total || 0 }}</div>
        <div class="stat-label">总证照数</div>
      </div>
      <div class="stat-card" style="background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);"
           :class="{ active: filterExpire === 'valid' }"
           @click="filterExpire = 'valid'; currentPage = 1">
        <div class="stat-num">{{ stats.valid || 0 }}</div>
        <div class="stat-label">正常</div>
      </div>
      <div class="stat-card stat-warning"
           :class="{ active: filterExpire === 'expiring' }"
           @click="filterExpire = 'expiring'; currentPage = 1">
        <div class="stat-num">{{ stats.expiring || 0 }}</div>
        <div class="stat-label">⚠️ 临期</div>
      </div>
      <div class="stat-card stat-danger"
           :class="{ active: filterExpire === 'expired' }"
           @click="filterExpire = 'expired'; currentPage = 1">
        <div class="stat-num">{{ stats.expired || 0 }}</div>
        <div class="stat-label">🚫 已过期</div>
      </div>
      <div class="stat-card" style="background: linear-gradient(135deg, #969799 0%, #646566 100%);"
           :class="{ active: filterExpire === 'unknown' }"
           @click="filterExpire = 'unknown'; currentPage = 1">
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

    <!-- 证照类型按钮选项 -->
    <div class="doc-type-bar">
      <span class="doc-type-label">证照类型：</span>
      <div class="doc-type-options">
        <span v-for="opt in docTypeOptions" :key="opt.value"
          class="doc-type-btn"
          :class="{ active: filterDocType === opt.value }"
          @click="filterDocType = opt.value; currentPage = 1">
          {{ opt.text }}
        </span>
      </div>
    </div>

    <!-- 结果信息 -->
    <div class="result-info" v-if="!loading">
      <span class="filter-result">{{ filteredTotal }} 条记录</span>
      <span v-if="filterExpire" class="clear-filter" @click="filterExpire = ''; currentPage = 1">清除筛选</span>
    </div>

    <!-- 数据表格 -->
    <div v-if="pagedRecords.length" class="data-table">
      <div class="table-header">
        <span class="col-status">效期类型</span>
        <span class="col-type">证照类型</span>
        <span class="col-name">公司/供应商名称</span>
        <span class="col-expire">到期日期</span>
      </div>
      <div v-for="r in pagedRecords" :key="r.id" class="table-row" @click="goToQuery(r.company_name)">
        <span class="col-status">
          <van-tag :type="statusTagType(r.expire_status)" size="small">
            {{ statusLabel(r.expire_status) }}
          </van-tag>
        </span>
        <span class="col-type">{{ r.license_type }}</span>
        <span class="col-name van-multi-ellipsis--l2">{{ r.company_name }}</span>
        <span class="col-expire">
          {{ r.expire_date || '-' }}
          <span v-if="r.expire_days_remaining !== null" class="days-remaining"
                :class="{ danger: r.expire_days_remaining < 0, warning: r.expire_days_remaining >= 0 && r.expire_days_remaining <= 30 }">
            {{ r.expire_days_remaining < 0 ? '已过期' : r.expire_days_remaining + '天' }}
          </span>
        </span>
      </div>
    </div>
    <van-empty v-else-if="!loading" :description="filteredTotal === 0 ? '暂无匹配记录' : '加载中...'" />

    <!-- 分页 -->
    <div v-if="totalPages > 1" class="pagination-wrapper">
      <van-pagination v-model="currentPage" :page-count="totalPages" mode="simple"
        @change="scrollToTop" />
    </div>

    <van-loading v-if="loading" class="page-loading" size="24">加载中...</van-loading>

    <!-- 证照类型分布（保持不变） -->
    <div class="section-title">证照类型分布</div>
    <div class="type-distribution">
      <div v-if="typeDistribution.length">
        <div v-for="item in typeDistribution" :key="item.type" class="type-bar-item">
          <span class="type-name">{{ item.type }}</span>
          <div class="bar-bg">
            <div class="bar-fill" :style="{ width: item.percent + '%', background: item.color }" />
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

const dailyReport = ref(null)
const loading = ref(true)
const stats = ref({})
const filterExpire = ref('')
const filterDocType = ref('')
const currentPage = ref(1)
const pageSize = 15

const docTypeOptions = [
  { text: '全部证照类型', value: '' },
  { text: '营业执照', value: 'business_license' },
  { text: '食品经营许可证', value: 'food_license' },
  { text: '食品生产许可证', value: 'food_production_license' },
  { text: '商品报告', value: 'product_report' },
]

const typeDistribution = computed(() => {
  const rows = stats.value.type_distribution || []
  const max = Math.max(...rows.map(i => i.count), 1)
  return rows.map(i => ({ ...i, percent: (i.count / max) * 100 }))
})

const allRecords = computed(() => {
  const d = dailyReport.value
  if (!d || !d.all_records) return []
  return d.all_records
})

const filteredRecords = computed(() => {
  let list = allRecords.value
  if (filterExpire.value) {
    list = list.filter(r => r.expire_status === filterExpire.value)
  }
  if (filterDocType.value) {
    const dt = filterDocType.value
    list = list.filter(r => r.document_type === dt || r._document_type === dt)
  }
  return list
})

const filteredTotal = computed(() => filteredRecords.value.length)

const totalPages = computed(() => Math.max(1, Math.ceil(filteredRecords.value.length / pageSize)))

const pagedRecords = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return filteredRecords.value.slice(start, start + pageSize)
})

function statusLabel(status) {
  const map = { valid: '正常', expiring_soon: '临期', expired: '过期', unknown: '未识别' }
  return map[status] || status || '未知'
}

function statusTagType(status) {
  if (status === 'valid') return 'success'
  if (status === 'expiring_soon') return 'warning'
  if (status === 'expired') return 'danger'
  return 'default'
}

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function goToQuery(companyName) {
  router.push({ path: '/query', query: { keyword: companyName } })
}

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
  transition: transform 0.15s, box-shadow 0.15s;
}
.stat-card.active {
  transform: scale(0.95);
  box-shadow: inset 0 0 0 3px rgba(255,255,255,0.6);
}
@media (min-width: 480px) {
  .stat-card { flex: 1; min-width: 0; }
}
.stat-num { font-size: 28px; font-weight: 700; }
.stat-label { font-size: 12px; opacity: 0.9; margin-top: 4px; }
/* 临期 - 暖橙醒目 */
.stat-warning {
  background: linear-gradient(135deg, #ff7a00 0%, #ff9400 100%);
  box-shadow: 0 2px 8px rgba(255, 122, 0, 0.3);
}
/* 已过期 - 深红突出 */
.stat-danger {
  background: linear-gradient(135deg, #cf1322 0%, #ff4d4f 100%);
  box-shadow: 0 2px 8px rgba(207, 19, 34, 0.35);
}

/* 证照类型按钮栏 */
.doc-type-bar {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 16px;
  background: #fff;
  flex-wrap: wrap;
}
.doc-type-label {
  font-size: 12px;
  color: #969799;
  line-height: 30px;
  white-space: nowrap;
  flex-shrink: 0;
}
.doc-type-options {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.doc-type-btn {
  display: inline-block;
  padding: 4px 12px;
  font-size: 12px;
  border-radius: 14px;
  border: 1px solid #dcdee0;
  color: #646566;
  background: #fff;
  cursor: pointer;
  transition: all 0.15s;
  white-space: nowrap;
}
.doc-type-btn.active {
  background: #1989fa;
  color: #fff;
  border-color: #1989fa;
}
.doc-type-btn:active {
  opacity: 0.7;
}

/* 结果信息 */
.result-info {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 16px 8px;
  font-size: 12px;
}
.filter-result { color: #969799; }
.clear-filter {
  color: #1989fa;
  cursor: pointer;
}
.clear-filter:active { opacity: 0.7; }

/* 数据表格 */
.data-table {
  margin: 8px 16px;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}
.table-header {
  display: flex;
  align-items: center;
  padding: 10px 12px;
  background: #f5f6f8;
  font-size: 12px;
  font-weight: 600;
  color: #646566;
}
.table-row {
  display: flex;
  align-items: center;
  padding: 12px;
  border-bottom: 1px solid #f5f6f8;
  font-size: 13px;
  cursor: pointer;
}
.table-row:last-child { border-bottom: none; }
.table-row:active { background: #f5f6f8; }
.col-status { width: 60px; flex-shrink: 0; }
.col-type { width: 85px; flex-shrink: 0; font-size: 12px; color: #646566; }
.col-name { flex: 1; min-width: 0; padding: 0 8px; color: #323233; }
.col-expire { width: 110px; flex-shrink: 0; text-align: right; font-size: 12px; color: #969799; }
.days-remaining {
  display: inline-block;
  margin-left: 4px;
  padding: 1px 4px;
  border-radius: 3px;
  font-size: 11px;
  background: #e8fae8;
  color: #07c160;
}
.days-remaining.warning { background: #fff7e6; color: #ff976a; }
.days-remaining.danger { background: #ffeeed; color: #ee0a24; }

/* 分页 */
.pagination-wrapper {
  display: flex;
  justify-content: center;
  padding: 12px 16px;
}
.pagination-wrapper :deep(.van-pagination__item) {
  white-space: nowrap;
}

/* 证照类型分布 */
.section-title {
  font-size: 14px; font-weight: 600; color: #323233;
  padding: 16px 16px 8px;
}
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
.page-loading { display: flex; justify-content: center; padding: 40px; }
</style>
