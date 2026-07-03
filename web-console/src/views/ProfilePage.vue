<template>
  <div class="profile-page">
    <!-- 用户信息头部 -->
    <div class="profile-header">
      <van-image
        round
        width="64"
        height="64"
        :src="avatarUrl"
      />
      <div class="profile-info">
        <div class="profile-name">{{ userName || '用户' }}</div>
        <div class="profile-id">{{ userId || '-' }}</div>
        <van-tag :type="isAdmin ? 'primary' : 'default'" size="small">
          {{ isAdmin ? '管理员' : '普通用户' }}
        </van-tag>
      </div>
    </div>

    <!-- 功能菜单 -->
    <van-cell-group>
      <van-cell title="我的查询历史" icon="search" is-link @click="openHistory" />
      <van-cell title="我的下载记录" icon="down" is-link @click="showDownloads = true" />
      <van-cell title="常用证照收藏" icon="star-o" is-link @click="showFavorites = true" />
    </van-cell-group>

    <van-cell-group style="margin-top: 12px;">
      <van-cell title="使用帮助" icon="info-o" is-link @click="showHelp = true" />
      <van-cell title="意见反馈" icon="chat-o" is-link @click="showFeedback = true" />
      <van-cell title="关于" icon="info-o" is-link @click="showAbout = true" />
    </van-cell-group>

    <van-cell-group style="margin-top: 12px;">
      <van-cell title="退出登录" icon="logout" @click="handleLogout" class="logout-cell" />
    </van-cell-group>

    <!-- 管理员入口（仅 A 可见） -->
    <div v-if="isAdmin" class="admin-entrance" @click="router.push('/admin')">
      <van-icon name="setting-o" size="20" color="#1989fa" />
      <span>进入系统管理</span>
      <van-icon name="arrow" color="#969799" />
    </div>

    <!-- 反馈弹窗 -->
    <van-dialog v-model:show="showFeedback" title="意见反馈" show-cancel-button confirm-button-text="提交" @confirm="submitFeedback">
      <van-field
        v-model="feedbackText"
        type="textarea"
        rows="4"
        placeholder="请描述您的建议或问题..."
        :rules="[{ required: true, message: '请输入反馈内容' }]"
      />
    </van-dialog>

    <!-- 关于弹窗 -->
    <van-dialog v-model:show="showAbout" title="关于" :confirm-button-text="'关闭'">
      <div class="about-content">
        <van-icon name="certificate" size="48" color="#1989fa" />
        <h3>证照管理系统</h3>
        <p>版本：v2.0.0</p>
        <p>基于企业微信工作台</p>
      </div>
    </van-dialog>

    <van-action-sheet v-model:show="showHistory" title="我的查询历史" close-on-popup-action>
      <van-cell
        v-for="item in searchHistory"
        :key="item"
        :title="item"
        is-link
        @click="goQuery(item)"
      />
      <van-empty v-if="!searchHistory.length" description="暂无查询历史" />
    </van-action-sheet>

    <van-dialog v-model:show="showDownloads" title="我的下载记录" :confirm-button-text="'关闭'">
      <van-empty description="下载记录暂未接入后端持久化" />
    </van-dialog>

    <van-dialog v-model:show="showFavorites" title="常用证照收藏" :confirm-button-text="'关闭'">
      <van-empty description="收藏功能暂未上线" />
    </van-dialog>

    <van-dialog v-model:show="showHelp" title="使用帮助" :confirm-button-text="'关闭'">
      <div class="help-content">
        <h4>🔍 证照查询</h4>
        <p>支持按公司名称、统一社会信用代码搜索证照。支持单个查询、批量文本查询和上传 Excel 查询。</p>
        <h4>📊 效期看板</h4>
        <p>按证照到期状态分类展示：<span class="hl-green">正常</span>（剩余&gt;30天）、<span class="hl-orange">临期</span>（≤30天）、<span class="hl-red">已过期</span>。点击统计卡片可筛选对应状态。</p>
        <h4>✅ 校验审核（管理员）</h4>
        <p>列表展示各证照的 LLM 识别结果与数据库字段的比对：</p>
        <ul>
          <li><b>匹配率</b>：所有校验字段中，识别值与数据库值一致的比例</li>
          <li><b>字段覆盖率</b>：OCR 成功识别出值的字段占总字段的比例</li>
          <li><b>核验结果</b>：系统自动判断通过/不通过，不通过项默认展开显示</li>
          <li><b>状态说明</b>：待审核 → 已认可（人工确认结果正确）/ 已标记异常（人工标记有误）</li>
        </ul>
        <h4>📋 证照状态说明</h4>
        <ul>
          <li><span class="hl-green">有效</span>：证照在有效期内且剩余天数 &gt; 30</li>
          <li><span class="hl-orange">临期</span>：证照即将到期（剩余 ≤30 天）</li>
          <li><span class="hl-red">已过期</span>：证照已超过有效期</li>
          <li><span class="hl-gray">未识别</span>：未上传证照文件或未识别到有效期</li>
        </ul>
        <h4>⚙️ 系统管理（管理员）</h4>
        <p>日报推送管理、证照类型管理、数据导出。批量导入仅做解析预览，不会自动入库。</p>
      </div>
    </van-dialog>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { getSearchHistory } from '@/utils'
