<template>
  <section class="workbench" aria-label="OA 烟草证核对工作台">
    <header class="workbench-header">
      <div>
        <p class="eyebrow">OA 提交材料</p>
        <h1>待办核对</h1>
      </div>
      <van-button plain size="small" type="primary" icon="replay" :loading="pendingLoading" @click="loadPendingStores()">
        刷新待办
      </van-button>
    </header>

    <van-notice-bar
      v-if="sourceUnavailable"
      color="#9d5d1d"
      background="#fff8e8"
      left-icon="warning-o"
      wrapable
    >StarRocks 当前不可用，不能将演示数据作为审核依据。</van-notice-bar>
    <van-notice-bar
      v-if="batchSummary"
      :color="batchSummary.failed ? '#b84f48' : '#357a56'"
      :background="batchSummary.failed ? '#fff4f3' : '#f0faf4'"
      left-icon="info-o"
    >最近一次批量核对：完成 {{ batchSummary.completed }} 条，失败 {{ batchSummary.failed }} 条。</van-notice-bar>

    <template v-if="selectedStore">
      <button class="back-button" type="button" @click="clearSelectedStore">
        <van-icon name="arrow-left" /> 返回待办队列
      </button>
      <div class="selected-store">
        <div>
          <p>当前核对对象</p>
          <h2>{{ selectedStore.store_name || selectedStore.store_code }}</h2>
        </div>
        <dl>
          <div><dt>门店编码</dt><dd>{{ selectedStore.store_code || '-' }}</dd></div>
          <div><dt>OA 流程</dt><dd>{{ selectedStore.requestid || '-' }}</dd></div>
          <div><dt>提交时间</dt><dd>{{ selectedStore.submit_date || '-' }}</dd></div>
        </dl>
      </div>

      <div v-if="sourceLoading" class="skeleton-documents" aria-label="正在准备 OA 附件"><span v-for="item in 3" :key="item"></span></div>
      <div v-else-if="sourceError" class="source-error">
        <van-icon name="warning-o" />
        <div><strong>来源附件未就绪</strong><span>{{ sourceError }}</span></div>
      </div>
      <template v-else-if="sourceDocuments.length">
        <div class="section-heading">
          <div><p class="eyebrow">审核证据</p><h2>OA 附件</h2></div>
          <span>{{ fileCount }} 个文件</span>
        </div>
        <article v-for="document in sourceDocuments" :key="documentKey(document)" class="document-group">
          <header>
            <div>
              <strong>{{ documentRoleLabel(document.source?.document_role) }}</strong>
              <span>文档 {{ document.source?.docid || '-' }}</span>
            </div>
            <van-tag plain type="primary">{{ document.files?.length || 0 }} 个附件</van-tag>
          </header>
          <div v-for="file in document.files" :key="file.relative_path" class="file-row">
            <div class="file-row__name">
              <van-icon :name="fileIcon(file)" color="#2b79b8" />
              <span>{{ file.file_name }}</span>
              <small>{{ formatFileSize(file.file_size) }}</small>
            </div>
            <div class="file-row__actions">
              <van-button size="small" plain type="primary" :loading="activeFilePath === file.relative_path" @click="previewFile(file)">预览</van-button>
              <van-button size="small" plain :loading="activeFilePath === file.relative_path" @click="downloadFile(file)">下载</van-button>
            </div>
          </div>
        </article>
      </template>
      <van-empty v-else-if="sourceQueried" image-size="64" description="未取得可核对的 OA 附件" />

      <TobaccoManualCorrection v-model:expanded="showManualCorrection" v-model:mode="reviewMode" v-model:business-fields="businessFields" v-model:tobacco-fields="tobaccoFields" v-model:relationship="relationship" v-model:multi-address-holder-name="multiAddressHolderName" v-model:multi-address-text="multiAddressText" />
      <div class="submit-panel">
        <div><strong>提交自动核对</strong><span>系统只基于上述 OA 附件抽取字段；异常结果转人工复核。</span></div>
        <van-button type="primary" icon="balance-list" :loading="comparing" @click="triggerComparison">开始核对</van-button>
      </div>
    </template>

    <template v-else>
      <div v-if="pendingLoading" class="skeleton-queue" aria-label="正在加载 OA 待办"><span v-for="item in 5" :key="item"><i></i><i></i></span></div>
      <div v-else-if="pendingError" class="source-error"><van-icon name="warning-o" /><div><strong>待办队列不可用</strong><span>{{ pendingError }}</span></div></div>
      <template v-else>
        <div class="queue-toolbar">
          <div><p class="eyebrow">待处理申请</p><h2>OA 队列</h2></div>
          <div class="queue-toolbar__actions">
            <button type="button" class="text-button" @click="toggleSelectAll">{{ allVisibleSelected ? '取消全选' : '全选' }}</button>
            <van-button size="small" type="primary" icon="balance-list" :disabled="!selectedStoreKeys.length" :loading="batching" @click="runBatchComparison">批量核对 {{ selectedStoreKeys.length }}</van-button>
          </div>
        </div>
        <van-empty v-if="!pendingStores.length" image-size="64" description="暂无 OA 待处理申请" />
        <van-checkbox-group v-else v-model="selectedStoreKeys" class="queue-list">
          <article v-for="store in pendingStores" :key="storeKey(store)" class="queue-item" @click="selectStore(store)">
            <van-checkbox :name="storeKey(store)" @click.stop />
            <div class="queue-item__main">
              <strong>{{ store.store_name || store.store_code }}</strong>
              <span>{{ store.request_name || store.summary_title || '烟草证申请' }}</span>
              <small><span>门店 {{ store.store_code || '-' }}</span><span>流程 {{ store.requestid || '-' }}</span><span>{{ store.submit_date || '-' }}</span></small>
            </div>
            <van-icon name="arrow" color="#9ca8b5" />
          </article>
        </van-checkbox-group>
        <div v-if="pendingHasMore" class="load-more"><van-button plain size="small" type="primary" :loading="pendingMoreLoading" @click="loadMorePendingStores">加载更多</van-button></div>
      </template>

      <van-collapse v-model="expandedPanels" class="manual-collapse">
        <van-collapse-item name="manual" title="按门店编号手工检索">
          <ManualSearch
            v-model:storeIdentifier="storeIdentifier"
            :source-loading="sourceLoading"
            :source-error="sourceError"
            :source-queried="sourceQueried"
            :source-documents="sourceDocuments"
            :active-file-path="activeFilePath"
            :comparing="comparing"
            @fetch="fetchSourceFiles"
            @preview="previewFile"
            @download="downloadFile"
            @trigger="triggerComparison"
          />
        </van-collapse-item>
      </van-collapse>
    </template>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRouter } from 'vue-router'
