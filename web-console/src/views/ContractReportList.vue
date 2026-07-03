<template>
  <div class="contract-page">
    <van-nav-bar title="合同审查报告" left-arrow @click-left="router.push('/home')" />

    <van-notice-bar
      text="合同审查功能暂未上线，敬请期待"
      left-icon="info-o"
      color="#969799"
      background="#f5f6f8"
    />

    <!-- 统计 -->
    <div class="stats-row">
      <div class="stat-card" @click="filterLevel = ''">
        <div class="stat-num">{{ stats.total || 0 }}</div>
        <div class="stat-label">全部</div>
      </div>
      <div class="stat-card danger" @click="filterLevel = '高'">
        <div class="stat-num">{{ stats['高'] || 0 }}</div>
        <div class="stat-label">高风险</div>
      </div>
      <div class="stat-card warning" @click="filterLevel = '中'">
        <div class="stat-num">{{ stats['中'] || 0 }}</div>
        <div class="stat-label">中风险</div>
      </div>
      <div class="stat-card success" @click="filterLevel = '低'">
        <div class="stat-num">{{ stats['低'] || 0 }}</div>
        <div class="stat-label">低风险</div>
      </div>
    </div>

    <!-- 搜索 -->
    <van-search
      v-model="keyword"
      placeholder="搜索合同名称"
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
        @click="router.push(`/contract/reports/${r.id}`)"
      >
        <div class="card-top">
          <span class="contract-name">{{ r.contract_name }}</span>
          <van-tag :type="riskTagType(r.risk_level)" size="small">{{ r.risk_level }}风险</van-tag>
        </div>
        <div class="card-meta">
          <span class="meta-tag">{{ r.contract_type || '通用合同' }}</span>
          <span class="sep">|</span>
          <span>{{ r.review_time || r.created_at?.slice(0, 10) || '-' }}</span>
        </div>
        <div class="card-summary">
          {{ r.overall_conclusion?.slice(0, 60) || '暂无总体结论' }}
        </div>
      </div>
    </div>

    <van-empty v-else-if="!loading" description="暂无审查报告" />
    <van-loading v-if="loading" class="page-loading" size="24">加载中...</van-loading>
  </div>
</template>

<script setup>
import { ref, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { contractApi } from '@/api'
import { showToast } from 'vant'

const router = useRouter()
const records = ref([])
const stats = ref({})
const loading = ref(true)
const keyword = ref('')
const filterLevel = ref('')

onMounted(() => loadList())
watch(filterLevel, () => loadList())

async function loadList() {
  loading.value = true
  try {
    const res = await contractApi.list({
      risk_level: filterLevel.value,
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

function riskTagType(level) {
  if (level === '高') return 'danger'
  if (level === '中') return 'warning'
  return 'success'
}
</script>

<style scoped>
.contract-page { padding-bottom: 16px; }
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
.contract-name { font-size: 15px; font-weight: 600; color: #323233; }
.card-meta { font-size: 12px; color: #969799; margin-bottom: 4px; }
.meta-tag { color: #1989fa; }
.sep { margin: 0 6px; color: #dcdee0; }
.card-summary { font-size: 13px; color: #646566; }
</style>
