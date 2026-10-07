import { useState } from 'react'

const CATEGORY_COLORS = {
  compute: 'bg-orange-500/20 text-orange-300 border-orange-500/30',
  storage: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/30',
  network: 'bg-blue-500/20 text-blue-300 border-blue-500/30',
  database: 'bg-purple-500/20 text-purple-300 border-purple-500/30',
  security: 'bg-red-500/20 text-red-300 border-red-500/30',
  messaging: 'bg-green-500/20 text-green-300 border-green-500/30',
  monitoring: 'bg-teal-500/20 text-teal-300 border-teal-500/30',
  identity: 'bg-pink-500/20 text-pink-300 border-pink-500/30',
  devops: 'bg-indigo-500/20 text-indigo-300 border-indigo-500/30',
  analytics: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/30',
}

const CATEGORIES = Object.keys(CATEGORY_COLORS)

const CLOUD_LOGOS = {
  aws: { label: 'AWS', color: 'text-orange-400' },
  azure: { label: 'Azure', color: 'text-blue-400' },
  gcp: { label: 'GCP', color: 'text-green-400' },
}

function ComponentCard({ component, editing, onChange, onDelete, onToggleEdit }) {
  const categoryClass = CATEGORY_COLORS[component.category] || 'bg-gray-700 text-gray-300 border-gray-600'

  if (editing) {
    return (
      <div className="card border-amber-500/40 bg-amber-500/5">
        <div className="flex items-start justify-between mb-3 gap-2">
          <input
            value={component.name}
            onChange={(e) => onChange({ ...component, name: e.target.value })}
            className="flex-1 bg-gray-950 border border-gray-700 rounded px-2 py-1 text-sm font-semibold text-white"
            placeholder="Component name"
          />
          <select
            value={component.category}
            onChange={(e) => onChange({ ...component, category: e.target.value })}
            className="bg-gray-950 border border-gray-700 rounded px-2 py-1 text-xs text-gray-200"
          >
            {CATEGORIES.map((c) => (
              <option key={c} value={c}>{c}</option>
            ))}
          </select>
        </div>
        <input
          value={component.type}
          onChange={(e) => onChange({ ...component, type: e.target.value })}
          className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 mb-2"
          placeholder="Type (e.g. LoadBalancer)"
        />
        <textarea
          rows={2}
          value={component.description}
          onChange={(e) => onChange({ ...component, description: e.target.value })}
          className="w-full bg-gray-950 border border-gray-700 rounded px-2 py-1 text-xs text-gray-300 mb-2"
          placeholder="Description"
        />
        <div className="grid grid-cols-3 gap-1 mb-3">
          {['aws', 'azure', 'gcp'].map((cloud) => (
            <input
              key={cloud}
              value={component[`${cloud}_equivalent`] || ''}
              onChange={(e) => onChange({ ...component, [`${cloud}_equivalent`]: e.target.value })}
              placeholder={CLOUD_LOGOS[cloud].label}
              className={`bg-gray-950 border border-gray-700 rounded px-2 py-1 text-xs ${CLOUD_LOGOS[cloud].color}`}
            />
          ))}
        </div>
        <div className="flex justify-between">
          <button onClick={onDelete} className="text-xs text-red-400 hover:text-red-300">
            🗑 Delete
          </button>
          <button onClick={onToggleEdit} className="text-xs text-amber-400 hover:text-amber-300">
            ✓ Done
          </button>
        </div>
      </div>
    )
  }

  return (
    <div className="card hover:border-gray-700 transition-colors group relative">
      <button
        onClick={onToggleEdit}
        className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 text-xs text-gray-500 hover:text-amber-400 transition-opacity"
        title="Edit"
      >
        ✎
      </button>
      <div className="flex items-start justify-between mb-2 pr-6">
        <div>
          <h3 className="font-semibold text-white text-sm">{component.name}</h3>
          <p className="text-xs text-gray-500">{component.type}</p>
        </div>
        <span className={`badge border ${categoryClass}`}>{component.category}</span>
      </div>
      <p className="text-xs text-gray-400 mb-3">{component.description}</p>
      <div className="grid grid-cols-3 gap-1 text-xs">
        {['aws', 'azure', 'gcp'].map((cloud) => {
          const equiv = component[`${cloud}_equivalent`]
          const meta = CLOUD_LOGOS[cloud]
          return (
            <div key={cloud} className="bg-gray-800 rounded px-2 py-1">
              <span className={`font-medium ${meta.color}`}>{meta.label}: </span>
              <span className="text-gray-400">{equiv || '—'}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}

export default function AnalysisResult({ data, onNext, onBack, onUpdate }) {
  const [editingIndex, setEditingIndex] = useState(null)
  const [editingMeta, setEditingMeta] = useState(false)

  const update = (patch) => onUpdate({ ...data, ...patch })

  const updateComponent = (idx, comp) => {
    const next = [...data.components]
    next[idx] = comp
    update({ components: next })
  }

  const deleteComponent = (idx) => {
    const next = data.components.filter((_, i) => i !== idx)
    update({ components: next })
    setEditingIndex(null)
  }

  const addComponent = () => {
    const next = [
      ...data.components,
      {
        name: 'New Component',
        type: 'Service',
        category: 'compute',
        description: '',
        aws_equivalent: '',
        azure_equivalent: '',
        gcp_equivalent: '',
      },
    ]
    update({ components: next })
    setEditingIndex(next.length - 1)
  }

  const categories = [...new Set(data.components.map((c) => c.category))]

  return (
    <div>
      {/* Header */}
      <div className="flex items-start justify-between mb-6">
        <div className="flex-1">
          {editingMeta ? (
            <div className="space-y-2">
              <input
                value={data.architecture_type}
                onChange={(e) => update({ architecture_type: e.target.value })}
                className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 text-2xl font-bold text-white"
              />
              <textarea
                rows={2}
                value={data.description}
                onChange={(e) => update({ description: e.target.value })}
                className="w-full bg-gray-950 border border-gray-700 rounded px-3 py-2 text-sm text-gray-300"
              />
              <button
                onClick={() => setEditingMeta(false)}
                className="text-xs text-amber-400 hover:text-amber-300"
              >
                ✓ Done
              </button>
            </div>
          ) : (
            <>
              <h2 className="text-2xl font-bold text-white flex items-center gap-2">
                {data.architecture_type}
                <button
                  onClick={() => setEditingMeta(true)}
                  className="text-xs text-gray-600 hover:text-amber-400"
                  title="Edit"
                >
                  ✎
                </button>
              </h2>
              <p className="text-gray-400 mt-1 max-w-2xl">{data.description}</p>
            </>
          )}
        </div>
        <div className="text-right shrink-0 ml-4">
          <div className="text-3xl font-bold text-blue-400">{data.components.length}</div>
          <div className="text-xs text-gray-500">components</div>
        </div>
      </div>

      {/* Edit hint */}
      <div className="mb-4 px-3 py-2 bg-amber-500/5 border border-amber-500/20 rounded-lg text-xs text-amber-300">
        💡 <span className="font-medium">Tip:</span> Hover any component to edit. Correct misidentified
        services before running WAF — accurate analysis = accurate recommendations.
      </div>

      {/* Category counts */}
      <div className="flex flex-wrap gap-2 mb-6">
        {categories.map((cat) => {
          const count = data.components.filter((c) => c.category === cat).length
          const cls = CATEGORY_COLORS[cat] || 'bg-gray-700 text-gray-300 border-gray-600'
          return (
            <span key={cat} className={`badge border ${cls} capitalize`}>
              {cat} ({count})
            </span>
          )
        })}
      </div>

      {/* Cloud services summary */}
      <div className="grid grid-cols-3 gap-4 mb-6">
        {Object.entries(CLOUD_LOGOS).map(([cloud, meta]) => {
          const services = data.detected_services[cloud] || []
          return (
            <div key={cloud} className="card">
              <p className={`text-sm font-semibold ${meta.color} mb-2`}>{meta.label} Services</p>
              {services.length > 0 ? (
                <div className="flex flex-wrap gap-1">
                  {services.slice(0, 8).map((s) => (
                    <span key={s} className="badge bg-gray-800 text-gray-400">{s}</span>
                  ))}
                  {services.length > 8 && (
                    <span className="badge bg-gray-800 text-gray-500">+{services.length - 8} more</span>
                  )}
                </div>
              ) : (
                <p className="text-xs text-gray-600">—</p>
              )}
            </div>
          )
        })}
      </div>

      {/* Component grid */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-lg font-semibold text-white">Detected Components</h3>
        <button
          onClick={addComponent}
          className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
        >
          + Add component
        </button>
      </div>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-4 mb-8">
        {data.components.map((c, i) => (
          <ComponentCard
            key={i}
            component={c}
            editing={editingIndex === i}
            onChange={(comp) => updateComponent(i, comp)}
            onDelete={() => deleteComponent(i)}
            onToggleEdit={() => setEditingIndex(editingIndex === i ? null : i)}
          />
        ))}
      </div>

      <div className="flex gap-3">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <button className="btn-primary flex-1" onClick={onNext}>
          Run WAF Review →
        </button>
      </div>
    </div>
  )
}
