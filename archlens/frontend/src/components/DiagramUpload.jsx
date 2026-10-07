import { useCallback, useState, useEffect, useRef } from 'react'
import { useDropzone } from 'react-dropzone'
import axios from 'axios'
import toast from 'react-hot-toast'
import UserContextPanel from './UserContextPanel'
import Logo from './Logo'
import ArchLensParticleBackground from './ArchLensParticleBackground'

const MAX_SIZE_MB = 20
const DRAWIO_EXTS = ['.drawio', '.drawio.svg', '.drawio.xml', '.xml']

const ANALYSIS_STEPS = [
  'Reading diagram structure…',
  'Identifying cloud services…',
  'Mapping components…',
  'Detecting connections…',
  'Finalizing analysis…',
]

const SAMPLES = [
  { file: 'aws-3tier-web-app.drawio', label: 'AWS 3-Tier Web App', emoji: '🟠', desc: '15 components: CloudFront, ALB, EC2, RDS, ElastiCache' },
  { file: 'azure-microservices-aks.drawio', label: 'Azure AKS Microservices', emoji: '🔵', desc: '17 components: Front Door, AKS, Cosmos, Service Bus' },
  { file: 'gcp-serverless-data-pipeline.drawio', label: 'GCP Serverless Pipeline', emoji: '🟢', desc: '17 components: Cloud Run, Pub/Sub, Dataflow, BigQuery' },
  { file: 'cloud-agnostic-microservices.drawio', label: 'Cloud-Agnostic Microservices', emoji: '⚪', desc: '19 components: API Gateway, Kafka, PostgreSQL, Redis' },
]

function isDrawioFile(file) {
  const name = (file?.name || '').toLowerCase()
  return DRAWIO_EXTS.some((ext) => name.endsWith(ext))
}

function readAsDataURL(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsDataURL(file)
  })
}

function readAsText(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(reader.result)
    reader.onerror = reject
    reader.readAsText(file)
  })
}

