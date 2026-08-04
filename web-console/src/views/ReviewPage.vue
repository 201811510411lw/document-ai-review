<template>
  <div class="review-page">
    <ReviewQueueView
      v-model:keyword="keyword"
      :current-document="currentDocument"
      :document-options="documentTypeOptions"
      :active-document-type="activeDocumentType"
      :stats="stats"
      :filter-status="filterStatus"
      :filtered-total="filteredTotal"
      :records="displayRecords"
      :loading="loading"
      :creating="creating"
      :current-page="pagination.currentPage"
      :total-pages="pagination.totalPages"
      :create-button-text="createButtonText"
      :on-switch-document="switchDocumentType"
      :on-set-filter="setFilterStatus"
      :on-search="loadList"
      :on-create="createReviewFromSrm"
      :on-open="goToDetail"
      :on-set-page="setCurrentPage"
      :record-title="recordTitle"
      :record-primary-meta="recordPrimaryMeta"
      :record-secondary-meta="recordSecondaryMeta"
      :record-footer-text="recordFooterText"
      :format-ratio="formatRatio"
      :status-text="statusText"
    />

  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { reviewApi } from '@/api'
import { showToast } from 'vant'
import ReviewQueueView from '@/features/review/ReviewQueueView.vue'
import { fetchCurrentReviewPage, reviewPagination } from '@/features/review/queueModel.js'

const router = useRouter()
const route = useRoute()
const records = ref([])
const stats = ref({})
const loading = ref(true)
const creating = ref(false)
const keyword = ref('')
const filterStatus = ref('')
const activeDocumentType = ref('')
const currentPage = ref(1)
const filteredTotal = ref(0)
const pageSize = 20
const pagination = computed(() => reviewPagination(filteredTotal.value, currentPage.value, pageSize))
const displayRecords = computed(() => records.value)
const documentTypeOptions = [
  {
    value: 'business_license',
    label: '营业执照',
    shortLabel: '营业执照',
    subjectLabel: '公司名',
  },
  {
    value: 'food_license',
    label: '食品经营许可证',
    shortLabel: '食品经营',
    subjectLabel: '经营者名称',
  },
  {
    value: 'food_production_license',
    label: '食品生产许可证',
    shortLabel: '食品生产',
    subjectLabel: '生产者名称',
  },
  {
    value: 'product_report',
    label: '商品报告',
    shortLabel: '商品报告',
    subjectLabel: '样品名称/供应商',
  },
  {
    value: 'batch_report',
    label: '商品批次报告',
    shortLabel: '批次报告',
    subjectLabel: '订单号/商品名/供应商',
  },
]

const documentTypeMap = Object.fromEntries(documentTypeOptions.map(item => [item.value, item]))

const documentType = computed(() => {
  const queryType = String(route.query.document_type || 'business_license')
  return documentTypeMap[queryType] ? queryType : 'business_license'
})

const currentDocument = computed(() => documentTypeMap[documentType.value])
const createButtonText = computed(() => (
  documentType.value === 'batch_report'
    ? '随机拉取批次'
    : `发起${currentDocument.value.shortLabel}审核`
))

let isMounted = false
let listRequestId = 0

onMounted(() => {
  isMounted = true
  if (route.query.document_type) {
    sessionStorage.setItem('review_doc_type', route.query.document_type)
  } else {
    // 无 query → 可能是从详情返回，从 sessionStorage 恢复上次的标签
    const saved = sessionStorage.getItem('review_doc_type')
    if (saved && documentTypeMap[saved]) {
      router.replace({ path: '/review', query: { document_type: saved } })
      // replace 同路径组件不复用，手动继续加载
      activeDocumentType.value = saved
      loadList()
      return
    }
  }
  activeDocumentType.value = documentType.value
  loadList()
})

watch(filterStatus, () => {
  if (isMounted) loadList()
})

watch(documentType, (value) => {
  activeDocumentType.value = value
  filterStatus.value = ''
  if (isMounted) loadList()
})

async function loadList(requestedPage = 1, { resetContext = true } = {}) {
  const requestId = ++listRequestId
  loading.value = true
  const targetPage = Math.max(1, Number(requestedPage) || 1)
  if (resetContext) {
    currentPage.value = targetPage
    records.value = []
    stats.value = {}
    filteredTotal.value = 0
  }
  try {
    const result = await fetchCurrentReviewPage({
      requestedPage: targetPage,
      pageSize,
      isCurrent: () => requestId === listRequestId,
      fetchPage: ({ limit, offset }) => reviewApi.list({
        review_status: filterStatus.value,
        keyword: keyword.value,
        document_type: documentType.value,
        limit,
        offset,
      }),
    })
    if (!result) return

    const { response: res, currentPage: resolvedPage } = result
    records.value = res.records || []
    stats.value = res.stats || {}
    filteredTotal.value = res.filtered_total ?? records.value.length
    currentPage.value = resolvedPage
  } catch (e) {
    if (requestId === listRequestId) showToast('加载失败')
  } finally {
    if (requestId === listRequestId) loading.value = false
  }
}

function setCurrentPage(page) {
  loadList(page, { resetContext: false })
  window.scrollTo({ top: 0, behavior: 'smooth' })
}

function switchDocumentType(name) {
  if (name === documentType.value) return
  sessionStorage.setItem('review_doc_type', name)
  router.push({
    path: '/review',
    query: { document_type: name },
  })
}

function setFilterStatus(status) {
  filterStatus.value = status
}

async function createReviewFromSrm() {
  creating.value = true
  try {
    const result = await reviewApi.createFromSrm(documentType.value)
    showToast('已发起审核')
    await loadList()
    if (result?.task_id) {
      router.push(`/review/${result.task_id}`)
    }
  } catch (e) {
    showToast(e.message || '发起审核失败')
  } finally {
    creating.value = false
  }
}

function goToDetail(id) {
  sessionStorage.setItem('review_doc_type', documentType.value)
  router.push(`/review/${id}`)
}

function formatRatio(val) {
  if (val === null || val === undefined) return '-'
  return Math.round(val) + '%'
}

function recordTitle(record) {
  if (documentType.value === 'batch_report') {
    return record.product_name || record.sku_name || record.company_name || record.order_number || '未识别商品批次'
  }
  return record.company_name || record.product_name || '未识别主体名称'
}

function recordPrimaryMeta(record) {
  if (documentType.value === 'batch_report') {
    return record.order_number ? `订单: ${record.order_number}` : (record.license_type || currentDocument.value.label)
  }
  return record.license_type || currentDocument.value.label || '未识别'
}

function recordSecondaryMeta(record) {
  if (documentType.value === 'batch_report') {
    return record.production_date || record.batch_no || record.vendor_name || record.company_name || '无批次信息'
  }
  return record.expire_date || '无到期日'
}

function recordFooterText(record) {
  if (documentType.value === 'batch_report') {
    const supplier = record.vendor_name || record.company_name || '-'
    return `供应商: ${supplier}`
  }
  return `批次: ${record.created_at?.slice(0, 10) || '-'}`
}

function statusText(status) {
  if (status === 'pending') return '待审核'
  if (status === 'confirmed') return '已认可'
  if (status === 'flagged') return '异常'
  return '无需审核'
}
</script>
