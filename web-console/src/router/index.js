import { createRouter, createWebHashHistory } from 'vue-router'

import { useUserStore } from '@/store/user'
import QueryPage from '@/views/QueryPage.vue'
import DashboardPage from '@/views/DashboardPage.vue'
import ReviewPage from '@/views/ReviewPage.vue'
import ReviewDetailPage from '@/views/ReviewDetailPage.vue'
import AdminPage from '@/views/AdminPage.vue'
import ImportPage from '@/views/ImportPage.vue'
import ProfilePage from '@/views/ProfilePage.vue'
import LoginPage from '@/views/LoginPage.vue'
import HomePage from '@/views/HomePage.vue'
import Scene1Home from '@/views/Scene1Home.vue'
import TobaccoReportList from '@/views/TobaccoReportList.vue'
import TobaccoReportDetail from '@/views/TobaccoReportDetail.vue'

const routes = [
  {
    path: '/login',
    name: 'Login',
    component: LoginPage,
    meta: { noAuth: true },
  },
  {
    path: '/home',
    name: 'Home',
    component: HomePage,
  },
  {
    path: '/scene1',
    name: 'Scene1',
    component: Scene1Home,
  },
  {
    path: '/query',
    name: 'Query',
    component: QueryPage,
  },
  {
    path: '/dashboard',
    name: 'Dashboard',
    component: DashboardPage,
  },
  {
    path: '/review',
    name: 'Review',
    component: ReviewPage,
    meta: { admin: true },
  },
  {
    path: '/review/:id',
    name: 'ReviewDetail',
    component: ReviewDetailPage,
    meta: { admin: true },
  },
  {
    path: '/admin',
    name: 'Admin',
    component: AdminPage,
    meta: { admin: true },
  },
  {
    path: '/admin/import',
    name: 'Import',
    component: ImportPage,
    meta: { admin: true },
  },
  {
    path: '/tobacco/reports',
    name: 'TobaccoReports',
    component: TobaccoReportList,
  },
  {
    path: '/tobacco/reports/:id',
    name: 'TobaccoReportDetail',
    component: TobaccoReportDetail,
  },
  {
    path: '/profile',
    name: 'Profile',
    component: ProfilePage,
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
