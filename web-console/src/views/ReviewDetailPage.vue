<template>
  <div class="detail-page">
    <van-nav-bar title="校验详情" left-arrow @click-left="router.back()" />

    <div v-if="loading" class="page-loading">
      <van-loading size="24">加载中...</van-loading>
    </div>

    <template v-if="record">
      <!-- 核验结果横幅 -->
      <div v-if="verificationResult" class="verify-banner" :class="verificationResult.result">
        <van-icon :name="verificationResult.result === 'pass' ? 'success' : 'cross'" :size="18" />
        <span class="verify-text">
          {{ verificationResult.result === 'pass' ? '核验通过' : '核验未通过' }}
        </span>
        <span v-if="verificationResult.failed_items?.length" class="verify-detail">
          （{{ verificationResult.failed_items.length }} 项不匹配）
        </span>
        <van-icon
          v-if="verificationResult.failed_items?.length"
          :name="showFailDetails ? 'arrow-up' : 'arrow-down'"
          class="toggle-icon"
          @click="showFailDetails = !showFailDetails"
        />
      </div>
      <!-- 失败详情展开 -->
      <div v-if="showFailDetails && verificationResult?.failed_items?.length" class="fail-details">
        <div v-for="item in verificationResult.failed_items" :key="item.field" class="fail-item">
          <van-icon name="cross" color="#ee0a24" size="14" />
          <span class="fail-field">{{ item.field }}</span>
          <span class="fail-reason">{{ item.reason }}</span>
        </div>
      </div>

      <!-- 头部信息 -->
      <div class="detail-header">
        <h2 class="company-name">{{ detailTitle }}</h2>
        <div class="meta-row">
          <span class="meta-label">{{ record.license_type || detailDocumentLabel }}</span>
          <span class="meta-sep">|</span>
          <span class="meta-label">匹配率</span>
          <span class="ratio-value" :class="ratioClass">{{ formatRatio(record.match_ratio) }}</span>
          <span v-if="record.field_coverage" class="coverage-badge">
            字段 {{ record.field_coverage.coverage }}%
          </span>
        </div>
        <!-- 批次报告订单号（可选复制） -->
        <div v-if="record.document_type === 'batch_report' && record.order_number" class="order-number-row">
          <span class="order-label">订单号</span>
          <span class="order-value">{{ record.order_number }}</span>
          <van-icon name="copy" class="copy-icon" @click="copyOrderNumber" />
        </div>
        <van-tag :type="statusTagType" size="medium">{{ statusText }}</van-tag>
        <div v-if="manualReviewReasons.length" class="review-reasons">
          <div v-for="reason in manualReviewReasons" :key="reason" class="review-reason">
            {{ reason }}
          </div>
        </div>
        <div v-if="record.review_comment" class="comment">
          备注: {{ record.review_comment }}
        </div>
      </div>

      <!-- 字段比对 -->
      <div class="section-title">字段比对</div>
      <div class="field-list">
        <div v-for="(group, gIdx) in fieldGroups" :key="gIdx" class="field-group">
          <div class="group-title">{{ group.label }}</div>
          <div v-for="(field, idx) in group.fields" :key="idx" class="field-item">
            <div class="field-name">
              {{ field.field }}
              <span v-if="field.confidence" class="confidence-badge" :class="'conf-' + field.confidence.toLowerCase()">
                {{ field.confidence }}
              </span>
            </div>
            <div class="field-values">
              <!-- 识别值 = 数据库值 => 显示"一致" -->
              <div v-if="field.recognized && field.expected && field.recognized === field.expected" class="value-row match-row">
                <van-icon name="check" color="#07c160" size="14" />
                <span class="value-text">{{ field.recognized }}</span>
              </div>
              <!-- 识别值 != 数据库值 => 两行对比 -->
              <template v-else-if="field.recognized && field.expected && field.recognized !== field.expected">
                <div class="value-row mismatch-row">
                  <span class="value-label">识别值</span>
                  <span class="value-text mismatch">{{ field.recognized }}</span>
                  <van-icon name="cross" color="#ee0a24" size="14" />
                </div>
                <div class="value-row">
                  <span class="value-label">数据库</span>
                  <span class="value-text" style="color:#07c160">{{ field.expected }}</span>
                  <van-icon name="check" color="#07c160" size="14" />
                </div>
              </template>
              <!-- 只有识别值（无数据库对照） -->
              <div v-else-if="field.recognized && !field.expected" class="value-row">
                <van-icon name="check" color="#07c160" size="14" />
                <span class="value-text">{{ field.recognized }}</span>
              </div>
              <!-- 只有数据库值 -->
              <div v-else-if="field.expected && !field.recognized" class="value-row">
                <span class="value-label">数据库</span>
                <span class="value-text">{{ field.expected }}</span>
                <van-icon name="warning-o" color="#ff976a" size="14" />
              </div>
              <!-- 都为空 -->
              <div v-else class="value-row empty-row">
                <van-icon name="info-o" color="#969799" size="14" />
                <span class="value-text empty">{{ field.missing_recognized ? '未识别到' : '-' }}</span>
              </div>
              <!-- LLM 匹配理由 -->
              <div v-if="field.match_reason" class="match-reason-row">
                <span class="reason-icon">💡</span>
                <span class="reason-text">{{ field.match_reason }}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      <!-- 原文件 -->
      <div class="section-title">原文件</div>
      <div class="file-section">
        <van-button
          v-if="record.source_file_url"
          plain
          type="primary"
          size="small"
          icon="eye-o"
          @click.stop="openSourceFile"
        >
          {{ sourceFileButtonText }}
        </van-button>
        <span v-else class="no-file">无附件</span>
      </div>

      <!-- 审核操作 -->
      <div v-if="record.review_status === 'pending'" class="action-section">
        <div class="section-title">审核操作</div>
        <van-field
          v-model="comment"
          placeholder="审核备注（可选）"
          type="textarea"
          rows="2"
          autosize
        />
        <div class="action-buttons">
          <van-button type="primary" block round :loading="submitting" @click="handleConfirm">
            ✅ 认可识别结果
          </van-button>
          <van-button type="warning" block round plain :loading="submitting" @click="handleFlag">
            ❌ 标记异常
          </van-button>
        </div>
      </div>

      <div v-else class="action-section">
        <div class="already-reviewed">
          <van-icon :name="record.review_status === 'confirmed' ? 'success' : 'warning'" />
          此记录已{{ statusText }}
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { reviewApi } from '@/api'
import { showToast, showConfirmDialog } from 'vant'

