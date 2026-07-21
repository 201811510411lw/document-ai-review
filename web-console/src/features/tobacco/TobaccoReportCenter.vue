<template>
  <section class="report-center" aria-label="核对报告中心">
    <header class="center-header">
      <div>
        <h1>比对报告</h1>
        <p>查看已完成的烟草证与营业执照核对结果。</p>
      </div>
      <van-button plain type="primary" size="small" icon="replay" :loading="loading" @click="$emit('reload')">
        刷新
      </van-button>
    </header>

    <div class="metrics" role="tablist" aria-label="报告状态筛选">
      <button
        v-for="metric in metrics"
        :key="metric.value"
        class="metric"
        :class="[{ active: filter === metric.value }, metric.tone]"
        type="button"
        @click="filter = metric.value"
      >
        <strong>{{ metric.count }}</strong>
        <span>{{ metric.label }}</span>
      </button>
    </div>

    <div class="search-panel"><van-search v-model="keyword" placeholder="搜索主体名称或门店编号" clearable aria-label="搜索比对报告" /></div>

    <div v-if="loading && !records.length" class="skeleton-list" aria-label="正在加载报告">
      <span v-for="item in 5" :key="item" class="skeleton-row"><i></i><i></i></span>
    </div>
    <van-empty v-else-if="!visibleRecords.length" image-size="72" description="暂无符合条件的比对报告" />

    <div v-else class="report-list">
      <article
        v-for="report in visibleRecords"
        :key="report.id"
        class="report-row"
        tabindex="0"
        role="button"
        @click="openReport(report.id)"
        @keydown.enter="openReport(report.id)"
      >
        <div class="report-row__main">
          <div class="report-row__name">{{ report.company_name || '未识别主体名称' }}</div>
          <div class="report-row__meta"><span>{{ modeLabel(report.review_mode) }}</span><span>{{ formatTime(report.compare_time || report.created_at) }}</span></div>
        </div>
        <div class="report-row__side">
          <van-tag :type="tagType(report.overall_result)" plain>{{ report.overall_result || '待校验' }}</van-tag>
          <span v-if="report.unmatched_fields?.length" class="issue-count">{{ report.unmatched_fields.length }} 项待处理</span>
          <van-icon name="arrow" color="#9ca8b5" />
        </div>
      </article>
    </div>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'

const props = defineProps({
  records: { type: Array, default: () => [] },
  loading: { type: Boolean, default: false },
})

defineEmits(['reload'])

const router = useRouter()
const keyword = ref('')
const filter = ref('')

const metrics = computed(() => [
  { label: '全部', value: '', count: props.records.length, tone: 'neutral' },
  { label: '通过', value: '通过', count: props.records.filter((item) => item.overall_result === '通过').length, tone: 'success' },
  { label: '待校验', value: '待校验', count: props.records.filter((item) => item.overall_result === '待校验').length, tone: 'warning' },
  { label: '不通过', value: '不通过', count: props.records.filter((item) => item.overall_result === '不通过').length, tone: 'danger' },
])

const visibleRecords = computed(() => {
  const term = keyword.value.trim().toLowerCase()
  return props.records.filter((record) => {
    const statusMatched = !filter.value || record.overall_result === filter.value
    const text = `${record.company_name || ''} ${record.store_code || ''}`.toLowerCase()
    return statusMatched && (!term || text.includes(term))
  })
})

function openReport(taskId) {
  router.push(`/tobacco/reports/${taskId}`)
}

function tagType(result) {
  return { '通过': 'success', '待校验': 'warning', '不通过': 'danger' }[result] || 'primary'
}

function modeLabel(mode) {
  return mode === 'store_in_store' ? '店中店' : '标准核对'
}

function formatTime(value) {
  if (!value) return '时间未知'
  return String(value).replace('T', ' ').slice(0, 16)
}
</script>

