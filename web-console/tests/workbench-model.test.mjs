import assert from 'node:assert/strict'

import {
  buildDesktopNavigation,
  buildMobileNavigation,
} from '../src/features/workbench/navigation.js'
import { buildWorkbenchOverview } from '../src/features/workbench/overview.js'

const reviewerDesktop = buildDesktopNavigation({ isAdmin: false, currentPath: '/tobacco/reports/abc' })
assert.deepEqual(reviewerDesktop.map(group => group.label), ['工作空间', '烟草业务'])
assert.equal(reviewerDesktop.flatMap(group => group.items).some(item => item.to === '/admin'), false)
assert.equal(reviewerDesktop.flatMap(group => group.items).some(item => item.to === '/review'), false)
assert.equal(reviewerDesktop[0].items.some(item => item.to === '/tobacco/reports'), false)
assert.deepEqual(reviewerDesktop.at(-1).items.map(item => item.to), ['/tobacco/reports'])
assert.equal(
  reviewerDesktop.flatMap(group => group.items).find(item => item.to === '/tobacco/reports')?.active,
  true,
)
const reviewerTobaccoList = buildDesktopNavigation({ isAdmin: false, currentPath: '/tobacco/reports' })
assert.equal(reviewerTobaccoList.at(-1).items[0].active, true)

const adminDesktop = buildDesktopNavigation({ isAdmin: true, currentPath: '/review/task-1' })
assert.deepEqual(adminDesktop.map(group => group.label), ['工作空间', '管理', '烟草业务'])
assert.equal(adminDesktop.flatMap(group => group.items).some(item => item.to === '/admin'), true)
assert.equal(adminDesktop.flatMap(group => group.items).find(item => item.to === '/review')?.active, true)
assert.deepEqual(adminDesktop.at(-1).items.map(item => item.to), ['/tobacco/reports'])

const adminMobile = buildMobileNavigation({ isAdmin: true, currentPath: '/dashboard' })
assert.deepEqual(adminMobile.map(item => item.to), ['/home', '/review', '/dashboard', '/profile'])
assert.equal(adminMobile.find(item => item.to === '/dashboard')?.active, true)

const overview = buildWorkbenchOverview({
  dashboardStats: {
    total: 286,
    valid: 231,
    expired: 7,
    pending_manual_review: 18,
  },
  reviewResponse: {
    stats: { total: 286, pending: 18, flagged: 7, confirmed: 231 },
    records: [
      {
        id: 'task-1',
        company_name: '北京华联综合超市股份有限公司',
        credit_code: '9111****752M',
        license_type: '营业执照',
        review_status: 'pending',
        risk_level: 'HIGH',
        match_ratio: 86,
        created_at: '2026-08-04T10:20:00',
      },
      {
        id: 'task-2',
        product_name: '示例商品',
        license_type: '商品报告',
        review_status: 'confirmed',
      },
    ],
  },
})

assert.deepEqual(overview.metrics.map(metric => metric.value), [286, 18, 7, 231])
assert.equal(overview.distributionTotal, 286)
assert.equal(overview.tasks[0].title, '北京华联综合超市股份有限公司')
assert.equal(overview.tasks[0].identifier, '9111****752M')
assert.equal(overview.tasks[0].statusLabel, '待人工复核')
assert.equal(overview.tasks[0].matchRatio, '86%')
assert.equal(overview.tasks[1].title, '示例商品')
assert.equal(overview.tasks[1].identifier, '-')
assert.equal(overview.tasks[1].matchRatio, '-')
assert.deepEqual(overview.distribution, [
  { label: '已认可', value: 231, tone: 'confirmed' },
  { label: '待复核', value: 18, tone: 'pending' },
  { label: '异常', value: 7, tone: 'flagged' },
  { label: '其他', value: 30, tone: 'other' },
])

const mixedTotals = buildWorkbenchOverview({
  dashboardStats: { total: 920, valid: 840 },
  reviewResponse: { stats: { total: 80, pending: 12, flagged: 8, confirmed: 50 } },
})
assert.equal(mixedTotals.metrics[0].value, 920)
assert.equal(mixedTotals.distributionTotal, 80)
assert.equal(mixedTotals.distribution.at(-1).value, 10)
