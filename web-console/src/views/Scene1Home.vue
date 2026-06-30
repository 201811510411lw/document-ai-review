<template>
  <div class="scene1-page">
    <van-nav-bar title="证照审核" left-arrow @click-left="router.push('/home')" />

    <!-- 场景描述 -->
    <div class="scene-desc-bar">
      <van-icon name="info-o" color="#1989fa" />
      <span>QC 证照及批次报告审核</span>
    </div>

    <!-- 功能入口 -->
    <van-cell-group>
      <van-cell
        title="🔍 证照查询"
        label="按供应商编码或公司名称查询证照信息"
        is-link
        @click="router.push('/query')"
      >
        <template #icon>
          <van-icon name="search" class="cell-icon" />
        </template>
      </van-cell>
      <van-cell
        title="📊 效期看板"
        label="查看证照效期统计和每日日报"
        is-link
        @click="router.push('/dashboard')"
      >
        <template #icon>
          <van-icon name="chart-trending-o" class="cell-icon" />
        </template>
      </van-cell>
      <van-cell
        v-if="isAdmin"
        title="📋 营业执照审核"
        label="营业执照识别结果与供应商主数据比对"
        is-link
        @click="router.push('/review?document_type=business_license')"
      >
        <template #icon>
          <van-icon name="records" class="cell-icon" />
        </template>
      </van-cell>
      <van-cell
        v-if="isAdmin"
        title="🍽 食品经营许可证审核"
        label="经营者名称、信用代码、经营项目、有效期校验"
        is-link
        @click="router.push('/review?document_type=food_license')"
      >
        <template #icon>
          <van-icon name="records" class="cell-icon" />
        </template>
      </van-cell>
      <van-cell
        v-if="isAdmin"
        title="🏭 食品生产许可证审核"
        label="生产者名称、信用代码、食品类别、有效期校验"
        is-link
        @click="router.push('/review?document_type=food_production_license')"
      >
        <template #icon>
          <van-icon name="records" class="cell-icon" />
        </template>
      </van-cell>
      <van-cell
        v-if="isAdmin"
        title="🧾 商品报告审核"
        label="样品名称、委托单位、签发日期、检验结论校验"
        is-link
        @click="router.push('/review?document_type=product_report')"
      >
        <template #icon>
          <van-icon name="description" class="cell-icon" />
        </template>
      </van-cell>
      <van-cell
        v-if="isAdmin"
        title="📄 审核记录"
        label="查看已完成审核的记录和报告"
        is-link
        @click="router.push('/review')"
      >
        <template #icon>
          <van-icon name="description" class="cell-icon" />
        </template>
      </van-cell>
      <van-cell
        v-if="isAdmin"
        title="⚙️ 系统管理"
        label="日报推送管理、证照管理、数据维护"
        is-link
        @click="router.push('/admin')"
      >
        <template #icon>
          <van-icon name="setting-o" class="cell-icon" />
        </template>
      </van-cell>
    </van-cell-group>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)
</script>

<style scoped>
.scene1-page {
  padding-bottom: 16px;
}
.scene-desc-bar {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 16px;
  font-size: 13px;
  color: #1989fa;
  background: #ecf5ff;
}
.cell-icon {
  font-size: 20px;
  margin-right: 8px;
  color: #1989fa;
}
</style>
