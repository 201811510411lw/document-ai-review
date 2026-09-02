<template>
  <section class="manual-correction">
    <button class="manual-correction__toggle" type="button" @click="$emit('update:expanded', !expanded)">
      <span>人工复核补充</span>
      <span>{{ expanded ? '收起' : '仅识别异常时填写' }}</span>
    </button>
    <div v-if="expanded" class="manual-correction__fields">
      <p>人工填写只覆盖对应空字段或识别异常字段，仍保留 OA 附件作为证据来源。</p>
      <van-cell title="审核模式">
        <template #value>
          <van-radio-group :model-value="mode" direction="horizontal" @update:model-value="$emit('update:mode', $event)">
            <van-radio name="standard">标准</van-radio>
            <van-radio name="store_in_store">店中店</van-radio>
          </van-radio-group>
        </template>
      </van-cell>
      <van-field label="加盟商名称" :model-value="franchiseeName" @update:model-value="$emit('update:franchiseeName', $event)" />
      <p class="field-group-title">{{ mode === 'store_in_store' ? '烟草持证主体营业执照' : '营业执照' }}</p>
      <van-field label="执照主体" :model-value="businessFields.subject_name" @update:model-value="updateBusiness('subject_name', $event)" />
      <van-field label="执照地址" :model-value="businessFields.business_address" @update:model-value="updateBusiness('business_address', $event)" />
      <van-field label="执照负责人" :model-value="businessFields.legal_person" @update:model-value="updateBusiness('legal_person', $event)" />
      <p class="field-group-title">烟草专卖零售许可证</p>
      <van-field label="烟草主体" :model-value="tobaccoFields.subject_name" @update:model-value="updateTobacco('subject_name', $event)" />
      <van-field label="烟草地址" :model-value="tobaccoFields.business_address" @update:model-value="updateTobacco('business_address', $event)" />
      <van-field label="烟草负责人" :model-value="tobaccoFields.legal_person" @update:model-value="updateTobacco('legal_person', $event)" />
      <van-field label="有效截止日" placeholder="YYYY-MM-DD" :model-value="tobaccoFields.valid_to" @update:model-value="updateTobacco('valid_to', $event)" />
      <template v-if="mode === 'store_in_store'">
        <p class="field-group-title">加盟店营业执照</p>
        <van-field label="执照主体" :model-value="franchiseeBusinessFields.subject_name" @update:model-value="updateFranchiseeBusiness('subject_name', $event)" />
        <van-field label="执照地址" :model-value="franchiseeBusinessFields.business_address" @update:model-value="updateFranchiseeBusiness('business_address', $event)" />
        <van-field label="执照负责人" :model-value="franchiseeBusinessFields.legal_person" @update:model-value="updateFranchiseeBusiness('legal_person', $event)" />
        <p class="field-group-title">同一经营场所证明</p>
        <van-field label="证明文件" :model-value="samePremisesEvidence.document_id" @update:model-value="updateSamePremisesEvidence('document_id', $event)" />
        <van-field label="证明说明" type="textarea" autosize :model-value="samePremisesEvidence.description" @update:model-value="updateSamePremisesEvidence('description', $event)" />
      </template>
    </div>
  </section>
</template>

<script setup>
const props = defineProps({
  expanded: { type: Boolean, default: false },
  mode: { type: String, default: 'standard' },
  franchiseeName: { type: String, default: '' },
  businessFields: { type: Object, required: true },
  franchiseeBusinessFields: { type: Object, required: true },
  tobaccoFields: { type: Object, required: true },
  samePremisesEvidence: { type: Object, required: true },
})

const emit = defineEmits(['update:expanded', 'update:mode', 'update:franchiseeName', 'update:businessFields', 'update:franchiseeBusinessFields', 'update:tobaccoFields', 'update:samePremisesEvidence'])

function updateBusiness(field, value) { emit('update:businessFields', { ...props.businessFields, [field]: value }) }
function updateFranchiseeBusiness(field, value) { emit('update:franchiseeBusinessFields', { ...props.franchiseeBusinessFields, [field]: value }) }
function updateTobacco(field, value) { emit('update:tobaccoFields', { ...props.tobaccoFields, [field]: value }) }
function updateSamePremisesEvidence(field, value) { emit('update:samePremisesEvidence', { ...props.samePremisesEvidence, [field]: value }) }
</script>

<style scoped>
.manual-correction { overflow: hidden; margin-top: 18px; border: 1px solid var(--tobacco-line); border-radius: 8px; background: var(--tobacco-surface); }.manual-correction__toggle { display: flex; width: 100%; align-items: center; justify-content: space-between; padding: 14px; border: 0; background: var(--tobacco-surface-muted); color: var(--tobacco-ink); font-size: 14px; font-weight: 650; }.manual-correction__toggle span:last-child { color: var(--tobacco-muted); font-size: 12px; font-weight: 400; }.manual-correction__toggle:active { transform: translateY(1px); }.manual-correction__fields { padding: 0 14px 14px; }.manual-correction__fields > p:first-child { margin: 0; padding: 12px 0; color: var(--tobacco-muted); font-size: 12px; line-height: 1.55; }.field-group-title { margin: 14px 0 0; padding: 9px 0 7px; border-top: 1px solid var(--tobacco-line); color: var(--tobacco-accent); font-size: 12px; font-weight: 650; }.manual-correction :deep(.van-cell) { padding-right: 0; padding-left: 0; background: transparent; }.manual-correction :deep(.van-field__label) { color: #40586a; font-size: 13px; }.manual-correction :deep(.van-field__control) { color: var(--tobacco-ink); font-size: 13px; }.manual-correction :deep(.van-radio__icon--checked .van-icon) { border-color: var(--tobacco-accent); background: var(--tobacco-accent); }
</style>
