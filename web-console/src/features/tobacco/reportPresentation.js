export function isReportProcessing(report) {
  return report?.processing_status === 'processing'
}

export function reportSubjectLabel(report) {
  if (report?.company_name) return report.company_name
  return isReportProcessing(report) ? '等待识别' : '未识别主体名称'
}
