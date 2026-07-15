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
            <div class="ms-document__meta">
              流程 {{ document.source.requestid || '-' }} · 附件 {{ document.source.docid || '-' }}
            </div>
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
              <div class="ms-file__meta">{{ formatFileSize(file.file_size) }}<span v-if="file.content_type"> · {{ file.content_type }}</span></div>
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
          round
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
.manual-search {
  padding: 0 0 4px;
}
.ms-error {
  padding: 9px 12px;
  margin: 4px 0 0;
  border-radius: 6px;
  background: #fff5f4;
  color: #c83b32;
  font-size: 13px;
  line-height: 1.45;
}
.ms-empty { margin: 4px 0 0; }
.ms-documents { margin-top: 8px; }
.ms-document {
  padding: 12px;
  margin-bottom: 8px;
  border: 1px solid #f0f2f4;
  border-radius: 8px;
  background: #fafbfc;
}
.ms-document__header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.ms-document__title { color: #1f2933; font-size: 14px; font-weight: 600; }
.ms-document__meta, .ms-file__meta { margin-top: 3px; color: #8a949e; font-size: 12px; line-height: 1.4; }
.ms-file {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 8px 0;
}
.ms-file + .ms-file { border-top: 1px solid #f0f2f4; }
.ms-file__body { min-width: 0; flex: 1; }
.ms-file__name {
  overflow: hidden;
  color: #323233;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
  display: flex;
  align-items: center;
  gap: 6px;
}
.ms-file__actions { display: flex; flex-shrink: 0; gap: 6px; }
.ms-action-bar {
  margin-top: 8px;
  text-align: center;
}
:deep(.van-field) { padding: 12px 0; }
:deep(.van-field__label) { width: 72px; color: #323233; }
</style>
