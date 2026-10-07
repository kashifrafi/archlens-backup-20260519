export default function About({ onBack }) {
  return (
    <div className="max-w-5xl mx-auto">
      {/* Header */}
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-white mb-4">
          About <span className="text-blue-400">ArchLens</span>
        </h1>
        <p className="text-xl text-gray-400 max-w-3xl mx-auto">
          Transform your cloud architecture diagrams into production-ready Infrastructure as Code
        </p>
      </div>

      {/* What is ArchLens */}
      <div className="card mb-8">
        <h2 className="text-2xl font-bold text-white mb-4 flex items-center gap-2">
          <span className="text-3xl">🎯</span>
          What is ArchLens?
        </h2>
        <p className="text-gray-300 leading-relaxed mb-4">
          ArchLens is an AI-powered cloud infrastructure platform that automatically analyzes your architecture diagrams 
          and generates production-ready Terraform code. Simply upload your cloud architecture diagram, and ArchLens 
          intelligently identifies components, validates configurations, and creates modular, best-practice Terraform 
          infrastructure-as-code ready for deployment.
        </p>
        <p className="text-gray-300 leading-relaxed">
          Built on fine-tuned Large Language Models specialized for Terraform IaC code generation and validation, 
          ArchLens bridges the gap between architectural design and infrastructure deployment, dramatically reducing 
          the time from design to production.
        </p>
      </div>

      {/* Key Benefits */}
      <div className="card mb-8">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <span className="text-3xl">✨</span>
          Why Use ArchLens?
        </h2>
        <div className="grid md:grid-cols-2 gap-6">
          <div className="flex gap-3">
            <div className="text-2xl shrink-0">⚡</div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-1">Save Time</h3>
              <p className="text-gray-400 text-sm">
                Generate production-ready Terraform in minutes, not hours or days. Automated code generation 
                eliminates manual IaC writing.
              </p>
            </div>
          </div>

          <div className="flex gap-3">
            <div className="text-2xl shrink-0">🛡️</div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-1">Security First</h3>
              <p className="text-gray-400 text-sm">
                Built-in Well-Architected Framework reviews ensure your infrastructure follows security 
                best practices across 6 pillars.
              </p>
            </div>
          </div>

          <div className="flex gap-3">
            <div className="text-2xl shrink-0">💰</div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-1">Cost Optimization</h3>
              <p className="text-gray-400 text-sm">
                Multi-cloud pricing comparison (AWS, Azure, GCP) helps you make informed decisions 
                and optimize infrastructure costs.
              </p>
            </div>
          </div>

          <div className="flex gap-3">
            <div className="text-2xl shrink-0">🤖</div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-1">AI Auto-Fix</h3>
              <p className="text-gray-400 text-sm">
                Intelligent error detection and automatic remediation during terraform validation 
                with real-time diff views.
              </p>
            </div>
          </div>

          <div className="flex gap-3">
            <div className="text-2xl shrink-0">☁️</div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-1">Multi-Cloud Support</h3>
              <p className="text-gray-400 text-sm">
                Generate infrastructure code for AWS, Azure, or GCP from the same architecture 
                diagram with cloud-specific optimizations.
              </p>
            </div>
          </div>

          <div className="flex gap-3">
            <div className="text-2xl shrink-0">📦</div>
            <div>
              <h3 className="text-lg font-semibold text-white mb-1">Modular Architecture</h3>
              <p className="text-gray-400 text-sm">
                Generated code follows best practices with reusable modules, proper structure, 
                and comprehensive variable management.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Key Features */}
      <div className="card mb-8">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <span className="text-3xl">🚀</span>
          Key Features
        </h2>
        <div className="space-y-4">
          <div className="flex items-start gap-3 p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <span className="text-xl">🔍</span>
            <div>
              <h3 className="font-semibold text-white mb-1">AI-Powered Diagram Analysis</h3>
              <p className="text-gray-400 text-sm">
                Automatically detects and identifies cloud components, networking, security groups, 
                and data flow from architecture diagrams (PNG, JPG, WebP).
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <span className="text-xl">⚙️</span>
            <div>
              <h3 className="font-semibold text-white mb-1">Terraform Code Generation</h3>
              <p className="text-gray-400 text-sm">
                Creates production-ready, modular Terraform code with proper folder structure 
                (modules/networking, modules/compute, etc.) and comprehensive variable management.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <span className="text-xl">✅</span>
            <div>
              <h3 className="font-semibold text-white mb-1">Real-Time Validation Pipeline</h3>
              <p className="text-gray-400 text-sm">
                Executes terraform fmt → init → validate → plan with live streaming logs and 
                automatic error remediation (max 3 attempts per stage).
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <span className="text-xl">📊</span>
            <div>
              <h3 className="font-semibold text-white mb-1">Cost Estimation & Comparison</h3>
              <p className="text-gray-400 text-sm">
                Detailed pricing breakdown with monthly/annual estimates across AWS, Azure, and GCP 
                to help you make cost-effective infrastructure decisions.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <span className="text-xl">🐙</span>
            <div>
              <h3 className="font-semibold text-white mb-1">GitHub Integration</h3>
              <p className="text-gray-400 text-sm">
                One-click push to GitHub repositories maintaining folder structure, or download 
                as ZIP with complete Terraform project organization.
              </p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <span className="text-xl">🔧</span>
            <div>
              <h3 className="font-semibold text-white mb-1">Side-by-Side Diff Viewer</h3>
              <p className="text-gray-400 text-sm">
                Visual before/after code comparison when AI fixes errors, showing exactly what 
                changed with red (error) to green (fixed) highlighting.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Technology Stack */}
      <div className="card mb-8">
        <h2 className="text-2xl font-bold text-white mb-6 flex items-center gap-2">
          <span className="text-3xl">🛠️</span>
          Powered By
        </h2>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="text-center p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <div className="text-2xl mb-2">⚛️</div>
            <p className="text-sm font-semibold text-white">React 18</p>
            <p className="text-xs text-gray-500">Frontend</p>
          </div>
          <div className="text-center p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <div className="text-2xl mb-2">⚡</div>
            <p className="text-sm font-semibold text-white">FastAPI</p>
            <p className="text-xs text-gray-500">Backend</p>
          </div>
          <div className="text-center p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <div className="text-2xl mb-2">🤖</div>
            <p className="text-sm font-semibold text-white">Fine-tuned LLM</p>
            <p className="text-xs text-gray-500">Analysis</p>
          </div>
          <div className="text-center p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <div className="text-2xl mb-2">💻</div>
            <p className="text-sm font-semibold text-white">Fine-tuned LLM</p>
            <p className="text-xs text-gray-500">IaC Code Gen</p>
          </div>
          <div className="text-center p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <div className="text-2xl mb-2">🌐</div>
            <p className="text-sm font-semibold text-white">Terraform</p>
            <p className="text-xs text-gray-500">IaC</p>
          </div>
          <div className="text-center p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <div className="text-2xl mb-2">☁️</div>
            <p className="text-sm font-semibold text-white">Cloud AI Platform</p>
            <p className="text-xs text-gray-500">AI Infrastructure</p>
          </div>
          <div className="text-center p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <div className="text-2xl mb-2">🎨</div>
            <p className="text-sm font-semibold text-white">Tailwind CSS</p>
            <p className="text-xs text-gray-500">Styling</p>
          </div>
          <div className="text-center p-4 rounded-lg bg-gray-900/50 border border-gray-800">
            <div className="text-2xl mb-2">🔥</div>
            <p className="text-sm font-semibold text-white">Vite</p>
            <p className="text-xs text-gray-500">Build Tool</p>
          </div>
        </div>
      </div>

      {/* CTA */}
      <div className="text-center py-8">
        <button 
          onClick={onBack}
          className="btn-primary text-lg px-8 py-3"
        >
          Get Started with ArchLens →
        </button>
      </div>
    </div>
  )
}
