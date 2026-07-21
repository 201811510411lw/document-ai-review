<template>
  <section class="report-center">
    <!-- 统计筛选卡片 -->
    <div class="metrics" role="tablist" aria-label="审核结果筛选">
      <button
        v-for="m in metrics"
        :key="m.value"
        class="metric"
        :class="[{ active: filter === m.value }, m.tone]"
        type="button"
        @click="filter = m.value"
      >
        <strong>{{ m.count }}</strong>
        <span>{{ m.icon }} {{ m.label }}</span>
      </button>
    </div>

    <!-- 搜索 -->
    <div class="search-bar">
      <van-search
        v-model="keyword"
        placeholder="搜索主体名称或门店编号"
        clearable
        shape="round"
        aria-label="搜索比对报告"
      />
    </div>

    <!-- 加载骨架 -->
    <div v-if="loading && !records.length" class="skeleton-list">
      <span v-for="item in 5" :key="item" class="skeleton-row"><i></i><i></i></span>
    </div>

    <div v-else-if="!visibleRecords.length" class="empty-hint">
      <van-empty image-size="72" description="暂无符合条件的记录" />
    </div>

    <!-- 报告列表 -->
    <div v-else class="report-list">
      <article
        v-for="report in pagedRecords"
        :key="report.id"
        class="report-row"
        tabindex="0"
        role="button"
        @click="openReport(report.id)"
        @keydown.enter="openReport(report.id)"
      >
        <div class="report-row__left">
          <!-- 状态图标 -->
          <div class="status-icon" :class="resultMeta(report).tone">
            <van-icon :name="resultMeta(report).icon" :size="20" />
          </div>
          <div class="report-row__main">
            <div class="report-row__name">{{ report.company_name || '未识别主体名称' }}</div>
            <div class="report-row__meta">
              <span>{{ modeLabel(report.review_mode) }}</span>
              <span>{{ formatTime(report.compare_time || report.created_at) }}</span>
            </div>
            <!-- 驳回/异常时，显示失败原因摘要 -->
            <div v-if="report.overall_result !== '通过' && report.unmatched_fields?.length" class="report-row__issues">
              <van-icon name="warning-o" />
              <span>{{ report.unmatched_fields.slice(0, 2).join('、') }}</span>
              <span v-if="report.unmatched_fields.length > 2" class="more-issues">等 {{ report.unmatched_fields.length }} 项</span>
            </div>
          </div>
        </div>
        <div class="report-row__right">
          <van-tag :type="tagType(report.overall_result)" plain size="small">{{ statusLabel(report) }}</van-tag>
          <van-icon name="arrow" color="#c8c9cc" />
        </div>
      </article>
    </div>

    <!-- 分页 -->
    <div v-if="totalPages > 1" class="pagination-wrapper">
      <van-pagination
        v-model="currentPage"
        :page-count="totalPages"
        mode="simple"
        @change="scrollToTop"
      />
    </div>
  </section>
</template>

<script setup>
import { computed, ref, watch } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  records: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

defineEmits(['reload'])

const router = useRouter()
const keyword = ref('')
const filter = ref('')
const currentPage = ref(1)
const pageSize = 15

const metrics = computed(() => [
  { label: '全部', icon: '', value: '', count: props.records.length, tone: 'neutral' },
  {
    label: '自动通过',
    icon: '✅',
    value: '通过',
    count: props.records.filter((r) => r.overall_result === '通过').length,
    tone: 'success',
  },
  {
    label: '驳回',
    icon: '❌',
    value: '不通过',
    count: props.records.filter((r) => r.overall_result === '不通过').length,
    tone: 'danger',
  },
  {
    label: '异常待处理',
    icon: '⚠️',
    value: '待校验',
    count: props.records.filter((r) => r.overall_result === '待校验').length,
    tone: 'warning',
  },
])

const visibleRecords = computed(() => {
  const term = keyword.value.trim().toLowerCase()
  return props.records.filter((r) => {
    const statusMatched = !filter.value || r.overall_result === filter.value
    const text = `${r.company_name || ''} ${r.store_code || ''}`.toLowerCase()
    return statusMatched && (!term || text.includes(term))
  })
})

const totalPages = computed(() => Math.max(1, Math.ceil(visibleRecords.value.length / pageSize)))

const pagedRecords = computed(() => {
  const start = (currentPage.value - 1) * pageSize
  return visibleRecords.value.slice(start, start + pageSize)
})

// 筛选或搜索变化时重置到第一页
watch([filter, keyword], () => { currentPage.value = 1 })

