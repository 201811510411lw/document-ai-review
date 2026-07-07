<template>
  <div class="review-page">
    <van-nav-bar :title="`${currentDocument.label}校验审核`" left-arrow @click-left="router.push('/scene1')" />

    <van-tabs v-model:active="activeDocumentType" class="document-tabs" @change="switchDocumentType">
      <van-tab
        v-for="item in documentTypeOptions"
        :key="item.value"
        :title="item.shortLabel"
        :name="item.value"
      />
    </van-tabs>

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card primary" @click="filterStatus = ''">
        <div class="stat-num">{{ stats.total || 0 }}</div>
        <div class="stat-label">全部校验</div>
      </div>
      <div class="stat-card warning" @click="filterStatus = 'pending'">
        <div class="stat-num">{{ stats.pending || 0 }}</div>
        <div class="stat-label">
          待审核
          <van-icon name="info-o" size="12" style="vertical-align:middle;margin-left:2px"
            @click.stop="showDialog({ message: '待审核 = 需要人工复核的记录\n规则审核未通过或关键字段缺失时进入待审核状态' })" />
        </div>
      </div>
      <div class="stat-card success" @click="filterStatus = 'confirmed'">
        <div class="stat-num">{{ stats.confirmed || 0 }}</div>
        <div class="stat-label">
          已认可
          <van-icon name="info-o" size="12" style="vertical-align:middle;margin-left:2px"
            @click.stop="showDialog({ message: '已认可 = 已人工审核通过\n管理员手动确认为有效的记录' })" />
        </div>
      </div>
      <div class="stat-card danger" @click="filterStatus = 'flagged'">
        <div class="stat-num">{{ stats.flagged || 0 }}</div>
        <div class="stat-label">
          异常
          <van-icon name="info-o" size="12" style="vertical-align:middle;margin-left:2px"
            @click.stop="showDialog({ message: '异常记录包含三类：\n1. 审核失败（自动审核未通过）\n2. 人工驳回（管理员审核后驳回）\n3. 高风险（关键字段不匹配等）' })" />
        </div>
      </div>
    </div>

    <!-- 搜索栏 -->
    <van-search
      v-model="keyword"
      :placeholder="`搜索${currentDocument.subjectLabel}`"
      shape="round"
      clearable
      @search="loadList"
    />

    <!-- 当前筛选指示 -->
    <div v-if="filterStatus || keyword" class="filter-bar">
      <div class="filter-tags">
        <span v-if="filterStatus" class="filter-tag">
          {{ filterStatus === 'pending' ? '待审核' : filterStatus === 'confirmed' ? '已认可' : '异常' }}
          <van-icon name="cross" @click="filterStatus = ''" />
        </span>
        <span v-if="keyword" class="filter-tag">
          "{{ keyword }}"
          <van-icon name="cross" @click="keyword = ''; loadList()" />
        </span>
      </div>
      <span v-if="stats.total !== undefined" class="result-count">{{ stats.total }} 条结果</span>
    </div>

    <!-- 待审核提示 -->
    <van-notice-bar
      v-if="stats.pending > 0"
      :text="`有 ${stats.pending} 条记录待人工审核，匹配率低于 60%`"
      color="#ee0a24"
      background="#fff2f0"
      left-icon="info-o"
    />

    <!-- 列表（分页加载） -->
    <div v-if="displayRecords.length" class="record-list">
      <van-list
        v-model:loading="listLoading"
        :finished="listFinished"
        finished-text="已全部展示"
        @load="onLoadMore"
      >
        <div
          v-for="r in displayRecords"
          :key="r.id"
          class="record-card"
          @click="goToDetail(r.id)"
        >
          <div class="card-top">
            <span class="company-name">{{ r.company_name }}</span>
            <van-tag :type="statusTagType(r.review_status)" size="small">
              {{ statusText(r.review_status) }}
            </van-tag>
          </div>
          <div class="card-meta">
            <span>{{ r.license_type || currentDocument.label || '未识别' }}</span>
            <span class="sep">|</span>
            <span>匹配率: {{ formatRatio(r.match_ratio) }}</span>
            <span class="sep">|</span>
            <span>{{ r.expire_date || '无到期日' }}</span>
          </div>
          <div class="card-bottom">
            <span class="batch-no">批次: {{ r.created_at?.slice(0, 10) || '-' }}</span>
            <van-icon name="arrow" />
          </div>
        </div>
      </van-list>
    </div>

    <van-empty v-else-if="!loading" description="暂无校验记录" />

    <van-loading v-if="loading" class="page-loading" size="24">加载中...</van-loading>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { reviewApi } from '@/api'
import { showDialog, showToast } from 'vant'

