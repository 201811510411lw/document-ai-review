export function reviewQueueNotice({ filterStatus = '', stats = {} }) {
  const pending = Number(stats.pending || 0)
  if (!pending || !['', 'pending'].includes(filterStatus)) return ''
  return `有 ${pending} 条记录需要人工复核，请优先处理。`
}
