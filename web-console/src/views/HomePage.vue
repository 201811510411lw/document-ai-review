<template>
  <div class="workbench-home">
    <header class="overview-heading">
      <div>
        <span class="eyebrow">证照审核工作台</span>
        <h1>{{ greeting }}，{{ userName }}</h1>
        <p>集中查看证照状态、待复核任务和审核结果。</p>
      </div>
      <button class="primary-action" type="button" @click="openPrimaryAction">
        <van-icon :name="isAdmin ? 'plus' : 'search'" />
        <span>{{ isAdmin ? '发起新审核' : '查询证照' }}</span>
      </button>
    </header>

    <section class="metric-grid" aria-label="审核概览">
      <article
        v-for="(metric, index) in overview.metrics"
        :key="metric.label"
        :class="['metric-item', `tone-${metric.tone}`, { 'desktop-only': index === 3 }]"
      >
        <span>{{ metric.label }}</span>
        <strong>{{ loading || metricUnavailable(metric.tone) ? '--' : metric.value }}</strong>
        <small>{{ metricHint(metric.tone) }}</small>
      </article>
    </section>

    <div class="workbench-grid">
      <section class="panel task-panel">
        <div class="panel-heading">
          <div>
            <h2>{{ isAdmin ? '待处理审核队列' : '证照状态概览' }}</h2>
            <p>{{ isAdmin ? '优先处理需要人工判断的审核任务' : '查看当前证照有效期与异常情况' }}</p>
          </div>
          <button type="button" class="text-action" @click="router.push(isAdmin ? '/review' : '/query')">
            {{ isAdmin ? '查看全部' : '进入查询' }}
            <van-icon name="arrow" />
          </button>
        </div>

        <div v-if="loading" class="task-loading" aria-label="正在加载">
          <div v-for="item in 5" :key="item" />
        </div>

        <template v-else-if="overview.tasks.length">
          <div class="task-table-head" role="row">
            <span>审核对象</span>
            <span>材料类型</span>
            <span>核验情况</span>
            <span>更新时间</span>
            <span>操作</span>
          </div>
          <article
            v-for="task in overview.tasks"
            :key="task.id"
            class="task-row"
            tabindex="0"
            @click="openTask(task.id)"
            @keydown.enter="openTask(task.id)"
          >
            <div class="task-subject">
              <span class="document-mark" aria-hidden="true"><van-icon name="description" /></span>
              <div>
                <strong>{{ task.title }}</strong>
                <small>{{ task.identifier }}</small>
              </div>
            </div>
            <span class="task-type">{{ formatDocumentType(task.documentType) }}</span>
            <div class="task-result">
              <span :class="['status-label', `status-${task.status}`]">{{ task.statusLabel }}</span>
              <small v-if="task.matchRatio !== '-'">匹配率 {{ task.matchRatio }}</small>
            </div>
            <time>{{ formatTime(task.updatedAt) }}</time>
            <button type="button" class="row-action" @click.stop="openTask(task.id)">查看</button>
          </article>
        </template>

        <div v-else class="task-empty">
          <van-icon :name="taskLoadError ? 'warning-o' : 'passed'" />
          <strong>{{ taskLoadError ? '数据加载失败' : isAdmin ? '当前没有审核任务' : '证照数据已准备就绪' }}</strong>
          <p>{{ taskLoadError ? '请稍后刷新页面重试' : isAdmin ? '新任务发起后会显示在这里' : '可通过证照查询或效期看板继续工作' }}</p>
        </div>
      </section>

      <aside class="side-column">
        <section class="panel distribution-panel">
          <div class="panel-heading compact">
            <div>
              <h2>审核结果分布</h2>
              <p>当前数据状态</p>
            </div>
            <button type="button" class="text-action" @click="router.push('/dashboard')">查看看板</button>
          </div>
          <div class="distribution-body">
            <div class="distribution-total">
              <strong>{{ loading ? '--' : overview.distributionTotal }}</strong>
              <span>记录总数</span>
            </div>
            <ul>
              <li v-for="item in overview.distribution" :key="item.label">
                <span><i :class="`dot-${item.tone}`" />{{ item.label }}</span>
                <strong>{{ item.value }}</strong>
              </li>
            </ul>
          </div>
        </section>

        <section class="panel quick-panel">
          <div class="panel-heading compact">
            <div>
              <h2>快捷入口</h2>
              <p>常用审核场景</p>
            </div>
          </div>
          <div class="quick-grid">
            <button v-for="item in quickEntries" :key="item.path" type="button" @click="router.push(item.path)">
              <van-icon :name="item.icon" />
              <span><strong>{{ item.label }}</strong><small>{{ item.description }}</small></span>
            </button>
          </div>
        </section>
      </aside>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { dashboardApi, reviewApi, tobaccoApi } from '@/api'
