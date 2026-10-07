import { useState } from 'react'

const SCALES = [
  { value: '', label: 'Not specified' },
  { value: 'dev', label: 'Dev / Test' },
  { value: 'small', label: 'Small (<1K users)' },
  { value: 'medium', label: 'Medium (1K-100K)' },
  { value: 'large', label: 'Large (>100K, multi-region)' },
]

const COMPLIANCE = ['HIPAA', 'PCI-DSS', 'SOC2', 'GDPR', 'FedRAMP', 'ISO 27001']

const REGIONS = [
  'us-east', 'us-west', 'eu-west', 'eu-central',
  'ap-south', 'ap-southeast', 'ap-northeast',
]

const PRIORITIES = [
  { value: '', label: 'Balanced' },
  { value: 'cost', label: '💰 Cost' },
  { value: 'performance', label: '⚡ Performance' },
  { value: 'reliability', label: '🛡 Reliability' },
  { value: 'security', label: '🔒 Security' },
]

export default function UserContextPanel({ value, onChange }) {
  const [open, setOpen] = useState(false)
  const ctx = value || {}

  const update = (patch) => onChange({ ...ctx, ...patch })

  const toggleArrayItem = (field, item) => {
    const arr = ctx[field] || []
    const next = arr.includes(item) ? arr.filter((x) => x !== item) : [...arr, item]
    update({ [field]: next })
  }

  const filledCount = [
    ctx.workload_description,
    ctx.expected_scale,
    ctx.compliance?.length,
    ctx.region_preferences?.length,
    ctx.budget_monthly_usd,
    ctx.priority,
    ctx.constraints,
  ].filter(Boolean).length

  return (
    <div className="card">
      <button
        type="button"
        onClick={() => setOpen(!open)}
        className="w-full flex items-center justify-between text-left"
      >
        <div>
          <p className="text-sm font-semibold text-amber-400">
            ✨ Add context (optional, recommended)
          </p>
          <p className="text-xs text-gray-500 mt-0.5">
            Tell ArchLens about your workload, scale, and priorities for sharper analysis
            {filledCount > 0 && (
              <span className="ml-2 text-amber-400">· {filledCount} field{filledCount > 1 ? 's' : ''} added</span>
            )}
          </p>
        </div>
        <span className={`text-gray-500 transition-transform ${open ? 'rotate-180' : ''}`}>▾</span>
      </button>

      {open && (
        <div className="mt-4 space-y-4 border-t border-gray-800 pt-4">
          {/* Workload description */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-1">
              Workload description
            </label>
            <textarea
              rows={2}
              value={ctx.workload_description || ''}
              onChange={(e) => update({ workload_description: e.target.value })}
              placeholder="e.g. E-commerce checkout API, ~10K req/min peak, primarily US customers"
              className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
            />
          </div>

          {/* Scale + Priority */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Expected scale</label>
              <select
                value={ctx.expected_scale || ''}
                onChange={(e) => update({ expected_scale: e.target.value })}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
              >
                {SCALES.map((s) => (
                  <option key={s.value} value={s.value}>{s.label}</option>
                ))}
              </select>
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">Optimization priority</label>
              <select
                value={ctx.priority || ''}
                onChange={(e) => update({ priority: e.target.value })}
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
              >
                {PRIORITIES.map((p) => (
                  <option key={p.value} value={p.value}>{p.label}</option>
                ))}
              </select>
            </div>
          </div>

          {/* Compliance chips */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-2">
              Compliance requirements
            </label>
            <div className="flex flex-wrap gap-1.5">
              {COMPLIANCE.map((c) => {
                const active = (ctx.compliance || []).includes(c)
                return (
                  <button
                    key={c}
                    type="button"
                    onClick={() => toggleArrayItem('compliance', c)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                      active
                        ? 'bg-purple-600 text-white'
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    {c}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Region chips */}
          <div>
            <label className="block text-xs font-medium text-gray-400 mb-2">
              Preferred regions
            </label>
            <div className="flex flex-wrap gap-1.5">
              {REGIONS.map((r) => {
                const active = (ctx.region_preferences || []).includes(r)
                return (
                  <button
                    key={r}
                    type="button"
                    onClick={() => toggleArrayItem('region_preferences', r)}
                    className={`px-2.5 py-1 rounded-full text-xs font-medium transition-colors ${
                      active
                        ? 'bg-blue-600 text-white'
                        : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                    }`}
                  >
                    {r}
                  </button>
                )
              })}
            </div>
          </div>

          {/* Budget + Constraints */}
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Monthly budget (USD)
              </label>
              <input
                type="number"
                min="0"
                value={ctx.budget_monthly_usd || ''}
                onChange={(e) =>
                  update({ budget_monthly_usd: e.target.value ? parseFloat(e.target.value) : null })
                }
                placeholder="e.g. 5000"
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-gray-400 mb-1">
                Constraints (free-form)
              </label>
              <input
                type="text"
                value={ctx.constraints || ''}
                onChange={(e) => update({ constraints: e.target.value })}
                placeholder='e.g. "Azure-only", "No serverless"'
                className="w-full bg-gray-950 border border-gray-800 rounded-lg px-3 py-2 text-sm text-gray-200 focus:border-blue-500 focus:outline-none"
              />
            </div>
          </div>

          {filledCount > 0 && (
            <button
              type="button"
              onClick={() => onChange({})}
              className="text-xs text-gray-500 hover:text-red-400 transition-colors"
            >
              Clear all context
            </button>
          )}
        </div>
      )}
    </div>
  )
}
