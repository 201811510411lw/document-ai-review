<template>
  <div class="detail-page">
    <van-nav-bar title="比对详情" left-arrow @click-left="router.back()" />

    <div v-if="loading" class="page-loading">
      <van-loading size="24">加载中...</van-loading>
    </div>

    <template v-if="report">
      <!-- 头部 -->
      <div class="detail-header">
        <h2 class="company-name">{{ report.company_name }}</h2>
        <div class="overall-result" :class="report.overall_result === '通过' ? 'pass' : 'fail'">
          <van-icon :name="report.overall_result === '通过' ? 'success' : 'cross'" size="20" />
          <span>{{ report.overall_result === '通过' ? '核验通过' : '核验未通过' }}</span>
        </div>
        <div class="compare-time">比对时间: {{ report.compare_time || report.created_at?.slice(0, 10) || '-' }}</div>
        <div v-if="report.review_mode === 'store_in_store'" class="compare-time">模式: 店中店</div>
      </div>

      <div v-if="report.needs_manual_review || report.overall_result === '待校验'" class="manual-actions">
        <van-button size="small" type="primary" :loading="manualLoading" @click="submitManualReview('APPROVE')">人工通过</van-button>
        <van-button size="small" plain type="danger" :loading="manualLoading" @click="submitManualReview('REJECT')">驳回</van-button>
        <van-button size="small" plain :loading="manualLoading" @click="submitManualReview('REQUEST_MORE_INFO')">要求补件</van-button>
      </div>

      <template v-if="report.rule_results?.length">
        <div class="section-title">自动核对结论</div>
        <div class="compare-grid">
          <div v-for="rule in report.rule_results" :key="rule.rule_code" class="compare-item" :class="rule.passed ? 'match' : 'mismatch'">
            <div class="field-header"><van-icon :name="rule.passed ? 'success' : 'warning-o'" :color="rule.passed ? '#07c160' : '#ee0a24'" /><span>{{ rule.rule_name }}</span></div>
            <div class="field-values"><div class="value-row"><span class="val">{{ rule.message }}</span></div></div>
          </div>
        </div>
      </template>

      <template v-if="report.review_mode === 'store_in_store'">
        <div class="section-title">店中店证据链</div>
        <div class="compare-grid">
          <div class="compare-item" :class="report.comparison?.differences?.some((item) => item.rule_code === 'STORE_IN_STORE_RELATIONSHIP_EVIDENCE') ? 'mismatch' : 'match'">
            <div class="field-header"><span>加盟/联营/场地授权凭证</span></div>
            <div class="field-values"><div class="value-row"><span class="label">文件</span><span class="val">{{ report.comparison?.store_in_store?.relationship_evidence?.document_id || '-' }}</span></div></div>
          </div>
          <div class="compare-item" :class="report.comparison?.differences?.some((item) => item.rule_code === 'STORE_IN_STORE_ADDRESS_COVERAGE') ? 'mismatch' : 'match'">
            <div class="field-header"><span>多经营地址佐证</span></div>
            <div class="field-values"><div class="value-row"><span class="label">地址</span><span class="val">{{ report.comparison?.store_in_store?.multi_address_evidence?.addresses?.join('、') || '营业执照登记地址' }}</span></div></div>
          </div>
        </div>
      </template>

      <template v-if="report.oa">
        <div class="section-title">OA 来源与附件</div>
        <div class="oa-source">
          <div class="oa-meta-grid">
            <div class="oa-meta"><span>流程号</span><strong>{{ report.oa.requestid || '-' }}</strong></div>
            <div class="oa-meta"><span>流程状态</span><strong>{{ report.oa.request_status || '-' }}</strong></div>
            <div class="oa-meta oa-meta-wide"><span>流程标题</span><strong>{{ report.oa.request_name || report.oa.summary_title || '-' }}</strong></div>
            <div class="oa-meta oa-meta-wide"><span>提交时间</span><strong>{{ [report.oa.created_date, report.oa.created_time].filter(Boolean).join(' ') || '-' }}</strong></div>
          </div>
          <div v-if="report.oa.content_summary" class="oa-content">
            <div class="oa-content-label">OA 申请正文</div>
            <div class="oa-content-text">{{ report.oa.content_summary }}</div>
          </div>
          <div v-if="report.oa.unavailable_message" class="oa-unavailable">{{ report.oa.unavailable_message }}</div>
          <div v-if="report.oa.attachments?.length" class="oa-attachments">
            <div class="oa-content-label">原始附件</div>
            <div v-for="(attachment, index) in report.oa.attachments" :key="`${attachment.docid || 'attachment'}-${attachment.relative_path || index}`" class="oa-attachment">
              <div class="oa-attachment-info">
                <van-icon name="description" color="#1989fa" />
                <div>
                  <div class="oa-attachment-name">{{ attachment.file_name || attachment.doc_subject || 'OA 附件' }}</div>
                  <div class="oa-attachment-meta">{{ attachmentRoleLabel(attachment.document_role) }}<span v-if="attachment.docid"> · 文档 {{ attachment.docid }}</span></div>
                </div>
              </div>
              <van-button v-if="attachment.relative_path" size="small" plain type="primary" icon="eye-o" @click="previewOaAttachment(attachment)">预览</van-button>
              <span v-else class="attachment-unavailable">未落盘</span>
            </div>
          </div>
        </div>
      </template>

      <!-- 比对结果表格 -->
      <div class="section-title">字段比对</div>
      <div class="compare-grid">
        <!-- 证照类型 -->
        <div class="compare-item" :class="report.type_match === '正确' ? 'match' : 'mismatch'">
          <div class="field-header">
            <van-icon :name="report.type_match === '正确' ? 'success' : 'cross'"
              :color="report.type_match === '正确' ? '#07c160' : '#ee0a24'" />
            <span>证照类型</span>
          </div>
          <div class="field-values">
            <div class="value-row"><span class="label">营业执照</span><span class="val">{{ report.business_license_name?.slice(0, 6) || '-' }}</span></div>
            <div class="value-row"><span class="label">烟草证</span><span class="val">烟草专卖零售许可证</span></div>
          </div>
          <div class="field-verdict">{{ report.type_match }}</div>
        </div>

        <!-- 企业名称 -->
        <div class="compare-item" :class="report.name_match === '匹配' ? 'match' : 'mismatch'">
          <div class="field-header">
            <van-icon :name="report.name_match === '匹配' ? 'success' : 'cross'"
              :color="report.name_match === '匹配' ? '#07c160' : '#ee0a24'" />
            <span>企业名称</span>
          </div>
          <div class="field-values">
            <div class="value-row"><span class="label">营业执照</span><span class="val">{{ report.business_license_name || '-' }}</span></div>
            <div class="value-row"><span class="label">烟草证</span><span class="val">{{ report.tobacco_license_name || '-' }}</span></div>
          </div>
          <div class="field-verdict">{{ report.name_match }}</div>
        </div>

        <!-- 经营场所 -->
        <div class="compare-item" :class="report.address_match === '匹配' ? 'match' : 'mismatch'">
          <div class="field-header">
            <van-icon :name="report.address_match === '匹配' ? 'success' : 'cross'"
              :color="report.address_match === '匹配' ? '#07c160' : '#ee0a24'" />
            <span>经营场所</span>
          </div>
          <div class="field-values">
            <div class="value-row"><span class="label">营业执照</span><span class="val">{{ report.business_license_address || '-' }}</span></div>
            <div class="value-row"><span class="label">烟草证</span><span class="val">{{ report.tobacco_license_address || '-' }}</span></div>
          </div>
          <div class="field-verdict">{{ report.address_match }}</div>
        </div>

        <!-- 负责人 -->
        <div class="compare-item" :class="report.person_match === '匹配' ? 'match' : 'mismatch'">
          <div class="field-header">
            <van-icon :name="report.person_match === '匹配' ? 'success' : 'cross'"
              :color="report.person_match === '匹配' ? '#07c160' : '#ee0a24'" />
            <span>负责人</span>
          </div>
          <div class="field-values">
            <div class="value-row"><span class="label">营业执照</span><span class="val">{{ report.business_license_person || '-' }}</span></div>
            <div class="value-row"><span class="label">烟草证</span><span class="val">{{ report.tobacco_license_person || '-' }}</span></div>
          </div>
          <div class="field-verdict">{{ report.person_match }}</div>
        </div>

        <!-- 有效期 -->
        <div class="compare-item" :class="report.validity_status === '未过期' ? 'match' : 'mismatch'">
          <div class="field-header">
            <van-icon :name="report.validity_status === '未过期' ? 'success' : 'cross'"
              :color="report.validity_status === '未过期' ? '#07c160' : '#ee0a24'" />
            <span>有效期</span>
          </div>
          <div class="field-values">
            <div class="value-row"><span class="label">烟草证</span><span class="val">{{ report.validity_status }}</span></div>
          </div>
          <div class="field-verdict">{{ report.validity_status }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { tobaccoApi } from '@/api'
import { showToast } from 'vant'

const router = useRouter()
const route = useRoute()
const report = ref(null)
const loading = ref(true)
const manualLoading = ref(false)

onMounted(async () => {
  try {
    const res = await tobaccoApi.detail(route.params.id)
    report.value = res.report || res
  } catch (e) {
    showToast('加载失败')
  } finally {
    loading.value = false
  }
})

async function submitManualReview(decision) {
  manualLoading.value = true
  try {
    const res = await tobaccoApi.manualReview(route.params.id, decision)
    report.value = res.report || report.value
    showToast(decision === 'APPROVE' ? '已人工通过' : decision === 'REJECT' ? '已驳回' : '已标记为待补件')
  } catch (e) {
    showToast(e.message || '人工复核提交失败')
  } finally {
    manualLoading.value = false
  }
}

function attachmentRoleLabel(role) {
  return {
    tobacco_license: '烟草证',
    business_license: '营业执照',
    selected_attachment: '核对选用附件',
  }[role] || 'OA 附件'
}

async function previewOaAttachment(attachment) {
  // Open synchronously so mobile browsers retain the click gesture.
  const previewWindow = window.open('', '_blank')
  try {
    const blob = await tobaccoApi.fetchSourceFile(attachment.relative_path)
    const url = URL.createObjectURL(blob)
    if (previewWindow) {
      previewWindow.opener = null
      previewWindow.location.href = url
    } else {
      window.location.assign(url)
    }
    window.setTimeout(() => URL.revokeObjectURL(url), 60000)
  } catch (error) {
    previewWindow?.close()
    showToast(error.message || '附件预览失败')
  }
}
</script>

<style scoped>
.detail-page { padding-bottom: 32px; }
.page-loading { display: flex; justify-content: center; padding: 60px; }
.detail-header {
  background: #fff;
  padding: 20px 16px;
  margin-bottom: 12px;
  text-align: center;
}
.oa-source {
  margin: 0 12px 16px;
  border: 1px solid #ebedf0;
  border-radius: 8px;
  overflow: hidden;
}
.oa-meta-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 0;
  border-bottom: 1px solid #ebedf0;
}
.oa-meta {
  min-width: 0;
  padding: 10px 12px;
  border-bottom: 1px solid #f5f6f8;
}
.oa-meta:nth-last-child(-n + 2) { border-bottom: 0; }
.oa-meta:nth-child(odd) { border-right: 1px solid #f5f6f8; }
.oa-meta-wide { grid-column: span 2; border-right: 0 !important; }
.oa-meta span, .oa-content-label { display: block; margin-bottom: 4px; color: #969799; font-size: 12px; }
.oa-meta strong { display: block; color: #323233; font-size: 13px; font-weight: 500; line-height: 1.45; overflow-wrap: anywhere; }
.oa-content { padding: 10px 12px; border-bottom: 1px solid #ebedf0; }
.oa-content-text { color: #323233; font-size: 13px; line-height: 1.55; white-space: pre-wrap; overflow-wrap: anywhere; }
.oa-unavailable { padding: 10px 12px; color: #969799; font-size: 13px; line-height: 1.5; background: #fafafa; }
.oa-attachments { padding: 10px 12px; }
.oa-attachment { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 8px 0; }
.oa-attachment + .oa-attachment { border-top: 1px solid #f5f6f8; }
.oa-attachment-info { min-width: 0; display: flex; align-items: center; gap: 8px; }
.oa-attachment-name { color: #323233; font-size: 13px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.oa-attachment-meta, .attachment-unavailable { color: #969799; font-size: 12px; }
.company-name { font-size: 18px; font-weight: 600; margin: 0 0 8px; }
.overall-result {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 15px;
  font-weight: 600;
}
.overall-result.pass { background: #e8fae8; color: #07c160; }
.overall-result.fail { background: #ffeeed; color: #ee0a24; }
.compare-time { font-size: 12px; color: #969799; margin-top: 8px; }
.manual-actions { display: flex; gap: 8px; padding: 12px 16px 0; }
.section-title {
  font-size: 14px; font-weight: 600; color: #323233;
  padding: 16px 16px 8px;
}
.compare-grid { margin: 0 16px; display: flex; flex-direction: column; gap: 10px; }
.compare-item {
  background: #fff;
  border-radius: 8px;
  padding: 12px 14px;
  border-left: 3px solid #dcdee0;
}
.compare-item.match { border-left-color: #07c160; }
.compare-item.mismatch { border-left-color: #ee0a24; }
.field-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #323233;
  margin-bottom: 8px;
}
.field-values {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.value-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
}
.label {
  color: #969799;
  width: 60px;
  flex-shrink: 0;
}
.val { color: #323233; }
.field-verdict {
  margin-top: 6px;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  display: inline-block;
}
.match .field-verdict { background: #e8fae8; color: #07c160; }
.mismatch .field-verdict { background: #ffeeed; color: #ee0a24; }
</style>
