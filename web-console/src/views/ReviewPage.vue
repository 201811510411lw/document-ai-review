<template>
  <div class="review-page">
    <van-nav-bar title="营业执照校验审核" left-arrow @click-left="router.push('/scene1')" />

    <!-- 统计卡片 -->
    <div class="stats-row">
      <div class="stat-card primary" @click="filterStatus = ''">
        <div class="stat-num">{{ stats.total || 0 }}</div>
        <div class="stat-label">全部校验</div>
      </div>
      <div class="stat-card warning" @click="filterStatus = 'pending'">
        <div class="stat-num">{{ stats.pending || 0 }}</div>
        <div class="stat-label">待审核</div>
      </div>
      <div class="stat-card success" @click="filterStatus = 'confirmed'">
        <div class="stat-num">{{ stats.confirmed || 0 }}</div>
        <div class="stat-label">已认可</div>
      </div>
      <div class="stat-card danger" @click="filterStatus = 'flagged'">
        <div class="stat-num">{{ stats.flagged || 0 }}</div>
        <div class="stat-label">已标记</div>
      </div>
    </div>

    <!-- 搜索栏 -->
    <van-search
      v-model="keyword"
      placeholder="搜索公司名"
      shape="round"
      clearable
      @search="loadList"
    />

    <!-- 待审核提示 -->
    <van-notice-bar
      v-if="stats.pending > 0"
      :text="`有 ${stats.pending} 条记录待人工审核，匹配率低于 60%`"
      color="#ee0a24"
      background="#fff2f0"
      left-icon="info-o"
    />

    <!-- 列表 -->
    <div v-if="records.length" class="record-list">
      <div
        v-for="r in records"
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
          <span>{{ r.license_type || '未识别' }}</span>
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
    </div>

    <van-empty v-else-if="!loading" description="暂无校验记录" />

    <van-loading v-if="loading" class="page-loading" size="24">加载中...</van-loading>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { reviewApi } from '@/api'
import { showToast } from 'vant'

const router = useRouter()
const records = ref([])
const stats = ref({})
const loading = ref(true)
const keyword = ref('')
const filterStatus = ref('')

onMounted(() => loadList())

watch(filterStatus, () => loadList())

async function loadList() {
  loading.value = true
  try {
    const res = await reviewApi.list({
      review_status: filterStatus.value,
      keyword: keyword.value,
      document_type: 'business_license',
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

function goToDetail(id) {
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
  if (status === 'flagged') return '已标记'
  return '无需审核'
}
</script>

<style scoped>
.review-page { padding-bottom: 16px; }
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
</style>
