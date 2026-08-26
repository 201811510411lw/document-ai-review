import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  callbackDecisionLabel,
  callbackRecords,
  callbackStatusMeta,
  callbackSuccessMessage,
  manualActionConfig,
} from '../src/features/tobacco/oaCallbackAudit.js'

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const detailSource = fs.readFileSync(
  path.join(repoRoot, 'web-console/src/views/TobaccoReportDetail.vue'),
  'utf8',
)

assert.equal(manualActionConfig('REJECT').commentRequired, true)
assert.equal(manualActionConfig('REQUEST_MORE_INFO').commentRequired, true)
assert.equal(manualActionConfig('APPROVE').commentRequired, false)

const acknowledged = {
  status: 'SENT',
  business_accepted: true,
  request_payload: { result: { data: { decision: 'pass' } } },
}
assert.deepEqual(callbackStatusMeta(acknowledged), { label: 'OA 已接受', type: 'success' })
assert.equal(callbackDecisionLabel(acknowledged), '通过')
assert.equal(callbackSuccessMessage('已人工通过', acknowledged), '已人工通过，OA 已接受')

const unconfirmed = { status: 'SENT', business_accepted: null }
assert.equal(callbackStatusMeta(unconfirmed).label, 'HTTP 已投递，业务未确认')
assert.match(callbackSuccessMessage('已驳回', unconfirmed), /等待 OA 确认/)

const legacy = callbackRecords({ oa_callback: { status: 'SENT' } })
assert.equal(legacy[0].legacy, true)
assert.deepEqual(
  callbackRecords({ oa_callback_history: [{ updated_at: 'old' }, { updated_at: 'new' }] }),
  [{ updated_at: 'new' }, { updated_at: 'old' }],
)

assert.match(detailSource, /OA 回调记录/)
assert.match(detailSource, /request_payload/)
assert.match(detailSource, /response_body/)
assert.match(detailSource, /van-dialog/)

console.log('oa callback audit tests passed')
