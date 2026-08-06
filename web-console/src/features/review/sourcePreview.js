export function reviewSourcePreviewKind(mimeType) {
  const normalized = String(mimeType || '').toLowerCase().split(';', 1)[0].trim()
  if (normalized.startsWith('image/')) return 'image'
  if (normalized === 'application/pdf') return 'pdf-pages'
  return 'unsupported'
}

export async function renderReviewPdfPages({
  data,
  container,
  getDocument,
  createCanvas = () => document.createElement('canvas'),
  pixelRatio = globalThis.window?.devicePixelRatio || 1,
  signal,
}) {
  throwIfAborted(signal)
  const loadingTask = getDocument({ data })
  const abortLoading = () => loadingTask.destroy?.()
  signal?.addEventListener('abort', abortLoading, { once: true })
  let pdf
  try {
    pdf = await loadingTask.promise
  } catch (error) {
    if (signal?.aborted) throw abortError()
    throw error
  } finally {
    signal?.removeEventListener('abort', abortLoading)
  }
  try {
    throwIfAborted(signal)
    const outputScale = Math.min(Math.max(Number(pixelRatio) || 1, 1), 2)
    const availableWidth = Math.max(Number(container.clientWidth) || 0, 1)
    container.replaceChildren()

    for (let pageNumber = 1; pageNumber <= pdf.numPages; pageNumber += 1) {
      throwIfAborted(signal)
      const page = await pdf.getPage(pageNumber)
      const baseViewport = page.getViewport({ scale: 1 })
      const viewport = page.getViewport({ scale: availableWidth / baseViewport.width })
      const canvas = createCanvas()
      const context = canvas.getContext('2d')
      canvas.width = Math.floor(viewport.width * outputScale)
      canvas.height = Math.floor(viewport.height * outputScale)
      canvas.style.width = `${Math.floor(viewport.width)}px`
      canvas.style.height = `${Math.floor(viewport.height)}px`
      canvas.className = 'source-pdf-page'
      const renderTask = page.render({
        canvasContext: context,
        viewport,
        transform: outputScale === 1 ? null : [outputScale, 0, 0, outputScale, 0, 0],
      })
      const abortRendering = () => renderTask.cancel?.()
      signal?.addEventListener('abort', abortRendering, { once: true })
      try {
        await renderTask.promise
      } catch (error) {
        if (signal?.aborted) throw abortError()
        throw error
      } finally {
        signal?.removeEventListener('abort', abortRendering)
      }
      throwIfAborted(signal)
      container.appendChild(canvas)
    }
  } finally {
    await pdf.destroy()
  }
}

function throwIfAborted(signal) {
  if (signal?.aborted) throw abortError()
}

function abortError() {
  const error = new Error('PDF rendering aborted')
  error.name = 'AbortError'
  return error
}
