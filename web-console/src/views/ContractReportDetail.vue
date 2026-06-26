<template>
  <div class="detail-page">
    <van-nav-bar title="审查报告" left-arrow @click-left="router.back()" />

    <div v-if="loading" class="page-loading">
      <van-loading size="24">加载中...</van-loading>
    </div>

    <template v-if="report">
      <!-- 头部 -->
      <div class="detail-header">
        <h2 class="contract-title">{{ report.contract_name }}</h2>
        <div class="header-tags">
          <van-tag :type="riskTagType" size="medium">{{ report.risk_level }}风险</van-tag>
          <van-tag plain size="medium">{{ report.contract_type || '通用合同' }}</van-tag>
        </div>
        <div class="review-time">审查时间: {{ report.review_time || report.created_at?.slice(0, 10) || '-' }}</div>
      </div>

      <!-- 总体结论 -->
      <div class="section-title">总体结论</div>
      <div class="conclusion-box">
        {{ report.overall_conclusion || '暂无总体结论' }}
      </div>

      <!-- 审查项列表 -->
      <div class="section-title">审查明细</div>
      <div v-if="report.review_items && report.review_items.length" class="review-items">
        <div
          v-for="(item, idx) in report.review_items"
          :key="idx"
          class="review-item"
        >
          <div class="item-header">
            <van-tag :type="itemLevelTag(item.level)" size="small">
              {{ item.level || '中' }}风险
            </van-tag>
            <span class="item-title">{{ item.title || `审查项 ${idx + 1}` }}</span>
          </div>

          <div v-if="item.clause" class="item-field">
            <span class="field-label">涉及条款</span>
            <span class="field-val">{{ item.clause }}</span>
          </div>

          <div v-if="item.original_text" class="item-field">
            <span class="field-label">原文引用</span>
            <div class="quote-box">{{ item.original_text }}</div>
          </div>

          <div v-if="item.suggestion" class="item-field">
            <span class="field-label">修改建议</span>
            <span class="field-val suggestion">{{ item.suggestion }}</span>
          </div>

          <div v-if="item.law_basis" class="item-field">
            <span class="field-label">法律依据</span>
            <span class="field-val law">{{ item.law_basis }}</span>
          </div>
        </div>
      </div>
      <van-empty v-else description="暂无审查明细" />
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { contractApi } from '@/api'
import { showToast } from 'vant'

const router = useRouter()
const route = useRoute()
const report = ref(null)
const loading = ref(true)

const riskTagType = computed(() => {
  const lv = report.value?.risk_level
  if (lv === '高') return 'danger'
  if (lv === '中') return 'warning'
  return 'success'
})

onMounted(async () => {
  try {
    const res = await contractApi.detail(route.params.id)
    report.value = res.report || res
  } catch (e) {
    showToast('加载失败')
  } finally {
    loading.value = false
  }
})

function itemLevelTag(level) {
  if (level === '高') return 'danger'
  if (level === '中') return 'warning'
  return 'success'
}
</script>

<style scoped>
.detail-page { padding-bottom: 32px; }
.page-loading { display: flex; justify-content: center; padding: 60px; }
.detail-header {
  background: #fff;
  padding: 20px 16px;
  margin-bottom: 12px;
}
.contract-title { font-size: 18px; font-weight: 600; margin: 0 0 8px; }
.header-tags { display: flex; gap: 8px; margin-bottom: 8px; }
.review-time { font-size: 12px; color: #969799; }
.section-title {
  font-size: 14px; font-weight: 600; color: #323233;
  padding: 16px 16px 8px;
}
.conclusion-box {
  margin: 0 16px;
  background: #f5f6f8;
  border-radius: 8px;
  padding: 14px;
  font-size: 14px;
  color: #323233;
  line-height: 1.6;
}
.review-items { margin: 0 16px; display: flex; flex-direction: column; gap: 10px; }
.review-item {
  background: #fff;
  border-radius: 8px;
  padding: 14px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.04);
}
.item-header {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 10px;
}
.item-title {
  font-size: 14px;
  font-weight: 600;
  color: #323233;
}
.item-field {
  margin-bottom: 8px;
  font-size: 13px;
}
.field-label {
  display: block;
  font-size: 11px;
  color: #969799;
  margin-bottom: 2px;
}
.field-val { color: #323233; }
.field-val.suggestion { color: #07c160; }
.field-val.law { color: #667eea; }
.quote-box {
  background: #f5f6f8;
  border-radius: 4px;
  padding: 8px 10px;
  font-size: 13px;
  color: #646566;
  line-height: 1.5;
  border-left: 3px solid #1989fa;
}
</style>
