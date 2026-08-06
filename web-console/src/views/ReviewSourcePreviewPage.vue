<template>
  <div class="preview-page">
    <van-nav-bar title="证照原图" left-arrow @click-left="closePreview" />

    <div v-if="loading && previewKind === 'unsupported'" class="preview-loading">
      <van-loading size="26">正在加载证照...</van-loading>
    </div>

    <div v-else-if="errorMessage" class="preview-error">
      <van-empty image="error" :description="errorMessage">
        <van-button plain type="primary" size="small" @click="loadSourceFile">重新加载</van-button>
      </van-empty>
    </div>

    <div v-else-if="previewKind !== 'unsupported'" class="preview-content">
      <div v-if="loading" class="preview-rendering">
        <van-loading size="24">正在渲染原文件...</van-loading>
      </div>
      <img v-if="previewKind === 'image'" :src="sourceUrl" alt="证照原图" class="source-image">
      <div v-else ref="pdfContainer" class="source-pdf-pages" aria-label="PDF 原文件预览" :aria-busy="loading" />
    </div>
  </div>
</template>

<script setup>
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { reviewApi } from '@/api'
import {
  renderReviewPdfPages,
  reviewSourcePreviewKind,
} from '@/features/review/sourcePreview.js'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const errorMessage = ref('')
const sourceUrl = ref('')
const mimeType = ref('')
const previewKind = ref('unsupported')
const pdfContainer = ref(null)
let activeLoadController = null

function releaseSourceUrl() {
  activeLoadController?.abort()
  activeLoadController = null
  if (sourceUrl.value) {
    URL.revokeObjectURL(sourceUrl.value)
    sourceUrl.value = ''
  }
  pdfContainer.value?.replaceChildren()
}

async function loadSourceFile() {
  releaseSourceUrl()
  const loadController = new AbortController()
  activeLoadController = loadController
  loading.value = true
  errorMessage.value = ''
  try {
    const content = await reviewApi.sourceFile(route.params.id)
    mimeType.value = content.type || 'application/pdf'
    previewKind.value = reviewSourcePreviewKind(mimeType.value)
    if (previewKind.value === 'unsupported') {
      throw new Error('该附件格式不支持在线预览')
    }
    if (previewKind.value === 'image') {
      sourceUrl.value = URL.createObjectURL(content)
      return
    }

    await nextTick()
    const [pdfjs, workerModule] = await Promise.all([
      import('pdfjs-dist/legacy/build/pdf.mjs'),
      import('pdfjs-dist/legacy/build/pdf.worker.min.mjs?url'),
    ])
    pdfjs.GlobalWorkerOptions.workerSrc = workerModule.default
    await renderReviewPdfPages({
      data: new Uint8Array(await content.arrayBuffer()),
      container: pdfContainer.value,
      getDocument: pdfjs.getDocument,
      signal: loadController.signal,
    })
  } catch (error) {
    if (error.name === 'AbortError') return
    previewKind.value = 'unsupported'
    errorMessage.value = error.message || '证照附件加载失败'
  } finally {
    if (activeLoadController === loadController) {
      activeLoadController = null
      loading.value = false
    }
  }
}

function closePreview() {
  if (window.history.length > 1) {
    router.back()
  } else {
    window.close()
  }
}

onMounted(loadSourceFile)
onBeforeUnmount(releaseSourceUrl)
</script>

<style scoped>
.preview-page {
  min-height: 100vh;
  background: #f5f6f8;
}
.preview-loading,
.preview-error {
  min-height: calc(100vh - 46px);
  display: flex;
  align-items: center;
  justify-content: center;
}
.preview-content {
  position: relative;
  min-height: calc(100vh - 46px);
  padding: 12px;
  box-sizing: border-box;
}
.preview-rendering {
  position: sticky;
  z-index: 1;
  top: 8px;
  width: fit-content;
  margin: 0 auto 12px;
  padding: 8px 12px;
  border-radius: 4px;
  color: #334155;
  background: rgb(255 255 255 / 92%);
  box-shadow: 0 1px 4px rgb(15 23 42 / 16%);
}
.source-image {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
  background: #fff;
}
.source-pdf-pages {
  display: grid;
  justify-items: center;
  gap: 12px;
  width: 100%;
}
.source-pdf-pages :deep(.source-pdf-page) {
  display: block;
  max-width: 100%;
  height: auto !important;
  background: #fff;
  box-shadow: 0 1px 3px rgb(15 23 42 / 14%);
}
</style>
