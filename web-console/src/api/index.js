import http from './http'

export const authApi = {
  providers() {
    return http.get('/api/v1/auth/providers')
  },
  login(username, password) {
    return http.post('/api/v1/auth/login', { username, password })
  },
  startSso(mode = 'qr') {
    return http.get('/api/v1/auth/sso/start', {
      params: { provider: 'wecom', mode },
    })
  },
  profile() {
    return http.get('/auth/profile')
  },
}

export const queryApi = {
  single(params) {
    return http.post('/api/query', params)
  },
  batch(names) {
    return http.post('/api/query/batch', { names })
  },
  uploadExcel(file) {
    const form = new FormData()
    form.append('file', file)
    return http.post('/api/query/excel', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },
  download(ids) {
    return http.post('/api/query/download', { ids }, {
      responseType: 'blob',
      timeout: 180000,
    })
  },
  recent() {
    return http.get('/api/query/recent')
  },
}

export const dashboardApi = {
  stats() {
    return http.get('/api/dashboard/stats')
  },
  daily() {
    return http.get('/api/dashboard/daily')
  },
  history() {
    return http.get('/api/dashboard/history')
  },
}

export const adminApi = {
  getNotifyUsers() {
    return http.get('/api/admin/notify-users')
  },
  setNotifyUsers(userIds) {
    return http.put('/api/admin/notify-users', { userIds })
  },
  getLicenseTypes() {
    return http.get('/api/admin/license-types')
  },
  importPreview(file) {
    const form = new FormData()
    form.append('file', file)
    return http.post('/api/admin/import/preview', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
      timeout: 120000,
    })
  },
  checkExpiry() {
    return http.post('/api/admin/check-expiry')
  },
  getRecords(params) {
    return http.get('/api/records', { params })
  },
  exportRecords(params) {
    return http.get('/api/records/export', {
      params,
      responseType: 'blob',
      timeout: 120000,
    })
  },
  deleteRecord(id) {
    return http.delete(`/api/records/${id}`)
  },
}

export const reviewApi = {
  list(params) {
    return http.get('/api/review/list', { params })
  },
  createFromSrm(documentType = 'business_license') {
    const endpoints = {
      business_license: '/api/v1/business-license/reviews/from-srm',
      food_license: '/api/v1/food-license/reviews/from-srm',
      food_production_license: '/api/v1/qc/food-production-license/reviews/from-srm',
      product_report: '/api/v1/qc/product-report/reviews/from-srm',
      batch_report: '/api/v1/qc/batch-report/reviews/from-starrocks',
    }
    const endpoint = endpoints[documentType] || endpoints.business_license
    return http.post(endpoint)
  },
  detail(id) {
    return http.get(`/api/review/${id}`)
  },
  confirm(id, comment = '') {
    return http.post(`/api/review/${id}/confirm`, { comment })
  },
  flag(id, comment = '') {
    return http.post(`/api/review/${id}/flag`, { comment })
  },
}

export const tobaccoApi = {
  list(params) {
    return http.get('/api/tobacco/reports', { params })
  },
  detail(id) {
    return http.get(`/api/tobacco/reports/${id}`)
  },
  fetchSourceFiles(storeIdentifier) {
    return http.post('/api/v1/tobacco-license/source-files/from-starrocks', {
      store_identifier: storeIdentifier,
    }, {
      timeout: 120000,
    })
  },
  fetchSourceFile(relativePath, download = false) {
    const encodedPath = relativePath
      .split('/')
      .map((part) => encodeURIComponent(part))
      .join('/')
    return http.get(`/api/v1/tobacco-license/source-files/local/${encodedPath}`, {
      params: download ? { download: 1 } : undefined,
      responseType: 'blob',
      timeout: 120000,
    })
  },
  getPendingStores() {
    return http.get('/api/v1/tobacco-license-consistency/pending-stores')
  },
  createConsistencyReview(storeIdentifier, payload = {}) {
    return http.post('/api/v1/tobacco-license-consistency/reviews', {
      store_identifier: storeIdentifier,
      ...payload,
    }, {
      timeout: 180000,
    })
  },
  manualReview(taskId, decision, comment = '') {
    return http.post(`/api/v1/tobacco-license-consistency/reviews/${taskId}/manual-review`, {
      decision,
      comment,
    })
  },
}

export const contractApi = {
  list(params) {
    return http.get('/api/contract/reports', { params })
  },
  detail(id) {
    return http.get(`/api/contract/reports/${id}`)
  },
}

export default { authApi, queryApi, dashboardApi, adminApi, reviewApi, tobaccoApi, contractApi }
