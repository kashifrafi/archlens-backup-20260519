export default function Demo({ onBack }) {
  const videoUrl = '/demo-video.mp4'

  return (
    <div className="space-y-8">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-4xl font-bold text-white mb-2">ArchLens Demo</h1>
          <p className="text-gray-400 text-lg">
            Watch how ArchLens transforms cloud architecture diagrams into actionable insights
          </p>
        </div>
        <button
          onClick={onBack}
          className="px-4 py-2 bg-gray-800 hover:bg-gray-700 text-white rounded-lg transition-colors"
        >
          Back
        </button>
      </div>

      {/* Video Container */}
      <div className="bg-gray-900 rounded-lg overflow-hidden border border-gray-800 shadow-2xl">
        <div className="aspect-video bg-black">
          <video
            autoPlay
            muted
            loop
            controls
            className="w-full h-full"
            poster="data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 1920 1080'%3E%3Crect fill='%23111827' width='1920' height='1080'/%3E%3Ctext x='50%25' y='50%25' dominant-baseline='middle' text-anchor='middle' fill='%236b7280' font-size='48' font-family='Arial'%3EDemo Video...%3C/text%3E%3C/svg%3E"
          >
            <source src={videoUrl} type="video/mp4" />
            Your browser does not support the video tag.
          </video>
        </div>
      </div>

      {/* Demo Description */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
          <div className="text-3xl mb-3">⬆️</div>
          <h3 className="text-lg font-semibold text-white mb-2">Upload Diagram</h3>
          <p className="text-gray-400 text-sm">
            Upload your cloud architecture diagram in Draw.io format to get started
          </p>
        </div>

        <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
          <div className="text-3xl mb-3">�️</div>
          <h3 className="text-lg font-semibold text-white mb-2">WAF - Framework Review</h3>
          <p className="text-gray-400 text-sm">
            Well Architected Framework review across multicloud pillars with gap analysis
          </p>
        </div>

        <div className="bg-gray-900 rounded-lg border border-gray-800 p-6">
          <div className="text-3xl mb-3">🚀</div>
          <h3 className="text-lg font-semibold text-white mb-2">Generate & Deploy</h3>
          <p className="text-gray-400 text-sm">
            Auto-generate Terraform code and deploy to AWS, Azure, or GCP instantly
          </p>
        </div>
      </div>

      {/* Features Highlight */}
      <div className="bg-gradient-to-r from-blue-900/30 to-purple-900/30 rounded-lg border border-blue-800/50 p-8">
        <h2 className="text-2xl font-bold text-white mb-6">Key Features</h2>
        <ul className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <li className="flex items-start gap-3">
            <span className="text-blue-400 font-bold">✓</span>
            <div>
              <p className="text-white font-semibold">Automatic Architecture Analysis</p>
              <p className="text-gray-400 text-sm">Detect components, relationships, and patterns</p>
            </div>
          </li>
          <li className="flex items-start gap-3">
            <span className="text-blue-400 font-bold">✓</span>
            <div>
              <p className="text-white font-semibold">WAF - Well Architected Framework Review</p>
              <p className="text-gray-400 text-sm">Review across multicloud pillars, gap analysis and recommendations</p>
            </div>
          </li>
          <li className="flex items-start gap-3">
            <span className="text-blue-400 font-bold">✓</span>
            <div>
              <p className="text-white font-semibold">Cost Estimation</p>
              <p className="text-gray-400 text-sm">Compare pricing across AWS, Azure, and GCP</p>
            </div>
          </li>
          <li className="flex items-start gap-3">
            <span className="text-blue-400 font-bold">✓</span>
            <div>
              <p className="text-white font-semibold">Terraform Generation</p>
              <p className="text-gray-400 text-sm">Auto-generate Infrastructure as Code</p>
            </div>
          </li>
        </ul>
      </div>

      {/* CTA */}
      <div className="bg-gray-900 rounded-lg border border-gray-800 p-8 text-center">
        <h2 className="text-2xl font-bold text-white mb-4">Ready to analyze your architecture?</h2>
        <button
          onClick={onBack}
          className="px-8 py-3 bg-blue-600 hover:bg-blue-500 text-white font-semibold rounded-lg transition-colors inline-block"
        >
          Try ArchLens Now
        </button>
      </div>
    </div>
  )
}
