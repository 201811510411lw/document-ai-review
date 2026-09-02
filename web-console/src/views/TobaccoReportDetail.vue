<template>
  <div class="detail-page">
    <van-nav-bar title="烟草证核对结果" left-arrow @click-left="router.back()" />
    <div v-if="loading" class="detail-skeleton" aria-label="正在加载核对结果"><span></span><span></span><span></span></div>
    <van-empty v-else-if="!report" image-size="72" description="未找到该核对报告" />

    <main v-else class="detail-shell">
      <section class="decision-summary" :class="resultMeta.tone">
        <div>
          <p>审核结论</p>
          <h1>{{ reportSubjectLabel(report) }}</h1>
          <span>{{ modeLabel(report.review_mode) }}<b>{{ formatTime(report.compare_time || report.created_at) }}</b></span>
        </div>
        <div class="result-badge"><van-icon :name="resultMeta.icon" /><strong>{{ resultMeta.label }}</strong></div>
      </section>

      <section v-if="canManualReview" class="manual-actions" aria-label="人工处置">
        <div><strong>异常待处理 — 需要人工复核</strong><span>系统无法自动完成核对，请检查 OA 附件后人工确认。</span></div>
        <div class="manual-actions__buttons">
          <van-button v-if="canRetryOaCallback" size="small" plain type="primary" icon="replay" :loading="callbackLoading" @click="retryOaCallback">重新回调 OA</van-button>
          <van-button size="small" type="primary" :loading="manualLoading" @click="openManualReview('APPROVE')">人工通过</van-button>
          <van-button size="small" plain type="danger" :loading="manualLoading" @click="openManualReview('REJECT')">驳回</van-button>
          <van-button size="small" plain :loading="manualLoading" @click="openManualReview('REQUEST_MORE_INFO')">要求补件</van-button>
        </div>
      </section>

      <section class="content-section">
        <header class="section-header"><div><p>审核证据</p><h2>字段核对</h2></div><span>{{ isReportProcessing(report) ? '等待识别' : `${mismatchCount} 项异常` }}</span></header>
        <van-notice-bar
          v-if="isReportProcessing(report)"
          left-icon="clock-o"
          color="#526979"
          background="#f5f8f9"
        >证照字段正在识别，完成后展示主体名称、经营场所和负责人核对结果。</van-notice-bar>
        <div v-else class="comparison-grid">
          <article v-for="field in comparisonFields" :key="field.key" class="comparison-card" :class="field.passed ? 'passed' : 'failed'">
            <header><div><van-icon :name="field.passed ? 'success' : 'cross'" /><strong>{{ field.label }}</strong></div><van-tag :type="field.passed ? 'success' : 'danger'" plain>{{ field.verdict }}</van-tag></header>
            <dl>
              <div v-for="value in field.values" :key="value.label"><dt>{{ value.label }}</dt><dd>{{ value.value || '-' }}</dd></div>
            </dl>
          </article>
        </div>
      </section>

      <section v-if="report.rule_results?.length" class="content-section">
        <header class="section-header"><div><p>规则明细</p><h2>一致性核对结论</h2></div></header>
        <div class="rule-list">
          <article v-for="rule in report.rule_results" :key="rule.rule_code" :class="rule.passed ? 'passed' : 'failed'">
            <van-icon :name="rule.passed ? 'success' : 'warning-o'" />
            <div>
              <strong>{{ rule.rule_name }}</strong>
              <span>{{ rule.message }}</span>
              <!-- 失败规则展示解决方案 -->
              <div v-if="!rule.passed" class="rule-solution">
                <van-icon name="info-o" /> {{ ruleSolution(rule.rule_code) }}
              </div>
            </div>
          </article>
        </div>
      </section>

      <!-- RPA 官网验真 -->
      <section v-if="showRpaSection" class="content-section">
        <header class="section-header"><div><p>外部核验</p><h2>烟草证官网验真</h2></div>
          <van-tag :type="rpaStatusTagType" plain size="small">{{ rpaStatusLabel }}</van-tag>
        </header>
        <div class="rpa-card">
          <div v-if="rpaStatus === 'AUTHENTIC'" class="rpa-status rpa-pass">
            <van-icon name="success" /> 该烟草证经国家烟草专卖局官网核验为真实有效
          </div>
          <div v-else-if="rpaStatus === 'SUSPECTED'" class="rpa-status rpa-fail">
            <van-icon name="cross" /> 烟草证信息与官网记录不符，疑似伪造
          </div>
          <div v-else-if="rpaStatus === 'NOT_FOUND'" class="rpa-status rpa-warn">
            <van-icon name="info-o" /> 未在国家烟草专卖局官网查到该证照记录
          </div>
          <div v-else-if="rpaStatus === 'FAILED'" class="rpa-status rpa-fail">
            <van-icon name="cross" /> 官网验真未通过
          </div>
          <div v-else-if="rpaStatus === 'ERROR'" class="rpa-status rpa-warn">
            <van-icon name="info-o" /> 验真未完成或执行异常
          </div>
          <div v-else-if="rpaStatus === 'IN_PROGRESS'" class="rpa-status rpa-pending">
            <van-loading size="14" /> 验真实时结果查询中…
          </div>
          <div v-else-if="rpaCapability && !rpaCapability.enabled" class="rpa-status rpa-idle">
            <van-icon name="info-o" /> {{ rpaCapability.disabled_reason || 'RPA 验真功能未启用' }}
          </div>
          <div v-else class="rpa-status rpa-idle">
            <van-icon name="search" /> 尚未发起官网验真
          </div>

          <div class="rpa-meta">
            <div><span>许可证号</span><strong>{{ rpaCertificateNo || '—' }}</strong></div>
            <div v-if="rpaVerifiedAt"><span>验真时间</span><strong>{{ rpaVerifiedAt }}</strong></div>
            <div v-if="rpaError"><span>结果说明</span><strong class="rpa-error-text">{{ rpaError }}</strong></div>
          </div>

          <div v-if="rpaScreenshotUrl" class="rpa-screenshot">
            <span>验真截图</span>
            <a :href="rpaScreenshotUrl" target="_blank" rel="noopener">查看截图 <van-icon name="arrow" /></a>
          </div>

          <div v-if="rpaAction.visible" class="rpa-actions">
            <van-button size="small" plain type="primary" :loading="rpaLoading" :disabled="!rpaAction.enabled" @click="triggerRpaVerification">
              <template #icon><van-icon name="send" /></template>
              {{ rpaLoading ? '验真中…' : '发起官网验真' }}
            </van-button>
            <span v-if="rpaAction.reason">{{ rpaAction.reason }}</span>
          </div>
        </div>
      </section>

      <section v-if="report.review_mode === 'store_in_store'" class="content-section">
        <header class="section-header"><div><p>证照角色</p><h2>店中店三证核对</h2></div></header>
        <div class="store-evidence">
          <div><span>烟草持证主体</span><strong>{{ report.comparison?.holder_business_license?.subject_name || '-' }}</strong></div>
          <div><span>加盟店主体</span><strong>{{ report.comparison?.franchisee_business_license?.subject_name || '-' }}</strong></div>
          <div><span>加盟店地址</span><strong>{{ report.comparison?.franchisee_business_license?.business_address || '-' }}</strong></div>
          <div><span>同址证明</span><strong>{{ report.comparison?.store_in_store?.same_premises_evidence?.document_id || '无需补充证明' }}</strong></div>
        </div>
      </section>

      <section v-if="report.oa" class="content-section oa-section">
        <header class="section-header"><div><p>原始凭据</p><h2>OA 来源与必需证照原件</h2></div><span>流程 {{ report.oa.requestid || '-' }}</span></header>
        <dl class="oa-meta">
          <div><dt>流程状态</dt><dd>{{ report.oa.request_status || '-' }}</dd></div>
          <div><dt>提交时间</dt><dd>{{ [report.oa.created_date, report.oa.created_time].filter(Boolean).join(' ') || '-' }}</dd></div>
          <div class="wide"><dt>流程标题</dt><dd>{{ report.oa.request_name || report.oa.summary_title || '-' }}</dd></div>
        </dl>
        <div v-if="report.oa.content_summary" class="oa-content"><span>OA 申请正文</span><p>{{ report.oa.content_summary }}</p></div>
        <van-notice-bar v-if="report.oa.unavailable_message" left-icon="warning-o" color="#9d5d1d" background="#fff8e8">{{ report.oa.unavailable_message }}</van-notice-bar>
        <van-notice-bar
          v-if="missingRequiredAttachmentRoles.length"
          left-icon="warning-o"
          color="#9d5d1d"
          background="#fff8e8"
        >
          缺少必需原件：{{ missingRequiredAttachmentRoles.map(attachmentRoleLabel).join('、') }}，本次两证审核不可继续。
        </van-notice-bar>
        <div v-if="report.oa.attachments?.length" class="attachment-list">
          <article v-for="(attachment, index) in report.oa.attachments" :key="`${attachment.docid || 'attachment'}-${attachment.relative_path || index}`">
            <div><van-icon name="description" color="#176784" /><span><strong>{{ attachment.file_name || attachment.doc_subject || 'OA 附件' }}</strong><small>{{ attachmentRoleLabel(attachment.document_role) }}<template v-if="attachment.docid"><b>文档 {{ attachment.docid }}</b></template></small></span></div>
            <van-button v-if="attachment.relative_path" size="small" plain type="primary" icon="eye-o" @click="previewOaAttachment(attachment)">预览</van-button>
            <em v-else>必需原件未落盘</em>
          </article>
        </div>
      </section>

      <section v-if="report.oa" class="content-section callback-section">
        <header class="section-header">
          <div><p>投递审计</p><h2>OA 回调记录</h2></div>
          <div class="callback-header-actions">
            <span>{{ callbackRecordsView.length }} 次</span>
            <van-button
              v-if="canRetryOaCallback && !canManualReview"
              size="small"
              plain
              type="primary"
              icon="replay"
              :loading="callbackLoading"
              @click="retryOaCallback"
            >重新回调 OA</van-button>
          </div>
        </header>
        <van-notice-bar
          v-if="!callbackRecordsView.length"
          left-icon="info-o"
          color="#526979"
          background="#f5f8f9"
        >尚无可查看的回调记录</van-notice-bar>
        <div v-else class="callback-list">
          <article v-for="(record, index) in callbackRecordsView" :key="`${record.updated_at || 'callback'}-${index}`">
            <header>
              <div>
                <strong>{{ callbackTriggerLabel(record.trigger) }}</strong>
                <span>{{ formatTime(record.updated_at) }}</span>
              </div>
              <van-tag :type="callbackStatusMeta(record).type" plain>{{ callbackStatusMeta(record).label }}</van-tag>
            </header>
            <dl>
              <div><dt>目标地址</dt><dd>{{ record.target || '历史记录未保存' }}</dd></div>
              <div><dt>业务决定</dt><dd>{{ callbackDecisionLabel(record) }}</dd></div>
              <div><dt>HTTP 状态</dt><dd>{{ record.http_status || '-' }}</dd></div>
              <div><dt>发送次数</dt><dd>{{ record.attempt_count || '-' }}</dd></div>
            </dl>
            <van-notice-bar
              v-if="record.legacy"
              left-icon="info-o"
              color="#7a6500"
              background="#fff8e8"
            >该历史回调未保存请求正文和接收端响应</van-notice-bar>
            <details v-if="record.request_payload">
              <summary>发送 JSON</summary>
              <pre>{{ formatAuditJson(record.request_payload) }}</pre>
            </details>
            <details v-if="record.response_body != null">
              <summary>接收端响应</summary>
              <pre>{{ formatAuditJson(record.response_body) }}</pre>
            </details>
            <p v-if="record.error" class="callback-error">{{ record.error }}</p>
          </article>
        </div>
      </section>
    </main>

    <van-dialog
      v-model:show="manualDialogVisible"
      :title="manualDialogConfig.title"
      show-cancel-button
      :confirm-button-loading="manualLoading"
      :before-close="beforeManualDialogClose"
    >
      <van-field
        v-model="manualComment"
        type="textarea"
        rows="3"
        maxlength="300"
        show-word-limit
        :required="manualDialogConfig.commentRequired"
        label="处理说明"
        :placeholder="manualDialogConfig.placeholder"
      />
    </van-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { tobaccoApi, rpaApi } from '@/api'
