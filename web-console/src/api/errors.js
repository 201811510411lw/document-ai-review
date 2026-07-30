export function apiErrorMessage(error) {
  const data = error?.response?.data
  const detail = data?.detail
  if (detail && typeof detail === 'object' && detail.message) {
    return detail.message
  }
  if (typeof detail === 'string' && detail) {
    return detail
  }
  return data?.message || error?.message || '请求失败'
}