import { closeToast, showLoadingToast, showToast } from 'vant'
import ManualSearch from '@/components/ManualSearch.vue'
import { tobaccoApi } from '@/api'
import TobaccoManualCorrection from './TobaccoManualCorrection.vue'

const emit = defineEmits(['report-created'])
const router = useRouter()
const pendingStores = ref([])
const pendingLoading = ref(false)
const pendingMoreLoading = ref(false)
const pendingPage = ref(0)
const pendingHasMore = ref(false)
const pendingError = ref('')
const sourceUnavailable = ref(false)
const selectedStoreKeys = ref([])
const selectedStore = ref(null)
const batching = ref(false)
const batchSummary = ref(null)
const storeIdentifier = ref('')
const sourceDocuments = ref([])
const sourceLoading = ref(false)
const sourceQueried = ref(false)
const sourceError = ref('')
const activeFilePath = ref('')
const comparing = ref(false)
const expandedPanels = ref([])
const showManualCorrection = ref(false)
const reviewMode = ref('standard')
const businessFields = ref({ subject_name: '', business_address: '', legal_person: '' })
const tobaccoFields = ref({ subject_name: '', business_address: '', legal_person: '', valid_to: '' })
const relationship = ref({ document_id: '', franchisee_name: '', holder_name: '', address: '' })
const multiAddressHolderName = ref('')
const multiAddressText = ref('')

const fileCount = computed(() => sourceDocuments.value.reduce((total, document) => total + (document.files?.length || 0), 0))
const selectedStores = computed(() => pendingStores.value.filter((store) => selectedStoreKeys.value.includes(storeKey(store))))
const allVisibleSelected = computed(() => pendingStores.value.length > 0 && pendingStores.value.every((store) => selectedStoreKeys.value.includes(storeKey(store))))

loadPendingStores()

