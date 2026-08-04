const statusLabels = {
  pending: '待人工复核',
  confirmed: '已认可',
  flagged: '异常',
}

function firstValue(record, keys, fallback = '-') {
  for (const key of keys) {
    const value = record?.[key]
    if (value !== null && value !== undefined && String(value).trim()) return String(value)
  }
  return fallback
}

function formatMatchRatio(value) {
  if (value === null || value === undefined || value === '') return '-'
  return `${Math.round(Number(value))}%`
}

export function buildWorkbenchOverview({ dashboardStats = {}, reviewResponse = {} }) {
  const reviewStats = reviewResponse.stats || {}
  const reviewTotal = Number(reviewStats.total ?? 0)
  const total = Number(dashboardStats.total ?? reviewTotal)
  const pending = Number(reviewStats.pending ?? dashboardStats.pending_manual_review ?? 0)
  const flagged = Number(reviewStats.flagged ?? dashboardStats.expired ?? 0)
  const confirmed = Number(reviewStats.confirmed ?? dashboardStats.valid ?? 0)
  const other = Math.max(total - confirmed - pending - flagged, 0)

  return {
    distributionTotal: reviewTotal || total,
    metrics: [
      { label: '证照总量', value: total, tone: 'primary' },
      { label: '待人工复核', value: pending, tone: 'pending' },
      { label: '异常记录', value: flagged, tone: 'flagged' },
      { label: '有效证照', value: Number(dashboardStats.valid ?? confirmed), tone: 'confirmed' },
    ],
    distribution: [
      { label: '已认可', value: confirmed, tone: 'confirmed' },
      { label: '待复核', value: pending, tone: 'pending' },
      { label: '异常', value: flagged, tone: 'flagged' },
      { label: '其他', value: other, tone: 'other' },
    ],
    tasks: (reviewResponse.records || []).map(record => ({
      id: record.id,
      title: firstValue(record, ['company_name', 'product_name', 'sample_name'], '未识别审核对象'),
      identifier: firstValue(record, ['credit_code', 'license_no', 'order_number', 'batch_no']),
      documentType: firstValue(record, ['license_type', 'document_type']),
      status: record.review_status || 'default',
      statusLabel: statusLabels[record.review_status] || '无需审核',
      riskLevel: record.risk_level || '',
      matchRatio: formatMatchRatio(record.match_ratio),
      updatedAt: firstValue(record, ['updated_at', 'created_at']),
    })),
  }
}
