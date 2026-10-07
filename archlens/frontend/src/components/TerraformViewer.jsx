import { useState, useEffect } from 'react'
import toast from 'react-hot-toast'
import { Prism as SyntaxHighlighter } from 'react-syntax-highlighter'
import { vscDarkPlus } from 'react-syntax-highlighter/dist/esm/styles/prism'

const CLOUD_META = {
  aws: { label: 'AWS', emoji: '🟠', color: 'text-orange-400', border: 'border-orange-500/40' },
  azure: { label: 'Azure', emoji: '🔵', color: 'text-blue-400', border: 'border-blue-500/40' },
  gcp: { label: 'GCP', emoji: '🟢', color: 'text-green-400', border: 'border-green-500/40' },
}

function copyToClipboard(text) {
  navigator.clipboard.writeText(text).then(() => toast.success('Copied to clipboard'))
}

function downloadFile(filename, content) {
  const blob = new Blob([content], { type: 'text/plain' })
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

function downloadAll(files, cloud) {
  // Create a simple zip-like download of all files concatenated with headers
  const combined = files.map((f) => `# === ${f.filename} ===\n${f.content}`).join('\n\n')
  downloadFile(`archlens-${cloud}-terraform.tf`, combined)
}

export default function TerraformViewer({ analysis, terraformData, onTerraformLoaded, onBack, onReset, onNext, userContext }) {
  const [selectedCloud, setSelectedCloud] = useState(() => terraformData?.cloud || 'aws')
  const [loading, setLoading] = useState(false)
  const [progressMsg, setProgressMsg] = useState('')
  const [activeFile, setActiveFile] = useState(0)
  // Seed from the prop so navigating back restores the generated code
  const [generated, setGenerated] = useState(() => {
    if (terraformData?.cloud) return { [terraformData.cloud]: terraformData }
    return {}
  })

  // If parent updates terraformData (e.g. files fixed in validation), keep local cache in sync
  useEffect(() => {
    if (terraformData?.cloud) {
      setGenerated(prev => ({ ...prev, [terraformData.cloud]: terraformData }))
    }
  }, [terraformData])

  const handleGenerate = async (forceRegenerate = false) => {
    if (!forceRegenerate && generated[selectedCloud]) {
      onTerraformLoaded({ ...generated[selectedCloud], cloud: selectedCloud })
      return
    }
    setLoading(true)
    setProgressMsg('Generating Terraform code…')
    try {
      const response = await fetch('/api/terraform/stream', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          analysis,
          cloud: selectedCloud,
          include_modules: true,
          ...(userContext && Object.keys(userContext).length > 0 ? { user_context: userContext } : {}),
        }),
      })
      if (!response.ok) {
        const txt = await response.text()
        throw new Error(`HTTP ${response.status}: ${txt}`)
      }

      const reader  = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer    = ''

      // Step labels shown as the generation progresses
      const STEP_LABELS = {
        llm:      'Generating Terraform code…',
        hcl_fix:  'Fixing HCL syntax errors…',
        schema:   'Applying provider schema fixes…',
        finalize: 'Locking provider versions & defaults…',
        fmt:      'Running terraform fmt…',
      }

      while (true) {
        const { done, value } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() ?? ''

        for (const block of blocks) {
          let eventType = 'message', dataStr = ''
          for (const line of block.split('\n')) {
            if (line.startsWith('event: ')) eventType = line.slice(7).trim()
            if (line.startsWith('data: '))  dataStr   = line.slice(6).trim()
          }
          if (!dataStr) continue
          let payload
          try { payload = JSON.parse(dataStr) } catch { continue }

          if (eventType === 'progress') {
            setProgressMsg(STEP_LABELS[payload.step] || payload.message)
          } else if (eventType === 'done') {
            const enriched = { ...payload, cloud: selectedCloud }
            const updated  = { ...generated, [selectedCloud]: enriched }
            setGenerated(updated)
            onTerraformLoaded(enriched)
            setActiveFile(0)
            toast.success(`Terraform for ${selectedCloud.toUpperCase()} generated`)
          } else if (eventType === 'error') {
            throw new Error(payload.message || 'Generation failed')
          }
        }
      }
    } catch (err) {
      toast.error(err.message || 'Terraform generation failed')
    } finally {
      setLoading(false)
      setProgressMsg('')
    }
  }

  const currentData = generated[selectedCloud]

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h2 className="text-2xl font-bold text-white">Terraform Generator</h2>
          <p className="text-gray-400">Generate production-ready IaC for your chosen cloud</p>
        </div>
      </div>

      {/* Cloud selector */}
      <div className="flex gap-3 mb-6">
        {Object.entries(CLOUD_META).map(([cloud, meta]) => (
          <button
            key={cloud}
            onClick={() => { setSelectedCloud(cloud); setActiveFile(0) }}
            className={`flex-1 card border transition-all text-center py-4 ${
              selectedCloud === cloud ? meta.border : 'border-transparent hover:border-gray-700'
            }`}
          >
            <div className="text-2xl mb-1">{meta.emoji}</div>
            <div className={`font-semibold ${selectedCloud === cloud ? meta.color : 'text-gray-400'}`}>
              {meta.label}
            </div>
            {generated[cloud] && (
              <div className="text-xs text-green-400 mt-1">✓ Generated</div>
            )}
          </button>
        ))}
      </div>

      {/* Generate button */}
      {!currentData && (
        <div className="card text-center py-10 mb-6">
          <div className="text-5xl mb-4">⚙</div>
          <p className="text-gray-400 mb-1 font-medium">
            Generate Terraform for {CLOUD_META[selectedCloud].label}
          </p>
          <p className="text-gray-600 text-sm mb-5">
            Generates structured hierarchy: root files + modules/compute · modules/database · …
          </p>
          <button onClick={handleGenerate} disabled={loading} className="btn-primary">
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="animate-spin">⟳</span>
                <span className="text-xs truncate max-w-[240px]">{progressMsg || 'Generating…'}</span>
              </span>
            ) : (
              `Generate ${CLOUD_META[selectedCloud].label} Terraform`
            )}
          </button>
        </div>
      )}

      {/* Code viewer */}
      {currentData && (
        <div className="card mb-6">
          {/* Summary */}
          <div className="flex items-center justify-between mb-4">
            <div>
              <p className="font-medium text-white">{currentData.summary}</p>
              <p className="text-xs text-gray-500 mt-0.5">
                ~{currentData.estimated_resources} resources · {currentData.files.length} files
              </p>
            </div>
            <button
              onClick={() => downloadAll(currentData.files, selectedCloud)}
              className="btn-secondary text-sm"
            >
              ⬇ Download All
            </button>
          </div>

          {/* Grouped folder-tree tabs */}
          {(() => {
            const rootFiles = currentData.files.filter(f => !f.filename.includes('/'))
            const moduleDirs = {}
            currentData.files
              .filter(f => f.filename.includes('/'))
              .forEach(f => {
                const dir = f.filename.split('/').slice(0, -1).join('/')
                if (!moduleDirs[dir]) moduleDirs[dir] = []
                moduleDirs[dir].push(f)
              })
            return (
              <div className="mb-4 space-y-2">
                <div>
                  <p className="text-[10px] font-semibold text-gray-500 uppercase tracking-wider mb-1.5">📁 root</p>
                  <div className="flex gap-1 flex-wrap">
                    {rootFiles.map(f => {
                      const idx = currentData.files.indexOf(f)
                      const isExample = f.filename.endsWith('.example')
                      return (
                        <button
                          key={f.filename}
                          onClick={() => setActiveFile(idx)}
                          className={`px-2.5 py-1.5 text-xs rounded-lg font-mono transition-colors ${
                            activeFile === idx
                              ? 'bg-blue-600 text-white'
                              : isExample
                                ? 'bg-yellow-900/40 border border-yellow-700/40 text-yellow-300 hover:bg-yellow-800/40'
                                : 'bg-gray-800 text-gray-400 hover:bg-gray-700'
                          }`}
                        >
                          {f.filename}
                        </button>
                      )
                    })}
                  </div>
                </div>
                {Object.entries(moduleDirs).map(([dir, dirFiles]) => (
                  <div key={dir}>
                    <p className="text-[10px] font-semibold text-indigo-400/70 uppercase tracking-wider mb-1.5">
                      📦 {dir}
                    </p>
                    <div className="flex gap-1 flex-wrap pl-3">
                      {dirFiles.map(f => {
                        const idx = currentData.files.indexOf(f)
                        const shortName = f.filename.split('/').pop()
                        return (
                          <button
                            key={f.filename}
                            onClick={() => setActiveFile(idx)}
                            className={`px-2.5 py-1.5 text-xs rounded-lg font-mono transition-colors ${
                              activeFile === idx
                                ? 'bg-indigo-600 text-white'
                                : 'bg-gray-800/60 text-gray-400 hover:bg-gray-700'
                            }`}
                          >
                            {shortName}
                          </button>
                        )
                      })}
                    </div>
                  </div>
                ))}
              </div>
            )
          })()}

          {/* Active file */}
          {currentData.files[activeFile] && (
            <div>
              <div className="flex items-center justify-between mb-2">
                <div>
                  <span className="text-[10px] font-mono text-indigo-400/80 bg-indigo-500/10 border border-indigo-500/20 px-2 py-0.5 rounded">
                    {currentData.files[activeFile].filename}
                  </span>
                  {currentData.files[activeFile].description && (
                    <span className="text-xs text-gray-500 ml-2">{currentData.files[activeFile].description}</span>
                  )}
                </div>
                <button
                  onClick={() => copyToClipboard(currentData.files[activeFile].content)}
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors"
                >
                  Copy
                </button>
              </div>
              <div className="rounded-lg overflow-hidden border border-gray-800 max-h-[600px] overflow-y-auto">
                <SyntaxHighlighter
                  language="hcl"
                  style={vscDarkPlus}
                  customStyle={{ margin: 0, fontSize: '12px', background: '#0d1117' }}
                  showLineNumbers
                >
                  {currentData.files[activeFile].content}
                </SyntaxHighlighter>
              </div>
              <div className="flex justify-end mt-2">
                <button
                  onClick={() => downloadFile(currentData.files[activeFile].filename, currentData.files[activeFile].content)}
                  className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                >
                  ⬇ Download {currentData.files[activeFile].filename}
                </button>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Switch cloud */}
      {currentData && (
        <div className="card mb-4 flex items-center justify-between">
          <p className="text-sm text-gray-400">Want Terraform for another cloud?</p>
          <div className="flex gap-2">
            {Object.entries(CLOUD_META)
              .filter(([c]) => c !== selectedCloud)
              .map(([cloud, meta]) => (
                <button
                  key={cloud}
                  onClick={() => { setSelectedCloud(cloud); setActiveFile(0) }}
                  className="btn-secondary text-sm"
                >
                  {meta.emoji} {meta.label}
                </button>
              ))}
          </div>
        </div>
      )}

      <div className="flex gap-3 mt-6">
        <button className="btn-secondary" onClick={onBack}>← Back</button>
        {currentData && (
          <button onClick={() => handleGenerate(true)} disabled={loading} className="btn-secondary">
            {loading ? '⟳' : '↻ Regenerate'}
          </button>
        )}
        {currentData && onNext && (
          <button className="btn-primary flex-1 flex items-center justify-center gap-2" onClick={onNext}>
            🔬 Validate →
          </button>
        )}
        <button className={`${currentData && onNext ? 'btn-secondary' : 'btn-primary flex-1'}`} onClick={onReset}>
          + New Diagram
        </button>
      </div>
    </div>
  )
}
