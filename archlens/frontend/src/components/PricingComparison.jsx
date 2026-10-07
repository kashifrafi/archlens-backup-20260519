import { useEffect, useState } from 'react'
import axios from 'axios'
import toast from 'react-hot-toast'
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, Legend, ResponsiveContainer
} from 'recharts'
import { exportPricingToExcel } from '../lib/exporters'

const CLOUD_META = {
  aws: { label: 'AWS', color: '#f97316', bg: 'bg-orange-500/20', border: 'border-orange-500/30', text: 'text-orange-400' },
  azure: { label: 'Azure', color: '#3b82f6', bg: 'bg-blue-500/20', border: 'border-blue-500/30', text: 'text-blue-400' },
  gcp: { label: 'GCP', color: '#22c55e', bg: 'bg-green-500/20', border: 'border-green-500/30', text: 'text-green-400' },
}

const CustomTooltip = ({ active, payload, label }) => {
  if (active && payload?.length) {
    return (
      <div className="bg-gray-900 border border-gray-700 rounded-lg p-3 text-sm">
        <p className="font-semibold text-white mb-1">{label}</p>
        {payload.map((p) => (
          <p key={p.dataKey} style={{ color: p.color }}>
            {p.name}: ${p.value?.toLocaleString()}
          </p>
        ))}
      </div>
    )
  }
  return null
}

