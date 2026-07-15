<template>
  <div class="tobacco-page">
    <van-nav-bar title="烟草证比对报告" left-arrow @click-left="router.push('/home')" />

    <section class="source-section" aria-label="烟草证来源文件查询">
      <van-field
        v-model.trim="storeIdentifier"
        label="门店编号"
        placeholder="请输入门店编号"
        clearable
        :disabled="sourceLoading"
        @keyup.enter="fetchSourceFiles"
      >
        <template #button>
          <van-button
            size="small"
            type="primary"
            :loading="sourceLoading"
            :disabled="!storeIdentifier"
            @click="fetchSourceFiles"
          >获取</van-button>
        </template>
      </van-field>

      <div v-if="sourceError" class="source-error" role="alert">{{ sourceError }}</div>

      <div v-if="sourceQueried && !sourceLoading && !sourceDocuments.length" class="source-empty">
        <van-empty image-size="72" description="未找到来源附件" />
      </div>

      <div v-if="sourceDocuments.length" class="source-documents">
        <article v-for="document in sourceDocuments" :key="documentKey(document)" class="source-document">
          <div class="source-document__header">
            <div>
              <div class="source-document__title">{{ document.source.store_name || document.source.store_code || storeIdentifier }}</div>
              <div class="source-document__meta">
                流程 {{ document.source.requestid || '-' }} · 附件 {{ document.source.docid || '-' }}
              </div>
            </div>
            <van-tag plain type="primary">{{ document.files.length }} 个文件</van-tag>
          </div>

          <div class="source-file-list">
            <div v-for="file in document.files" :key="file.relative_path" class="source-file">
              <div class="source-file__body">
                <div class="source-file__name">{{ file.file_name }}</div>
                <div class="source-file__meta">{{ formatFileSize(file.file_size) }}<span v-if="file.content_type"> · {{ file.content_type }}</span></div>
              </div>
              <div class="source-file__actions">
                <van-button size="small" plain type="primary" :loading="activeFilePath === file.relative_path" @click="previewFile(file)">预览</van-button>
                <van-button size="small" plain :loading="activeFilePath === file.relative_path" @click="downloadFile(file)">下载</van-button>
              </div>
            </div>
          </div>
        </article>
      </div>
    </section>

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
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { tobaccoApi } from '@/api'
import { showToast } from 'vant'

const router = useRouter()
const records = ref([])
const stats = ref({})
const loading = ref(true)
const keyword = ref('')
const filterResult = ref('')
const storeIdentifier = ref('')
const sourceDocuments = ref([])
const sourceLoading = ref(false)
const sourceQueried = ref(false)
const sourceError = ref('')
const activeFilePath = ref('')

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
.tobacco-page { padding-bottom: 16px; }
.source-section {
  margin: 12px 16px 16px;
  overflow: hidden;
  border: 1px solid #e7edf3;
  border-radius: 8px;
  background: #fff;
}
.source-section :deep(.van-field) { padding: 12px; }
.source-section :deep(.van-field__label) { width: 72px; color: #323233; }
.source-section :deep(.van-button) { min-width: 56px; }
.source-error {
  padding: 9px 12px;
  border-top: 1px solid #f3d8d5;
  background: #fff5f4;
  color: #c83b32;
  font-size: 13px;
  line-height: 1.45;
}
.source-empty { border-top: 1px solid #eef1f4; }
.source-documents { border-top: 1px solid #eef1f4; }
.source-document { padding: 12px; }
.source-document + .source-document { border-top: 1px solid #eef1f4; }
.source-document__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.source-document__title { color: #1f2933; font-size: 15px; font-weight: 600; }
.source-document__meta, .source-file__meta { margin-top: 3px; color: #8a949e; font-size: 12px; line-height: 1.4; }
.source-file-list { border-top: 1px solid #f0f2f4; }
.source-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 0;
}
.source-file + .source-file { border-top: 1px solid #f0f2f4; }
.source-file__body { min-width: 0; flex: 1; }
.source-file__name { overflow: hidden; color: #323233; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.source-file__actions { display: flex; flex-shrink: 0; gap: 6px; }
.stats-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 12px 16px;
}
.stat-card {
  border-radius: 8px;
  padding: 14px;
  color: #323233;
  text-align: center;
  background: #f5f6f8;
  cursor: pointer;
}
.stat-card:active { opacity: 0.8; }
.stat-card.success { background: #e8fae8; color: #07c160; }
.stat-card.danger { background: #ffeeed; color: #ee0a24; }
.stat-card.warning { background: #fff7e6; color: #ff976a; }
.stat-num { font-size: 24px; font-weight: 700; }
.stat-label { font-size: 12px; margin-top: 2px; }
.page-loading { display: flex; justify-content: center; padding: 40px; }
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
</style>
