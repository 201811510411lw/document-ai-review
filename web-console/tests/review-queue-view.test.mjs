import assert from 'node:assert/strict'
import { createSSRApp, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import vue from '@vitejs/plugin-vue'
import { createServer } from 'vite'

const stats = { pending: 53, confirmed: 20, flagged: 1 }
const vite = await createServer({
  appType: 'custom',
  configFile: false,
  logLevel: 'silent',
  plugins: [vue({
    template: {
      compilerOptions: {
        isCustomElement: (tag) => tag === 'van-icon',
      },
    },
  })],
  server: { middlewareMode: true },
})

try {
  const { default: ReviewQueueView } = await vite.ssrLoadModule('/src/features/review/ReviewQueueView.vue')

  async function renderQueue(filterStatus) {
    const app = createSSRApp({
      render: () => h(ReviewQueueView, {
        currentDocument: { label: '营业执照', subjectLabel: '公司名' },
        documentOptions: [{ value: 'business_license', shortLabel: '营业执照' }],
        activeDocumentType: 'business_license',
        stats,
        filterStatus,
        keyword: '',
        filteredTotal: 0,
        records: [],
        loading: false,
        creating: false,
        listLoading: false,
        listFinished: true,
        createButtonText: '发起营业执照审核',
        onSwitchDocument: () => {},
        onSetFilter: () => {},
        onSearch: () => {},
        onCreate: () => {},
        onOpen: () => {},
        onLoadMore: () => {},
        recordTitle: () => '',
        recordPrimaryMeta: () => '',
        recordSecondaryMeta: () => '',
        recordFooterText: () => '',
        formatRatio: () => '',
        statusText: () => '',
      }),
    })
    return renderToString(app)
  }

  for (const filterStatus of ['', 'pending']) {
    const html = await renderQueue(filterStatus)
    assert.match(html, /class="pending-notice"/)
    assert.match(html, /有 53 条记录需要人工复核，请优先处理。/)
  }
  for (const filterStatus of ['confirmed', 'flagged']) {
    assert.doesNotMatch(await renderQueue(filterStatus), /class="pending-notice"/)
  }
} finally {
  await vite.close()
}
