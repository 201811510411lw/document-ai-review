import assert from 'node:assert/strict'
import { createMemoryHistory, createRouter } from 'vue-router'

import {
  buildTobaccoAttachmentPreviewRoute,
  createTobaccoAttachmentLoader,
  isTobaccoPreviewImage,
  openTobaccoAttachmentPreview,
  tobaccoPreviewKind,
} from '../src/features/tobacco/attachmentPreview.js'

assert.deepEqual(buildTobaccoAttachmentPreviewRoute({
  relative_path: '流程 2801287/烟草证#正面.jpg',
  file_name: '烟草证#正面.jpg',
}), {
  name: 'TobaccoSourcePreview',
  query: {
    path: '流程 2801287/烟草证#正面.jpg',
    name: '烟草证#正面.jpg',
  },
})
assert.equal(buildTobaccoAttachmentPreviewRoute({ file_name: '未落盘.jpg' }), null)
assert.equal(isTobaccoPreviewImage('image/jpeg'), true)
assert.equal(isTobaccoPreviewImage('application/pdf'), false)
assert.equal(tobaccoPreviewKind('application/pdf'), 'pdf')
assert.equal(tobaccoPreviewKind('application/zip'), 'unsupported')

const router = createRouter({
  history: createMemoryHistory(),
  routes: [{
    path: '/tobacco/reports/:id/source-preview',
    name: 'TobaccoSourcePreview',
    component: { render: () => null },
  }],
})
const openedUrls = []
const opened = openTobaccoAttachmentPreview({
  attachment: {
    relative_path: '流程 2801287/烟草证#正面.jpg',
    file_name: '烟草证#正面.jpg',
  },
  reportId: 'report-1',
  router,
  openWindow: (url) => {
    openedUrls.push(url)
    return { opener: {} }
  },
})
assert.equal(opened.opened, true)
assert.equal(openedUrls.length, 1)
assert.match(opened.url, /\/tobacco\/reports\/report-1\/source-preview\?/)
assert.match(opened.url, /path=.*%23/)
assert.equal(openTobaccoAttachmentPreview({
  attachment: { relative_path: 'a.jpg' },
  reportId: 'report-1',
  router,
  openWindow: () => null,
}).reason, 'blocked')

let resolveOldRequest
const createdUrls = []
const revokedUrls = []
const loader = createTobaccoAttachmentLoader({
  fetchFile: (path) => path === 'old.jpg'
    ? new Promise((resolve) => { resolveOldRequest = resolve })
    : Promise.resolve({ type: 'application/pdf' }),
  createObjectUrl: () => {
    const url = `blob:${createdUrls.length + 1}`
    createdUrls.push(url)
    return url
  },
  revokeObjectUrl: (url) => revokedUrls.push(url),
})
const oldRequest = loader.load('old.jpg')
assert.deepEqual(await loader.load('new.pdf'), {
  status: 'ready',
  url: 'blob:1',
  kind: 'pdf',
})
resolveOldRequest({ type: 'image/jpeg' })
assert.deepEqual(await oldRequest, { status: 'stale' })
assert.deepEqual(createdUrls, ['blob:1'])
loader.dispose()
assert.deepEqual(revokedUrls, ['blob:1'])

let resolveDisposedRequest
const disposedLoader = createTobaccoAttachmentLoader({
  fetchFile: () => new Promise((resolve) => { resolveDisposedRequest = resolve }),
  createObjectUrl: () => { throw new Error('disposed request must not create a URL') },
  revokeObjectUrl: () => {},
})
const disposedRequest = disposedLoader.load('slow.jpg')
disposedLoader.dispose()
resolveDisposedRequest({ type: 'image/jpeg' })
assert.deepEqual(await disposedRequest, { status: 'stale' })
