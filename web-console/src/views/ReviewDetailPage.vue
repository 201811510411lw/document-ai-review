<template>
  <div class="detail-page">
    <van-nav-bar title="校验详情" left-arrow @click-left="router.back()" />

    <div v-if="loading" class="page-loading">
      <van-loading size="24">加载中...</van-loading>
    </div>

    <template v-if="record">
      <!-- 头部信息 -->
      <div class="detail-header">
        <h2 class="company-name">{{ record.company_name }}</h2>
        <div class="ratio-bar">
          <div class="ratio-label">匹配率</div>
          <div class="ratio-value" :class="ratioClass">{{ formatRatio(record.match_ratio) }}</div>
        </div>
        <van-tag :type="statusTagType" size="medium">{{ statusText }}</van-tag>
        <div v-if="record.review_comment" class="comment">
          备注: {{ record.review_comment }}
        </div>
      </div>

      <!-- 字段比对 -->
      <div class="section-title">字段比对</div>
      <div class="field-list">
        <div v-for="(field, idx) in validationFields" :key="idx" class="field-item">
          <div class="field-name">{{ field.field }}</div>
          <div class="field-values">
            <div class="value-row">
              <span class="value-label">识别值</span>
              <span class="value-text" :class="{ mismatch: !field.match }">{{ field.recognized || '-' }}</span>
              <van-icon v-if="!field.match" name="cross" color="#ee0a24" />
              <van-icon v-else name="check" color="#07c160" />
            </div>
            <div class="value-row">
              <span class="value-label">数据库</span>
              <span class="value-text">{{ field.expected || '-' }}</span>
            </div>
          </div>
        </div>
      </div>

      <!-- 原文件 -->
      <div class="section-title">原文件</div>
      <div class="file-section">
        <van-button
          v-if="record.source_file_url"
          plain
          type="primary"
          size="small"
          icon="eye-o"
          @click.stop="openSourceFile"
        >
          查看证照原图
        </van-button>
        <span v-else class="no-file">无附件</span>
      </div>

      <!-- 审核操作 -->
      <div v-if="record.review_status === 'pending'" class="action-section">
        <div class="section-title">审核操作</div>
        <van-field
          v-model="comment"
          placeholder="审核备注（可选）"
          type="textarea"
          rows="2"
          autosize
        />
        <div class="action-buttons">
          <van-button type="primary" block round :loading="submitting" @click="handleConfirm">
            ✅ 认可识别结果
          </van-button>
          <van-button type="warning" block round plain :loading="submitting" @click="handleFlag">
            ❌ 标记异常
          </van-button>
        </div>
      </div>

      <!-- 已审核状态提示 -->
      <div v-else class="action-section">
        <div class="already-reviewed">
          <van-icon :name="record.review_status === 'confirmed' ? 'success' : 'warning'" />
          此记录已{{ statusText }}
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { reviewApi } from '@/api'
import { showToast, showConfirmDialog } from 'vant'

const router = useRouter()
const route = useRoute()

const record = ref(null)
const loading = ref(true)
const submitting = ref(false)
const openingSourceFile = ref(false)
const comment = ref('')

const validationFields = computed(() => {
  return record.value?.validation_fields || []
})

const ratioClass = computed(() => {
  const ratio = record.value?.match_ratio
  if (ratio === null || ratio === undefined) return ''
  if (ratio >= 80) return 'ratio-good'
  if (ratio >= 60) return 'ratio-ok'
  return 'ratio-bad'
})

const statusTagType = computed(() => {
  const s = record.value?.review_status
  if (s === 'pending') return 'danger'
  if (s === 'confirmed') return 'success'
  if (s === 'flagged') return 'warning'
  return 'default'
})

const statusText = computed(() => {
  const s = record.value?.review_status
  if (s === 'pending') return '待审核'
  if (s === 'confirmed') return '已认可'
  if (s === 'flagged') return '已标记异常'
  return '无需审核'
})

onMounted(async () => {
  const id = route.params.id
  try {
    const res = await reviewApi.detail(id)
    record.value = res.record || res
  } catch (e) {
    showToast('加载失败')
  } finally {
    loading.value = false
  }
})

function formatRatio(val) {
  if (val === null || val === undefined) return '-'
  return Math.round(val) + '%'
}

function openSourceFile() {
  if (openingSourceFile.value) return
  const url = record.value?.source_file_url
  if (!url) {
    showToast('无附件地址')
    return
  }
  openingSourceFile.value = true
  const opened = window.open(url, '_blank', 'noopener,noreferrer')
  if (!opened) {
    showToast('浏览器阻止打开，请允许弹窗后重试')
  }
  window.setTimeout(() => {
    openingSourceFile.value = false
  }, 800)
}

async function handleConfirm() {
  showConfirmDialog({
    title: '确认认可',
    message: '认可后将标记为"已认可"，数据库字段保持不变',
  }).then(async () => {
    submitting.value = true
    try {
      await reviewApi.confirm(route.params.id, comment.value)
      showToast('已认可')
      record.value.review_status = 'confirmed'
    } catch (e) {
      showToast('操作失败: ' + e.message)
    } finally {
      submitting.value = false
    }
  }).catch(() => {})
}

async function handleFlag() {
  showConfirmDialog({
    title: '标记异常',
    message: '标记为异常后将进入异常记录列表',
  }).then(async () => {
    submitting.value = true
    try {
      await reviewApi.flag(route.params.id, comment.value)
      showToast('已标记')
      record.value.review_status = 'flagged'
    } catch (e) {
      showToast('操作失败: ' + e.message)
    } finally {
      submitting.value = false
    }
  }).catch(() => {})
}
</script>

<style scoped>
.detail-page { padding-bottom: 32px; }
.page-loading { display: flex; justify-content: center; padding: 60px; }
.detail-header {
  background: #fff;
  padding: 20px 16px;
  margin-bottom: 12px;
}
.company-name { font-size: 18px; font-weight: 600; margin: 0 0 8px; }
.ratio-bar { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
.ratio-label { font-size: 13px; color: #969799; }
.ratio-value { font-size: 22px; font-weight: 700; }
.ratio-good { color: #07c160; }
.ratio-ok { color: #ff976a; }
.ratio-bad { color: #ee0a24; }
.comment { margin-top: 8px; font-size: 13px; color: #ee0a24; background: #fff2f0; padding: 6px 10px; border-radius: 4px; }
.section-title {
  font-size: 14px; font-weight: 600; color: #323233;
  padding: 16px 16px 8px;
}
.field-list { margin: 0 16px; background: #fff; border-radius: 8px; overflow: hidden; }
.field-item {
  padding: 12px 16px;
  border-bottom: 1px solid #f5f6f8;
}
.field-name { font-size: 13px; font-weight: 600; color: #646566; margin-bottom: 6px; }
.value-row { display: flex; align-items: center; gap: 6px; margin: 3px 0; font-size: 13px; }
.value-label { font-size: 11px; color: #969799; width: 40px; flex-shrink: 0; }
.value-text { flex: 1; color: #323233; }
.value-text.mismatch { color: #ee0a24; text-decoration: line-through; }
.file-section { margin: 0 16px; background: #fff; border-radius: 8px; padding: 16px; }
.no-file { color: #969799; font-size: 13px; }
.action-section { margin: 0 16px; }
.action-buttons { display: flex; flex-direction: column; gap: 10px; margin-top: 12px; }
.already-reviewed {
  background: #f5f6f8; border-radius: 8px; padding: 16px; text-align: center; color: #969799; font-size: 14px;
}
</style>
