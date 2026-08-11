<template>
  <div class="workspace-shell">
    <aside class="workspace-sidebar">
      <button class="workspace-brand" type="button" @click="router.push('/home')">
        <span class="brand-mark"><van-icon name="description" /></span>
        <span class="brand-copy"><strong>证照智审</strong><small>DOCUMENT AI REVIEW</small></span>
      </button>

      <nav class="desktop-navigation" aria-label="工作台导航">
        <section v-for="group in desktopNavigation" :key="group.label">
          <p>{{ group.label }}</p>
          <button
            v-for="item in group.items"
            :key="item.to"
            type="button"
            :class="{ active: item.active }"
            :title="item.label"
            @click="router.push(item.to)"
          >
            <van-icon :name="item.icon" />
            <span>{{ item.label }}</span>
          </button>
        </section>
      </nav>

      <button class="sidebar-user" type="button" @click="router.push('/profile')">
        <span class="user-avatar">{{ userInitials }}</span>
        <span><strong>{{ userName || '用户' }}</strong><small>{{ isAdmin ? '系统管理员' : '业务用户' }}</small></span>
      </button>
    </aside>

    <div class="workspace-main">
      <header class="desktop-topbar">
        <div class="route-heading">
          <small>首页 / {{ pageTitle }}</small>
          <strong>{{ pageTitle }}</strong>
        </div>
        <div class="topbar-actions">
          <form class="global-search" role="search" @submit.prevent="submitSearch">
            <van-icon name="search" />
            <input v-model="searchKeyword" type="search" placeholder="搜索企业名称、证照编号" />
          </form>
          <button type="button" title="个人中心" @click="router.push('/profile')"><van-icon name="contact-o" /></button>
        </div>
      </header>

      <header class="mobile-topbar">
        <button class="mobile-brand" type="button" @click="router.push('/home')">
          <span class="brand-mark">证</span>
          <span><strong>证照智审</strong><small>AI DOCUMENT REVIEW</small></span>
        </button>
        <button class="mobile-avatar" type="button" @click="router.push('/profile')">{{ userInitials }}</button>
      </header>

      <div class="workspace-content" :class="{ 'top-level-route': route.meta.topLevel }">
        <slot />
      </div>

      <nav
        class="mobile-navigation"
        :class="{ 'has-five-items': mobileNavigation.length === 5 }"
        aria-label="移动端导航"
      >
        <button
          v-for="item in mobileNavigation"
          :key="item.to"
          type="button"
          :class="{ active: item.active }"
          @click="router.push(item.to)"
        >
          <van-icon :name="item.icon" />
          <span>{{ item.label }}</span>
        </button>
      </nav>
    </div>
  </div>
</template>

<script setup>
import { computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useUserStore } from '@/store/user'
import { buildDesktopNavigation, buildMobileNavigation } from '@/features/workbench/navigation'

const route = useRoute()
const router = useRouter()
const userStore = useUserStore()
const searchKeyword = ref('')

const isAdmin = computed(() => userStore.isAdmin)
const userName = computed(() => userStore.userName)
const userInitials = computed(() => {
  const value = userName.value || userStore.userId || '用户'
  return String(value).slice(0, 2).toUpperCase()
})
const pageTitle = computed(() => String(route.meta.title || '智能审核工作台'))
const desktopNavigation = computed(() => buildDesktopNavigation({
  isAdmin: isAdmin.value,
  currentPath: route.path,
}))
const mobileNavigation = computed(() => buildMobileNavigation({
  isAdmin: isAdmin.value,
  currentPath: route.path,
}))

function submitSearch() {
  const keyword = searchKeyword.value.trim()
  router.push({ path: '/query', query: keyword ? { keyword } : {} })
}
</script>

