export function buildRuleRiskBadge(rule = {}) {
  const riskLevel = String(rule.risk_level_on_failure || '').trim().toUpperCase()
  if (!riskLevel) return null
  return { label: riskLevel, className: `risk-${riskLevel.toLowerCase()}` }
}
