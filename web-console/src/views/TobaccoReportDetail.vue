<template>
  <div class="detail-page">
    <van-nav-bar title="烟草证核对结果" left-arrow @click-left="router.back()" />
    <div v-if="loading" class="detail-skeleton" aria-label="正在加载核对结果"><span></span><span></span><span></span></div>
    <van-empty v-else-if="!report" image-size="72" description="未找到该核对报告" />

    <main v-else class="detail-shell">
      <section class="decision-summary" :class="resultMeta.tone">
        <div>
          <p>审核结论</p>
          <h1>{{ report.company_name || '未识别主体名称' }}</h1>
          <span>{{ modeLabel(report.review_mode) }}<b>{{ formatTime(report.compare_time || report.created_at) }}</b></span>
        </div>
        <div class="result-badge"><van-icon :name="resultMeta.icon" /><strong>{{ resultMeta.label }}</strong></div>
      </section>

      <section v-if="canManualReview" class="manual-actions" aria-label="人工处置">
        <div><strong>需要人工处置</strong><span>自动核对结论及 OA 附件会保留在当前报告中。</span></div>
        <div class="manual-actions__buttons">
          <van-button size="small" type="primary" :loading="manualLoading" @click="submitManualReview('APPROVE')">人工通过</van-button>
          <van-button size="small" plain type="danger" :loading="manualLoading" @click="submitManualReview('REJECT')">驳回</van-button>
          <van-button size="small" plain :loading="manualLoading" @click="submitManualReview('REQUEST_MORE_INFO')">要求补件</van-button>
        </div>
      </section>

      <section class="content-section">
        <header class="section-header"><div><p>审核证据</p><h2>字段核对</h2></div><span>{{ mismatchCount }} 项异常</span></header>
        <div class="comparison-grid">
          <article v-for="field in comparisonFields" :key="field.key" class="comparison-card" :class="field.passed ? 'passed' : 'failed'">
            <header><div><van-icon :name="field.passed ? 'success' : 'cross'" /><strong>{{ field.label }}</strong></div><van-tag :type="field.passed ? 'success' : 'danger'" plain>{{ field.verdict }}</van-tag></header>
            <dl>
              <div v-for="value in field.values" :key="value.label"><dt>{{ value.label }}</dt><dd>{{ value.value || '-' }}</dd></div>
            </dl>
          </article>
        </div>
      </section>

      <section v-if="report.rule_results?.length" class="content-section">
        <header class="section-header"><div><p>规则明细</p><h2>自动审核结果</h2></div></header>
        <div class="rule-list">
          <article v-for="rule in report.rule_results" :key="rule.rule_code" :class="rule.passed ? 'passed' : 'failed'">
            <van-icon :name="rule.passed ? 'success' : 'warning-o'" />
            <div><strong>{{ rule.rule_name }}</strong><span>{{ rule.message }}</span></div>
          </article>
        </div>
      </section>

      <section v-if="report.review_mode === 'store_in_store'" class="content-section">
        <header class="section-header"><div><p>补充材料</p><h2>店中店证据链</h2></div></header>
        <div class="store-evidence">
          <div><span>加盟/联营/场地授权凭证</span><strong>{{ report.comparison?.store_in_store?.relationship_evidence?.document_id || '-' }}</strong></div>
          <div><span>多经营地址佐证</span><strong>{{ report.comparison?.store_in_store?.multi_address_evidence?.addresses?.join('、') || '营业执照登记地址' }}</strong></div>
        </div>
      </section>

      <section v-if="report.oa" class="content-section oa-section">
        <header class="section-header"><div><p>原始凭据</p><h2>OA 来源与附件</h2></div><span>流程 {{ report.oa.requestid || '-' }}</span></header>
        <dl class="oa-meta">
          <div><dt>流程状态</dt><dd>{{ report.oa.request_status || '-' }}</dd></div>
          <div><dt>提交时间</dt><dd>{{ [report.oa.created_date, report.oa.created_time].filter(Boolean).join(' ') || '-' }}</dd></div>
          <div class="wide"><dt>流程标题</dt><dd>{{ report.oa.request_name || report.oa.summary_title || '-' }}</dd></div>
        </dl>
        <div v-if="report.oa.content_summary" class="oa-content"><span>OA 申请正文</span><p>{{ report.oa.content_summary }}</p></div>
        <van-notice-bar v-if="report.oa.unavailable_message" left-icon="warning-o" color="#9d5d1d" background="#fff8e8">{{ report.oa.unavailable_message }}</van-notice-bar>
        <div v-if="report.oa.attachments?.length" class="attachment-list">
          <article v-for="(attachment, index) in report.oa.attachments" :key="`${attachment.docid || 'attachment'}-${attachment.relative_path || index}`">
            <div><van-icon name="description" color="#176784" /><span><strong>{{ attachment.file_name || attachment.doc_subject || 'OA 附件' }}</strong><small>{{ attachmentRoleLabel(attachment.document_role) }}<template v-if="attachment.docid"><b>文档 {{ attachment.docid }}</b></template></small></span></div>
            <van-button v-if="attachment.relative_path" size="small" plain type="primary" icon="eye-o" @click="previewOaAttachment(attachment)">预览</van-button>
            <em v-else>未落盘</em>
          </article>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { showToast } from 'vant'
