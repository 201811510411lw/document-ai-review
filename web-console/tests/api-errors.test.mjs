import assert from 'node:assert/strict'

import { apiErrorMessage } from '../src/api/errors.js'


assert.equal(
  apiErrorMessage({
    response: {
      data: {
        detail: {
          code: 'RPA_VERIFICATION_DISABLED',
          message: 'RPA 验真功能未启用',
        },
      },
    },
    message: 'Request failed with status code 400',
  }),
  'RPA 验真功能未启用',
)

assert.equal(
  apiErrorMessage({ response: { data: { detail: '记录不存在' } } }),
  '记录不存在',
)

assert.equal(
  apiErrorMessage({ response: { data: { message: '请求参数错误' } } }),
  '请求参数错误',
)

assert.equal(apiErrorMessage({ message: 'Network Error' }), 'Network Error')
