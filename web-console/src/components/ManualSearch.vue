<template>
  <div class="manual-search">
    <van-field
      :model-value="storeIdentifier"
      label="门店编号"
      placeholder="请输入门店编号"
      clearable
      :disabled="sourceLoading"
      @update:model-value="$emit('update:storeIdentifier', $event)"
      @keyup.enter="$emit('fetch')"
    >
      <template #button>
        <van-button
          size="small"
          type="primary"
          :loading="sourceLoading"
          :disabled="!storeIdentifier"
          @click="$emit('fetch')"
        >获取</van-button>
      </template>
    </van-field>

    <div v-if="sourceError" class="ms-error">{{ sourceError }}</div>

    <div v-if="sourceQueried && !sourceLoading && !sourceDocuments.length" class="ms-empty">
      <van-empty image-size="56" description="未找到来源附件" />
    </div>

    <div v-if="sourceDocuments.length" class="ms-documents">
      <article v-for="document in sourceDocuments" :key="documentKey(document)" class="ms-document">
        <div class="ms-document__header">
          <div>
            <div class="ms-document__title">{{ document.source.store_name || document.source.store_code || storeIdentifier }}</div>
            <div class="ms-document__meta"><span>流程 {{ document.source.requestid || '-' }}</span><span>附件 {{ document.source.docid || '-' }}</span></div>
          </div>
          <van-tag plain type="primary">{{ document.files.length }} 个文件</van-tag>
        </div>

        <div class="ms-file-list">
          <div v-for="file in document.files" :key="file.relative_path" class="ms-file">
            <div class="ms-file__body">
              <div class="ms-file__name">
                <van-icon :name="fileIcon(file)" size="14" color="#1989fa" />
                {{ file.file_name }}
              </div>
              <div class="ms-file__meta"><span>{{ formatFileSize(file.file_size) }}</span><span v-if="file.content_type">{{ file.content_type }}</span></div>
            </div>
            <div class="ms-file__actions">
              <van-button size="small" plain type="primary" :loading="activeFilePath === file.relative_path" @click="$emit('preview', file)">预览</van-button>
              <van-button size="small" plain :loading="activeFilePath === file.relative_path" @click="$emit('download', file)">下载</van-button>
            </div>
          </div>
        </div>
      </article>

      <div class="ms-action-bar">
        <van-button
          type="primary"
          block
          :loading="comparing"
          icon="balance-list"
          @click="$emit('trigger')"
        >提交比对</van-button>
      </div>
    </div>
  </div>
</template>

<script setup>
defineProps({
  storeIdentifier: { type: String, default: '' },
  sourceLoading: { type: Boolean, default: false },
  sourceError: { type: String, default: '' },
  sourceQueried: { type: Boolean, default: false },
  sourceDocuments: { type: Array, default: () => [] },
  activeFilePath: { type: String, default: '' },
  comparing: { type: Boolean, default: false },
})

defineEmits(['update:storeIdentifier', 'fetch', 'preview', 'download', 'trigger'])

function fileIcon(file) {
  const name = (file.file_name || '').toLowerCase()
  if (name.includes('.pdf')) return 'eye-o'
  if (name.match(/\.(jpg|jpeg|png|gif|bmp|webp)/)) return 'photo-o'
  return 'description'
}

function documentKey(document) {
  const source = document.source || {}
  return `${source.requestid || ''}-${source.docid || ''}-${source.imagefile_id || ''}`
}

function formatFileSize(size) {
  const bytes = Number(size || 0)
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
}
</script>

<style scoped>
.manual-search { padding: 0; color: var(--tobacco-ink); }.manual-search :deep(.van-field) { padding: 8px 0 12px; }.manual-search :deep(.van-field__label) { width: 76px; color: var(--tobacco-ink); font-size: 13px; font-weight: 600; }.manual-search :deep(.van-field__control) { color: var(--tobacco-ink); font-size: 13px; }.manual-search :deep(.van-field__button .van-button) { border-radius: 5px; background: var(--tobacco-accent); border-color: var(--tobacco-accent); }
.ms-error { margin: 4px 0 0; padding: 10px 12px; border-left: 3px solid #c2524b; border-radius: 5px; background: #fff2f1; color: #a4433b; font-size: 13px; line-height: 1.45; }.ms-empty { margin: 4px 0 0; }.ms-documents { margin-top: 8px; }.ms-document { overflow: hidden; margin-bottom: 10px; border: 1px solid var(--tobacco-line); border-radius: 6px; background: var(--tobacco-surface); }.ms-document__header { display: flex; align-items: flex-start; justify-content: space-between; gap: 12px; padding: 12px; border-bottom: 1px solid var(--tobacco-line); background: var(--tobacco-surface-muted); }.ms-document__title { color: var(--tobacco-ink); font-size: 14px; font-weight: 650; }.ms-document__meta, .ms-file__meta { display: flex; flex-wrap: wrap; gap: 0; margin-top: 5px; color: var(--tobacco-muted); font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; line-height: 1.4; }.ms-document__meta span + span, .ms-file__meta span + span { margin-left: 8px; padding-left: 8px; border-left: 1px solid var(--tobacco-line-strong); }.ms-document__header :deep(.van-tag) { border-radius: 4px; }.ms-file { display: flex; align-items: center; justify-content: space-between; gap: 10px; padding: 11px 12px; }.ms-file + .ms-file { border-top: 1px solid var(--tobacco-line); }.ms-file__body { min-width: 0; flex: 1; }.ms-file__name { display: flex; align-items: center; gap: 7px; overflow: hidden; color: #31495c; font-size: 13px; text-overflow: ellipsis; white-space: nowrap; }.ms-file__actions { display: flex; flex-shrink: 0; gap: 6px; }.ms-file__actions :deep(.van-button), .ms-action-bar :deep(.van-button) { border-radius: 5px; }.ms-action-bar { margin-top: 10px; }.ms-action-bar :deep(.van-button) { background: var(--tobacco-accent); border-color: var(--tobacco-accent); }
@media (max-width: 600px) { .ms-file { align-items: flex-start; flex-direction: column; }.ms-file__actions { width: 100%; }.ms-file__actions :deep(.van-button) { flex: 1; } }
</style>
