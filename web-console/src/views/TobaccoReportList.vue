<template>
  <div class="tobacco-page">
    <van-nav-bar title="烟草证比对报告" left-arrow @click-left="router.push('/home')" />

    <van-notice-bar
      text="烟草证比对功能暂未上线，敬请期待"
      left-icon="info-o"
      color="#969799"
      background="#f5f6f8"
    />

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
</script>

<style scoped>
.tobacco-page { padding-bottom: 16px; }
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
