<template>
  <div class="detail-page">
    <van-nav-bar title="烟草证核对结果" left-arrow @click-left="router.back()" />
    <div v-if="loading" class="detail-skeleton" aria-label="正在加载核对结果"><span></span><span></span><span></span></div>
    <van-empty v-else-if="!report" image-size="72" description="未找到该核对报告" />

    <main v-else class="detail-shell" :class="{ 'has-manual-bar': canManualReview }">
      <!-- ① 决策区：只给结论和下一步，动作统一放底部处置条 -->
      <section class="decision-summary" :class="resultMeta.tone">
        <div>
          <p>审核结论</p>
          <h1>{{ reportSubjectLabel(report) }}</h1>
          <span>{{ modeLabel(report.review_mode) }}<b>{{ formatTime(report.compare_time || report.created_at) }}</b><b v-if="report.store_code">门店 {{ report.store_code }}</b></span>
        </div>
        <div class="result-badge"><van-icon :name="resultMeta.icon" /><strong>{{ resultMeta.label }}</strong></div>
      </section>

      <section v-if="keyIssues.length || actionHint" class="issue-summary" :class="resultMeta.tone">
        <header class="issue-summary__head">
          <strong>{{ keyIssues.length ? `有 ${keyIssues.length} 项需要关注` : '审核提示' }}</strong>
          <span v-if="actionHint">{{ actionHint }}</span>
        </header>
        <ul v-if="keyIssues.length" class="issue-list">
          <li v-for="issue in keyIssues" :key="issue.key">
            <b>{{ issue.title }}</b>
            <span>{{ issue.message }}</span>
            <small v-if="issue.detail">{{ issue.detail }}</small>
          </li>
        </ul>
      </section>

      <!-- ② 证据对照台：原件 / 官网验真 / 字段对照 三栏并排 -->
      <section class="content-section evidence-section">
        <header class="section-header">
          <div><p>审核证据</p><h2>证据对照台</h2></div>
          <span>{{ evidenceAttachments.length }} 份原件 · {{ rpaStatusLabel }}</span>
        </header>

        <van-notice-bar
          v-if="missingRequiredAttachmentRoles.length"
          left-icon="warning-o"
          color="#9d5d1d"
          background="#fff8e8"
        >缺少必需原件：{{ missingRequiredAttachmentRoles.map(attachmentRoleLabel).join('、') }}，本次两证审核不可继续。</van-notice-bar>

        <div class="evidence-desk">
          <section class="evidence-col evidence-col--compare">
            <h3 class="evidence-col__title">
              <span>原件与官网对照</span>
              <small>{{ evidenceAttachments.length }} 份原件 · {{ rpaStatusLabel }}</small>
            </h3>

            <div class="rpa-status-line">
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
            </div>

            <div v-if="compareItems.length" class="compare-stage">
              <figure v-for="pane in comparePanes" :key="pane.side" class="compare-pane">
                <label class="compare-pane__picker">
                  <span>{{ pane.label }}</span>
                  <select
                    :value="pane.item?.key || ''"
                    :aria-label="`选择${pane.label}对照文件`"
                    @change="pickCompareItem(pane.side, $event.target.value)"
                  >
                    <option value="" disabled>{{ compareItems.length ? '未选择' : '暂无材料' }}</option>
                    <option v-for="item in compareItems" :key="item.key" :value="item.key">{{ item.optionLabel }}</option>
                  </select>
                  <van-icon name="arrow-down" />
                </label>
                <button
                  type="button"
                  class="compare-pane__frame"
                  :disabled="!pane.item"
                  @click="openCompareItem(pane.item)"
                >
                  <img
                    v-if="pane.item?.isImage"
                    :src="pane.item.imageUrl"
                    :alt="pane.item.title"
                    @error="onCompareImageError(pane.item)"
                  />
                  <span v-else class="compare-placeholder">
                    <van-icon :name="compareIcon(pane.item)" />
                    <b>{{ comparePlaceholderTitle(pane.item) }}</b>
                    <em>{{ comparePlaceholderHint(pane.item) }}</em>
                  </span>
                </button>
                <figcaption v-if="pane.item?.type === 'rpa'" class="compare-pane__note">
                  官网验真 · {{ rpaStatusLabel }}
                </figcaption>
              </figure>
            </div>
            <p v-if="!compareItems.length" class="evidence-empty">未取得 OA 附件</p>
            <p v-else class="evidence-hint">左右两侧可分别选择任意原件或官网截图，自由组合对照；点击图片可放大查看。</p>

            <div class="rpa-meta">
              <div><span>官网核验许可证号</span><strong>{{ rpaCertificateNo || '—' }}</strong></div>
              <div v-if="rpaVerifiedAt"><span>验真时间</span><strong>{{ rpaVerifiedAt }}</strong></div>
              <div v-if="rpaError" class="wide"><span>结果说明</span><strong class="rpa-error-text">{{ rpaError }}</strong></div>
            </div>
            <p class="evidence-hint">官网验真由系统自动执行一次，结果与截图仅作审核依据，页面不提供重复验真入口。</p>
          </section>

          <section class="evidence-col evidence-col--fields">
            <h3 class="evidence-col__title"><span>字段对照</span><small>{{ isReportProcessing(report) ? '等待识别' : `${mismatchCount} 项异常` }}</small></h3>
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
            <div v-if="report.review_mode === 'store_in_store'" class="store-evidence store-evidence--inline">
              <div><span>烟草持证主体</span><strong>{{ report.comparison?.holder_business_license?.subject_name || '-' }}</strong></div>
              <div><span>加盟店主体</span><strong>{{ report.comparison?.franchisee_business_license?.subject_name || '-' }}</strong></div>
              <div><span>加盟店地址</span><strong>{{ report.comparison?.franchisee_business_license?.business_address || '-' }}</strong></div>
              <div><span>同址证明</span><strong>{{ report.comparison?.store_in_store?.same_premises_evidence?.document_id || '无需补充证明' }}</strong></div>
            </div>
          </section>
        </div>
      </section>

      <!-- ③ 判定依据：默认收起，失败规则置顶 -->
      <section v-if="report.rule_results?.length" class="content-section">
        <details class="fold-section">
          <summary>
            <span><p class="eyebrow">判定依据</p><h2>问题与规则</h2></span>
            <span class="fold-meta">{{ failedRules.length }} 项未通过 / 共 {{ orderedRules.length }} 项</span>
          </summary>
          <div class="rule-list">
            <article v-for="rule in orderedRules" :key="rule.rule_code" :class="rule.passed ? 'passed' : 'failed'">
              <van-icon :name="rule.passed ? 'success' : 'warning-o'" />
              <div>
                <strong>{{ rule.rule_name }}</strong>
                <span>{{ rule.message }}</span>
                <div v-if="!rule.passed" class="rule-solution">
                  <van-icon name="info-o" /> {{ ruleSolution(rule) }}
                </div>
              </div>
            </article>
          </div>
        </details>
      </section>

      <!-- ④ OA 来源与附件：默认收起，完整附件可预览与下载 -->
      <section v-if="report.oa" class="content-section">
        <details class="fold-section">
          <summary>
            <span><p class="eyebrow">溯源信息</p><h2>申请与附件信息</h2></span>
            <span class="fold-meta">流程 {{ report.oa.requestid || '-' }}</span>
          </summary>
          <div class="oa-section">
            <dl class="oa-meta">
              <div><dt>流程状态</dt><dd>{{ report.oa.request_status || '-' }}</dd></div>
              <div><dt>提交时间</dt><dd>{{ [report.oa.created_date, report.oa.created_time].filter(Boolean).join(' ') || '-' }}</dd></div>
              <div class="wide"><dt>流程标题</dt><dd>{{ report.oa.request_name || report.oa.summary_title || '-' }}</dd></div>
            </dl>
            <div v-if="report.oa.content_summary" class="oa-content"><span>OA 申请正文</span><p>{{ report.oa.content_summary }}</p></div>
            <van-notice-bar v-if="report.oa.unavailable_message" left-icon="warning-o" color="#9d5d1d" background="#fff8e8">{{ report.oa.unavailable_message }}</van-notice-bar>
            <div v-if="evidenceAttachments.length" class="attachment-list">
              <article v-for="attachment in evidenceAttachments" :key="attachment.key">
                <div>
                  <van-icon name="description" color="#176784" />
                  <span>
                    <strong>{{ attachment.file_name || attachment.doc_subject || 'OA 附件' }}</strong>
                    <small>{{ attachmentRoleLabel(attachment.document_role) }}<template v-if="attachment.docid"><b>文档 {{ attachment.docid }}</b></template></small>
                  </span>
                </div>
                <div class="attachment-actions">
                  <van-button v-if="attachment.relative_path" size="small" plain type="primary" icon="eye-o" @click="openAttachmentViewer(attachment)">预览</van-button>
                  <van-button v-if="attachment.relative_path" size="small" plain icon="down" @click="downloadAttachment(attachment)">下载</van-button>
                  <em v-else>未落盘</em>
                </div>
              </article>
            </div>
          </div>
        </details>
      </section>

      <!-- ⑤ 投递审计 -->
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

      <!-- ⑥ 底部固定处置条：结论在确认弹窗内提交，避免遮挡正文 -->
      <section v-if="canManualReview" class="manual-actions" aria-label="人工处置">
        <div class="manual-actions__inner">
          <div class="manual-summary">
            <strong>待人工处置</strong>
            <span>提交前需在确认框中核对原件、官网验真和字段差异。</span>
          </div>
          <div class="manual-actions__buttons">
            <van-button v-if="canRetryOaCallback" size="small" plain type="primary" icon="replay" :loading="callbackLoading" @click="retryOaCallback">重新回调 OA</van-button>
            <van-button size="small" type="primary" :loading="manualLoading" @click="openManualReview('APPROVE')">人工通过</van-button>
            <van-button size="small" plain type="danger" :loading="manualLoading" @click="openManualReview('REJECT')">驳回</van-button>
            <van-button size="small" plain :loading="manualLoading" @click="openManualReview('REQUEST_MORE_INFO')">要求补件</van-button>
          </div>
        </div>
        <p class="manual-impact">提交后系统会向 OA 回传处理结果；OA 流程是否推进以 OA 节点规则为准。</p>
      </section>
    </main>

    <!-- 页内原件查看器 -->
    <div v-if="viewer.open" class="evidence-viewer" role="dialog" aria-modal="true" @click.self="closeViewer">
      <header>
        <strong>{{ viewer.name }}</strong>
        <div>
          <van-button v-if="viewerNavigation.hasPrev" size="small" plain icon="arrow-left" @click="stepViewer(-1)">上一份</van-button>
          <van-button v-if="viewerNavigation.hasNext" size="small" plain @click="stepViewer(1)">下一份<van-icon name="arrow" /></van-button>
          <van-button size="small" plain icon="cross" @click="closeViewer">关闭</van-button>
        </div>
      </header>
      <div class="evidence-viewer__body">
        <img v-if="viewer.kind === 'image'" :src="viewer.url" :alt="viewer.name" />
        <iframe v-else-if="viewer.kind === 'pdf'" :src="viewer.url" :title="viewer.name" />
        <div v-else class="evidence-viewer__unsupported">
          <span>该文件类型不支持在线预览。</span>
          <a :href="viewer.url" :download="viewer.name">下载原文件</a>
        </div>
      </div>
    </div>

    <van-dialog
      v-model:show="manualDialogVisible"
      :title="manualDialogConfig.title"
      show-cancel-button
      :confirm-button-loading="manualLoading"
      :before-close="beforeManualDialogClose"
    >
      <div class="manual-checks">
        <strong>提交前确认</strong>
        <van-checkbox v-for="check in reviewCheckItems" :key="check.key" v-model="reviewChecks[check.key]" icon-size="16px">{{ check.label }}</van-checkbox>
      </div>
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
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { tobaccoApi, rpaApi } from '@/api'
import { isReportProcessing, reportSubjectLabel, formatReportTime } from '@/features/tobacco/reportPresentation.js'
import {
  callbackDecisionLabel,
  callbackRecords,
  callbackStatusMeta,
  callbackSuccessMessage,
  callbackTriggerLabel,
  formatAuditJson,
  manualActionConfig,
} from '@/features/tobacco/oaCallbackAudit.js'
import { resolveRpaCertificateNo } from '@/features/tobacco/rpaVerification'

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
const screenshotFailed = ref(false)
const manuallyDecided = computed(() => (
  callbackRecords(report.value).some((record) => record.trigger === 'manual_review')
))
const resultMeta = computed(() => {
  const result = report.value?.overall_result
  if (report.value?.processing_status === 'processing') return { label: '审核处理中', tone: 'pending', icon: 'clock-o' }
  if (['manual_review', 'failed'].includes(report.value?.processing_status)) {
    return { label: '待人工处理', tone: 'pending', icon: 'warning-o' }
  }
  if (result === '通过') return { label: manuallyDecided.value ? '人工通过' : '自动通过', tone: 'passed', icon: 'success' }
  if (result === '待校验') return { label: '异常待处理', tone: 'pending', icon: 'warning-o' }
  return { label: '驳回', tone: 'failed', icon: 'cross' }
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

// ── 规则与关注项 ──
const orderedRules = computed(() => {
  const rules = report.value?.rule_results || []
  return [...rules].sort((left, right) => Number(Boolean(left.passed)) - Number(Boolean(right.passed)))
})
const failedRules = computed(() => orderedRules.value.filter((rule) => !rule.passed))
const fieldFailedRules = computed(() => failedRules.value.filter((rule) => rule.rule_code !== 'TOBACCO_LICENSE_RPA_VERIFICATION'))

const rpaIssueMessage = computed(() => {
  if (rpaStatus.value === 'NOT_FOUND') return '官网未查询到该许可证号，可能是编码识别错误，也可能是官网尚未更新。'
  if (rpaStatus.value === 'SUSPECTED') return '官网记录与上传证照信息不一致，请核对原件与官网截图。'
  if (rpaStatus.value === 'FAILED') return '官网验真未通过，请核对原件后人工判断。'
  if (rpaStatus.value === 'ERROR') return rpaError.value || '验真技术未完成，不代表证照为假。'
  return ''
})

const keyIssues = computed(() => {
  const issues = []
  if (['NOT_FOUND', 'SUSPECTED', 'FAILED', 'ERROR'].includes(rpaStatus.value)) {
    issues.push({ key: 'rpa', title: `官网验真：${rpaStatusLabel.value}`, message: rpaIssueMessage.value })
  }
  fieldFailedRules.value.slice(0, 3).forEach((rule) => {
    issues.push({
      key: rule.rule_code,
      title: rule.rule_name,
      message: rule.message,
      detail: ruleFieldDetail(rule),
    })
  })
  return issues
})

const actionHint = computed(() => {
  if (rpaStatus.value === 'NOT_FOUND') return '建议先核对许可证号识别是否正确，必要时修正编码后重新验真。'
  if (['SUSPECTED', 'FAILED'].includes(rpaStatus.value)) return '官网信息与上传证照不一致，建议核对原件后人工处理。'
  if (rpaStatus.value === 'ERROR') return '验真技术未完成，不代表证照为假；可重试或人工判断。'
  if (mismatchCount.value) return '存在字段不一致，请对照证据后人工处理。'
  return ''
})

// ── 附件与页内预览 ──
const evidenceAttachments = computed(() => {
  const items = report.value?.oa?.attachments || []
  return items.map((attachment, index) => ({
    ...attachment,
    key: attachment.key || `${attachment.docid || 'attachment'}-${attachment.relative_path || index}`,
    kind: attachmentKind(attachment.file_name || attachment.doc_subject || ''),
  })).sort((left, right) => attachmentRoleRank(left.document_role) - attachmentRoleRank(right.document_role))
})
const viewableAttachments = computed(() => evidenceAttachments.value.filter((item) => item.relative_path))

const thumbnailUrls = ref({})
let thumbnailObjectUrls = []
let thumbnailRequest = 0

const viewer = ref({ open: false, name: '', kind: '', url: '', path: '', owned: false })
const viewerNavigation = computed(() => {
  const items = viewableAttachments.value
  const index = items.findIndex((item) => item.relative_path === viewer.value.path)
  return { index, hasPrev: index > 0, hasNext: index >= 0 && index < items.length - 1 }
})

// ── RPA 验真 ──
const rpaStatus = computed(() => rpaVerification.value?.status || report.value?.rpa_verification?.status)
const rpaCertificateNo = computed(() => resolveRpaCertificateNo(report.value, rpaVerification.value))
const rpaVerifiedAt = computed(() => {
  const raw = rpaVerification.value?.verified_at || report.value?.rpa_verification?.verified_at
  return raw ? formatReportTime(raw) : null
})
const rpaScreenshotUrl = computed(() => rpaVerification.value?.screenshot_url || report.value?.rpa_verification?.screenshot_url)
const rpaError = computed(() => rpaVerification.value?.error_message || report.value?.rpa_verification?.error_message)
const rpaStatusLabel = computed(() => {
  if (!rpaStatus.value && rpaCapability.value && !rpaCapability.value.enabled) return '未启用'
  return rpaVerification.value?.result_label || report.value?.rpa_verification?.result_label || '未验真'
})

// ── 原件与官网截图并排对照：左右两侧都可自由选择对照材料 ──
const RPA_COMPARE_KEY = 'rpa_screenshot'
const leftCompareKey = ref('')
const rightCompareKey = ref('')
const compareItems = computed(() => {
  const items = evidenceAttachments.value.map((attachment) => {
    const imageUrl = attachment.preview_url || thumbnailUrls.value[attachment.relative_path] || ''
    const title = attachment.file_name || attachment.doc_subject || 'OA 附件'
    const roleLabel = attachmentRoleShortLabel(attachment.document_role)
    return {
      key: attachment.key,
      type: 'attachment',
      kind: attachment.kind,
      attachment,
      title,
      roleLabel,
      optionLabel: `${roleLabel} · ${title}`,
      imageUrl,
      isImage: attachment.kind === 'image' && Boolean(imageUrl),
    }
  })
  if (rpaScreenshotUrl.value) {
    items.push({
      key: RPA_COMPARE_KEY,
      type: 'rpa',
      kind: 'image',
      attachment: null,
      title: '官网验真截图',
      roleLabel: '官网验真',
      optionLabel: `官网验真 · ${rpaStatusLabel.value}`,
      imageUrl: rpaScreenshotUrl.value,
      isImage: !screenshotFailed.value,
    })
  }
  return items
})
const comparePanes = computed(() => [
  { side: 'left', label: '左侧', item: compareItems.value.find((item) => item.key === leftCompareKey.value) || null },
  { side: 'right', label: '右侧', item: compareItems.value.find((item) => item.key === rightCompareKey.value) || null },
])
watch(compareItems, (items) => {
  if (!items.length) {
    leftCompareKey.value = ''
    rightCompareKey.value = ''
    return
  }
  const keys = items.map((item) => item.key)
  if (!keys.includes(leftCompareKey.value)) leftCompareKey.value = items[0].key
  if (!keys.includes(rightCompareKey.value) || rightCompareKey.value === leftCompareKey.value) {
    const alternative = items.find((item) => item.key !== leftCompareKey.value && item.type === 'rpa')
      || items.find((item) => item.key !== leftCompareKey.value)
    rightCompareKey.value = alternative?.key || ''
  }
}, { immediate: true })

// ── 人工处置前确认 ──
const reviewCheckItems = [
  { key: 'original', label: '已核对上传的证照原件' },
  { key: 'rpa', label: '已核对官网验真结果或截图' },
  { key: 'fields', label: '已核对字段差异与规则说明' },
]
const reviewChecks = ref({ original: false, rpa: false, fields: false })
const checksComplete = computed(() => reviewCheckItems.every((check) => reviewChecks.value[check.key]))

watch(rpaScreenshotUrl, () => {
  screenshotFailed.value = false
})

onMounted(async () => {
  await loadReport()
  await Promise.all([tryLoadRpaStatus(), loadRpaCapability()])
})

onBeforeUnmount(() => {
  thumbnailRequest += 1
  revokeThumbnails()
  closeViewer()
})

async function loadReport() {
  loading.value = true
  try {
    const response = await tobaccoApi.detail(route.params.id)
    report.value = response.report || response
    loadThumbnails()
  } catch (error) {
    // The empty state already explains a missing report; avoid a redundant Toast overlay.
    if (error.status !== 404) {
      showToast(error.message || '加载核对报告失败')
    }
  } finally {
    loading.value = false
  }
}

async function loadThumbnails() {
  const request = ++thumbnailRequest
  revokeThumbnails()
  const queue = []
  evidenceAttachments.value.forEach((item) => {
    if (item.kind !== 'image') return
    if (item.preview_url) {
      thumbnailUrls.value = { ...thumbnailUrls.value, [item.relative_path]: item.preview_url }
    } else if (item.relative_path) {
      queue.push(item)
    }
  })
  const worker = async () => {
    while (queue.length) {
      const attachment = queue.shift()
      if (!attachment || request !== thumbnailRequest) return
      try {
        const blob = await tobaccoApi.fetchSourceFile(attachment.relative_path)
        if (request !== thumbnailRequest) return
        const url = URL.createObjectURL(blob)
        thumbnailObjectUrls.push(url)
        thumbnailUrls.value = { ...thumbnailUrls.value, [attachment.relative_path]: url }
      } catch {
        // 加载失败时对照区会显示占位提示，点击可重新拉取原件。
        if (request !== thumbnailRequest) return
      }
    }
  }
  await Promise.all(Array.from({ length: Math.min(3, queue.length) }, worker))
}

function revokeThumbnails() {
  thumbnailObjectUrls.forEach((url) => URL.revokeObjectURL(url))
  thumbnailObjectUrls = []
  thumbnailUrls.value = {}
}

// 对照区左右两侧可以任意组合；选中对方正在展示的材料时自动互换。
function pickCompareItem(side, key) {
  if (!key) return
  if (side === 'left') {
    if (key === leftCompareKey.value) return
    const previous = leftCompareKey.value
    leftCompareKey.value = key
    if (rightCompareKey.value === key) rightCompareKey.value = previous || ''
    return
  }
  if (key === rightCompareKey.value) return
  const previous = rightCompareKey.value
  rightCompareKey.value = key
  if (leftCompareKey.value === key) leftCompareKey.value = previous || ''
}

async function openCompareItem(item) {
  if (!item) return
  if (item.type === 'rpa') {
    openScreenshotViewer()
    return
  }
  await openAttachmentViewer(item.attachment)
}

function onCompareImageError(item) {
  if (item?.type === 'rpa') screenshotFailed.value = true
}

function compareIcon(item) {
  if (!item || item.kind === 'image') return 'photo-o'
  if (item.kind === 'pdf') return 'description'
  return 'file-o'
}

function comparePlaceholderTitle(item) {
  if (!item) return '未选择文件'
  if (item.type === 'rpa') return item.isImage ? '截图加载失败' : '未回传官网截图'
  if (item.kind === 'image') return '图片加载失败'
  if (item.kind === 'pdf') return 'PDF 原件'
  return '文件'
}

function comparePlaceholderHint(item) {
  if (!item) return '请在上方选择要对照的文件'
  if (item.type === 'rpa') return item.isImage ? '点击打开原始链接' : rpaStatusLabel.value
  if (item.kind === 'image') return '点击重新加载'
  return '点击查看原件'
}

async function openAttachmentViewer(attachment) {
  if (!attachment?.relative_path) {
    showToast('附件尚未落盘，无法预览')
    return
  }
  await showViewerItem(attachment)
}

async function showViewerItem(attachment) {
  closeViewer()
  let url = attachment.preview_url || thumbnailUrls.value[attachment.relative_path]
  let owned = false
  if (!url) {
    try {
      const blob = await tobaccoApi.fetchSourceFile(attachment.relative_path)
      url = URL.createObjectURL(blob)
      owned = true
    } catch (error) {
      showToast(error.message || '附件加载失败')
      return
    }
  }
  viewer.value = {
    open: true,
    name: attachment.file_name || attachment.doc_subject || 'OA 附件',
    kind: attachment.kind,
    url,
    path: attachment.relative_path,
    owned,
  }
}

async function stepViewer(delta) {
  const items = viewableAttachments.value
  const index = items.findIndex((item) => item.relative_path === viewer.value.path)
  const next = items[index + delta]
  if (next) await showViewerItem(next)
}

function openScreenshotViewer() {
  if (!rpaScreenshotUrl.value) return
  if (screenshotFailed.value) {
    window.open(rpaScreenshotUrl.value, '_blank', 'noopener')
    return
  }
  viewer.value = {
    open: true,
    name: '官网验真截图',
    kind: 'image',
    url: rpaScreenshotUrl.value,
    path: '',
    owned: false,
  }
}

function closeViewer() {
  const current = viewer.value
  if (current.owned && current.url) URL.revokeObjectURL(current.url)
  viewer.value = { open: false, name: '', kind: '', url: '', path: '', owned: false }
}

async function downloadAttachment(attachment) {
  if (!attachment?.relative_path) return
  if (attachment.preview_url) {
    window.open(attachment.preview_url, '_blank', 'noopener')
    return
  }
  try {
    const blob = await tobaccoApi.fetchSourceFile(attachment.relative_path, true)
    const url = URL.createObjectURL(blob)
    const link = document.createElement('a')
    link.href = url
    link.download = attachment.file_name || attachment.doc_subject || 'OA 附件'
    document.body.appendChild(link)
    link.click()
    link.remove()
    setTimeout(() => URL.revokeObjectURL(url), 0)
  } catch (error) {
    showToast(error.message || '附件下载失败')
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

function openManualReview(decision) {
  pendingDecision.value = decision
  manualComment.value = ''
  reviewChecks.value = { original: false, rpa: false, fields: false }
  manualDialogVisible.value = true
}

async function beforeManualDialogClose(action) {
  if (action !== 'confirm') return true
  if (!checksComplete.value) {
    showToast('请先逐项确认证据已核对')
    return false
  }
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
function formatTime(value) { return formatReportTime(value) }

function attachmentRoleLabel(role) {
  return {
    tobacco_license: '烟草证',
    business_license: '烟草持证主体营业执照',
    franchisee_business_license: '加盟店营业执照',
    selected_attachment: '核对选用附件',
  }[role] || 'OA 附件'
}
function attachmentRoleShortLabel(role) {
  return {
    tobacco_license: '烟草证',
    business_license: '营业执照',
    franchisee_business_license: '加盟店执照',
    selected_attachment: '其他附件',
  }[role] || '附件'
}
function attachmentRoleRank(role) {
  return ['tobacco_license', 'business_license', 'franchisee_business_license', 'selected_attachment'].indexOf(role) === -1
    ? 9
    : ['tobacco_license', 'business_license', 'franchisee_business_license', 'selected_attachment'].indexOf(role)
}
function attachmentKind(fileName) {
  const extension = String(fileName || '').split('.').pop().toLowerCase()
  if (['jpg', 'jpeg', 'png', 'gif', 'bmp', 'webp'].includes(extension)) return 'image'
  if (extension === 'pdf') return 'pdf'
  return 'other'
}

function ruleSolution(rule) {
  return rule?.suggestion || '请核对证照信息后重新提交'
}

function ruleFieldDetail(rule) {
  const details = rule?.details || {}
  if (details.expected == null && details.actual == null) return ''
  return `营业执照：${details.expected ?? '-'} ／ 烟草证：${details.actual ?? '-'}`
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
.callback-header-actions { display: flex; align-items: center; gap: 10px; }.callback-header-actions > span { color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }.callback-header-actions :deep(.van-button) { border-radius: 5px; }
.callback-list { display: grid; gap: 10px; }.callback-list article { overflow: hidden; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); }.callback-list article > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-bottom: 1px solid var(--tobacco-line); background: var(--tobacco-surface-muted); }.callback-list article > header strong, .callback-list article > header span { display: block; }.callback-list article > header strong { color: var(--tobacco-ink); font-size: 13px; }.callback-list article > header span { margin-top: 3px; color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }.callback-list dl { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); margin: 0; padding: 10px 14px; }.callback-list dl div { min-width: 0; padding: 5px 8px 5px 0; }.callback-list dt { color: var(--tobacco-muted); font-size: 11px; }.callback-list dd { margin: 3px 0 0; color: #30485d; font-size: 12px; overflow-wrap: anywhere; }.callback-list details { border-top: 1px solid var(--tobacco-line); }.callback-list summary { padding: 10px 14px; color: var(--tobacco-accent); cursor: pointer; font-size: 12px; font-weight: 650; }.callback-list pre { max-height: 320px; overflow: auto; margin: 0; padding: 12px 14px; background: #17232c; color: #dbe8ee; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }.callback-error { margin: 0; padding: 10px 14px; border-top: 1px solid #f0cdca; background: #fff1f0; color: #a6443d; font-size: 12px; overflow-wrap: anywhere; }
@media (max-width: 600px) { .callback-list dl { grid-template-columns: 1fr; } }

/* Evidence desk */
.detail-shell { width: min(1180px, 100%); }
.detail-shell.has-manual-bar { padding-bottom: 140px; }
@media (max-width: 640px) { .detail-shell.has-manual-bar { padding-bottom: 240px; } }
.detail-skeleton { width: min(1180px, calc(100% - 32px)); }
.issue-summary { margin-top: 14px; padding: 14px 16px; border: 1px solid #ead6aa; border-radius: 8px; background: #fffaf0; }
.issue-summary.failed { border-color: #ecc9c6; background: #fff5f4; }
.issue-summary__head { display: flex; flex-wrap: wrap; align-items: baseline; gap: 6px 14px; }
.issue-summary__head strong { color: #6d4f1c; font-size: 14px; }
.issue-summary.failed .issue-summary__head strong { color: #963f39; }
.issue-summary__head span { color: #7c6a4b; font-size: 12px; line-height: 1.5; }
.issue-summary.failed .issue-summary__head span { color: #8a5a55; }
.issue-list { display: grid; gap: 8px; margin: 10px 0 0; padding: 0; list-style: none; }
.issue-list li { display: grid; gap: 2px; padding-left: 10px; border-left: 2px solid #d8b978; }
.issue-summary.failed .issue-list li { border-left-color: #d59690; }
.issue-list b { color: #4a3a1f; font-size: 13px; font-weight: 650; }
.issue-list span { color: #6b5c3f; font-size: 12px; line-height: 1.55; }
.issue-list small { color: #7d8e9d; font-size: 11px; overflow-wrap: anywhere; }

.evidence-section .section-header { margin-bottom: 12px; }
.evidence-desk { display: grid; grid-template-columns: minmax(0, 1.3fr) minmax(0, 0.7fr); gap: 12px; align-items: start; }
.evidence-col { min-width: 0; padding: 14px; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); }
.evidence-col__title { display: flex; align-items: baseline; justify-content: space-between; gap: 8px; margin: 0 0 10px; padding-bottom: 8px; border-bottom: 1px solid var(--tobacco-line); }
.evidence-col__title span { color: var(--tobacco-ink); font-size: 14px; font-weight: 700; }
.evidence-col__title small { color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; font-weight: 400; }
.evidence-empty, .evidence-hint { margin: 8px 0 0; color: var(--tobacco-muted); font-size: 12px; line-height: 1.5; }

/* 原件与官网截图并排对照 */
.rpa-status-line { margin-bottom: 10px; }
.rpa-status-line .rpa-status { padding: 10px 12px; border-radius: 6px; font-size: 13px; }
.compare-stage { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 10px; }
.compare-pane { display: grid; min-width: 0; gap: 6px; margin: 0; }
.compare-pane__frame { display: flex; width: 100%; height: 320px; align-items: center; justify-content: center; padding: 0; overflow: hidden; border: 1px solid var(--tobacco-line); border-radius: 6px; background: #f2f6f8; cursor: zoom-in; }
.compare-pane__frame:disabled { cursor: default; }
.compare-pane__frame img { display: block; width: 100%; height: 100%; object-fit: contain; }
.compare-placeholder { display: flex; align-items: center; justify-content: center; flex-direction: column; gap: 5px; padding: 12px; color: #8aa0ae; font-size: 12px; text-align: center; }
.compare-placeholder .van-icon { font-size: 28px; }
.compare-placeholder b { color: #60798a; font-weight: 600; }
.compare-placeholder em { color: #93a6b3; font-size: 11px; font-style: normal; }
.compare-pane__picker { position: relative; display: grid; grid-template-columns: auto minmax(0, 1fr); align-items: center; gap: 6px; }
.compare-pane__picker > span { padding: 2px 6px; border-radius: 3px; background: var(--tobacco-surface-muted); color: var(--tobacco-muted); font-size: 11px; }
.compare-pane__picker select { width: 100%; min-width: 0; height: 28px; padding: 0 22px 0 8px; border: 1px solid var(--tobacco-line-strong); border-radius: 5px; appearance: none; background: #fff; color: #30485d; cursor: pointer; font-family: inherit; font-size: 12px; }
.compare-pane__picker select:focus-visible { border-color: var(--tobacco-accent); outline: 2px solid rgba(23, 103, 132, 0.18); }
.compare-pane__picker .van-icon { position: absolute; right: 6px; color: #8aa0ae; font-size: 12px; pointer-events: none; }
.compare-pane__note { margin: 0; color: var(--tobacco-muted); font-size: 11px; }

.rpa-meta { margin-top: 12px; padding: 10px 14px; border: 1px solid var(--tobacco-line); border-radius: 6px; background: #fbfcfd; }
.rpa-meta .wide { grid-column: span 2; }
.store-evidence--inline { margin-top: 12px; }

.fold-section { overflow: hidden; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); }
.fold-section > summary { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 14px 16px; cursor: pointer; list-style: none; }
.fold-section > summary::-webkit-details-marker { display: none; }
.fold-section > summary::after { content: '展开'; color: var(--tobacco-accent); font-size: 12px; }
.fold-section[open] > summary::after { content: '收起'; }
.fold-section > summary .eyebrow { margin: 0 0 3px; color: var(--tobacco-muted); font-size: 12px; }
.fold-section > summary h2 { margin: 0; color: var(--tobacco-ink); font-size: 17px; font-weight: 700; }
.fold-meta { color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; overflow-wrap: anywhere; }
.fold-section .rule-list, .fold-section .oa-section { border: 0; border-top: 1px solid var(--tobacco-line); border-radius: 0; }
.fold-section .oa-section { padding: 14px 16px 16px; }
.attachment-actions { display: flex; flex: 0 0 auto; gap: 6px; }
.attachment-actions :deep(.van-button) { border-radius: 5px; }

/* 固定处置条从侧边栏右侧开始，避免遮挡导航 */
.manual-actions { position: fixed; right: 0; bottom: 0; left: 238px; z-index: 30; display: flex; justify-content: center; flex-direction: column; gap: 4px; margin: 0; padding: 10px 16px calc(10px + env(safe-area-inset-bottom)); border: 0; border-top: 1px solid #e3d5b8; border-radius: 0; background: rgba(255, 252, 244, 0.97); box-shadow: 0 -6px 24px rgba(22, 42, 58, 0.08); backdrop-filter: blur(8px); }
.manual-actions__inner { display: flex; width: min(1180px, 100%); margin: 0 auto; align-items: center; justify-content: space-between; gap: 14px; }
.manual-summary { display: grid; gap: 2px; min-width: 0; }
.manual-summary strong { color: #5f4a28; font-size: 13px; }
.manual-summary span { margin: 0; color: #7c6a4b; font-size: 12px; line-height: 1.45; }
.manual-checks { display: grid; gap: 8px; margin: 16px 16px 0; padding: 12px 14px; border: 1px solid #e3d5b8; border-radius: 6px; background: #fffaf0; }
.manual-checks > strong { color: #5f4a28; font-size: 13px; }
.manual-checks :deep(.van-checkbox) { align-items: flex-start; }
.manual-checks :deep(.van-checkbox__label) { color: #6b5c3f; font-size: 12px; line-height: 1.5; }
.manual-actions__buttons { display: flex; flex-wrap: wrap; align-items: center; gap: 8px; }
.manual-impact { width: min(1180px, 100%); margin: 2px auto 0; color: #847455 !important; font-size: 11px !important; }
@media (max-width: 1050px) and (min-width: 641px) {
  .manual-actions { left: 76px; }
}
@media (max-width: 640px) {
  .manual-actions { left: 0; bottom: calc(66px + env(safe-area-inset-bottom)); padding-bottom: 10px; }
  .manual-actions__inner { flex-direction: column; align-items: stretch; gap: 8px; }
  .manual-summary span { font-size: 11px; }
  .manual-actions__buttons :deep(.van-button) { flex: 1 1 auto; }
  .manual-impact { text-align: center; }
}
@media (max-width: 900px) {
  .evidence-desk { display: block; }
  .evidence-col + .evidence-col { margin-top: 12px; }
}
@media (max-width: 560px) {
  .compare-stage { gap: 6px; }
  .compare-pane__frame { height: 200px; }
  .compare-pane__picker { gap: 4px; }
  .compare-pane__picker > span { padding: 2px 4px; font-size: 10px; }
  .compare-pane__picker select { height: 26px; padding-left: 6px; font-size: 11px; }
}

.evidence-viewer { position: fixed; inset: 0; z-index: 100; display: flex; flex-direction: column; background: rgba(12, 23, 31, 0.9); }
.evidence-viewer > header { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 16px; color: #fff; }
.evidence-viewer > header strong { overflow: hidden; font-size: 14px; text-overflow: ellipsis; white-space: nowrap; }
.evidence-viewer > header > div { display: flex; flex: 0 0 auto; gap: 6px; }
.evidence-viewer__body { display: flex; flex: 1; min-height: 0; align-items: center; justify-content: center; padding: 0 16px 16px; }
.evidence-viewer__body img { max-width: 100%; max-height: 100%; border-radius: 4px; background: #fff; object-fit: contain; }
.evidence-viewer__body iframe { width: min(960px, 100%); height: 100%; border: 0; border-radius: 4px; background: #fff; }
.evidence-viewer__unsupported { display: grid; gap: 10px; color: #dbe8ee; font-size: 13px; text-align: center; }
.evidence-viewer__unsupported a { color: #8fd0ec; }

@media (max-width: 600px) {
  .fold-section > summary { flex-wrap: wrap; }
  .rpa-meta { grid-template-columns: 1fr; }
  .rpa-meta .wide { grid-column: span 1; }
  .evidence-viewer > header { flex-direction: column; align-items: stretch; }
}
</style>
