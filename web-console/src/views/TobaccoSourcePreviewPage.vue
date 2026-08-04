<template>
  <div class="preview-page">
    <van-nav-bar :title="fileName" left-arrow @click-left="closePreview" />

    <div v-if="loading" class="preview-state">
      <van-loading size="26">正在加载附件...</van-loading>
    </div>

    <div v-else-if="errorMessage" class="preview-state">
      <van-empty image="error" :description="errorMessage">
        <van-button plain type="primary" size="small" @click="loadSourceFile">重新加载</van-button>
      </van-empty>
    </div>

    <div v-else-if="sourceUrl && previewKind !== 'unsupported'" class="preview-content">
      <img v-if="previewKind === 'image'" :src="sourceUrl" :alt="fileName" class="source-image">
      <iframe v-else-if="previewKind === 'pdf'" :src="sourceUrl" :title="`${fileName}预览`" class="source-document" />
    </div>

    <div v-else-if="sourceUrl" class="preview-state">
      <van-empty description="该文件类型不支持在线预览">
        <a class="download-link" :href="sourceUrl" :download="fileName">下载附件</a>
      </van-empty>
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { tobaccoApi } from '@/api'
import { createTobaccoAttachmentLoader } from '@/features/tobacco/attachmentPreview.js'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const errorMessage = ref('')
const sourceUrl = ref('')
const previewKind = ref('')

const relativePath = computed(() => String(route.query.path || ''))
const fileName = computed(() => String(route.query.name || 'OA 附件预览'))
const attachmentLoader = createTobaccoAttachmentLoader({
  fetchFile: (path) => tobaccoApi.fetchSourceFile(path),
  createObjectUrl: (content) => URL.createObjectURL(content),
  revokeObjectUrl: (url) => URL.revokeObjectURL(url),
})

async function loadSourceFile() {
  sourceUrl.value = ''
  previewKind.value = ''
  errorMessage.value = ''
  loading.value = true
  const result = await attachmentLoader.load(relativePath.value)
  if (result.status === 'stale') return
  if (result.status === 'error') errorMessage.value = result.message
  if (result.status === 'ready') {
    sourceUrl.value = result.url
    previewKind.value = result.kind
  }
  loading.value = false
}

function closePreview() {
  if (window.history.length > 1) router.back()
  else window.close()
}

watch(relativePath, loadSourceFile, { immediate: true })
onBeforeUnmount(() => attachmentLoader.dispose())
</script>

<style scoped>
.preview-page { min-height: 100vh; background: #f5f6f8; }
.preview-state { display: flex; min-height: calc(100vh - 46px); align-items: center; justify-content: center; }
.preview-content { min-height: calc(100vh - 46px); box-sizing: border-box; padding: 12px; }
.source-image { display: block; max-width: 100%; height: auto; margin: 0 auto; background: #fff; }
.source-document { display: block; width: 100%; height: calc(100vh - 70px); border: 0; background: #fff; }
.download-link { display: inline-flex; height: 34px; align-items: center; padding: 0 14px; border: 1px solid #176784; border-radius: 4px; color: #176784; background: #fff; font-size: 13px; text-decoration: none; }
</style>
