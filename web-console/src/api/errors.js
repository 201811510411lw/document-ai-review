export function apiErrorInfo(error) {
  const data = error?.response?.data
  const detail = data?.detail
  if (detail && typeof detail === 'object' && detail.message) {
    return {
      message: detail.message,
      code: detail.code || '',
      status: error.response?.status || 0,
    }
  }
  if (typeof detail === 'string' && detail) {
    return {
      message: detail,
      code: '',
      status: error.response?.status || 0,
    }
  }
  if (Array.isArray(detail) && detail.length) {
    const firstError = detail[0]
    return {
      message: firstError?.msg || '请求参数不符合要求',
      code: firstError?.type || '',
      status: error.response?.status || 0,
    }
  }
  if (error?.code === 'ECONNABORTED') {
    return {
      message: '请求超时，请稍后重试',
      code: 'REQUEST_TIMEOUT',
      status: 0,
    }
  }
  return {
    message: data?.message || error?.message || '请求失败',
    code: data?.code || error?.code || '',
    status: error.response?.status || 0,
  }
}

export function apiErrorMessage(error) {
  return apiErrorInfo(error).message
}
