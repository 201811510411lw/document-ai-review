import { createRouter, createWebHashHistory } from 'vue-router'

import { useUserStore } from '@/store/user'
import QueryPage from '@/views/QueryPage.vue'
import DashboardPage from '@/views/DashboardPage.vue'
import ReviewPage from '@/views/ReviewPage.vue'
import ReviewDetailPage from '@/views/ReviewDetailPage.vue'
import ReviewSourcePreviewPage from '@/views/ReviewSourcePreviewPage.vue'
import AdminPage from '@/views/AdminPage.vue'
import ImportPage from '@/views/ImportPage.vue'
import ProfilePage from '@/views/ProfilePage.vue'
import LoginPage from '@/views/LoginPage.vue'
import HomePage from '@/views/HomePage.vue'
import TobaccoReportList from '@/views/TobaccoReportList.vue'
import TobaccoReportDetail from '@/views/TobaccoReportDetail.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginPage,
    meta: { noAuth: true, noShell: true, title: '登录' },
  },
  {
    path: '/home',
    name: 'Home',
    component: HomePage,
    meta: { title: '智能审核工作台', topLevel: true },
  },
  {
    path: '/scene1',
    name: 'Scene1',
    redirect: '/home',
    meta: { title: '证照审核', topLevel: true },
  },
  {
    path: '/query',
    name: 'Query',
    component: QueryPage,
    meta: { title: '证照查询', topLevel: true },
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: DashboardPage,
    meta: { title: '效期看板', topLevel: true },
  },
  {
    path: '/review',
    name: 'Review',
    component: ReviewPage,
    meta: { admin: true, title: '证照审核', topLevel: true },
  },
  {
    path: '/review/:id',
    name: 'ReviewDetail',
    component: ReviewDetailPage,
    meta: { admin: true, title: '审核详情' },
  },
  {
    path: '/review/:id/source-preview',
    name: 'ReviewSourcePreview',
    component: ReviewSourcePreviewPage,
    meta: { admin: true, noTabbar: true, noShell: true, title: '原文件预览' },
  },
  {
    path: '/admin',
    name: 'Admin',
    component: AdminPage,
    meta: { admin: true, title: '系统配置', topLevel: true },
  },
  {
    path: '/admin/import',
    name: 'Import',
    component: ImportPage,
    meta: { admin: true, title: '批量导入' },
  },
  {
    path: '/tobacco/reports',
    name: 'TobaccoReports',
    component: TobaccoReportList,
    meta: { title: '一致性校验', topLevel: true },
  },
  {
    path: '/tobacco/reports/:id',
    name: 'TobaccoReportDetail',
    component: TobaccoReportDetail,
    meta: { title: '一致性校验详情' },
  },
  {
    path: '/profile',
    name: 'Profile',
    component: ProfilePage,
    meta: { title: '个人中心', topLevel: true },
  },
  {
    path: '/:pathMatch(.*)*',
    redirect: '/home',
  },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

let profilePromise = null
let sessionVerified = false

function loginRedirect(to) {
  return {
    path: '/login',
    query: to.fullPath && to.fullPath !== '/login' ? { redirect: to.fullPath } : {},
  }
}

async function verifySession() {
  const userStore = useUserStore()
  if (sessionVerified && userStore.user) return true

  if (!profilePromise) {
    profilePromise = userStore.fetchProfile()
      .then(() => {
        sessionVerified = true
        return true
      })
      .catch(() => {
        sessionVerified = false
        userStore.logout()
        return false
      })
      .finally(() => {
        profilePromise = null
      })
  }
  return profilePromise
}

// 登录守卫：每次进入业务页面都以后端真实会话为准。
router.beforeEach(async (to) => {
  if (to.meta.noAuth) return true

  return (await verifySession()) ? true : loginRedirect(to)
})

export default router