function PricingCard({ estimate, isWinner }) {
  const meta = CLOUD_META[estimate.cloud]
  const [showBreakdown, setShowBreakdown] = useState(false)
  return (
    <div className={`card border ${meta.border} relative`}>
      {isWinner && (
        <div className="absolute -top-3 left-1/2 -translate-x-1/2 bg-green-500 text-white text-xs font-bold px-3 py-1 rounded-full">
          🏆 Best Price
        </div>
      )}
      <div className="flex items-start justify-between mb-3">
        <div>
          <h3 className={`text-lg font-bold ${meta.text}`}>{meta.label}</h3>
          <p className="text-xs text-gray-500">{estimate.region}</p>
        </div>
        <div className="text-right">
          <div className={`text-2xl font-bold ${meta.text}`}>
            ${estimate.monthly_estimate.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}
            <span className="text-sm font-normal text-gray-500">/mo</span>
          </div>
          <div className="text-xs text-gray-500">
            ${estimate.annual_estimate.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 0 })}/yr
          </div>
        </div>
      </div>

      {/* Top services */}
      <div className="space-y-1 mb-3">
        {estimate.breakdown.slice(0, 5).map((item, i) => (
          <div key={i} className="flex justify-between text-xs">
            <span className="text-gray-400 truncate max-w-[60%]">{item.service}</span>
            <span className="text-gray-300">${item.monthly_cost.toFixed(0)}/mo</span>
          </div>
        ))}
      </div>

      <button
        onClick={() => setShowBreakdown(!showBreakdown)}
        className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
      >
        {showBreakdown ? '▲ Hide' : `▼ Full breakdown (${estimate.breakdown.length} services)`}
      </button>

      {showBreakdown && (
        <div className="mt-3 overflow-x-auto">
          <table className="w-full text-xs">
            <thead>
              <tr className="text-gray-500 border-b border-gray-800">
                <th className="text-left py-1">Service</th>
                <th className="text-left py-1">Component</th>
                <th className="text-right py-1">Qty</th>
                <th className="text-right py-1">Unit $</th>
                <th className="text-right py-1">Monthly</th>
              </tr>
            </thead>
            <tbody>
              {estimate.breakdown.map((item, i) => (
                <tr key={i} className="border-b border-gray-800/50 text-gray-400">
                  <td className="py-1">{item.service}</td>
                  <td className="py-1 text-gray-500">{item.component}</td>
                  <td className="py-1 text-right">{item.quantity}</td>
                  <td className="py-1 text-right">${item.unit_price.toFixed(4)}</td>
                  <td className="py-1 text-right">${item.monthly_cost.toFixed(2)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {estimate.assumptions?.length > 0 && (
        <div className="mt-3 pt-3 border-t border-gray-800">
          <p className="text-xs text-gray-500 font-medium mb-1">Assumptions</p>
          <ul className="text-xs text-gray-600 space-y-0.5">
            {estimate.assumptions.map((a, i) => <li key={i}>• {a}</li>)}
          </ul>
        </div>
      )}
    </div>
  )
}

const REGION_DEFAULTS = { aws: 'us-east-1', azure: 'eastus', gcp: 'us-central1' }
const REGION_EXAMPLES = { aws: 'us-west-2, eu-west-1, ap-southeast-1', azure: 'westeurope, eastasia, uksouth', gcp: 'europe-west1, asia-east1, us-west1' }

export default function PricingComparison({ analysis, pricingData, onPricingLoaded, onNext, onBack, userContext }) {
  const [loading, setLoading] = useState(false)
  const [regions, setRegions] = useState({ aws: '', azure: '', gcp: '' })

  useEffect(() => {
    if (!pricingData) loadPricing()
  }, [])

  const loadPricing = async () => {
    setLoading(true)
    try {
      const regionPrefs = Object.fromEntries(Object.entries(regions).filter(([, v]) => v.trim()))
      const { data } = await axios.post('/api/pricing', {
        analysis,
        ...(Object.keys(regionPrefs).length > 0 ? { region_preferences: regionPrefs } : {}),
        ...(userContext && Object.keys(userContext).length > 0 ? { user_context: userContext } : {}),
      })
      onPricingLoaded(data)
      toast.success('Pricing comparison ready')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'Pricing estimation failed')
    } finally {
      setLoading(false)
    }
  }

  const chartData = pricingData
    ? [
        { name: 'Monthly', AWS: pricingData.aws?.monthly_estimate, Azure: pricingData.azure?.monthly_estimate, GCP: pricingData.gcp?.monthly_estimate },
        { name: 'Annual', AWS: pricingData.aws?.annual_estimate, Azure: pricingData.azure?.annual_estimate, GCP: pricingData.gcp?.annual_estimate },
      ]
    : []

  const estimates = pricingData
    ? [pricingData.aws, pricingData.azure, pricingData.gcp].filter(Boolean)
    : []

  return (
    <div>
      <div className="flex items-center justify-between mb-4">
        <div>
          <h2 className="text-2xl font-bold text-white">Pricing Comparison</h2>
          <p className="text-gray-400">Estimated monthly costs across AWS, Azure & GCP</p>
        </div>
        <div className="flex gap-2">
          <button onClick={loadPricing} disabled={loading} className="btn-secondary text-sm">
            {loading ? '⟳' : '↻ Refresh'}
          </button>
          {pricingData && (
            <button
              onClick={() => exportPricingToExcel(pricingData, analysis?.architecture_type)}
              className="btn-secondary text-sm"
              title="Download pricing comparison (Excel) — all 3 clouds"
            >
              ⬇ Excel
            </button>
          )}
        </div>
      </div>

      {/* Region selector */}
      <div className="card mb-6 bg-gray-900/60">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-3">
          Region Preferences
          <span className="ml-2 text-gray-600 font-normal normal-case">— leave blank to use defaults</span>
        </p>
        <div className="grid grid-cols-3 gap-3">
          {(['aws', 'azure', 'gcp']).map((cloud) => (
            <div key={cloud}>
              <label className={`block text-xs font-medium mb-1 ${CLOUD_META[cloud].text}`}>
                {CLOUD_META[cloud].label}
                <span className="ml-1 text-gray-600 font-normal">({REGION_DEFAULTS[cloud]})</span>
              </label>
              <input
                type="text"
                value={regions[cloud]}
                onChange={(e) => setRegions(r => ({ ...r, [cloud]: e.target.value }))}
                onKeyDown={(e) => e.key === 'Enter' && loadPricing()}
                placeholder={REGION_DEFAULTS[cloud]}
                title={`e.g. ${REGION_EXAMPLES[cloud]}`}
                className="w-full bg-gray-800 border border-gray-700 rounded-lg px-3 py-1.5 text-sm text-white placeholder-gray-600 focus:outline-none focus:border-blue-500 transition-colors"
              />
            </div>
          ))}
        </div>
      </div>

      {loading && (
        <div className="card text-center py-16">
          <div className="text-4xl mb-4 animate-pulse">💰</div>
          <p className="text-gray-400 font-medium">Estimating costs across all clouds...</p>
        </div>
      )}

      {pricingData && !loading && (
        <>
          {/* Recommendation banner */}
          {pricingData.recommendation && (
            <div className="bg-blue-500/10 border border-blue-500/30 rounded-xl p-4 mb-6 flex gap-3">
              <span className="text-2xl shrink-0">💡</span>
              <div>
                <p className="text-sm font-semibold text-blue-300 mb-0.5">AI Recommendation</p>
                <p className="text-sm text-gray-400">{pricingData.recommendation}</p>
              </div>
            </div>
          )}

          {/* Chart */}
          <div className="card mb-6">
            <h3 className="text-sm font-semibold text-gray-400 mb-4">Cost Overview (USD)</h3>
            <ResponsiveContainer width="100%" height={220}>
              <BarChart data={chartData} margin={{ top: 5, right: 10, left: 10, bottom: 5 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#374151" />
                <XAxis dataKey="name" tick={{ fill: '#9ca3af', fontSize: 12 }} />
                <YAxis tick={{ fill: '#9ca3af', fontSize: 12 }} tickFormatter={(v) => `$${(v / 1000).toFixed(0)}k`} />
                <Tooltip content={<CustomTooltip />} />
                <Legend wrapperStyle={{ fontSize: '12px', color: '#9ca3af' }} />
                <Bar dataKey="AWS" fill="#f97316" radius={[4, 4, 0, 0]} />
                <Bar dataKey="Azure" fill="#3b82f6" radius={[4, 4, 0, 0]} />
                <Bar dataKey="GCP" fill="#22c55e" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-6 mb-6">
            {estimates.map((est) => (
              <PricingCard
                key={est.cloud}
                estimate={est}
                isWinner={pricingData.cheapest === est.cloud}
              />
            ))}
          </div>
        </>
      )}

      <div className="flex gap-3 mt-4">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <button className="btn-primary flex-1" onClick={onNext} disabled={!pricingData}>
          Generate Terraform →
        </button>
      </div>
    </div>
  )
}
