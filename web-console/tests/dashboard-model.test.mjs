import assert from 'node:assert/strict'

import {
  buildDashboardMetrics,
  filterDashboardRecords,
} from '../src/features/dashboard/dashboardModel.js'

const records = [
  { id: 1, document_type: 'business_license', expire_status: 'valid' },
  { id: 2, document_type: 'business_license', expire_status: 'valid' },
  { id: 3, document_type: 'business_license', expire_status: 'expiring_soon' },
  { id: 4, _document_type: 'business_license', expire_status: 'unknown' },
  { id: 5, document_type: 'food_license', expire_status: 'expired' },
]

assert.deepEqual(buildDashboardMetrics(records), {
  total: 5,
  valid: 2,
  expiring: 1,
  expired: 1,
  unknown: 1,
})
assert.deepEqual(buildDashboardMetrics(records, 'business_license'), {
  total: 4,
  valid: 2,
  expiring: 1,
  expired: 0,
  unknown: 1,
})
assert.equal(filterDashboardRecords(records, {
  documentType: 'business_license',
  expireStatus: 'valid',
}).length, 2)
assert.equal(filterDashboardRecords(records, {
  documentType: 'business_license',
  expireStatus: 'expiring',
}).length, 1)
