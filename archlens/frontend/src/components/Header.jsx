import Logo from './Logo'

export default function Header({ currentPage, onNavigate }) {
  return (
    <header className="h-16 border-b border-gray-800 bg-gray-950 flex items-center px-6 sticky top-0 z-20">
      <div className="flex items-center gap-3 cursor-pointer" onClick={() => onNavigate('home')}>
        <Logo size={36} />
        <div>
          <span className="text-xl font-bold text-white tracking-tight">
            Arch<span className="text-blue-400">Lens</span>
          </span>
          <span className="ml-2 text-xs text-gray-500 hidden sm:inline">
            Navigate your cloud architectures
          </span>
        </div>
      </div>
      <div className="ml-auto flex items-center gap-6">
        <span className="text-xs text-gray-500 hidden md:block">
          AWS · Azure · GCP · WAF · Pricing · Terraform
        </span>
        <button
          onClick={() => onNavigate('about')}
          className={`text-sm font-medium transition-colors ${
            currentPage === 'about' 
              ? 'text-blue-400' 
              : 'text-gray-300 hover:text-white'
          }`}
        >
          About
        </button>
        <button
          onClick={() => onNavigate('demo')}
          className={`text-sm font-medium transition-colors ${
            currentPage === 'demo' 
              ? 'text-blue-400' 
              : 'text-gray-300 hover:text-white'
          }`}
        >
          Demo
        </button>
        <button
          onClick={() => onNavigate('contact')}
          className={`text-sm font-medium transition-colors ${
            currentPage === 'contact' 
              ? 'text-blue-400' 
              : 'text-gray-300 hover:text-white'
          }`}
        >
          Contact
        </button>
        <a
          href="/api/docs"
          target="_blank"
          rel="noreferrer"
          className="text-sm text-blue-400 hover:text-blue-300 transition-colors font-medium"
        >
          API Docs
        </a>
      </div>
    </header>
  )
}
