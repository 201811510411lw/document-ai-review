import http from './http'

export const authApi = {
  login(code) {
    return http.post('/auth/login', { code })
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
  checkExpiry() {
    return http.post('/api/admin/check-expiry')
  },
  getRecords(params) {
    return http.get('/api/records', { params })
  },
  deleteRecord(id) {
    return http.delete(`/api/records/${id}`)
  },
}

export const reviewApi = {
  list(params) {
    return http.get('/api/review/list', { params })
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
