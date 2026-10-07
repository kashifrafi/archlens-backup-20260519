import { useState, useEffect } from 'react'
import axios from 'axios'
import toast from 'react-hot-toast'

const STATUS_UI = {
  loading:              { icon: '⟳', spin: true,  cls: 'border-blue-500/40 bg-blue-500/5'     },
  pending:              { icon: '○', spin: false, cls: 'border-gray-700 bg-gray-900/40'        },
  planned_and_finished: { icon: '✓', spin: false, cls: 'border-green-500/40 bg-green-500/5'   },
  planned:              { icon: '⚠', spin: false, cls: 'border-yellow-500/40 bg-yellow-500/5' },
  errored:              { icon: '✗', spin: false, cls: 'border-red-500/40 bg-red-500/5'       },
  skipped:              { icon: '⊘', spin: false, cls: 'border-yellow-500/40 bg-yellow-500/5' },
}

// Strip ANSI escape codes from HCP log output
const stripAnsi = (str) => str.replace(/\x1B\[[0-9;]*[mGKHF]/g, '')

// Colorize a single plan log line
function PlanLogLine({ raw }) {
  const line = stripAnsi(raw)
  let cls = 'text-gray-400'
  if (/^\s*\+/.test(line))                          cls = 'text-green-400'
  else if (/^\s*-/.test(line))                      cls = 'text-red-400'
  else if (/^\s*~/.test(line))                      cls = 'text-yellow-300'
  else if (/Error:|error:/i.test(line))             cls = 'text-red-400 font-semibold'
  else if (/Warning:|warning:/i.test(line))         cls = 'text-yellow-400'
  else if (/Plan:|Apply:|Refreshing|will be|must be/i.test(line)) cls = 'text-white'
  else if (/^\s*#/.test(line))                      cls = 'text-blue-300'
  return <div className={`whitespace-pre font-mono text-xs leading-5 ${cls}`}>{line || ' '}</div>
}

export default function HcpPlan({ terraformData, onBack, onNext, onFilesUpdated }) {
  const [loading,      setLoading]      = useState(false)
  const [fixing,       setFixing]       = useState(false)
  const [result,       setResult]       = useState(null)
  const [currentFiles, setCurrentFiles] = useState([])
  const [activeIdx,    setActiveIdx]    = useState(0)
  const [editMode,     setEditMode]     = useState(false)
  const [logOpen,      setLogOpen]      = useState(false)
  const [copied,       setCopied]       = useState(false)

  // Sync files from parent whenever terraformData changes (and we're not mid-fix)
  useEffect(() => {
    if (!fixing && terraformData?.files?.length) {
      setCurrentFiles(terraformData.files.map(f => ({ ...f })))
      setActiveIdx(0)
    }
  }, [terraformData])

  const runPlan = async (files) => {
    if (!files?.length) {
      toast.error('No Terraform files — generate Terraform first')
      return
    }
    setLoading(true)
    setResult(null)
    setLogOpen(false)
    try {
      const { data } = await axios.post('/api/terraform/hcp-plan', { files })
      setResult(data)
      if (data.plan_log) setLogOpen(true)   // auto-expand log when it arrives
      if (data.passed)       toast.success('HCP speculative plan passed!')
      else if (data.skipped) toast('HCP Plan skipped — check config', { icon: '⚠' })
      else                   toast.error('HCP Plan errored — fix the issues below and re-run')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'HCP Plan request failed')
    } finally {
      setLoading(false)
    }
  }

  const fixWithAI = async () => {
    setFixing(true)
    try {
      const { data } = await axios.post('/api/terraform/fix', {
        files:    currentFiles,
        cloud:    terraformData?.cloud || 'aws',
        findings: errorLines,
      })
      const fixed = data.files
      setCurrentFiles(fixed)
      onFilesUpdated?.(fixed)
      setResult(null)
      toast.success('AI applied fixes — review then click ↻ Re-run Plan')
    } catch (err) {
      toast.error(err.response?.data?.detail || 'AI fix failed')
    } finally {
      setFixing(false)
    }
  }

  const updateContent = (content) =>
    setCurrentFiles(prev => prev.map((f, i) => i === activeIdx ? { ...f, content } : f))

  const copyLog = () => {
    navigator.clipboard.writeText(stripAnsi(planLog)).then(() => {
      setCopied(true)
      setTimeout(() => setCopied(false), 2000)
    })
  }

  const saveAndRerun = () => {
    onFilesUpdated?.(currentFiles)
    setEditMode(false)
    runPlan(currentFiles)
  }

  // ── Derived state ──────────────────────────────────────────────────────────
  const planStatus = loading
    ? 'loading'
    : !result         ? 'pending'
    : result.skipped  ? 'skipped'
    : result.passed   ? 'planned_and_finished'
    : 'errored'

  const ui       = STATUS_UI[planStatus] || STATUS_UI.pending
  const isError  = planStatus === 'errored'
  const isPassed = planStatus === 'planned_and_finished'

  const runUrl     = result?.details?.find(d => d.startsWith('Run:'))?.replace('Run: ', '')
  const changes    = result?.details?.filter(d => !d.startsWith('Run:') && !d.startsWith('[CHANGE]')) || []
  const errorLines = result?.details?.filter(d => !d.startsWith('Run:') && !d.startsWith('[CHANGE]')) || []
  const planLog    = result?.plan_log || ''

  // Parse error lines to build { filename → Set<lineNumber> }
  const errorMap = (() => {
    const map = {}
    const patterns = [
      /on\s+([\w.\/\-]+\.tf)\s+line\s+(\d+)/gi,
      /([\w.\/\-]+\.tf):(\d+)/gi,
      /([\w.\/\-]+\.tf)\s+line\s+(\d+)/gi,
    ]
    for (const line of errorLines) {
      for (const pat of patterns) {
        pat.lastIndex = 0
        let m
        while ((m = pat.exec(line)) !== null) {
          const fname = m[1]
          const lnum  = parseInt(m[2], 10)
          if (!map[fname]) map[fname] = new Set()
          map[fname].add(lnum)
        }
      }
    }
    return map
  })()

  return (
    <div>

      {/* ── Header ── */}
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white flex items-center gap-2">☁️ HCP Cloud Plan</h2>
          <p className="text-gray-400 text-sm">
            Speculative plan on HCP Terraform — validates against real provider schemas
          </p>
        </div>
        <button
          onClick={() => runPlan(currentFiles)}
          disabled={loading || fixing}
          className="btn-primary"
        >
          {loading
            ? <span className="flex items-center gap-2"><span className="animate-spin inline-block">⟳</span> Running…</span>
            : result ? '↻ Re-run Plan' : '▶ Run HCP Plan'}
        </button>
      </div>

      {/* ── Status card ── */}
      <div className={`rounded-xl border p-6 mb-4 transition-all ${ui.cls}`}>
        <div className="flex items-start gap-5">
          <div className={`text-4xl shrink-0 mt-1 ${
            ui.spin    ? 'animate-spin text-blue-400'
            : isError  ? 'text-red-400'
            : isPassed ? 'text-green-400'
            : 'text-gray-400'
          }`}>
            {ui.icon}
          </div>
          <div className="flex-1">
            <div className="flex items-center gap-3 mb-1">
              <span className="text-lg font-bold text-white">Speculative Plan</span>
              <span className="text-xs font-mono text-gray-500">
                HCP Terraform · {(terraformData?.cloud || 'aws').toUpperCase()}
              </span>
            </div>
            <p className="text-sm text-gray-400">
              {loading
                ? 'Uploading config and waiting for HCP to finish planning (~1–2 min)…'
                : result
                  ? result.message
                  : 'Click "Run HCP Plan" to trigger a speculative plan on HashiCorp Cloud Platform.'}
            </p>

            {/* Planned resource changes */}
            {changes.length > 0 && (
              <div className="mt-4">
                <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
                  Planned Changes ({changes.length})
                </p>
                <div className="bg-gray-950 rounded-lg border border-gray-800 p-3 space-y-1 font-mono text-xs max-h-48 overflow-y-auto">
                  {changes.map((c, i) => <div key={i} className="text-yellow-300">{c}</div>)}
                </div>
              </div>
            )}

            {/* Skipped notice */}
            {result?.skipped && (
              <div className="mt-4 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-xs text-yellow-300">
                ⚠ {result.message}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* ── Plan Log panel — shown when we have a text log ── */}
      {planLog && (
        <div className="mb-5 rounded-xl border border-gray-700 bg-gray-900 overflow-hidden">
          {/* Collapsible header */}
          <button
            onClick={() => setLogOpen(o => !o)}
            className="w-full flex items-center justify-between px-4 py-3 hover:bg-gray-800 transition-colors"
          >
            <span className="flex items-center gap-2 text-sm font-semibold text-gray-200">
              🖥 Plan Output
              <span className={`text-xs font-normal px-2 py-0.5 rounded-full border ${
                isPassed
                  ? 'text-green-400 border-green-600 bg-green-900/30'
                  : isError
                  ? 'text-red-400 border-red-600 bg-red-900/30'
                  : 'text-gray-400 border-gray-600'
              }`}>
                {isPassed ? 'No errors' : isError ? 'Errors detected' : 'Complete'}
              </span>
            </span>
            <div className="flex items-center gap-3">
              <button
                onClick={e => { e.stopPropagation(); copyLog() }}
                className="text-xs text-gray-500 hover:text-gray-300 transition-colors px-2 py-1 rounded border border-gray-700 hover:border-gray-500"
              >
                {copied ? '✓ Copied' : '📋 Copy'}
              </button>
              {runUrl && (
                <a
                  href={runUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  onClick={e => e.stopPropagation()}
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors px-2 py-1 rounded border border-blue-800 hover:border-blue-600"
                >
                  🔗 HCP →
                </a>
              )}
              <span className="text-gray-500 text-sm">{logOpen ? '▲' : '▼'}</span>
            </div>
          </button>

          {/* Log body */}
          {logOpen && (
            <div className="border-t border-gray-800 bg-gray-950 p-4 max-h-96 overflow-y-auto">
              {planLog.split('\n').map((line, i) => (
                <PlanLogLine key={i} raw={line} />
              ))}
            </div>
          )}
        </div>
      )}

      {/* ── Error panel — shown only when plan errored ── */}      {isError && (
        <div className="mb-5 rounded-xl border border-red-500/40 bg-red-500/5 p-4">

          {/* Error header + action buttons */}
          <div className="flex items-center justify-between mb-3 flex-wrap gap-2">
            <p className="text-sm font-semibold text-red-400 flex items-center gap-2">
              ✗ Plan Error — fix the code and re-run
            </p>
            <div className="flex gap-2">
              <button
                onClick={fixWithAI}
                disabled={fixing || loading}
                className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-semibold transition-colors disabled:opacity-50"
              >
                {fixing
                  ? <><span className="animate-spin inline-block">⟳</span> Fixing…</>
                  : '🤖 Fix with AI'}
              </button>
              <button
                onClick={() => setEditMode(e => !e)}
                className={`flex items-center gap-1 px-3 py-1.5 rounded-lg border text-xs font-semibold transition-colors
                  ${editMode
                    ? 'border-blue-500 bg-blue-500/10 text-blue-400'
                    : 'border-gray-700 bg-gray-900 text-gray-400 hover:text-gray-200'}`}
              >
                ✏️ {editMode ? 'Editing…' : 'Manual Edit'}
              </button>
            </div>
          </div>

          {/* Error log */}
          {errorLines.length > 0 && (
            <div className="mb-4 bg-gray-950 rounded-lg border border-red-800/30 p-3 font-mono text-xs text-red-300 max-h-44 overflow-y-auto whitespace-pre-wrap">
              {errorLines.join('\n')}
            </div>
          )}

          {/* Inline code editor */}
          <div className="rounded-xl border border-gray-700 bg-gray-900 overflow-hidden">
            {/* File tabs */}
            <div className="flex overflow-x-auto border-b border-gray-800 bg-gray-950">
              {currentFiles.map((f, i) => {
                const hasFileError = !!errorMap[f.filename]?.size
                return (
                  <button
                    key={f.filename}
                    onClick={() => setActiveIdx(i)}
                    className={`flex items-center gap-1.5 px-3 py-2 text-xs font-mono whitespace-nowrap border-r border-gray-800 transition-colors
                      ${activeIdx === i ? 'bg-gray-800 text-white' : 'text-gray-500 hover:text-gray-300'}`}
                  >
                    {hasFileError && (
                      <span className="inline-block w-1.5 h-1.5 rounded-full bg-red-500 shrink-0" title="Has errors" />
                    )}
                    {f.filename}
                    {hasFileError && (
                      <span className="text-red-400 font-bold text-[10px]">
                        ({errorMap[f.filename].size})
                      </span>
                    )}
                  </button>
                )
              })}
            </div>

            {/* Code view — highlighted when read-only, plain textarea when editing */}
            {!editMode ? (
              <div className="h-72 overflow-auto bg-gray-900 font-mono text-xs">
                {(currentFiles[activeIdx]?.content || '').split('\n').map((line, i) => {
                  const lineNum  = i + 1
                  const filename = currentFiles[activeIdx]?.filename || ''
                  const hasError = errorMap[filename]?.has(lineNum)
                  return (
                    <div
                      key={i}
                      className={`flex items-start min-w-0 ${
                        hasError ? 'bg-red-500/20 border-l-2 border-red-500' : 'border-l-2 border-transparent'
                      }`}
                    >
                      {/* Gutter */}
                      <span className={`select-none shrink-0 w-10 text-right pr-2 py-px leading-5 ${
                        hasError ? 'text-red-400 font-bold' : 'text-gray-600'
                      }`}>
                        {hasError ? '●' : lineNum}
                      </span>
                      {/* Line content */}
                      <span className={`pl-2 py-px leading-5 whitespace-pre break-all ${
                        hasError ? 'text-red-200' : 'text-gray-300'
                      }`}>
                        {line || ' '}
                      </span>
                    </div>
                  )
                })}
              </div>
            ) : (
              <textarea
                value={currentFiles[activeIdx]?.content || ''}
                onChange={e => updateContent(e.target.value)}
                autoFocus
                spellCheck={false}
                className="w-full h-72 p-4 font-mono text-xs resize-none outline-none bg-gray-800 text-gray-200 cursor-text"
              />
            )}

            {/* Save bar — only shown in edit mode */}
            {editMode && (
              <div className="flex items-center justify-between px-4 py-2 border-t border-gray-800 bg-gray-950">
                <span className="text-xs text-gray-500">Editing {currentFiles[activeIdx]?.filename}</span>
                <div className="flex gap-2">
                  <button
                    onClick={() => setEditMode(false)}
                    className="text-xs text-gray-500 hover:text-gray-300"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={saveAndRerun}
                    className="text-xs px-3 py-1 rounded bg-blue-600 hover:bg-blue-500 text-white font-semibold"
                  >
                    Save &amp; Re-run Plan
                  </button>
                </div>
              </div>
            )}
          </div>

          <p className="mt-3 text-xs text-center text-gray-500">
            After fixing, click <strong className="text-white">↻ Re-run Plan</strong> above to verify
          </p>
        </div>
      )}

      {/* ── Info box (hidden when error panel is showing) ── */}
      {!isError && (
        <div className="card mb-6 p-4 border-gray-800">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide mb-2">
            About HCP Speculative Plans
          </p>
          <ul className="text-xs text-gray-500 space-y-1 list-disc list-inside">
            <li>Does <strong className="text-gray-400">not</strong> create or modify any real infrastructure</li>
            <li>Validates your Terraform config against real AWS provider schemas</li>
            <li>Shows exactly which resources would be created, updated, or destroyed</li>
            <li>Run is visible in your HCP Terraform workspace dashboard</li>
          </ul>
        </div>
      )}

      {/* ── Navigation ── */}
      <div className="flex gap-3 mt-6">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        <div className="flex-1 flex flex-col gap-1">
          <button
            className="btn-primary w-full disabled:opacity-40 disabled:cursor-not-allowed"
            onClick={onNext}
            disabled={!isPassed}
          >
            🐙 Push to GitHub →
          </button>
          {!isPassed && (
            <p className="text-xs text-center text-gray-500">
              {!result
                ? 'Run HCP Plan first to unlock GitHub push'
                : isError
                ? '❌ Fix all plan errors before pushing to GitHub'
                : ''}
            </p>
          )}
        </div>
      </div>

    </div>
  )
}
