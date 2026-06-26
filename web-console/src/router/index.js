import { createRouter, createWebHashHistory } from 'vue-router'

import QueryPage from '@/views/QueryPage.vue'
import DashboardPage from '@/views/DashboardPage.vue'
import ReviewPage from '@/views/ReviewPage.vue'
import ReviewDetailPage from '@/views/ReviewDetailPage.vue'
import AdminPage from '@/views/AdminPage.vue'
import ProfilePage from '@/views/ProfilePage.vue'
import LoginPage from '@/views/LoginPage.vue'
import HomePage from '@/views/HomePage.vue'
import Scene1Home from '@/views/Scene1Home.vue'
import TobaccoReportList from '@/views/TobaccoReportList.vue'
import TobaccoReportDetail from '@/views/TobaccoReportDetail.vue'
import ContractReportList from '@/views/ContractReportList.vue'
import ContractReportDetail from '@/views/ContractReportDetail.vue'

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
    path: '/contract/reports',
    name: 'ContractReports',
    component: ContractReportList,
  },
  {
    path: '/contract/reports/:id',
    name: 'ContractReportDetail',
    component: ContractReportDetail,
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

// 登录守卫：未登录且非演示模式 → 跳转登录页
router.beforeEach(async (to) => {
  if (to.meta.noAuth) return true

  const token = localStorage.getItem('auth_token')
  const isDemo = localStorage.getItem('demo_mode') === 'true'
  if (!token && !isDemo) {
    return { path: '/login' }
  }
  return true
})

export default router
