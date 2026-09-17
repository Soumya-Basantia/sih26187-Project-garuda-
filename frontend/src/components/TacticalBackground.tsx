import React, { useEffect, useRef, useState } from 'react'
import { useTheme } from '../hooks/useTheme'

interface TacticalNode {
  x: number
  y: number
  vx: number
  vy: number
  radius: number
  label: string
  type: 'SENSOR' | 'RADAR' | 'DRONE' | 'HQ' | 'SATELLITE'
  ping: number
  pingSpeed: number
}

export default function TacticalBackground() {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const { resolvedTheme } = useTheme()
  const mousePos = useRef<{ x: number; y: number; active: boolean }>({ x: 0, y: 0, active: false })
  const radarAngle = useRef(0)
  const [hasCanvasError, setHasCanvasError] = useState(false)

  useEffect(() => {
    const canvas = canvasRef.current
    if (!canvas) return
    const ctx = canvas.getContext('2d')
    if (!ctx) {
      setHasCanvasError(true)
      return
    }

    let animationFrameId: number
    let width = (canvas.width = Math.max(window.innerWidth || 1200, 300))
    let height = (canvas.height = Math.max(window.innerHeight || 800, 300))

    const handleResize = () => {
      if (!canvas) return
      width = canvas.width = Math.max(window.innerWidth || 1200, 300)
      height = canvas.height = Math.max(window.innerHeight || 800, 300)
    }
    window.addEventListener('resize', handleResize)

    // Generate Tactical Nodes
    const nodeCount = Math.max(Math.min(Math.floor((width * height) / 28000), 50), 20)
    const types: TacticalNode['type'][] = ['SENSOR', 'RADAR', 'DRONE', 'HQ', 'SATELLITE']
    const nodes: TacticalNode[] = Array.from({ length: nodeCount }, (_, i) => ({
      x: Math.random() * width,
      y: Math.random() * height,
      vx: (Math.random() - 0.5) * 0.4,
      vy: (Math.random() - 0.5) * 0.4,
      radius: Math.random() * 2 + 2,
      label: `NODE-${(i + 1).toString().padStart(2, '0')}`,
      type: types[i % types.length],
      ping: Math.random() * 20,
      pingSpeed: 0.03 + Math.random() * 0.04,
    }))

    // Mouse Tracking
    const handleMouseMove = (e: MouseEvent) => {
      mousePos.current = { x: e.clientX, y: e.clientY, active: true }
    }
    const handleMouseLeave = () => {
      mousePos.current.active = false
    }
    window.addEventListener('mousemove', handleMouseMove)
    window.addEventListener('mouseleave', handleMouseLeave)

    // Radar Center Anchor
    const getRadarCenter = () => {
      return {
        cx: width > 1024 ? width * 0.72 : width * 0.5,
        cy: height > 768 ? height * 0.45 : height * 0.5,
        maxRadius: Math.max(Math.max(width, height) * 0.65, 150),
      }
    }

    const render = () => {
      try {
        ctx.clearRect(0, 0, width, height)
        const isDark = resolvedTheme === 'dark'
        const { cx, cy, maxRadius } = getRadarCenter()

        if (maxRadius > 10) {
          // 1. Concentric Tactical Range Rings
          const ringCount = 5
          for (let i = 1; i <= ringCount; i++) {
            const r = Math.max((maxRadius / ringCount) * i, 1)
            ctx.beginPath()
            ctx.arc(cx, cy, r, 0, Math.PI * 2)
            ctx.strokeStyle = isDark ? 'rgba(6, 182, 212, 0.08)' : 'rgba(14, 116, 144, 0.09)'
            ctx.lineWidth = 1
            ctx.setLineDash([4, 6])
            ctx.stroke()
            ctx.setLineDash([])

            // Range Marks
            ctx.fillStyle = isDark ? 'rgba(6, 182, 212, 0.28)' : 'rgba(14, 116, 144, 0.32)'
            ctx.font = '9px "JetBrains Mono", monospace'
            ctx.fillText(`${i * 25} KM`, cx + 8, cy - r + 12)
          }

          // 2. Crosshairs Axis Lines (N-S-E-W)
          ctx.beginPath()
          ctx.moveTo(cx - maxRadius, cy)
          ctx.lineTo(cx + maxRadius, cy)
          ctx.moveTo(cx, cy - maxRadius)
          ctx.lineTo(cx, cy + maxRadius)
          ctx.strokeStyle = isDark ? 'rgba(6, 182, 212, 0.06)' : 'rgba(14, 116, 144, 0.07)'
          ctx.lineWidth = 1
          ctx.stroke()

          // 3. Rotating Radar Sweep Beam
          radarAngle.current = (radarAngle.current + 0.008) % (Math.PI * 2)
          const sweepAngle = radarAngle.current

          const sweepGradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, maxRadius)
          if (isDark) {
            sweepGradient.addColorStop(0, 'rgba(6, 182, 212, 0.18)')
            sweepGradient.addColorStop(0.5, 'rgba(6, 182, 212, 0.05)')
            sweepGradient.addColorStop(1, 'rgba(6, 182, 212, 0)')
          } else {
            sweepGradient.addColorStop(0, 'rgba(14, 116, 144, 0.14)')
            sweepGradient.addColorStop(0.5, 'rgba(14, 116, 144, 0.04)')
            sweepGradient.addColorStop(1, 'rgba(14, 116, 144, 0)')
          }

          ctx.save()
          ctx.beginPath()
          ctx.moveTo(cx, cy)
          ctx.arc(cx, cy, maxRadius, sweepAngle - 0.45, sweepAngle)
          ctx.closePath()
          ctx.fillStyle = sweepGradient
          ctx.fill()

          // Leading Beam Line
          ctx.beginPath()
          ctx.moveTo(cx, cy)
          ctx.lineTo(cx + Math.cos(sweepAngle) * maxRadius, cy + Math.sin(sweepAngle) * maxRadius)
          ctx.strokeStyle = isDark ? 'rgba(6, 182, 212, 0.35)' : 'rgba(14, 116, 144, 0.35)'
          ctx.lineWidth = 1.5
          ctx.stroke()
          ctx.restore()

          // 4. Update and Draw Interconnected Nodes
          for (let i = 0; i < nodes.length; i++) {
            const node = nodes[i]
            node.x += node.vx
            node.y += node.vy

            if (node.x < 30 || node.x > width - 30) node.vx *= -1
            if (node.y < 30 || node.y > height - 30) node.vy *= -1

            if (mousePos.current.active) {
              const dx = mousePos.current.x - node.x
              const dy = mousePos.current.y - node.y
              const dist = Math.sqrt(dx * dx + dy * dy)
              if (dist < 160 && dist > 0) {
                node.x -= (dx / dist) * 0.7
                node.y -= (dy / dist) * 0.7
              }
            }

            // Connections
            for (let j = i + 1; j < nodes.length; j++) {
              const nodeB = nodes[j]
              const dx = node.x - nodeB.x
              const dy = node.y - nodeB.y
              const dist = Math.sqrt(dx * dx + dy * dy)

              if (dist < 130) {
                const alpha = (1 - dist / 130) * (isDark ? 0.16 : 0.12)
                ctx.beginPath()
                ctx.moveTo(node.x, node.y)
                ctx.lineTo(nodeB.x, nodeB.y)
                ctx.strokeStyle = isDark ? `rgba(56, 189, 248, ${alpha})` : `rgba(2, 132, 199, ${alpha})`
                ctx.lineWidth = 0.8
                ctx.stroke()
              }
            }

            // Radar Sweep Ping Calculation
            const angleToNode = Math.atan2(node.y - cy, node.x - cx)
            let normalizedNodeAngle = angleToNode < 0 ? angleToNode + Math.PI * 2 : angleToNode
            let diffAngle = sweepAngle - normalizedNodeAngle
            if (diffAngle < 0) diffAngle += Math.PI * 2

            const isPinged = diffAngle < 0.25
            if (isPinged) {
              node.ping = 1.0
            } else if (node.ping > 0) {
              node.ping -= node.pingSpeed
            }

            // Render Node
            ctx.beginPath()
            ctx.arc(node.x, node.y, node.radius, 0, Math.PI * 2)
            ctx.fillStyle = isDark
              ? node.type === 'HQ'
                ? 'rgba(239, 68, 68, 0.9)'
                : 'rgba(6, 182, 212, 0.8)'
              : node.type === 'HQ'
              ? 'rgba(220, 38, 38, 0.85)'
              : 'rgba(14, 116, 144, 0.85)'
            ctx.fill()

            // Ping Ring
            if (node.ping > 0) {
              ctx.beginPath()
              ctx.arc(node.x, node.y, Math.max(node.radius + (1 - node.ping) * 16, 0.1), 0, Math.PI * 2)
              ctx.strokeStyle = isDark
                ? `rgba(6, 182, 212, ${node.ping * 0.7})`
                : `rgba(14, 116, 144, ${node.ping * 0.6})`
              ctx.lineWidth = 1
              ctx.stroke()
            }

            // Label
            if (node.type === 'HQ' || node.ping > 0.4) {
              ctx.fillStyle = isDark ? 'rgba(226, 232, 240, 0.45)' : 'rgba(71, 85, 105, 0.55)'
              ctx.font = '8px "JetBrains Mono", monospace'
              ctx.fillText(node.label, node.x + 6, node.y - 4)
            }
          }

          // 5. Mouse Target Reticle
          if (mousePos.current.active) {
            const mx = mousePos.current.x
            const my = mousePos.current.y
            ctx.save()
            ctx.strokeStyle = isDark ? 'rgba(6, 182, 212, 0.5)' : 'rgba(14, 116, 144, 0.5)'
            ctx.lineWidth = 1

            const size = 16
            ctx.strokeRect(mx - size, my - size, size * 2, size * 2)

            ctx.beginPath()
            ctx.moveTo(mx - size - 6, my)
            ctx.lineTo(mx + size + 6, my)
            ctx.moveTo(mx, my - size - 6)
            ctx.lineTo(mx, my + size + 6)
            ctx.stroke()

            ctx.fillStyle = isDark ? 'rgba(6, 182, 212, 0.7)' : 'rgba(14, 116, 144, 0.7)'
            ctx.font = '9px "JetBrains Mono", monospace'
            ctx.fillText(`TRK: [${Math.round(mx)}, ${Math.round(my)}]`, mx + size + 8, my + 3)
            ctx.restore()
          }
        }
      } catch (err) {
        console.warn('TacticalBackground canvas render catch:', err)
      }

      animationFrameId = requestAnimationFrame(render)
    }

    render()

    return () => {
      window.removeEventListener('resize', handleResize)
      window.removeEventListener('mousemove', handleMouseMove)
      window.removeEventListener('mouseleave', handleMouseLeave)
      cancelAnimationFrame(animationFrameId)
    }
  }, [resolvedTheme])

  return (
    <div className="absolute inset-0 w-full h-full pointer-events-none overflow-hidden z-0">
      {/* CSS Pulse Ring Fallback */}
      <div className="absolute top-1/2 right-1/4 -translate-y-1/2 w-[480px] h-[480px] rounded-full border border-ops-accent/15 animate-ping opacity-20 pointer-events-none" />
      <div className="absolute top-1/2 right-1/4 -translate-y-1/2 w-[720px] h-[720px] rounded-full border border-ops-accent/10 pointer-events-none" />

      {!hasCanvasError && (
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full pointer-events-none transition-opacity duration-500"
          style={{ opacity: resolvedTheme === 'dark' ? 0.95 : 0.8 }}
        />
      )}
    </div>
  )
}