import { openTobaccoAttachmentPreview } from '@/features/tobacco/attachmentPreview.js'
import { isReportProcessing, reportSubjectLabel } from '@/features/tobacco/reportPresentation.js'
import {
  callbackDecisionLabel,
  callbackRecords,
  callbackStatusMeta,
  callbackSuccessMessage,
  callbackTriggerLabel,
  formatAuditJson,
  manualActionConfig,
} from '@/features/tobacco/oaCallbackAudit.js'
import { resolveRpaAction, resolveRpaCertificateNo } from '@/features/tobacco/rpaVerification'

const router = useRouter()
const route = useRoute()
const report = ref(null)
const loading = ref(true)
const manualLoading = ref(false)
const callbackLoading = ref(false)
const manualDialogVisible = ref(false)
const pendingDecision = ref('APPROVE')
const manualComment = ref('')
const rpaVerification = ref(null)
const rpaCapability = ref(null)
const rpaLoading = ref(false)

const resultMeta = computed(() => {
  const result = report.value?.overall_result
  if (report.value?.processing_status === 'processing') return { label: '审核处理中', tone: 'pending', icon: 'clock-o' }
  if (['manual_review', 'failed'].includes(report.value?.processing_status)) {
    return { label: '待人工处理', tone: 'pending', icon: 'warning-o' }
  }
  if (result === '通过') return { label: '自动通过 · 已流转至法务节点', tone: 'passed', icon: 'success' }
  if (result === '待校验') return { label: '异常待处理', tone: 'pending', icon: 'warning-o' }
  return { label: '驳回 · 已退回申请人', tone: 'failed', icon: 'cross' }
})

