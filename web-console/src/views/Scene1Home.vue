<template>
  <div class="scene1-page">
    <van-nav-bar title="证照审核" left-arrow @click-left="router.push('/home')" />

    <main class="scene-content">
      <header class="scene-intro">
        <p>QC 证照及批次报告审核</p>
      </header>

      <section
        v-for="section in visibleSections"
        :key="section.id"
        class="entry-section"
        :aria-labelledby="`${section.id}-section-title`"
      >
        <h2 :id="`${section.id}-section-title`">{{ section.title }}</h2>
        <div class="entry-list">
          <button
            v-for="entry in section.entries"
            :key="entry.path"
            type="button"
            class="entry-row"
            @click="router.push(entry.path)"
          >
            <strong>{{ entry.title }}</strong>
            <span>{{ entry.description }}</span>
          </button>
        </div>
      </section>
    </main>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'

const router = useRouter()
const userStore = useUserStore()
const isAdmin = computed(() => userStore.isAdmin)

const businessEntries = [
  {
    title: '证照查询',
    description: '按供应商编码或公司名称查询证照信息',
    path: '/query',
  },
  {
    title: '效期看板',
    description: '查看证照效期统计和每日日报',
    path: '/dashboard',
  },
  {
    title: '供应商及商品证照',
    description: '营业执照、食品经营许可证、食品生产许可证、商品报告的统一校验审核',
    path: '/review',
    adminOnly: true,
  },
]

const adminEntries = [
  {
    title: '系统管理',
    description: '日报推送管理、证照管理、数据维护',
    path: '/admin',
  },
]

const visibleSections = computed(() => {
  const sections = [
    {
      id: 'business',
      title: '业务审核',
      entries: businessEntries.filter((entry) => !entry.adminOnly || isAdmin.value),
    },
  ]

  if (isAdmin.value) {
    sections.push({ id: 'admin', title: '系统管理', entries: adminEntries })
  }

  return sections
})
</script>

<style scoped>
.scene1-page {
  min-height: calc(100dvh - 50px);
  padding-bottom: 48px;
  background: #f6f7f9;
  color: #20242b;
}

.scene-content {
  width: min(100% - 40px, 920px);
  margin: 0 auto;
}

.scene-intro {
  padding: 24px 0 20px;
  border-bottom: 1px solid #cfd5dd;
}

.scene-intro p {
  margin: 0;
  color: #586170;
  font-size: 14px;
  line-height: 1.5;
}

.entry-section {
  padding-top: 28px;
}

.entry-section h2 {
  margin: 0 0 10px;
  color: #687180;
  font-size: 13px;
  font-weight: 600;
  line-height: 1.5;
  letter-spacing: 0;
}

.entry-list {
  border-top: 1px solid #aeb6c2;
}

.entry-row {
  display: grid;
  width: 100%;
  gap: 5px;
  min-height: 72px;
  padding: 15px 4px;
  border: 0;
  border-bottom: 1px solid #d9dee5;
  background: transparent;
  color: inherit;
  font: inherit;
  text-align: left;
  cursor: pointer;
  transition: background-color 140ms ease;
}

.entry-row:hover {
  background: #eef1f4;
}

.entry-row:active {
  background: #e5e9ee;
}

.entry-row:focus-visible {
  outline: 2px solid #245a9a;
  outline-offset: 2px;
}

.entry-row strong {
  font-size: 15px;
  font-weight: 600;
  line-height: 1.45;
}

.entry-row span {
  color: #687180;
  font-size: 13px;
  line-height: 1.55;
  overflow-wrap: anywhere;
}

@media (max-width: 600px) {
  .scene-content {
    width: calc(100% - 32px);
  }

  .scene-intro {
    padding: 18px 0 16px;
  }

  .entry-section {
    padding-top: 22px;
  }

  .entry-row {
    min-height: 68px;
    padding: 14px 2px;
  }
}
</style>
