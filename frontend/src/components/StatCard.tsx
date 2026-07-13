/** Shared UI component: KPI stat card with trend indicator */
import { type ReactNode } from 'react'
import { TrendingUp, TrendingDown, Minus } from 'lucide-react'
import { clsx } from 'clsx'

interface StatCardProps {
  title: string
  value: string | number
  subtitle?: string
  trend?: 'up' | 'down' | 'neutral'
  trendValue?: string
  icon?: ReactNode
  color?: 'brand' | 'success' | 'warning' | 'danger'
  loading?: boolean
}

export function StatCard({ title, value, subtitle, trend, trendValue, icon, color = 'brand', loading }: StatCardProps) {
  const colorMap = {
    brand: 'from-brand-500/20 to-violet-500/20 border-brand-500/30',
    success: 'from-emerald-500/20 to-teal-500/20 border-emerald-500/30',
    warning: 'from-amber-500/20 to-orange-500/20 border-amber-500/30',
    danger: 'from-red-500/20 to-rose-500/20 border-red-500/30',
  }
  const iconColorMap = {
    brand: 'bg-brand-500/20 text-brand-400',
    success: 'bg-emerald-500/20 text-emerald-400',
    warning: 'bg-amber-500/20 text-amber-400',
    danger: 'bg-red-500/20 text-red-400',
  }

  if (loading) {
    return (
      <div className="card animate-pulse">
        <div className="h-4 w-24 skeleton rounded mb-3" />
        <div className="h-8 w-32 skeleton rounded mb-2" />
        <div className="h-3 w-20 skeleton rounded" />
      </div>
    )
  }

  return (
    <div className={clsx('card relative overflow-hidden bg-gradient-to-br border', colorMap[color], 'transition-all duration-200 hover:scale-[1.02] hover:shadow-lg')}>
      <div className="flex items-start justify-between mb-4">
        <p className="text-sm text-gray-400 font-medium">{title}</p>
        {icon && (
          <div className={clsx('p-2 rounded-lg', iconColorMap[color])}>
            {icon}
          </div>
        )}
      </div>
      <p className="text-3xl font-bold text-white mb-1 tracking-tight">{value}</p>
      {subtitle && <p className="text-xs text-gray-500">{subtitle}</p>}
      {trend && trendValue && (
        <div className={clsx('flex items-center gap-1 mt-3 text-xs font-medium',
          trend === 'up' ? 'text-emerald-400' : trend === 'down' ? 'text-red-400' : 'text-gray-400'
        )}>
          {trend === 'up' ? <TrendingUp className="h-3 w-3" /> : trend === 'down' ? <TrendingDown className="h-3 w-3" /> : <Minus className="h-3 w-3" />}
          {trendValue}
        </div>
      )}
    </div>
  )
}
