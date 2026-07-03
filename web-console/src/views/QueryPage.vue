<template>
  <div class="query-page">
    <van-nav-bar title="证照查询" left-arrow @click-left="router.push('/scene1')" />
    <!-- 搜索栏 -->
    <van-search
      v-model="keyword"
      placeholder="输入供应商编码或公司名称"
      shape="round"
      clearable
      @search="handleSearch"
      @clear="handleClear"
    >
      <template #action>
        <div @click="handleSearch">搜索</div>
      </template>
    </van-search>

    <!-- 类型筛选 -->
    <div class="type-filter-row">
      <span
        v-for="t in typeOptions"
        :key="t.value"
        class="type-chip"
        :class="{ active: queryType === t.value }"
        @click="queryType = t.value; if (keyword) handleSearch()"
      >{{ t.label }}</span>
    </div>

    <!-- 批量查询入口 -->
    <van-cell-group inset class="batch-section">
      <van-cell title="批量查询" icon="records" is-link @click="showBatchInput = true" />
      <van-cell title="上传 Excel 查询" icon="uploader" is-link @click="showExcelUpload = true" />
    </van-cell-group>

    <!-- 搜索结果区域 -->
    <div v-if="searchResult !== null" class="result-section">
      <!-- 单条结果 -->
      <div v-if="searchResult.type === 'single'" class="result-card">
        <cert-result-card :record="searchResult.data" />
      </div>

      <!-- 批量结果 -->
      <div v-else class="batch-result">
        <van-sticky>
          <div class="batch-summary">
            <span class="summary-item success">✅ 找到 {{ searchResult.stats.found }}</span>
            <span class="summary-item warning">⚠️ 临期 {{ searchResult.stats.expiring }}</span>
            <span class="summary-item danger">❌ 过期 {{ searchResult.stats.expired }}</span>
            <span class="summary-item muted">❓ 未找到 {{ searchResult.stats.missing }}</span>
          </div>
          <div class="batch-actions">
            <van-button
              type="primary"
              size="small"
              round
              :disabled="!hasResults"
              @click="handleBatchDownload"
            >
              📦 打包下载全部
            </van-button>
            <van-button
              size="small"
              round
              plain
              @click="handleExportCsv"
            >
              📋 导出结果
            </van-button>
          </div>
        </van-sticky>

        <van-list
          v-model:loading="listLoading"
          :finished="listFinished"
          finished-text="已全部展示"
        >
          <cert-result-card
            v-for="item in searchResult.records"
            :key="item.id"
            :record="item"
          />
        </van-list>
      </div>
    </div>

    <!-- 空状态/提示 -->
    <div v-else-if="!keyword && !searchResult" class="empty-state">
      <van-empty description="输入供应商编码或公司名称查询证照">
        <template #image>
          <van-icon name="search" size="80" color="#dcdee0" />
        </template>
      </van-empty>

      <!-- 最近查询 -->
      <van-cell-group v-if="recentList.length" title="最近查询">
        <van-cell
          v-for="item in recentList"
          :key="item"
          :title="item"
          is-link
          @click="keyword = item; handleSearch()"
        />
      </van-cell-group>
    </div>

    <!-- 加载中 -->
    <van-loading v-if="loading" class="page-loading" size="24">查询中...</van-loading>

    <!-- 批量输入弹窗 -->
    <van-dialog
      v-model:show="showBatchInput"
      title="粘贴查询数据"
      show-cancel-button
      confirm-button-text="批量查询"
      @confirm="handleBatchQuery"
    >
      <van-field
        v-model="batchText"
        type="textarea"
        rows="8"
        placeholder="每行输入一个编码或公司名称&#10;例如:&#10;贵州益佰制药&#10;北京华联超市&#10;ABC-001"
        autosize
      />
    </van-dialog>

    <!-- Excel 上传弹窗 -->
    <van-dialog
      v-model:show="showExcelUpload"
      title="上传 Excel"
      show-cancel-button
      confirm-button-text="开始解析"
      @confirm="handleExcelUpload"
    >
      <van-uploader
        v-model="excelFileList"
        accept=".xlsx,.xls,.csv"
        max-count="1"
        :after-read="afterExcelRead"
      />
      <div v-if="excelPreview.length" class="excel-preview">
        <p class="preview-label">预览前 5 行 — 选择公司所在列：</p>
        <van-radio-group v-model="excelColumn" direction="horizontal">
          <van-radio
            v-for="(col, idx) in excelColumns"
            :key="idx"
            :name="idx"
          >
            {{ col.name }}
          </van-radio>
        </van-radio-group>
        <div class="preview-table">
          <div v-for="(row, ri) in excelPreview.slice(0, 5)" :key="ri" class="preview-row">
            {{ row }}
          </div>
        </div>
      </div>
    </van-dialog>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { queryApi } from '@/api'
