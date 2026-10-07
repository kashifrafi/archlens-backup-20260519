import { useEffect, useState } from 'react'
import axios from 'axios'
import toast from 'react-hot-toast'
import { exportWAFToExcel } from '../lib/exporters'

const STATUS_CONFIG = {
  Excellent: { color: 'text-emerald-400', bg: 'bg-emerald-500', ring: '#10b981' },
  Good: { color: 'text-blue-400', bg: 'bg-blue-500', ring: '#3b82f6' },
  Fair: { color: 'text-yellow-400', bg: 'bg-yellow-500', ring: '#f59e0b' },
  Poor: { color: 'text-red-400', bg: 'bg-red-500', ring: '#ef4444' },
}

const CLOUD_META = {
  aws: { label: 'AWS', subtitle: 'Well-Architected Framework', emoji: '🟠', color: 'border-orange-500/40' },
  azure: { label: 'Azure', subtitle: 'Well-Architected Framework', emoji: '🔵', color: 'border-blue-500/40' },
  gcp: { label: 'GCP', subtitle: 'Architecture Framework', emoji: '🟢', color: 'border-green-500/40' },
}

function ScoreRing({ score, status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.Fair
  const circumference = 2 * Math.PI * 45
  const offset = circumference - (score / 100) * circumference
  return (
    <div className="relative w-28 h-28 shrink-0">
      <svg viewBox="0 0 100 100" className="w-full h-full -rotate-90">
        <circle cx="50" cy="50" r="45" fill="none" stroke="#374151" strokeWidth="8" />
        <circle
          cx="50" cy="50" r="45" fill="none"
          stroke={cfg.ring} strokeWidth="8"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          strokeLinecap="round"
          style={{ transition: 'stroke-dashoffset 1s ease' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className={`text-2xl font-bold ${cfg.color}`}>{score}</span>
        <span className={`text-xs ${cfg.color}`}>{status}</span>
      </div>
    </div>
  )
}

function PillarBar({ pillar, score, status }) {
  const cfg = STATUS_CONFIG[status] || STATUS_CONFIG.Fair
  return (
    <div>
      <div className="flex justify-between text-xs mb-1">
        <span className="text-gray-300 font-medium">{pillar}</span>
        <span className={cfg.color}>{score}/100</span>
      </div>
      <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-700 ${cfg.bg}`}
          style={{ width: `${score}%` }}
        />
      </div>
    </div>
  )
}

function WAFCard({ review }) {
  const meta = CLOUD_META[review.cloud] || {}
  const [expanded, setExpanded] = useState(null)

  return (
    <div className={`card border ${meta.color}`}>
      {/* Cloud header */}
      <div className="flex items-center gap-4 mb-5">
        <ScoreRing score={review.overall_score} status={review.overall_status} />
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-lg">{meta.emoji}</span>
            <h3 className="text-xl font-bold text-white">{meta.label}</h3>
          </div>
          <p className="text-xs text-gray-500 mb-2">{meta.subtitle}</p>
          <p className="text-sm text-gray-400">{review.summary}</p>
        </div>
      </div>

      {/* Pillar bars */}
      <div className="space-y-2 mb-5">
        {review.pillars.map((p) => (
          <PillarBar key={p.pillar} pillar={p.pillar} score={p.score} status={p.status} />
        ))}
      </div>

      {/* Critical gaps */}
      {review.critical_gaps?.length > 0 && (
        <div className="bg-red-500/10 border border-red-500/20 rounded-lg p-3 mb-4">
          <p className="text-xs font-semibold text-red-400 mb-1">Critical Gaps</p>
          <ul className="text-xs text-red-300 space-y-0.5 list-disc list-inside">
            {review.critical_gaps.map((g, i) => <li key={i}>{g}</li>)}
          </ul>
        </div>
      )}

      {/* Expandable pillars */}
      <div className="space-y-2">
        {review.pillars.map((p) => (
          <div key={p.pillar} className="border border-gray-800 rounded-lg overflow-hidden">
            <button
              className="w-full flex items-center justify-between px-4 py-2.5 text-left hover:bg-gray-800/50 transition-colors"
              onClick={() => setExpanded(expanded === p.pillar ? null : p.pillar)}
            >
              <div className="flex items-center gap-3">
                <span className={`text-xs font-bold ${STATUS_CONFIG[p.status]?.color || 'text-gray-400'}`}>
                  {p.score}
                </span>
                <span className="text-sm font-medium text-gray-300">{p.pillar}</span>
              </div>
              <span className="text-gray-500 text-xs">{expanded === p.pillar ? '▲' : '▼'}</span>
            </button>
            {expanded === p.pillar && (
              <div className="px-4 pb-4 pt-1 bg-gray-800/30">
                {p.findings.length > 0 && (
                  <div className="mb-3">
                    <p className="text-xs font-semibold text-yellow-400 mb-1">Findings</p>
                    <ul className="text-xs text-gray-400 space-y-0.5 list-disc list-inside">
                      {p.findings.map((f, i) => <li key={i}>{f}</li>)}
                    </ul>
                  </div>
                )}
                {p.recommendations.length > 0 && (
                  <div>
                    <p className="text-xs font-semibold text-blue-400 mb-1">Recommendations</p>
                    <ul className="text-xs text-gray-400 space-y-0.5 list-disc list-inside">
                      {p.recommendations.map((r, i) => <li key={i}>{r}</li>)}
                    </ul>
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}

export default function WAFReview({ analysis, wafData, onWafLoaded, onNext, onBack, userContext }) {
  const [loading, setLoading] = useState(false)
  const [activeCloud, setActiveCloud] = useState('aws')

  useEffect(() => {
    if (!wafData) loadWAF()
  }, [])

  const loadWAF = async () => {
    setLoading(true)
    try {
      const { data } = await axios.post('/api/waf-review', {
        analysis,
        clouds: ['aws', 'azure', 'gcp'],
        ...(userContext && Object.keys(userContext).length > 0 ? { user_context: userContext } : {}),
      })
      onWafLoaded(data)
      toast.success('WAF review complete')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'WAF review failed')
    } finally {
      setLoading(false)
    }
  }

  const activeReview = wafData?.find((r) => r.cloud === activeCloud)

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white">WAF Review</h2>
          <p className="text-gray-400">Well-Architected Framework assessment across all three clouds</p>
        </div>
        {wafData && (
          <div className="flex gap-2">
            <button onClick={loadWAF} disabled={loading} className="btn-secondary text-sm">
              {loading ? '⟳ Refreshing...' : '↻ Refresh'}
            </button>
            <button
              onClick={() => exportWAFToExcel(wafData, analysis?.architecture_type)}
              className="btn-secondary text-sm"
              title="Download WAF report (Excel) — all 3 clouds"
            >
              ⬇ Excel
            </button>
          </div>
        )}
      </div>

      {loading && (
        <div className="card text-center py-16">
          <div className="text-4xl mb-4 animate-pulse">🛡</div>
          <p className="text-gray-400 font-medium">Running WAF analysis across AWS, Azure & GCP...</p>
          <p className="text-gray-500 text-sm mt-1">This may take ~30 seconds</p>
        </div>
      )}

      {wafData && !loading && (
        <>
          {/* Comparison row */}
          <div className="grid grid-cols-3 gap-4 mb-6">
            {wafData.map((r) => {
              const meta = CLOUD_META[r.cloud]
              const cfg = STATUS_CONFIG[r.overall_status] || STATUS_CONFIG.Fair
              return (
                <button
                  key={r.cloud}
                  onClick={() => setActiveCloud(r.cloud)}
                  className={`card border transition-all text-left ${
                    activeCloud === r.cloud ? meta.color : 'border-transparent'
                  }`}
                >
                  <div className="flex items-center gap-2 mb-2">
                    <span>{meta.emoji}</span>
                    <span className="font-bold text-white">{meta.label}</span>
                  </div>
                  <div className={`text-3xl font-bold ${cfg.color}`}>{r.overall_score}</div>
                  <div className={`text-xs ${cfg.color}`}>{r.overall_status}</div>
                </button>
              )
            })}
          </div>

          {activeReview && <WAFCard review={activeReview} />}
        </>
      )}

      <div className="flex gap-3 mt-6">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <button className="btn-primary flex-1" onClick={onNext} disabled={!wafData}>
          Compare Pricing →
        </button>
      </div>
    </div>
  )
}
