import { BrowserRouter, Route, Routes, Navigate } from 'react-router-dom'
import { Toaster } from 'react-hot-toast'
import { lazy, Suspense } from 'react'
import { useAuthStore } from '@/hooks/useAuth'
import { AppLayout } from '@/components/AppLayout'

// Lazy-loaded pages
const Overview = lazy(() => import('@/pages/Overview'))
const Login = lazy(() => import('@/pages/Login'))
const Spending = lazy(() => import('@/pages/Spending'))
const Assistant = lazy(() => import('@/pages/Assistant'))

// Placeholder pages for phases not yet UI-built
const ComingSoon = ({ title }: { title: string }) => (
  <div className="flex flex-col items-center justify-center min-h-[60vh] gap-4 animate-fade-in">
    <div className="text-5xl">🚀</div>
    <h1 className="text-2xl font-bold text-gradient">{title}</h1>
    <p className="text-gray-400 text-sm">Full UI shipping in Phase 8</p>
  </div>
)

// Auth guard
function RequireAuth({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuthStore()
  if (!accessToken) return <Navigate to="/login" replace />
  return <>{children}</>
}

function PageLoader() {
  return (
    <div className="flex items-center justify-center h-full min-h-[60vh]">
      <div className="w-8 h-8 border-2 border-brand-500/30 border-t-brand-400 rounded-full animate-spin" />
    </div>
  )
}

export default function App() {
  return (
    <BrowserRouter>
      <Toaster
        position="top-right"
        toastOptions={{
          style: { background: '#1f2937', color: '#f9fafb', border: '1px solid rgba(255,255,255,0.1)' },
          success: { iconTheme: { primary: '#10b981', secondary: '#fff' } },
          error: { iconTheme: { primary: '#ef4444', secondary: '#fff' } },
        }}
      />
      <Suspense fallback={<PageLoader />}>
        <Routes>
          {/* Public */}
          <Route path="/login" element={<Login />} />
          <Route path="/register" element={<ComingSoon title="Create Account" />} />

          {/* Protected — wrapped in AppLayout (sidebar) */}
          <Route element={<RequireAuth><AppLayout /></RequireAuth>}>
            <Route path="/" element={<Overview />} />
            <Route path="/spending" element={<Spending />} />
            <Route path="/forecasts" element={<ComingSoon title="Spending Forecasts" />} />
            <Route path="/clusters" element={<ComingSoon title="Customer Segments" />} />
            <Route path="/recommendations" element={<ComingSoon title="Recommendations" />} />
            <Route path="/goals" element={<ComingSoon title="Financial Goals" />} />
            <Route path="/alerts" element={<ComingSoon title="Alerts" />} />
            <Route path="/assistant" element={<Assistant />} />
            <Route path="/admin" element={<ComingSoon title="Admin Console" />} />
            <Route path="/settings" element={<ComingSoon title="Settings" />} />
          </Route>

          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </Suspense>
    </BrowserRouter>
  )
}
