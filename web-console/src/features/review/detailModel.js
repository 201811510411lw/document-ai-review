export function buildRuleRiskBadge(rule = {}) {
  if (rule.passed) return null
  const riskLevel = String(rule.risk_level_on_failure || '').trim().toUpperCase()
  if (!riskLevel) return null
  return { label: riskLevel, className: `risk-${riskLevel.toLowerCase()}` }
}

export function buildFieldRiskBadge(field = {}) {
  const rawRisk = String(field.risk || '').trim().toLowerCase()
  const riskLevel = {
    expired: 'HIGH',
    invalid: 'HIGH',
    expiring_soon: 'MEDIUM',
  }[rawRisk] || rawRisk.toUpperCase()
  if (!['HIGH', 'MEDIUM', 'LOW'].includes(riskLevel)) return null
  return { label: riskLevel, className: `risk-${riskLevel.toLowerCase()}` }
}
