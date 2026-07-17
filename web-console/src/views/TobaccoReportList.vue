<template>
  <div class="tobacco-page">
    <van-nav-bar title="烟草证比对报告" left-arrow @click-left="router.push('/home')" />

    <!-- ========== 路径A：日常浏览 ========== -->

    <!-- 统计 -->
    <div class="stats-row">
      <div class="stat-card" @click="filterResult = ''">
        <div class="stat-num">{{ stats.total || 0 }}</div>
        <div class="stat-label"><span>全部</span><button class="stat-help" @click.stop="showFilterHelp('all')">!</button></div>
      </div>
      <div class="stat-card success" @click="filterResult = '通过'">
        <div class="stat-num">{{ stats.passed || 0 }}</div>
        <div class="stat-label"><span>通过</span><button class="stat-help" @click.stop="showFilterHelp('passed')">!</button></div>
      </div>
      <div class="stat-card danger" @click="filterResult = '不通过'">
        <div class="stat-num">{{ stats.failed || 0 }}</div>
        <div class="stat-label"><span>不通过</span><button class="stat-help" @click.stop="showFilterHelp('failed')">!</button></div>
      </div>
      <div class="stat-card warning" @click="filterResult = '待校验'">
        <div class="stat-num">{{ stats.pending || 0 }}</div>
        <div class="stat-label"><span>待校验</span><button class="stat-help" @click.stop="showFilterHelp('pending')">!</button></div>
      </div>
    </div>
    <div class="filter-hint">{{ filterHint }}</div>

    <!-- 搜索 -->
    <van-search
      v-model="keyword"
      placeholder="搜索报告或待处理申请"
      shape="round"
      clearable
      @search="loadList"
    />

    <div class="pending-shortcut">
      <van-button plain type="primary" icon="records" block @click="openPendingQueue">
        待处理申请<span v-if="pendingStores.length">（{{ pendingStores.length }}）</span>
      </van-button>
    </div>

    <!-- 列表 -->
    <div v-if="visibleRecords.length" class="report-list">
      <div
        v-for="r in visibleRecords"
        :key="r.id"
        class="report-card"
        @click="router.push(`/tobacco/reports/${r.id}`)"
      >
        <div class="card-top">
          <span class="company-name">{{ r.company_name }}</span>
          <van-tag :type="resultTagType(r.overall_result)" size="small">
            {{ r.overall_result }}
          </van-tag>
        </div>
        <div class="card-detail">
          <span>比对时间: {{ r.compare_time || r.created_at?.slice(0, 10) || '-' }}</span>
        </div>
        <div v-if="r.unmatched_fields && r.unmatched_fields.length" class="card-warning">
          <van-icon name="cross-circle-o" color="#ee0a24" />
          <span>{{ r.unmatched_fields.length }} 个字段不匹配</span>
        </div>
      </div>
    </div>

    <van-empty v-else-if="!loading" description="暂无比对报告" />
    <van-loading v-if="loading && !records.length" class="page-loading" size="24">加载中...</van-loading>

    <!-- ========== 路径B：待处理申请 ========== -->

    <div ref="pendingSection" class="new-comp-section">
      <div class="new-comp-header" @click="toggleSection">
        <div class="new-comp-header-left">
          <span class="new-comp-icon" :class="{ rotated: showComparisonForm }">
            <van-icon name="add" size="16" />
          </span>
          <span class="new-comp-title">待处理申请</span>
        </div>
        <div class="new-comp-header-right">
          <span v-if="!showComparisonForm" class="new-comp-hint">处理 OA 新提交材料</span>
          <van-icon :name="showComparisonForm ? 'arrow-up' : 'arrow-down'" color="#c8c9cc" size="14" />
        </div>
      </div>

      <div v-if="showComparisonForm" class="comp-form-body">

        <!-- ── Phase 1a: 待处理列表 ── -->
        <template v-if="!selectedStore">

          <!-- 加载中 -->
          <div v-if="pendingLoading" class="comp-phase">
            <van-loading size="20" class="comp-loading">加载待处理门店...</van-loading>
          </div>

          <!-- 加载失败（API 未就绪）—— 直接退回到手动搜索 -->
          <div v-else-if="pendingError" class="comp-phase">
            <div class="comp-phase-empty">
              <van-icon name="info-o" size="40" color="#dcdee0" />
              <p class="comp-empty-text">暂无法获取待处理列表</p>
              <p class="comp-empty-hint">{{ pendingError }}</p>
            </div>
            <ManualSearch
              :storeIdentifier="storeIdentifier"
              :sourceLoading="sourceLoading"
              :sourceError="sourceError"
              :sourceQueried="sourceQueried"
              :sourceDocuments="sourceDocuments"
              :activeFilePath="activeFilePath"
              :comparing="comparing"
              @update:storeIdentifier="storeIdentifier = $event"
              @fetch="fetchSourceFiles"
              @preview="previewFile"
              @download="downloadFile"
              @trigger="triggerComparison"
            />
          </div>

          <!-- 有待处理门店 -->
          <div v-else-if="pendingStores.length" class="comp-phase">
            <div class="pending-header">
              <div class="pending-header__title">
                <van-icon name="records" color="#1989fa" />
                <span>OA 待处理申请（{{ filteredPendingStores.length }}/{{ pendingStores.length }} 条）</span>
              </div>
              <div class="pending-header__actions">
                <button class="pending-select-all" @click.stop="toggleSelectAllPending">
                  {{ allFilteredPendingSelected ? '取消全选' : '全选' }}
                </button>
                <van-button size="small" type="primary" icon="balance-list" :loading="batching" :disabled="!selectedPendingStoreCodes.length" @click.stop="runBatchComparison">批量核对（{{ selectedPendingStoreCodes.length }}）</van-button>
              </div>
            </div>
            <van-notice-bar v-if="batchSummary" class="batch-summary" :color="batchSummary.failed ? '#c83b32' : '#1989fa'" :background="batchSummary.failed ? '#fff5f4' : '#f0f9ff'" left-icon="info-o">最近一次批量核对：完成 {{ batchSummary.completed }} 条，失败 {{ batchSummary.failed }} 条</van-notice-bar>
            <van-checkbox-group v-model="selectedPendingStoreCodes">
              <div
                v-for="store in filteredPendingStores"
                :key="store.store_code"
                class="pending-item"
                @click="selectPendingStore(store)"
              >
                <div class="pending-item-left" @click.stop>
                  <van-checkbox :name="pendingStoreKey(store)" />
                </div>
                <div class="pending-item-body">
                  <div class="pending-item-name">{{ store.store_name || store.store_code }}</div>
                  <div class="pending-item-title">{{ store.request_name || store.summary_title || 'OA 烟草证申请' }}</div>
                  <div v-if="store.content_summary" class="pending-item-content">{{ store.content_summary }}</div>
                  <div class="pending-item-meta">门店编码: {{ store.store_code || '-' }} · 提交时间: {{ store.submit_date || '-' }} · 流程 {{ store.requestid || '-' }}</div>
                </div>
                <van-icon name="arrow" color="#c8c9cc" />
              </div>
            </van-checkbox-group>
            <van-empty v-if="!filteredPendingStores.length" image-size="56" description="未找到匹配的待处理申请" />
            <div v-else-if="pendingHasMore" class="pending-load-more">
              <van-button size="small" plain type="primary" :loading="pendingMoreLoading" @click="loadMorePendingStores">加载更多申请</van-button>
            </div>

            <!-- 手动搜索兜底 -->
            <div class="manual-search-divider">
              <span class="divider-line"></span>
              <span class="divider-text">或者手动搜索</span>
              <span class="divider-line"></span>
            </div>
            <div class="manual-search-trigger" @click.stop="showManualSearch = !showManualSearch">
              <van-icon :name="showManualSearch ? 'arrow-down' : 'search'" color="#1989fa" />
              <span>{{ showManualSearch ? '收起搜索' : '按门店编号或公司名称搜索' }}</span>
            </div>
            <div v-if="showManualSearch" class="manual-search-body">
              <ManualSearch
                :storeIdentifier="storeIdentifier"
                :sourceLoading="sourceLoading"
                :sourceError="sourceError"
                :sourceQueried="sourceQueried"
                :sourceDocuments="sourceDocuments"
                :activeFilePath="activeFilePath"
                :comparing="comparing"
                @update:storeIdentifier="storeIdentifier = $event"
                @fetch="fetchSourceFiles"
                @preview="previewFile"
                @download="downloadFile"
                @trigger="triggerComparison"
              />
            </div>
          </div>

          <!-- 无待处理 -->
          <div v-else class="comp-phase">
            <div class="comp-phase-empty">
              <van-icon name="smile-o" size="44" color="#07c160" />
              <p class="comp-empty-text">暂无待处理的烟草证新提交</p>
              <p class="comp-empty-hint">有新的 OA 提交流程时会自动出现在这里</p>
            </div>
            <div class="manual-search-divider">
              <span class="divider-line"></span>
              <span class="divider-text">手动搜索</span>
              <span class="divider-line"></span>
            </div>
            <ManualSearch
              :storeIdentifier="storeIdentifier"
              :sourceLoading="sourceLoading"
              :sourceError="sourceError"
              :sourceQueried="sourceQueried"
              :sourceDocuments="sourceDocuments"
              :activeFilePath="activeFilePath"
              :comparing="comparing"
              @update:storeIdentifier="storeIdentifier = $event"
              @fetch="fetchSourceFiles"
              @preview="previewFile"
              @download="downloadFile"
              @trigger="triggerComparison"
            />
          </div>
        </template>

        <!-- ── Phase 2: 已选门店，展示文件 ── -->
        <template v-else>
          <!-- 返回 -->
          <div class="comp-back" @click="clearSelectedStore">
            <van-icon name="arrow-left" />
            <span>返回待处理列表</span>
          </div>

          <!-- 门店信息 -->
          <div class="selected-store-info">
            <div class="selected-store-name">{{ selectedStore.store_name || selectedStore.store_code }}</div>
            <div class="selected-store-meta">
              提交时间: {{ selectedStore.submit_date || '-' }} · 流程 {{ selectedStore.requestid || '-' }}
            </div>
          </div>

          <!-- 来源文件 -->
          <div v-if="sourceLoading" class="comp-phase">
            <van-loading size="20" class="comp-loading">加载来源文件...</van-loading>
          </div>
          <div v-else-if="sourceError" class="comp-phase">
            <div class="comp-phase-empty">
              <van-icon name="info-o" size="36" color="#ff976a" />
              <p class="comp-empty-text" style="font-size:13px">无法获取来源文件</p>
              <p class="comp-empty-hint">{{ sourceError }}</p>
            </div>
            <div class="comp-action-bar">
              <van-button
                type="primary"
                block
                round
                :loading="comparing"
                icon="balance-list"
                @click="triggerComparison"
              >开始自动核对</van-button>
              <p class="comp-action-hint">来源附件不可用时将转人工复核</p>
            </div>
          </div>
          <div v-else-if="sourceDocuments.length" class="source-documents">
            <div class="source-files-label">来源文件（共 {{ fileCount }} 个）</div>
            <article v-for="document in sourceDocuments" :key="documentKey(document)" class="source-document">
              <div class="source-document__header">
                <div>
                  <div class="source-document__title">{{ document.source.store_name || document.source.store_code || selectedStore.store_code }}</div>
                  <div class="source-document__meta">
                    流程 {{ document.source.requestid || '-' }} · 附件 {{ document.source.docid || '-' }}
                  </div>
                </div>
                <van-tag plain type="primary">{{ document.files.length }} 个文件</van-tag>
              </div>

              <div class="source-file-list">
                <div v-for="file in document.files" :key="file.relative_path" class="source-file">
                  <div class="source-file__body">
                    <div class="source-file__name">
                      <van-icon :name="fileIcon(file)" size="14" color="#1989fa" />
                      {{ file.file_name }}
                    </div>
                    <div class="source-file__meta">{{ formatFileSize(file.file_size) }}<span v-if="file.content_type"> · {{ file.content_type }}</span></div>
                  </div>
                  <div class="source-file__actions">
                    <van-button size="small" plain type="primary" :loading="activeFilePath === file.relative_path" @click="previewFile(file)">预览</van-button>
                    <van-button size="small" plain :loading="activeFilePath === file.relative_path" @click="downloadFile(file)">下载</van-button>
                  </div>
                </div>
              </div>
            </article>

            <van-cell-group inset title="自动核对" class="comparison-inputs">
              <van-cell title="处理方式" value="自动抽取附件并执行规则" />
              <van-cell
                title="人工复核补充"
                :value="showManualCorrection ? '收起' : '仅识别异常时填写'"
                is-link
                @click="showManualCorrection = !showManualCorrection"
              />
              <template v-if="showManualCorrection">
              <van-cell title="审核模式">
                <template #value>
                  <van-radio-group v-model="reviewMode" direction="horizontal">
                    <van-radio name="standard">标准</van-radio>
                    <van-radio name="store_in_store">店中店</van-radio>
                  </van-radio-group>
                </template>
              </van-cell>
              <van-field v-model="businessFields.subject_name" label="持证主体" placeholder="营业执照主体名称" />
              <van-field v-model="businessFields.business_address" label="执照地址" placeholder="营业执照经营地址" />
              <van-field v-model="businessFields.legal_person" label="执照负责人" placeholder="营业执照负责人" />
              <van-field v-model="tobaccoFields.subject_name" label="烟草证主体" placeholder="烟草证主体名称" />
              <van-field v-model="tobaccoFields.business_address" label="烟草证地址" placeholder="烟草证经营地址" />
              <van-field v-model="tobaccoFields.legal_person" label="烟草证负责人" placeholder="烟草证负责人" />
              <van-field v-model="tobaccoFields.valid_to" label="有效截止日" placeholder="YYYY-MM-DD，空值按长期有效" />
              <template v-if="reviewMode === 'store_in_store'">
                <van-field v-model="relationship.document_id" label="关系凭证文件" placeholder="从上方附件填写文件名" />
                <van-field v-model="relationship.franchisee_name" label="加盟商" placeholder="加盟/联营凭证中的加盟商名称" />
                <van-field v-model="relationship.holder_name" label="持证主体" placeholder="加盟/联营凭证中的持证主体" />
                <van-field v-model="relationship.address" label="关系地址" placeholder="凭证中约定的经营地址" />
                <van-field v-model="multiAddressHolderName" label="多址材料主体" placeholder="多经营地址材料列明的持证主体" />
                <van-field v-model="multiAddressText" label="多经营地址" placeholder="一行一个，仅在附件明确列明时填写" type="textarea" autosize />
              </template>
              </template>
            </van-cell-group>

            <div class="comp-action-bar">
              <van-button
                type="primary"
                block
                round
                size="large"
                :loading="comparing"
                icon="balance-list"
                @click="triggerComparison"
              >开始自动核对</van-button>
              <p class="comp-action-hint">系统自动生成报告，异常材料进入人工复核</p>
            </div>
          </div>
          <div v-else class="comp-phase">
            <van-empty image-size="60" description="未找到来源附件" />
          </div>
        </template>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { tobaccoApi } from '@/api'
