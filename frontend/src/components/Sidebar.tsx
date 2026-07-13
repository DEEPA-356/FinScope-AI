/** Sidebar navigation component */
import { NavLink, useNavigate } from 'react-router-dom'
import {
  LayoutDashboard, TrendingUp, CreditCard, Target, Bell,
  MessageCircle, Settings, LogOut, ShieldAlert, BarChart3,
  Sparkles, ChevronRight
} from 'lucide-react'
import { clsx } from 'clsx'
import { useAuthStore } from '@/hooks/useAuth'
import { alertsApi } from '@/api/client'
import { useQuery } from '@tanstack/react-query'

const navItems = [
  { to: '/', label: 'Overview', icon: LayoutDashboard, exact: true },
  { to: '/spending', label: 'Spending', icon: CreditCard },
  { to: '/forecasts', label: 'Forecasts', icon: TrendingUp },
  { to: '/clusters', label: 'Segments', icon: BarChart3 },
  { to: '/recommendations', label: 'Recommendations', icon: Sparkles },
  { to: '/goals', label: 'Goals', icon: Target },
  { to: '/assistant', label: 'AI Assistant', icon: MessageCircle },
]

const adminItems = [
  { to: '/admin', label: 'Admin Console', icon: ShieldAlert },
]

const bottomItems = [
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Sidebar() {
  const { user, logout } = useAuthStore()
  const navigate = useNavigate()

  const { data: alerts } = useQuery({
    queryKey: ['alerts'],
    queryFn: () => alertsApi.list().then((r) => r.data),
    refetchInterval: 60_000,
  })
  const unreadAlerts = alerts?.filter((a) => a.status !== 'dismissed').length ?? 0

  const handleLogout = async () => {
    const refreshToken = localStorage.getItem('refresh_token')
    if (refreshToken) {
      try { await alertsApi } catch {}
    }
    logout()
    navigate('/login')
  }

  return (
    <aside className="fixed inset-y-0 left-0 z-50 w-64 flex flex-col glass border-r border-white/10">
      {/* Logo */}
      <div className="h-16 flex items-center px-6 border-b border-white/10">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-brand-400 to-violet-500 flex items-center justify-center">
            <span className="text-white font-bold text-sm">F</span>
          </div>
          <span className="font-bold text-lg text-gradient">FinScope AI</span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 px-3 py-4 overflow-y-auto space-y-1">
        {navItems.map((item) => (
          <NavItem key={item.to} {...item} />
        ))}

        {unreadAlerts > 0 && (
          <NavLink to="/alerts" className="relative flex items-center gap-3 px-3 py-2.5 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-all duration-150 text-sm font-medium group">
            <Bell className="h-4 w-4" />
            <span>Alerts</span>
            <span className="ml-auto bg-red-500 text-white text-xs rounded-full w-5 h-5 flex items-center justify-center">
              {unreadAlerts > 9 ? '9+' : unreadAlerts}
            </span>
          </NavLink>
        )}

        {user?.role === 'admin' && (
          <>
            <div className="pt-4 pb-1 px-3">
              <p className="text-xs text-gray-600 uppercase tracking-wider">Admin</p>
            </div>
            {adminItems.map((item) => (
              <NavItem key={item.to} {...item} />
            ))}
          </>
        )}
      </nav>

      {/* User section */}
      <div className="border-t border-white/10 p-3 space-y-1">
        {bottomItems.map((item) => (
          <NavItem key={item.to} {...item} />
        ))}
        <button
          onClick={handleLogout}
          className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-gray-400 hover:text-red-400 hover:bg-red-500/10 transition-all duration-150 text-sm font-medium"
        >
          <LogOut className="h-4 w-4" />
          <span>Sign Out</span>
        </button>

        {/* User avatar */}
        <div className="flex items-center gap-3 px-3 py-2 mt-2">
          <div className="w-8 h-8 rounded-full bg-gradient-to-br from-brand-400 to-violet-500 flex items-center justify-center flex-shrink-0">
            <span className="text-white text-xs font-bold">
              {user?.full_name?.charAt(0)?.toUpperCase() ?? 'U'}
            </span>
          </div>
          <div className="flex-1 min-w-0">
            <p className="text-sm font-medium text-white truncate">{user?.full_name}</p>
            <p className="text-xs text-gray-500 truncate">{user?.email}</p>
          </div>
        </div>
      </div>
    </aside>
  )
}

function NavItem({ to, label, icon: Icon, exact }: { to: string; label: string; icon: React.ElementType; exact?: boolean }) {
  return (
    <NavLink
      to={to}
      end={exact}
      className={({ isActive }) => clsx(
        'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-all duration-150 group',
        isActive
          ? 'bg-brand-500/20 text-brand-300 border border-brand-500/30'
          : 'text-gray-400 hover:text-white hover:bg-white/10'
      )}
    >
      <Icon className="h-4 w-4" />
      <span>{label}</span>
      <ChevronRight className="h-3 w-3 ml-auto opacity-0 group-hover:opacity-100 transition-opacity" />
    </NavLink>
  )
}
