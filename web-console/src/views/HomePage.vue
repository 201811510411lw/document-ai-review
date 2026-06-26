<template>
  <div class="home-page">
    <!-- 顶部标题 -->
    <div class="home-header">
      <van-icon name="certificate" size="32" color="#1989fa" />
      <h1>合同及证照智能审核系统</h1>
      <p class="subtitle">企业微信工作台应用</p>
    </div>

    <!-- 场景入口卡片 -->
    <div class="scene-list">
      <!-- 场景一：证照审核 -->
      <div class="scene-card" @click="router.push('/scene1')">
        <div class="scene-icon" style="background: linear-gradient(135deg, #667eea, #764ba2);">
          <van-icon name="records" size="28" color="#fff" />
        </div>
        <div class="scene-info">
          <h3>证照审核</h3>
          <p class="scene-desc">QC 证照及批次报告审核</p>
          <div class="scene-stats">
            <span class="stat-tag primary">待审核 {{ scene1Stats.pending || 0 }}</span>
            <span class="stat-tag success">有效 {{ scene1Stats.valid || 0 }}</span>
            <span class="stat-tag danger">过期 {{ scene1Stats.expired || 0 }}</span>
          </div>
        </div>
        <van-icon name="arrow" color="#dcdee0" />
      </div>

      <!-- 场景二：烟草证比对 -->
      <div class="scene-card" @click="router.push('/tobacco/reports')">
        <div class="scene-icon" style="background: linear-gradient(135deg, #f093fb, #f5576c);">
          <van-icon name="balance-list" size="28" color="#fff" />
        </div>
        <div class="scene-info">
          <h3>烟草证比对</h3>
          <p class="scene-desc">营业执照↔烟草证一致性校验</p>
          <div class="scene-stats">
            <span v-if="tobaccoStats.pending > 0" class="stat-tag warning">待处理 {{ tobaccoStats.pending }}</span>
            <span class="stat-tag success">通过 {{ tobaccoStats.passed || 0 }}</span>
            <span class="stat-tag danger">不通过 {{ tobaccoStats.failed || 0 }}</span>
          </div>
        </div>
        <van-icon name="arrow" color="#dcdee0" />
      </div>

      <!-- 场景三：合同审核 -->
      <div class="scene-card" @click="router.push('/contract/reports')">
        <div class="scene-icon" style="background: linear-gradient(135deg, #4facfe, #00f2fe);">
          <van-icon name="description" size="28" color="#fff" />
        </div>
        <div class="scene-info">
          <h3>合同审核</h3>
          <p class="scene-desc">法务合同内容审查</p>
          <div class="scene-stats">
            <span v-if="contractStats['高'] > 0" class="stat-tag danger">高风险 {{ contractStats['高'] }}</span>
            <span v-if="contractStats['中'] > 0" class="stat-tag warning">中风险 {{ contractStats['中'] }}</span>
            <span class="stat-tag success">低风险 {{ contractStats['低'] || 0 }}</span>
          </div>
        </div>
        <van-icon name="arrow" color="#dcdee0" />
      </div>
    </div>

    <!-- 底部提示 -->
    <div class="home-footer">
      <p>数据由后台自动同步更新</p>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { dashboardApi, tobaccoApi, contractApi } from '@/api'
import { showToast } from 'vant'

const router = useRouter()
const scene1Stats = ref({})
const tobaccoStats = ref({})
const contractStats = ref({})

onMounted(async () => {
  // 并行加载三个场景的统计数据
  try {
    const [statsRes, reviewRes] = await Promise.all([
      dashboardApi.stats(),
      import('@/api').then(m => m.reviewApi.list({ review_status: 'pending', limit: 1 })),
    ])
    scene1Stats.value = statsRes.data || statsRes
    scene1Stats.value.pending = reviewRes.stats?.pending || 0
  } catch {
    // 静默
  }

  try {
    const res = await tobaccoApi.list({ limit: 1 })
    tobaccoStats.value = res.stats || {}
  } catch {
    // 静默
  }

  try {
    const res = await contractApi.list({ limit: 1 })
    contractStats.value = res.stats || {}
  } catch {
    // 静默
  }
})
</script>

<style scoped>
.home-page {
  padding-bottom: 16px;
}
.home-header {
  text-align: center;
  padding: 32px 16px 24px;
  background: #fff;
}
.home-header h1 {
  font-size: 20px;
  margin: 12px 0 4px;
  color: #323233;
}
.subtitle {
  font-size: 13px;
  color: #969799;
  margin: 0;
}
.scene-list {
  padding: 12px 16px;
}
.scene-card {
  display: flex;
  align-items: center;
  gap: 14px;
  background: #fff;
  border-radius: 12px;
  padding: 16px;
  margin-bottom: 12px;
  box-shadow: 0 1px 4px rgba(0,0,0,0.06);
  cursor: pointer;
}
.scene-card:active {
  transform: scale(0.98);
  opacity: 0.9;
}
.scene-icon {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.scene-info {
  flex: 1;
  min-width: 0;
}
.scene-info h3 {
  font-size: 16px;
  font-weight: 600;
  margin: 0 0 2px;
  color: #323233;
}
.scene-desc {
  font-size: 12px;
  color: #969799;
  margin: 0 0 6px;
}
.scene-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.stat-tag {
  font-size: 11px;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f5f6f8;
  color: #969799;
}
.stat-tag.primary { color: #667eea; background: #f0f0ff; }
.stat-tag.success { color: #07c160; background: #e8fae8; }
.stat-tag.danger { color: #ee0a24; background: #ffeeed; }
.stat-tag.warning { color: #ff976a; background: #fff7e6; }
.home-footer {
  text-align: center;
  padding: 24px;
}
.home-footer p {
  font-size: 12px;
  color: #dcdee0;
}
</style>
