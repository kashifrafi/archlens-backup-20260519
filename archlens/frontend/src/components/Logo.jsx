/**
 * ArchLens compass logo — represents navigation through cloud architectures.
 * Outer ring + cardinal ticks + bold N/S needle (blue/red) + center pivot.
 * Needles slowly rotate while AI is thinking (any LLM request in flight).
 */
import { useThinking } from '../lib/thinking'

export default function Logo({ size = 36, className = '', spinning }) {
  const aiThinking = useThinking()
  const isSpinning = spinning ?? aiThinking
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 64 64"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
      aria-label="ArchLens compass logo"
      role="img"
    >
      <defs>
        <linearGradient id="archlens-needle-n" x1="32" y1="32" x2="32" y2="10" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#60a5fa" />
          <stop offset="1" stopColor="#2563eb" />
        </linearGradient>
        <linearGradient id="archlens-needle-s" x1="32" y1="32" x2="32" y2="54" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#1e293b" />
          <stop offset="1" stopColor="#475569" />
        </linearGradient>
        <radialGradient id="archlens-bg" cx="32" cy="32" r="28" gradientUnits="userSpaceOnUse">
          <stop offset="0" stopColor="#0b1220" />
          <stop offset="1" stopColor="#020617" />
        </radialGradient>
      </defs>

      {/* Outer ring */}
      <circle cx="32" cy="32" r="29" fill="url(#archlens-bg)" stroke="#334155" strokeWidth="2" />
      <circle cx="32" cy="32" r="24" fill="none" stroke="#1e293b" strokeWidth="1" />

      {/* Cardinal tick marks */}
      <g stroke="#64748b" strokeWidth="1.5" strokeLinecap="round">
        <line x1="32" y1="5" x2="32" y2="11" />
        <line x1="32" y1="53" x2="32" y2="59" />
        <line x1="5" y1="32" x2="11" y2="32" />
        <line x1="53" y1="32" x2="59" y2="32" />
      </g>

      {/* Diagonal small ticks */}
      <g stroke="#475569" strokeWidth="1" strokeLinecap="round">
        <line x1="13.5" y1="13.5" x2="16.5" y2="16.5" />
        <line x1="50.5" y1="13.5" x2="47.5" y2="16.5" />
        <line x1="13.5" y1="50.5" x2="16.5" y2="47.5" />
        <line x1="50.5" y1="50.5" x2="47.5" y2="47.5" />
      </g>

      {/* North needle (blue) */}
      <g className={isSpinning ? 'archlens-needle-spin' : ''}>
        <polygon points="32,10 27,32 32,30 37,32" fill="url(#archlens-needle-n)" />
        {/* South needle (slate) */}
        <polygon points="32,54 27,32 32,34 37,32" fill="url(#archlens-needle-s)" />

        {/* East/West needle (thin amber accent) */}
        <polygon points="10,32 32,29 30,32 32,35" fill="#f59e0b" opacity="0.85" />
        <polygon points="54,32 32,29 34,32 32,35" fill="#f59e0b" opacity="0.85" />

        {/* Center pivot */}
        <circle cx="32" cy="32" r="3.5" fill="#0f172a" stroke="#94a3b8" strokeWidth="1.2" />
        <circle cx="32" cy="32" r="1.2" fill="#e2e8f0" />
      </g>

      {/* Tiny "N" label */}
      <text x="32" y="9" textAnchor="middle" fontSize="6" fontWeight="700" fill="#60a5fa" fontFamily="ui-sans-serif, system-ui">
        N
      </text>
    </svg>
  )
}
