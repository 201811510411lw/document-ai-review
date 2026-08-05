import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'

const queryPageSource = readFileSync(
  new URL('../src/views/QueryPage.vue', import.meta.url),
  'utf8',
)
const uploadHandler = queryPageSource.slice(
  queryPageSource.indexOf('async function handleExcelUpload()'),
  queryPageSource.indexOf('// 打包下载'),
)

const uploadCallIndex = uploadHandler.indexOf('await queryApi.uploadExcel')
const querySourceAssignmentIndex = uploadHandler.indexOf("querySource.value = 'excel'")

assert.ok(uploadCallIndex >= 0)
assert.ok(
  querySourceAssignmentIndex > uploadCallIndex,
  'Excel 查询来源只能在上传查询成功后提交',
)

assert.match(
  queryPageSource,
  /const hasResults = computed\(\(\) => \{\s+return searchResult\.value\?\.records\?\.length > 0\s+\}\)/,
  '打包下载全部的启用状态必须基于完整查询结果',
)

console.log('query page view tests passed')
