/**
 * TerraformRunner — Real-time terraform execution panel via SSE streaming.
 *
 * Connects to POST /api/terraform/run and streams:
 *   event: stage        → stage started  { stage, message }
 *   event: stage_done   → stage finished { stage, passed, [summary], [attempts] }
 *   event: log          → one output line { stage, line }
 *   event: validate_errors → errors found { errors, attempt }
 *   event: files_updated → AI fixed / fmt applied { stage, files }
 *   event: done         → all done { passed, plan_summary, files }
 *   event: error        → fatal { stage, message }
 */
import { useState, useRef, useEffect } from 'react'
import toast from 'react-hot-toast'
import JSZip from 'jszip'

// Main pipeline stages shown as badges (AI Fix is shown as a loop arc, not a stage)
const STAGES = [
  { key: 'fmt',      label: 'Format',   icon: '📝', description: 'terraform fmt -recursive' },
  { key: 'init',     label: 'Init',     icon: '🔧', description: 'terraform init -upgrade' },
  { key: 'validate', label: 'Validate', icon: '✅', description: 'terraform validate with AI auto-fix' },
  { key: 'plan',     label: 'Plan',     icon: '📋', description: 'terraform plan — compute resource changes' },
]

function useElapsed(startTime, active) {
  const [elapsed, setElapsed] = useState(0)
  useEffect(() => {
    if (!active || !startTime) { setElapsed(0); return }
    const id = setInterval(() => setElapsed(Math.floor((Date.now() - startTime) / 1000)), 500)
    return () => clearInterval(id)
  }, [startTime, active])
  return elapsed
}

function fmtElapsed(secs) {
  if (secs < 60) return `${secs}s`
  return `${Math.floor(secs / 60)}m ${secs % 60}s`
}

function StageBadge({ stageKey, stageState, stageStartTimes, aiFixActive }) {
  const { status, attempts, nonBlocking } = stageState[stageKey] || { status: 'pending' }
  const elapsed = useElapsed(stageStartTimes?.[stageKey], status === 'running')
  // If AI fix is running after this stage completed, pulse the border
  const fixingAfterMe = aiFixActive && (
    (aiFixActive.stage === 'llm_fix' && (stageKey === 'validate' || stageKey === 'init')) ||
    (aiFixActive.stage === 'plan_fix' && stageKey === 'plan')
  )
  const base = 'flex flex-col items-center px-3 py-2.5 rounded-xl border min-w-[80px] transition-all'
  const styles = fixingAfterMe
    ? `${base} border-indigo-500/80 bg-indigo-500/10 text-indigo-300 ring-1 ring-indigo-500/40 animate-pulse`
    : {
        pending:  `${base} border-gray-700 bg-gray-900 text-gray-500`,
        running:  `${base} border-blue-500/60 bg-blue-500/10 text-blue-400`,
        passed:   `${base} border-green-500/40 bg-green-500/10 text-green-400`,
        warning:  `${base} border-yellow-500/40 bg-yellow-500/10 text-yellow-300`,
        failed:   `${base} border-red-500/40 bg-red-500/10 text-red-400`,
        skipped:  `${base} border-gray-600/40 bg-gray-800/20 text-gray-500`,
      }[status] || `${base} border-gray-700 bg-gray-900 text-gray-500`

  const icon = {
    pending: <span className="text-gray-600 text-sm">○</span>,
    running: <span className="animate-spin text-blue-400 text-sm">⟳</span>,
    passed:  <span className="text-sm">✓</span>,
    warning: <span className="text-sm">⚠</span>,
    failed:  <span className="text-sm">✗</span>,
    skipped: <span className="text-sm">⊘</span>,
  }[status] || <span className="text-gray-600 text-sm">○</span>

  const stage = STAGES.find(s => s.key === stageKey)
  return (
    <div className={styles} title={stage?.description}>
      <div className="text-xl mb-1">{stage?.icon}</div>
      <div className="flex items-center gap-1 text-[11px] font-semibold whitespace-nowrap">
        {icon} {stage?.label}
        {attempts > 1 && <span className="text-[9px] text-gray-500 ml-0.5">×{attempts}</span>}
      </div>
      {status === 'running' && elapsed > 0 && (
        <span className="text-[9px] text-blue-400/70 mt-0.5 tabular-nums">{fmtElapsed(elapsed)}</span>
      )}
      {nonBlocking && status !== 'pending' && (
        <span className="text-[8px] text-gray-500 mt-0.5 uppercase tracking-wider">non-blocking</span>
      )}
    </div>
  )
}

