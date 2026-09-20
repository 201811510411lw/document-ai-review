import assert from 'node:assert/strict'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'

import {
  isReportProcessing,
  reportSubjectLabel,
  reportFilterStatus,
  filterReports,
  formatReportTime,
} from '../src/features/tobacco/reportPresentation.js'

assert.equal(reportSubjectLabel({ processing_status: 'processing', company_name: '' }), '等待识别')
assert.equal(reportSubjectLabel({ processing_status: 'failed', company_name: '' }), '未识别主体名称')
assert.equal(
  reportSubjectLabel({ processing_status: 'processing', company_name: '测试便利店' }),
  '测试便利店',
)
assert.equal(isReportProcessing({ processing_status: 'processing' }), true)
assert.equal(isReportProcessing({ processing_status: 'failed' }), false)

const reports = [
  { id: 'earlier', company_name: '其他门店', overall_result: '不通过', compare_time: '2026-09-20T09:22:02+08:00' },
  { id: 'rpa-error', store_code: 'X000001', company_name: '测试便利店', overall_result: '异常', compare_time: '2026-09-20T01:57:33.123995+00:00' },
  { id: 'pending', company_name: '待审核门店', overall_result: '待校验' },
]
assert.equal(reportFilterStatus(reports[1]), '待校验')
assert.deepEqual(filterReports(reports, { keyword: ' x000001 ', status: '待校验' }).map(r => r.id), ['rpa-error'])
assert.deepEqual(filterReports(reports, { status: '待校验' }).map(r => r.id), ['rpa-error', 'pending'])
assert.deepEqual(filterReports(reports, { status: '不通过' }).map(r => r.id), ['earlier'])
assert.deepEqual(filterReports(reports).map(r => r.id), ['rpa-error', 'earlier', 'pending'])
assert.equal(reports[0].id, 'earlier', 'sorting must not mutate records')
assert.equal(formatReportTime('2026-09-20T01:57:33.123995+00:00'), '2026-09-20 09:57:33')
assert.equal(formatReportTime('2026-09-20T09:57:33+08:00'), '2026-09-20 09:57:33')
assert.equal(formatReportTime('2026-09-20T16:30:00Z'), '2026-09-21 00:30:00')
assert.equal(formatReportTime('2026-09-20 09:57:33'), '2026-09-20 09:57:33')
assert.equal(formatReportTime(null), '时间未知')
assert.equal(formatReportTime('invalid'), '时间未知')

const repoRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..')
const detailSource = fs.readFileSync(
  path.join(repoRoot, 'web-console/src/views/TobaccoReportDetail.vue'),
  'utf8',
)

assert.match(detailSource, /v-if="isReportProcessing\(report\)"[\s\S]*证照字段正在识别/)
assert.match(detailSource, /v-else class="comparison-grid"/)

console.log('tobacco report presentation tests passed')
