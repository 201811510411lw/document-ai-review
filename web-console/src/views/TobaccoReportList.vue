<template>
  <div class="tobacco-page">
    <van-nav-bar title="烟草证比对报告" left-arrow @click-left="router.push('/home')" />

    <!-- ========== 路径A：日常浏览 ========== -->

    <!-- 统计 -->
    <div class="stats-row">
      <div class="stat-card" @click="filterResult = ''">
        <div class="stat-num">{{ stats.total || 0 }}</div>
        <div class="stat-label">全部</div>
      </div>
      <div class="stat-card success" @click="filterResult = '通过'">
        <div class="stat-num">{{ stats.passed || 0 }}</div>
        <div class="stat-label">通过</div>
      </div>
      <div class="stat-card danger" @click="filterResult = '不通过'">
        <div class="stat-num">{{ stats.failed || 0 }}</div>
        <div class="stat-label">不通过</div>
      </div>
      <div class="stat-card warning" @click="filterResult = '待校验'">
        <div class="stat-num">{{ stats.pending || 0 }}</div>
        <div class="stat-label">待校验</div>
      </div>
    </div>

    <!-- 搜索 -->
    <van-search
      v-model="keyword"
      placeholder="搜索公司名称"
      shape="round"
      clearable
      @search="loadList"
    />

    <!-- 列表 -->
    <div v-if="records.length" class="report-list">
      <div
        v-for="r in records"
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
    <van-loading v-if="loading" class="page-loading" size="24">加载中...</van-loading>

    <!-- ========== 路径B：发起新比对 ========== -->

    <div class="new-comp-section">
      <div class="new-comp-header" @click="toggleSection">
        <div class="new-comp-header-left">
          <span class="new-comp-icon" :class="{ rotated: showComparisonForm }">
            <van-icon name="add" size="16" />
          </span>
          <span class="new-comp-title">发起新比对</span>
        </div>
        <div class="new-comp-header-right">
          <span v-if="!showComparisonForm" class="new-comp-hint">查看待处理门店并触发比对</span>
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
              <van-icon name="records" color="#1989fa" />
              <span>待处理的新提交（共 {{ pendingStores.length }} 条）</span>
            </div>
            <div
              v-for="store in pendingStores"
              :key="store.store_code"
              class="pending-item"
              @click="selectPendingStore(store)"
            >
              <div class="pending-item-left">
                <div class="pending-item-icon">📋</div>
              </div>
              <div class="pending-item-body">
                <div class="pending-item-name">{{ store.store_name || store.store_code }}</div>
                <div class="pending-item-meta">提交时间: {{ store.submit_date || '-' }}</div>
              </div>
              <van-icon name="arrow" color="#c8c9cc" />
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
              >直接发起比对</van-button>
              <p class="comp-action-hint">将基于 OA 表单数据执行一致性校验</p>
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

            <div class="comp-action-bar">
              <van-button
                type="primary"
                block
                round
                size="large"
                :loading="comparing"
                icon="balance-list"
                @click="triggerComparison"
              >提交比对</van-button>
              <p class="comp-action-hint">将基于营业执照和烟草证文件发起一致性校验</p>
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
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { tobaccoApi } from '@/api'
import { showToast, showLoadingToast, closeToast } from 'vant'

const router = useRouter()
const records = ref([])
const stats = ref({})
const loading = ref(true)
const keyword = ref('')
const filterResult = ref('')

// 发起新比对
const showComparisonForm = ref(false)
const pendingStores = ref([])
const pendingLoading = ref(false)
const pendingError = ref('')
const showManualSearch = ref(false)
const selectedStore = ref(null)
const storeIdentifier = ref('')
const sourceDocuments = ref([])
const sourceLoading = ref(false)
const sourceQueried = ref(false)
const sourceError = ref('')
const activeFilePath = ref('')
const comparing = ref(false)

const fileCount = computed(() => {
  return sourceDocuments.value.reduce((sum, doc) => sum + doc.files.length, 0)
})

onMounted(() => loadList())
watch(filterResult, () => loadList())

async function loadList() {
  loading.value = true
  try {
    const res = await tobaccoApi.list({
      overall_result: filterResult.value,
      keyword: keyword.value,
      limit: 200,
    })
    records.value = res.records || []
    stats.value = res.stats || {}
  } catch (e) {
    showToast('加载失败')
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

// ========== 发起新比对 ==========

function toggleSection() {
  showComparisonForm.value = !showComparisonForm.value
  if (showComparisonForm.value && !pendingStores.value.length && !pendingLoading.value && !pendingError.value) {
    loadPendingStores()
  }
}

async function loadPendingStores() {
  pendingLoading.value = true
  pendingError.value = ''
  try {
    const res = await tobaccoApi.getPendingStores()
    pendingStores.value = res.stores || []
  } catch (e) {
    pendingError.value = e.message || '获取待处理列表失败'
    pendingStores.value = []
  } finally {
    pendingLoading.value = false
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
  const objectUrl = await fetchFileObjectUrl(file)
  if (!objectUrl) return
  const previewWindow = window.open(objectUrl, '_blank', 'noopener')
  if (!previewWindow) {
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

  // 待处理门店：允许直接用OA表单数据比对（不需要本地文件）
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
  showLoadingToast({ message: '正在提交比对...', forbidClick: true, duration: 0 })
  try {
    const res = await tobaccoApi.createConsistencyReview(identifier)
    closeToast()
    showToast('比对任务已提交')

    // 将新生成的报告插入到列表顶部，确保用户立即看到
    if (res.report) {
      records.value.unshift(res.report)
      stats.value.total = (stats.value.total || 0) + 1
      if (res.report.overall_result === '通过') stats.value.passed = (stats.value.passed || 0) + 1
      else if (res.report.overall_result === '不通过') stats.value.failed = (stats.value.failed || 0) + 1
      else stats.value.pending = (stats.value.pending || 0) + 1
    }

    // 关闭展开区，重置状态
    showComparisonForm.value = false
    clearSelectedStore()
    await loadList()
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
.stat-label { font-size: 12px; margin-top: 2px; }

/* ===== 报告列表 ===== */
.report-list { padding: 0 16px; }
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
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #323233;
  padding: 0 0 10px;
  border-bottom: 1px solid #f5f6f8;
  margin-bottom: 6px;
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
.pending-item-icon { font-size: 20px; line-height: 1; }
.pending-item-body { flex: 1; min-width: 0; }
.pending-item-name {
  font-size: 14px;
  font-weight: 500;
  color: #323233;
}
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