// 超时失败仍然是可人工处置的 OA 任务；不能只允许正常的 manual_review 状态。
const canManualReview = computed(() => ['manual_review', 'failed'].includes(report.value?.processing_status))
const canRetryOaCallback = computed(() => (
  report.value?.processing_status !== 'processing'
  && Boolean(report.value?.oa?.requestid)
))
const manualDialogConfig = computed(() => manualActionConfig(pendingDecision.value))
const callbackRecordsView = computed(() => callbackRecords(report.value))
const comparisonFields = computed(() => {
  const item = report.value || {}
  return [
    { key: 'type', label: '证照类型', verdict: item.type_match || '待校验', passed: item.type_match === '正确', values: [{ label: '营业执照', value: '营业执照' }, { label: '烟草证', value: '烟草专卖零售许可证' }] },
    { key: 'name', label: '主体名称', verdict: item.name_match || '待校验', passed: item.name_match === '匹配', values: [{ label: '营业执照', value: item.business_license_name }, { label: '烟草证', value: item.tobacco_license_name }] },
    { key: 'address', label: '经营场所', verdict: item.address_match || '待校验', passed: item.address_match === '匹配', values: [{ label: '营业执照', value: item.business_license_address }, { label: '烟草证', value: item.tobacco_license_address }] },
    { key: 'person', label: '负责人', verdict: item.person_match || '待校验', passed: item.person_match === '匹配', values: [{ label: '营业执照', value: item.business_license_person }, { label: '烟草证', value: item.tobacco_license_person }] },
    { key: 'validity', label: '有效期', verdict: item.validity_status || '待校验', passed: item.validity_status === '未过期', values: [{ label: '烟草证', value: item.validity_status }] },
  ]
})
const mismatchCount = computed(() => comparisonFields.value.filter((item) => !item.passed).length)
const missingRequiredAttachmentRoles = computed(() => {
  const attachments = report.value?.oa?.attachments || []
  const roles = new Set(attachments.filter((item) => item.relative_path).map((item) => item.document_role))
  return ['business_license', 'tobacco_license'].filter((role) => !roles.has(role))
})

