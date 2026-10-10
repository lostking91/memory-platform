import axios from 'axios'

const api = axios.create({ baseURL: '/api', timeout: 15000 })

export default {
  health: () => api.get('/health').then(r => r.data),
  overview: () => api.get('/overview').then(r => r.data),
  sources: (params) => api.get('/sources', { params }).then(r => r.data),
  sourceDetail: (id) => api.get(`/sources/${id}`).then(r => r.data),
  memories: (params) => api.get('/memories', { params }).then(r => r.data),
  memoryDetail: (id) => api.get(`/memories/${id}`).then(r => r.data)
}
