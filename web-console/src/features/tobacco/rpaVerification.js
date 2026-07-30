export function resolveRpaCertificateNo(report, verification) {
  return verification?.certificate_no || report?.tobacco_license_no || ''
}

export function resolveRpaAction({ capability, status, certificateNo }) {
  const visible = !status || status === 'ERROR'
  if (!visible) {
    return { visible: false, enabled: false, reason: '' }
  }
  if (!capability) {
    return { visible: true, enabled: false, reason: '正在读取官网验真能力状态' }
  }
  if (!capability.enabled) {
    return {
      visible: true,
      enabled: false,
      reason: capability.disabled_reason || 'RPA 验真功能未启用',
    }
  }
  if (!certificateNo) {
    return { visible: true, enabled: false, reason: '缺少烟草证许可证号' }
  }
  return { visible: true, enabled: true, reason: '' }
}