function PlanSummary({ summary, persistentValErrors }) {
  const hasSummary = summary && (summary.changes?.add || summary.changes?.change || summary.changes?.remove || summary.resources?.length)
  const hasManual  = persistentValErrors?.length > 0

  if (!hasSummary && !hasManual) return null

  const { changes = {}, resources = [] } = summary || {}
  const totalPlannedResources = (changes.add || 0) + (changes.change || 0) + (changes.remove || 0)
  const totalErrors = persistentValErrors?.length || 0

  return (
    <div className="mt-3 space-y-2">
      {/* Overall Status Banner */}
      {hasSummary && hasManual && (
        <div className="p-3 rounded-lg bg-gradient-to-r from-green-500/10 to-amber-500/10 border-2 border-gray-700">
          <div className="flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <span className="text-2xl">📊</span>
              <div>
                <p className="text-sm font-bold text-white">Pipeline Results</p>
                <p className="text-xs text-gray-400">Terraform plan completed with partial success</p>
              </div>
            </div>
            <div className="flex items-center gap-6 text-xs font-mono">
              <div className="text-center">
                <div className="text-2xl font-bold text-green-400">{totalPlannedResources}</div>
                <div className="text-[10px] text-gray-400 uppercase tracking-wide">✅ Planned</div>
              </div>
              <div className="text-gray-600 text-2xl">|</div>
              <div className="text-center">
                <div className="text-2xl font-bold text-amber-400">{totalErrors}</div>
                <div className="text-[10px] text-gray-400 uppercase tracking-wide">⚠️ Need Fixes</div>
              </div>
            </div>
          </div>
        </div>
      )}

      {hasSummary && (
        <div className="p-3 rounded-lg bg-gray-950 border border-gray-800">
          <p className="text-xs font-semibold text-gray-400 mb-2 uppercase tracking-wide flex items-center gap-2">
            <span>✅</span>
            Plan Summary — {totalPlannedResources} Resource{totalPlannedResources !== 1 ? 's' : ''} Ready
          </p>
          <div className="flex gap-4 text-sm mb-2">
            {changes.add > 0 && <span className="text-green-400 font-bold">+{changes.add} to add</span>}
            {changes.change > 0 && <span className="text-yellow-400 font-bold">~{changes.change} to change</span>}
            {changes.remove > 0 && <span className="text-red-400 font-bold">-{changes.remove} to destroy</span>}
            {!changes.add && !changes.change && !changes.remove && (
              <span className="text-gray-400">No changes</span>
            )}
          </div>
          {resources.length > 0 && (
            <div className="max-h-32 overflow-y-auto space-y-0.5">
              {resources.map((r, i) => (
                <div key={i} className={`text-xs font-mono ${
                  r.startsWith('+') ? 'text-green-400' :
                  r.startsWith('~') ? 'text-yellow-400' :
                  r.startsWith('-') ? 'text-red-400' : 'text-gray-400'
                }`}>{r}</div>
              ))}
            </div>
          )}
        </div>
      )}

      {hasManual && (
        <div className="p-3 rounded-lg bg-amber-500/8 border-2 border-amber-500/40">
          <p className="text-sm font-bold text-amber-300 mb-1.5 flex items-center gap-2">
            <span className="text-xl">⚠️</span>
            {totalErrors} Validation Error{totalErrors !== 1 ? 's' : ''} Require Manual Fixes
          </p>
          <p className="text-[11px] text-amber-200/70 mb-2 leading-relaxed">
            The following errors could not be auto-fixed after 2 GPT-5.3-codex fix attempts.
            {hasSummary && <strong className="text-amber-200"> The {totalPlannedResources} resource{totalPlannedResources !== 1 ? 's' : ''} shown above will be created successfully — only fix the errors below to complete the remaining resources.</strong>}
          </p>
          <div className="space-y-1.5 max-h-40 overflow-y-auto">
            {persistentValErrors.map((e, i) => (
              <div key={i} className="text-[11px] font-mono text-amber-200/90 bg-amber-900/20 rounded px-2 py-1 border-l-4 border-amber-500">{e}</div>
            ))}
          </div>
          <div className="mt-3 p-2 rounded bg-amber-900/20 border border-amber-500/30">
            <p className="text-[10px] text-amber-200 font-semibold mb-1">💡 How to Fix:</p>
            <ol className="text-[10px] text-amber-200/80 space-y-0.5 list-decimal list-inside">
              <li>Manual fix mode will open showing error lines with <span className="text-red-400 font-bold">thick red borders</span></li>
              <li>Click <span className="font-bold text-amber-300">"➜ Jump to Line"</span> buttons to navigate to each error</li>
              <li>Fix the highlighted lines (usually unsupported arguments or missing required fields)</li>
              <li>Click <span className="font-bold text-emerald-400">"💾 Save & Re-run"</span> to validate your fixes</li>
            </ol>
          </div>
        </div>
      )}
    </div>
  )
}

// Side-by-side diff viewer for AI fixes
function CodeDiffView({ beforeCode, afterCode, filename }) {
  if (!beforeCode || !afterCode) return null
  
  return (
    <div className="mt-3 rounded-lg border border-gray-700 overflow-hidden">
      <div className="bg-gray-900/80 px-3 py-2 border-b border-gray-700 flex items-center gap-2">
        <span className="text-xs font-mono text-gray-400">{filename}</span>
        <span className="text-[10px] text-gray-500">— Auto-fix applied</span>
      </div>
      <div className="grid grid-cols-2 divide-x divide-gray-700">
        {/* Before (Error) */}
        <div className="bg-red-950/20">
          <div className="bg-red-900/40 px-3 py-1.5 border-b border-red-800/40">
            <span className="text-[10px] font-semibold text-red-300 uppercase tracking-wide">❌ Before (Error)</span>
          </div>
          <pre className="text-xs font-mono text-red-200 p-3 overflow-x-auto max-h-64 overflow-y-auto">
            <code>{beforeCode}</code>
          </pre>
        </div>
        {/* After (Fixed) */}
        <div className="bg-green-950/20">
          <div className="bg-green-900/40 px-3 py-1.5 border-b border-green-800/40">
            <span className="text-[10px] font-semibold text-green-300 uppercase tracking-wide">✅ After (Fixed)</span>
          </div>
          <pre className="text-xs font-mono text-green-200 p-3 overflow-x-auto max-h-64 overflow-y-auto">
            <code>{afterCode}</code>
          </pre>
        </div>
      </div>
    </div>
  )
}

function ValidationErrors({ errors, attempt, diffData }) {
  if (!errors?.length) return null
  return (
    <div className="mt-2 p-3 rounded-lg bg-red-500/5 border border-red-500/30">
      <p className="text-xs font-semibold text-red-400 mb-2">
        Validation errors (attempt {attempt}/3) — Fixing the code:
      </p>
      <div className="space-y-1 max-h-32 overflow-y-auto">
        {errors.map((e, i) => (
          <div key={i} className="text-xs font-mono text-red-300">{e}</div>
        ))}
      </div>
      {diffData && (
        <CodeDiffView
          beforeCode={diffData.before}
          afterCode={diffData.after}
          filename={diffData.filename}
        />
      )}
    </div>
  )
}

function PlanErrors({ errors, attempt, diffData }) {
  if (!errors?.length) return null
  return (
    <div className="mt-2 p-3 rounded-lg bg-orange-500/8 border border-orange-500/40">
      <p className="text-xs font-semibold text-orange-300 mb-2 flex items-center gap-1.5">
        <span>🔴</span> Plan errors (attempt {attempt}/3) — Fixing the code:
      </p>
      <div className="space-y-1 max-h-36 overflow-y-auto">
        {errors.map((e, i) => (
          <div key={i} className="text-xs font-mono text-orange-200/80">{e}</div>
        ))}
      </div>
      {diffData && (
        <CodeDiffView
          beforeCode={diffData.before}
          afterCode={diffData.after}
          filename={diffData.filename}
        />
      )}
      <p className="text-[10px] text-orange-400/60 mt-2">
        ⚠ AI analyzes errors and provides intelligent fixes. Review the changes after each attempt.
      </p>
    </div>
  )
}

