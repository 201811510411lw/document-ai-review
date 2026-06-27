<template>
  <div class="import-page">
    <van-nav-bar title="批量导入证照" left-arrow @click-left="router.push('/admin')" />

    <van-cell-group title="导入文件">
      <van-cell title="支持格式" value="CSV / XLSX" />
      <van-cell title="处理方式" value="解析预览，不自动入库" />
      <div class="upload-box">
        <van-uploader
          v-model="fileList"
          accept=".csv,.xlsx"
          max-count="1"
          :after-read="afterRead"
        />
        <van-button
          type="primary"
          block
          :disabled="!selectedFile || loading"
          :loading="loading"
          @click="submitPreview"
        >
          解析预览
        </van-button>
      </div>
    </van-cell-group>

    <van-cell-group v-if="result" title="解析结果">
      <van-cell title="状态" :value="result.message" />
      <van-cell title="匹配记录" :value="`${result.success_count || 0} 条`" />
      <van-cell title="未匹配" :value="`${result.failure_count || 0} 条`" />
    </van-cell-group>

    <van-cell-group v-if="result?.errors?.length" title="错误原因">
      <van-cell
        v-for="item in result.errors"
        :key="item.value"
        :title="item.value"
        :label="item.reason"
      />
    </van-cell-group>

    <div v-if="result?.records?.length" class="records">
      <cert-result-card
        v-for="record in result.records"
        :key="record.id"
        :record="record"
      />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import { adminApi } from '@/api'
import { showToast } from 'vant'
import CertResultCard from '@/components/CertResultCard.vue'

const router = useRouter()
const fileList = ref([])
const selectedFile = ref(null)
const loading = ref(false)
const result = ref(null)

function afterRead(file) {
  selectedFile.value = file.file
}

async function submitPreview() {
  if (!selectedFile.value) {
    showToast('请先选择文件')
    return
  }
  loading.value = true
  try {
    result.value = await adminApi.importPreview(selectedFile.value)
  } catch (error) {
    showToast('解析失败: ' + error.message)
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.import-page {
  padding-bottom: 16px;
}
.upload-box {
  padding: 16px;
  display: grid;
  gap: 12px;
}
.records {
  padding: 12px 16px;
}
</style>
