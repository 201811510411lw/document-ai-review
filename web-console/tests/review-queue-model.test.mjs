import assert from 'node:assert/strict'

import {
  createReviewAndRefreshQueue,
  fetchCurrentReviewPage,
  reviewCreateFailureMessage,
  reviewPagination,
  reviewQueueNotice,
} from '../src/features/review/queueModel.js'

assert.equal(
  reviewCreateFailureMessage({ code: 'UNAUTHORIZED', message: '请先登录工作台' }),
  '登录状态已失效，请重新登录后再发起审核。',
)
assert.equal(
  reviewCreateFailureMessage({ code: 'REQUEST_TIMEOUT' }),
  '发起审核超时。来源文件较大或识别服务响应较慢，请稍后重试。',
)

const stats = { pending: 53, confirmed: 20, flagged: 1 }

assert.equal(reviewQueueNotice({ filterStatus: '', stats }), '有 53 条记录需要人工复核，请优先处理。')
assert.equal(reviewQueueNotice({ filterStatus: 'pending', stats }), '有 53 条记录需要人工复核，请优先处理。')
assert.equal(reviewQueueNotice({ filterStatus: 'confirmed', stats }), '')
assert.equal(reviewQueueNotice({ filterStatus: 'flagged', stats }), '')
assert.equal(reviewQueueNotice({ filterStatus: '', stats: { pending: 0 } }), '')

assert.deepEqual(reviewPagination(45, 2, 20), {
  currentPage: 2,
  totalPages: 3,
  offset: 20,
})
assert.deepEqual(reviewPagination(45, 99, 20), {
  currentPage: 3,
  totalPages: 3,
  offset: 40,
})
assert.deepEqual(reviewPagination(8, 1, 20), {
  currentPage: 1,
  totalPages: 1,
  offset: 0,
})

const requestedOffsets = []
const correctedResult = await fetchCurrentReviewPage({
  requestedPage: 3,
  pageSize: 20,
  fetchPage: async ({ offset }) => {
    requestedOffsets.push(offset)
    return offset === 40
      ? { records: [], filtered_total: 25 }
      : { records: [{ id: 21 }], filtered_total: 25 }
  },
})
assert.deepEqual(requestedOffsets, [40, 20])
assert.deepEqual(correctedResult, {
  response: { records: [{ id: 21 }], filtered_total: 25 },
  currentPage: 2,
})

let resolveStaleRequest
let requestIsCurrent = true
const staleResultPromise = fetchCurrentReviewPage({
  requestedPage: 2,
  fetchPage: () => new Promise((resolve) => { resolveStaleRequest = resolve }),
  isCurrent: () => requestIsCurrent,
})
requestIsCurrent = false
resolveStaleRequest({ records: [{ id: 'stale' }], filtered_total: 40 })
assert.equal(await staleResultPromise, null)

const createFlowEvents = []
await createReviewAndRefreshQueue({
  documentType: 'batch_report',
  createReview: async (documentType) => {
    createFlowEvents.push(`create:${documentType}`)
    return { task_id: 'review-task-batch-1' }
  },
  refreshQueue: async (options) => {
    createFlowEvents.push(`refresh:${options.preserveVisibleRecords}`)
  },
  openReview: (taskId) => createFlowEvents.push(`open:${taskId}`),
})
assert.deepEqual(createFlowEvents, [
  'create:batch_report',
  'refresh:true',
  'open:review-task-batch-1',
])

const productRefreshOptions = []
await createReviewAndRefreshQueue({
  documentType: 'product_report',
  createReview: async () => ({}),
  refreshQueue: async (options) => productRefreshOptions.push(options),
  openReview: () => { throw new Error('task without id must not navigate') },
})
assert.deepEqual(productRefreshOptions, [{ preserveVisibleRecords: false }])
