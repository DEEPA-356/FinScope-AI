/** Spending Analysis page with filterable transaction table */
import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { Search, Filter, Upload, AlertTriangle } from 'lucide-react'
import { txApi, mlApi } from '@/api/client'
import { clsx } from 'clsx'

const COLORS = ['#6366f1','#10b981','#f59e0b','#ef4444','#8b5cf6','#14b8a6','#ec4899','#f97316']

export default function SpendingPage() {
  const [search, setSearch] = useState('')
  const [anomalyOnly, setAnomalyOnly] = useState(false)
  const [page, setPage] = useState(1)

  const { data: txList, isLoading } = useQuery({
    queryKey: ['transactions', { page, search, is_anomaly: anomalyOnly || undefined }],
    queryFn: () => txApi.list({ page, page_size: 20, search: search || undefined, is_anomaly: anomalyOnly || undefined }).then((r) => r.data),
  })

  const { data: features } = useQuery({
    queryKey: ['features'],
    queryFn: () => mlApi.features().then((r) => r.data),
  })

  const categoryData = Object.entries(features?.spend_by_category ?? {})
    .map(([name, value]) => ({ name: name.replace('_', ' '), value: Math.round(value as number) }))
    .sort((a, b) => b.value - a.value)

  return (
    <div className="space-y-8 animate-fade-in">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-3xl font-bold text-white">Spending Analysis</h1>
          <p className="text-gray-400 mt-1">Explore and filter your transaction history</p>
        </div>
        <button className="flex items-center gap-2 px-4 py-2 bg-brand-500/20 border border-brand-500/30 rounded-lg text-brand-300 text-sm hover:bg-brand-500/30 transition-all">
          <Upload className="h-4 w-4" />
          Upload Statement
        </button>
      </div>

      {/* Category Bar Chart */}
      {categoryData.length > 0 && (
        <div className="card">
          <h2 className="text-lg font-semibold text-white mb-6">30-Day Spend by Category</h2>
          <ResponsiveContainer width="100%" height={220}>
            <BarChart data={categoryData} barSize={32}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.05)" vertical={false} />
              <XAxis dataKey="name" tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} />
              <YAxis tick={{ fill: '#6b7280', fontSize: 11 }} axisLine={false} tickLine={false} tickFormatter={(v) => `$${v}`} />
              <Tooltip
                contentStyle={{ background: '#1f2937', border: '1px solid rgba(255,255,255,0.1)', borderRadius: '8px', color: '#fff' }}
                formatter={(v: number) => [`$${v}`, 'Spend']}
              />
              <Bar dataKey="value" radius={[4, 4, 0, 0]}>
                {categoryData.map((_, i) => (
                  <Cell key={i} fill={COLORS[i % COLORS.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-500" />
          <input
            type="text"
            value={search}
            onChange={(e) => { setSearch(e.target.value); setPage(1) }}
            placeholder="Search transactions..."
            className="w-full bg-white/5 border border-white/10 rounded-lg pl-10 pr-4 py-2.5 text-white placeholder-gray-600 focus:outline-none focus:border-brand-500 transition-colors text-sm"
          />
        </div>
        <button
          onClick={() => { setAnomalyOnly(!anomalyOnly); setPage(1) }}
          className={clsx('flex items-center gap-2 px-4 py-2.5 rounded-lg text-sm font-medium transition-all',
            anomalyOnly ? 'bg-red-500/20 border border-red-500/30 text-red-300' : 'glass glass-hover text-gray-400'
          )}
        >
          <AlertTriangle className="h-4 w-4" />
          Anomalies Only
        </button>
      </div>

      {/* Transaction Table */}
      <div className="card overflow-hidden p-0">
        <table className="w-full">
          <thead>
            <tr className="border-b border-white/10">
              {['Date', 'Description', 'Category', 'Amount', 'Status'].map((h) => (
                <th key={h} className="text-left text-xs font-medium text-gray-500 uppercase tracking-wider px-6 py-4">{h}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-white/5">
            {isLoading ? (
              [...Array(5)].map((_, i) => (
                <tr key={i}>
                  {[...Array(5)].map((_, j) => (
                    <td key={j} className="px-6 py-4">
                      <div className="h-4 skeleton rounded w-24" />
                    </td>
                  ))}
                </tr>
              ))
            ) : txList?.items.map((tx) => (
              <tr key={tx.id} className="hover:bg-white/5 transition-colors">
                <td className="px-6 py-4 text-sm text-gray-400 whitespace-nowrap">{tx.transaction_date.slice(0, 10)}</td>
                <td className="px-6 py-4">
                  <p className="text-sm text-white font-medium truncate max-w-[200px]">{tx.merchant_name || tx.description}</p>
                  <p className="text-xs text-gray-600 truncate max-w-[200px]">{tx.description}</p>
                </td>
                <td className="px-6 py-4">
                  <span className="text-xs px-2 py-1 bg-white/10 rounded-full text-gray-400 capitalize">
                    {tx.category?.replace('_', ' ') ?? 'Uncategorized'}
                  </span>
                </td>
                <td className={clsx('px-6 py-4 text-sm font-semibold', tx.transaction_type === 'credit' ? 'text-emerald-400' : 'text-white')}>
                  {tx.transaction_type === 'credit' ? '+' : '-'}${Number(tx.amount_raw).toFixed(2)}
                </td>
                <td className="px-6 py-4">
                  {tx.is_anomaly ? (
                    <span className="flex items-center gap-1 text-xs text-red-400 bg-red-500/10 border border-red-500/20 px-2 py-1 rounded-full">
                      <AlertTriangle className="h-3 w-3" />
                      Anomaly
                    </span>
                  ) : (
                    <span className="text-xs text-gray-600">Normal</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Pagination */}
        {txList && txList.total_pages > 1 && (
          <div className="flex items-center justify-between px-6 py-4 border-t border-white/10">
            <p className="text-sm text-gray-500">
              {txList.total} transactions · Page {txList.page} of {txList.total_pages}
            </p>
            <div className="flex gap-2">
              <button onClick={() => setPage(Math.max(1, page - 1))} disabled={page === 1}
                className="px-3 py-1.5 glass rounded text-sm text-gray-400 disabled:opacity-40 hover:text-white glass-hover transition-all">
                Previous
              </button>
              <button onClick={() => setPage(Math.min(txList.total_pages, page + 1))} disabled={page === txList.total_pages}
                className="px-3 py-1.5 glass rounded text-sm text-gray-400 disabled:opacity-40 hover:text-white glass-hover transition-all">
                Next
              </button>
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