// ── RPA 验真 ──
const rpaStatus = computed(() => rpaVerification.value?.status || report.value?.rpa_verification?.status)
const rpaCertificateNo = computed(() => resolveRpaCertificateNo(report.value, rpaVerification.value))
const rpaVerifiedAt = computed(() => {
  const raw = rpaVerification.value?.verified_at || report.value?.rpa_verification?.verified_at
  return raw ? String(raw).replace('T', ' ').slice(0, 19) : null
})
const rpaScreenshotUrl = computed(() => rpaVerification.value?.screenshot_url || report.value?.rpa_verification?.screenshot_url)
const rpaError = computed(() => rpaVerification.value?.error_message || report.value?.rpa_verification?.error_message)
const showRpaSection = computed(() => report.value?.id || rpaVerification.value)
const rpaAction = computed(() => resolveRpaAction({
  capability: rpaCapability.value,
  status: rpaStatus.value,
  certificateNo: rpaCertificateNo.value,
}))
const rpaStatusLabel = computed(() => {
  if (!rpaStatus.value && rpaCapability.value && !rpaCapability.value.enabled) return '未启用'
  return rpaVerification.value?.result_label || report.value?.rpa_verification?.result_label || '未验真'
})
const rpaStatusTagType = computed(() => ({
  AUTHENTIC: 'success', FAILED: 'danger', SUSPECTED: 'danger', NOT_FOUND: 'warning',
  ERROR: 'warning', IN_PROGRESS: 'primary', PENDING: 'primary',
}[rpaStatus.value] || 'default'))

onMounted(async () => {
  await loadReport()
  await Promise.all([tryLoadRpaStatus(), loadRpaCapability()])
})

async function loadReport() {

  loading.value = true
  try {
    const response = await tobaccoApi.detail(route.params.id)
    report.value = response.report || response
  } catch (error) {
    // The empty state already explains a missing report; avoid a redundant Toast overlay.
    if (error.status !== 404) {
      showToast(error.message || '加载核对报告失败')
    }
  } finally {
    loading.value = false
  }
}

async function tryLoadRpaStatus() {
  if (!report.value?.id) return
  try {
    const res = await rpaApi.getStatus(report.value.id)
    rpaVerification.value = res
  } catch {
    // 无验真记录或接口不可用，静默
  }
}

async function loadRpaCapability() {
  try {
    rpaCapability.value = await rpaApi.getCapability()
  } catch (error) {
    rpaCapability.value = {
      enabled: false,
      disabled_reason: error.message || '无法读取官网验真能力状态',
    }
  }
}

async function triggerRpaVerification() {
  const item = report.value
  if (!item?.id || !rpaAction.value.enabled) {
    showToast(rpaAction.value.reason || '当前无法发起官网验真')
    return
  }
  rpaLoading.value = true
  try {
    const res = await rpaApi.triggerVerify(item.id, rpaCertificateNo.value, item.company_name || '')
    rpaVerification.value = res
    showToast('验真请求已提交')
  } catch (error) {
    showToast(error.message || '发起验真失败')
  } finally {
    rpaLoading.value = false
  }
}

function openManualReview(decision) {
  pendingDecision.value = decision
  manualComment.value = ''
  manualDialogVisible.value = true
}

async function beforeManualDialogClose(action) {
  if (action !== 'confirm') return true
  if (manualDialogConfig.value.commentRequired && !manualComment.value.trim()) {
    showToast('请填写处理说明')
    return false
  }
  return submitManualReview()
}

async function submitManualReview() {
  const decision = pendingDecision.value
  manualLoading.value = true
  try {
    const response = await tobaccoApi.manualReview(route.params.id, decision, manualComment.value.trim())
    await loadReport()
    showToast(callbackSuccessMessage(manualDialogConfig.value.success, response.oa_callback))
    return true
  } catch (error) {
    showToast(error.message || '人工复核提交失败')
    return false
  } finally {
    manualLoading.value = false
  }
}

async function retryOaCallback() {
  callbackLoading.value = true
  try {
    const response = await tobaccoApi.retryOaCallback(route.params.id)
    await loadReport()
    showToast(callbackSuccessMessage('OA 回调已重新发送', response.oa_callback))
  } catch (error) {
    showToast(error.message || 'OA 回调发送失败')
  } finally {
    callbackLoading.value = false
  }
}

