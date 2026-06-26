<template>
  <div class="detail-page">
    <van-nav-bar title="比对详情" left-arrow @click-left="router.back()" />

    <div v-if="loading" class="page-loading">
      <van-loading size="24">加载中...</van-loading>
    </div>

    <template v-if="report">
      <!-- 头部 -->
      <div class="detail-header">
        <h2 class="company-name">{{ report.company_name }}</h2>
        <div class="overall-result" :class="report.overall_result === '通过' ? 'pass' : 'fail'">
          <van-icon :name="report.overall_result === '通过' ? 'success' : 'cross'" size="20" />
          <span>{{ report.overall_result === '通过' ? '核验通过' : '核验未通过' }}</span>
        </div>
        <div class="compare-time">比对时间: {{ report.compare_time || report.created_at?.slice(0, 10) || '-' }}</div>
      </div>

      <!-- 比对结果表格 -->
      <div class="section-title">字段比对</div>
      <div class="compare-grid">
        <!-- 证照类型 -->
        <div class="compare-item" :class="report.type_match === '正确' ? 'match' : 'mismatch'">
          <div class="field-header">
            <van-icon :name="report.type_match === '正确' ? 'success' : 'cross'"
              :color="report.type_match === '正确' ? '#07c160' : '#ee0a24'" />
            <span>证照类型</span>
          </div>
          <div class="field-values">
            <div class="value-row"><span class="label">营业执照</span><span class="val">{{ report.business_license_name?.slice(0, 6) || '-' }}</span></div>
            <div class="value-row"><span class="label">烟草证</span><span class="val">烟草专卖零售许可证</span></div>
          </div>
          <div class="field-verdict">{{ report.type_match }}</div>
        </div>

        <!-- 企业名称 -->
        <div class="compare-item" :class="report.name_match === '匹配' ? 'match' : 'mismatch'">
          <div class="field-header">
            <van-icon :name="report.name_match === '匹配' ? 'success' : 'cross'"
              :color="report.name_match === '匹配' ? '#07c160' : '#ee0a24'" />
            <span>企业名称</span>
          </div>
          <div class="field-values">
            <div class="value-row"><span class="label">营业执照</span><span class="val">{{ report.business_license_name || '-' }}</span></div>
            <div class="value-row"><span class="label">烟草证</span><span class="val">{{ report.tobacco_license_name || '-' }}</span></div>
          </div>
          <div class="field-verdict">{{ report.name_match }}</div>
        </div>

        <!-- 经营场所 -->
        <div class="compare-item" :class="report.address_match === '匹配' ? 'match' : 'mismatch'">
          <div class="field-header">
            <van-icon :name="report.address_match === '匹配' ? 'success' : 'cross'"
              :color="report.address_match === '匹配' ? '#07c160' : '#ee0a24'" />
            <span>经营场所</span>
          </div>
          <div class="field-values">
            <div class="value-row"><span class="label">营业执照</span><span class="val">{{ report.business_license_address || '-' }}</span></div>
            <div class="value-row"><span class="label">烟草证</span><span class="val">{{ report.tobacco_license_address || '-' }}</span></div>
          </div>
          <div class="field-verdict">{{ report.address_match }}</div>
        </div>

        <!-- 负责人 -->
        <div class="compare-item" :class="report.person_match === '匹配' ? 'match' : 'mismatch'">
          <div class="field-header">
            <van-icon :name="report.person_match === '匹配' ? 'success' : 'cross'"
              :color="report.person_match === '匹配' ? '#07c160' : '#ee0a24'" />
            <span>负责人</span>
          </div>
          <div class="field-values">
            <div class="value-row"><span class="label">营业执照</span><span class="val">{{ report.business_license_person || '-' }}</span></div>
            <div class="value-row"><span class="label">烟草证</span><span class="val">{{ report.tobacco_license_person || '-' }}</span></div>
          </div>
          <div class="field-verdict">{{ report.person_match }}</div>
        </div>

        <!-- 有效期 -->
        <div class="compare-item" :class="report.validity_status === '未过期' ? 'match' : 'mismatch'">
          <div class="field-header">
            <van-icon :name="report.validity_status === '未过期' ? 'success' : 'cross'"
              :color="report.validity_status === '未过期' ? '#07c160' : '#ee0a24'" />
            <span>有效期</span>
          </div>
          <div class="field-values">
            <div class="value-row"><span class="label">烟草证</span><span class="val">{{ report.validity_status }}</span></div>
          </div>
          <div class="field-verdict">{{ report.validity_status }}</div>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import { tobaccoApi } from '@/api'
import { showToast } from 'vant'

const router = useRouter()
const route = useRoute()
const report = ref(null)
const loading = ref(true)

onMounted(async () => {
  try {
    const res = await tobaccoApi.detail(route.params.id)
    report.value = res.report || res
  } catch (e) {
    showToast('加载失败')
  } finally {
    loading.value = false
  }
})
</script>

<style scoped>
.detail-page { padding-bottom: 32px; }
.page-loading { display: flex; justify-content: center; padding: 60px; }
.detail-header {
  background: #fff;
  padding: 20px 16px;
  margin-bottom: 12px;
  text-align: center;
}
.company-name { font-size: 18px; font-weight: 600; margin: 0 0 8px; }
.overall-result {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 6px 16px;
  border-radius: 20px;
  font-size: 15px;
  font-weight: 600;
}
.overall-result.pass { background: #e8fae8; color: #07c160; }
.overall-result.fail { background: #ffeeed; color: #ee0a24; }
.compare-time { font-size: 12px; color: #969799; margin-top: 8px; }
.section-title {
  font-size: 14px; font-weight: 600; color: #323233;
  padding: 16px 16px 8px;
}
.compare-grid { margin: 0 16px; display: flex; flex-direction: column; gap: 10px; }
.compare-item {
  background: #fff;
  border-radius: 8px;
  padding: 12px 14px;
  border-left: 3px solid #dcdee0;
}
.compare-item.match { border-left-color: #07c160; }
.compare-item.mismatch { border-left-color: #ee0a24; }
.field-header {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 14px;
  font-weight: 600;
  color: #323233;
  margin-bottom: 8px;
}
.field-values {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.value-row {
  display: flex;
  gap: 8px;
  font-size: 13px;
}
.label {
  color: #969799;
  width: 60px;
  flex-shrink: 0;
}
.val { color: #323233; }
.field-verdict {
  margin-top: 6px;
  font-size: 12px;
  font-weight: 500;
  padding: 2px 8px;
  border-radius: 4px;
  display: inline-block;
}
.match .field-verdict { background: #e8fae8; color: #07c160; }
.mismatch .field-verdict { background: #ffeeed; color: #ee0a24; }
</style>
