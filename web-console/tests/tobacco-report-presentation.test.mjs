import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  isReportProcessing,
  reportSubjectLabel,
} from '../src/features/tobacco/reportPresentation.js'

assert.equal(reportSubjectLabel({ processing_status: 'processing', company_name: '' }), '等待识别')
assert.equal(reportSubjectLabel({ processing_status: 'failed', company_name: '' }), '未识别主体名称')
assert.equal(
  reportSubjectLabel({ processing_status: 'processing', company_name: '测试便利店' }),
  '测试便利店',
)
assert.equal(isReportProcessing({ processing_status: 'processing' }), true)
assert.equal(isReportProcessing({ processing_status: 'failed' }), false)

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const detailSource = fs.readFileSync(
  path.join(repoRoot, 'web-console/src/views/TobaccoReportDetail.vue'),
  'utf8',
)

assert.match(detailSource, /v-if="isReportProcessing\(report\)"[\s\S]*证照字段正在识别/)
assert.match(detailSource, /v-else class="comparison-grid"/)

console.log('tobacco report presentation tests passed')