function modeLabel(mode) { return mode === 'store_in_store' ? '店中店核对' : '标准核对' }
function formatTime(value) { return value ? String(value).replace('T', ' ').slice(0, 19) : '-' }
function attachmentRoleLabel(role) { return { tobacco_license: '烟草证', business_license: '烟草持证主体营业执照', franchisee_business_license: '加盟店营业执照', selected_attachment: '核对选用附件' }[role] || 'OA 附件' }

const RULE_SUGGESTIONS = {
  BUSINESS_TOBACCO_SUBJECT_NAME_MATCH:
    '按照法律规定，用于办理烟证的营业执照与烟证上的三信息（企业名称、负责人、经营地址）一致，'
    + '现企业名称不一致，按照法律规定需要变更为一致，若未变更被执法机关查到，'
    + '轻则限期整改，重则被罚款、取消烟草证等，同时会对我司品牌造成不良影响。'
    + '建议加盟商变更后经营。\n'
    + '店中店模式仅要求烟草持证主体营业执照与烟草证名称一致，不要求加盟店营业执照与持证主体同名。\n'
    + '如无法变更但坚持售卖，需要在 OA 流程写：'
    + '已确认和接受因企业名称、地址、负责人不一致，未变更被执法机关查到，'
    + '轻则限期整改，重则被罚款、取消烟草证等，同时会对我司品牌造成不良影响的风险。',
  BUSINESS_TOBACCO_ADDRESS_MATCH:
    '按照法律规定，用于办理烟证的营业执照与烟证上的三信息（企业名称、负责人、经营地址）一致，'
    + '现地址不一致，按照法律规定需要变更为一致，若未变更被执法机关查到，'
    + '轻则限期整改，重则被罚款、取消烟草证等，同时会对我司品牌造成不良影响。\n'
    + '按照法律规定，一定要在烟证上的地址上卖烟，如果在零食有鸣店铺上卖烟，那么烟证地址需在零食有鸣店铺上。\n'
    + '请选择以下方式之一处理：\n'
    + '1. 变更地址使两证一致；\n'
    + '2. 上传烟证上的地址是用于经营零食有鸣的照片（照片上要显示烟证上的门牌号 + 实际用于经营零食有鸣）；\n'
    + '3. 上传政府部门（如当地派出所/房管局等出具的地址名称一致证明文件）。\n'
    + '如无法变更但坚持售卖，需要在 OA 流程写：'
    + '已确认和接受因企业名称、地址、负责人不一致，未变更被执法机关查到，'
    + '轻则限期整改，重则被罚款、取消烟草证等，同时会对我司品牌造成不良影响的风险。',
  BUSINESS_TOBACCO_PERSON_MATCH:
    '单店模式：经营零食有鸣营业执照上的负责人与烟草证上的负责人需要一致，'
    + '现经营零食有鸣营业执照上的负责人与烟草证上的负责人不一致，'
    + '请联系招商处理是否需要补签三方协议还是门店模式填写错误。\n'
    + '按照法律规定，用于办理烟证的营业执照与烟证上的三信息（企业名称、负责人、经营地址）一致，'
    + '现负责人不一致，按照法律规定需要变更为一致，若未变更被执法机关查到，'
    + '轻则限期整改，重则被罚款、取消烟草证等，同时会对我司品牌造成不良影响。'
    + '建议加盟商变更后经营。\n'
    + '如无法变更但坚持售卖，需要在 OA 流程写：'
    + '已确认和接受因企业名称、地址、负责人不一致，未变更被执法机关查到，'
    + '轻则限期整改，重则被罚款、取消烟草证等，同时会对我司品牌造成不良影响的风险。',
  BUSINESS_TOBACCO_TOBACCO_VALIDITY:
    '烟草证已过期或临近过期，请前往当地烟草专卖局办理续期后重新提交。',
  STORE_IN_STORE_HOLDER_NAME_MATCH:
    '店中店模式下，烟草持证主体营业执照与烟草证的企业名称必须一致，请核对两份证照或办理变更。',
  STORE_IN_STORE_HOLDER_PERSON_MATCH:
    '店中店模式下，烟草持证主体营业执照与烟草证的负责人必须一致，请核对两份证照或办理变更。',
  STORE_IN_STORE_HOLDER_ADDRESS_MATCH:
    '请确认烟草持证主体营业执照与烟草证登记地址一致；地址名称不同但实为同址时，上传门牌照片或政府同址证明。',
  STORE_IN_STORE_FRANCHISEE_ADDRESS_MATCH:
    '加盟店营业执照地址必须与烟草证售烟地址一致或属于同一经营场所；请上传门牌照片或政府同址证明后人工复核。',
  STANDARD_FRANCHISEE_NAME_MATCH:
    '单店模式下，营业执照和烟草证主体必须与加盟商名称一致，请核对 OA 加盟商信息或办理证照变更。',
  STANDARD_FRANCHISEE_NAME_EVIDENCE:
    'OA 未提供加盟商主体名称，无法完成单店主体绑定校验，请补充后重新审核。',
}