import { addSearchHistory, getSearchHistory, downloadBlob } from '@/utils'
import { showToast, showLoadingToast, closeToast, showConfirmDialog } from 'vant'
import CertResultCard from '@/components/CertResultCard.vue'

const route = useRoute()
const router = useRouter()
const keyword = ref('')
const queryType = ref('')
const searchResult = ref(null)
const loading = ref(false)
const listLoading = ref(false)
const listFinished = ref(false)
const recentList = ref(getSearchHistory())

const typeOptions = [
  { value: '', label: '全部' },
  { value: 'business_license', label: '营业执照' },
  { value: 'food_license', label: '食品经营' },
  { value: 'food_production_license', label: '食品生产' },
  { value: 'product_report', label: '商品报告' },
]

// 批量查询
const showBatchInput = ref(false)
const batchText = ref('')

// Excel 上传
const showExcelUpload = ref(false)
const excelFileList = ref([])
const excelPreview = ref([])
const excelColumns = ref([])
const excelColumn = ref(0)
const excelRawData = ref(null)

const hasResults = computed(() => {
  return searchResult.value?.records?.length > 0
})

onMounted(() => {
  // 从路由参数读取 keyword（从效期看板点击跳转过来）
  const kw = route.query.keyword
  if (kw) {
    keyword.value = kw
    handleSearch()
  }
})

// 单个搜索
async function handleSearch() {
  if (!keyword.value.trim()) return
  loading.value = true
  searchResult.value = null
  addSearchHistory(keyword.value.trim())
  recentList.value = getSearchHistory()

  try {
    const res = await queryApi.single({
      keyword: keyword.value.trim(),
      document_type: queryType.value,
    })
    if (res.records?.length === 1) {
      searchResult.value = { type: 'single', data: res.records[0] }
    } else {
      searchResult.value = {
        type: 'batch',
        records: res.records || [],
        stats: res.stats || { found: 0, expiring: 0, expired: 0, missing: 0 },
      }
    }
  } catch (e) {
    showToast(e.message)
    searchResult.value = { type: 'batch', records: [], stats: { found: 0, expiring: 0, expired: 0, missing: 0 } }
  } finally {
    loading.value = false
  }
}

function handleClear() {
  searchResult.value = null
}

// 批量查询
async function handleBatchQuery() {
  const names = batchText.value.split('\n').map(s => s.trim()).filter(Boolean)
  if (!names.length) {
    showToast('请输入查询数据')
    return
  }

  loading.value = true
  searchResult.value = null
  showBatchInput.value = false

  try {
    const res = await queryApi.batch(names)
    searchResult.value = {
      type: 'batch',
      records: res.records || [],
      stats: res.stats || { found: 0, expiring: 0, expired: 0, missing: 0 },
    }
  } catch (e) {
    showToast(e.message)
  } finally {
    loading.value = false
  }
}

// Excel 上传
function afterExcelRead(file) {
  excelRawData.value = file.file
}

