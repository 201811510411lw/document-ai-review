import assert from 'node:assert/strict'
import { createServer } from 'vite'

globalThis.localStorage = { getItem: () => null }

const vite = await createServer({
  appType: 'custom',
  configFile: false,
  logLevel: 'silent',
  server: { middlewareMode: true },
})

try {
  const { reviewApi } = await vite.ssrLoadModule('/src/api/index.js')
  const { default: http } = await vite.ssrLoadModule('/src/api/http.js')

  const requests = []
  http.defaults.adapter = async (config) => {
    requests.push(config)
    return {
      data: { task_id: 'review-task-1' },
      status: 200,
      statusText: 'OK',
      headers: {},
      config,
    }
  }

  await reviewApi.createFromSrm('product_report')

  assert.equal(requests[0].url, '/api/v1/qc/product-report/reviews/from-srm')
  assert.equal(requests[0].timeout, 0)

  await reviewApi.createFromSrm('business_license')
  assert.equal(requests[1].url, '/api/v1/business-license/reviews/from-srm')
  assert.equal(requests[1].timeout, 30000)
} finally {
  await vite.close()
}
