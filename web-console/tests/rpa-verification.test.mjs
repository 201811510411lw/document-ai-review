import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

import {
  resolveRpaAction,
  resolveRpaCertificateNo,
} from '../src/features/tobacco/rpaVerification.js'


assert.equal(
  resolveRpaCertificateNo(
    { tobacco_license_no: '510100100001', tobacco_license_name: '测试烟草商行' },
    null,
  ),
  '510100100001',
)
assert.equal(
  resolveRpaCertificateNo(
    { tobacco_license_no: '510100100001' },
    { certificate_no: '510100100099' },
  ),
  '510100100099',
)
assert.equal(
  resolveRpaCertificateNo({ tobacco_license_name: '测试烟草商行' }, null),
  '',
)

assert.deepEqual(
  resolveRpaAction({ capability: null, status: null, certificateNo: '510100100001' }),
  { visible: true, enabled: false, reason: '正在读取官网验真能力状态' },
)
assert.deepEqual(
  resolveRpaAction({
    capability: { enabled: false, disabled_reason: 'RPA 验真功能未启用' },
    status: null,
    certificateNo: '510100100001',
  }),
  { visible: true, enabled: false, reason: 'RPA 验真功能未启用' },
)
assert.deepEqual(
  resolveRpaAction({
    capability: { enabled: true },
    status: null,
    certificateNo: '',
  }),
  { visible: true, enabled: false, reason: '缺少烟草证许可证号' },
)
assert.deepEqual(
  resolveRpaAction({
    capability: { enabled: true },
    status: null,
    certificateNo: '510100100001',
  }),
  { visible: true, enabled: true, reason: '' },
)
assert.deepEqual(
  resolveRpaAction({
    capability: { enabled: true },
    status: 'AUTHENTIC',
    certificateNo: '510100100001',
  }),
  { visible: false, enabled: false, reason: '' },
)
assert.deepEqual(
  resolveRpaAction({
    capability: { enabled: true },
    status: 'FAILED',
    certificateNo: '510100100001',
  }),
  { visible: false, enabled: false, reason: '' },
)

const repoRoot = path.resolve(fileURLToPath(new URL('../..', import.meta.url)))
const apiSource = readFileSync(path.join(repoRoot, 'web-console/src/api/index.js'), 'utf8')
const detailSource = readFileSync(
  path.join(repoRoot, 'web-console/src/views/TobaccoReportDetail.vue'),
  'utf8',
)

assert.match(
  apiSource,
  /getCapability\(\)[\s\S]*rpa-verify-capability/,
  'rpaApi should expose the backend capability endpoint',
)
assert.match(
  detailSource,
  /rpaApi\.getCapability\(\)/,
  'Tobacco report detail should load the backend RPA capability',
)
assert.match(
  detailSource,
  /rpaApi\.triggerVerify\(item\.id, rpaCertificateNo\.value,/,
  'Tobacco report detail should submit the extracted license number',
)
assert.doesNotMatch(
  detailSource,
  /rpaApi\.triggerVerify\(item\.id, item\.tobacco_license_name,/,
  'Tobacco report detail must not submit the subject name as certificate_no',
)
assert.match(
  detailSource,
  /rpaStatus === 'FAILED'[\s\S]*官网验真未通过/,
  'Tobacco report detail should distinguish verification failure from execution error',
)
assert.match(
  detailSource,
  /rpaStatus === 'ERROR'[\s\S]*验真未完成或执行异常/,
  'Tobacco report detail should describe missing results as an execution error',
)