import { showToast } from 'vant'

const router = useRouter()
const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)
const userName = computed(() => userStore.userName)
const userId = computed(() => userStore.userId)
const avatarUrl = ref('')

const showFeedback = ref(false)
const feedbackText = ref('')
const showAbout = ref(false)
const showHistory = ref(false)
const showDownloads = ref(false)
const showFavorites = ref(false)
const showHelp = ref(false)
const searchHistory = ref([])

function openHistory() {
  searchHistory.value = getSearchHistory()
  showHistory.value = true
}

function goQuery(keyword) {
  showHistory.value = false
  router.push({ path: '/query', query: { keyword } })
}

function handleLogout() {
  userStore.logout()
  router.push('/login')
  showToast('已退出')
}

function submitFeedback() {
  if (!feedbackText.value.trim()) {
    showToast('请输入反馈内容')
    return
  }
  showToast('感谢您的反馈！')
  feedbackText.value = ''
}
</script>

<style scoped>
.profile-page {
  padding-bottom: 16px;
}
.profile-header {
  display: flex;
  align-items: center;
  gap: 16px;
  padding: 24px 16px;
  background: #fff;
  margin-bottom: 12px;
}
.profile-info {
  flex: 1;
}
.profile-name {
  font-size: 18px;
  font-weight: 600;
  color: #323233;
}
.profile-id {
  font-size: 12px;
  color: #969799;
  margin: 4px 0;
}
.logout-cell {
  color: #ee0a24;
  --van-cell-text-color: #ee0a24;
}
.admin-entrance {
  display: flex;
  align-items: center;
  gap: 8px;
  justify-content: center;
  padding: 16px;
  margin: 12px 16px;
  background: #ecf5ff;
  border-radius: 8px;
  color: #1989fa;
  font-size: 14px;
  cursor: pointer;
}
.admin-entrance span {
  flex: 1;
  text-align: center;
}
.about-content {
  text-align: center;
  padding: 24px;
}
.about-content h3 {
  margin: 12px 0 4px;
}
.about-content p {
  color: #969799;
  font-size: 13px;
  margin: 2px 0;
}
.help-content {
  padding: 16px 20px;
  text-align: left;
}
.help-content h4 {
  font-size: 14px;
  margin: 12px 0 4px;
  color: #323233;
}
.help-content p {
  margin: 4px 0 8px;
  color: #646566;
  font-size: 13px;
  line-height: 1.6;
}
.help-content ul {
  margin: 4px 0 8px;
  padding-left: 18px;
}
.help-content li {
  font-size: 13px;
  color: #646566;
  line-height: 1.7;
}
.hl-green { color: #07c160; font-weight: 600; }
.hl-orange { color: #ff976a; font-weight: 600; }
.hl-red { color: #ee0a24; font-weight: 600; }
.hl-gray { color: #969799; font-weight: 600; }
</style>