import { showDialog, showToast, showLoadingToast, closeToast } from 'vant'

const router = useRouter()
const records = ref([])
const stats = ref({})
const loading = ref(true)
const keyword = ref('')
const filterResult = ref('')

// 发起新比对
const showComparisonForm = ref(false)
const pendingSection = ref(null)
const pendingStores = ref([])
const pendingLoading = ref(false)
const pendingMoreLoading = ref(false)
const pendingPage = ref(0)
const pendingHasMore = ref(false)
const pendingError = ref('')
const showManualSearch = ref(false)
const selectedStore = ref(null)
const selectedPendingStoreCodes = ref([])
const batching = ref(false)
const batchSummary = ref(null)
const storeIdentifier = ref('')
const sourceDocuments = ref([])
const sourceLoading = ref(false)
const sourceQueried = ref(false)
const sourceError = ref('')
const activeFilePath = ref('')
const comparing = ref(false)
const showManualCorrection = ref(false)
const reviewMode = ref('standard')
const businessFields = ref({ subject_name: '', business_address: '', legal_person: '' })
const tobaccoFields = ref({ subject_name: '', business_address: '', legal_person: '', valid_to: '' })
const relationship = ref({ document_id: '', franchisee_name: '', holder_name: '', address: '' })
const multiAddressHolderName = ref('')
const multiAddressText = ref('')
const tobaccoReportCacheKey = 'tobacco_report_list_cache_v2'

