const ACTIONS = {
  APPROVE: {
    title: '确认人工通过',
    placeholder: '可填写人工核对依据',
    success: '已人工通过',
    commentRequired: false,
  },
  REJECT: {
    title: '确认驳回',
    placeholder: '请填写驳回原因',
    success: '已驳回',
    commentRequired: true,
  },
  REQUEST_MORE_INFO: {
    title: '确认要求补件',
    placeholder: '请填写需要补充的材料',
    success: '已要求补件',
    commentRequired: true,
  },
}

export function manualActionConfig(decision) {
  return ACTIONS[decision] || ACTIONS.APPROVE
}

export function callbackRecords(report) {
  const history = Array.isArray(report?.oa_callback_history)
    ? report.oa_callback_history.filter(Boolean)
    : []
  if (history.length) return [...history].reverse()
  return report?.oa_callback ? [{ ...report.oa_callback, legacy: true }] : []
}

export function callbackStatusMeta(record) {
  if (record?.status === 'FAILED' || record?.business_accepted === false) {
    return { label: '发送失败', type: 'danger' }
  }
  if (record?.status === 'PENDING') {
    return { label: '发送中', type: 'primary' }
  }
  if (record?.business_accepted === true) {
    return { label: 'OA 已接受', type: 'success' }
  }
  if (record?.status === 'SENT') {
    return { label: 'HTTP 已投递，业务未确认', type: 'warning' }
  }
  return { label: '状态未知', type: 'default' }
}

export function callbackTriggerLabel(trigger) {
  return {
    auto_review: '自动审核完成',
    manual_review: '人工处置',
    manual_retry: '手动重新回调',
    recovery: '后台恢复重试',
  }[trigger] || '历史回调'
}

export function callbackDecisionLabel(record) {
  return {
    pass: '通过',
    reject: '驳回',
    manual_review: '人工复核 / 补件',
    exception: '技术异常',
  }[record?.request_payload?.result?.data?.decision] || '-'
}

export function formatAuditJson(value) {
  if (value == null || value === '') return '-'
  if (typeof value === 'string') return value
  return JSON.stringify(value, null, 2)
}

export function callbackSuccessMessage(baseMessage, callback) {
  if (callback?.status === 'FAILED' || callback?.business_accepted === false) {
    return `${baseMessage}，但 OA 回调失败`
  }
  if (callback?.business_accepted === true) {
    return `${baseMessage}，OA 已接受`
  }
  return `${baseMessage}，HTTP 已投递，等待 OA 确认`
}