const CLOUD_CRED_FIELDS = {
  aws: [
    { key: 'AWS_ACCESS_KEY_ID',     label: 'Access Key ID',     placeholder: 'AKIAIOSFODNN7EXAMPLE',    type: 'text' },
    { key: 'AWS_SECRET_ACCESS_KEY', label: 'Secret Access Key', placeholder: 'wJalrXUtnFEMI/K7MDENG…',  type: 'password' },
    { key: 'AWS_SESSION_TOKEN',     label: 'Session Token',     placeholder: 'Optional — for STS/SSO',  type: 'password' },
    { key: 'AWS_DEFAULT_REGION',    label: 'Region',            placeholder: 'us-east-1',               type: 'text' },
  ],
  azure: [
    { key: 'ARM_CLIENT_ID',       label: 'Client ID',       placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', type: 'text' },
    { key: 'ARM_CLIENT_SECRET',   label: 'Client Secret',   placeholder: 'your-client-secret',                  type: 'password' },
    { key: 'ARM_TENANT_ID',       label: 'Tenant ID',       placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', type: 'text' },
    { key: 'ARM_SUBSCRIPTION_ID', label: 'Subscription ID', placeholder: 'xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx', type: 'text' },
  ],
  gcp: [
    { key: 'GOOGLE_PROJECT',                    label: 'Project ID',       placeholder: 'my-gcp-project',     type: 'text' },
    { key: 'GOOGLE_CREDENTIALS',                label: 'Service Account JSON', placeholder: '{"type":"service_account",...}', type: 'password' },
    { key: 'GOOGLE_APPLICATION_CREDENTIALS',    label: 'Credentials File', placeholder: '/path/to/key.json',  type: 'text' },
  ],
}

function CredentialsPanel({ cloud, creds, onChange }) {
  const [showPasswords, setShowPasswords] = useState(false)
  const fields = CLOUD_CRED_FIELDS[cloud] || CLOUD_CRED_FIELDS.aws
  const cloudLabel = { aws: '☁ AWS', azure: '☁ Azure', gcp: '☁ GCP' }[cloud] || cloud.toUpperCase()
  const allFilled = fields.slice(0, cloud === 'aws' ? 2 : 3).every(f => creds[f.key]?.trim())

  return (
    <div className="rounded-xl border border-gray-700/60 bg-gray-900/60 overflow-hidden">
      <div className="flex items-center justify-between px-4 py-2.5 bg-gray-800/40 border-b border-gray-700/50">
        <div className="flex items-center gap-2">
          <span className="text-sm font-semibold text-white">{cloudLabel}</span>
          {allFilled
            ? <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-green-500/20 text-green-400 border border-green-500/30">Ready</span>
            : <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-gray-700 text-gray-500">Not configured</span>
          }
        </div>
        <button
          onClick={() => setShowPasswords(!showPasswords)}
          className="text-gray-400 hover:text-gray-200 transition-colors"
          title={showPasswords ? 'Hide passwords' : 'Show passwords'}
        >
          {showPasswords ? '👁️' : '👁️‍🗨️'}
        </button>
      </div>
      <div className="p-3 grid grid-cols-2 gap-2">
        {fields.map(f => (
          <div key={f.key} className={f.key === 'GOOGLE_CREDENTIALS' ? 'col-span-2' : ''}>
            <label className="block text-[10px] text-gray-500 mb-0.5 font-mono">{f.label}</label>
            <input
              type={f.type === 'password' && !showPasswords ? 'password' : 'text'}
              value={creds[f.key] || ''}
              onChange={e => onChange(f.key, e.target.value)}
              placeholder={f.placeholder}
              className="w-full px-2 py-1.5 text-[11px] font-mono rounded-md bg-gray-950 border border-gray-700 text-gray-200 placeholder-gray-700 focus:outline-none focus:border-indigo-500/60"
              autoComplete="off"
              spellCheck={false}
            />
          </div>
        ))}
      </div>
    </div>
  )
}

export default function TerraformRunner({ files, cloud = 'aws', onFilesUpdated, onValidationDone, onRegenerate }) {
  const [running, setRunning]         = useState(false)
  const [done, setDone]               = useState(false)
  const [error, setError]             = useState(null)
  const [stageState, setStageState]   = useState({})
  const [logs, setLogs]               = useState([])
  const [valErrors, setValErrors]     = useState(null)
  const [valDiffData, setValDiffData] = useState(null) // Diff data for validation fixes
  const [planSummary, setPlanSummary]         = useState(null)
  const [planSkipped, setPlanSkipped]         = useState(null)
  const [persistentValErrors, setPersistentValErrors] = useState([]) // validate errors not auto-fixed
  const [logFilter, setLogFilter]     = useState('all')
  const [runPlan, setRunPlan]         = useState(false)
  const [showCreds, setShowCreds]     = useState(false)
  const [creds, setCreds]             = useState({})
  const [planErrors, setPlanErrors]   = useState(null)
  const [planDiffData, setPlanDiffData] = useState(null) // Diff data for plan fixes
  const [finalFiles, setFinalFiles]   = useState(null)
  const [aiFixStatus, setAiFixStatus] = useState(null)  // { stage, attempt, message } when AI fix is running
  const [activeFileTab, setActiveFileTab] = useState(0)
  const [stageStartTimes, setStageStartTimes] = useState({}) // key → Date.now() when stage started
  const [filesBeforeFix, setFilesBeforeFix] = useState({}) // Store files before each fix attempt
  // Manual fix mode: triggered when AI fix exhausts retries (3 attempts).
  // { stage, errors, lineMap: { filename: Set<lineNum> } }
  const [manualFixMode, setManualFixMode]       = useState(null)
  const [manualFixFiles, setManualFixFiles]     = useState([])
  const [manualActiveTab, setManualActiveTab]   = useState(0)
  const logEndRef = useRef(null)
  const abortRef  = useRef(null)

  const updateCred = (key, value) => setCreds(prev => ({ ...prev, [key]: value }))

  // Auto-scroll logs
  useEffect(() => {
    logEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [logs])

  // Auto-scroll to first error line when manual fix mode opens
  useEffect(() => {
    if (manualFixMode && manualFixFiles.length > 0) {
      // Find the first file with errors
      const firstFileWithErrors = manualFixFiles.findIndex(f => {
        const flaggedLines = manualFixMode.lineMap?.[f.filename]
        return flaggedLines && flaggedLines.size > 0
      })
      
      if (firstFileWithErrors >= 0) {
        // Switch to that tab
        setManualActiveTab(firstFileWithErrors)
        
        // Get the first error line number
        const flaggedLines = manualFixMode.lineMap[manualFixFiles[firstFileWithErrors].filename]
        const firstErrorLine = Math.min(...Array.from(flaggedLines))
        
        // Scroll to it after a short delay for tab switch and render
        setTimeout(() => {
          const editorDiv = document.querySelector('.manual-fix-editor-scroll')
          if (editorDiv) {
            const lineHeight = 20 // 1.25rem = 20px
            editorDiv.scrollTop = (firstErrorLine - 1) * lineHeight - 100 // Offset to center
          }
        }, 150)
      }
    }
  }, [manualFixMode]) // Only run when manualFixMode changes

  const setStage = (key, partial) => {
    if (partial.status === 'running') {
      setStageStartTimes(prev => ({ ...prev, [key]: Date.now() }))
    }
    setStageState(prev => ({
      ...prev,
      [key]: { ...(prev[key] || {}), ...partial },
    }))
  }

  const reset = () => {
    setRunning(false)
    setDone(false)
    setError(null)
    setStageState({})
    setStageStartTimes({})
    setLogs([])
    setValErrors(null)
    setValDiffData(null)
    setPlanErrors(null)
    setPlanDiffData(null)
    setPlanSummary(null)
    setPlanSkipped(null)
    setPersistentValErrors([])
    setFinalFiles(null)
    setAiFixStatus(null)
    setActiveFileTab(0)
    setManualFixMode(null)
    setManualFixFiles([])
    setManualActiveTab(0)
    setFilesBeforeFix({})
  }

  // Parse terraform error messages like "on main.tf line 42:" into a {filename: Set<lineNum>} map
  const parseErrorLineMap = (errors) => {
    const map = {}
    const re = /on\s+([^\s,]+\.tf)\s+line\s+(\d+)/gi
    for (const e of errors || []) {
      let m
      while ((m = re.exec(e)) !== null) {
        const fn = m[1]
        const ln = parseInt(m[2], 10)
        if (!map[fn]) map[fn] = new Set()
        map[fn].add(ln)
      }
    }
    return map
  }

  const enterManualFix = (stage, errors, fileList) => {
    if (!fileList || !fileList.length) return
    setManualFixMode({ stage, errors: errors || [], lineMap: parseErrorLineMap(errors) })
    setManualFixFiles(fileList.map(f => ({ filename: f.filename, content: f.content })))
    setManualActiveTab(0)
  }

  const run = async (filesOverride) => {
    reset()
    setRunning(true)
    // Guard: if called from an onClick that passed a SyntheticEvent, ignore it
    const filesToSend = Array.isArray(filesOverride) ? filesOverride : files

    // Use fetch for POST+SSE (EventSource only supports GET)
    const controller = new AbortController()
    abortRef.current = controller

    try {
      const response = await fetch('/api/terraform/run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ files: filesToSend, cloud, run_plan: runPlan, env_vars: creds }),
        signal: controller.signal,
      })

      if (!response.ok) {
        const text = await response.text()
        throw new Error(`HTTP ${response.status}: ${text}`)
      }

      // Overall 8-minute timeout guard
      let overallTimer = setTimeout(() => {
        controller.abort()
        setError({ message: 'Pipeline timed out after 8 minutes. Click ↻ Regenerate or Re-run to retry.' })
        setRunning(false)
      }, 8 * 60 * 1000)

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done: readerDone, value } = await reader.read()
        if (readerDone) break
        buffer += decoder.decode(value, { stream: true })

        // SSE lines come as "event: X\ndata: {...}\n\n"
        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() ?? ''   // keep incomplete trailing block

        // Collect all log lines from this chunk for a single state update
        const logBatch = []

        for (const block of blocks) {
          let eventType = 'message'
          let dataStr   = ''
          for (const line of block.split('\n')) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim()
            if (line.startsWith('data: '))  dataStr   = line.slice(6).trim()
          }
          if (!dataStr) continue
          let payload
          try { payload = JSON.parse(dataStr) } catch { continue }

          switch (eventType) {
            case 'stage':
              if (payload.stage === 'codex_fix' || payload.stage === 'deterministic_fix') {
                setAiFixStatus({ stage: payload.stage, attempt: payload.attempt, message: payload.message })
              } else {
                setStage(payload.stage, { status: 'running', message: payload.message })
                setAiFixStatus(null)
              }
              break

            case 'stage_done':
              if (payload.stage === 'codex_fix' || payload.stage === 'deterministic_fix') {
                setAiFixStatus(null)
              } else {
                // Non-blocking tools (tflint/tfsec): show warning if they found issues
                const nonBlocking = payload.non_blocking === true
                const foundIssues = nonBlocking && payload.rc != null && payload.rc !== 0
                // Validate that exhausted retries but continues: show as warning not failed
                const isPartial = payload.partial === true
                setStage(payload.stage, {
                  status:      payload.skipped ? 'skipped'
                             : foundIssues     ? 'warning'
                             : isPartial       ? 'warning'
                             : payload.passed  ? 'passed'
                             :                   'failed',
                  attempts:    payload.attempts,
                  summary:     payload.summary,
                  nonBlocking,
                  message:     payload.message,
                })
                if (payload.summary) setPlanSummary(payload.summary)
              }
              break

            case 'log':
              logBatch.push({ stage: payload.stage, line: payload.line })
              break

            case 'init_errors':
              // Store files before fix for diff view
              setFilesBeforeFix(prev => ({ ...prev, init: files }))
              setValErrors({ errors: payload.errors, attempt: payload.attempt })
              break

            case 'validate_errors':
              // Store files before fix for diff view
              setFilesBeforeFix(prev => ({ ...prev, validate: files }))
              setValErrors({ errors: payload.errors, attempt: payload.attempt })
              break

            case 'plan_errors':
              // Store files before fix for diff view
              setFilesBeforeFix(prev => ({ ...prev, plan: files }))
              setPlanErrors({ errors: payload.errors, attempt: payload.attempt })
              break

            case 'files_updated':
              if (onFilesUpdated && payload.files) {
                onFilesUpdated(payload.files)
                
                // If this is a fix stage, create diff data
                if (payload.stage === 'codex_fix' && payload.changes?.length > 0) {
                  const beforeFiles = filesBeforeFix[payload.stage === 'codex_fix' ? 
                    (stageState.validate?.status === 'running' || valErrors ? 'validate' : 
                     stageState.init?.status === 'running' ? 'init' : 'plan') : '']
                  
                  if (beforeFiles && beforeFiles.length > 0 && payload.changes[0]) {
                    // Extract the first change description to show in diff
                    const changeDesc = payload.changes[0]
                    
                    // Try to find which file was changed based on the description
                    const changedFile = payload.files.find(f => 
                      changeDesc.toLowerCase().includes(f.filename.toLowerCase()) ||
                      changeDesc.toLowerCase().includes(f.filename.replace(/^.*\//, '').toLowerCase())
                    )
                    
                    if (changedFile) {
                      const beforeFile = beforeFiles.find(f => f.filename === changedFile.filename)
                      if (beforeFile) {
                        // Extract relevant snippet (first 20 lines or around error)
                        const beforeLines = beforeFile.content.split('\n').slice(0, 25).join('\n')
                        const afterLines = changedFile.content.split('\n').slice(0, 25).join('\n')
                        
                        const diffData = {
                          before: beforeLines + (beforeFile.content.split('\n').length > 25 ? '\n...' : ''),
                          after: afterLines + (changedFile.content.split('\n').length > 25 ? '\n...' : ''),
                          filename: changedFile.filename,
                          changes: payload.changes
                        }
                        
                        // Set diff data based on which stage is running
                        if (valErrors) {
                          setValDiffData(diffData)
                        } else if (planErrors) {
                          setPlanDiffData(diffData)
                        }
                      }
                    }
                  }
                }
              }
              break

            case 'done': {
              clearTimeout(overallTimer)
              const passed = payload.passed !== false
              setDone(true)
              setRunning(false)
              if (payload.plan_summary) setPlanSummary(payload.plan_summary)
              if (payload.plan_skipped) setPlanSkipped(payload.plan_skip_reason || 'Plan skipped')
              if (payload.validate_errors_persistent?.length) {
                setPersistentValErrors(payload.validate_errors_persistent)
              }
              if (payload.files) {
                setFinalFiles(payload.files)
                if (onFilesUpdated) onFilesUpdated(payload.files)
              }
              if (passed) {
                if (onValidationDone) onValidationDone({ passed: true, plan_summary: payload.plan_summary })
                const hasValWarnings = payload.validate_errors_persistent?.length > 0
                toast.success(
                  payload.plan_skipped
                    ? 'Validation passed ✓' + (hasValWarnings ? ' (with manual-fix items)' : '')
                    : 'Terraform plan completed' + (hasValWarnings ? ' — some resources need manual fixes' : ' successfully')
                )
              } else {
                // Plan failed after AI retries — enter manual fix mode
                const planErrList = (planErrors && planErrors.errors) || []
                enterManualFix('plan', planErrList, payload.files || [])
                toast.error('Terraform plan finished with errors — manual fix required')
              }
              break
            }

            case 'error':
              clearTimeout(overallTimer)
              setError(payload)
              setRunning(false)
              if (payload.stage) setStage(payload.stage, { status: 'failed' })
              // If backend sent files alongside error, offer manual fix
              if (payload.files && payload.files.length) {
                enterManualFix(payload.stage || 'unknown', payload.errors || [payload.message], payload.files)
                toast.error((payload.message || 'Execution failed') + ' — manual fix required')
              } else {
                toast.error(payload.message || 'Terraform execution failed')
              }
              break

            default:
              break
          }
        }

        // Flush all log lines from this chunk in a single render
        if (logBatch.length > 0) {
          setLogs(prev => [...prev, ...logBatch])
        }
      }
      clearTimeout(overallTimer)
    } catch (err) {
      clearTimeout(overallTimer)
      if (err.name === 'AbortError') return
      setError({ message: err.message })
      setRunning(false)
      toast.error(err.message || 'Stream failed')
    }
  }

  const downloadArtifacts = async () => {
    if (!finalFiles || finalFiles.length === 0) {
      toast.error('No files to download')
      return
    }

    try {
      const zip = new JSZip()
      
      // Add all files maintaining folder structure
      finalFiles.forEach(file => {
        zip.file(file.filename, file.content)
      })

      // Generate ZIP file
      const blob = await zip.generateAsync({ type: 'blob' })
      
      // Download the ZIP
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `terraform-${cloud}-${Date.now()}.zip`
      a.click()
      URL.revokeObjectURL(url)
      
      toast.success('Downloaded Terraform artifacts as ZIP')
    } catch (err) {
      toast.error(`Download failed: ${err.message}`)
    }
  }

  const stop = () => {
    abortRef.current?.abort()
    setRunning(false)
    setLogs(prev => [...prev, { stage: 'system', line: '— Execution stopped by user —' }])
  }

  const visibleLogs = logFilter === 'all'
    ? logs
    : logs.filter(l => l.stage === logFilter)

  const stageKeys = ['fmt', 'init', 'validate', 'plan']
  const hasAnyRun = Object.keys(stageState).length > 0 || logs.length > 0

  return (
    <div className="mt-5 rounded-xl border border-indigo-500/30 bg-gray-900/40 overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-800 bg-gray-950">
        <div>
          <h4 className="text-sm font-bold text-white flex items-center gap-2">
            ⚡ Real Terraform Execution
          </h4>
          <p className="text-[11px] text-gray-500">fmt init validate plan</p>
        </div>
        <div className="flex items-center gap-2">
          {onRegenerate && (
            <button
              onClick={onRegenerate}
              disabled={running}
              title="Go back to Terraform step and regenerate code from scratch"
              className="px-3 py-1.5 text-xs rounded-lg border border-amber-500/40 bg-amber-500/10 text-amber-300 hover:bg-amber-500/20 font-medium transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
            >
              ⟳ Regenerate
            </button>
          )}
          <button
            onClick={() => setShowCreds(v => !v)}
            className={`px-3 py-1.5 text-xs rounded-lg border font-medium transition-colors ${
              showCreds
                ? 'bg-indigo-500/20 border-indigo-500/50 text-indigo-300'
                : 'bg-gray-800 border-gray-700 text-gray-400 hover:text-gray-200'
            }`}
          >
            🔑 Credentials
          </button>
          <label className="flex items-center gap-1.5 text-xs text-gray-400 cursor-pointer select-none" title="Requires AWS/Azure/GCP credentials">
            <input
              type="checkbox"
              checked={runPlan}
              onChange={e => setRunPlan(e.target.checked)}
              disabled={running}
              className="accent-indigo-500"
            />
            Run plan
          </label>
          {running ? (
            <button
              onClick={stop}
              className="px-3 py-1.5 text-xs rounded-lg bg-red-600/80 hover:bg-red-500 text-white font-medium"
            >
              ✕ Stop
            </button>
          ) : (
            <button
              onClick={run}
              className="px-3 py-1.5 text-xs rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-semibold"
            >
              {hasAnyRun ? '↻ Re-run' : '▶ Run'}
            </button>
          )}
        </div>
      </div>

      {/* Credentials panel */}
      {showCreds && (
        <div className="px-4 py-4 border-b border-gray-800 bg-gray-950/60">
          <p className="text-xs text-gray-400 mb-3">
            Enter credentials to enable <strong className="text-indigo-400">terraform plan</strong>. Values are sent only to your local backend and never stored.
          </p>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {['aws', 'azure', 'gcp'].map(c => (
              <CredentialsPanel key={c} cloud={c} creds={creds} onChange={updateCred} />
            ))}
          </div>
          <p className="text-[10px] text-gray-600 mt-2">
            💡 Enable "Run plan" checkbox above after entering credentials.
          </p>
        </div>
      )}

      {/* Stage pipeline + compact AI Fix Loop indicator */}
      <div className="px-4 pt-3 pb-3 border-b border-gray-800">
        <div className="flex items-center justify-between gap-3 flex-wrap">
          {/* Stage badges row */}
          <div className="flex items-center gap-4 overflow-x-auto">
            {STAGES.map((stage, i) => {
              const stageStatus = stageState[stage.key]?.status
              const isDone = stageStatus === 'passed' || stageStatus === 'warning'
              return (
                <div key={stage.key} className="flex items-center gap-4 shrink-0">
                  <StageBadge stageKey={stage.key} stageState={stageState} stageStartTimes={stageStartTimes} aiFixActive={aiFixStatus} />
                  {i < STAGES.length - 1 && (
                    <span className={`text-2xl font-bold transition-colors ${
                      isDone ? 'text-green-500' : 'text-gray-700'
                    }`}>→</span>
                  )}
                </div>
              )
            })}
          </div>
          {/* AI Fix status - only show when actively fixing */}
          {aiFixStatus && (
            <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full bg-indigo-500/20 border border-indigo-500/40 text-indigo-200 text-[10px] font-medium animate-pulse max-w-[260px] truncate">
              {aiFixStatus.message}
            </span>
          )}
        </div>
      </div>

      {/* Validate errors (live) */}
      {valErrors && (
        <div className="px-4 py-2 border-b border-gray-800">
          <ValidationErrors errors={valErrors.errors} attempt={valErrors.attempt} diffData={valDiffData} />
        </div>
      )}

      {/* Plan errors (live) */}
      {planErrors && (
        <div className="px-4 py-2 border-b border-gray-800">
          <PlanErrors errors={planErrors.errors} attempt={planErrors.attempt} diffData={planDiffData} />
        </div>
      )}

      {/* ───── Manual Fix mode (after AI fix loop exhausts 3 retries) ───── */}
      {manualFixMode && (
        <div className="px-4 py-3 border-b border-gray-800 bg-amber-500/5">
          <div className="flex items-center justify-between gap-3 mb-3 flex-wrap">
            <div>
              <p className="text-sm font-bold text-amber-300 flex items-center gap-2">
                🛠 Manual Fix Required
                <span className="text-[10px] uppercase tracking-wider px-2 py-0.5 rounded-full bg-amber-500/20 border border-amber-500/40">
                  stage: {manualFixMode.stage}
                </span>
              </p>
              <p className="text-[11px] text-amber-200/70 mt-0.5">
                Auto-fix couldn't resolve all errors after 2 attempts. Edit the highlighted lines below, then re-run.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                onClick={() => setManualFixMode(null)}
                className="px-3 py-1.5 text-xs rounded-lg bg-gray-800 border border-gray-700 text-gray-400 hover:text-gray-200"
              >
                Dismiss
              </button>
              <button
                onClick={() => {
                  if (onFilesUpdated) onFilesUpdated(manualFixFiles)
                  run(manualFixFiles)
                }}
                disabled={running}
                className="px-3 py-1.5 text-xs rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-semibold disabled:opacity-50"
              >
                💾 Save & Re-run
              </button>
            </div>
          </div>

          {/* Error list with line numbers prominently displayed + jump buttons */}
          {manualFixMode.errors?.length > 0 && (
            <div className="mb-3 p-3 rounded-lg bg-red-500/10 border-2 border-red-500/40 max-h-48 overflow-y-auto">
              <p className="text-xs font-bold text-red-300 mb-2 uppercase tracking-wider flex items-center gap-2">
                <span className="text-lg">⚠️</span>
                {manualFixMode.errors.length} Unresolved Error{manualFixMode.errors.length !== 1 ? 's' : ''}
              </p>
              <div className="space-y-1.5">
                {manualFixMode.errors.map((e, i) => {
                  // Extract filename and line number from error message (e.g., "main.tf:450 — Error message")
                  const match = e.match(/^([^:]+):(\d+)\s*[—-]\s*(.+)$/)
                  const filename = match?.[1] || ''
                  const lineNum = match?.[2] || ''
                  const message = match?.[3] || e
                  
                  // Find the file index for this error
                  const fileIdx = manualFixFiles.findIndex(f => f.filename === filename)
                  
                  return (
                    <div key={i} className="p-2 rounded bg-red-900/20 border border-red-500/30">
                      <div className="flex items-start gap-2">
                        <span className="text-red-400 font-bold text-xs shrink-0">🔴</span>
                        <div className="flex-1 min-w-0">
                          {filename && lineNum && (
                            <div className="flex items-center gap-2 mb-1">
                              <div className="text-[10px] font-bold text-red-300 font-mono">
                                {filename} <span className="text-red-400">Line {lineNum}</span>
                              </div>
                              {fileIdx >= 0 && (
                                <button
                                  onClick={() => {
                                    // Switch to the file tab
                                    setManualActiveTab(fileIdx)
                                    // Scroll to the line after a short delay for tab switch
                                    setTimeout(() => {
                                      const editorDiv = document.querySelector('.manual-fix-editor-scroll')
                                      if (editorDiv && lineNum) {
                                        const targetLine = parseInt(lineNum) - 1
                                        const lineHeight = 20 // 1.25rem = 20px
                                        editorDiv.scrollTop = targetLine * lineHeight - 100 // Offset to center
                                      }
                                    }, 50)
                                  }}
                                  className="px-2 py-0.5 text-[9px] font-bold rounded bg-red-500 hover:bg-red-400 text-white uppercase tracking-wide transition-colors"
                                >
                                  ➜ Jump to Line
                                </button>
                              )}
                            </div>
                          )}
                          <div className="text-[11px] text-red-200/90 leading-snug break-words">
                            {message}
                          </div>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          )}

          {/* File tabs */}
          <div className="rounded-xl border border-gray-700 overflow-hidden">
            <div className="flex overflow-x-auto border-b border-gray-800 bg-gray-950">
              {manualFixFiles.map((f, i) => {
                const flagged = manualFixMode.lineMap?.[f.filename]?.size > 0
                return (
                  <button
                    key={f.filename}
                    onClick={() => setManualActiveTab(i)}
                    className={`flex items-center gap-1.5 px-3 py-2 text-xs font-mono whitespace-nowrap border-r border-gray-800 transition-colors ${
                      manualActiveTab === i
                        ? 'bg-gray-800 text-white border-b-2 border-b-amber-500'
                        : 'text-gray-500 hover:text-gray-300'
                    }`}
                  >
                    {flagged && <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block shrink-0" title="Has flagged lines" />}
                    {f.filename}
                    {flagged && (
                      <span className="text-[9px] text-red-400 ml-1">
                        ({manualFixMode.lineMap[f.filename].size} err)
                      </span>
                    )}
                  </button>
                )
              })}
            </div>

            {/* Editable file content with line numbers + PROMINENT error line highlighting */}
            {manualFixFiles[manualActiveTab] && (() => {
              const f = manualFixFiles[manualActiveTab]
              const flaggedLines = manualFixMode.lineMap?.[f.filename] || new Set()
              const lines = f.content.split('\n')
              const errorLineNumbers = Array.from(flaggedLines).sort((a, b) => a - b)
              
              return (
                <div className="flex bg-gray-900 relative" style={{ maxHeight: '28rem' }}>
                  {/* Sticky line number gutter with red error indicators */}
                  <div className="sticky left-0 z-10 overflow-hidden shrink-0 bg-gray-950 select-none border-r-2 border-gray-800 py-2 pr-3 pl-2 text-right font-mono text-xs leading-5" style={{ minWidth: '4rem' }}>
                    {lines.map((_, i) => {
                      const ln = i + 1
                      const flagged = flaggedLines.has(ln)
                      return (
                        <div 
                          key={i} 
                          className={`leading-5 transition-all ${
                            flagged 
                              ? 'text-red-300 font-extrabold bg-red-600/40 px-1.5 -mx-1 rounded shadow-lg' 
                              : 'text-gray-600'
                          }`}
                        >
                          {flagged ? `❌ ${ln}` : ln}
                        </div>
                      )
                    })}
                  </div>
                  {/* Editable textarea with EXTREME error line highlighting */}
                  <div className="flex-1 relative overflow-auto manual-fix-editor-scroll">
                    {/* Background layer with THICK RED LEFT BORDER + red underlines for error lines */}
                    <div className="absolute inset-0 p-2 font-mono text-xs leading-5 pointer-events-none whitespace-pre">
                      {lines.map((line, i) => {
                        const isError = flaggedLines.has(i + 1)
                        return (
                          <div 
                            key={i} 
                            className={isError 
                              ? 'bg-red-600/30 border-l-4 border-red-500 border-b-2 border-b-red-500 font-bold pl-2 shadow-lg animate-pulse' 
                              : ''
                            }
                            style={{ minHeight: '1.25rem' }}
                          >
                            {isError ? `▶ ${line}` : ' '}
                          </div>
                        )
                      })}
                    </div>
                    {/* Editable textarea */}
                    <textarea
                      value={f.content}
                      onChange={(e) => {
                        const next = [...manualFixFiles]
                        next[manualActiveTab] = { ...f, content: e.target.value }
                        setManualFixFiles(next)
                      }}
                      spellCheck={false}
                      className="relative w-full p-2 font-mono text-xs leading-5 bg-transparent text-gray-200 outline-none resize-none whitespace-pre"
                      style={{ minHeight: '28rem' }}
                    />
                  </div>
                </div>
              )
            })()}

            <div className="px-3 py-2 border-t border-gray-800 bg-gray-950 flex items-center justify-between">
              <span className="flex items-center gap-3 text-[10px] text-gray-400">
                {(() => {
                  const currentFile = manualFixFiles[manualActiveTab]
                  const flaggedLines = currentFile ? (manualFixMode.lineMap?.[currentFile.filename] || new Set()) : new Set()
                  const errorLines = Array.from(flaggedLines).sort((a, b) => a - b)
                  return (
                    <span className="flex items-center gap-1.5 font-bold text-red-300">
                      ❌ Error lines: {errorLines.length > 0 ? errorLines.join(', ') : 'none'}
                    </span>
                  )
                })()}
                <span className="text-gray-600">|</span>
                <span>▶ Thick red left border = error line — Click "Jump to Line" button to navigate</span>
              </span>
              <span className="font-mono text-gray-600 text-[10px]">{manualFixFiles[manualActiveTab]?.filename}</span>
            </div>
          </div>
        </div>
      )}

      {/* Plan summary + download + file viewer */}
      {(planSummary || (done && finalFiles?.length)) && (
        <div className="px-4 pt-2 border-b border-gray-800 pb-3">
          {(planSummary || persistentValErrors.length > 0) && <PlanSummary summary={planSummary} persistentValErrors={persistentValErrors} />}
          {done && finalFiles?.length > 0 && (
            <>
              {/* Download button row */}
              <div className="mt-3 flex items-center gap-3">
                <button
                  onClick={downloadArtifacts}
                  className="flex items-center gap-2 px-4 py-2 rounded-lg bg-emerald-600/20 border border-emerald-500/40 text-emerald-300 text-xs font-semibold hover:bg-emerald-600/30 hover:border-emerald-400/60 transition-colors"
                >
                  ⬇ Download Terraform Artifacts
                  <span className="text-[10px] text-emerald-500 font-normal">
                    ({finalFiles.length} file{finalFiles.length !== 1 ? 's' : ''})
                  </span>
                </button>
                <p className="text-[10px] text-gray-600">
                  Review <span className="text-red-400 font-mono">ARCHLENS DEFAULT</span> markers before applying.
                </p>
              </div>

              {/* Multi-file tabbed viewer */}
              <div className="mt-4 rounded-xl border border-gray-700 overflow-hidden">
                {/* File tabs */}
                <div className="flex overflow-x-auto border-b border-gray-800 bg-gray-950">
                  {finalFiles.map((f, i) => {
                    const hasDefault = f.content?.includes('ARCHLENS DEFAULT')
                    return (
                      <button
                        key={f.filename}
                        onClick={() => setActiveFileTab(i)}
                        className={`flex items-center gap-1.5 px-3 py-2 text-xs font-mono whitespace-nowrap border-r border-gray-800 transition-colors ${
                          activeFileTab === i
                            ? 'bg-gray-800 text-white border-b-2 border-b-indigo-500'
                            : 'text-gray-500 hover:text-gray-300'
                        }`}
                      >
                        {hasDefault && <span className="w-1.5 h-1.5 rounded-full bg-red-500 inline-block shrink-0" title="Contains ARCHLENS DEFAULT" />}
                        {f.filename}
                      </button>
                    )
                  })}
                </div>
                {/* File content with line numbers */}
                {finalFiles[activeFileTab] && (() => {
                  const content = finalFiles[activeFileTab].content || ''
                  const lineCount = (content.match(/\n/g) || []).length + 1
                  return (
                    <div className="flex bg-gray-900 overflow-hidden" style={{ maxHeight: '22rem' }}>
                      <div className="overflow-hidden shrink-0 bg-gray-950 select-none border-r border-gray-800 py-3 pr-3 pl-2 text-right text-gray-600 font-mono text-xs leading-5" style={{ minWidth: '3rem' }}>
                        {Array.from({ length: lineCount }, (_, i) => (
                          <div key={i} className="leading-5">{i + 1}</div>
                        ))}
                      </div>
                      <pre className="flex-1 overflow-auto p-3 text-xs font-mono leading-5 text-gray-200 whitespace-pre">
                        {content.split('\n').map((line, i) => {
                          const isDefault = line.includes('ARCHLENS DEFAULT') || line.includes('│ ⚠') || line.includes('┌─────') || line.includes('└─────')
                          return (
                            <div key={i} className={isDefault ? 'bg-red-500/10 text-red-300' : ''}>
                              {line || ' '}
                            </div>
                          )
                        })}
                      </pre>
                    </div>
                  )
                })()}
                {/* Footer */}
                <div className="flex items-center justify-between px-3 py-1.5 border-t border-gray-800 bg-gray-950">
                  <span className="text-[10px] text-gray-600 font-mono">{finalFiles[activeFileTab]?.filename}</span>
                  <button
                    onClick={() => {
                      const f = finalFiles[activeFileTab]
                      if (!f) return
                      const blob = new Blob([f.content], { type: 'text/plain' })
                      const url = URL.createObjectURL(blob)
                      const a = document.createElement('a')
                      a.href = url; a.download = f.filename; a.click()
                      URL.revokeObjectURL(url)
                    }}
                    className="text-[10px] text-emerald-400 hover:text-emerald-300 font-medium"
                  >
                    ⬇ {finalFiles[activeFileTab]?.filename}
                  </button>
                </div>
              </div>
            </>
          )}
        </div>
      )}

      {/* Plan skipped notice */}
      {planSkipped && (
        <div className="mx-4 my-3 p-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 flex items-start gap-2">
          <span className="text-yellow-400 mt-0.5">⚠</span>
          <div>
            <p className="text-xs font-semibold text-yellow-300">Plan skipped</p>
            <p className="text-xs text-yellow-200/70 mt-0.5">{planSkipped}</p>
          </div>
        </div>
      )}

      {/* Fatal error */}
      {error && (
        <div className="mx-4 my-3 p-3 rounded-lg bg-red-500/10 border border-red-500/30">
          <p className="text-xs font-semibold text-red-400 mb-1">
            ✗ {error.stage ? `Error in ${error.stage}` : 'Execution failed'}
          </p>
          <p className="text-xs text-red-300 font-mono">{error.message}</p>
          {error.output && (
            <pre className="mt-2 text-[10px] text-gray-400 max-h-32 overflow-y-auto">{error.output}</pre>
          )}
        </div>
      )}

      {/* Log console */}
      {hasAnyRun && (
        <div>
          {/* Log filter tabs */}
          <div className="flex items-center gap-0 border-b border-gray-800 bg-gray-950 overflow-x-auto">
            {['all', ...stageKeys].map(k => {
              const count = k === 'all'
                ? logs.length
                : logs.filter(l => l.stage === k).length
              const stage = STAGES.find(s => s.key === k)
              return (
                <button
                  key={k}
                  onClick={() => setLogFilter(k)}
                  className={`flex items-center gap-1 px-3 py-2 text-[11px] font-medium whitespace-nowrap border-r border-gray-800 transition-colors ${
                    logFilter === k ? 'bg-gray-800 text-white' : 'text-gray-500 hover:text-gray-300'
                  }`}
                >
                  {k === 'all' ? `All (${count})` : `${stage?.icon} ${stage?.label} (${count})`}
                </button>
              )
            })}
          </div>

          {/* Log output */}
          <div className="h-48 overflow-y-auto bg-gray-950 p-3 font-mono text-[11px] leading-5">
            {visibleLogs.length === 0 ? (
              <span className="text-gray-700">No output for this stage yet…</span>
            ) : (
              visibleLogs.map((l, i) => {
                const isDefault = l.line.includes('ARCHLENS DEFAULT') ||
                  l.line.includes('│ ⚠') ||
                  l.line.includes('┌─────') ||
                  l.line.includes('└─────')
                const isRemoved = l.line.includes('ARCHLENS: removed')
                return (
                  <div key={i} className={
                    isDefault ? 'text-red-300 bg-red-500/10 px-1 rounded' :
                    isRemoved ? 'text-orange-300 bg-orange-500/8 px-1 rounded' :
                    l.line.includes('Error') || l.line.includes('error') ? 'text-red-400' :
                    l.line.includes('Warning') || l.line.includes('warn') ? 'text-yellow-400' :
                    l.stage === 'system' ? 'text-gray-600 italic' :
                    'text-gray-400'
                  }>
                    {logFilter === 'all' && (
                      <span className="text-gray-700 mr-2 select-none">[{l.stage}]</span>
                    )}
                    {l.line}
                  </div>
                )
              })
            )}
            <div ref={logEndRef} />
          </div>
        </div>
      )}

      {!hasAnyRun && !running && (
        <div className="px-4 py-8 text-center">
          <p className="text-gray-500 text-sm">
            Click <strong className="text-indigo-400">▶ Run</strong> to execute terraform against the generated code.
          </p>
          <p className="text-gray-600 text-xs mt-1">
            Requires terraform {'>'}= 1.5 in PATH — provider downloads are cached in ~/.archlens/tf-plugin-cache
          </p>
        </div>
      )}
    </div>
  )
}