const fileCount = computed(() => {
  return sourceDocuments.value.reduce((sum, doc) => sum + doc.files.length, 0)
})
const visibleRecords = computed(() => records.value.filter((record) => {
  const matchesResult = !filterResult.value || record.overall_result === filterResult.value
  const matchesKeyword = !keyword.value.trim() || String(record.company_name || '').includes(keyword.value.trim())
  return matchesResult && matchesKeyword
}))
const filteredPendingStores = computed(() => {
  const term = keyword.value.trim().toLowerCase()
  if (!term) return pendingStores.value
  return pendingStores.value.filter((store) => [
    store.store_code,
    store.store_name,
    store.requestid,
    store.submit_date,
    store.request_name,
    store.summary_title,
    store.content_summary,
  ].some((value) => String(value || '').toLowerCase().includes(term)))
})
const filterHint = computed(() => ({
  '': '全部：展示所有自动核对结果',
  '通过': '通过：所有适用规则均已通过，无需人工复核',
  '不通过': '不通过：存在高风险问题，例如证照类型错误或已过期',
  '待校验': '待校验：证据不足或存在差异，需要人工复核',
}[filterResult.value]))

onMounted(() => loadList())

async function loadList() {
  const cached = cachedReports()
  if (cached.length) {
    records.value = cached
    stats.value = reportStats(cached)
  } else if (!records.value.length) {
    records.value = demoReports()
    stats.value = reportStats(records.value)
  }
  loading.value = true
  try {
    const res = await tobaccoApi.list({
      overall_result: filterResult.value,
      keyword: keyword.value,
      limit: 200,
    })
    const merged = mergeReports(res.records || [], cached)
    records.value = merged.length ? merged : demoReports()
    stats.value = reportStats(records.value)
    cacheReports(records.value)
  } catch (e) {
    records.value = cached.length ? cached : demoReports()
    stats.value = reportStats(records.value)
    showToast('报告服务暂不可用，已展示演示报告')
  } finally {
    loading.value = false
  }
}

