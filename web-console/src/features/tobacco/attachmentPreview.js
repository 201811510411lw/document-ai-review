export function buildTobaccoAttachmentPreviewRoute(attachment) {
  if (!attachment?.relative_path) return null
  return {
    name: 'TobaccoSourcePreview',
    query: {
      path: attachment.relative_path,
      name: attachment.file_name || attachment.doc_subject || 'OA 附件',
    },
  }
}

export function isTobaccoPreviewImage(mimeType) {
  return String(mimeType || '').startsWith('image/')
}

export function tobaccoPreviewKind(mimeType) {
  if (isTobaccoPreviewImage(mimeType)) return 'image'
  if (String(mimeType || '').toLowerCase() === 'application/pdf') return 'pdf'
  return 'unsupported'
}

export function openTobaccoAttachmentPreview({ attachment, reportId, router, openWindow }) {
  const location = buildTobaccoAttachmentPreviewRoute(attachment)
  if (!location) return { opened: false, reason: 'unavailable' }

  const url = router.resolve({ ...location, params: { id: reportId } }).href
  const previewWindow = openWindow(url, '_blank')
  if (!previewWindow) return { opened: false, reason: 'blocked', url }
  previewWindow.opener = null
  return { opened: true, url }
}

export function createTobaccoAttachmentLoader({ fetchFile, createObjectUrl, revokeObjectUrl }) {
  let activeUrl = ''
  let requestId = 0
  let disposed = false

  function release() {
    if (!activeUrl) return
    revokeObjectUrl(activeUrl)
    activeUrl = ''
  }

  async function load(relativePath) {
    const currentRequestId = ++requestId
    release()
    if (!relativePath) return { status: 'error', message: '附件路径无效' }

    try {
      const content = await fetchFile(relativePath)
      if (disposed || currentRequestId !== requestId) return { status: 'stale' }

      const mimeType = content.type || 'application/octet-stream'
      activeUrl = createObjectUrl(content)
      return {
        status: 'ready',
        url: activeUrl,
        kind: tobaccoPreviewKind(mimeType),
      }
    } catch (error) {
      if (disposed || currentRequestId !== requestId) return { status: 'stale' }
      return { status: 'error', message: error.message || '附件预览失败' }
    }
  }

  function dispose() {
    disposed = true
    requestId += 1
    release()
  }

  return { load, dispose }
}
