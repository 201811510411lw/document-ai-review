import axios from 'axios'
import { apiErrorInfo } from './errors.js'

const http = axios.create({
  baseURL: '/',
  timeout: 30000,
})

http.interceptors.request.use((config) => {
  const token = localStorage.getItem('auth_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

http.interceptors.response.use(
  (res) => res.data,
  (err) => {
    const info = apiErrorInfo(err)
    const normalizedError = new Error(info.message)
    normalizedError.code = info.code
    normalizedError.status = info.status
    return Promise.reject(normalizedError)
  }
)

export default http