function resultTagType(result) {
  if (result === '通过') return 'success'
  if (result === '不通过') return 'danger'
  if (result === '待校验') return 'warning'
  return 'default'
}

function showFilterHelp(type) {
  const content = {
    all: ['全部', '展示所有自动核对结果。'],
    passed: ['通过', '所有适用规则均已通过，无需人工复核。'],
    failed: ['不通过', '存在高风险问题，例如证照类型错误或烟草证已过期。'],
    pending: ['待校验', '证据不足或存在字段差异，需要人工复核。'],
  }[type]
  showDialog({ title: content[0], message: content[1] })
}

function demoReports() {
  return [
    {
      id: 'demo-standard-review',
      company_name: '成都示例烟草商行',
      overall_result: '通过',
      compare_time: '2026-07-16T09:00:00+08:00',
      unmatched_fields: [],
      review_mode: 'standard',
    },
    {
      id: 'demo-store-in-store-review',
      company_name: '乙便利店',
      overall_result: '通过',
      compare_time: '2026-07-16T09:00:00+08:00',
      unmatched_fields: [],
      review_mode: 'store_in_store',
    },
    {
      id: 'demo-failed-review',
      company_name: '成都其他烟草商行',
      overall_result: '不通过',
      compare_time: '2026-07-15T16:30:00+08:00',
      unmatched_fields: ['主体名称一致', '烟草证有效期'],
      review_mode: 'standard',
    },
    {
      id: 'demo-pending-review',
      company_name: '丙店中店便利店',
      overall_result: '待校验',
      compare_time: '2026-07-15T10:15:00+08:00',
      unmatched_fields: ['加盟/联营/场地授权凭证'],
      review_mode: 'store_in_store',
    },
  ]
}

