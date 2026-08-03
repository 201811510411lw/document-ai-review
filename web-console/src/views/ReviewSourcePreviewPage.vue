<template>
  <div class="preview-page">
    <van-nav-bar title="证照原图" left-arrow @click-left="closePreview" />

    <div v-if="loading" class="preview-loading">
      <van-loading size="26">正在加载证照...</van-loading>
    </div>

    <div v-else-if="errorMessage" class="preview-error">
      <van-empty image="error" :description="errorMessage">
        <van-button plain type="primary" size="small" @click="loadSourceFile">重新加载</van-button>
      </van-empty>
    </div>

    <div v-else-if="sourceUrl" class="preview-content">
      <img v-if="isImage" :src="sourceUrl" alt="证照原图" class="source-image">
      <iframe
        v-else
        :src="sourceUrl"
        title="证照文件预览"
        class="source-pdf"
      />
    </div>
  </div>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { reviewApi } from '@/api'

const route = useRoute()
const router = useRouter()
const loading = ref(true)
const errorMessage = ref('')
const sourceUrl = ref('')
const mimeType = ref('')

const isImage = computed(() => mimeType.value.startsWith('image/'))

function releaseSourceUrl() {
  if (sourceUrl.value) {
    URL.revokeObjectURL(sourceUrl.value)
    sourceUrl.value = ''
  }
}

async function loadSourceFile() {
  releaseSourceUrl()
  loading.value = true
  errorMessage.value = ''
  try {
    const content = await reviewApi.sourceFile(route.params.id)
    mimeType.value = content.type || 'application/pdf'
    sourceUrl.value = URL.createObjectURL(content)
  } catch (error) {
    errorMessage.value = error.message || '证照附件加载失败'
  } finally {
    loading.value = false
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
  min-height: calc(100vh - 46px);
  padding: 12px;
  box-sizing: border-box;
}
.source-image {
  display: block;
  max-width: 100%;
  height: auto;
  margin: 0 auto;
  background: #fff;
}
.source-pdf {
  display: block;
  width: 100%;
  height: calc(100vh - 70px);
  border: 0;
  background: #fff;
}
</style>
