import assert from 'node:assert/strict'
import { createReportRefresher } from '../src/features/tobacco/reportRefresh.js'

let visible = true
let pending = null
let resolveRequest
const calls = []
const refresher = createReportRefresher({
  load(options) {
    calls.push(options)
    return new Promise(resolve => { resolveRequest = resolve })
  },
  isVisible: () => visible,
  schedule(callback, delay) {
    assert.equal(delay, 15000)
    pending = callback
    return callback
  },
  cancel(timer) {
    if (pending === timer) pending = null
  },
})

const initial = refresher.start()
assert.deepEqual(calls, [{ background: false }])
assert.equal(pending, null)
await refresher.refresh()
assert.equal(calls.length, 1, 'slow requests must not overlap')
resolveRequest()
await initial
assert.equal(typeof pending, 'function')

visible = false
await pending()
assert.equal(calls.length, 1, 'hidden pages must not request data')
assert.equal(typeof pending, 'function')
visible = true
const resumed = refresher.refresh()
assert.deepEqual(calls[1], { background: true })
resolveRequest()
await resumed

const tick = pending()
assert.equal(calls.length, 3, 'visible pages refresh on the next timer')
refresher.stop()
resolveRequest()
await tick
assert.equal(pending, null, 'completion after unmount must not reschedule')
await refresher.refresh()
assert.equal(calls.length, 3)

console.log('tobacco report refresh tests passed')
