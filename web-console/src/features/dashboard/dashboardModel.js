function recordDocumentType(record) {
  return record.document_type || record._document_type || ''
}

function recordExpireStatus(expireStatus) {
  return expireStatus === 'expiring' ? 'expiring_soon' : expireStatus
}

export function filterDashboardRecords(records, { documentType = '', expireStatus = '' } = {}) {
  const normalizedExpireStatus = recordExpireStatus(expireStatus)
  return records.filter((record) => (
    (!documentType || recordDocumentType(record) === documentType)
    && (!normalizedExpireStatus || record.expire_status === normalizedExpireStatus)
  ))
}

export function buildDashboardMetrics(records, documentType = '') {
  const scopedRecords = filterDashboardRecords(records, { documentType })
  return {
    total: scopedRecords.length,
    valid: scopedRecords.filter((record) => record.expire_status === 'valid').length,
    expiring: scopedRecords.filter((record) => record.expire_status === 'expiring_soon').length,
    expired: scopedRecords.filter((record) => record.expire_status === 'expired').length,
    unknown: scopedRecords.filter((record) => record.expire_status === 'unknown').length,
  }
}