const router = useRouter()
const route = useRoute()

const record = ref(null)
const loading = ref(true)
const submitting = ref(false)
const openingSourceFile = ref(false)
const comment = ref('')
const showFailDetails = ref(true)

const verificationResult = computed(() => {
  return record.value?.verification_result || null
})

const detailDocumentLabel = computed(() => {
  const typeMap = {
    'business_license': '营业执照',
    'food_license': '食品经营许可证',
    'food_production_license': '食品生产许可证',
    'product_report': '商品报告',
    'batch_report': '商品批次报告',
    'tobacco_license': '烟草专卖零售许可证',
    'business_tobacco_consistency': '营业执照与烟草证一致性',
  }
  return typeMap[record.value?.document_type] || record.value?.license_type || '审核材料'
})

const detailTitle = computed(() => {
  if (record.value?.document_type === 'batch_report') {
    return (
      record.value?.product_name ||
      record.value?.sku_name ||
      record.value?.company_name ||
      record.value?.order_number ||
      '未识别商品批次'
    )
  }
  return record.value?.company_name || record.value?.product_name || '未识别主体名称'
})

const sourceFileButtonText = computed(() => (
  record.value?.document_type === 'batch_report' ? '查看批次报告原件' : '查看证照原图'
))

const fieldGroups = computed(() => {
  const allFields = record.value?.validation_fields || []
  if (!allFields.length) return []

  // 按字段名分组
  const groups = []
  const typeFields = []
  const infoFields = []
  const validityFields = []
  const otherFields = []

  for (const f of allFields) {
    const name = f.field || ''
    if (name.includes('证照类型') || name.includes('文档类型')) {
      typeFields.push(f)
    } else if (name.includes('有效期') || name.includes('效期') || name.includes('到期')) {
      validityFields.push(f)
    } else if (name.includes('名称') || name.includes('代码') || name.includes('信用') ||
               name.includes('法人') || name.includes('负责') || name.includes('住所') ||
               name.includes('经营') || name.includes('地址') || name.includes('编号')) {
      infoFields.push(f)
    } else {
      otherFields.push(f)
    }
  }

  if (typeFields.length) groups.push({ label: '证照类型', fields: typeFields })
  if (infoFields.length) groups.push({ label: '企业信息', fields: infoFields })
  if (validityFields.length) groups.push({ label: '有效期', fields: validityFields })
  if (otherFields.length) groups.push({ label: '其他', fields: otherFields })

  return groups
})