const router = useRouter()
const route = useRoute()
const records = ref([])
const stats = ref({})
const loading = ref(true)
const creating = ref(false)
const keyword = ref('')
const filterStatus = ref('')
const activeDocumentType = ref('')
// 分页状态
const displayRecords = ref([])
const listLoading = ref(false)
const listFinished = ref(false)
const pageSize = 20

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
]

const documentTypeMap = Object.fromEntries(documentTypeOptions.map(item => [item.value, item]))

const documentType = computed(() => {
  const queryType = String(route.query.document_type || 'business_license')
  return documentTypeMap[queryType] ? queryType : 'business_license'
})

const currentDocument = computed(() => documentTypeMap[documentType.value])

let isMounted = false

onMounted(() => {
  isMounted = true
  if (route.query.document_type) {
    sessionStorage.setItem('review_doc_type', route.query.document_type)
  } else {
    // 无 query → 可能是从详情返回，从 sessionStorage 恢复上次的标签
    const saved = sessionStorage.getItem('review_doc_type')
    if (saved && documentTypeMap[saved]) {
      router.replace({ path: '/review', query: { document_type: saved } })
      return  // 重定向后 onMounted 会再次触发
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

async function loadList() {
  loading.value = true
  displayRecords.value = []
  listFinished.value = false
  try {
    const res = await reviewApi.list({
      review_status: filterStatus.value,
      keyword: keyword.value,
      document_type: documentType.value,
      limit: 200,
    })
    records.value = res.records || []
    stats.value = res.stats || {}
    // 首次显示前 pageSize 条
    displayRecords.value = records.value.slice(0, pageSize)
    if (records.value.length <= pageSize) {
      listFinished.value = true
    }
  } catch (e) {
    showToast('加载失败')
  } finally {
    loading.value = false
  }
}

function onLoadMore() {
  const current = displayRecords.value.length
  const next = current + pageSize
  if (current >= records.value.length) {
    listFinished.value = true
    listLoading.value = false
    return
  }
  displayRecords.value = records.value.slice(0, next)
  listLoading.value = false
  if (next >= records.value.length) {
    listFinished.value = true
  }
}

function switchDocumentType(name) {
  if (name === documentType.value) return
  sessionStorage.setItem('review_doc_type', name)
  router.push({
    path: '/review',
    query: { document_type: name },
  })
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

function statusTagType(status) {
  if (status === 'pending') return 'danger'
  if (status === 'confirmed') return 'success'
  if (status === 'flagged') return 'warning'
  return 'default'
}

function statusText(status) {
  if (status === 'pending') return '待审核'
  if (status === 'confirmed') return '已认可'
  if (status === 'flagged') return '异常'
  return '无需审核'
}
</script>

<style scoped>
.review-page { padding-bottom: 16px; }
.document-tabs { background: #fff; }
.stats-row {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  padding: 12px 16px;
}
.stat-card {
  border-radius: 8px;
  padding: 14px;
  color: #fff;
  text-align: center;
  cursor: pointer;
}
.stat-card:active { opacity: 0.8; }
.stat-card.primary { background: linear-gradient(135deg, #667eea, #764ba2); }
.stat-card.warning { background: linear-gradient(135deg, #f093fb, #f5576c); }
.stat-card.success { background: linear-gradient(135deg, #4facfe, #00f2fe); }
.stat-card.danger { background: linear-gradient(135deg, #fa709a, #fee140); }
.stat-num { font-size: 26px; font-weight: 700; }
.stat-label { font-size: 12px; opacity: 0.9; margin-top: 2px; }
.toolbar {
  display: flex;
  justify-content: flex-end;
  padding: 0 16px 10px;
  background: #f7f8fa;
}
.page-loading { display: flex; justify-content: center; padding: 40px; }
.record-list { padding: 0 16px; }
.record-card {
  background: #fff;
  border-radius: 8px;
  padding: 12px 16px;
  margin-bottom: 10px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
  cursor: pointer;
}
.record-card:active { background: #f5f6f8; }
.card-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
}
.company-name { font-size: 15px; font-weight: 600; color: #323233; }
.card-meta { font-size: 12px; color: #969799; margin-bottom: 6px; }
.sep { margin: 0 6px; color: #dcdee0; }
.card-bottom {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding-top: 6px;
  border-top: 1px solid #f5f6f8;
  font-size: 12px;
  color: #969799;
}
/* 筛选栏 */
.filter-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 6px 16px;
  background: #f7f8fa;
}
.filter-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}
.filter-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  padding: 3px 8px;
  border-radius: 12px;
  background: #e8f0fe;
  color: #1989fa;
}
.filter-tag .van-icon {
  font-size: 12px;
  cursor: pointer;
}
.result-count {
  font-size: 12px;
  color: #969799;
  white-space: nowrap;
}
</style>
