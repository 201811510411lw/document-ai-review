<template>
  <div class="cert-card" :style="{ borderLeftColor: statusInfo.color }">
    <div class="card-header">
      <span class="status-badge" :style="{ background: statusInfo.color }">
        {{ statusInfo.icon }} {{ statusInfo.text }}
      </span>
      <van-icon name="ellipsis" @click="showActions = true" />
    </div>

    <div class="card-body">
      <h3 class="company-name">{{ record.company_name }}</h3>
      <div class="info-grid">
        <div class="info-item">
          <span class="label">证照类型</span>
          <span class="value">{{ record.license_type || '未识别' }}</span>
        </div>
        <div class="info-item">
          <span class="label">信用代码</span>
          <span class="value">{{ record.credit_code || '未识别' }}</span>
        </div>
        <div class="info-item">
          <span class="label">法定代表人</span>
          <span class="value">{{ record.legal_person || '未识别' }}</span>
        </div>
        <div class="info-item">
          <span class="label">到期日期</span>
          <span class="value" :style="{ color: statusInfo.color }">
            {{ record.expire_date || '未知' }}
          </span>
        </div>
      </div>
    </div>

    <div class="card-footer">
      <van-button
        size="small"
        plain
        :type="hasFile ? 'primary' : 'default'"
        icon="eye-o"
        round
        :disabled="!hasFile"
        @click.stop="previewCert"
      >
        查看证照
      </van-button>
      <van-button
        size="small"
        plain
        :type="hasFile ? 'primary' : 'default'"
        icon="down"
        round
        :disabled="!hasFile"
        @click.stop="downloadSingle"
      >
        下载
      </van-button>
      <span v-if="!hasFile" class="no-file-hint">未查询到相应证照文件</span>
    </div>

    <!-- 操作菜单 -->
    <van-action-sheet v-model:show="showActions" :actions="actions" @select="onAction" />
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { EXPIRE_STATUS_MAP } from '@/utils'
import { showToast } from 'vant'

const props = defineProps({
  record: { type: Object, required: true },
})

const showActions = ref(false)
const openingCert = ref(false)
const downloadingCert = ref(false)

const statusInfo = computed(() => {
  // 无证照文件时左上角标识改为未知
  if (!props.record.source_file_url) {
    return EXPIRE_STATUS_MAP.unknown
  }
  return EXPIRE_STATUS_MAP[props.record.expire_status] || EXPIRE_STATUS_MAP.unknown
})

const hasFile = computed(() => !!props.record.source_file_url)

const actions = [
  { name: '查看证照', value: 'preview' },
  { name: '下载文件', value: 'download' },
  { name: '复制公司名称', value: 'copy' },
]

function onAction(action) {
  showActions.value = false
  switch (action.value) {
    case 'preview': previewCert(); break
    case 'download': downloadSingle(); break
    case 'copy': copyName(); break
  }
}

function previewCert() {
  if (openingCert.value) return
  if (props.record.source_file_url) {
    openingCert.value = true
    const opened = window.open(props.record.source_file_url, '_blank', 'noopener,noreferrer')
    if (!opened) {
      showToast('浏览器阻止打开，请允许弹窗后重试')
    }
    window.setTimeout(() => {
      openingCert.value = false
    }, 800)
  }
}

function downloadSingle() {
  if (downloadingCert.value) return
  if (props.record.source_file_url) {
    downloadingCert.value = true
    const a = document.createElement('a')
    a.href = props.record.source_file_url
    a.download = props.record.source_file_name || '证照文件'
    a.click()
    window.setTimeout(() => {
      downloadingCert.value = false
    }, 800)
  }
}

function copyName() {
  navigator.clipboard.writeText(props.record.company_name).then(() => {
    showToast('已复制')
  })
}
</script>

<style scoped>
.cert-card {
  background: #fff;
  border-radius: 8px;
  border-left: 4px solid;
  padding: 12px 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.status-badge {
  font-size: 11px;
  color: #fff;
  padding: 2px 8px;
  border-radius: 10px;
}
.company-name {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 8px;
  color: #323233;
}
.info-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 6px;
}
.info-item .label {
  font-size: 12px;
  color: #969799;
  display: block;
}
.info-item .value {
  font-size: 13px;
  color: #323233;
}
.card-footer {
  display: flex;
  gap: 8px;
  margin-top: 10px;
  padding-top: 10px;
  border-top: 1px solid #f5f6f8;
  align-items: center;
  flex-wrap: wrap;
}
.no-file-hint {
  font-size: 12px;
  color: #c8c9cc;
  margin-left: 4px;
}
</style>
