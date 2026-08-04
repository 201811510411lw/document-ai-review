import assert from 'node:assert/strict'

import { buildRuleRiskBadge } from '../src/features/review/detailModel.js'

assert.deepEqual(
  buildRuleRiskBadge({ risk_level_on_failure: 'HIGH', details: { confidence: 'HIGH' } }),
  { label: 'HIGH', className: 'risk-high' },
)
assert.deepEqual(
  buildRuleRiskBadge({ risk_level_on_failure: 'MEDIUM', details: { confidence: 'HIGH' } }),
  { label: 'MEDIUM', className: 'risk-medium' },
)
assert.equal(buildRuleRiskBadge({ details: { confidence: 'LOW' } }), null)
