<template>
  <div class="cert-card" :style="{ borderLeftColor: statusInfo.color }">
    <div class="card-header">
      <span class="status-badge" :style="{ background: statusInfo.color }">
        {{ statusInfo.icon }} {{ statusInfo.text }}
      </span>
      <van-icon name="ellipsis" @click="showActions = true" />
    </div>

    <div class="card-body">
      <h3 class="company-name" v-html="highlightText(record.company_name)"></h3>
      <div v-if="keyword && record.company_name && record.company_name.toLowerCase().includes(keyword.toLowerCase())" class="match-hint">🔍 公司名称匹配</div>
      <div v-else-if="keyword && record.credit_code && record.credit_code.toLowerCase().includes(keyword.toLowerCase())" class="match-hint">🔍 信用代码匹配</div>
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

    <!-- 时间信息 -->
    <div class="time-info">
      <div class="time-row">
        <span class="time-label">📤 SRM上传</span>
        <span class="time-value">{{ record.source_created_at ? String(record.source_created_at).substring(0,10) : '未记录' }}</span>
      </div>
      <div class="time-row">
        <span class="time-label">📋 审核时间</span>
        <span class="time-value">{{ record.created_at ? String(record.created_at).substring(0,10) : '未记录' }}</span>
      </div>
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
  keyword: { type: String, default: '' },
})

function highlightText(text) {
  if (!props.keyword || !text) return text
  const str = String(text)
  const kw = props.keyword.trim()
  if (!kw) return str
  const index = str.toLowerCase().indexOf(kw.toLowerCase())
  if (index === -1) return str
  return str.slice(0, index) + '<mark class="kw-highlight">' + str.slice(index, index + kw.length) + '</mark>' + str.slice(index + kw.length)
}

const showActions = ref(false)
const openingCert = ref(false)
const downloadingCert = ref(false)

const statusInfo = computed(() => {
  // 无证照文件 → 显示"无附件"
  if (!props.record.source_file_url) {
    return { icon: '📄', text: '无附件', color: '#c8c9cc' }
  }
  // 有文件但到期未知 → 显示"到期未知"
  if (props.record.expire_status === 'unknown') {
    return { icon: '❓', text: '到期未知', color: '#969799' }
  }
  // 有文件且有效期明确 → 显示有效期状态
  return EXPIRE_STATUS_MAP[props.record.expire_status] || { icon: '❓', text: '到期未知', color: '#969799' }
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
.upload-time {
  font-size: 11px;
  color: #969799;
  padding: 4px 0 0;
  border-top: 1px dashed #f0f0f0;
  margin-top: 4px;
}
.time-info {
  font-size: 11px;
  padding: 4px 0 0;
  border-top: 1px dashed #f0f0f0;
  margin-top: 4px;
}
.time-row {
  display: flex;
  align-items: baseline;
  padding: 1px 0;
}
.time-label {
  color: #969799;
  display: inline-block;
  min-width: 8em;
  flex-shrink: 0;
}
.time-value { color: #646566; }
/* 无附件时按钮灰显 */
.van-button--disabled { opacity: 0.4 !important; }
.match-hint {
  font-size: 11px;
  color: #1989fa;
  margin-bottom: 6px;
}
:deep(.kw-highlight) {
  background: #fff3cd;
  padding: 0 2px;
  border-radius: 2px;
  color: #ee0a24;
  font-weight: 600;
}
</style>