export default function DiagramUpload({ onAnalyzed, onDiagramChange, userContext, onUserContextChange }) {
  const [preview, setPreview] = useState(null)
  const [file, setFile] = useState(null)
  const [fileKind, setFileKind] = useState(null) // 'image' | 'drawio'
  const [loading, setLoading] = useState(false)
  const [loadingStep, setLoadingStep] = useState(0)
  const stepTimerRef = useRef(null)

  // Cycle through progress messages while loading
  useEffect(() => {
    if (loading) {
      setLoadingStep(0)
      stepTimerRef.current = setInterval(() => {
        setLoadingStep(s => Math.min(s + 1, ANALYSIS_STEPS.length - 1))
      }, 3500)
    } else {
      clearInterval(stepTimerRef.current)
    }
    return () => clearInterval(stepTimerRef.current)
  }, [loading])

  const onDrop = useCallback((accepted) => {
    const f = accepted[0]
    if (!f) return
    if (f.size > MAX_SIZE_MB * 1024 * 1024) {
      toast.error(`File too large. Max ${MAX_SIZE_MB}MB.`)
      return
    }
    setFile(f)
    if (isDrawioFile(f)) {
      setFileKind('drawio')
      setPreview(null)
      if (onDiagramChange) onDiagramChange({ preview: null, filename: f.name, kind: 'drawio' })
    } else {
      const url = URL.createObjectURL(f)
      setFileKind('image')
      setPreview(url)
      if (onDiagramChange) onDiagramChange({ preview: url, filename: f.name, kind: 'image' })
    }
  }, [onDiagramChange])

  const { getRootProps, getInputProps, isDragActive } = useDropzone({
    onDrop,
    accept: {
      'image/*': ['.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg'],
      'text/plain': ['.drawio', '.xml'],
      'application/xml': ['.xml', '.drawio'],
      'text/xml': ['.xml', '.drawio'],
      'application/vnd.jgraph.mxfile': ['.drawio'],
      'application/octet-stream': ['.drawio'],
    },
    multiple: false,
    maxSize: MAX_SIZE_MB * 1024 * 1024,
  })

  const handleAnalyze = async () => {
    if (!file) return
    setLoading(true)
    try {
      let payload
      if (fileKind === 'drawio') {
        const dataUrl = await readAsDataURL(file)
        payload = { drawio_xml: dataUrl, source_filename: file.name }
      } else {
        const dataUrl = await readAsDataURL(file)
        const base64 = dataUrl.split(',')[1]
        payload = {
          image_base64: base64,
          mime_type: file.type || 'image/png',
          source_filename: file.name,
        }
      }
      if (userContext && Object.keys(userContext).length > 0) {
        payload.user_context = userContext
      }

      const { data } = await axios.post('/api/analyze', payload)
      toast.success(`Detected ${data.components.length} components`)
      onAnalyzed(data)
    } catch (err) {
      const msg = err.response?.data?.detail || err.message
      toast.error(`Analysis failed: ${msg}`)
    } finally {
      setLoading(false)
    }
  }

  const loadSample = async (sampleFile) => {
    setLoading(true)
    try {
      const res = await axios.get(`/samples/${sampleFile}`, { responseType: 'text' })
      const xml = res.data
      const blob = new Blob([xml], { type: 'application/xml' })
      const fakeFile = new File([blob], sampleFile, { type: 'application/xml' })
      setFile(fakeFile)
      setFileKind('drawio')
      setPreview(null)
      toast.success(`Loaded sample: ${sampleFile}`)

      if (onDiagramChange) onDiagramChange({ preview: null, filename: sampleFile, kind: 'drawio' })
      const { data } = await axios.post('/api/analyze', {
        drawio_xml: xml,
        source_filename: sampleFile,
        ...(userContext && Object.keys(userContext).length > 0 ? { user_context: userContext } : {}),
      })
      toast.success(`Detected ${data.components.length} components`)
      onAnalyzed(data)
    } catch (err) {
      const msg = err.response?.data?.detail || err.message
      toast.error(`Sample failed: ${msg}`)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-5xl mx-auto">
      <section className="relative overflow-hidden rounded-3xl border border-blue-400/10 bg-gray-950/40 px-4 py-8 shadow-2xl shadow-blue-950/10 sm:px-8">
        <div className="absolute inset-0 bg-[radial-gradient(circle_at_left_center,rgba(59,130,246,0.2),transparent_36%),radial-gradient(circle_at_right_center,rgba(139,92,246,0.18),transparent_36%),linear-gradient(90deg,rgba(34,211,238,0.08),transparent_26%,transparent_74%,rgba(59,130,246,0.08))]" aria-hidden="true" />
        <div className="pointer-events-none absolute inset-0 opacity-35 [background-image:radial-gradient(circle,rgba(34,211,238,0.55)_1px,transparent_1.5px)] [background-size:28px_28px] [mask-image:linear-gradient(90deg,black,transparent_34%,transparent_66%,black)]" aria-hidden="true" />
        <ArchLensParticleBackground />
        <div className="pointer-events-none absolute inset-x-[28%] top-0 bottom-0 bg-gray-950/70 blur-2xl" aria-hidden="true" />

        <div className="relative z-10 max-w-2xl mx-auto">
          <div className="text-center mb-8">
            <h1 className="text-3xl sm:text-4xl font-bold text-white tracking-normal mb-3">
              AI-Powered Architecture Intelligence
            </h1>
            <p className="text-base sm:text-lg text-blue-100/80 leading-relaxed">
              ArchLens will analyze components, run WAF reviews, compare pricing, generate Terraform and push the code into GitHub.
            </p>
          </div>

          {/* Dropzone */}
          <div
            {...getRootProps()}
            className={`relative border-2 border-dashed rounded-2xl p-10 text-center cursor-pointer transition-colors shadow-2xl shadow-gray-950/40 ${
              isDragActive
                ? 'border-blue-500 bg-blue-500/10'
                : 'border-gray-700 hover:border-gray-600 bg-gray-900/90'
            }`}
          >
        <input {...getInputProps()} />
        {preview ? (
          <img
            src={preview}
            alt="Preview"
            className="max-h-64 mx-auto rounded-lg object-contain"
          />
        ) : fileKind === 'drawio' ? (
          <div className="space-y-2 py-4">
            <div className="flex justify-center">
              {loading ? <Logo size={56} /> : <div className="text-5xl">📄</div>}
            </div>
            <p className="text-lg font-medium text-blue-400">
              {loading ? ANALYSIS_STEPS[loadingStep] : 'draw.io file ready'}
            </p>
            {!loading && (
              <p className="text-xs text-gray-500">XML will be parsed for shape labels & connections</p>
            )}
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex justify-center">
              <Logo size={64} />
            </div>
            <p className="text-lg font-medium text-gray-300">
              {isDragActive ? 'Drop it here!' : 'Drag & drop your architecture diagram'}
            </p>
            <div className="flex flex-wrap items-center justify-center gap-2 pt-1">
              {['PNG', 'JPG', 'WEBP', 'SVG', '.drawio', '.xml'].map((fmt) => (
                <span
                  key={fmt}
                  className="inline-flex items-center px-2.5 py-1 rounded-full border border-gray-700 bg-gray-800/60 text-[11px] font-semibold tracking-wide text-gray-300 shadow-sm hover:border-blue-500/60 hover:text-blue-300 transition-colors"
                >
                  {fmt}
                </span>
              ))}
              <span className="inline-flex items-center px-2.5 py-1 rounded-full bg-blue-600/15 border border-blue-500/40 text-[11px] font-semibold text-blue-300">
                up to {MAX_SIZE_MB}MB
              </span>
            </div>
          </div>
        )}
          </div>

          {file && (
        <div className="mt-4 flex items-center justify-between bg-gray-900/95 rounded-xl p-4 border border-gray-800/80 shadow-xl shadow-gray-950/25">
          <div className="flex items-center gap-3">
            {loading ? (
              <Logo size={28} />
            ) : (
              <span className="text-2xl">{fileKind === 'drawio' ? '📄' : '🖼'}</span>
            )}
            <div>
              <p className="text-sm font-medium text-gray-300">{file.name}</p>
              <p className="text-xs text-gray-500">
                {loading ? (
                  <span className="font-semibold text-blue-400">{ANALYSIS_STEPS[loadingStep]}</span>
                ) : (
                  `${(file.size / 1024).toFixed(1)} KB · ${fileKind === 'drawio' ? 'draw.io XML' : 'image'}`
                )}
              </p>
            </div>
          </div>
          <button
            className="text-xs text-gray-500 hover:text-red-400 transition-colors"
            onClick={(e) => {
              e.stopPropagation()
              setPreview(null)
              setFile(null)
              setFileKind(null)
            }}
          >
            Remove
          </button>
        </div>
          )}

          <div className="mt-6">
            <UserContextPanel value={userContext} onChange={onUserContextChange} />
          </div>

          <div className="mt-6 flex gap-3">
            <button
              onClick={handleAnalyze}
              disabled={!file || loading}
              className="btn-primary flex-1 flex items-center justify-center gap-2"
            >
              {loading ? (
                <span className="flex items-center justify-center gap-2">
                  <Logo size={20} />
                  <span>{ANALYSIS_STEPS[loadingStep]}</span>
                </span>
              ) : (
                '🔍 Analyze Diagram'
              )}
            </button>
          </div>
        </div>
      </section>

      <div className="max-w-2xl mx-auto">
        {/* What you'll get */}
        <div className="mt-10">
        <p className="text-xs font-semibold uppercase tracking-[0.15em] text-gray-500 text-center mb-4">
          What you'll get
        </p>
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3">
          {[
            { icon: '🔍', title: 'Analysis', desc: 'Components, connections & architecture type', border: 'border-violet-500/30 hover:border-violet-500/60', accent: 'text-violet-400' },
            { icon: '🛡', title: 'WAF Review', desc: 'Well-Architected scores across AWS, Azure, GCP', border: 'border-red-500/30 hover:border-red-500/60', accent: 'text-red-400' },
            { icon: '💰', title: 'Pricing', desc: 'Monthly & annual cost compared across clouds', border: 'border-emerald-500/30 hover:border-emerald-500/60', accent: 'text-emerald-400' },
            { icon: '⚙', title: 'Terraform', desc: 'Production-ready IaC for any cloud', border: 'border-amber-500/30 hover:border-amber-500/60', accent: 'text-amber-400' },
            { icon: '🐙', title: 'GitHub Push', desc: 'One-click commit to your own repo', border: 'border-slate-500/30 hover:border-slate-400/60', accent: 'text-slate-300' },
          ].map((c) => (
            <div
              key={c.title}
              className={`bg-gray-900/50 border ${c.border} rounded-xl p-3 text-center transition-colors`}
            >
              <div className="text-2xl mb-1">{c.icon}</div>
              <p className={`text-xs font-semibold ${c.accent} mb-1`}>{c.title}</p>
              <p className="text-[11px] text-gray-500 leading-snug">{c.desc}</p>
            </div>
          ))}
        </div>
      </div>

      {/* Supported formats */}
      <div className="mt-6 grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="card">
          <p className="text-sm font-semibold text-blue-400 mb-2 flex items-center gap-2">
            <Logo size={18} /> Image diagrams
          </p>
          <p className="text-xs text-gray-500">
            PNG, JPG, WEBP, SVG screenshots from Lucidchart, Visio, Excalidraw,
            AWS/Azure/GCP visual designers — analyzed by GPT-4 Vision.
          </p>
        </div>
        <div className="card">
          <p className="text-sm font-semibold text-emerald-400 mb-2">📄 draw.io files</p>
          <p className="text-xs text-gray-500">
            Native <span className="font-mono">.drawio</span> /{' '}
            <span className="font-mono">.xml</span> exports — shape labels &
            connections parsed directly from XML.
          </p>
        </div>
      </div>

      <div className="mt-4 card">
        <p className="text-sm font-semibold text-gray-400 mb-3">Works great with:</p>
        <div className="grid grid-cols-2 gap-2 text-sm text-gray-500">
          {[
            'Three-Tier Web Applications',
            'Microservices / Kubernetes',
            'Serverless / Event-Driven',
            'Data Pipelines / Analytics',
            'Hybrid / Multi-Cloud',
            'Network / Security Architecture',
          ].map((item) => (
            <div key={item} className="flex items-center gap-2">
              <span className="text-green-500">✓</span> {item}
            </div>
          ))}
        </div>
      </div>

      {/* Sample diagrams */}
      <div className="mt-4 card">
        <div className="flex items-center justify-between mb-3">
          <p className="text-sm font-semibold text-purple-400">🎯 Try a sample diagram</p>
          <span className="text-xs text-gray-600">Pre-built .drawio files for testing</span>
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
          {SAMPLES.map((s) => (
            <div
              key={s.file}
              className="bg-gray-800/50 hover:bg-gray-800 border border-gray-800 rounded-lg p-3 transition-colors"
            >
              <div className="flex items-start justify-between gap-2 mb-1">
                <div className="flex items-center gap-2 min-w-0">
                  <span>{s.emoji}</span>
                  <span className="text-sm font-medium text-gray-200 truncate">{s.label}</span>
                </div>
              </div>
              <p className="text-xs text-gray-500 mb-2">{s.desc}</p>
              <div className="flex gap-2">
                <button
                  onClick={() => loadSample(s.file)}
                  disabled={loading}
                  className="text-xs text-blue-400 hover:text-blue-300 transition-colors disabled:opacity-50"
                >
                  ▶ Run Now
                </button>
                <a
                  href={`/samples/${s.file}`}
                  download
                  className="text-xs text-gray-500 hover:text-gray-300 transition-colors"
                >
                  ⬇ Download .drawio
                </a>
              </div>
            </div>
          ))}
        </div>
        <p className="text-xs text-gray-600 mt-3">
          💡 Tip: Download a file, open it at{' '}
          <a
            href="https://app.diagrams.net"
            target="_blank"
            rel="noreferrer"
            className="text-blue-400 hover:underline"
          >
            app.diagrams.net
          </a>{' '}
          to edit, then re-upload here.
        </p>
      </div>
      </div>
    </div>
  )
}