import { useUserStore } from '@/store/user'
import { buildWorkbenchOverview } from '@/features/workbench/overview'

const router = useRouter()
const userStore = useUserStore()
const loading = ref(true)
const dashboardError = ref(false)
const reviewError = ref(false)
const dashboardStats = ref({})
const reviewResponse = ref({ records: [], stats: {} })
const tobaccoStats = ref({})

const isAdmin = computed(() => userStore.isAdmin)
const userName = computed(() => userStore.user?.name || userStore.user?.username || '用户')
const greeting = computed(() => {
  const hour = new Date().getHours()
  if (hour < 11) return '上午好'
  if (hour < 14) return '中午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})
const overview = computed(() => buildWorkbenchOverview({
  dashboardStats: dashboardStats.value,
  reviewResponse: reviewResponse.value,
}))
const taskLoadError = computed(() => isAdmin.value ? reviewError.value : dashboardError.value)
const tobaccoSummary = computed(() => {
  const stats = tobaccoStats.value
  if (!Object.keys(stats).length) return '营业执照与烟草证'
  return `通过 ${stats.passed || 0} · 待处理 ${stats.pending || 0} · 不通过 ${stats.failed || 0}`
})

const quickEntries = computed(() => {
  const entries = isAdmin.value
    ? [
        { label: '营业执照审核', description: '主体、期限、登记状态', icon: 'certificate', path: '/review?document_type=business_license' },
        { label: '食品证照审核', description: '许可范围与有效期', icon: 'records-o', path: '/review?document_type=food_license' },
        { label: '商品报告审核', description: '报告、结论与效期', icon: 'orders-o', path: '/review?document_type=product_report' },
        { label: '烟草证一致性', description: tobaccoSummary.value, icon: 'balance-list', path: '/tobacco/reports' },
      ]
    : [
        { label: '证照查询', description: '按企业名称或编码', icon: 'search', path: '/query' },
        { label: '效期看板', description: '查看临期与过期记录', icon: 'bar-chart-o', path: '/dashboard' },
        { label: '烟草证一致性', description: tobaccoSummary.value, icon: 'balance-list', path: '/tobacco/reports' },
      ]
  return entries
})

onMounted(loadOverview)

async function loadOverview() {
  loading.value = true
  dashboardError.value = false
  reviewError.value = false
  const [dashboardResult, reviewResult, tobaccoResult] = await Promise.allSettled([
    dashboardApi.stats(),
    isAdmin.value ? reviewApi.list({ limit: 5 }) : Promise.resolve(null),
    tobaccoApi.list({ limit: 1 }),
  ])
  if (dashboardResult.status === 'fulfilled') {
    dashboardStats.value = dashboardResult.value?.data || dashboardResult.value || {}
  } else {
    dashboardError.value = true
  }
  if (reviewResult.status === 'fulfilled' && reviewResult.value) {
    reviewResponse.value = reviewResult.value
  } else if (isAdmin.value) {
    reviewError.value = true
  }
  if (tobaccoResult.status === 'fulfilled') tobaccoStats.value = tobaccoResult.value?.stats || {}
  loading.value = false
}

function metricHint(tone) {
  return {
    primary: '当前库存',
    pending: '需要人工处理',
    flagged: '需重点关注',
    confirmed: '状态正常',
  }[tone] || ''
}

function metricUnavailable(tone) {
  return dashboardError.value && (tone === 'primary' || tone === 'confirmed')
}

function formatDocumentType(value) {
  const labels = {
    business_license: '营业执照',
    food_license: '食品经营许可',
    food_production_license: '食品生产许可',
    product_report: '商品报告',
    batch_report: '批次报告',
  }
  return labels[value] || value || '-'
}

function formatTime(value) {
  if (!value || value === '-') return '-'
  return String(value).replace('T', ' ').slice(0, 16)
}

function openPrimaryAction() {
  router.push(isAdmin.value ? '/review' : '/query')
}

function openTask(id) {
  router.push(`/review/${id}`)
}
</script>

<style scoped>
.workbench-home {
  width: min(100% - 48px, 1280px);
  margin: 0 auto;
  padding: 28px 0 36px;
  color: #172033;
}

.overview-heading {
  display: flex;
  align-items: flex-end;
  justify-content: space-between;
  gap: 28px;
  margin-bottom: 18px;
}
.eyebrow { color: #4168e8; font-size: 12px; font-weight: 650; }
.overview-heading h1 { margin: 5px 0 3px; font-size: 26px; line-height: 1.3; }
.overview-heading p, .panel-heading p { margin: 0; color: #7d889d; font-size: 12px; }
.primary-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  height: 40px;
  padding: 0 18px;
  border: 0;
  border-radius: 6px;
  color: #fff;
  background: #3564eb;
  box-shadow: 0 6px 16px rgba(53, 100, 235, 0.18);
  font: inherit;
  font-size: 13px;
  font-weight: 650;
  cursor: pointer;
}

.metric-grid { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 14px; margin-bottom: 18px; }
.metric-item {
  position: relative;
  overflow: hidden;
  min-height: 118px;
  padding: 20px;
  border: 1px solid #e1e6ee;
  border-radius: 8px;
  background: #fff;
}
.metric-item::after { position: absolute; top: 0; right: 0; width: 52px; height: 52px; border-radius: 0 0 0 38px; background: #edf2ff; content: ''; }
.metric-item.tone-pending::after { background: #fff4d8; }
.metric-item.tone-flagged::after { background: #feebec; }
.metric-item.tone-confirmed::after { background: #e6f6ee; }
.metric-item > span { display: block; color: #7a879c; font-size: 12px; }
.metric-item > strong { display: block; margin: 14px 0 6px; font-size: 27px; line-height: 1; font-variant-numeric: tabular-nums; }
.metric-item > small { color: #8c97aa; font-size: 11px; }
.tone-pending > small { color: #aa6d00; }.tone-flagged > small { color: #c43b47; }.tone-confirmed > small { color: #24835c; }

.workbench-grid { display: grid; grid-template-columns: minmax(0, 1fr) 354px; gap: 16px; align-items: start; }
.panel { overflow: hidden; border: 1px solid #dfe4ec; border-radius: 8px; background: #fff; }
.panel-heading { display: flex; align-items: center; justify-content: space-between; gap: 20px; min-height: 70px; padding: 14px 20px; border-bottom: 1px solid #e5e9f0; }
.panel-heading.compact { min-height: 64px; }
.panel-heading h2 { margin: 0 0 3px; font-size: 16px; }
.text-action, .row-action { border: 0; color: #315ee3; background: transparent; font: inherit; font-size: 12px; font-weight: 600; cursor: pointer; }
.text-action { display: inline-flex; align-items: center; gap: 3px; white-space: nowrap; }

.task-table-head, .task-row { display: grid; grid-template-columns: minmax(220px, 1.6fr) minmax(110px, .8fr) minmax(120px, .8fr) 118px 42px; gap: 16px; align-items: center; }
.task-table-head { min-height: 42px; padding: 0 20px; color: #7c8799; background: #f7f8fa; font-size: 11px; }
.task-row { min-height: 74px; padding: 11px 20px; border-top: 1px solid #edf0f4; cursor: pointer; }
.task-row:hover { background: #fafbfc; }
.task-subject { display: flex; align-items: center; gap: 10px; min-width: 0; }
.document-mark { display: grid; width: 30px; height: 36px; flex: 0 0 30px; place-items: center; border: 1px solid #dbe2ed; border-radius: 5px; color: #91a0b5; background: #f8fafc; }
.task-subject div { min-width: 0; }
.task-subject strong { display: block; overflow: hidden; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }
.task-subject small, .task-result small { display: block; margin-top: 3px; color: #8994a6; font-size: 10px; }
.task-type, .task-row time { color: #5f6b7e; font-size: 11px; }
.status-label { display: inline-block; padding: 4px 8px; border-radius: 10px; font-size: 10px; font-weight: 650; }
.status-pending { color: #a76500; background: #fff3d5; }.status-flagged { color: #bf3341; background: #fdebed; }.status-confirmed { color: #197552; background: #e6f6ef; }.status-default { color: #596579; background: #edf0f4; }
.task-loading { padding: 0 20px; }.task-loading div { height: 74px; border-bottom: 1px solid #edf0f4; background: #f6f7f9; }
.task-empty { display: flex; min-height: 320px; align-items: center; justify-content: center; flex-direction: column; color: #8b96a8; text-align: center; }
.task-empty > .van-icon { margin-bottom: 10px; color: #6c84d9; font-size: 27px; }.task-empty strong { color: #465166; font-size: 14px; }.task-empty p { margin: 5px 0 0; font-size: 11px; }

.side-column { display: grid; gap: 16px; }
.distribution-body { display: grid; grid-template-columns: 124px 1fr; gap: 20px; align-items: center; min-height: 154px; padding: 18px 20px; }
.distribution-total { display: flex; width: 112px; height: 112px; align-items: center; justify-content: center; flex-direction: column; border: 16px solid #3564eb; border-right-color: #f1ad22; border-bottom-color: #ed5a62; border-radius: 50%; }
.distribution-total strong { font-size: 21px; }.distribution-total span { color: #8a95a7; font-size: 10px; }
.distribution-body ul { display: grid; gap: 10px; margin: 0; padding: 0; list-style: none; }
.distribution-body li { display: flex; align-items: center; justify-content: space-between; gap: 12px; color: #687489; font-size: 11px; }
.distribution-body li span { display: inline-flex; align-items: center; gap: 7px; }.distribution-body li i { width: 7px; height: 7px; border-radius: 2px; background: #c9d0db; }
.distribution-body li i.dot-confirmed { background: #3564eb; }.distribution-body li i.dot-pending { background: #f0ad24; }.distribution-body li i.dot-flagged { background: #ed5a62; }
.quick-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px; padding: 16px; }
.quick-grid button { display: flex; min-height: 84px; align-items: flex-start; gap: 9px; padding: 12px; border: 1px solid #e1e6ee; border-radius: 7px; color: #1d2940; background: #fbfcfe; text-align: left; font: inherit; cursor: pointer; }
.quick-grid button:hover { border-color: #b6c5ef; background: #f7f9ff; }.quick-grid .van-icon { display: grid; width: 28px; height: 28px; flex: 0 0 28px; place-items: center; border-radius: 5px; color: #3564eb; background: #eaf0ff; font-size: 16px; }
.quick-grid strong, .quick-grid small { display: block; }.quick-grid strong { margin: 2px 0 5px; font-size: 12px; }.quick-grid small { color: #8a95a7; font-size: 10px; line-height: 1.5; }

@media (max-width: 1080px) {
  .workbench-grid { grid-template-columns: 1fr; }
  .side-column { grid-template-columns: 1fr 1fr; }
}

@media (max-width: 640px) {
  .workbench-home { width: 100%; padding: 18px 14px 28px; }
  .overview-heading { align-items: center; margin-bottom: 14px; }
  .eyebrow, .overview-heading p { display: none; }
  .overview-heading h1 { margin: 0; font-size: 20px; }
  .primary-action { width: 42px; height: 42px; padding: 0; border-radius: 7px; font-size: 20px; }
  .primary-action span { display: none; }
  .metric-grid { grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; margin-bottom: 16px; }
  .metric-item { min-height: 104px; padding: 15px 11px; }
  .metric-item::after { width: 34px; height: 34px; }
  .metric-item > strong { margin: 13px 0 5px; font-size: 22px; }
  .metric-item > small { font-size: 9px; }
  .desktop-only { display: none; }
  .panel { border-radius: 7px; }
  .panel-heading { min-height: 58px; padding: 11px 13px; }
  .panel-heading h2 { font-size: 15px; }
  .panel-heading p { display: none; }
  .task-table-head { display: none; }
  .task-row { display: grid; grid-template-columns: 1fr auto; gap: 10px; min-height: 132px; margin-top: 10px; padding: 13px; border: 1px solid #e3e7ed; border-radius: 7px; }
  .task-row:first-of-type { margin-top: 0; }
  .task-panel { overflow: visible; border: 0; background: transparent; }
  .task-panel > .panel-heading { padding-right: 2px; padding-left: 2px; border-bottom: 0; }
  .task-subject { grid-column: 1; }.task-result { grid-column: 2; grid-row: 1; align-self: start; text-align: right; }
  .task-type { grid-column: 1; }.task-row time { grid-column: 1; }.row-action { grid-column: 2; grid-row: 3; }
  .task-result small { margin-top: 6px; }
  .task-empty { min-height: 190px; border: 1px solid #e1e6ee; border-radius: 7px; background: #fff; }
  .side-column { grid-template-columns: 1fr; }
  .distribution-panel { display: none; }
  .quick-grid { padding: 12px; }
}
</style>
