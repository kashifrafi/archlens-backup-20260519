export default function Footer() {
  return (
    <footer className="border-t border-gray-800 bg-gray-950 mt-auto">
      <div className="max-w-7xl mx-auto px-6 py-6">
        <div className="flex flex-col md:flex-row items-center justify-between gap-4">
          {/* Copyright */}
          <div className="text-sm text-gray-500">
            © 2026 ArchLens. All rights reserved.
          </div>
          
          {/* Links */}
          <div className="flex items-center gap-6 text-sm">
            <a 
              href="#" 
              className="text-gray-400 hover:text-blue-400 transition-colors"
            >
              Privacy Policy
            </a>
            <span className="text-gray-700">|</span>
            <a 
              href="#" 
              className="text-gray-400 hover:text-blue-400 transition-colors"
            >
              Terms of Service
            </a>
            <span className="text-gray-700">|</span>
            <a 
              href="mailto:support@archlens.in" 
              className="text-gray-400 hover:text-blue-400 transition-colors flex items-center gap-1"
            >
              <span>Contact</span>
              <span className="text-blue-400">support@archlens.in</span>
            </a>
          </div>
        </div>
      </div>
    </footer>
  )
}
