<template>
  <div class="admin-page">
    <van-nav-bar title="系统管理" left-arrow @click-left="router.push('/scene1')" />

    <!-- 日报推送管理 -->
    <van-cell-group title="日报推送管理">
      <van-cell title="当前接收人" is-link @click="showUserManager = true">
        <template #value>
          <span v-if="notifyUsers.length">{{ notifyUsers.length }} 人</span>
          <span v-else class="danger-text">未配置</span>
        </template>
      </van-cell>
      <van-cell title="推送时间" value="09:00" />
      <van-cell title="临期预警天数" value="30 天" />
    </van-cell-group>

    <!-- 证照管理 -->
    <van-cell-group title="证照管理">
      <van-cell title="批量导入证照" icon="records" is-link to="/admin/import" />
      <van-cell title="全部证照记录" icon="records" is-link @click="showRecords = true" />
      <van-cell title="证照类型管理" icon="label-o" is-link @click="showToast('功能开发中')" />
    </van-cell-group>

    <!-- 数据维护 -->
    <van-cell-group title="数据维护">
      <van-cell title="手动触发效期检查" icon="refresh" is-link @click="handleManualCheck" />
      <van-cell title="导出全部数据" icon="down" is-link @click="handleExportAll" />
      <van-cell title="数据统计" icon="chart-trending-o" is-link>
        <template #value>
          <span class="stat-link">{{ stats.total || '-' }} 条记录</span>
        </template>
      </van-cell>
    </van-cell-group>

    <!-- 日报接收人管理弹窗 -->
    <van-dialog
      v-model:show="showUserManager"
      title="管理日报接收人"
      show-cancel-button
      confirm-button-text="保存"
      @confirm="handleSaveUsers"
    >
      <div class="user-list-editor">
        <van-field
          v-model="newUserId"
          placeholder="输入 UserID，回车添加"
          @keypress.enter="addUser"
        >
          <template #button>
            <van-button size="small" type="primary" @click="addUser">添加</van-button>
          </template>
        </van-field>
        <div v-for="(uid, idx) in notifyUsers" :key="idx" class="user-tag">
          <span>{{ uid }}</span>
          <van-icon name="cross" @click="notifyUsers.splice(idx, 1)" />
        </div>
      </div>
    </van-dialog>

    <!-- 记录列表弹窗 -->
    <van-action-sheet v-model:show="showRecords" title="证照记录" close-on-popup-action>
      <div class="records-sheet">
        <van-search v-model="recordKeyword" placeholder="搜索公司名" @search="loadRecords" />
        <van-list v-model:loading="recordsLoading" :finished="recordsFinished" finished-text="暂无更多">
          <div v-for="r in records" :key="r.id" class="record-item">
            <div class="record-info">
              <div class="record-name">{{ r.company_name }}</div>
              <div class="record-meta">{{ r.license_type }} · {{ r.expire_date }}</div>
            </div>
            <van-icon name="delete" color="#ee0a24" @click="handleDeleteRecord(r.id)" />
          </div>
        </van-list>
      </div>
    </van-action-sheet>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { adminApi, dashboardApi } from '@/api'
import { downloadBlob } from '@/utils'
import { showToast, showLoadingToast, closeToast, showConfirmDialog } from 'vant'

const notifyUsers = ref([])
const newUserId = ref('')
const showUserManager = ref(false)
const showRecords = ref(false)
const recordKeyword = ref('')
const records = ref([])
const recordsLoading = ref(false)
const recordsFinished = ref(false)
const stats = ref({})

onMounted(async () => {
  loadUsers()
  try {
    const res = await dashboardApi.stats()
    stats.value = res.data || res
  } catch (_) {}
})

async function loadUsers() {
  try {
    const res = await adminApi.getNotifyUsers()
    notifyUsers.value = res.users || []
  } catch (_) {
    notifyUsers.value = ['ZhangSan', 'LiSi']
  }
}

function addUser() {
  const uid = newUserId.value.trim()
  if (!uid) return
  if (notifyUsers.value.includes(uid)) {
    showToast('已存在')
    return
  }
  notifyUsers.value.push(uid)
  newUserId.value = ''
}

async function handleSaveUsers() {
  try {
    await adminApi.setNotifyUsers(notifyUsers.value)
    showToast('保存成功')
  } catch (e) {
    showToast('保存失败: ' + e.message)
  }
}

async function handleManualCheck() {
  showLoadingToast({ message: '效期检查中...', forbidClick: true })
  try {
    await adminApi.checkExpiry()
    closeToast()
    showToast('效期检查完成')
  } catch (e) {
    closeToast()
    showToast('检查失败: ' + e.message)
  }
}

function handleExportAll() {
  showToast('导出功能开发中')
}

async function loadRecords() {
  recordsLoading.value = true
  try {
    const res = await adminApi.getRecords({ keyword: recordKeyword.value, limit: 100 })
    records.value = res.records || []
    recordsFinished.value = true
  } catch (e) {
    showToast('加载失败')
  } finally {
    recordsLoading.value = false
  }
}

async function handleDeleteRecord(id) {
  showConfirmDialog({
    title: '确认删除',
    message: '确定删除该证照记录吗？',
  }).then(async () => {
    try {
      await adminApi.deleteRecord(id)
      records.value = records.value.filter(r => r.id !== id)
      showToast('已删除')
    } catch (e) {
      showToast('删除失败')
    }
  }).catch(() => {})
}
</script>

<style scoped>
.admin-page {
  padding-bottom: 16px;
}
.danger-text { color: #ee0a24; }
.user-list-editor {
  padding: 16px;
  max-height: 300px;
  overflow-y: auto;
}
.user-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  background: #ecf5ff;
  color: #1989fa;
  padding: 4px 10px;
  border-radius: 12px;
  font-size: 13px;
  margin: 4px;
}
.stat-link { color: #1989fa; }
.records-sheet {
  padding: 0 16px 24px;
  max-height: 60vh;
  overflow-y: auto;
}
.record-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid #f5f6f8;
}
.record-name { font-size: 14px; font-weight: 500; }
.record-meta { font-size: 12px; color: #969799; }
</style>
