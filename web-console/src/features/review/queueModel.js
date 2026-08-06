export function reviewQueueNotice({ filterStatus = '', stats = {} }) {
  const pending = Number(stats.pending || 0)
  if (!pending || !['', 'pending'].includes(filterStatus)) return ''
  return `有 ${pending} 条记录需要人工复核，请优先处理。`
}

export async function createReviewAndRefreshQueue({
  documentType,
  createReview,
  refreshQueue,
  openReview,
}) {
  const result = await createReview(documentType)
  await refreshQueue({ preserveVisibleRecords: documentType === 'batch_report' })
  if (result?.task_id) openReview(result.task_id)
  return result
}

export function reviewPagination(totalRecords, requestedPage, pageSize = 20) {
  const totalPages = Math.max(1, Math.ceil(totalRecords / pageSize))
  const currentPage = Math.min(Math.max(1, Number(requestedPage) || 1), totalPages)

  return {
    currentPage,
    totalPages,
    offset: reviewPageOffset(currentPage, pageSize),
  }
}

export function reviewPageOffset(requestedPage, pageSize = 20) {
  const currentPage = Math.max(1, Number(requestedPage) || 1)
  return (currentPage - 1) * pageSize
}

export async function fetchCurrentReviewPage({
  fetchPage,
  requestedPage,
  pageSize = 20,
  isCurrent = () => true,
}) {
  let currentPage = Math.max(1, Number(requestedPage) || 1)

  while (true) {
    const response = await fetchPage({
      limit: pageSize,
      offset: reviewPageOffset(currentPage, pageSize),
    })
    if (!isCurrent()) return null

    const correctedPage = reviewPagination(
      response.filtered_total ?? response.records?.length ?? 0,
      currentPage,
      pageSize,
    ).currentPage
    if (correctedPage === currentPage) return { response, currentPage }
    currentPage = correctedPage
  }
}
