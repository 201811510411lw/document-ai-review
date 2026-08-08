import assert from 'node:assert/strict'

import { buildFieldRiskBadge, buildRuleRiskBadge } from '../src/features/review/detailModel.js'

assert.deepEqual(
  buildRuleRiskBadge({ passed: false, risk_level_on_failure: 'HIGH', details: { confidence: 'HIGH' } }),
  { label: 'HIGH', className: 'risk-high' },
)
assert.deepEqual(
  buildRuleRiskBadge({ passed: false, risk_level_on_failure: 'MEDIUM', details: { confidence: 'HIGH' } }),
  { label: 'MEDIUM', className: 'risk-medium' },
)
assert.equal(buildRuleRiskBadge({ details: { confidence: 'LOW' } }), null)
assert.equal(buildRuleRiskBadge({ passed: true, risk_level_on_failure: 'HIGH' }), null)

assert.deepEqual(
  buildFieldRiskBadge({ risk: 'HIGH' }),
  { label: 'HIGH', className: 'risk-high' },
)
assert.deepEqual(
  buildFieldRiskBadge({ risk: 'expiring_soon' }),
  { label: 'MEDIUM', className: 'risk-medium' },
)
assert.equal(buildFieldRiskBadge({ risk: '' }), null)
