import assert from 'node:assert/strict'

import {
  renderReviewPdfPages,
  reviewSourcePreviewKind,
} from '../src/features/review/sourcePreview.js'

assert.equal(reviewSourcePreviewKind('image/jpeg'), 'image')
assert.equal(reviewSourcePreviewKind('application/pdf'), 'pdf-pages')
assert.equal(reviewSourcePreviewKind('application/zip'), 'unsupported')

const renderedPages = []
const appendedCanvases = []
const container = {
  clientWidth: 320,
  replaceChildren: () => { appendedCanvases.length = 0 },
  appendChild: (canvas) => appendedCanvases.push(canvas),
}
const pdf = {
  numPages: 2,
  getPage: async (pageNumber) => ({
    getViewport: ({ scale }) => ({ width: 800 * scale, height: 1000 * scale }),
    render: ({ viewport, transform }) => {
      renderedPages.push({ pageNumber, viewport, transform })
      return { promise: Promise.resolve() }
    },
  }),
  destroy: async () => {},
}

await renderReviewPdfPages({
  data: new Uint8Array([1, 2, 3]),
  container,
  pixelRatio: 2,
  getDocument: () => ({ promise: Promise.resolve(pdf) }),
  createCanvas: () => ({ style: {}, getContext: () => ({}) }),
})

assert.equal(appendedCanvases.length, 2)
assert.deepEqual(appendedCanvases.map((canvas) => ({
  width: canvas.width,
  height: canvas.height,
  cssWidth: canvas.style.width,
})), [
  { width: 640, height: 800, cssWidth: '320px' },
  { width: 640, height: 800, cssWidth: '320px' },
])
assert.deepEqual(renderedPages.map(({ pageNumber, transform }) => ({ pageNumber, transform })), [
  { pageNumber: 1, transform: [2, 0, 0, 2, 0, 0] },
  { pageNumber: 2, transform: [2, 0, 0, 2, 0, 0] },
])

const abortController = new AbortController()
const abortedCanvases = []
let abortedPdfDestroyed = 0
const abortablePdf = {
  ...pdf,
  destroy: async () => { abortedPdfDestroyed += 1 },
}
const abortedRender = renderReviewPdfPages({
  data: new Uint8Array([4, 5, 6]),
  container: {
    clientWidth: 320,
    replaceChildren: () => {},
    appendChild: (canvas) => abortedCanvases.push(canvas),
  },
  signal: abortController.signal,
  getDocument: () => ({ promise: Promise.resolve(abortablePdf) }),
  createCanvas: () => ({ style: {}, getContext: () => ({}) }),
})
abortController.abort()

await assert.rejects(abortedRender, { name: 'AbortError' })
assert.equal(abortedCanvases.length, 0)
assert.equal(abortedPdfDestroyed, 1)
