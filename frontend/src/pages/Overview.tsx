/**
 * Overview Dashboard — the main landing page.
 * Shows KPI cards, spending chart, recent transactions, and health score.
 */
import { useQuery } from '@tanstack/react-query'
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell
} from 'recharts'
import { DollarSign, TrendingUp, ShieldCheck, Zap, RefreshCw } from 'lucide-react'
import { mlApi, txApi, recsApi } from '@/api/client'
import { StatCard } from '@/components/StatCard'
import { useAuthStore } from '@/hooks/useAuth'
import { clsx } from 'clsx'

const COLORS = ['#6366f1', '#10b981', '#f59e0b', '#ef4444', '#8b5cf6', '#14b8a6']

const RISK_CONFIG: Record<string, { label: string; color: string; bg: string }> = {
  low: { label: 'Low Risk', color: 'text-emerald-400', bg: 'bg-emerald-500/20' },
  medium: { label: 'Moderate Risk', color: 'text-amber-400', bg: 'bg-amber-500/20' },
  high: { label: 'High Risk', color: 'text-orange-400', bg: 'bg-orange-500/20' },
  critical: { label: 'Critical Risk', color: 'text-red-400', bg: 'bg-red-500/20' },
}

export default function OverviewPage() {
  const { user } = useAuthStore()

  const { data: features, isLoading: featLoading } = useQuery({
    queryKey: ['features'],
    queryFn: () => mlApi.features().then((r) => r.data),
    retry: 1,
  })

  const { data: transactions, isLoading: txLoading } = useQuery({
    queryKey: ['transactions', { page: 1, page_size: 10 }],
    queryFn: () => txApi.list({ page: 1, page_size: 10 }).then((r) => r.data),
  })

  const { data: risk } = useQuery({
    queryKey: ['risk'],
    queryFn: () => mlApi.risk().then((r) => r.data),
  })

  const { data: recs } = useQuery({
    queryKey: ['recommendations'],
    queryFn: () => recsApi.list().then((r) => r.data),
  })

  const { data: forecasts } = useQuery({
    queryKey: ['forecasts', 30],
    queryFn: () => mlApi.forecasts(30).then((r) => r.data),
  })

  // Transform forecast for chart
  const forecastData = forecasts?.total?.slice(0, 30).map((p) => ({
    date: p.date.slice(5), // MM-DD
    predicted: p.predicted,
    lower: p.lower_80,
    upper: p.upper_80,
  })) ?? []

  // Category pie data
  const categoryData = Object.entries(features?.spend_by_category ?? {})
    .sort(([, a], [, b]) => b - a)
    .slice(0, 6)
    .map(([name, value]) => ({ name: name.replace('_', ' '), value: Math.round(value) }))

  const riskCfg = RISK_CONFIG[risk?.risk_level ?? 'low']
  const healthScore = features?.financial_health_score ?? null

  return (
    <div className="space-y-8 animate-fade-in">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">
            Good {getGreeting()},{' '}
            <span className="text-gradient">{user?.full_name?.split(' ')[0]}</span>
          </h1>
          <p className="text-gray-400 mt-1">Here's your financial health snapshot</p>
        </div>
        <button
          onClick={() => mlApi.refreshFeatures()}
          className="flex items-center gap-2 px-4 py-2 glass rounded-lg text-sm text-gray-400 hover:text-white glass-hover transition-all"
        >
          <RefreshCw className="h-4 w-4" />
          Refresh
        </button>
      </div>

      {/* KPI Cards */}
      <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-4 gap-4">
        <StatCard
          title="Monthly Spending"
          value={features ? `$${features.avg_monthly_spend?.toLocaleString() ?? '—'}` : '—'}
          subtitle="30-day average"
          trend={features && features.spend_volatility && features.spend_volatility > 0.3 ? 'up' : 'neutral'}
          trendValue={features?.spend_volatility ? `${(features.spend_volatility * 100).toFixed(0)}% volatility` : undefined}
          icon={<DollarSign className="h-4 w-4" />}
          color="brand"
          loading={featLoading}
        />
        <StatCard
          title="Monthly Income"
          value={features ? `$${features.avg_monthly_income?.toLocaleString() ?? '—'}` : '—'}
          subtitle="Average inflow"
          icon={<TrendingUp className="h-4 w-4" />}
          color="success"
          loading={featLoading}
        />
        <StatCard
          title="Health Score"
          value={healthScore !== null ? `${healthScore}/100` : '—'}
          subtitle={healthScore && healthScore > 70 ? '✨ Healthy finances' : healthScore && healthScore > 40 ? '⚠️ Room to improve' : '🚨 Needs attention'}
          icon={<ShieldCheck className="h-4 w-4" />}
          color={healthScore && healthScore > 70 ? 'success' : healthScore && healthScore > 40 ? 'warning' : 'danger'}
          loading={featLoading}
        />
        <StatCard
          title="Savings Rate"
          value={features?.savings_rate !== null && features?.savings_rate !== undefined ? `${(features.savings_rate * 100).toFixed(1)}%` : '—'}
          subtitle="Income saved monthly"
          icon={<Zap className="h-4 w-4" />}
          color={features && features.savings_rate && features.savings_rate > 0.15 ? 'success' : 'warning'}
          loading={featLoading}
        />
      </div>

      {/* Charts Row */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Forecast Chart */}
        <div className="xl:col-span-2 card">
          <h2 className="text-lg font-semibold text-white mb-6">30-Day Spending Forecast</h2>
          {forecastData.length > 0 ? (
            <ResponsiveContainer width="100%" height={240}>
              <AreaChart data={forecastData}>
                <defs>
                  <linearGradient id="forecastGrad" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="5%" stopColor="#6366f1" stopOpacity={0.3} />
                    <stop offset="95%" stopColor="#6366f1" stopOpacity={0} />
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" />
                <XAxis dataKey="date" tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
                <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} />
                <Tooltip
                  contentStyle={{ background: '#1f2937', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' }}
                  formatter={(v: number) => [`$${v.toFixed(2)}`, 'Predicted']}
                />
                <Area type="monotone" dataKey="upper" stroke="none" fill="rgba(99,102,241,0.1)" />
                <Area type="monotone" dataKey="predicted" stroke="#6366f1" strokeWidth={2} fill="url(#forecastGrad)" />
                <Area type="monotone" dataKey="lower" stroke="none" fill="rgba(99,102,241,0.05)" />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <div className="h-60 flex items-center justify-center text-gray-500">
              Upload transactions to generate forecasts
            </div>
          )}
        </div>

        {/* Category Pie */}
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-6">Spend by Category</h2>
          {categoryData.length > 0 ? (
            <>
              <ResponsiveContainer width="100%" height={180}>
                <PieChart>
                  <Pie data={categoryData} cx="50%" cy="50%" innerRadius={50} outerRadius={80}
                    dataKey="value" paddingAngle={2}>
                    {categoryData.map((_, i) => (
                      <Cell key={i} fill={COLORS[i % COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{ background: '#1f2937', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' }}
                    formatter={(v: number) => [`$${v}`, '']}
                  />
                </PieChart>
              </ResponsiveContainer>
              <div className="space-y-2 mt-2">
                {categoryData.map((item, i) => (
                  <div key={item.name} className="flex items-center justify-between text-sm">
                    <div className="flex items-center gap-2">
                      <div className="w-2 h-2 rounded-full" style={{ background: COLORS[i % COLORS.length] }} />
                      <span className="text-gray-400 capitalize">{item.name}</span>
                    </div>
                    <span className="text-white font-medium">${item.value}</span>
                  </div>
                ))}
              </div>
            </>
          ) : (
            <div className="h-60 flex items-center justify-center text-gray-500 text-sm text-center">
              No category data yet.<br />Upload a bank statement.
            </div>
          )}
        </div>
      </div>

      {/* Bottom Row */}
      <div className="grid grid-cols-1 xl:grid-cols-3 gap-6">
        {/* Recent Transactions */}
        <div className="xl:col-span-2 card">
          <h2 className="text-lg font-semibold text-white mb-4">Recent Transactions</h2>
          {txLoading ? (
            <div className="space-y-3">
              {[...Array(5)].map((_, i) => (
                <div key={i} className="flex justify-between items-center">
                  <div className="h-4 w-40 skeleton rounded" />
                  <div className="h-4 w-16 skeleton rounded" />
                </div>
              ))}
            </div>
          ) : transactions?.items.length ? (
            <div className="space-y-1">
              {transactions.items.map((tx) => (
                <div key={tx.id} className="flex items-center justify-between py-2.5 px-3 rounded-lg hover:bg-white/5 transition-colors">
                  <div className="flex items-center gap-3">
                    {tx.is_anomaly && (
                      <span className="w-2 h-2 rounded-full bg-red-400 flex-shrink-0" title="Anomaly detected" />
                    )}
                    <div>
                      <p className="text-sm text-white font-medium truncate max-w-[200px]">
                        {tx.merchant_name || tx.description}
                      </p>
                      <p className="text-xs text-gray-500">{tx.transaction_date.slice(0, 10)} · {tx.category?.replace('_', ' ') ?? 'Uncategorized'}</p>
                    </div>
                  </div>
                  <span className={clsx('text-sm font-semibold',
                    tx.transaction_type === 'credit' ? 'text-emerald-400' : 'text-white'
                  )}>
                    {tx.transaction_type === 'credit' ? '+' : '-'}${Number(tx.amount_raw).toFixed(2)}
                  </span>
                </div>
              ))}
            </div>
          ) : (
            <p className="text-gray-500 text-sm py-8 text-center">No transactions yet. Upload a bank statement to get started.</p>
          )}
        </div>

        {/* Risk + Recommendations */}
        <div className="space-y-4">
          {/* Risk Panel */}
          <div className="card">
            <h2 className="text-lg font-semibold text-white mb-3">Risk Assessment</h2>
            {risk ? (
              <>
                <div className={clsx('inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm font-medium mb-3', riskCfg.bg, riskCfg.color)}>
                  <ShieldCheck className="h-4 w-4" />
                  {riskCfg.label}
                </div>
                <div className="mb-3">
                  <div className="flex justify-between text-xs text-gray-500 mb-1">
                    <span>Risk Score</span>
                    <span>{(risk.risk_score * 100).toFixed(0)}%</span>
                  </div>
                  <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
                    <div
                      className={clsx('h-full rounded-full transition-all duration-700',
                        risk.risk_level === 'low' ? 'bg-emerald-400' :
                        risk.risk_level === 'medium' ? 'bg-amber-400' :
                        risk.risk_level === 'high' ? 'bg-orange-400' : 'bg-red-400'
                      )}
                      style={{ width: `${risk.risk_score * 100}%` }}
                    />
                  </div>
                </div>
                {risk.top_risk_factors.length > 0 && (
                  <ul className="space-y-1">
                    {risk.top_risk_factors.map((f, i) => (
                      <li key={i} className="text-xs text-gray-400 flex items-start gap-2">
                        <span className="text-orange-400 mt-0.5">•</span>
                        {f}
                      </li>
                    ))}
                  </ul>
                )}
              </>
            ) : (
              <div className="h-20 skeleton rounded" />
            )}
          </div>

          {/* Top Recommendation */}
          {recs?.[0] && (
            <div className="card bg-gradient-to-br from-brand-500/10 to-violet-500/10 border-brand-500/20">
              <div className="flex items-start gap-3">
                <div className="p-2 bg-brand-500/20 rounded-lg flex-shrink-0">
                  <Zap className="h-4 w-4 text-brand-400" />
                </div>
                <div>
                  <p className="text-sm font-semibold text-white mb-1">{recs[0].title}</p>
                  <p className="text-xs text-gray-400 leading-relaxed">{recs[0].body}</p>
                  {recs[0].potential_savings && (
                    <p className="text-xs text-emerald-400 mt-2 font-medium">
                      💰 Save up to ${recs[0].potential_savings.toFixed(0)}/year
                    </p>
                  )}
                </div>
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

function getGreeting(): string {
  const h = new Date().getHours()
  if (h < 12) return 'morning'
  if (h < 17) return 'afternoon'
  return 'evening'
}