async function handleExcelUpload() {
  if (!excelRawData.value) {
    showToast('请先上传文件')
    return
  }

  showLoadingToast({ message: '正在解析 Excel...', forbidClick: true, duration: 0 })
  try {
    const res = await queryApi.uploadExcel(excelRawData.value)
    closeToast()

    excelPreview.value = res.preview || []
    excelColumns.value = res.columns || []

    if (res.records?.length) {
      // 直接有结果
      searchResult.value = {
        type: 'batch',
        records: res.records,
        stats: res.stats || { found: 0, expiring: 0, expired: 0, missing: 0 },
      }
      showExcelUpload.value = false
    }
  } catch (e) {
    closeToast()
    showToast('解析失败: ' + e.message)
  }
}

// 打包下载
async function handleBatchDownload() {
  if (!searchResult.value?.records?.length) {
    showToast('没有可下载的证照')
    return
  }

  const ids = searchResult.value.records.map(r => r.id)
  showLoadingToast({ message: '正在打包...', forbidClick: true, duration: 0 })

  try {
    const blob = await queryApi.download(ids)
    closeToast()
    downloadBlob(blob, `证照包_${new Date().toISOString().slice(0, 10)}.zip`)
    showToast('下载已开始')
  } catch (e) {
    closeToast()
    showToast('打包失败: ' + e.message)
  }
}

// 导出 CSV
function handleExportCsv() {
  if (!searchResult.value?.records?.length) {
    showToast('没有可导出的数据')
    return
  }

  const records = searchResult.value.records
  const header = '公司名称,证照类型,信用代码,到期日期,状态\n'
  const rows = records.map(r =>
    `${r.company_name},${r.license_type || ''},${r.credit_code || ''},${r.expire_date || ''},${r.expire_status || ''}`
  ).join('\n')

  const blob = new Blob(['﻿' + header + rows], { type: 'text/csv;charset=utf-8;' })
  downloadBlob(blob, `查询结果_${new Date().toISOString().slice(0, 10)}.csv`)
  showToast('导出成功')
}
</script>

<style scoped>
.query-page {
  padding-bottom: 16px;
}
.batch-section {
  margin: 0 16px 12px;
}
.result-section {
  padding: 0 16px;
}
.page-loading {
  display: flex;
  justify-content: center;
  padding: 40px;
}
.batch-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  padding: 12px 16px;
  background: #fff;
  border-radius: 8px;
  margin-bottom: 8px;
}
.summary-item {
  font-size: 13px;
  padding: 2px 8px;
  border-radius: 4px;
  background: #f5f6f8;
}
.summary-item.success { color: #07c160; }
.summary-item.warning { color: #ff976a; }
.summary-item.danger { color: #ee0a24; }
.summary-item.muted { color: #969799; }
.batch-actions {
  display: flex;
  gap: 8px;
  padding: 8px 0;
}
.empty-state {
  padding: 32px 16px;
}
.excel-preview {
  padding: 12px 16px;
}
.preview-label {
  font-size: 13px;
  color: #646566;
  margin-bottom: 8px;
}
.preview-table {
  margin-top: 8px;
  background: #f5f6f8;
  border-radius: 4px;
  padding: 8px;
}
.preview-row {
  font-size: 12px;
  color: #323233;
  padding: 4px 0;
  border-bottom: 1px solid #ebedf0;
}
.preview-row:last-child { border-bottom: none; }
.type-filter-row {
  display: flex;
  gap: 6px;
  padding: 0 16px 8px;
  overflow-x: auto;
  -webkit-overflow-scrolling: touch;
}
.type-chip {
  flex-shrink: 0;
  font-size: 12px;
  padding: 4px 12px;
  border-radius: 14px;
  background: #f5f6f8;
  color: #646566;
  cursor: pointer;
}
.type-chip.active {
  background: #1989fa;
  color: #fff;
}
</style>
