import { useEffect, useRef } from 'react'

const COLORS = [
  [59, 130, 246],
  [34, 211, 238],
  [139, 92, 246],
  [255, 255, 255],
]

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
}

function getParticleCount(width, height) {
  const area = width * height
  if (width < 640) return Math.min(42, Math.max(24, Math.floor(area / 15000)))
  if (width < 1024) return Math.min(82, Math.max(48, Math.floor(area / 12000)))
  return Math.min(140, Math.max(92, Math.floor(area / 9500)))
}

function createParticles(width, height, count) {
  return Array.from({ length: count }, (_, index) => {
    const side = index % 2 === 0 ? 'left' : 'right'
    const sideWidth = Math.max(width * 0.34, 180)
    const x = side === 'left'
      ? Math.random() * sideWidth
      : width - Math.random() * sideWidth
    const color = COLORS[index % COLORS.length]

    return {
      baseX: x,
      baseY: Math.random() * height,
      phase: Math.random() * Math.PI * 2,
      drift: 12 + Math.random() * 28,
      speed: 0.00012 + Math.random() * 0.00018,
      radius: 1 + Math.random() * 2.2,
      alpha: 0.2 + Math.random() * 0.35,
      glow: index % 11 === 0,
      color,
    }
  })
}

export default function ArchLensParticleBackground() {
  const canvasRef = useRef(null)
  const frameRef = useRef(null)
  const resizeTimerRef = useRef(null)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return undefined

    const context = canvas.getContext('2d', { alpha: true })
    if (!context) return undefined

    let particles = []
    let width = 0
    let height = 0
    let pixelRatio = 1
    const reducedMotion = prefersReducedMotion()
    const lowPower = window.innerWidth < 640 || (navigator.hardwareConcurrency && navigator.hardwareConcurrency <= 4)
    const animate = !reducedMotion && !lowPower

    const resize = () => {
      const rect = canvas.getBoundingClientRect()
      width = Math.max(1, Math.floor(rect.width))
      height = Math.max(1, Math.floor(rect.height))
      pixelRatio = Math.min(window.devicePixelRatio || 1, 2)
      canvas.width = Math.floor(width * pixelRatio)
      canvas.height = Math.floor(height * pixelRatio)
      context.setTransform(pixelRatio, 0, 0, pixelRatio, 0, 0)
      particles = createParticles(width, height, getParticleCount(width, height))
    }

    const draw = (timestamp = 0) => {
      context.clearRect(0, 0, width, height)

      const centerX = width / 2
      const centerSafeWidth = Math.min(width * 0.3, 310)

      particles.forEach((particle) => {
        const waveX = Math.sin(timestamp * particle.speed + particle.phase) * particle.drift
        const waveY = Math.cos(timestamp * particle.speed * 1.35 + particle.phase) * (particle.drift * 0.45)
        const x = particle.baseX + (animate ? waveX : 0)
        const y = (particle.baseY + (animate ? waveY : 0) + height) % height
        const distanceFromCenter = Math.abs(x - centerX)
        const centerFade = Math.min(1, Math.max(0.2, (distanceFromCenter - centerSafeWidth * 0.22) / centerSafeWidth))
        const verticalFade = 0.5 + Math.sin((y / height) * Math.PI) * 0.5
        const alpha = Math.min(0.58, particle.alpha * centerFade * (0.7 + verticalFade * 0.3))
        const [red, green, blue] = particle.color

        if (particle.glow) {
          const glow = context.createRadialGradient(x, y, 0, x, y, particle.radius * 7)
          glow.addColorStop(0, `rgba(${red}, ${green}, ${blue}, ${alpha * 0.22})`)
          glow.addColorStop(1, `rgba(${red}, ${green}, ${blue}, 0)`)
          context.fillStyle = glow
          context.beginPath()
          context.arc(x, y, particle.radius * 7, 0, Math.PI * 2)
          context.fill()
        }

        context.fillStyle = `rgba(${red}, ${green}, ${blue}, ${alpha})`
        context.beginPath()
        context.arc(x, y, particle.radius, 0, Math.PI * 2)
        context.fill()
      })

      if (animate) frameRef.current = requestAnimationFrame(draw)
    }

    const onResize = () => {
      window.clearTimeout(resizeTimerRef.current)
      resizeTimerRef.current = window.setTimeout(() => {
        resize()
        draw()
      }, 120)
    }

    resize()
    draw()
    if (animate) frameRef.current = requestAnimationFrame(draw)
    window.addEventListener('resize', onResize)

    return () => {
      window.removeEventListener('resize', onResize)
      window.clearTimeout(resizeTimerRef.current)
      if (frameRef.current) cancelAnimationFrame(frameRef.current)
    }
  }, [])

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full opacity-90"
    />
  )
}