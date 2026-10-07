export default function Contact({ onBack }) {
  return (
    <div className="max-w-3xl mx-auto">
      {/* Header */}
      <div className="text-center mb-12">
        <h1 className="text-4xl font-bold text-white mb-4">
          Contact <span className="text-blue-400">Us</span>
        </h1>
        <p className="text-xl text-gray-400">
          Get in touch with the ArchLens team
        </p>
      </div>

      {/* Contact Information */}
      <div className="card mb-8">
        <div className="text-center py-8">
          <div className="inline-flex items-center justify-center w-20 h-20 rounded-full bg-blue-600/20 mb-6">
            <span className="text-4xl">✉️</span>
          </div>
          
          <h2 className="text-2xl font-bold text-white mb-3">Email Support</h2>
          <p className="text-gray-400 mb-6 max-w-lg mx-auto">
            Have questions, feedback, or need assistance? We'd love to hear from you. 
            Our support team typically responds within 24 hours.
          </p>
          
          <a 
            href="mailto:support@archlens.in"
            className="inline-flex items-center gap-2 px-6 py-3 bg-blue-600 hover:bg-blue-500 text-white rounded-lg font-semibold transition-colors text-lg"
          >
            <span>📧</span>
            <span>support@archlens.in</span>
          </a>
        </div>
      </div>

      {/* Support Topics */}
      <div className="card mb-8">
        <h2 className="text-xl font-bold text-white mb-4">How Can We Help?</h2>
        <div className="space-y-3">
          <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-900/50">
            <span className="text-xl">🐛</span>
            <div>
              <h3 className="font-semibold text-white text-sm">Bug Reports</h3>
              <p className="text-gray-400 text-xs">Found an issue? Let us know and we'll fix it.</p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-900/50">
            <span className="text-xl">💡</span>
            <div>
              <h3 className="font-semibold text-white text-sm">Feature Requests</h3>
              <p className="text-gray-400 text-xs">Have an idea? We'd love to hear your suggestions.</p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-900/50">
            <span className="text-xl">❓</span>
            <div>
              <h3 className="font-semibold text-white text-sm">General Questions</h3>
              <p className="text-gray-400 text-xs">Need help understanding a feature? Ask away.</p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-900/50">
            <span className="text-xl">🤝</span>
            <div>
              <h3 className="font-semibold text-white text-sm">Partnership Inquiries</h3>
              <p className="text-gray-400 text-xs">Interested in collaborating? Get in touch.</p>
            </div>
          </div>

          <div className="flex items-start gap-3 p-3 rounded-lg bg-gray-900/50">
            <span className="text-xl">🔒</span>
            <div>
              <h3 className="font-semibold text-white text-sm">Security Concerns</h3>
              <p className="text-gray-400 text-xs">Found a security issue? Please report it responsibly.</p>
            </div>
          </div>
        </div>
      </div>

      {/* Additional Info */}
      <div className="card mb-8">
        <h2 className="text-xl font-bold text-white mb-4">Before You Contact Us</h2>
        <div className="space-y-3 text-sm">
          <div className="flex gap-3">
            <span className="text-blue-400 shrink-0">✓</span>
            <p className="text-gray-400">
              Check the <span className="text-white font-semibold">API Docs</span> for technical documentation
            </p>
          </div>
          <div className="flex gap-3">
            <span className="text-blue-400 shrink-0">✓</span>
            <p className="text-gray-400">
              Review the <span className="text-white font-semibold">About</span> page for feature details
            </p>
          </div>
          <div className="flex gap-3">
            <span className="text-blue-400 shrink-0">✓</span>
            <p className="text-gray-400">
              Include relevant details (error messages, screenshots) in your email
            </p>
          </div>
          <div className="flex gap-3">
            <span className="text-blue-400 shrink-0">✓</span>
            <p className="text-gray-400">
              For security issues, include steps to reproduce if applicable
            </p>
          </div>
        </div>
      </div>

      {/* Back Button */}
      <div className="text-center py-4">
        <button 
          onClick={onBack}
          className="btn-secondary px-6 py-2"
        >
          ← Back to Home
        </button>
      </div>
    </div>
  )
}