function scrollToTop() {
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function resultMeta(report) {
  if (report.overall_result === '通过') return { icon: 'success', tone: 'pass', label: '自动通过' }
  if (report.overall_result === '不通过') return { icon: 'cross', tone: 'reject', label: '驳回' }
  return { icon: 'warning', tone: 'exception', label: '异常待处理' }
}

function statusLabel(report) {
  if (report.overall_result === '通过') return '自动通过'
  if (report.overall_result === '不通过') return '驳回'
  return '异常待处理'
}

function tagType(result) {
  if (result === '通过') return 'success'
  if (result === '不通过') return 'danger'
  return 'warning'
}

function modeLabel(mode) {
  return mode === 'store_in_store' ? '店中店核对' : '标准核对'
}

function formatTime(value) {
  if (!value) return '时间未知'
  return String(value).replace('T', ' ').slice(0, 16)
}

function openReport(taskId) {
  router.push(`/tobacco/reports/${taskId}`)
}
</script>

<style scoped>
.report-center { color: #323233; }

/* 统计卡片 */
.metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; margin-bottom: 12px; }
.metric { display: flex; flex-direction: column; align-items: center; gap: 4px; padding: 14px 8px; border: 1px solid #ebedf0; border-radius: 8px; background: #fff; cursor: pointer; transition: all .15s; }
.metric:active { transform: scale(.96); }
.metric strong { font-size: 24px; font-weight: 700; font-variant-numeric: tabular-nums; line-height: 1.2; color: #323233; }
.metric span { font-size: 12px; color: #969799; }
.metric.active { border-color: #1989fa; background: #ecf5ff; }
.metric.active strong { color: #1989fa; }
.metric.active span { color: #1989fa; }
.metric.success.active { border-color: #07c160; background: #e8fae8; }
.metric.success.active strong { color: #07c160; }
.metric.success.active span { color: #07c160; }
.metric.danger.active { border-color: #ee0a24; background: #fff1f0; }
.metric.danger.active strong { color: #ee0a24; }
.metric.danger.active span { color: #ee0a24; }
.metric.warning.active { border-color: #ff976a; background: #fff7e6; }
.metric.warning.active strong { color: #ff7d00; }
.metric.warning.active span { color: #ff7d00; }

/* 搜索 */
.search-bar { margin-bottom: 8px; }
.search-bar :deep(.van-search) { padding: 8px 0; }
.search-bar :deep(.van-search__content) { border-radius: 18px; background: #fff; border: 1px solid #ebedf0; }

/* 骨架 */
.skeleton-list { display: flex; flex-direction: column; gap: 1px; overflow: hidden; border: 1px solid #ebedf0; border-radius: 8px; background: #ebedf0; }
.skeleton-row { display: flex; align-items: center; justify-content: space-between; height: 68px; padding: 0 16px; background: #fff; }
.skeleton-row i { display: block; width: 35%; height: 12px; border-radius: 3px; background: #f2f3f5; }
.skeleton-row i:last-child { width: 12%; }

/* 报告列表 */
.report-list { overflow: hidden; border: 1px solid #ebedf0; border-radius: 8px; background: #fff; }
.report-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; border-bottom: 1px solid #f2f3f5; cursor: pointer; outline: 0; transition: background .15s; }
.report-row:last-child { border-bottom: 0; }
.report-row:hover { background: #f7f8fa; }
.report-row:active { transform: translateY(1px); }

.report-row__left { display: flex; align-items: flex-start; gap: 12px; min-width: 0; flex: 1; }
.status-icon { flex-shrink: 0; width: 36px; height: 36px; display: flex; align-items: center; justify-content: center; border-radius: 50%; }
.status-icon.pass { background: #e8fae8; color: #07c160; }
.status-icon.reject { background: #fff1f0; color: #ee0a24; }
.status-icon.exception { background: #fff7e6; color: #ff7d00; }

.report-row__main { min-width: 0; flex: 1; }
.report-row__name { overflow: hidden; color: #323233; font-size: 15px; font-weight: 600; text-overflow: ellipsis; white-space: nowrap; }
.report-row__meta { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 5px; color: #969799; font-size: 12px; }
.report-row__meta span + span { padding-left: 10px; border-left: 1px solid #ebedf0; }
.report-row__issues { display: flex; align-items: center; gap: 4px; margin-top: 6px; font-size: 12px; color: #ee0a24; }
.report-row__issues .van-icon { flex-shrink: 0; }
.report-row__issues span { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.report-row__issues .more-issues { color: #969799; flex-shrink: 0; }

.report-row__right { display: flex; flex-shrink: 0; align-items: center; gap: 8px; }
.report-row__right :deep(.van-tag) { border-radius: 4px; font-weight: 600; }

/* 分页 */
.pagination-wrapper { display: flex; justify-content: center; padding: 16px 0 4px; }
.pagination-wrapper :deep(.van-pagination__item) { white-space: nowrap; }

@media (max-width: 600px) {
  .metrics { grid-template-columns: repeat(2, 1fr); }
  .report-row__issues { font-size: 11px; }
}
</style>