async function loadPendingStores({ reset = true } = {}) {
  const page = reset ? 1 : pendingPage.value + 1
  if (reset) {
    pendingLoading.value = true
    pendingError.value = ''
    sourceUnavailable.value = false
  } else {
    pendingMoreLoading.value = true
  }
  try {
    const result = await tobaccoApi.getPendingStores(page)
    const incoming = result.stores || []
    sourceUnavailable.value = Boolean(result.source_unavailable)
    pendingStores.value = reset ? incoming : [...pendingStores.value, ...incoming.filter((item) => !pendingStores.value.some((current) => storeKey(current) === storeKey(item)))]
    pendingPage.value = page
    pendingHasMore.value = Boolean(result.has_more)
  } catch (error) {
    pendingError.value = error.message || '获取待办队列失败'
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

function toggleSelectAll() {
  selectedStoreKeys.value = allVisibleSelected.value ? [] : pendingStores.value.map(storeKey)
}

async function runBatchComparison() {
  if (!selectedStores.value.length) return
  batching.value = true
  showLoadingToast({ message: `正在核对 ${selectedStores.value.length} 条申请`, forbidClick: true, duration: 0 })
  try {
    const response = await tobaccoApi.createConsistencyReviewsBatch(selectedStores.value.map(storeKey))
    const completed = (response.items || []).filter((item) => item.status === 'completed' && item.report).map((item) => item.report)
    completed.forEach((report) => emit('report-created', report))
    const completedStores = new Set((response.items || []).filter((item) => item.status === 'completed').map((item) => item.store_identifier))
    pendingStores.value = pendingStores.value.filter((store) => !completedStores.has(storeKey(store)))
    selectedStoreKeys.value = []
    batchSummary.value = { completed: response.completed || 0, failed: response.failed || 0 }
    showToast(`批量核对完成：${response.completed || 0} 条`)
  } catch (error) {
    showToast(error.message || '批量核对提交失败')
  } finally {
    closeToast()
    batching.value = false
  }
}

async function selectStore(store) {
  selectedStore.value = store
  storeIdentifier.value = storeKey(store)
  await fetchSourceFiles()
}

function clearSelectedStore() {
  selectedStore.value = null
  sourceDocuments.value = []
  sourceError.value = ''
  sourceQueried.value = false
  showManualCorrection.value = false
}

async function fetchSourceFiles() {
  const identifier = selectedStore.value ? storeKey(selectedStore.value) : storeIdentifier.value.trim()
  if (!identifier) return
  sourceLoading.value = true
  sourceError.value = ''
  sourceQueried.value = false
  sourceDocuments.value = []
  try {
    const result = await tobaccoApi.fetchSourceFiles(identifier)
    sourceDocuments.value = result.documents || []
    sourceQueried.value = true
  } catch (error) {
    sourceError.value = error.message || '获取 OA 来源附件失败'
  } finally {
    sourceLoading.value = false
  }
}

async function triggerComparison() {
  const identifier = selectedStore.value ? storeKey(selectedStore.value) : storeIdentifier.value.trim()
  if (!identifier) return showToast('请先选择待办或输入门店编号')
  if (!selectedStore.value && !sourceDocuments.value.length) return showToast('请先获取 OA 来源附件')
  comparing.value = true
  showLoadingToast({ message: '正在抽取 OA 附件并执行核对', forbidClick: true, duration: 0 })
  try {
    const selectedFiles = sourceDocuments.value.flatMap((document) => document.files || [])
    const result = await tobaccoApi.createConsistencyReview(identifier, {
      review_mode: reviewMode.value,
      business_license_fields: { document_type: 'business_license', ...businessFields.value },
      tobacco_license_fields: { document_type: 'tobacco_license', ...tobaccoFields.value },
      store_in_store: reviewMode.value === 'store_in_store' ? {
        relationship_evidence: relationship.value,
        multi_address_evidence: {
          holder_name: multiAddressHolderName.value,
          addresses: multiAddressText.value.split('\n').map((item) => item.trim()).filter(Boolean),
        },
      } : {},
      selected_files: selectedFiles.map((file) => ({ relative_path: file.relative_path, file_name: file.file_name })),
    })
    emit('report-created', result.report)
    showToast('自动核对已完成')
    router.push(`/tobacco/reports/${result.task_id}`)
  } catch (error) {
    showToast(error.message || '提交核对失败')
  } finally {
    closeToast()
    comparing.value = false
  }
}

async function previewFile(file) {
  const previewWindow = window.open('', '_blank')
  const url = await fetchFileObjectUrl(file)
  if (!url) return previewWindow?.close()
  if (previewWindow) {
    previewWindow.opener = null
    previewWindow.location.href = url
  } else {
    window.location.assign(url)
  }
  window.setTimeout(() => URL.revokeObjectURL(url), 60000)
}

async function downloadFile(file) {
  const url = await fetchFileObjectUrl(file, true)
  if (!url) return
  const link = document.createElement('a')
  link.href = url
  link.download = file.file_name || 'oa-attachment'
  document.body.appendChild(link)
  link.click()
  link.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
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

function storeKey(store) { return String(store?.store_code || store?.store_name || '') }
function documentKey(document) { const source = document.source || {}; return `${source.requestid || ''}-${source.docid || ''}-${source.imagefile_id || ''}` }
function documentRoleLabel(role) { return { business_license: '营业执照', tobacco_license: '烟草专卖零售许可证' }[role] || 'OA 审核附件' }
function fileIcon(file) { return /\.(jpg|jpeg|png|gif|bmp|webp)$/i.test(file.file_name || '') ? 'photo-o' : (String(file.file_name || '').toLowerCase().includes('.pdf') ? 'description' : 'records') }
function formatFileSize(size) { const bytes = Number(size || 0); return bytes < 1024 ? `${bytes} B` : (bytes < 1024 * 1024 ? `${(bytes / 1024).toFixed(1)} KB` : `${(bytes / 1024 / 1024).toFixed(1)} MB`) }

</script>

<style scoped>
.workbench { min-width: 0; color: var(--tobacco-ink); }.workbench-header, .queue-toolbar, .section-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 18px; }.workbench-header { padding: 8px 0 22px; }.eyebrow { margin: 0 0 6px; color: var(--tobacco-accent); font-size: 12px; font-weight: 600; }h1, h2 { margin: 0; color: var(--tobacco-ink); font-weight: 720; letter-spacing: 0; }h1 { font-size: 25px; }h2 { font-size: 17px; }.workbench-header :deep(.van-button) { border-color: var(--tobacco-line-strong); border-radius: 6px; color: var(--tobacco-accent); }
.source-error { display: flex; gap: 10px; margin-top: 2px; padding: 14px; border: 1px solid #eac9c5; border-left: 3px solid #c2524b; border-radius: 8px; background: #fff6f5; color: #a1433d; }.source-error strong, .source-error span { display: block; }.source-error span { margin-top: 4px; font-size: 12px; line-height: 1.5; }
.skeleton-queue, .skeleton-documents { display: grid; gap: 1px; overflow: hidden; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-line); }.skeleton-queue > span { display: flex; align-items: center; justify-content: space-between; height: 74px; padding: 0 16px; background: var(--tobacco-surface); }.skeleton-queue i, .skeleton-documents span { display: block; width: 40%; height: 12px; border-radius: 3px; background: #e9eff3; }.skeleton-queue i:last-child { width: 16%; }.skeleton-documents { margin-top: 20px; padding: 14px; gap: 12px; background: var(--tobacco-surface); }.skeleton-documents span { width: 100%; }.skeleton-documents span:nth-child(2) { width: 72%; }.skeleton-documents span:nth-child(3) { width: 86%; }
.queue-toolbar { align-items: end; margin-top: 8px; padding: 0 0 12px; border-bottom: 1px solid var(--tobacco-line-strong); }.queue-toolbar__actions { display: flex; align-items: center; gap: 10px; }.queue-toolbar :deep(.van-button) { border-radius: 6px; }.text-button, .back-button { border: 0; background: transparent; color: var(--tobacco-accent); font-size: 13px; font-weight: 600; }.text-button:active, .back-button:active { transform: translateY(1px); }
.queue-list { overflow: hidden; margin-top: 10px; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); }.queue-item { display: flex; align-items: center; gap: 13px; padding: 15px 16px; border-bottom: 1px solid var(--tobacco-line); cursor: pointer; transition: background-color .16s ease; }.queue-item:last-child { border-bottom: 0; }.queue-item:hover { background: var(--tobacco-surface-muted); }.queue-item:active { transform: translateY(1px); }.queue-item :deep(.van-checkbox__icon--checked .van-icon) { border-color: var(--tobacco-accent); background: var(--tobacco-accent); }.queue-item__main { min-width: 0; flex: 1; }.queue-item__main strong, .queue-item__main span, .queue-item__main small { display: block; }.queue-item__main strong { overflow: hidden; color: var(--tobacco-ink); font-size: 15px; font-weight: 650; text-overflow: ellipsis; white-space: nowrap; }.queue-item__main > span { margin-top: 5px; color: #425c6e; font-size: 13px; line-height: 1.4; }.queue-item__main small { display: flex; flex-wrap: wrap; gap: 0; margin-top: 7px; color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }.queue-item__main small span + span { margin-left: 9px; padding-left: 9px; border-left: 1px solid var(--tobacco-line-strong); }.load-more { padding: 14px; text-align: center; }.load-more :deep(.van-button) { border-radius: 6px; }
.manual-collapse { overflow: hidden; margin-top: 22px; border: 1px solid var(--tobacco-line); border-radius: 8px; }.manual-collapse :deep(.van-collapse-item__title) { color: var(--tobacco-ink); font-size: 14px; font-weight: 600; }.manual-collapse :deep(.van-cell) { background: var(--tobacco-surface); }.manual-collapse :deep(.van-collapse-item__content) { padding: 12px; background: var(--tobacco-surface-muted); }.back-button { display: inline-flex; align-items: center; gap: 5px; padding: 0 0 16px; }.selected-store { display: flex; align-items: end; justify-content: space-between; gap: 20px; padding: 18px; border: 1px solid var(--tobacco-line); border-left: 4px solid var(--tobacco-accent); border-radius: 8px; background: var(--tobacco-surface); }.selected-store p { margin: 0 0 7px; color: var(--tobacco-muted); font-size: 12px; }.selected-store dl { display: flex; flex-wrap: wrap; justify-content: end; gap: 18px; margin: 0; }.selected-store dt { color: var(--tobacco-muted); font-size: 11px; }.selected-store dd { margin: 4px 0 0; color: var(--tobacco-ink); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.section-heading { align-items: end; margin-top: 26px; padding-bottom: 10px; border-bottom: 1px solid var(--tobacco-line-strong); }.section-heading > span { color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }.document-group { overflow: hidden; margin-top: 10px; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); }.document-group header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-bottom: 1px solid var(--tobacco-line); background: var(--tobacco-surface-muted); }.document-group header strong { color: var(--tobacco-ink); font-size: 14px; }.document-group header span { margin-left: 8px; color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }.document-group header :deep(.van-tag) { border-radius: 4px; }.file-row { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-top: 1px solid var(--tobacco-line); }.document-group header + .file-row { border-top: 0; }.file-row__name { display: flex; min-width: 0; align-items: center; gap: 8px; }.file-row__name span { overflow: hidden; color: #31495c; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.file-row__name small { color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; white-space: nowrap; }.file-row__actions { display: flex; flex: 0 0 auto; gap: 7px; }.file-row__actions :deep(.van-button) { border-radius: 5px; }
.submit-panel { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-top: 18px; padding: 16px 18px; border: 1px solid #bdd5df; border-radius: 8px; background: var(--tobacco-accent-soft); }.submit-panel strong, .submit-panel span { display: block; }.submit-panel strong { color: var(--tobacco-ink); font-size: 14px; }.submit-panel span { margin-top: 5px; color: #4d6b7c; font-size: 12px; line-height: 1.45; }.submit-panel :deep(.van-button) { border-radius: 6px; background: var(--tobacco-accent); border-color: var(--tobacco-accent); }
@media (max-width: 600px) { .workbench-header { padding-top: 2px; }.workbench-header h1 { font-size: 22px; }.selected-store, .submit-panel { align-items: stretch; flex-direction: column; }.selected-store dl { justify-content: start; }.queue-toolbar { align-items: stretch; flex-direction: column; }.queue-toolbar__actions { justify-content: space-between; }.submit-panel :deep(.van-button) { width: 100%; }.file-row { align-items: flex-start; flex-direction: column; }.file-row__actions { width: 100%; }.file-row__actions :deep(.van-button) { flex: 1; }.queue-item { align-items: flex-start; padding: 14px; }.queue-item__main strong { white-space: normal; }.queue-item > :last-child { margin-top: 12px; }.selected-store dl { gap: 12px; } }
</style>