const manualReviewReasons = computed(() => {
  const reasons = record.value?.manual_review?.reasons || record.value?.manual_review_reasons || []
  return Array.isArray(reasons) ? reasons.filter(Boolean) : []
})

const ratioClass = computed(() => {
  const ratio = record.value?.match_ratio
  if (ratio === null || ratio === undefined) return ''
  if (ratio >= 80) return 'ratio-good'
  if (ratio >= 60) return 'ratio-ok'
  return 'ratio-bad'
})

const statusTagType = computed(() => {
  const s = record.value?.review_status
  if (s === 'pending') return 'danger'
  if (s === 'confirmed') return 'success'
  if (s === 'flagged') return 'warning'
  return 'default'
})

const statusText = computed(() => {
  const s = record.value?.review_status
  if (s === 'pending') return '待审核'
  if (s === 'confirmed') return '已认可'
  if (s === 'flagged') return '已标记异常'
  return '无需审核'
})

onMounted(async () => {
  const id = route.params.id
  try {
    const res = await reviewApi.detail(id)
    record.value = res.record || res
  } catch (e) {
    showToast('加载失败')
  } finally {
    loading.value = false
  }
})

function formatRatio(val) {
  if (val === null || val === undefined) return '-'
  return Math.round(val) + '%'
}

function openSourceFile() {
  if (openingSourceFile.value) return
  const url = record.value?.source_file_url
  if (!url) {
    showToast('无附件地址')
    return
  }
  openingSourceFile.value = true
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (!opened) {
    showToast('浏览器阻止打开，请允许弹窗后重试')
  }
  window.setTimeout(() => {
    openingSourceFile.value = false
  }, 800)
}

async function handleConfirm() {
  showConfirmDialog({
    title: '确认认可',
    message: '认可后将标记为"已认可"，数据库字段保持不变',
  }).then(async () => {
    submitting.value = true
    try {
      await reviewApi.confirm(route.params.id, comment.value)
      showToast('已认可')
      record.value.review_status = 'confirmed'
    } catch (e) {
      showToast('操作失败: ' + e.message)
    } finally {
      submitting.value = false
    }
  }).catch(() => {})
}

function copyOrderNumber() {
  const num = record.value?.order_number
  if (!num) return
  navigator.clipboard.writeText(num).then(() => {
    showToast('已复制订单号')
  }).catch(() => {
    // 降级方案
    const ta = document.createElement('textarea')
    ta.value = num
    ta.style.position = 'fixed'
    ta.style.opacity = '0'
    document.body.appendChild(ta)
    ta.select()
    document.execCommand('copy')
    document.body.removeChild(ta)
    showToast('已复制订单号')
  })
}

async function handleFlag() {
  showConfirmDialog({
    title: '标记异常',
    message: '标记为异常后将进入异常记录列表',
  }).then(async () => {
    submitting.value = true
    try {
      await reviewApi.flag(route.params.id, comment.value)
      showToast('已标记')
      record.value.review_status = 'flagged'
    } catch (e) {
      showToast('操作失败: ' + e.message)
    } finally {
      submitting.value = false
    }
  }).catch(() => {})
}
</script>

<style scoped>
.detail-page { padding-bottom: 32px; }
.page-loading { display: flex; justify-content: center; padding: 60px; }

/* 核验结果横幅 */
.verify-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  margin: 0 0 2px;
  font-size: 14px;
  font-weight: 600;
}
.verify-banner.pass {
  background: #e8fae8;
  color: #07c160;
}
.verify-banner.fail {
  background: #ffeeed;
  color: #ee0a24;
}
.verify-detail {
  font-weight: 400;
  font-size: 13px;
  opacity: 0.8;
}
.toggle-icon {
  margin-left: auto;
  cursor: pointer;
  font-size: 16px;
}
.fail-details {
  background: #fff2f0;
  margin: 0 0 2px;
  padding: 8px 16px 12px;
  border-bottom: 1px solid #ffccc7;
}
.fail-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  margin-top: 6px;
}
.fail-field {
  font-weight: 600;
  color: #323233;
  min-width: 80px;
}
.fail-reason {
  color: #ee0a24;
  font-size: 12px;
}