import { tobaccoApi } from '@/api'

const router = useRouter()
const route = useRoute()
const report = ref(null)
const loading = ref(true)
const manualLoading = ref(false)

const resultMeta = computed(() => {
  const result = report.value?.overall_result
  if (result === '通过') return { label: '核对通过', tone: 'passed', icon: 'success' }
  if (result === '待校验') return { label: '待人工核验', tone: 'pending', icon: 'warning-o' }
  return { label: result || '核对未通过', tone: 'failed', icon: 'cross' }
})

const canManualReview = computed(() => report.value?.needs_manual_review || report.value?.overall_result === '待校验')
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

onMounted(loadReport)

async function loadReport() {
  loading.value = true
  try {
    const response = await tobaccoApi.detail(route.params.id)
    report.value = response.report || response
  } catch (error) {
    showToast(error.message || '加载核对报告失败')
  } finally {
    loading.value = false
  }
}

async function submitManualReview(decision) {
  manualLoading.value = true
  try {
    const response = await tobaccoApi.manualReview(route.params.id, decision)
    report.value = response.report || report.value
    showToast({ APPROVE: '已人工通过', REJECT: '已驳回', REQUEST_MORE_INFO: '已标记为待补件' }[decision])
  } catch (error) {
    showToast(error.message || '人工复核提交失败')
  } finally {
    manualLoading.value = false
  }
}

function modeLabel(mode) { return mode === 'store_in_store' ? '店中店核对' : '标准核对' }
function formatTime(value) { return value ? String(value).replace('T', ' ').slice(0, 19) : '-' }
function attachmentRoleLabel(role) { return { tobacco_license: '烟草证', business_license: '营业执照', selected_attachment: '核对选用附件' }[role] || 'OA 附件' }

async function previewOaAttachment(attachment) {
  const previewWindow = window.open('', '_blank')
  try {
    const blob = await tobaccoApi.fetchSourceFile(attachment.relative_path)
    const url = URL.createObjectURL(blob)
    if (previewWindow) { previewWindow.opener = null; previewWindow.location.href = url } else window.location.assign(url)
    window.setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (error) {
    previewWindow?.close()
    showToast(error.message || '附件预览失败')
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
.rule-list, .store-evidence, .oa-section { border-color: var(--tobacco-line); border-radius: 8px; }.rule-list article { padding: 13px 14px; border-left: 3px solid #c2524b; }.rule-list article + article { border-top-color: var(--tobacco-line); }.rule-list article.passed { border-left-color: #2f8b58; }.rule-list article > :first-child { color: #b04942; }.rule-list article.passed > :first-child { color: #27784c; }.rule-list span { color: var(--tobacco-muted); }.store-evidence { background: var(--tobacco-line); }.store-evidence div { padding: 13px 14px; }.store-evidence span { color: var(--tobacco-muted); }.oa-section { padding: 16px; background: var(--tobacco-surface); }.oa-meta, .oa-content, .attachment-list { border-top-color: var(--tobacco-line); }.oa-meta .wide { border-top-color: var(--tobacco-line); }.oa-meta dt, .oa-content > span { color: var(--tobacco-muted); }.attachment-list article + article { border-top-color: var(--tobacco-line); }.attachment-list strong { color: #30485d; }.attachment-list small, .attachment-list em { display: flex; flex-wrap: wrap; gap: 0; color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; }.attachment-list small b { margin-left: 8px; padding-left: 8px; border-left: 1px solid var(--tobacco-line-strong); font-weight: 400; }.attachment-list :deep(.van-button) { border-radius: 5px; }
@media (prefers-reduced-motion: reduce) { .detail-page *, .detail-page *::before, .detail-page *::after { transition: none !important; } }@media (max-width: 600px) { .detail-shell { padding: 18px 12px; }.decision-summary h1 { font-size: 20px; }.oa-section { padding: 13px; } }
</style>
