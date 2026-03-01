import axios from 'axios'
import { ElMessage } from 'element-plus'

const api = axios.create({
  baseURL: '/api',
  timeout: 180000,
  headers: {
    'Content-Type': 'application/json',
  },
})

// Response interceptor for unified error handling
api.interceptors.response.use(
  (response) => response.data,
  (error) => {
    const message =
      error.response?.data?.detail ||
      error.response?.data?.message ||
      error.message ||
      '请求失败，请稍后重试'
    ElMessage.error(message)
    return Promise.reject(error)
  }
)

// ---- Dashboard APIs ----

export function getSummary() {
  return api.get('/dashboard/summary')
}

export function getPlatformDistribution() {
  return api.get('/dashboard/platform-distribution')
}

export function getDailyPnl(params) {
  return api.get('/dashboard/daily-pnl', { params })
}

export function getTopHoldings(params) {
  return api.get('/dashboard/top-holdings', { params })
}

export function backfillPortfolioNav() {
  return api.post('/dashboard/backfill-portfolio-nav')
}

// ---- Holdings APIs ----

export function getHoldings(params) {
  return api.get('/holdings', { params })
}

export function getHoldingsByPlatform() {
  return api.get('/holdings/by-platform')
}

export function getPlatforms() {
  return api.get('/holdings/platforms')
}

export function updateHoldingCost(holdingId, costNav) {
  return api.patch(`/holdings/${holdingId}`, { cost_nav: costNav })
}

// ---- Fund APIs ----

export function getFundDetail(code) {
  return api.get(`/funds/${code}`)
}

export function getFundNavHistory(code, params) {
  return api.get(`/funds/${code}/nav-history`, { params })
}

// ---- Import APIs ----

export function uploadExcel(file) {
  const formData = new FormData()
  formData.append('file', file)
  return api.post('/imports/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
    timeout: 60000,
  })
}

export function getImportHistory() {
  return api.get('/imports/history')
}

export function getImportChanges(importId) {
  return api.get(`/imports/${importId}/changes`)
}

// ---- NAV APIs ----

export function refreshNav() {
  return api.post('/nav/refresh', null, { timeout: 180000 })
}

export function getNavStatus() {
  return api.get('/nav/status')
}

export function createSnapshot() {
  return api.post('/nav/snapshot')
}

export function backfillNavHistory() {
  return api.post('/nav/backfill-history', null, { timeout: 300000 })
}

export function backfillSnapshots() {
  return api.post('/nav/backfill-snapshots')
}

// ---- Analysis APIs ----

export function getAnalysisPeriods() {
  return api.get('/analysis/periods')
}

export function getPeriodDetail(params) {
  return api.get('/analysis/period-detail', { params })
}

export function getFundPnl(params) {
  return api.get('/analysis/fund-pnl', { params })
}

// ---- Calendar APIs ----

export function getCalendarMonth(params) {
  return api.get('/analysis/calendar', { params })
}

export function getCalendarDayDetail(date) {
  return api.get(`/analysis/calendar/${date}/detail`)
}

export default api
