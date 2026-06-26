/**
 * 工具函数
 */

// 效期状态图标和文字
export const EXPIRE_STATUS_MAP = {
  valid: { icon: '✅', text: '未过期', color: '#07c160' },
  expiring_soon: { icon: '⚠️', text: '即将过期', color: '#ff976a' },
  expired: { icon: '❌', text: '已过期', color: '#ee0a24' },
  unknown: { icon: '❓', text: '未知', color: '#969799' },
}

// 格式化日期
export function formatDate(dateStr) {
  if (!dateStr) return '未知'
  return dateStr
}

// 下载 Blob 文件
export function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

// 本地存储历史查询
export function getSearchHistory() {
  try {
    return JSON.parse(localStorage.getItem('search_history') || '[]')
  } catch {
    return []
  }
}

export function addSearchHistory(keyword) {
  const history = getSearchHistory().filter(h => h !== keyword)
  history.unshift(keyword)
  localStorage.setItem('search_history', JSON.stringify(history.slice(0, 20)))
}
