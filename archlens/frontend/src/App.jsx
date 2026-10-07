import { useState } from 'react'
import Header from './components/Header'
import Footer from './components/Footer'
import About from './components/About'
import Contact from './components/Contact'
import Demo from './components/Demo'
import DiagramUpload from './components/DiagramUpload'
import AnalysisResult from './components/AnalysisResult'
import WAFReview from './components/WAFReview'
import PricingComparison from './components/PricingComparison'
import TerraformViewer from './components/TerraformViewer'
import TerraformRunner from './components/TerraformRunner'
import GithubPush from './components/GithubPush'

const STEPS = [
  { id: 0, label: 'Upload', icon: '⬆' },
  { id: 1, label: 'Analysis', icon: '🔍' },
  { id: 2, label: 'WAF Review', icon: '🛡' },
  { id: 3, label: 'Pricing', icon: '💰' },
  { id: 4, label: 'Terraform', icon: '⚙' },
  { id: 5, label: 'Validate', icon: '🔬' },
  { id: 6, label: 'GitHub', icon: '🐙' },
]

export default function App() {
  const [currentPage, setCurrentPage] = useState('home') // 'home' | 'about' | 'demo' | 'contact'
  const [step, setStep] = useState(0)
  const [userContext, setUserContext] = useState({})
  const [analysisData, setAnalysisData] = useState(null)
  const [wafData, setWafData] = useState(null)
  const [pricingData, setPricingData] = useState(null)
  const [terraformData, setTerraformData] = useState(null)
  const [validationData, setValidationData] = useState(null)
  const [uploadedDiagram, setUploadedDiagram] = useState(null) // { preview, filename, kind }

  const isCompleted = (stepId) => {
    switch (stepId) {
      case 0: return analysisData !== null
      case 1: return analysisData !== null && step > 1
      case 2: return wafData !== null
      case 3: return pricingData !== null
      case 4: return terraformData !== null
      case 5: return validationData !== null
      default: return false
    }
  }

  const reset = () => {
    setAnalysisData(null)
    setWafData(null)
    setPricingData(null)
    setTerraformData(null)
    setValidationData(null)
    setUploadedDiagram(null)
    setStep(0)
  }

  return (
    <div className="min-h-screen flex flex-col">
      <Header currentPage={currentPage} onNavigate={setCurrentPage} />

      {/* About Page */}
      {currentPage === 'about' && (
        <main className="flex-1 mx-auto w-full max-w-7xl px-4 py-8">
          <About onBack={() => setCurrentPage('home')} />
        </main>
      )}

      {/* Demo Page */}
      {currentPage === 'demo' && (
        <main className="flex-1 mx-auto w-full max-w-7xl px-4 py-8">
          <Demo onBack={() => setCurrentPage('home')} />
        </main>
      )}

      {/* Contact Page */}
      {currentPage === 'contact' && (
        <main className="flex-1 mx-auto w-full max-w-7xl px-4 py-8">
          <Contact onBack={() => setCurrentPage('home')} />
        </main>
      )}

      {/* Home Page - Main Application */}
      {currentPage === 'home' && (
        <>
          {/* Step progress */}
          <div className="border-b border-gray-800 bg-gray-950/80 backdrop-blur sticky top-16 z-10">
        <div className="max-w-5xl mx-auto px-4 py-3">
          <div className="flex items-center gap-1">
            {STEPS.map((s, i) => {
              const done = isCompleted(s.id)
              const active = step === s.id
              const clickable = done && !active
              return (
                <div key={s.id} className="flex items-center flex-1 last:flex-none">
                  <button
                    onClick={() => clickable && setStep(s.id)}
                    className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                      active
                        ? 'bg-blue-600 text-white'
                        : done
                        ? 'text-green-400 hover:text-green-300 cursor-pointer'
                        : 'text-gray-500 cursor-default'
                    }`}
                  >
                    {done && !active
                      ? <span className="inline-flex items-center justify-center w-4 h-4 rounded-full bg-green-500 text-white text-[10px] font-bold leading-none">✓</span>
                      : <span>{s.icon}</span>
                    }
                    <span className="hidden sm:inline">{s.label}</span>
                  </button>
                  {i < STEPS.length - 1 && (
                    <div className={`flex-1 h-px mx-2 ${done ? 'bg-green-500' : step > i ? 'bg-blue-600' : 'bg-gray-800'}`} />
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>

      {/* Main content */}
      <main className={`flex-1 mx-auto w-full px-4 py-8 ${analysisData ? 'max-w-7xl' : 'max-w-5xl'}`}>
        <div className={analysisData ? 'flex gap-6 items-start' : ''}>

          {/* Left pane — uploaded diagram (shown from step 1 onwards) */}
          {analysisData && (
            <div className="w-80 shrink-0 sticky top-28">
              <div className="rounded-xl border border-gray-800 bg-gray-900/60 overflow-hidden">
                <div className="px-3 py-2 border-b border-gray-800 bg-gray-900">
                  <p className="text-xs font-semibold text-gray-400 uppercase tracking-wide">Uploaded Diagram</p>
                  {uploadedDiagram?.filename && (
                    <p className="text-xs text-gray-500 truncate mt-0.5" title={uploadedDiagram.filename}>
                      {uploadedDiagram.filename}
                    </p>
                  )}
                </div>
                {uploadedDiagram?.preview ? (
                  <img
                    src={uploadedDiagram.preview}
                    alt="Uploaded diagram"
                    className="w-full object-contain max-h-[28rem] bg-gray-950 p-2"
                  />
                ) : (
                  <div className="flex flex-col items-center justify-center py-10 px-4 text-center bg-gray-950">
                    <span className="text-4xl mb-2">📐</span>
                    <p className="text-xs text-gray-500">draw.io / XML diagram</p>
                    {uploadedDiagram?.filename && (
                      <p className="text-[10px] text-gray-600 mt-1 break-all">{uploadedDiagram.filename}</p>
                    )}
                  </div>
                )}
                {/* Component count badge */}
                {analysisData?.components?.length > 0 && (
                  <div className="px-3 py-2 border-t border-gray-800 bg-gray-900/80">
                    <p className="text-xs text-gray-400">
                      <span className="font-bold text-white">{analysisData.components.length}</span> components detected
                    </p>
                    {analysisData.cloud_provider && (
                      <p className="text-xs text-gray-500 mt-0.5 capitalize">
                        Provider: <span className="text-blue-400">{analysisData.cloud_provider}</span>
                      </p>
                    )}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Right pane — step content */}
          <div className="flex-1 min-w-0">
        {step === 0 && (
          <DiagramUpload
            userContext={userContext}
            onUserContextChange={setUserContext}
            onDiagramChange={setUploadedDiagram}
            onAnalyzed={(data) => {
              setAnalysisData(data)
              setWafData(null)
              setPricingData(null)
              setTerraformData(null)
              setStep(1)
            }}
          />
        )}
        {step === 1 && analysisData && (
          <AnalysisResult
            data={analysisData}
            onUpdate={(updated) => {
              setAnalysisData(updated)
              setWafData(null)
              setPricingData(null)
              setTerraformData(null)
            }}
            onNext={() => setStep(2)}
            onBack={() => setStep(0)}
          />
        )}
        {step === 2 && analysisData && (
          <WAFReview
            analysis={analysisData}
            wafData={wafData}
            onWafLoaded={setWafData}
            userContext={userContext}
            onNext={() => setStep(3)}
            onBack={() => setStep(1)}
          />
        )}
        {step === 3 && analysisData && (
          <PricingComparison
            analysis={analysisData}
            pricingData={pricingData}
            onPricingLoaded={setPricingData}
            userContext={userContext}
            onNext={() => setStep(4)}
            onBack={() => setStep(2)}
          />
        )}
        {step === 4 && analysisData && (
          <TerraformViewer
            analysis={analysisData}
            terraformData={terraformData}
            onTerraformLoaded={setTerraformData}
            userContext={userContext}
            onBack={() => setStep(3)}
            onNext={() => setStep(5)}
            onReset={reset}
          />
        )}
        {step === 5 && analysisData && (
          <div>
            <div className="flex items-center justify-between mb-6">
              <div>
                <h2 className="text-2xl font-bold text-white">Validation Report</h2>
                <p className="text-gray-400">Security, syntax and provider checks on your Terraform</p>
              </div>
            </div>
            {!terraformData && (
              <div className="card text-center py-12">
                <p className="text-gray-500">Generate Terraform first (step 4) before running validation.</p>
              </div>
            )}
            <div className="flex gap-3 mt-6">
              <button className="btn-secondary" onClick={() => setStep(4)}>← Back</button>
              <button
                className="btn-primary flex-1"
                onClick={() => setStep(6)}
                disabled={!validationData}
              >
                🐙 Push to GitHub →
              </button>
            </div>
          </div>
        )}
        {/* TerraformRunner: always mounted when terraformData exists to preserve execution state.
            Hidden via CSS when not on step 5 — avoids losing logs/results on back-navigation. */}
        {analysisData && terraformData && (
          <div style={{ display: step === 5 ? undefined : 'none' }}>
            <TerraformRunner
              files={terraformData.files}
              cloud={terraformData.cloud || 'aws'}
              onValidationDone={setValidationData}
              onFilesUpdated={(newFiles) => setTerraformData(d => ({ ...d, files: newFiles }))}
              onRegenerate={() => { setTerraformData(null); setStep(4) }}
            />
          </div>
        )}
        {step === 6 && analysisData && (
          <GithubPush
            analysis={analysisData}
            terraformData={terraformData}
            onBack={() => setStep(5)}
            onReset={reset}
          />
        )}
          </div>{/* end right pane */}
        </div>{/* end flex row */}
      </main>
        </>
      )}

      <Footer />
    </div>
  )
}
