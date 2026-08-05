import assert from 'node:assert/strict'

import {
  projectQueryResult,
  shouldRefreshSingleQuery,
} from '../src/features/query/queryResultModel.js'

const sourceResult = {
  type: 'batch',
  records: [
    { id: 'business-valid', document_type: 'business_license', expire_status: 'valid' },
    { id: 'business-expiring', document_type: 'business_license', expire_status: 'expiring_soon' },
    { id: 'food-expired', document_type: 'food_production_license', expire_status: 'expired' },
  ],
  stats: { found: 3, expiring: 1, expired: 1, missing: 2 },
}

const businessResult = projectQueryResult(sourceResult, 'business_license')

assert.deepEqual(
  businessResult.records.map((record) => record.id),
  ['business-valid', 'business-expiring'],
)
assert.deepEqual(businessResult.stats, {
  found: 2,
  expiring: 1,
  expired: 0,
  missing: 2,
})

const allResult = projectQueryResult(sourceResult, '')

assert.deepEqual(allResult, sourceResult)
assert.notEqual(allResult, sourceResult)
assert.notEqual(allResult.records, sourceResult.records)

assert.equal(projectQueryResult(null, 'business_license'), null)

assert.equal(shouldRefreshSingleQuery('single', '供应商 A'), true)
assert.equal(shouldRefreshSingleQuery('batch', '供应商 A'), false)
assert.equal(shouldRefreshSingleQuery('excel', '供应商 A'), false)
assert.equal(shouldRefreshSingleQuery('single', '   '), false)

console.log('query result model tests passed')