function ruleSolution(ruleCode) {
  return RULE_SUGGESTIONS[ruleCode] || '请核对证照信息后重新提交'
}

function previewOaAttachment(attachment) {
  const result = openTobaccoAttachmentPreview({
    attachment,
    reportId: route.params.id,
    router,
    openWindow: (url, target) => window.open(url, target),
  })
  if (result.reason === 'unavailable') {
    showToast('附件尚未落盘，无法预览')
    return
  }
  if (result.reason === 'blocked') {
    showToast('浏览器阻止打开，请允许弹窗后重试')
  }
}
</script>

<style scoped>
.detail-page { min-height: 100vh; background: #f4f7f9; padding-bottom: 40px; }.page-loading { display: flex; justify-content: center; padding: 72px 0; }.detail-shell { width: min(980px, 100%); box-sizing: border-box; margin: 0 auto; padding: 20px 16px; }.decision-summary { display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 20px; border-left: 4px solid #cc5960; background: #fff; }.decision-summary.passed { border-left-color: #2e9e67; }.decision-summary.pending { border-left-color: #c6872d; }.decision-summary p, .section-header p { margin: 0 0 5px; color: #6c8294; font-size: 12px; }.decision-summary h1 { margin: 0; color: #1a2e40; font-size: 21px; }.decision-summary span { display: block; margin-top: 7px; color: #728494; font-size: 12px; }.result-badge { display: inline-flex; flex: 0 0 auto; align-items: center; gap: 6px; color: #b44b50; }.passed .result-badge { color: #278552; }.pending .result-badge { color: #a56b1e; }.result-badge strong { font-size: 15px; }.manual-actions { display: flex; align-items: center; justify-content: space-between; gap: 14px; margin-top: 14px; padding: 14px; border: 1px solid #e9d5a8; border-radius: 6px; background: #fff9ed; }.manual-actions strong, .manual-actions span { display: block; }.manual-actions strong { color: #5f481f; font-size: 14px; }.manual-actions span { margin-top: 4px; color: #847455; font-size: 12px; }.manual-actions__buttons { display: flex; flex-wrap: wrap; gap: 8px; }.content-section { margin-top: 26px; }.section-header { display: flex; align-items: end; justify-content: space-between; gap: 12px; margin-bottom: 10px; }.section-header h2 { margin: 0; color: #21394d; font-size: 17px; }.section-header > span { color: #778b9c; font-size: 12px; }.comparison-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }.comparison-card { min-width: 0; border: 1px solid #e0e7ec; border-left: 3px solid #c85d60; border-radius: 6px; background: #fff; }.comparison-card.passed { border-left-color: #2e9e67; }.comparison-card header { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 12px; border-bottom: 1px solid #edf1f4; }.comparison-card header > div { display: flex; align-items: center; gap: 6px; color: #a9474d; }.comparison-card.passed header > div { color: #278552; }.comparison-card strong { color: #243d51; font-size: 14px; }.comparison-card dl { margin: 0; padding: 10px 12px; }.comparison-card dl div { display: grid; grid-template-columns: 64px minmax(0, 1fr); gap: 8px; padding: 3px 0; font-size: 13px; }.comparison-card dt { color: #778b9c; }.comparison-card dd { margin: 0; color: #354b5d; overflow-wrap: anywhere; }.rule-list { border: 1px solid #e0e7ec; border-radius: 6px; background: #fff; }.rule-list article { display: flex; gap: 9px; padding: 12px; border-left: 3px solid #c85d60; }.rule-list article + article { border-top: 1px solid #edf1f4; }.rule-list article.passed { border-left-color: #2e9e67; }.rule-list article > :first-child { color: #b64e53; }.rule-list article.passed > :first-child { color: #278552; }.rule-list strong, .rule-list span { display: block; }.rule-list strong { color: #2c4356; font-size: 13px; }.rule-list span { margin-top: 4px; color: #718596; font-size: 12px; line-height: 1.5; }.store-evidence { display: grid; gap: 1px; background: #e0e7ec; border: 1px solid #e0e7ec; border-radius: 6px; overflow: hidden; }.store-evidence div { padding: 12px; background: #fff; }.store-evidence span, .store-evidence strong { display: block; }.store-evidence span { color: #778b9c; font-size: 12px; }.store-evidence strong { margin-top: 5px; color: #30485d; font-size: 13px; font-weight: 500; overflow-wrap: anywhere; }.oa-section { padding: 14px; border: 1px solid #e0e7ec; border-radius: 6px; background: #fff; }.oa-meta { display: grid; grid-template-columns: 1fr 1fr; margin: 0; border-top: 1px solid #e9eef2; }.oa-meta div { min-width: 0; padding: 10px 0; }.oa-meta div:nth-child(odd) { padding-right: 12px; }.oa-meta .wide { grid-column: span 2; border-top: 1px solid #edf1f4; }.oa-meta dt, .oa-content > span { color: #778b9c; font-size: 12px; }.oa-meta dd { margin: 4px 0 0; color: #31495d; font-size: 13px; line-height: 1.5; overflow-wrap: anywhere; }.oa-content { padding: 10px 0; border-top: 1px solid #edf1f4; }.oa-content p { margin: 5px 0 0; color: #465c6d; font-size: 13px; line-height: 1.6; white-space: pre-wrap; }.attachment-list { margin-top: 10px; border-top: 1px solid #edf1f4; }.attachment-list article { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 0; }.attachment-list article + article { border-top: 1px solid #edf1f4; }.attachment-list article > div { display: flex; min-width: 0; align-items: center; gap: 8px; }.attachment-list strong, .attachment-list small { display: block; }.attachment-list strong { overflow: hidden; color: #30485d; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.attachment-list small, .attachment-list em { margin-top: 3px; color: #7d8e9d; font-size: 12px; font-style: normal; }.attachment-list em { flex: 0 0 auto; } @media (max-width: 600px) { .detail-shell { padding: 14px 12px; }.decision-summary, .manual-actions { align-items: stretch; flex-direction: column; }.comparison-grid { grid-template-columns: 1fr; }.manual-actions__buttons :deep(.van-button) { flex: 1; }.oa-section { padding: 12px; }.attachment-list article { align-items: flex-start; }.attachment-list strong { white-space: normal; } }
/* Tobacco review detail visual system */
.detail-page { --tobacco-ink: #162a3a; --tobacco-muted: #657887; --tobacco-accent: #176784; --tobacco-line: #dce6eb; --tobacco-line-strong: #becfd7; --tobacco-surface: #fff; --tobacco-surface-muted: #f5f8f9; min-height: 100vh; padding-bottom: 48px; background: #eef3f5; color: var(--tobacco-ink); font-family: "Microsoft YaHei", "PingFang SC", system-ui, sans-serif; }
.detail-page :deep(.van-nav-bar) { height: 58px; border-bottom: 1px solid var(--tobacco-line); background: var(--tobacco-surface); }.detail-page :deep(.van-nav-bar__title) { color: var(--tobacco-ink); font-size: 16px; font-weight: 650; }.detail-page :deep(.van-nav-bar .van-icon) { color: var(--tobacco-accent); }
.page-loading { display: none; }.detail-skeleton { display: grid; width: min(980px, calc(100% - 32px)); gap: 14px; margin: 24px auto; }.detail-skeleton span { display: block; height: 104px; border-radius: 8px; background: #e2eaee; }.detail-skeleton span:nth-child(2) { height: 180px; }.detail-skeleton span:nth-child(3) { height: 140px; }.detail-shell { padding: 28px 20px; }
.decision-summary { padding: 22px; border: 1px solid #e7c5c1; border-left: 5px solid #c2524b; border-radius: 8px; background: var(--tobacco-surface); }.decision-summary.passed { border-color: #c6e1d0; border-left-color: #2f8b58; }.decision-summary.pending { border-color: #ead6aa; border-left-color: #b67b1d; }.decision-summary p, .section-header p { color: var(--tobacco-muted); }.decision-summary h1 { color: var(--tobacco-ink); font-size: 23px; font-weight: 720; line-height: 1.3; }.decision-summary span { display: flex; flex-wrap: wrap; gap: 10px; color: var(--tobacco-muted); }.decision-summary span b { padding-left: 10px; border-left: 1px solid var(--tobacco-line-strong); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 400; }.result-badge { color: #a6443d; }.passed .result-badge { color: #27784c; }.pending .result-badge { color: #98671d; }
.manual-actions { padding: 16px; border: 1px solid #e3d5b8; border-radius: 8px; background: #fffaf0; }.manual-actions strong { color: #5f4a28; }.manual-actions span { color: #7c6a4b; }.manual-actions__buttons :deep(.van-button) { border-radius: 5px; }.manual-actions__buttons :deep(.van-button--primary) { background: var(--tobacco-accent); border-color: var(--tobacco-accent); }
.content-section { margin-top: 30px; }.section-header { margin-bottom: 11px; padding-bottom: 10px; border-bottom: 1px solid var(--tobacco-line-strong); }.section-header h2 { color: var(--tobacco-ink); font-weight: 700; }.section-header > span { color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.comparison-grid { gap: 10px; }.comparison-card { overflow: hidden; border-color: var(--tobacco-line); border-left: 3px solid #c2524b; border-radius: 7px; }.comparison-card.passed { border-left-color: #2f8b58; }.comparison-card header { padding: 12px 14px; border-bottom-color: var(--tobacco-line); background: var(--tobacco-surface-muted); }.comparison-card header > div { color: #a6443d; }.comparison-card.passed header > div { color: #27784c; }.comparison-card header :deep(.van-tag) { border-radius: 4px; }.comparison-card strong { color: var(--tobacco-ink); }.comparison-card dl { padding: 10px 14px; }.comparison-card dl div { grid-template-columns: 68px minmax(0, 1fr); padding: 4px 0; }.comparison-card dt { color: var(--tobacco-muted); }.comparison-card dd { color: #31495c; line-height: 1.45; }
.rule-list, .store-evidence, .oa-section { border-color: var(--tobacco-line); border-radius: 8px; }.rule-list article { padding: 13px 14px; border-left: 3px solid #c2524b; }.rule-list article + article { border-top-color: var(--tobacco-line); }.rule-list article.passed { border-left-color: #2f8b58; }.rule-list article > :first-child { color: #b04942; }.rule-list article.passed > :first-child { color: #27784c; }.rule-list span { color: var(--tobacco-muted); }
.rule-solution { display: flex; align-items: flex-start; gap: 4px; margin-top: 6px; padding: 6px 8px; border-radius: 4px; background: #fff7e6; color: #7a6500; font-size: 12px; line-height: 1.5; }
.rule-solution .van-icon { flex-shrink: 0; margin-top: 2px; }.store-evidence { background: var(--tobacco-line); }.store-evidence div { padding: 13px 14px; }.store-evidence span { color: var(--tobacco-muted); }.oa-section { padding: 16px; background: var(--tobacco-surface); }.oa-meta, .oa-content, .attachment-list { border-top-color: var(--tobacco-line); }.oa-meta .wide { border-top-color: var(--tobacco-line); }.oa-meta dt, .oa-content > span { color: var(--tobacco-muted); }.attachment-list article + article { border-top-color: var(--tobacco-line); }.attachment-list strong { color: #30485d; }.attachment-list small, .attachment-list em { display: flex; flex-wrap: wrap; gap: 0; color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }.attachment-list small b { margin-left: 8px; padding-left: 8px; border-left: 1px solid var(--tobacco-line-strong); font-weight: 400; }.attachment-list :deep(.van-button) { border-radius: 5px; }
@media (prefers-reduced-motion: reduce) { .detail-page *, .detail-page *::before, .detail-page *::after { transition: none !important; } }@media (max-width: 600px) { .detail-shell { padding: 18px 12px; }.decision-summary h1 { font-size: 20px; }.oa-section { padding: 13px; } }
/* RPA Verification */
.rpa-card { border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); overflow: hidden; }
.rpa-status { display: flex; align-items: center; gap: 8px; padding: 14px 16px; font-size: 14px; font-weight: 500; }
.rpa-pass { color: #27784c; background: #e8fae8; }
.rpa-fail { color: #b44b50; background: #ffeeed; }
.rpa-warn { color: #98671d; background: #fff7e6; }
.rpa-pending { color: #176784; background: #ebf7ff; }
.rpa-idle { color: var(--tobacco-muted); background: var(--tobacco-surface-muted); }
.rpa-meta { display: grid; grid-template-columns: 1fr 1fr; gap: 0; border-top: 1px solid var(--tobacco-line); padding: 10px 16px; }
.rpa-meta div { padding: 4px 0; }
.rpa-meta span, .rpa-meta strong { display: block; }
.rpa-meta span { color: var(--tobacco-muted); font-size: 12px; }
.rpa-meta strong { color: var(--tobacco-ink); font-size: 13px; margin-top: 2px; }
.rpa-error-text { color: #b44b50; }
.rpa-screenshot { display: flex; align-items: center; justify-content: space-between; padding: 8px 16px; border-top: 1px solid var(--tobacco-line); font-size: 13px; }
.rpa-screenshot span { color: var(--tobacco-muted); }
.rpa-screenshot a { color: var(--tobacco-accent); text-decoration: none; }
.rpa-actions { display: flex; align-items: center; gap: 10px; padding: 10px 16px; border-top: 1px solid var(--tobacco-line); }
.rpa-actions > span { color: var(--tobacco-muted); font-size: 12px; }
.callback-header-actions { display: flex; align-items: center; gap: 10px; }.callback-header-actions > span { color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }.callback-header-actions :deep(.van-button) { border-radius: 5px; }
.callback-list { display: grid; gap: 10px; }.callback-list article { overflow: hidden; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); }.callback-list article > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-bottom: 1px solid var(--tobacco-line); background: var(--tobacco-surface-muted); }.callback-list article > header strong, .callback-list article > header span { display: block; }.callback-list article > header strong { color: var(--tobacco-ink); font-size: 13px; }.callback-list article > header span { margin-top: 3px; color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }.callback-list dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; padding: 10px 14px; }.callback-list dl div { min-width: 0; padding: 5px 8px 5px 0; }.callback-list dt { color: var(--tobacco-muted); font-size: 11px; }.callback-list dd { margin: 3px 0 0; color: #30485d; font-size: 12px; overflow-wrap: anywhere; }.callback-list details { border-top: 1px solid var(--tobacco-line); }.callback-list summary { padding: 10px 14px; color: var(--tobacco-accent); cursor: pointer; font-size: 12px; font-weight: 650; }.callback-list pre { max-height: 320px; overflow: auto; margin: 0; padding: 12px 14px; background: #17232c; color: #dbe8ee; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }.callback-error { margin: 0; padding: 10px 14px; border-top: 1px solid #f0cdca; background: #fff1f0; color: #a6443d; font-size: 12px; overflow-wrap: anywhere; }
@media (max-width: 600px) { .callback-list dl { grid-template-columns: 1fr; } }
</style>
