function resultStats(records, sourceStats = {}) {
  return {
    ...sourceStats,
    found: records.length,
    expiring: records.filter((record) => record.expire_status === 'expiring_soon').length,
    expired: records.filter((record) => record.expire_status === 'expired').length,
    missing: Number(sourceStats.missing ?? 0),
  }
}

export function projectQueryResult(result, documentType = '') {
  if (!result) return null

  if (result.type === 'single') {
    const record = result.data
    if (!documentType || record?.document_type === documentType) {
      return { ...result, data: record ? { ...record } : record }
    }
    return { type: 'batch', records: [], stats: resultStats([], result.stats) }
  }

  const records = (result.records || [])
    .filter((record) => !documentType || record.document_type === documentType)
    .map((record) => ({ ...record }))

  return {
    ...result,
    records,
    stats: resultStats(records, result.stats),
  }
}

export function shouldRefreshSingleQuery(querySource, keyword = '') {
  return querySource === 'single' && Boolean(keyword.trim())
}