function reportStats(items) {
  return {
    total: items.length,
    passed: items.filter((item) => item.overall_result === '通过').length,
    failed: items.filter((item) => item.overall_result === '不通过').length,
    pending: items.filter((item) => item.overall_result === '待校验').length,
  }
}

function cachedReports() {
  try {
    const parsed = JSON.parse(sessionStorage.getItem(tobaccoReportCacheKey) || '[]')
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function cacheReports(items) {
  sessionStorage.setItem(tobaccoReportCacheKey, JSON.stringify(items))
}

function mergeReports(serverReports, cached) {
  const byId = new Map()
  for (const report of cached) {
    if (report?.id) byId.set(report.id, report)
  }
  for (const report of serverReports) {
    if (report?.id) byId.set(report.id, report)
  }
  return Array.from(byId.values())
}

// ========== 发起新比对 ==========

function toggleSection() {
  showComparisonForm.value = !showComparisonForm.value
  if (showComparisonForm.value && !pendingStores.value.length && !pendingLoading.value && !pendingError.value) {
    loadPendingStores()
  }
}

async function openPendingQueue() {
  if (!showComparisonForm.value) toggleSection()
  await nextTick()
  pendingSection.value?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

async function loadPendingStores({ reset = true } = {}) {
  const page = reset ? 1 : pendingPage.value + 1
  if (reset) {
    pendingLoading.value = true
    pendingError.value = ''
  } else {
    pendingMoreLoading.value = true
  }
  try {
    const res = await tobaccoApi.getPendingStores(page)
    const incoming = res.stores || []
    pendingStores.value = reset
      ? incoming
      : [...pendingStores.value, ...incoming.filter((store) => !pendingStores.value.some((current) => pendingStoreKey(current) === pendingStoreKey(store)))]
    pendingPage.value = page
    pendingHasMore.value = Boolean(res.has_more)
    selectedPendingStoreCodes.value = selectedPendingStoreCodes.value.filter((code) =>
      pendingStores.value.some((store) => pendingStoreKey(store) === code),
    )
  } catch (e) {
    pendingError.value = e.message || '获取待处理列表失败'
    pendingStores.value = []
  } finally {
    pendingLoading.value = false
    pendingMoreLoading.value = false
  }
}

function loadMorePendingStores() {
  if (!pendingHasMore.value || pendingMoreLoading.value) return
  loadPendingStores({ reset: false })
}

function pendingStoreKey(store) {
  return String(store.store_code || store.store_name || '')
}

const selectedPendingStores = computed(() => pendingStores.value.filter((store) =>
  selectedPendingStoreCodes.value.includes(pendingStoreKey(store)),
))
const allFilteredPendingSelected = computed(() => {
  const visibleKeys = filteredPendingStores.value.map(pendingStoreKey)
  return visibleKeys.length > 0 && visibleKeys.every((key) => selectedPendingStoreCodes.value.includes(key))
})

function toggleSelectAllPending() {
  const visibleKeys = filteredPendingStores.value.map(pendingStoreKey)
  const allVisibleSelected = visibleKeys.length > 0 && visibleKeys.every((key) =>
    selectedPendingStoreCodes.value.includes(key),
  )
  selectedPendingStoreCodes.value = allVisibleSelected
    ? selectedPendingStoreCodes.value.filter((key) => !visibleKeys.includes(key))
    : [...new Set([...selectedPendingStoreCodes.value, ...visibleKeys])]
}

async function runBatchComparison() {
  const stores = selectedPendingStores.value
  if (!stores.length) return

  batching.value = true
  showLoadingToast({ message: `正在核对 ${stores.length} 条申请...`, forbidClick: true, duration: 0 })
  try {
    const response = await tobaccoApi.createConsistencyReviewsBatch(stores.map(pendingStoreKey))
    const completedReports = (response.items || [])
      .filter((item) => item.status === 'completed' && item.report)
      .map((item) => item.report)
    const completedIds = new Set((response.items || [])
      .filter((item) => item.status === 'completed')
      .map((item) => item.store_identifier))
    records.value = [
      ...completedReports,
      ...records.value.filter((item) => !completedReports.some((report) => report.id === item.id)),
    ]
    stats.value = reportStats(records.value)
    cacheReports(records.value)
    pendingStores.value = pendingStores.value.filter((store) => !completedIds.has(pendingStoreKey(store)))
    selectedPendingStoreCodes.value = []
    batchSummary.value = { completed: response.completed || 0, failed: response.failed || 0 }
    closeToast()
    showToast(`批量核对完成：${response.completed || 0} 条`)
  } catch (error) {
    closeToast()
    showToast(error.message || '批量核对提交失败')
  } finally {
    batching.value = false
  }
}

async function selectPendingStore(store) {
  selectedStore.value = store
  sourceDocuments.value = []
  sourceQueried.value = false
  sourceError.value = ''
  sourceLoading.value = true
  try {
    const identifier = store.store_code || store.store_name || ''
    const res = await tobaccoApi.fetchSourceFiles(identifier)
    sourceDocuments.value = res.documents || []
    if (store.source === 'demo') applyDemoExtraction()
    sourceQueried.value = true
  } catch (error) {
    sourceError.value = error.message || '获取来源文件失败'
  } finally {
    sourceLoading.value = false
  }
}

function clearSelectedStore() {
  selectedStore.value = null
  sourceDocuments.value = []
  sourceError.value = ''
  sourceQueried.value = false
  storeIdentifier.value = ''
  showManualCorrection.value = false
}

function applyDemoExtraction() {
  reviewMode.value = 'store_in_store'
  businessFields.value = {
    subject_name: '乙便利店',
    business_address: '成都市锦江区总店',
    legal_person: '张三',
  }
  tobaccoFields.value = {
    subject_name: '乙便利店',
    business_address: '成都市高新区天府大道 1 号',
    legal_person: '张三',
    valid_to: '2099-12-31',
  }
  relationship.value = {
    document_id: '加盟及场地授权协议.pdf',
    franchisee_name: '甲加盟商',
    holder_name: '乙便利店',
    address: '成都市高新区天府大道 1 号',
  }
  multiAddressHolderName.value = '乙便利店'
  multiAddressText.value = '成都市高新区天府大道 1 号'
}

async function fetchSourceFiles() {
  const identifier = storeIdentifier.value.trim()
  if (!identifier) return

  sourceLoading.value = true
  sourceQueried.value = false
  sourceError.value = ''
  sourceDocuments.value = []
  try {
    const res = await tobaccoApi.fetchSourceFiles(identifier)
    sourceDocuments.value = res.documents || []
    sourceQueried.value = true
  } catch (error) {
    sourceError.value = error.message || '获取来源文件失败'
  } finally {
    sourceLoading.value = false
  }
}

async function previewFile(file) {
  // Mobile browsers block windows opened after an awaited network request.
  const previewWindow = window.open('', '_blank')
  const objectUrl = await fetchFileObjectUrl(file)
  if (!objectUrl) {
    previewWindow?.close()
    return
  }
  if (previewWindow) {
    previewWindow.opener = null
    previewWindow.location.href = objectUrl
  } else {
    window.location.assign(objectUrl)
  }
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 60000)
}

async function downloadFile(file) {
  const objectUrl = await fetchFileObjectUrl(file, true)
  if (!objectUrl) return
  const link = document.createElement('a')
  link.href = objectUrl
  link.download = file.file_name
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000)
}

async function fetchFileObjectUrl(file, download = false) {
  activeFilePath.value = file.relative_path
  try {
    const blob = await tobaccoApi.fetchSourceFile(file.relative_path, download)
    return URL.createObjectURL(blob)
  } catch (error) {
    showToast(error.message || '文件获取失败')
    return ''
  } finally {
    activeFilePath.value = ''
  }
}

async function triggerComparison() {
  const identifier = selectedStore.value
    ? (selectedStore.value.store_code || selectedStore.value.store_name || '')
    : storeIdentifier.value.trim()

  if (!identifier) {
    showToast('请先获取门店信息')
    return
  }
  // 手动搜索模式：必须有来源文件才能比对
  if (!selectedStore.value && !sourceDocuments.value.length) {
    showToast('请先获取来源文件')
    return
  }

  comparing.value = true
  showLoadingToast({ message: '正在自动核对...', forbidClick: true, duration: 0 })
  try {
    const selectedFiles = sourceDocuments.value.flatMap((document) => document.files || [])
    const res = await tobaccoApi.createConsistencyReview(identifier, {
      review_mode: reviewMode.value,
      business_license_fields: { document_type: 'business_license', ...businessFields.value },
      tobacco_license_fields: { document_type: 'tobacco_license', ...tobaccoFields.value },
      store_in_store: reviewMode.value === 'store_in_store' ? {
        relationship_evidence: relationship.value,
        multi_address_evidence: {
          holder_name: multiAddressHolderName.value,
          addresses: multiAddressText.value.split('\n').map((value) => value.trim()).filter(Boolean),
        },
      } : {},
      selected_files: selectedFiles.map((file) => ({
        relative_path: file.relative_path,
        file_name: file.file_name,
      })),
    })
    closeToast()
    showToast('自动核对已完成')
    const updated = [res.report, ...cachedReports().filter((item) => item.id !== res.report.id)]
    cacheReports(updated)
    router.push(`/tobacco/reports/${res.task_id}`)
  } catch (e) {
    closeToast()
    showToast(e.message || '提交比对失败')
  } finally {
    comparing.value = false
  }
}

function fileIcon(file) {
  const name = (file.file_name || '').toLowerCase()
  if (name.includes('.pdf')) return 'eye-o'
  if (name.match(/\.(jpg|jpeg|png|gif|bmp|webp)/)) return 'photo-o'
  return 'description'
}

function documentKey(document) {
  const source = document.source || {}
  return `${source.requestid || ''}-${source.docid || ''}-${source.imagefile_id || ''}`
}

function formatFileSize(size) {
  const bytes = Number(size || 0)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<style scoped>
.tobacco-page { padding-bottom: 24px; }

/* ===== 统计卡片 ===== */
.stats-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 12px 16px 0;
}
.stat-card {
  border-radius: 8px;
  padding: 14px;
  color: #323233;
  text-align: center;
  background: #f5f6f8;
  cursor: pointer;
  transition: opacity 0.15s;
}
.stat-card:active { opacity: 0.7; }
.stat-card.success { background: #e8fae8; color: #07c160; }
.stat-card.danger { background: #ffeeed; color: #ee0a24; }
.stat-card.warning { background: #fff7e6; color: #ff976a; }
.stat-num { font-size: 24px; font-weight: 700; }
.stat-label { display: flex; align-items: center; justify-content: center; gap: 4px; font-size: 12px; margin-top: 2px; }
.stat-help { width: 15px; height: 15px; padding: 0; border: 1px solid currentColor; border-radius: 50%; color: inherit; background: transparent; font-size: 10px; font-weight: 700; line-height: 13px; }
.pending-shortcut { padding: 0 16px 4px; }

/* ===== 报告列表 ===== */
.filter-hint { padding: 8px 16px 4px; color: #969799; font-size: 12px; line-height: 1.4; }
.report-list { padding: 10px 16px 0; }
.report-card {
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  cursor: pointer;
}
.report-card:active { background: #f5f6f8; }
.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.company-name { font-size: 15px; font-weight: 600; color: #323233; }
.card-detail { font-size: 12px; color: #969799; }
.card-warning {
  display: flex;
  align-items: center;
  gap: 4px;
  margin-top: 6px;
  font-size: 12px;
  color: #ee0a24;
}
.page-loading { display: flex; justify-content: center; padding: 40px; }

/* ===== 发起新比对 ===== */
.new-comp-section {
  margin: 12px 16px 0;
  border: 1px solid #e7edf3;
  border-radius: 10px;
  background: #fff;
  overflow: hidden;
}
.new-comp-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  cursor: pointer;
  user-select: none;
  -webkit-tap-highlight-color: transparent;
}
.new-comp-header:active { background: #f7f8fa; }
.new-comp-header-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.new-comp-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 6px;
  background: #ecf5ff;
  color: #1989fa;
  transition: transform 0.2s;
}
.new-comp-icon.rotated {
  transform: rotate(45deg);
  background: #1989fa;
  color: #fff;
}
.new-comp-title {
  font-size: 15px;
  font-weight: 600;
  color: #323233;
}
.new-comp-header-right {
  display: flex;
  align-items: center;
  gap: 6px;
}
.new-comp-hint {
  font-size: 12px;
  color: #c8c9cc;
}
.comp-form-body {
  border-top: 1px solid #f0f2f4;
}
.comp-phase {
  padding: 16px 12px;
}
.comp-phase-empty {
  text-align: center;
  padding: 16px 0;
}
.comp-empty-text {
  font-size: 14px;
  color: #323233;
  margin: 8px 0 4px;
}
.comp-empty-hint {
  font-size: 12px;
  color: #c8c9cc;
  margin: 0;
}
.comp-loading {
  display: flex;
  justify-content: center;
  padding: 20px 0;
}

/* 待处理列表 */
.pending-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 13px;
  font-weight: 600;
  color: #323233;
  padding: 0 0 10px;
  border-bottom: 1px solid #f5f6f8;
  margin-bottom: 6px;
}
.pending-header__title,
.pending-header__actions {
  display: flex;
  align-items: center;
  gap: 6px;
}
.pending-header__title { min-width: 0; flex: 1; }
.pending-header__actions { flex-shrink: 0; }
.pending-select-all {
  padding: 0;
  border: 0;
  background: transparent;
  color: #1989fa;
  font-size: 12px;
}
.batch-summary { margin: 8px 0; }
.pending-load-more { display: flex; justify-content: center; padding: 10px 0 2px; }
@media (max-width: 420px) {
  .pending-header {
    align-items: flex-start;
    flex-wrap: wrap;
  }
  .pending-header__title {
    flex: 1 1 100%;
  }
  .pending-header__actions {
    width: 100%;
    justify-content: flex-end;
  }
}
.pending-item {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 8px;
  border-radius: 8px;
  cursor: pointer;
  transition: background 0.15s;
}
.pending-item:active { background: #f5f6f8; }
.pending-item + .pending-item { border-top: 1px solid #f5f6f8; }
.pending-item-body { flex: 1; min-width: 0; }
.pending-item-name {
  font-size: 14px;
  font-weight: 500;
  color: #323233;
}
.pending-item-title { margin-top: 3px; color: #646566; font-size: 12px; line-height: 1.4; }
.pending-item-content { margin-top: 2px; color: #969799; font-size: 12px; line-height: 1.4; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.pending-item-meta {
  font-size: 12px;
  color: #969799;
  margin-top: 2px;
}

/* 手动搜索 */
.manual-search-divider {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0 8px;
}
.divider-line {
  flex: 1;
  height: 1px;
  background: #ebedf0;
}
.divider-text {
  font-size: 12px;
  color: #c8c9cc;
  white-space: nowrap;
}
.manual-search-trigger {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #1989fa;
  cursor: pointer;
  padding: 4px 0;
}
.manual-search-trigger:active { opacity: 0.7; }
.manual-search-body {
  margin-top: 8px;
}

/* 门店被选中后 */
.comp-back {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 13px;
  color: #1989fa;
  cursor: pointer;
  padding: 12px 12px 8px;
}
.comp-back:active { opacity: 0.7; }
.selected-store-info {
  padding: 4px 12px 12px;
  border-bottom: 1px solid #f5f6f8;
}
.selected-store-name {
  font-size: 16px;
  font-weight: 600;
  color: #323233;
}
.selected-store-meta {
  font-size: 12px;
  color: #969799;
  margin-top: 4px;
}

/* 来源文件 */
.source-error {
  padding: 9px 12px;
  margin: 8px 12px;
  border-radius: 6px;
  background: #fff5f4;
  color: #c83b32;
  font-size: 13px;
  line-height: 1.45;
}
.source-files-label {
  font-size: 12px;
  font-weight: 600;
  color: #969799;
  padding: 10px 12px 4px;
}
.source-document {
  margin: 0 12px 8px;
  padding: 12px;
  border: 1px solid #f0f2f4;
  border-radius: 8px;
  background: #fafbfc;
}
.source-document__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.source-document__title { color: #1f2933; font-size: 14px; font-weight: 600; }
.source-document__meta, .source-file__meta { margin-top: 3px; color: #8a949e; font-size: 12px; line-height: 1.4; }
.source-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 0;
}
.source-file + .source-file { border-top: 1px solid #f0f2f4; }
.source-file__body { min-width: 0; flex: 1; }
.source-file__name {
  overflow: hidden;
  color: #323233;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 6px;
}
.source-file__actions { display: flex; flex-shrink: 0; gap: 6px; }

/* 提交比对按钮 */
.comp-action-bar {
  margin: 0 12px 16px;
  padding: 0 0 0;
  text-align: center;
}
.comp-action-hint {
  margin: 8px 0 0;
  font-size: 12px;
  color: #c8c9cc;
}
:deep(.van-field) { padding: 12px; }
:deep(.van-field__label) { width: 72px; color: #323233; }
</style>
