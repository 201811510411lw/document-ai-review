import assert from 'node:assert/strict'

import { reviewQueueNotice } from '../src/features/review/queueModel.js'

const stats = { pending: 53, confirmed: 20, flagged: 1 }

assert.equal(reviewQueueNotice({ filterStatus: '', stats }), '有 53 条记录需要人工复核，请优先处理。')
assert.equal(reviewQueueNotice({ filterStatus: 'pending', stats }), '有 53 条记录需要人工复核，请优先处理。')
assert.equal(reviewQueueNotice({ filterStatus: 'confirmed', stats }), '')
assert.equal(reviewQueueNotice({ filterStatus: 'flagged', stats }), '')
assert.equal(reviewQueueNotice({ filterStatus: '', stats: { pending: 0 } }), '')
