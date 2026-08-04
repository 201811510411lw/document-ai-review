import assert from 'node:assert/strict'

import {
  fetchCurrentReviewPage,
  reviewPagination,
  reviewQueueNotice,
} from '../src/features/review/queueModel.js'

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