<style scoped>
.report-center { min-width: 0; color: var(--tobacco-ink); }
.center-header { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; padding: 8px 0 20px; }
.center-header h1 { margin: 0; color: var(--tobacco-ink); font-size: 25px; font-weight: 720; line-height: 1.2; letter-spacing: 0; }
.center-header p { margin: 7px 0 0; color: var(--tobacco-muted); font-size: 13px; }
.center-header :deep(.van-button) { border-color: var(--tobacco-line-strong); color: var(--tobacco-accent); border-radius: 6px; }
.metrics { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); overflow: hidden; margin: 0; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); }
.metric { position: relative; min-height: 82px; padding: 15px 16px; border: 0; border-right: 1px solid var(--tobacco-line); background: transparent; color: var(--tobacco-muted); text-align: left; transition: background-color .16s ease, color .16s ease; }
.metric:last-child { border-right: 0; }.metric::before { position: absolute; top: 0; right: 0; left: 0; height: 3px; background: transparent; content: ''; }
.metric strong { display: block; color: var(--tobacco-ink); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 25px; font-weight: 650; font-variant-numeric: tabular-nums; line-height: 1; }
.metric span { display: block; margin-top: 9px; font-size: 12px; }.metric:hover { background: var(--tobacco-surface-muted); }.metric:active { transform: translateY(1px); }
.metric.active { background: var(--tobacco-accent-soft); color: var(--tobacco-accent); }.metric.active::before { background: var(--tobacco-accent); }
.metric.success.active { background: #eff8f2; color: #237248; }.metric.success.active::before { background: #2f8b58; }
.metric.warning.active { background: #fff8e8; color: #8d611c; }.metric.warning.active::before { background: #b67b1d; }
.metric.danger.active { background: #fff3f1; color: #a6443d; }.metric.danger.active::before { background: #c2524b; }
.search-panel { margin: 16px 0 8px; overflow: hidden; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); }.search-panel :deep(.van-search) { padding: 7px 10px; background: transparent; }.search-panel :deep(.van-search__content) { border-radius: 5px; background: var(--tobacco-surface-muted); }.search-panel :deep(.van-field__control) { color: var(--tobacco-ink); font-size: 13px; }
.skeleton-list { display: grid; gap: 1px; overflow: hidden; margin-top: 14px; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-line); }.skeleton-row { display: flex; align-items: center; justify-content: space-between; gap: 24px; height: 70px; padding: 0 16px; background: var(--tobacco-surface); }.skeleton-row i { display: block; width: 38%; height: 12px; border-radius: 3px; background: #e9eff3; }.skeleton-row i:last-child { width: 13%; }
.report-list { overflow: hidden; margin-top: 14px; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); }
.report-row { display: flex; align-items: center; justify-content: space-between; gap: 18px; padding: 16px; border-bottom: 1px solid var(--tobacco-line); cursor: pointer; outline: 0; transition: background-color .16s ease; }.report-row:last-child { border-bottom: 0; }.report-row:hover, .report-row:focus-visible { background: var(--tobacco-surface-muted); }.report-row:focus-visible { box-shadow: inset 0 0 0 2px var(--tobacco-focus); }.report-row:active { transform: translateY(1px); }
.report-row__main { min-width: 0; }.report-row__name { overflow: hidden; color: var(--tobacco-ink); font-size: 15px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }.report-row__meta { display: flex; flex-wrap: wrap; gap: 14px; margin-top: 7px; color: var(--tobacco-muted); font-size: 12px; }.report-row__meta span + span { padding-left: 14px; border-left: 1px solid var(--tobacco-line-strong); }
.report-row__side { display: flex; flex: 0 0 auto; align-items: center; gap: 10px; }.report-row__side :deep(.van-tag) { border-radius: 4px; font-weight: 600; }.issue-count { color: #9b641d; font-size: 12px; white-space: nowrap; }
@media (max-width: 600px) { .center-header { padding-top: 2px; }.center-header h1 { font-size: 22px; }.center-header p { display: none; }.metrics { grid-template-columns: repeat(2, minmax(0, 1fr)); }.metric:nth-child(2) { border-right: 0; }.metric:nth-child(-n+2) { border-bottom: 1px solid var(--tobacco-line); }.report-row { align-items: flex-start; padding: 14px; }.report-row__side { align-items: flex-end; flex-direction: column; }.issue-count { max-width: 92px; text-align: right; white-space: normal; } }
</style>
