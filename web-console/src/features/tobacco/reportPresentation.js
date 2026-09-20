export function isReportProcessing(report) {
  return report?.processing_status === 'processing'
}

export function reportSubjectLabel(report) {
  if (report?.company_name) return report.company_name
  return isReportProcessing(report) ? '等待识别' : '未识别主体名称'
}

export function reportFilterStatus(report) {
  const result = report?.overall_result
  return result === '通过' || result === '不通过' ? result : '待校验'
}

function reportDate(value) {
  if (!value) return null
  let text = String(value).trim().replace(' ', 'T')
  // Legacy values without an offset are business local time (Asia/Shanghai).
  if (/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/.test(text)) text += '+08:00'
  const date = new Date(text)
  return Number.isNaN(date.getTime()) ? null : date
}

export function formatReportTime(value) {
  const date = reportDate(value)
  if (!date) return '时间未知'
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Shanghai', hourCycle: 'h23',
    year: 'numeric', month: '2-digit', day: '2-digit',
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  }).formatToParts(date).map(({ type, value }) => [type, value]))
  return `${parts.year}-${parts.month}-${parts.day} ${parts.hour}:${parts.minute}:${parts.second}`
}

export function filterReports(records, { keyword = '', status = '' } = {}) {
  const term = keyword.trim().toLowerCase()
  return records.filter((report) => {
    const text = `${report.company_name || ''} ${report.store_code || ''}`.toLowerCase()
    return (!status || reportFilterStatus(report) === status) && (!term || text.includes(term))
  }).sort((left, right) => (
    (reportDate(right.compare_time || right.created_at)?.getTime() || 0)
    - (reportDate(left.compare_time || left.created_at)?.getTime() || 0)
  ))
}