/* 头部 */
.detail-header {
  background: #fff;
  padding: 16px;
  margin-bottom: 8px;
}
.company-name { font-size: 18px; font-weight: 600; margin: 0 0 6px; }
.meta-row { display: flex; align-items: center; gap: 6px; margin-bottom: 8px; font-size: 13px; }
.meta-label { color: #969799; }
.meta-sep { color: #dcdee0; }
.ratio-value { font-size: 20px; font-weight: 700; }
.ratio-good { color: #07c160; }
.ratio-ok { color: #ff976a; }
.ratio-bad { color: #ee0a24; }
.coverage-badge {
  font-size: 11px;
  color: #969799;
  background: #f5f6f8;
  padding: 1px 6px;
  border-radius: 8px;
  font-weight: 400;
}
.review-reasons { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; }
.review-reason {
  width: fit-content;
  max-width: 100%;
  color: #ee0a24;
  background: #fff2f0;
  border: 1px solid #ffccc7;
  border-radius: 4px;
  padding: 4px 8px;
  font-size: 12px;
  line-height: 1.4;
}
.order-number-row {
  display: flex; align-items: center; gap: 6px;
  margin: 6px 0 4px; font-size: 13px;
  background: #f5f6f8; padding: 4px 8px; border-radius: 4px;
  user-select: text; -webkit-user-select: text;
}
.order-label { color: #969799; font-size: 12px; flex-shrink: 0; }
.order-value { color: #323233; font-weight: 500; flex: 1; }
.copy-icon { font-size: 14px; color: #1989fa; cursor: pointer; flex-shrink: 0; }
.comment { margin-top: 8px; font-size: 13px; color: #ee0a24; background: #fff2f0; padding: 6px 10px; border-radius: 4px; }

.section-title {
  font-size: 14px; font-weight: 600; color: #323233;
  padding: 14px 16px 8px;
}

/* 字段分组 */
.field-group {
  margin: 0 12px 8px;
  background: #fff;
  border-radius: 8px;
  overflow: hidden;
}
.group-title {
  font-size: 12px;
  font-weight: 600;
  color: #969799;
  padding: 10px 14px 4px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}
.field-item {
  padding: 8px 14px;
  border-bottom: 1px solid #f5f6f8;
}
.field-item:last-child { border-bottom: none; }
.field-name { font-size: 12px; font-weight: 500; color: #969799; margin-bottom: 3px; display: flex; align-items: center; gap: 6px; }
.confidence-badge {
  font-size: 10px; font-weight: 600; padding: 0 5px; border-radius: 3px; line-height: 16px;
}
.conf-high { background: #e8fae8; color: #07c160; }
.conf-medium { background: #fff7e6; color: #ff976a; }
.conf-low { background: #ffeeed; color: #ee0a24; }
.match-reason-row {
  display: flex; align-items: flex-start; gap: 4px;
  font-size: 12px; color: #969799; margin-top: 3px; padding: 3px 6px;
  background: #f9fafb; border-radius: 4px;
}
.reason-icon { font-size: 12px; flex-shrink: 0; }
.reason-text { line-height: 1.4; }
.value-row { display: flex; align-items: center; gap: 5px; font-size: 13px; padding: 2px 0; }
.value-label { font-size: 11px; color: #969799; width: 44px; flex-shrink: 0; }
.value-text { color: #323233; flex: 1; }
.value-text.mismatch { color: #ee0a24; }
.value-text.empty { color: #969799; font-style: italic; }
.match-row { color: #07c160; }
.mismatch-row { color: #ee0a24; }
.empty-row { color: #969799; }

.file-section { margin: 0 16px; background: #fff; border-radius: 8px; padding: 16px; }
.no-file { color: #969799; font-size: 13px; }
.action-section { margin: 0 16px; }
.action-buttons { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
.already-reviewed {
  background: #f5f6f8; border-radius: 8px; padding: 16px; text-align: center; color: #969799; font-size: 14px;
}
</style>
