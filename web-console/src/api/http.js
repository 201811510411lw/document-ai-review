import axios from 'axios'
import { apiErrorMessage } from './errors.js'

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
    return Promise.reject(new Error(apiErrorMessage(err)))
  }
)

export default http