<style scoped>
.workspace-shell {
  display: grid;
  grid-template-columns: 238px minmax(0, 1fr);
  min-height: 100dvh;
  color: #182238;
  background: #f3f6fb;
}
.workspace-sidebar { position: sticky; top: 0; display: flex; flex-direction: column; height: 100dvh; padding: 24px 16px 18px; color: #cbd4e6; background: #101d36; }
.workspace-brand, .mobile-brand, .sidebar-user, .desktop-navigation button, .topbar-actions > button, .mobile-avatar, .mobile-navigation button { border: 0; font: inherit; cursor: pointer; }
.workspace-brand { display: flex; align-items: center; gap: 11px; padding: 0 10px 26px; color: #fff; background: transparent; text-align: left; }
.brand-mark { display: grid; flex: none; width: 38px; height: 38px; place-items: center; border-radius: 11px; color: #fff; background: #4d6ff0; box-shadow: 0 8px 18px rgba(48, 83, 207, 0.25); }
.brand-mark :deep(.van-icon) { font-size: 20px; }
.brand-copy { min-width: 0; }.brand-copy strong { display: block; font-size: 17px; }.brand-copy small { display: block; margin-top: 3px; color: #8491a7; font-size: 9px; }
.desktop-navigation { display: grid; gap: 20px; }.desktop-navigation section { display: grid; gap: 5px; }.desktop-navigation p { margin: 0 12px 4px; color: #66758f; font-size: 10px; }
.desktop-navigation button { position: relative; display: grid; grid-template-columns: 22px 1fr; gap: 10px; align-items: center; min-height: 44px; padding: 0 12px; border-radius: 10px; color: #aeb9cc; background: transparent; text-align: left; transition: color 150ms ease, background 150ms ease; }
.desktop-navigation button:hover { color: #fff; background: rgba(255,255,255,0.05); }.desktop-navigation button.active { color: #fff; background: #1c3162; box-shadow: inset 3px 0 #6f8cff; }.desktop-navigation button :deep(.van-icon) { font-size: 18px; }.desktop-navigation button span { font-size: 13px; }
.sidebar-user { display: flex; align-items: center; gap: 10px; margin-top: auto; padding: 14px 10px 0; border-top: 1px solid rgba(255,255,255,0.08); color: inherit; background: transparent; text-align: left; }.user-avatar, .mobile-avatar { display: grid; place-items: center; border-radius: 50%; color: #fff; background: #efa955; font-size: 11px; font-weight: 700; }.user-avatar { width: 34px; height: 34px; }.sidebar-user strong, .sidebar-user small { display: block; }.sidebar-user strong { color: #f5f7fb; font-size: 12px; }.sidebar-user small { margin-top: 3px; color: #77859f; font-size: 10px; }
.workspace-main { min-width: 0; min-height: 100dvh; }.desktop-topbar { display: flex; align-items: center; justify-content: space-between; height: 72px; padding: 0 28px; border-bottom: 1px solid #e3e8f0; background: rgba(255,255,255,0.96); }.route-heading small, .route-heading strong { display: block; }.route-heading small { margin-bottom: 5px; color: #8d97a8; font-size: 11px; }.route-heading strong { font-size: 19px; }
.topbar-actions { display: flex; align-items: center; gap: 12px; }.global-search { display: flex; align-items: center; width: 260px; height: 38px; padding: 0 13px; border: 1px solid #e3e8f0; border-radius: 10px; color: #8d97a8; background: #f6f8fb; }.global-search input { min-width: 0; flex: 1; margin-left: 9px; border: 0; outline: 0; color: #38445a; background: transparent; font: inherit; font-size: 12px; }.topbar-actions > button { display: grid; width: 38px; height: 38px; place-items: center; border: 1px solid #e3e8f0; border-radius: 10px; color: #59657a; background: #fff; }.topbar-actions > button :deep(.van-icon) { font-size: 18px; }
.workspace-content { min-height: calc(100dvh - 72px); }.mobile-topbar, .mobile-navigation { display: none; }
button:focus-visible, input:focus-visible { outline: 2px solid #5272eb; outline-offset: 2px; }
@media (max-width: 1050px) and (min-width: 641px) {
  .workspace-shell { grid-template-columns: 76px minmax(0, 1fr); }.workspace-sidebar { padding-right: 10px; padding-left: 10px; }.workspace-brand { justify-content: center; padding-right: 0; padding-left: 0; }.brand-copy, .desktop-navigation p, .desktop-navigation button span, .sidebar-user > span:last-child { display: none; }.desktop-navigation button { display: grid; grid-template-columns: 1fr; justify-items: center; padding: 0; }.sidebar-user { justify-content: center; padding-right: 0; padding-left: 0; }
}
@media (max-width: 640px) {
  .workspace-shell { display: block; }.workspace-sidebar, .desktop-topbar { display: none; }.mobile-topbar { position: sticky; z-index: 20; top: 0; display: flex; align-items: center; justify-content: space-between; height: 66px; padding: 0 18px; border-bottom: 1px solid #e4e9f1; background: rgba(255,255,255,0.98); }.mobile-brand { display: flex; align-items: center; gap: 10px; padding: 0; color: #182238; background: transparent; text-align: left; }.mobile-brand .brand-mark { width: 34px; height: 34px; font-size: 16px; }.mobile-brand strong, .mobile-brand small { display: block; }.mobile-brand strong { font-size: 15px; }.mobile-brand small { margin-top: 2px; color: #8a95a7; font-size: 8px; }.mobile-avatar { width: 34px; height: 34px; }.workspace-content { min-height: calc(100dvh - 132px); padding-bottom: 66px; }.mobile-navigation { position: fixed; z-index: 30; right: 0; bottom: 0; left: 0; display: grid; grid-template-columns: repeat(4, 1fr); height: 66px; border-top: 1px solid #e4e9f1; background: rgba(255,255,255,0.98); }.mobile-navigation.has-five-items { grid-template-columns: repeat(5, 1fr); }.mobile-navigation button { display: grid; align-content: center; justify-items: center; gap: 4px; padding: 0; color: #8d97a8; background: transparent; font-size: 9px; }.mobile-navigation button :deep(.van-icon) { font-size: 20px; }.mobile-navigation button.active { color: #3159e7; }.mobile-navigation button.active :deep(.van-icon) { display: grid; width: 26px; height: 25px; place-items: center; border-radius: 8px; background: #eef2ff; }
}
</style>
