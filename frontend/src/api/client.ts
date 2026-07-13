/**
 * Typed API client — all backend communication goes through here.
 * Uses axios with interceptors for JWT token injection and refresh.
 */

import axios, { type AxiosInstance, type AxiosResponse } from 'axios'

// Default to empty string so requests are relative (e.g., /api/v1/...)
// This is required for Vercel where frontend and backend share the same domain.
const BASE_URL = import.meta.env.VITE_API_BASE_URL ?? ''

// ── Axios instance ─────────────────────────────────────────────────────────

const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: { 'Content-Type': 'application/json' },
})

// ── Request interceptor — inject JWT ──────────────────────────────────────

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) {
    config.headers.Authorization = `Bearer ${token}`
  }
  return config
})

// ── Response interceptor — handle 401 with token refresh ─────────────────

let isRefreshing = false
let failedQueue: Array<{ resolve: (v: string) => void; reject: (e: unknown) => void }> = []

api.interceptors.response.use(
  (response) => response,
  async (error) => {
    const original = error.config

    if (error.response?.status === 401 && !original._retry) {
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({ resolve, reject })
        }).then((token) => {
          original.headers.Authorization = `Bearer ${token}`
          return api(original)
        })
      }

      original._retry = true
      isRefreshing = true

      const refreshToken = localStorage.getItem('refresh_token')
      if (!refreshToken) {
        localStorage.clear()
        window.location.href = '/login'
        return Promise.reject(error)
      }

      try {
        const { data } = await axios.post(`${BASE_URL}/api/v1/auth/refresh`, {
          refresh_token: refreshToken,
        })
        localStorage.setItem('access_token', data.access_token)
        localStorage.setItem('refresh_token', data.refresh_token)
        failedQueue.forEach((q) => q.resolve(data.access_token))
        failedQueue = []
        original.headers.Authorization = `Bearer ${data.access_token}`
        return api(original)
      } catch {
        failedQueue.forEach((q) => q.reject(error))
        failedQueue = []
        localStorage.clear()
        window.location.href = '/login'
        return Promise.reject(error)
      } finally {
        isRefreshing = false
      }
    }

    return Promise.reject(error)
  },
)

// ── API functions ─────────────────────────────────────────────────────────

export interface LoginRequest { username: string; password: string }
export interface RegisterRequest { email: string; password: string; full_name: string }
export interface TokenResponse { access_token: string; refresh_token: string; token_type: string }
export interface UserProfile { id: string; email: string; full_name: string; role: string; base_currency: string }

export interface TransactionItem {
  id: string; account_id: string | null; transaction_date: string
  description: string; merchant_name: string | null
  amount_raw: number; currency_code: string; amount_usd: number | null
  transaction_type: string; category: string | null
  is_anomaly: boolean; anomaly_score: number | null; is_recurring: boolean
}

export interface TransactionList { items: TransactionItem[]; total: number; page: number; page_size: number; total_pages: number }

export interface UserFeatures {
  avg_monthly_spend: number | null; avg_monthly_income: number | null
  financial_health_score: number | null; savings_rate: number | null
  spend_volatility: number | null; clv_score: number | null
  risk_score: number | null; risk_level: string | null
  cluster_id: number | null; cluster_label: string | null
  spend_by_category: Record<string, number>
}

export interface ForecastPoint { date: string; predicted: number; lower_80: number; upper_80: number }
export interface ForecastResponse { total: ForecastPoint[]; by_category: Record<string, ForecastPoint[]> }
export interface RiskResponse { risk_score: number; risk_level: string; top_risk_factors: string[] }
export interface SegmentResponse { cluster_id: number; cluster_label: string; distance_to_centroid: number }
export interface Goal { id: string; title: string; goal_type: string; status: string; target_amount: number; current_amount: number; currency_code: string; progress_pct: number; target_date: string | null }
export interface Alert { id: string; alert_type: string; title: string; message: string; status: string; created_at: string }
export interface Recommendation { id: string; title: string; body: string; category: string; priority: number; potential_savings: number | null; is_viewed: boolean; is_acted_on: boolean }
export interface ChatResponse { answer: string; context_used: boolean; sources: string[]; timestamp: string }
export interface PlatformStats { total_users: number; active_users: number; total_transactions: number; flagged_transactions: number; avg_health_score: number | null; high_risk_users: number }
export interface CohortStat { cluster_label: string | null; user_count: number; avg_health_score: number | null; avg_monthly_spend: number | null }

// Auth
export const authApi = {
  login: (d: LoginRequest) => api.post<TokenResponse>('/api/v1/auth/login', null, { params: d }),
  loginForm: (username: string, password: string) => {
    const form = new FormData(); form.append('username', username); form.append('password', password)
    return api.post<TokenResponse>('/api/v1/auth/login', form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
  register: (d: RegisterRequest) => api.post<UserProfile>('/api/v1/auth/register', d),
  me: () => api.get<UserProfile>('/api/v1/auth/me'),
  logout: (refresh_token: string) => api.post('/api/v1/auth/logout', { refresh_token }),
}

// Transactions
export const txApi = {
  list: (params?: Record<string, unknown>) => api.get<TransactionList>('/api/v1/transactions', { params }),
  upload: (file: File, account_id: string) => {
    const form = new FormData(); form.append('file', file)
    return api.post<unknown>(`/api/v1/transactions/upload?account_id=${account_id}`, form, { headers: { 'Content-Type': 'multipart/form-data' } })
  },
}

// ML
export const mlApi = {
  features: () => api.get<UserFeatures>('/api/v1/ml/features'),
  refreshFeatures: () => api.post<UserFeatures>('/api/v1/ml/features/refresh'),
  risk: () => api.get<RiskResponse>('/api/v1/ml/risk'),
  clv: () => api.get<{ clv_score: number; churn_probability: number }>('/api/v1/ml/clv'),
  segment: () => api.get<SegmentResponse>('/api/v1/ml/segment'),
  forecasts: (horizon?: number) => api.get<ForecastResponse>('/api/v1/ml/forecasts', { params: { horizon_days: horizon } }),
  explainRisk: () => api.get<unknown>('/api/v1/explain/risk'),
}

// Goals
export const goalsApi = {
  list: () => api.get<Goal[]>('/api/v1/goals'),
  create: (d: Partial<Goal>) => api.post<Goal>('/api/v1/goals', d),
  update: (id: string, d: Partial<Goal>) => api.patch<Goal>(`/api/v1/goals/${id}`, d),
  delete: (id: string) => api.delete(`/api/v1/goals/${id}`),
}

// Alerts
export const alertsApi = {
  list: () => api.get<Alert[]>('/api/v1/alerts'),
  dismiss: (id: string) => api.post(`/api/v1/alerts/${id}/dismiss`),
}

// Recommendations
export const recsApi = {
  list: () => api.get<Recommendation[]>('/api/v1/recommendations'),
  act: (id: string) => api.post(`/api/v1/recommendations/${id}/act`),
  dismiss: (id: string) => api.post(`/api/v1/recommendations/${id}/dismiss`),
}

// Chat
export const chatApi = {
  send: (message: string) => api.post<ChatResponse>('/api/v1/chat/message', { message }),
}

// Admin
export const adminApi = {
  stats: () => api.get<PlatformStats>('/api/v1/admin/stats'),
  cohorts: () => api.get<CohortStat[]>('/api/v1/admin/cohorts'),
}

export default api
