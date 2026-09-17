import React, { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { Camera, Alert, cameraApi } from '../services/api'
import L from 'leaflet'
import 'leaflet/dist/leaflet.css'
import { Compass, Wand2, RotateCw, RotateCcw, Play, ArrowUp, ArrowDown, Trash2, Plus, X } from 'lucide-react'

interface TacticalRadarMapProps {
  cameras: Camera[]
  alerts: Alert[]
  onSelectCamera?: (cameraId: string) => void
}

export interface CameraPlacement {
  x: number
  y: number
  angle: number // 0 to 360 deg (0 = North, 90 = East, 180 = South, 270 = West)
  fov: number   // cone spread 30 to 120 deg
  range: number // realistic cone reach 45 to 140 px (~12 to 35 meters)
}

interface TacticalEntity {
  id: string
  name: string
  role: 'student' | 'faculty' | 'staff' | 'visitor' | 'security' | 'threat'
  x: number
  y: number
  speed: string
  sector: string
  status: 'TRACKED' | 'BLIND_SPOT' | 'THREAT_LOCKED'
  trackingCamName?: string
  dwellSeconds: number
  headingDeg: number
  routeIndex: number
  routeProgress: number
}

interface CircularHandoverState {
  active: boolean
  currentLeg: number
  stage: 'in_cam' | 'transition' | 'handover_confirmed'
  progress: number
  x: number
  y: number
  fromCamId: string
  toCamId: string
  fromCamName: string
  toCamName: string
  etaCountdown: number
  msg: string
}

/**
 * Automatically map connected systems/cameras into a continuous perimeter circle.
 * Computes the geometric centroid of all cameras and sorts them by polar angle (atan2),
 * guaranteeing a non-intersecting, closed circular perimeter traversal around the campus.
 */
export function autoMapPerimeterCircle(nodes: Array<{ id: string; x: number; y: number; name: string }>): string[] {
  if (nodes.length <= 1) return nodes.map(n => n.id)
  
  const cx = nodes.reduce((sum, n) => sum + n.x, 0) / nodes.length
  const cy = nodes.reduce((sum, n) => sum + n.y, 0) / nodes.length
  
  const sorted = [...nodes].sort((a, b) => {
    const angleA = Math.atan2(a.y - cy, a.x - cx)
    const angleB = Math.atan2(b.y - cy, b.x - cx)
    return angleA - angleB
  })
  
  return sorted.map(n => n.id)
}

// 12 Camera Presets calibrated to the user's College Campus satellite layout (1000 x 770 coordinate system)
export const COLLEGE_CAMPUS_PRESETS: Array<{
  id: string
  name: string
  location: string
  x: number
  y: number
  angle: number
  fov: number
  range: number
}> = [
  { id: 'cam_gate_01', name: 'CAM-01: Main West Campus Gate', location: 'West Road Entrance & Barrier', x: 80, y: 640, angle: 45, fov: 75, range: 95 },
  { id: 'cam_nw_02', name: 'CAM-02: North Wing (West Corner)', location: 'North Block Outer Edge', x: 85, y: 130, angle: 90, fov: 70, range: 90 },
  { id: 'cam_north_03', name: 'CAM-03: North Wing (Central Overlook)', location: 'North Block Facing Road', x: 320, y: 130, angle: 180, fov: 75, range: 95 },
  { id: 'cam_ne_04', name: 'CAM-04: North Wing (East Corner)', location: 'North-East Corner Junction', x: 550, y: 130, angle: 135, fov: 70, range: 90 },
  { id: 'cam_east_05', name: 'CAM-05: East Complex (North Edge)', location: 'East Wing Rooftop North', x: 720, y: 100, angle: 180, fov: 75, range: 90 },
  { id: 'cam_east_06', name: 'CAM-06: East Complex (Courtyard)', location: 'East Wing Inner Garden Lightwell', x: 815, y: 290, angle: 0, fov: 80, range: 85 },
  { id: 'cam_east_07', name: 'CAM-07: East Perimeter Outer Wall', location: 'Eastern Campus Boundary', x: 940, y: 390, angle: 270, fov: 75, range: 95 },
  { id: 'cam_se_08', name: 'CAM-08: South-East Wing Corner', location: 'South-East Perimeter Edge', x: 940, y: 700, angle: 315, fov: 70, range: 90 },
  { id: 'cam_south_09', name: 'CAM-09: South Academic Quad', location: 'South Block Inner Courtyard', x: 400, y: 620, angle: 0, fov: 80, range: 95 },
  { id: 'cam_sw_10', name: 'CAM-10: South Block (West Corner)', location: 'South Wing West Outer Corner', x: 140, y: 700, angle: 0, fov: 75, range: 90 },
  { id: 'cam_road_11', name: 'CAM-11: Central Curved Roadway', location: 'Main Access Road Apex Turn', x: 580, y: 340, angle: 270, fov: 80, range: 95 },
  { id: 'cam_garden_12', name: 'CAM-12: Central Garden & Trees', location: 'Campus Central Courtyard Clearing', x: 310, y: 390, angle: 90, fov: 80, range: 95 },
]

// Walking paths following the visible campus roads and walkways
const CAMPUS_SATELLITE_ROUTES = [
  // Route 0: Student walking Main West Gate -> Up West Roadway -> North Wing
  [
    { x: 65, y: 680 }, { x: 80, y: 520 }, { x: 80, y: 290 }, { x: 80, y: 200 },
    { x: 150, y: 150 }, { x: 320, y: 150 }, { x: 450, y: 150 }
  ],
  // Route 1: Faculty walking North Wing -> Central Road Curve -> East Wing
  [
    { x: 350, y: 150 }, { x: 550, y: 220 }, { x: 600, y: 290 }, { x: 680, y: 290 },
    { x: 750, y: 290 }, { x: 815, y: 290 }
  ],
  // Route 2: Security Patrol vehicle / foot patrol along the curved campus road
  [
    { x: 65, y: 680 }, { x: 80, y: 520 }, { x: 80, y: 290 }, { x: 250, y: 290 },
    { x: 450, y: 290 }, { x: 620, y: 340 }, { x: 625, y: 500 }, { x: 450, y: 530 },
    { x: 200, y: 530 }, { x: 100, y: 600 }
  ],
  // Route 3: Student crossing from South Building into Central Garden
  [
    { x: 380, y: 530 }, { x: 380, y: 440 }, { x: 320, y: 380 }, { x: 250, y: 320 },
    { x: 250, y: 200 }
  ]
]

// Point-in-cone calculation
function isPointInCone(
  px: number,
  py: number,
  cam: { x: number; y: number; angle: number; fov: number; range: number }
): boolean {
  const dx = px - cam.x
  const dy = py - cam.y
  const dist = Math.hypot(dx, dy)
  if (dist > cam.range || dist < 6) return false

  let ptAngleDeg = (Math.atan2(dx, -dy) * 180) / Math.PI
  if (ptAngleDeg < 0) ptAngleDeg += 360

  let diff = Math.abs(ptAngleDeg - cam.angle)
  if (diff > 180) diff = 360 - diff
  return diff <= cam.fov / 2
}

interface TacticalLiveStreamFeedProps {
  camera: Camera | null
  handover: CircularHandoverState
  selectedEntity: TacticalEntity | null
  isSimRunning: boolean
}

export function TacticalLiveStreamFeed({
  camera,
  handover,
  selectedEntity,
  isSimRunning
}: TacticalLiveStreamFeedProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const [streamError, setStreamError] = useState(false)
  const [streamLoaded, setStreamLoaded] = useState(false)
  const [timeStr, setTimeStr] = useState('')
  const frameRef = useRef(0)

  // Reset stream status when camera changes
  useEffect(() => {
    setStreamError(false)
    setStreamLoaded(false)
  }, [camera?.camera_id])

  // Live millisecond timecode for tactical HUD
  useEffect(() => {
    const updateTime = () => {
      const now = new Date()
      const time = now.toTimeString().split(' ')[0]
      const ms = String(Math.floor(now.getMilliseconds() / 10)).padStart(2, '0')
      setTimeStr(`${time}:${ms}`)
    }
    updateTime()
    const timer = setInterval(updateTime, 60)
    return () => clearInterval(timer)
  }, [])

  // Canvas animation loop (active whenever stream is not loaded or has error or during simulation)
  useEffect(() => {
    if (!canvasRef.current || (streamLoaded && !streamError)) return

    const canvas = canvasRef.current
    const ctx = canvas.getContext('2d')
    if (!ctx) return

    let animId: number
    let localFrame = 0

    const render = () => {
      localFrame++
      frameRef.current = localFrame
      const width = canvas.width
      const height = canvas.height

      // 1. Clear & Background Gradient (Deep tactical CCTV surveillance palette)
      const grad = ctx.createLinearGradient(0, 0, 0, height)
      grad.addColorStop(0, '#040b17')
      grad.addColorStop(0.5, '#02060e')
      grad.addColorStop(1, '#060f1c')
      ctx.fillStyle = grad
      ctx.fillRect(0, 0, width, height)

      // 2. Horizon & Tactical Perspective Grid
      ctx.strokeStyle = '#08253d'
      ctx.lineWidth = 1
      const horizonY = height * 0.42
      ctx.beginPath()
      ctx.moveTo(0, horizonY)
      ctx.lineTo(width, horizonY)
      for (let i = -width; i < width * 2; i += 70) {
        ctx.moveTo(width / 2, horizonY)
        ctx.lineTo(i, height)
      }
      for (let y = horizonY + 15; y < height; y += (y - horizonY) * 0.35 + 8) {
        ctx.moveTo(0, y)
        ctx.lineTo(width, y)
      }
      ctx.stroke()

      // 3. Sector Architecture Outlines (buildings/fences in distance)
      ctx.fillStyle = '#061626'
      ctx.fillRect(40, horizonY - 45, 90, 45)
      ctx.fillRect(150, horizonY - 65, 120, 65)
      ctx.fillRect(440, horizonY - 55, 140, 55)
      ctx.strokeStyle = '#0e385e'
      ctx.strokeRect(40, horizonY - 45, 90, 45)
      ctx.strokeRect(150, horizonY - 65, 120, 65)
      ctx.strokeRect(440, horizonY - 55, 140, 55)

      // 4. Moving Scanline / Radar Laser Sweep
      const scanY = (localFrame * 2.2) % height
      const scanGrad = ctx.createLinearGradient(0, scanY - 20, 0, scanY + 2)
      scanGrad.addColorStop(0, 'rgba(0, 240, 255, 0)')
      scanGrad.addColorStop(1, 'rgba(0, 240, 255, 0.12)')
      ctx.fillStyle = scanGrad
      ctx.fillRect(0, scanY - 20, width, 22)
      ctx.strokeStyle = 'rgba(0, 240, 255, 0.4)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.moveTo(0, scanY)
      ctx.lineTo(width, scanY)
      ctx.stroke()

      // 5. Interlaced Scanlines Overlay
      ctx.fillStyle = 'rgba(0, 0, 0, 0.25)'
      for (let y = 0; y < height; y += 4) {
        ctx.fillRect(0, y, width, 1.5)
      }

      // 6. TARGET TRACKING & HANDOVER VISUALIZATION
      if (handover.active) {
        const isFrom = camera?.camera_id === handover.fromCamId
        const isTo = camera?.camera_id === handover.toCamId

        if (isFrom || isTo) {
          // Calculate animated target position in frame
          let targetX = width * 0.5
          let targetY = height * 0.58
          let targetW = 64
          let targetH = 120

          if (isFrom) {
            if (handover.stage === 'in_cam') {
              targetX = width * 0.48 + Math.sin(localFrame * 0.05) * 15
            } else if (handover.stage === 'transition') {
              targetX = width * (0.48 + handover.progress * 0.45)
            }
          } else if (isTo) {
            if (handover.stage === 'transition') {
              targetX = width * (0.05 + handover.progress * 0.43)
            } else {
              targetX = width * 0.5
            }
          }

          const boxLeft = targetX - targetW / 2
          const boxTop = targetY - targetH / 2

          const isConfirmed = handover.stage === 'handover_confirmed'
          const strokeCol = isConfirmed ? '#00e676' : isTo ? '#00e5ff' : '#ff9100'
          const fillBg = isConfirmed ? 'rgba(0, 230, 118, 0.15)' : isTo ? 'rgba(0, 229, 255, 0.12)' : 'rgba(255, 145, 0, 0.14)'

          // Target Body Silhouette (Tactical Pedestrian Figure)
          ctx.fillStyle = isConfirmed ? '#00e676' : '#ff5252'
          // Head
          ctx.beginPath()
          ctx.arc(targetX, boxTop + 18, 11, 0, Math.PI * 2)
          ctx.fill()
          // Torso
          ctx.fillRect(targetX - 9, boxTop + 32, 18, 48)
          // Animated Legs walking
          const legPhase = Math.sin(localFrame * 0.2) * 12
          ctx.beginPath()
          ctx.moveTo(targetX - 5, boxTop + 80)
          ctx.lineTo(targetX - 7 + legPhase, boxTop + 115)
          ctx.moveTo(targetX + 5, boxTop + 80)
          ctx.lineTo(targetX + 7 - legPhase, boxTop + 115)
          ctx.strokeStyle = ctx.fillStyle
          ctx.lineWidth = 4
          ctx.stroke()

          // Bounding Box
          ctx.fillStyle = fillBg
          ctx.fillRect(boxLeft, boxTop, targetW, targetH)
          ctx.strokeStyle = strokeCol
          ctx.lineWidth = 2
          ctx.strokeRect(boxLeft, boxTop, targetW, targetH)

          // Reticle Corner Brackets
          const kLen = 10
          ctx.lineWidth = 2.5
          ctx.beginPath()
          ctx.moveTo(boxLeft - 3, boxTop + kLen)
          ctx.lineTo(boxLeft - 3, boxTop - 3)
          ctx.lineTo(boxLeft + kLen, boxTop - 3)
          ctx.moveTo(boxLeft + targetW + 3 - kLen, boxTop - 3)
          ctx.lineTo(boxLeft + targetW + 3, boxTop - 3)
          ctx.lineTo(boxLeft + targetW + 3, boxTop + kLen)
          ctx.moveTo(boxLeft - 3, boxTop + targetH - kLen)
          ctx.lineTo(boxLeft - 3, boxTop + targetH + 3)
          ctx.lineTo(boxLeft + kLen, boxTop + targetH + 3)
          ctx.moveTo(boxLeft + targetW + 3 - kLen, boxTop + targetH + 3)
          ctx.lineTo(boxLeft + targetW + 3, boxTop + targetH + 3)
          ctx.lineTo(boxLeft + targetW + 3, boxTop + targetH - kLen)
          ctx.stroke()

          // Identification Tag
          ctx.fillStyle = 'rgba(0, 0, 0, 0.85)'
          ctx.fillRect(boxLeft - 4, boxTop - 22, 120, 18)
          ctx.strokeStyle = strokeCol
          ctx.lineWidth = 1
          ctx.strokeRect(boxLeft - 4, boxTop - 22, 120, 18)

          ctx.fillStyle = strokeCol
          ctx.font = 'bold 10px monospace'
          ctx.fillText(`T-112: RE-ID 99.1%`, boxLeft, boxTop - 9)

          // Sub-telemetry banner
          ctx.fillStyle = 'rgba(0, 0, 0, 0.75)'
          ctx.fillRect(boxLeft - 4, boxTop + targetH + 4, 110, 14)
          ctx.fillStyle = '#ffffff'
          ctx.font = '9px monospace'
          ctx.fillText(`V: 1.3m/s · ${isFrom ? 'HANDOVER OUT' : isConfirmed ? 'LOCKED' : 'ACQUIRING'}`, boxLeft, boxTop + targetH + 15)

          // Pulsing tracking ring on head
          ctx.beginPath()
          ctx.arc(targetX, boxTop + 18, 16 + Math.sin(localFrame * 0.2) * 3, 0, Math.PI * 2)
          ctx.strokeStyle = strokeCol
          ctx.lineWidth = 1.2
          ctx.stroke()
        } else {
          ctx.fillStyle = 'rgba(0, 229, 255, 0.8)'
          ctx.font = '11px monospace'
          ctx.fillText(`CIRCUIT UPLINK ACTIVE · AWAITING PERIMETER TRANSIT`, 40, height * 0.48)
          ctx.fillStyle = 'rgba(255, 255, 255, 0.4)'
          ctx.font = '10px monospace'
          ctx.fillText(`TARGET CURRENTLY AT: ${handover.fromCamName || 'NEXT NODE'}`, 40, height * 0.55)
        }
      } else {
        const pedX = ((localFrame * 1.5) % (width + 100)) - 50
        const pedY = height * 0.62
        ctx.fillStyle = '#00b4d8'
        ctx.beginPath()
        ctx.arc(pedX, pedY - 35, 8, 0, Math.PI * 2)
        ctx.fill()
        ctx.fillRect(pedX - 6, pedY - 25, 12, 35)

        ctx.strokeStyle = 'rgba(0, 229, 255, 0.6)'
        ctx.lineWidth = 1.2
        ctx.strokeRect(pedX - 16, pedY - 48, 32, 65)
        ctx.fillStyle = 'rgba(0, 0, 0, 0.7)'
        ctx.fillRect(pedX - 16, pedY - 60, 75, 12)
        ctx.fillStyle = '#00e5ff'
        ctx.font = '8.5px monospace'
        ctx.fillText('PERSON 94%', pedX - 14, pedY - 51)
      }

      // 7. Tactical Crosshair Reticle Center
      ctx.strokeStyle = 'rgba(0, 240, 255, 0.25)'
      ctx.lineWidth = 1
      ctx.beginPath()
      ctx.arc(width / 2, height / 2, 28, 0, Math.PI * 2)
      ctx.moveTo(width / 2 - 38, height / 2)
      ctx.lineTo(width / 2 - 14, height / 2)
      ctx.moveTo(width / 2 + 14, height / 2)
      ctx.lineTo(width / 2 + 38, height / 2)
      ctx.moveTo(width / 2, height / 2 - 38)
      ctx.lineTo(width / 2, height / 2 - 14)
      ctx.moveTo(width / 2, height / 2 + 14)
      ctx.lineTo(width / 2, height / 2 + 38)
      ctx.stroke()

      // 8. OSD Header & Telemetry Data
      ctx.fillStyle = 'rgba(0, 0, 0, 0.6)'
      ctx.fillRect(0, 0, width, 24)
      ctx.fillRect(0, height - 22, width, 22)

      ctx.fillStyle = '#00e5ff'
      ctx.font = 'bold 10px monospace'
      ctx.fillText(`CAM: ${camera?.camera_id || 'NODE'} · ${camera?.name?.split(':')[0] || 'PERIMETER'}`, 10, 16)

      ctx.fillStyle = localFrame % 30 < 15 ? '#ff1744' : '#770011'
      ctx.beginPath()
      ctx.arc(width - 92, 12, 4.5, 0, Math.PI * 2)
      ctx.fill()
      ctx.fillStyle = '#00e676'
      ctx.font = 'bold 10px monospace'
      ctx.fillText('REC 25.0 FPS', width - 82, 16)

      ctx.fillStyle = '#94a3b8'
      ctx.font = '9.5px monospace'
      ctx.fillText(`LOC: ${camera?.location || 'CAMPUS SECTOR'}`, 10, height - 8)

      ctx.fillStyle = '#ffffff'
      ctx.font = 'bold 9.5px monospace'
      const timeVal = new Date().toISOString().replace('T', ' ').slice(11, 19)
      ctx.fillText(`${timeVal}:${String(localFrame % 25).padStart(2, '0')}  FRM #${localFrame}`, width - 180, height - 8)

      animId = requestAnimationFrame(render)
    }

    animId = requestAnimationFrame(render)
    return () => cancelAnimationFrame(animId)
  }, [camera, handover, selectedEntity, isSimRunning, streamLoaded, streamError])

  return (
    <div className="relative w-full h-full bg-black flex items-center justify-center overflow-hidden">
      {/* 1. Real MJPEG Camera Stream (for live webcams / RTSP streams) */}
      {camera && (camera as any).is_real && (
        <img
          key={camera.camera_id}
          src={cameraApi.streamUrl(camera.camera_id)}
          alt={camera.name}
          className={`w-full h-full object-cover transition-opacity duration-300 ${streamLoaded && !streamError ? 'opacity-100' : 'hidden'}`}
          onLoad={() => {
            setStreamLoaded(true)
            setStreamError(false)
          }}
          onError={() => {
            setStreamError(true)
            setStreamLoaded(false)
          }}
        />
      )}

      {/* 2. Tactical Live Surveillance Canvas (active when stream is simulated, offline, or during handover simulation) */}
      {(!(camera as any)?.is_real || !streamLoaded || streamError) && (
        <canvas
          ref={canvasRef}
          width={640}
          height={360}
          className="w-full h-full object-cover block"
        />
      )}

      {/* 3. Live HUD Overlay (Always visible on top of both Real Stream and Canvas) */}
      <div className="absolute inset-0 pointer-events-none flex flex-col justify-between p-2">
        {/* Corner Reticle Brackets */}
        <div className="absolute top-2 left-2 w-3.5 h-3.5 border-t-2 border-l-2 border-cyan-400/80" />
        <div className="absolute top-2 right-2 w-3.5 h-3.5 border-t-2 border-r-2 border-cyan-400/80" />
        <div className="absolute bottom-2 left-2 w-3.5 h-3.5 border-b-2 border-l-2 border-cyan-400/80" />
        <div className="absolute bottom-2 right-2 w-3.5 h-3.5 border-b-2 border-r-2 border-cyan-400/80" />

        {/* Top Badges */}
        <div className="flex justify-between items-center z-10">
          <div className="flex items-center gap-1.5 bg-black/80 px-2 py-0.5 rounded border border-white/10 text-[10px] font-mono text-cyan-300">
            <span className={`w-1.5 h-1.5 rounded-full ${(camera as any)?.is_real ? 'bg-red-500 animate-ping' : 'bg-emerald-400 animate-pulse'}`} />
            <span>{(camera as any)?.is_real ? '🔴 LIVE CAMERA:' : 'SIM NODE:'} {camera?.camera_id || 'NODE'}</span>
          </div>
          <div className="flex items-center gap-1 bg-black/80 px-2 py-0.5 rounded border border-white/10 text-[10px] font-mono text-emerald-400">
            <span className={`w-1.5 h-1.5 rounded-full ${(camera as any)?.is_real ? 'bg-red-500 animate-ping' : 'bg-cyan-400 animate-pulse'}`} />
            <span>{(camera as any)?.is_real ? 'HARDWARE FEED' : 'AI SIMULATION'}</span>
          </div>
        </div>

        {/* Handover Real-Time Telemetry Bar (overlaid on top of webcam stream if live) */}
        {handover.active && streamLoaded && !streamError && (
          <div className="self-center bg-black/85 border border-amber-500/80 text-amber-300 px-3 py-1 rounded text-[10px] font-mono font-bold flex items-center gap-2 shadow-lg animate-pulse">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
            <span>
              {handover.stage === 'handover_confirmed'
                ? `🟢 TARGET LOCKED IN ${camera?.name.split(':')[0]}`
                : `🚨 TRACKING T-112 ➔ ${handover.toCamName} (ETA ${handover.etaCountdown}s)`}
            </span>
          </div>
        )}

        {/* Bottom Bar OSD */}
        <div className="flex justify-between items-center text-[10px] font-mono text-slate-300 z-10">
          <span className="bg-black/80 px-1.5 py-0.5 rounded border border-white/10">
            {(camera as any)?.is_real ? `LIVE HARDWARE · ${camera?.location || 'Station'}` : (camera?.location || 'Perimeter Simulation Node')}
          </span>
          <span className="bg-black/80 px-1.5 py-0.5 rounded border border-white/10 text-cyan-300">
            {timeStr}
          </span>
        </div>
      </div>
    </div>
  )
}

interface NavTooltipBtnProps {
  icon: React.ReactNode
  onClick?: () => void
  active?: boolean
  activeClass?: string
  inactiveClass?: string
  title: string
  subtitle?: string
  badge?: string
  disabled?: boolean
  className?: string
}

function NavTooltipBtn({
  icon,
  onClick,
  active,
  activeClass = 'bg-cyan-500/30 text-cyan-200 border-cyan-400/80 shadow-[0_0_8px_rgba(0,229,255,0.3)]',
  inactiveClass = 'bg-black/60 text-slate-400 hover:text-white hover:bg-white/10 border-ops-border/80',
  title,
  subtitle,
  badge,
  disabled,
  className = ''
}: NavTooltipBtnProps) {
  return (
    <div className="relative group/btn inline-flex items-center">
      <button
        onClick={onClick}
        disabled={disabled}
        className={`w-7 h-7 rounded flex items-center justify-center text-xs transition-all cursor-pointer border select-none ${
          active ? activeClass : inactiveClass
        } ${disabled ? 'opacity-40 cursor-not-allowed' : 'hover:scale-105 active:scale-95'} ${className}`}
      >
        {icon}
      </button>

      {/* Floating Tactical Tooltip Box */}
      <div className="absolute top-full mt-2 left-1/2 -translate-x-1/2 hidden group-hover/btn:flex flex-col items-center pointer-events-none z-50 whitespace-nowrap drop-shadow-2xl">
        <div className="w-2 h-2 bg-[#090e1a] border-t border-l border-cyan-500/60 rotate-45 -mb-1 z-10" />
        <div className="bg-[#090e1a]/95 backdrop-blur-md border border-cyan-500/60 text-slate-100 text-[11px] px-2.5 py-1.5 rounded shadow-2xl flex flex-col items-center text-center">
          <div className="flex items-center gap-1.5">
            <span className="font-bold text-cyan-300 text-[11px] leading-tight font-mono">{title}</span>
            {badge && (
              <span className="text-[9px] font-mono px-1 py-0.2 rounded bg-cyan-500/20 text-cyan-200 border border-cyan-500/40">
                {badge}
              </span>
            )}
          </div>
          {subtitle && <span className="text-[10px] text-slate-400 font-normal leading-tight mt-0.5 max-w-[210px] text-wrap">{subtitle}</span>}
        </div>
      </div>
    </div>
  )
}

export default function TacticalRadarMap({ cameras, alerts, onSelectCamera }: TacticalRadarMapProps) {
  // Map View Mode: 'college_satellite' (user's campus photo) | 'google_maps' (interactive live satellite tiles) | 'blueprint' | 'gods_eye_live' (Bilawal Sidhu Official 3D)
  const [viewMode, setViewMode] = useState<'college_satellite' | 'google_maps' | 'blueprint' | 'gods_eye_live'>('college_satellite')
  const [godViewSubMode, setGodViewSubMode] = useState<'image' | 'live'>('image')

  // Custom Floorplan Upload support
  const [customMapImage, setCustomMapImage] = useState<string | null>(() => {
    try {
      return localStorage.getItem('garuda_custom_map_image') || null
    } catch {
      return null
    }
  })
  const [mapOpacity, setMapOpacity] = useState<number>(() => {
    try {
      const saved = localStorage.getItem('garuda_map_opacity')
      return saved ? Number(saved) : 95
    } catch {
      return 95
    }
  })
  const fileInputRef = useRef<HTMLInputElement | null>(null)

  // UNLOCKED BY DEFAULT
  const [isLocked, setIsLocked] = useState<boolean>(() => {
    try {
      const saved = localStorage.getItem('garuda_camera_locked')
      return saved ? JSON.parse(saved) : false
    } catch { return false }
  })

  // Mode: 'tracking' or 'setup'
  const [editorMode, setEditorMode] = useState<'tracking' | 'setup'>('tracking')

  // Simulation running state
  const [isSimRunning, setIsSimRunning] = useState<boolean>(true)

  // Zoom & Pan (Canvas coordinates: 1000 x 770, center is 500, 385)
  const [zoom, setZoom] = useState<number>(1.0)
  const [pan, setPan] = useState<{ x: number; y: number }>({ x: 0, y: 0 })
  const [isPanning, setIsPanning] = useState<boolean>(false)
  const panStartRef = useRef<{ x: number; y: number }>({ x: 0, y: 0 })
  const svgRef = useRef<SVGSVGElement | null>(null)

  // Google Maps Leaflet container ref & instance ref
  const leafletContainerRef = useRef<HTMLDivElement | null>(null)
  const leafletMapRef = useRef<L.Map | null>(null)
  const [searchLocationQuery, setSearchLocationQuery] = useState<string>('')
  // Google Satellite Map Rotation in degrees (0..360)
  const [mapRotation, setMapRotation] = useState<number>(0)

  // Camera Placements stored by camera_id
  const [placements, setPlacements] = useState<Record<string, CameraPlacement>>(() => {
    try {
      const saved = localStorage.getItem('garuda_camera_placements')
      if (saved) return JSON.parse(saved)
    } catch { /* fallback */ }
    return {}
  })

  // Set-to-click mode: when clicking "Click to Place"
  const [placingCamId, setPlacingCamId] = useState<string | null>(null)

  // Dragging camera ID & Dragging Rotation Handle ID
  const [draggingCamId, setDraggingCamId] = useState<string | null>(null)
  const [rotatingCamId, setRotatingCamId] = useState<string | null>(null)

  // Status notification message
  const [tacticalActionMsg, setTacticalActionMsg] = useState<string | null>(null)

  // Effective cameras list: hybrid blending of real connected cameras with campus perimeter nodes
  const effectiveCameras: (Camera & { is_real?: boolean })[] = useMemo(() => {
    const realCams = (cameras || []).map(c => ({
      ...c,
      is_real: true
    }))

    const realCount = realCams.length
    // Fill remaining slots up to COLLEGE_CAMPUS_PRESETS.length (12)
    const simulatedCams = COLLEGE_CAMPUS_PRESETS.slice(realCount).map((p) => ({
      camera_id: p.id,
      name: p.name,
      location: p.location,
      status: 'ONLINE',
      source_type: 'webcam' as const,
      source_uri: '0',
      is_real: false
    }))

    return [...realCams, ...simulatedCams]
  }, [cameras])

  // Selected camera & previews
  const [selectedCamId, setSelectedCamId] = useState<string>(effectiveCameras[0]?.camera_id || '')
  const [activeCamPreview, setActiveCamPreview] = useState<Camera | null>(effectiveCameras[0] || null)
  const [selectedEntity, setSelectedEntity] = useState<TacticalEntity | null>(null)

  // Simulated Campus Personnel
  const [pedestrians, setPedestrians] = useState<TacticalEntity[]>([
    {
      id: 'STU-101',
      name: 'Ananya Sharma (Student)',
      role: 'student',
      x: 80,
      y: 520,
      speed: '1.2 m/s',
      sector: 'West Campus Roadway',
      status: 'TRACKED',
      trackingCamName: 'CAM-01',
      dwellSeconds: 120,
      headingDeg: 0,
      routeIndex: 0,
      routeProgress: 0.15
    },
    {
      id: 'FAC-204',
      name: 'Dr. Ramesh Rao (Faculty)',
      role: 'faculty',
      x: 550,
      y: 220,
      speed: '1.1 m/s',
      sector: 'North Wing Corridor',
      status: 'TRACKED',
      trackingCamName: 'CAM-04',
      dwellSeconds: 240,
      headingDeg: 135,
      routeIndex: 1,
      routeProgress: 0.25
    },
    {
      id: 'SEC-01',
      name: 'Officer Gurpreet (Mobile Patrol)',
      role: 'security',
      x: 450,
      y: 290,
      speed: '1.8 m/s',
      sector: 'Central Curved Roadway',
      status: 'TRACKED',
      trackingCamName: 'CAM-11',
      dwellSeconds: 410,
      headingDeg: 90,
      routeIndex: 2,
      routeProgress: 0.35
    },
    {
      id: 'STU-312',
      name: 'Kavita Nair (Student)',
      role: 'student',
      x: 320,
      y: 380,
      speed: '1.2 m/s',
      sector: 'Central Garden Lawn',
      status: 'TRACKED',
      trackingCamName: 'CAM-12',
      dwellSeconds: 290,
      headingDeg: 45,
      routeIndex: 3,
      routeProgress: 0.45
    }
  ])

  // Handover state
  const [handover, setHandover] = useState<CircularHandoverState>({
    active: false,
    currentLeg: 0,
    stage: 'in_cam',
    progress: 0,
    x: 80,
    y: 640,
    fromCamId: '',
    toCamId: '',
    fromCamName: '',
    toCamName: '',
    etaCountdown: 0,
    msg: ''
  })
  const handoverLoopTimeoutRef = useRef<any>(null)
  const handoverIntervalRef = useRef<any>(null)
  const activeRingStartRef = useRef<number>(0)
  const [showHandoverModal, setShowHandoverModal] = useState<boolean>(false)

  // Custom handover circuit sequence (persisted in localStorage)
  const [handoverSequence, setHandoverSequence] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('garuda_handover_sequence')
      if (saved) {
        const parsed = JSON.parse(saved)
        if (Array.isArray(parsed) && parsed.length >= 2) return parsed
      }
    } catch {}
    return []
  })

  // Cleanup handover timers on unmount
  useEffect(() => {
    return () => {
      if (handoverLoopTimeoutRef.current) clearTimeout(handoverLoopTimeoutRef.current)
      if (handoverIntervalRef.current) clearInterval(handoverIntervalRef.current)
    }
  }, [])

  // Sync selected camera
  useEffect(() => {
    if (effectiveCameras.length > 0) {
      if (!selectedCamId || !effectiveCameras.some(c => c.camera_id === selectedCamId)) {
        setSelectedCamId(effectiveCameras[0].camera_id)
        setActiveCamPreview(effectiveCameras[0])
      }
    }
  }, [effectiveCameras, selectedCamId])

  // Build camera nodes with saved or default placements
  const cameraNodes = useMemo(() => {
    return effectiveCameras.map((cam, idx) => {
      const saved = placements[cam.camera_id]
      const preset = COLLEGE_CAMPUS_PRESETS[idx % COLLEGE_CAMPUS_PRESETS.length]

      return {
        id: cam.camera_id,
        name: cam.name || preset.name,
        location: cam.location || preset.location,
        status: cam.status || 'ONLINE',
        is_real: !!cam.is_real,
        x: saved?.x ?? preset.x,
        y: saved?.y ?? preset.y,
        angle: saved?.angle ?? preset.angle,
        fov: saved?.fov ?? preset.fov,
        range: saved?.range ?? preset.range
      }
    })
  }, [effectiveCameras, placements])

  // Active handover circuit sequence: validates stored sequence or auto-maps full perimeter circle
  const activeHandoverSeq = useMemo(() => {
    const valid = handoverSequence.filter(id => cameraNodes.some(c => c.id === id))
    if (valid.length >= 2) {
      return valid
    }
    return autoMapPerimeterCircle(cameraNodes)
  }, [handoverSequence, cameraNodes])

  const activeSelectedCamNode = cameraNodes.find(c => c.id === selectedCamId) || cameraNodes[0]

  // Dynamic scale factor for icons (stays crisp at any zoom level)
  const invZoom = useMemo(() => {
    return Math.max(0.4, Math.min(1.4, 1 / zoom))
  }, [zoom])

  /**
   * CONVERT CLIENT CLICK TO MAP COORDS (1000 x 770 coordinate system)
   * Center is at (500, 385)
   * Forward: screen = 500 + pan.x + (mapX - 500) * zoom
   * Inverse: mapX = 500 + (screen - 500 - pan.x) / zoom
   */
  const clientToMapCoords = useCallback((clientX: number, clientY: number) => {
    if (!svgRef.current) return { x: 500, y: 385 }
    const rect = svgRef.current.getBoundingClientRect()
    const screenX = ((clientX - rect.left) / rect.width) * 1000
    const screenY = ((clientY - rect.top) / rect.height) * 770
    const mapX = Math.round(500 + (screenX - 500 - pan.x) / zoom)
    const mapY = Math.round(385 + (screenY - 385 - pan.y) / zoom)
    return {
      x: Math.max(15, Math.min(985, mapX)),
      y: Math.max(15, Math.min(755, mapY))
    }
  }, [pan, zoom])

  // Update placement of a camera
  const updatePlacement = useCallback((camId: string, props: Partial<CameraPlacement>) => {
    if (isLocked) {
      setTacticalActionMsg('🔒 Layout is currently locked. Toggle Lock to edit.')
      setTimeout(() => setTacticalActionMsg(null), 2000)
      return
    }
    setPlacements(prev => {
      const existing = prev[camId] || {
        x: 500,
        y: 385,
        angle: 180,
        fov: 75,
        range: 90
      }
      const updated = { ...prev, [camId]: { ...existing, ...props } }
      try {
        localStorage.setItem('garuda_camera_placements', JSON.stringify(updated))
      } catch (e) { console.error(e) }
      return updated
    })
  }, [isLocked])

  // Custom map file upload handler
  function handleMapFileUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    const reader = new FileReader()
    reader.onload = () => {
      if (typeof reader.result === 'string') {
        setCustomMapImage(reader.result)
        try {
          localStorage.setItem('garuda_custom_map_image', reader.result)
        } catch (err) {
          console.warn('Custom map was too large for localStorage, kept in memory.')
        }
        setTacticalActionMsg('🗺️ Custom Map Loaded Successfully!')
        setTimeout(() => setTacticalActionMsg(null), 3000)
      }
    }
    reader.readAsDataURL(file)
  }

  function removeCustomMap() {
    setCustomMapImage(null)
    try {
      localStorage.removeItem('garuda_custom_map_image')
    } catch {}
    setTacticalActionMsg('↺ Restored College Satellite View')
    setTimeout(() => setTacticalActionMsg(null), 2500)
  }

  // GLOBAL DRAGGING & PANNING LISTENER (Never drops or freezes outside SVG)
  useEffect(() => {
    if (!draggingCamId && !rotatingCamId && !isPanning) return

    function onPointerMove(e: MouseEvent) {
      if (draggingCamId) {
        const coords = clientToMapCoords(e.clientX, e.clientY)
        updatePlacement(draggingCamId, { x: coords.x, y: coords.y })
      } else if (rotatingCamId) {
        const targetCam = cameraNodes.find(c => c.id === rotatingCamId)
        if (!targetCam) return
        const coords = clientToMapCoords(e.clientX, e.clientY)
        const dx = coords.x - targetCam.x
        const dy = coords.y - targetCam.y
        let angleDeg = Math.round((Math.atan2(dx, -dy) * 180) / Math.PI)
        if (angleDeg < 0) angleDeg += 360
        updatePlacement(rotatingCamId, { angle: angleDeg })
      } else if (isPanning) {
        setPan({
          x: Math.round(e.clientX - panStartRef.current.x),
          y: Math.round(e.clientY - panStartRef.current.y)
        })
      }
    }

    function onPointerUp() {
      if (draggingCamId) {
        setTacticalActionMsg(`📍 Camera Position Saved!`)
        setTimeout(() => setTacticalActionMsg(null), 2000)
      }
      setDraggingCamId(null)
      setRotatingCamId(null)
      setIsPanning(false)
    }

    window.addEventListener('mousemove', onPointerMove)
    window.addEventListener('mouseup', onPointerUp)

    return () => {
      window.removeEventListener('mousemove', onPointerMove)
      window.removeEventListener('mouseup', onPointerUp)
    }
  }, [draggingCamId, rotatingCamId, isPanning, clientToMapCoords, updatePlacement, cameraNodes])

  // Pedestrian movement tick simulation
  useEffect(() => {
    if (!isSimRunning) return

    const interval = setInterval(() => {
      setPedestrians(prev => {
        return prev.map(ped => {
          const route = CAMPUS_SATELLITE_ROUTES[ped.routeIndex % CAMPUS_SATELLITE_ROUTES.length]
          if (!route || route.length < 2) return ped

          const stepSize = ped.role === 'security' ? 0.015 : 0.012
          let nextProgress = ped.routeProgress + stepSize
          if (nextProgress >= 1) nextProgress = 0

          const totalSegments = route.length - 1
          const segFloat = nextProgress * totalSegments
          const segIdx = Math.floor(segFloat)
          const segProgress = segFloat - segIdx

          const p1 = route[segIdx]
          const p2 = route[Math.min(segIdx + 1, route.length - 1)]

          const curX = Math.round(p1.x + (p2.x - p1.x) * segProgress)
          const curY = Math.round(p1.y + (p2.y - p1.y) * segProgress)

          const angleRad = Math.atan2(p2.x - p1.x, -(p2.y - p1.y))
          let headingDeg = Math.round((angleRad * 180) / Math.PI)
          if (headingDeg < 0) headingDeg += 360

          let trackingCam: (typeof cameraNodes)[0] | null = null
          for (const cam of cameraNodes) {
            if (isPointInCone(curX, curY, cam)) {
              trackingCam = cam
              break
            }
          }

          return {
            ...ped,
            x: curX,
            y: curY,
            headingDeg,
            routeProgress: nextProgress,
            status: trackingCam ? 'TRACKED' : 'BLIND_SPOT',
            trackingCamName: trackingCam ? trackingCam.name.split(':')[0] : undefined,
            dwellSeconds: ped.dwellSeconds + 1
          }
        })
      })
    }, 200)

    return () => clearInterval(interval)
  }, [cameraNodes, isSimRunning])

  // Lock toggle
  function toggleLock() {
    setIsLocked(prev => {
      const next = !prev
      try {
        localStorage.setItem('garuda_camera_locked', JSON.stringify(next))
      } catch (e) { console.error(e) }
      if (next) {
        setPlacingCamId(null)
        setDraggingCamId(null)
        setTacticalActionMsg('🔒 Layout Locked')
      } else {
        setTacticalActionMsg('🔓 Edit Mode Active — Drag camera nodes or dial')
      }
      setTimeout(() => setTacticalActionMsg(null), 2500)
      return next
    })
  }

  // Reset to default presets
  function resetToPresets() {
    if (isLocked) {
      setTacticalActionMsg('🔒 Unlock positions first')
      setTimeout(() => setTacticalActionMsg(null), 2000)
      return
    }
    const fresh: Record<string, CameraPlacement> = {}
    cameraNodes.forEach((cam, idx) => {
      const preset = COLLEGE_CAMPUS_PRESETS[idx % COLLEGE_CAMPUS_PRESETS.length]
      fresh[cam.id] = {
        x: preset.x,
        y: preset.y,
        angle: preset.angle,
        fov: preset.fov,
        range: preset.range
      }
    })
    setPlacements(fresh)
    try {
      localStorage.setItem('garuda_camera_placements', JSON.stringify(fresh))
    } catch (e) { console.error(e) }
    setTacticalActionMsg('↺ Cameras Snapped to College Satellite Perimeter Layout')
    setTimeout(() => setTacticalActionMsg(null), 2500)
  }

  // Generate SVG vision cone path
  function generateConePath(x: number, y: number, angleDeg: number, fovDeg: number, range: number): string {
    const halfFov = fovDeg / 2
    const startAngle = (angleDeg - halfFov) * (Math.PI / 180)
    const endAngle = (angleDeg + halfFov) * (Math.PI / 180)

    const x1 = x + range * Math.sin(startAngle)
    const y1 = y - range * Math.cos(startAngle)
    const x2 = x + range * Math.sin(endAngle)
    const y2 = y - range * Math.cos(endAngle)

    const largeArcFlag = fovDeg > 180 ? 1 : 0
    return `M ${x} ${y} L ${x1.toFixed(1)} ${y1.toFixed(1)} A ${range} ${range} 0 ${largeArcFlag} 1 ${x2.toFixed(1)} ${y2.toFixed(1)} Z`
  }

  // Map background click handler
  function handleMapClick(e: React.MouseEvent<SVGSVGElement>) {
    if (isPanning || draggingCamId || rotatingCamId) return
    const coords = clientToMapCoords(e.clientX, e.clientY)

    if (placingCamId) {
      updatePlacement(placingCamId, { x: coords.x, y: coords.y })
      setPlacingCamId(null)
      setTacticalActionMsg(`📍 Camera Placed at (${coords.x}, ${coords.y})`)
      setTimeout(() => setTacticalActionMsg(null), 2500)
    } else if (activeSelectedCamNode && !isLocked && editorMode === 'setup') {
      updatePlacement(activeSelectedCamNode.id, { x: coords.x, y: coords.y })
      setTacticalActionMsg(`📍 Moved ${activeSelectedCamNode.name.split(':')[0]} to (${coords.x}, ${coords.y})`)
      setTimeout(() => setTacticalActionMsg(null), 2000)
    }
  }

  // Background map pan start on left mouse click
  function handleMouseDownOnBackground(e: React.MouseEvent<SVGSVGElement>) {
    if (e.button === 0 && !placingCamId) {
      setIsPanning(true)
      panStartRef.current = { x: e.clientX - pan.x, y: e.clientY - pan.y }
    }
  }

  // Zoom with scroll wheel centered on mouse cursor
  function handleWheel(e: React.WheelEvent<SVGSVGElement>) {
    e.preventDefault()
    if (!svgRef.current) return
    const rect = svgRef.current.getBoundingClientRect()
    const screenX = ((e.clientX - rect.left) / rect.width) * 1000
    const screenY = ((e.clientY - rect.top) / rect.height) * 770

    const delta = e.deltaY < 0 ? 0.15 : -0.15
    const newZoom = Math.min(3.5, Math.max(0.6, Number((zoom + delta).toFixed(2))))
    if (newZoom === zoom) return

    // Keep point under cursor stationary:
    const scaleRatio = newZoom / zoom
    const newPanX = Math.round(screenX - 500 - (screenX - 500 - pan.x) * scaleRatio)
    const newPanY = Math.round(screenY - 385 - (screenY - 385 - pan.y) * scaleRatio)

    setZoom(newZoom)
    setPan({ x: newPanX, y: newPanY })
  }

  // Zoom button handler (zooms around center)
  function handleZoomButton(delta: number) {
    const newZoom = Math.min(3.5, Math.max(0.6, Number((zoom + delta).toFixed(2))))
    const scaleRatio = newZoom / zoom
    setZoom(newZoom)
    setPan(prev => ({
      x: Math.round(prev.x * scaleRatio),
      y: Math.round(prev.y * scaleRatio)
    }))
  }

  // Handover Simulation along Campus Perimeter Circuit
  function startHandoverSimulation(stepInRing = 0, isNewRandomRun = false) {
    const seq = activeHandoverSeq
    const ringSize = seq.length
    if (ringSize < 2 || cameraNodes.length < 2) return

    if (handoverLoopTimeoutRef.current) clearTimeout(handoverLoopTimeoutRef.current)
    if (handoverIntervalRef.current) clearInterval(handoverIntervalRef.current)

    let ringStartIndex: number
    if (isNewRandomRun || stepInRing === 0) {
      // Pick random camera node to start the run as requested by user!
      ringStartIndex = Math.floor(Math.random() * ringSize)
      activeRingStartRef.current = ringStartIndex
    } else {
      ringStartIndex = activeRingStartRef.current
    }

    const currentStep = stepInRing % ringSize
    const fromIdx = (ringStartIndex + currentStep) % ringSize
    const toIdx = (ringStartIndex + currentStep + 1) % ringSize

    const fromId = seq[fromIdx]
    const toId = seq[toIdx]

    const fromCam = cameraNodes.find(c => c.id === fromId) || cameraNodes[fromIdx % cameraNodes.length]
    const toCam = cameraNodes.find(c => c.id === toId) || cameraNodes[toIdx % cameraNodes.length]

    const realFromCam = effectiveCameras.find(c => c.camera_id === fromCam.id) || null
    const realToCam = effectiveCameras.find(c => c.camera_id === toCam.id) || null

    const previewFrom: Camera = realFromCam || {
      camera_id: fromCam.id,
      name: fromCam.name,
      location: fromCam.location,
      status: fromCam.status,
      source_type: 'webcam',
      source_uri: ''
    }
    setActiveCamPreview(previewFrom)
    setSelectedCamId(fromCam.id)

    const isLoopCompletionLeg = currentStep === ringSize - 1
    const originCam = cameraNodes.find(c => c.id === seq[ringStartIndex]) || fromCam

    setHandover({
      active: true,
      currentLeg: currentStep,
      stage: 'in_cam',
      progress: 0,
      x: fromCam.x,
      y: fromCam.y,
      fromCamId: fromCam.id,
      toCamId: toCam.id,
      fromCamName: fromCam.name.split(':')[0],
      toCamName: toCam.name.split(':')[0],
      etaCountdown: 4,
      msg: currentStep === 0
        ? `🎲 [RANDOM START: ${fromCam.name.split(':')[0]}] Perimeter target acquired. Initiating ${ringSize}-sensor circular handover loop.`
        : `🚨 [LEG ${currentStep + 1}/${ringSize}] Subject tracked at ${fromCam.name.split(':')[0]} ➔ Handing over to ${toCam.name.split(':')[0]}.`
    })

    handoverLoopTimeoutRef.current = setTimeout(() => {
      let step = 0
      const totalSteps = 30
      handoverIntervalRef.current = setInterval(() => {
        step++
        const progress = step / totalSteps
        const curX = Math.round(fromCam.x + (toCam.x - fromCam.x) * progress)
        const curY = Math.round(fromCam.y + (toCam.y - fromCam.y) * progress)
        const remainingEta = Math.max(1, Math.round(3.5 * (1 - progress)))

        setHandover(prev => ({
          ...prev,
          stage: 'transition',
          progress,
          x: curX,
          y: curY,
          etaCountdown: remainingEta,
          msg: `🟡 Target crossing perimeter: ${fromCam.name.split(':')[0]} ➔ ${toCam.name.split(':')[0]} (Re-ID: 98.9%). ETA: ${remainingEta}s.`
        }))

        if (step >= totalSteps) {
          clearInterval(handoverIntervalRef.current)
          const previewTo: Camera = realToCam || {
            camera_id: toCam.id,
            name: toCam.name,
            location: toCam.location,
            status: toCam.status,
            source_type: 'webcam',
            source_uri: ''
          }
          setActiveCamPreview(previewTo)
          setSelectedCamId(toCam.id)

          setHandover(prev => ({
            ...prev,
            stage: 'handover_confirmed',
            progress: 1,
            x: toCam.x,
            y: toCam.y,
            etaCountdown: 0,
            msg: isLoopCompletionLeg
              ? `🏁 [CIRCUIT CLOSED] Handover completed full circle back to origin (${originCam.name.split(':')[0]}) across all ${ringSize} cameras.`
              : `🟢 Handover Confirmed! Target acquired by ${toCam.name.split(':')[0]}.`
          }))

          handoverLoopTimeoutRef.current = setTimeout(() => {
            if (isLoopCompletionLeg) {
              // Circle complete! Start next random jump circle loop to maintain surveillance
              startHandoverSimulation(0, true)
            } else {
              startHandoverSimulation(currentStep + 1, false)
            }
          }, 2200)
        }
      }, 100)
    }, 1200)
  }

  function stopHandoverSimulation() {
    if (handoverLoopTimeoutRef.current) clearTimeout(handoverLoopTimeoutRef.current)
    if (handoverIntervalRef.current) clearInterval(handoverIntervalRef.current)
    setHandover(prev => ({ ...prev, active: false, stage: 'in_cam', progress: 0 }))
    setTacticalActionMsg('⏹ Handover Stopped')
    setTimeout(() => setTacticalActionMsg(null), 2000)
  }

  function triggerAction(actionName: string) {
    setTacticalActionMsg(`⚡ DISPATCHED: ${actionName}`)
    setTimeout(() => setTacticalActionMsg(null), 3000)
  }

  // =========================================================================
  // LIVE GOOGLE SATELLITE MAP (LEAFLET INTEGRATION)
  // =========================================================================
  useEffect(() => {
    if (viewMode !== 'google_maps') {
      if (leafletMapRef.current) {
        leafletMapRef.current.remove()
        leafletMapRef.current = null
      }
      return
    }

    if (!leafletContainerRef.current) return

    // Initialize Leaflet with Google Satellite Hybrid Tiles
    const map = L.map(leafletContainerRef.current, {
      center: [20.5937, 78.9629], // Center India (can jump anywhere)
      zoom: 5,
      zoomControl: false
    })
    leafletMapRef.current = map

    // Google Maps Satellite Hybrid Tile Layer
    L.tileLayer('https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}', {
      maxZoom: 21,
      subdomains: ['mt0', 'mt1', 'mt2', 'mt3'],
      attribution: '© Google Satellite'
    }).addTo(map)

    L.control.zoom({ position: 'bottomright' }).addTo(map)

    return () => {
      if (leafletMapRef.current) {
        leafletMapRef.current.remove()
        leafletMapRef.current = null
      }
    }
  }, [viewMode])

  // Invalidate map size after rotation changes to trigger loading of corner tiles
  useEffect(() => {
    if (viewMode === 'google_maps' && leafletMapRef.current) {
      const timer = setTimeout(() => {
        leafletMapRef.current?.invalidateSize()
      }, 350)
      return () => clearTimeout(timer)
    }
  }, [mapRotation, viewMode])

  // Geocode / Jump on Google Satellite map
  function handleSearchLocation(e: React.FormEvent) {
    e.preventDefault()
    if (!leafletMapRef.current || !searchLocationQuery.trim()) return

    fetch(`https://nominatim.openstreetmap.org/search?format=json&q=${encodeURIComponent(searchLocationQuery)}`)
      .then(res => res.json())
      .then(data => {
        if (data && data.length > 0) {
          const lat = parseFloat(data[0].lat)
          const lon = parseFloat(data[0].lon)
          leafletMapRef.current?.setView([lat, lon], 18)
          setTacticalActionMsg(`📍 Navigated to: ${data[0].display_name.split(',')[0]}`)
          setTimeout(() => setTacticalActionMsg(null), 3000)
        } else {
          setTacticalActionMsg('⚠️ Location not found. Try another search query.')
          setTimeout(() => setTacticalActionMsg(null), 3000)
        }
      })
      .catch(() => {
        setTacticalActionMsg('⚠️ Geocoding service busy. Pan manually on map.')
        setTimeout(() => setTacticalActionMsg(null), 3000)
      })
  }

  return (
    <div className="flex flex-col h-full bg-[#050811] text-slate-100 rounded-lg border border-ops-border overflow-hidden select-none font-sans">
      
      {/* Hidden file input for custom map upload */}
      <input
        type="file"
        ref={fileInputRef}
        onChange={handleMapFileUpload}
        accept="image/*"
        className="hidden"
      />

      {/* Top Header Navigation Ribbon */}
      <div className="px-4 py-2 bg-[#090e1a] border-b border-ops-border flex items-center justify-between text-xs shrink-0 gap-3">
        
        {/* Left Section: Status Beacon & View Mode */}
        <div className="flex items-center gap-3 shrink-0">
          <div className="flex items-center gap-2">
            <span className="relative flex h-2.5 w-2.5">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
              <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
            </span>
            <span className="font-bold tracking-wider font-mono text-white text-xs">
              TACTICAL RADAR VIEW
            </span>
          </div>

          <span className="text-slate-600">|</span>

          {/* Active Cameras Count Badge */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-black/60 rounded border border-ops-border font-mono text-[11px] text-slate-300">
            <span className="text-slate-500">Sensors:</span>
            <span className="text-cyan-400 font-bold">{cameraNodes.length} Nodes</span>
          </div>

          {/* Pedestrians tracked count */}
          <div className="flex items-center gap-1.5 px-2.5 py-1 bg-black/60 rounded border border-ops-border font-mono text-[11px] text-slate-300">
            <span className="text-slate-500">Targets:</span>
            <span className="text-emerald-400 font-bold">{pedestrians.filter(p => p.status === 'TRACKED').length}/{pedestrians.length} Tracked</span>
          </div>
        </div>

        {/* Center: Handover Active Status Bar / Demo Controls */}
        {handover.active ? (
          <div className="flex items-center gap-2 px-3 py-1 bg-amber-950/40 border border-amber-500/60 rounded font-mono text-[11px] text-amber-300 animate-pulse">
            <span className="w-2 h-2 rounded-full bg-amber-400 animate-ping" />
            <span className="truncate max-w-sm font-semibold">{handover.msg}</span>
            <button
              onClick={stopHandoverSimulation}
              className="ml-2 px-1.5 py-0.5 bg-red-500/30 hover:bg-red-500/50 text-red-200 rounded text-[10px] border border-red-500/50 font-bold transition-colors"
            >
              Stop
            </button>
          </div>
        ) : (
          <div className="flex items-center gap-1.5 bg-black/40 px-1.5 py-1 rounded-md border border-ops-border/60">
            <NavTooltipBtn
              icon={<RotateCw className="w-3.5 h-3.5 text-ops-accent" />}
              onClick={() => startHandoverSimulation(0, true)}
              title="Run Handover Simulation"
              subtitle="Start perimeter pursuit simulation across connected nodes with automatic camera handoff"
              badge="AUTO-LOOP"
              activeClass="bg-ops-accent/30 text-ops-accent border-ops-accent"
              inactiveClass="bg-black/60 text-ops-accent hover:bg-ops-accent/20 border-ops-accent/40"
            />
            <NavTooltipBtn
              icon={<Compass className="w-3.5 h-3.5 text-cyan-400" />}
              onClick={() => setShowHandoverModal(true)}
              title="Camera Placement & Circuit"
              subtitle="Configure camera coordinates, azimuth, and custom circular handover sequences"
              inactiveClass="bg-black/60 text-cyan-300 hover:bg-cyan-500/20 border-cyan-500/40"
            />
            <NavTooltipBtn
              icon={isSimRunning ? <span className="text-[11px]">⏸</span> : <Play className="w-3 h-3 text-emerald-400" />}
              onClick={() => setIsSimRunning(!isSimRunning)}
              title={isSimRunning ? "Pause Radar Simulation" : "Resume Radar Simulation"}
              subtitle={isSimRunning ? "Freeze real-time target movement and perimeter radar sweeps" : "Resume target walking simulation and sensor sweeps"}
              active={isSimRunning}
              activeClass="bg-emerald-500/25 text-emerald-300 border-emerald-500/50"
              inactiveClass="bg-slate-800/80 text-slate-400 border-slate-700"
            />
          </div>
        )}

        {/* Right Section: View Modes (College Satellite | Live Google Maps | Blueprint | Upload) & Lock */}
        <div className="flex items-center gap-2 shrink-0">
          
          {/* Main View Mode Selector */}
          <div className="flex bg-black/60 p-0.5 rounded border border-ops-border text-xs font-mono gap-0.5">
            <NavTooltipBtn
              icon={<span className="text-xs">🛰️</span>}
              onClick={() => setViewMode('college_satellite')}
              active={viewMode === 'college_satellite'}
              activeClass="bg-emerald-500/30 text-emerald-300 border-emerald-500/60 font-bold"
              inactiveClass="bg-transparent text-slate-400 hover:text-white border-transparent"
              title="College Campus Satellite"
              subtitle="High-resolution campus satellite imagery with perimeter camera layout"
              badge="LOCAL"
            />
            <NavTooltipBtn
              icon={<span className="text-xs">🌐</span>}
              onClick={() => setViewMode('google_maps')}
              active={viewMode === 'google_maps'}
              activeClass="bg-cyan-500/30 text-cyan-300 border-cyan-500/60 font-bold"
              inactiveClass="bg-transparent text-slate-400 hover:text-white border-transparent"
              title="Live Google Satellite"
              subtitle="Interactive worldwide satellite map tiles with zoom & pan"
              badge="GLOBAL"
            />
            <NavTooltipBtn
              icon={<span className="text-xs">📐</span>}
              onClick={() => setViewMode('blueprint')}
              active={viewMode === 'blueprint'}
              activeClass="bg-blue-500/30 text-blue-300 border-blue-500/60 font-bold"
              inactiveClass="bg-transparent text-slate-400 hover:text-white border-transparent"
              title="Tactical Blueprint"
              subtitle="Vector CAD schematic of campus wings, corridors & security zones"
              badge="CAD"
            />
            <NavTooltipBtn
              icon={<span className="text-xs">👁️</span>}
              onClick={() => setViewMode('gods_eye_live')}
              active={viewMode === 'gods_eye_live'}
              activeClass="bg-cyan-500/30 text-cyan-200 border-cyan-400/80 font-bold shadow-[0_0_12px_rgba(6,182,212,0.4)]"
              inactiveClass="bg-transparent text-slate-400 hover:text-white border-transparent"
              title="God's Eye View"
              subtitle="Geospatial Intelligence & Tactical Orbit View"
              badge="GEV"
            />
          </div>

          {/* Custom Map Upload Button */}
          {customMapImage ? (
            <div className="relative group/custom inline-flex items-center gap-1 bg-black/60 px-2 py-1 rounded border border-cyan-500/50 text-xs font-mono">
              <span className="text-xs">🗺️</span>
              <button
                onClick={removeCustomMap}
                className="text-red-400 hover:text-red-300 ml-0.5 text-[11px] font-bold cursor-pointer"
                title="Remove custom map and return to college satellite view"
              >
                ✕
              </button>
              <div className="absolute top-full mt-2 right-0 hidden group-hover/custom:flex flex-col items-center pointer-events-none z-50 whitespace-nowrap drop-shadow-2xl">
                <div className="w-2 h-2 bg-[#090e1a] border-t border-l border-cyan-500/60 rotate-45 -mb-1 z-10" />
                <div className="bg-[#090e1a]/95 backdrop-blur-md border border-cyan-500/60 text-slate-100 text-[11px] px-2.5 py-1 rounded shadow-2xl">
                  <span className="font-bold text-cyan-300 block font-mono">Custom Map Active</span>
                  <span className="text-[10px] text-slate-400">Click ✕ to remove custom map</span>
                </div>
              </div>
            </div>
          ) : (
            <NavTooltipBtn
              icon={<span className="text-xs">📁</span>}
              onClick={() => fileInputRef.current?.click()}
              title="Upload Custom Floorplan"
              subtitle="Import custom CAD blueprint, floorplan, or aerial imagery"
              inactiveClass="bg-black/60 text-slate-300 hover:text-white hover:bg-white/10 border-ops-border"
            />
          )}

          {/* Lock / Unlock Toggle Button */}
          <NavTooltipBtn
            icon={<span className="text-xs">{isLocked ? '🔒' : '🔓'}</span>}
            onClick={toggleLock}
            active={!isLocked}
            activeClass="bg-emerald-500/25 text-emerald-300 border-emerald-500/60 shadow-[0_0_8px_rgba(16,185,129,0.25)]"
            inactiveClass="bg-red-500/20 text-red-300 border-red-500/50"
            title={isLocked ? 'Camera Layout Locked' : 'Camera Edit Mode Active'}
            subtitle={isLocked ? 'Click to unlock repositioning & angle adjustment' : 'Click to lock camera positions and prevent movement'}
            badge={isLocked ? 'LOCKED' : 'EDIT'}
          />

          {/* Zoom Buttons (for SVG views) */}
          {viewMode !== 'google_maps' && viewMode !== 'gods_eye_live' && (
            <div className="flex items-center gap-1 bg-black/60 p-0.5 rounded border border-ops-border text-xs font-mono">
              <button
                onClick={() => handleZoomButton(-0.2)}
                className="w-6 h-6 flex items-center justify-center hover:bg-white/10 rounded text-slate-300 font-bold cursor-pointer"
                title="Zoom Out"
              >
                -
              </button>
              <span className="w-9 text-center text-cyan-400 font-bold text-[11px]">
                {Math.round(zoom * 100)}%
              </span>
              <button
                onClick={() => handleZoomButton(0.2)}
                className="w-6 h-6 flex items-center justify-center hover:bg-white/10 rounded text-slate-300 font-bold cursor-pointer"
                title="Zoom In"
              >
                +
              </button>
              <button
                onClick={() => { setZoom(1.0); setPan({ x: 0, y: 0 }) }}
                className="w-6 h-6 flex items-center justify-center hover:bg-white/10 rounded text-[10px] text-slate-400 hover:text-white border-l border-ops-border/60 cursor-pointer"
                title="Reset Zoom & Pan"
              >
                ↺
              </button>
            </div>
          )}
        </div>
      </div>

      {/* Main Content: Left Controls (3 cols) | Center Map (6 cols) | Right Stream (3 cols) */}
      <div className="grid grid-cols-12 flex-1 min-h-0">
        
        {/* Left Sidebar: Camera Controls & Positioning */}
        <div className="col-span-3 p-3 border-r border-ops-border bg-[#070b14]/95 flex flex-col justify-between overflow-y-auto text-xs space-y-3">
          
          {/* Mode Switcher */}
          <div className="grid grid-cols-2 gap-1 p-1 bg-black/60 rounded border border-ops-border font-mono text-xs">
            <button
              onClick={() => setEditorMode('tracking')}
              className={`py-1 rounded transition-all text-center font-bold ${
                editorMode === 'tracking' ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50' : 'text-slate-400 hover:text-white'
              }`}
            >
              🎯 Live Tracking
            </button>
            <button
              onClick={() => setEditorMode('setup')}
              className={`py-1 rounded transition-all text-center font-bold ${
                editorMode === 'setup' ? 'bg-ops-accent/20 text-ops-accent border border-ops-accent/50' : 'text-slate-400 hover:text-white'
              }`}
            >
              ⚙️ Camera Config
            </button>
          </div>

          {/* Quick Notice: Dragging is Live */}
          <div className="p-2 rounded bg-emerald-950/30 border border-emerald-800/40 text-[11px] font-mono text-emerald-300 flex items-center justify-between">
            <span>🖱️ Drag nodes or orange dial to adjust!</span>
          </div>

          {/* Active Selected Camera Calibration Controls */}
          {activeSelectedCamNode ? (
            <div className="space-y-2.5 p-2.5 rounded bg-black/40 border border-ops-border">
              <div className="flex items-center justify-between pb-1 border-b border-ops-border/60">
                <span className="font-bold text-white font-mono text-xs truncate max-w-[170px]">
                  {activeSelectedCamNode.name}
                </span>
                <span className="text-cyan-400 font-mono text-[10px]">
                  ({activeSelectedCamNode.x}, {activeSelectedCamNode.y})
                </span>
              </div>

              {/* Action Buttons: Relocate to Click & Reset */}
              <div className="grid grid-cols-2 gap-1.5">
                <button
                  onClick={() => {
                    setPlacingCamId(activeSelectedCamNode.id)
                    setTacticalActionMsg(`📍 Click anywhere on the map to place ${activeSelectedCamNode.name.split(':')[0]}`)
                  }}
                  className={`py-1.5 px-2 rounded font-mono text-[11px] font-bold border transition-all text-center ${
                    placingCamId === activeSelectedCamNode.id
                      ? 'bg-amber-500 text-black animate-pulse border-amber-400'
                      : 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40 hover:bg-cyan-500/30'
                  }`}
                >
                  {placingCamId === activeSelectedCamNode.id ? 'Click Map Now...' : '⌖ Click to Place'}
                </button>
                <button
                  onClick={resetToPresets}
                  className="py-1.5 px-2 rounded font-mono text-[11px] bg-white/5 hover:bg-white/10 text-slate-300 border border-ops-border transition-all"
                >
                  ↺ Reset Presets
                </button>
              </div>

              {/* X Position Slider */}
              <div className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="text-slate-400">Position X (West ➔ East):</span>
                  <span className="text-white font-bold">{activeSelectedCamNode.x}px</span>
                </div>
                <input
                  type="range"
                  min="20"
                  max="980"
                  step="5"
                  disabled={isLocked}
                  value={activeSelectedCamNode.x}
                  onChange={(e) => updatePlacement(activeSelectedCamNode.id, { x: Number(e.target.value) })}
                  className="w-full accent-cyan-400 cursor-pointer disabled:opacity-40"
                />
              </div>

              {/* Y Position Slider */}
              <div className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="text-slate-400">Position Y (North ➔ South):</span>
                  <span className="text-white font-bold">{activeSelectedCamNode.y}px</span>
                </div>
                <input
                  type="range"
                  min="20"
                  max="750"
                  step="5"
                  disabled={isLocked}
                  value={activeSelectedCamNode.y}
                  onChange={(e) => updatePlacement(activeSelectedCamNode.id, { y: Number(e.target.value) })}
                  className="w-full accent-cyan-400 cursor-pointer disabled:opacity-40"
                />
              </div>

              {/* Facing Angle Slider */}
              <div className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="text-slate-400">Facing Angle (Azimuth):</span>
                  <span className="text-cyan-400 font-bold">{activeSelectedCamNode.angle}°</span>
                </div>
                <input
                  type="range"
                  min="0"
                  max="360"
                  step="5"
                  disabled={isLocked}
                  value={activeSelectedCamNode.angle}
                  onChange={(e) => updatePlacement(activeSelectedCamNode.id, { angle: Number(e.target.value) })}
                  className="w-full accent-cyan-400 cursor-pointer disabled:opacity-40"
                />
                <div className="flex justify-between text-[9px] font-mono text-slate-500">
                  <span>0° (N)</span>
                  <span>90° (E)</span>
                  <span>180° (S)</span>
                  <span>270° (W)</span>
                  <span>360°</span>
                </div>
              </div>

              {/* Coverage Range Slider */}
              <div className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="text-slate-400">Vision Range:</span>
                  <span className="text-emerald-400 font-bold">
                    {Math.round(activeSelectedCamNode.range * 0.25)}m ({activeSelectedCamNode.range}px)
                  </span>
                </div>
                <input
                  type="range"
                  min="40"
                  max="140"
                  step="5"
                  disabled={isLocked}
                  value={activeSelectedCamNode.range}
                  onChange={(e) => updatePlacement(activeSelectedCamNode.id, { range: Number(e.target.value) })}
                  className="w-full accent-emerald-400 cursor-pointer disabled:opacity-40"
                />
              </div>

              {/* Field of View Slider */}
              <div className="space-y-1">
                <div className="flex justify-between text-[11px] font-mono">
                  <span className="text-slate-400">Field of View (FOV):</span>
                  <span className="text-ops-accent font-bold">{activeSelectedCamNode.fov}°</span>
                </div>
                <input
                  type="range"
                  min="30"
                  max="115"
                  step="5"
                  disabled={isLocked}
                  value={activeSelectedCamNode.fov}
                  onChange={(e) => updatePlacement(activeSelectedCamNode.id, { fov: Number(e.target.value) })}
                  className="w-full accent-ops-accent cursor-pointer disabled:opacity-40"
                />
              </div>
            </div>
          ) : null}

          {/* Camera Selector List */}
          <div className="space-y-1">
            <div className="text-[10px] font-mono text-slate-500 uppercase flex items-center justify-between">
              <span>Perimeter Nodes ({cameraNodes.length}):</span>
              <span className="text-slate-400">Click to Select</span>
            </div>
            <div className="space-y-1 max-h-36 overflow-y-auto pr-1">
              {cameraNodes.map((cam) => {
                const isSel = activeSelectedCamNode?.id === cam.id
                return (
                  <div
                    key={cam.id}
                    onClick={() => {
                      setSelectedCamId(cam.id)
                      const realCam = effectiveCameras.find(c => c.camera_id === cam.id) || null
                      setActiveCamPreview(realCam)
                      onSelectCamera?.(cam.id)
                    }}
                    className={`p-1.5 rounded border text-[11px] font-mono flex items-center justify-between cursor-pointer transition-all ${
                      isSel
                        ? 'bg-cyan-500/20 border-cyan-400 text-white font-bold'
                        : 'bg-black/30 border-ops-border/60 text-slate-300 hover:border-slate-500'
                    }`}
                  >
                    <div className="flex items-center gap-1.5 truncate">
                      <span className="w-2 h-2 rounded-full bg-emerald-400" />
                      <span className="truncate">{cam.name}</span>
                    </div>
                    <span className="text-[10px] text-slate-500">{cam.angle}°</span>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Action Feedback banner */}
          {tacticalActionMsg && (
            <div className="p-1.5 rounded bg-emerald-500/20 border border-emerald-500 text-[11px] text-emerald-300 text-center font-mono">
              {tacticalActionMsg}
            </div>
          )}
        </div>

        {/* Center: Satellite / Google Maps Tactical Display */}
        <div className="col-span-6 relative flex flex-col items-center justify-center p-2 bg-[#02050b] overflow-hidden">
          
          {/* Placing Banner Alert */}
          {placingCamId && (
            <div className="absolute top-4 left-1/2 -translate-x-1/2 bg-amber-500 text-black px-4 py-1.5 rounded-full font-mono text-xs font-bold shadow-lg shadow-amber-500/30 z-30 flex items-center gap-2 animate-bounce">
              <span>📍 Click anywhere on the map to place {effectiveCameras.find(c => c.camera_id === placingCamId)?.name?.split(':')[0] || 'Camera'}</span>
              <button onClick={() => setPlacingCamId(null)} className="text-black font-extrabold hover:underline">✕ Cancel</button>
            </div>
          )}

          {/* Top Overlay Legend (Only on 2D SVG & Leaflet modes) */}
          {viewMode !== 'gods_eye_live' && (
            <div className="absolute top-3 left-4 pointer-events-none z-10 flex items-center gap-2 font-mono text-[11px]">
              <span className="text-cyan-400 font-bold">
                {viewMode === 'college_satellite' ? 'COLLEGE CAMPUS SATELLITE C2' :
                 viewMode === 'google_maps' ? 'GOOGLE MAPS LIVE SATELLITE' :
                 'TACTICAL BLUEPRINT'}
              </span>
              <span className="text-slate-600">|</span>
              <span className="text-emerald-400">Perimeter Camera Network Active</span>
            </div>
          )}

          {/* ========================================================================= */}
          {/* MODE 1: GOD'S EYE VIEW (TACTICAL PICTURE & OPTIONAL LIVE STREAM)          */}
          {/* ========================================================================= */}
          {viewMode === 'gods_eye_live' ? (
            <div className="relative w-full h-full min-h-[520px] rounded overflow-hidden border border-cyan-500/40 shadow-2xl bg-[#030712] flex flex-col">
              {/* Header Action Bar */}
              <div className="bg-[#090e1a] border-b border-cyan-500/40 px-3 py-1.5 flex items-center justify-between font-mono text-[11px] shrink-0">
                <div className="flex items-center gap-2">
                  <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                  <span className="text-cyan-300 font-bold tracking-wider">GOD'S EYE VIEW ACTIVATED</span>
                  <span className="text-slate-500 text-[10px] hidden sm:inline">|</span>
                  <span className="text-slate-400 text-[10px] hidden sm:inline">GEOSPATIAL INTELLIGENCE</span>
                </div>
                <div className="flex items-center gap-2">
                  {godViewSubMode === 'live' ? (
                    <button
                      onClick={() => setGodViewSubMode('image')}
                      className="px-2 py-0.5 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-200 border border-cyan-400/50 text-[10px] font-bold transition-colors cursor-pointer"
                    >
                      🖼️ Display Pic
                    </button>
                  ) : (
                    <button
                      onClick={() => setGodViewSubMode('live')}
                      className="px-2 py-0.5 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-600 text-[10px] font-bold transition-colors cursor-pointer"
                      title="Switch to embedded 3D console if running on port 4173"
                    >
                      🌐 Try Live Stream
                    </button>
                  )}
                  <a
                    href={`http://${typeof window !== 'undefined' ? window.location.hostname : 'localhost'}:4173`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-2 py-0.5 rounded bg-slate-800/80 hover:bg-slate-700 text-slate-300 border border-slate-700 text-[10px] font-bold transition-colors"
                  >
                    Open Standalone ↗
                  </a>
                </div>
              </div>

              {/* View Content: Default to high-fidelity Tactical Picture to eliminate blank page */}
              {godViewSubMode === 'image' ? (
                <div className="w-full flex-1 flex flex-col items-center justify-center bg-[#02050b] p-4 relative overflow-hidden select-none">
                  {/* Tactical Cyber Grid Background */}
                  <div className="absolute inset-0 bg-[linear-gradient(to_right,#0e203820_1px,transparent_1px),linear-gradient(to_bottom,#0e203820_1px,transparent_1px)] bg-[size:28px_28px] pointer-events-none" />
                  
                  {/* Subtle Glowing Radial Aura */}
                  <div className="absolute w-96 h-96 rounded-full bg-cyan-500/10 blur-3xl pointer-events-none" />

                  {/* Main Picture Container */}
                  <div className="relative z-10 flex flex-col items-center justify-center max-w-full max-h-full">
                    <img
                      src="/gods_eye_view.png"
                      alt="God's Eye View"
                      className="max-h-[460px] w-auto max-w-full object-contain rounded-xl border border-cyan-500/30 shadow-[0_0_50px_rgba(0,246,255,0.18)] transition-all duration-300 hover:border-cyan-400/60"
                    />
                    
                    {/* Tactical Status Tag */}
                    <div className="mt-3 flex items-center gap-2 px-3 py-1 rounded-full bg-black/60 border border-cyan-500/30 text-[10px] font-mono text-cyan-300 shadow-md">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                      <span>SATELLITE & TACTICAL ORBIT FEED ONLINE</span>
                    </div>
                  </div>
                </div>
              ) : (
                <iframe
                  src={`http://${typeof window !== 'undefined' ? window.location.hostname : 'localhost'}:4173`}
                  title="God's Eye View Console"
                  className="w-full flex-1 border-0"
                  allow="geolocation; microphone; camera; display-capture; fullscreen"
                />
              )}
            </div>
          ) : viewMode !== 'google_maps' ? (
            <svg
              ref={svgRef}
              viewBox="0 0 1000 770"
              onClick={handleMapClick}
              onMouseDown={handleMouseDownOnBackground}
              onWheel={handleWheel}
              className={`w-full h-full max-w-[620px] max-h-[580px] ${
                placingCamId ? 'cursor-crosshair' :
                draggingCamId ? 'cursor-grabbing' :
                rotatingCamId ? 'cursor-alias' :
                isPanning ? 'cursor-grabbing' : 'cursor-grab'
              }`}
            >
              <defs>
                {/* Dynamic Camera Vision Cone Fill (Cyan) */}
                <radialGradient id="dynamicCone" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#00f0ff" stopOpacity="0.5" />
                  <stop offset="70%" stopColor="#00c8d7" stopOpacity="0.2" />
                  <stop offset="100%" stopColor="#00f0ff" stopOpacity="0" />
                </radialGradient>

                {/* Primed Handover Cone Fill (Amber) */}
                <radialGradient id="primedCone" cx="50%" cy="50%" r="50%">
                  <stop offset="0%" stopColor="#ffaa00" stopOpacity="0.55" />
                  <stop offset="70%" stopColor="#ff8800" stopOpacity="0.22" />
                  <stop offset="100%" stopColor="#ffaa00" stopOpacity="0" />
                </radialGradient>

                {/* Blueprint Grid Pattern */}
                <pattern id="blueprintGrid" width="40" height="40" patternUnits="userSpaceOnUse">
                  <path d="M 40 0 L 0 0 0 40" fill="none" stroke="#08223c" strokeWidth="0.6" />
                  <path d="M 200 0 L 0 0 0 200" fill="none" stroke="#0e3458" strokeWidth="1.0" />
                </pattern>
              </defs>

              {/**
               * TRANSFORM GROUP FOR PAN AND SYMMETRICAL CENTER ZOOM:
               * Canvas center is (500, 385)
               */}
              <g transform={`translate(${500 + pan.x}, ${385 + pan.y}) scale(${zoom}) translate(-500, -385)`}>
                
                {/* Background: User's College Satellite Photo */}
                {viewMode === 'college_satellite' && (
                  <g>
                    <image
                      href={customMapImage || "/college_satellite.jpg"}
                      x="0"
                      y="0"
                      width="1000"
                      height="770"
                      preserveAspectRatio="none"
                      opacity={mapOpacity / 100}
                    />
                    {/* Subtle grid overlay to enhance tactical look */}
                    <rect x="0" y="0" width="1000" height="770" fill="url(#blueprintGrid)" opacity="0.15" />
                    {/* Outer border */}
                    <rect x="2" y="2" width="996" height="766" fill="none" stroke="#00ffff" strokeWidth="1" strokeDasharray="8 6" opacity="0.4" />
                  </g>
                )}

                {/* Blueprint View fallback */}
                {viewMode === 'blueprint' && (
                  <g>
                    <rect x="0" y="0" width="1000" height="770" fill="#040a14" />
                    <rect x="0" y="0" width="1000" height="770" fill="url(#blueprintGrid)" />
                    {/* Building Outlines matching the user's college layout */}
                    {/* North Block */}
                    <rect x="70" y="65" width="500" height="130" rx="4" fill="#081728" stroke="#00e5ff" strokeWidth="1.5" />
                    <text x="320" y="135" fill="#cde2f5" fontSize="12" fontFamily="monospace" fontWeight="bold" textAnchor="middle">NORTH ACADEMIC WING</text>
                    {/* East Block with inner quad */}
                    <rect x="670" y="65" width="280" height="665" rx="4" fill="#081728" stroke="#00e5ff" strokeWidth="1.5" />
                    <rect x="760" y="160" width="110" height="260" rx="3" fill="#040a14" stroke="#00ffff" strokeWidth="1" />
                    <text x="815" y="520" fill="#cde2f5" fontSize="12" fontFamily="monospace" fontWeight="bold" textAnchor="middle">EAST COMPLEX</text>
                    {/* South Block with inner quad */}
                    <rect x="120" y="520" width="830" height="210" rx="4" fill="#081728" stroke="#00e5ff" strokeWidth="1.5" />
                    <rect x="260" y="570" width="260" height="110" rx="3" fill="#040a14" stroke="#00ffff" strokeWidth="1" />
                    <text x="390" y="630" fill="#cde2f5" fontSize="12" fontFamily="monospace" fontWeight="bold" textAnchor="middle">SOUTH BLOCK</text>
                    {/* Curved Roadway line */}
                    <path d="M 65 680 L 80 520 L 80 290 Q 80 280 90 280 L 550 280 Q 630 280 630 360 L 630 520" fill="none" stroke="#ffaa00" strokeWidth="18" opacity="0.3" />
                  </g>
                )}

                {/* ========================================================================= */}
                {/* DYNAMIC VISION CONES & CAMERA NODES                                       */}
                {/* ========================================================================= */}
                {cameraNodes.map((cam) => {
                  const isSelected = activeSelectedCamNode?.id === cam.id
                  const isBeingDragged = draggingCamId === cam.id
                  const isPrimed = handover.active && handover.toCamId === cam.id && handover.stage === 'transition'
                  const hasActiveDetection = pedestrians.some(p => p.trackingCamName?.startsWith(cam.name.split(':')[0]))

                  // End coordinates of aiming needle
                  const needleLength = 20
                  const needleRad = (cam.angle * Math.PI) / 180
                  const needleTipX = needleLength * Math.sin(needleRad)
                  const needleTipY = -needleLength * Math.cos(needleRad)

                  return (
                    <g key={cam.id}>
                      {/* Realistic Vision Cone */}
                      <path
                        d={generateConePath(cam.x, cam.y, cam.angle, cam.fov, cam.range)}
                        fill={isPrimed ? 'url(#primedCone)' : hasActiveDetection ? 'url(#primedCone)' : 'url(#dynamicCone)'}
                        stroke={isSelected ? '#00ffff' : isPrimed ? '#ffaa00' : hasActiveDetection ? '#ffaa00' : '#00c8d7'}
                        strokeWidth={isSelected ? 2.5 : 1}
                        strokeDasharray={isSelected ? '4 2' : 'none'}
                        className="cursor-pointer hover:opacity-90"
                        onClick={(e) => {
                          e.stopPropagation()
                          setSelectedCamId(cam.id)
                          const realCam = effectiveCameras.find(c => c.camera_id === cam.id) || {
                            camera_id: cam.id,
                            name: cam.name,
                            location: cam.location,
                            status: cam.status,
                            source_type: 'webcam',
                            source_uri: ''
                          }
                          setActiveCamPreview(realCam)
                          onSelectCamera?.(cam.id)
                        }}
                      />

                      {/* Camera Post Anchor (Inverse zoom scaling so it stays crisp and readable) */}
                      <g transform={`translate(${cam.x}, ${cam.y}) scale(${invZoom})`}>
                        
                        {/* Aiming Direction Needle Line */}
                        <line
                          x1="0"
                          y1="0"
                          x2={needleTipX}
                          y2={needleTipY}
                          stroke={isSelected ? '#ffffff' : '#00ffff'}
                          strokeWidth="3"
                          strokeLinecap="round"
                        />

                        {/* Interactive Angle Rotation Dial Knob (Orange circle at needle tip) */}
                        {isSelected && !isLocked && (
                          <circle
                            cx={needleTipX}
                            cy={needleTipY}
                            r="6"
                            fill="#ffaa00"
                            stroke="#ffffff"
                            strokeWidth="2"
                            className="cursor-alias hover:scale-125 transition-transform shadow-lg"
                            onMouseDown={(e) => {
                              e.stopPropagation()
                              setRotatingCamId(cam.id)
                            }}
                          >
                            <title>Drag to rotate camera angle</title>
                          </circle>
                        )}

                        {/* Main Camera Node Post */}
                        <circle
                          r={isSelected ? 10 : 8}
                          fill={isBeingDragged ? '#ff0055' : isSelected ? '#00ffff' : isPrimed ? '#ffaa00' : hasActiveDetection ? '#ffaa00' : '#0a2542'}
                          stroke={isSelected ? '#ffffff' : '#00b4d8'}
                          strokeWidth={isSelected ? 2.5 : 1.5}
                          className={`transition-all ${!isLocked ? 'cursor-grab active:cursor-grabbing hover:scale-110' : 'cursor-pointer'}`}
                          onClick={(e) => {
                            e.stopPropagation()
                            setSelectedCamId(cam.id)
                            const realCam = effectiveCameras.find(c => c.camera_id === cam.id) || {
                              camera_id: cam.id,
                              name: cam.name,
                              location: cam.location,
                              status: cam.status,
                              source_type: 'webcam',
                              source_uri: ''
                            }
                            setActiveCamPreview(realCam)
                          }}
                          onMouseDown={(e) => {
                            e.stopPropagation()
                            setSelectedCamId(cam.id)
                            if (!isLocked) {
                              setDraggingCamId(cam.id)
                            }
                          }}
                        >
                          <title>{isLocked ? `${cam.name} (Locked)` : `${cam.name} (Click to select · Drag to move)`}</title>
                        </circle>

                        {/* Center Pip */}
                        <circle r="3" fill={isSelected ? '#000000' : '#00ffff'} pointerEvents="none" />

                        {/* Live Real Camera Hardware Indicator */}
                        {cam.is_real && (
                          <g transform="translate(0, -15)" pointerEvents="none">
                            <rect
                              x="-20"
                              y="-6"
                              width="40"
                              height="12"
                              rx="3"
                              fill="#6b0515"
                              stroke="#ff1744"
                              strokeWidth="1"
                              opacity="0.95"
                            />
                            <text
                              x="0"
                              y="3"
                              fill="#ffffff"
                              fontSize="7.5"
                              fontFamily="monospace"
                              fontWeight="bold"
                              textAnchor="middle"
                            >
                              🔴 LIVE
                            </text>
                          </g>
                        )}

                        {/* Label Badge Pill */}
                        <g transform="translate(0, 16)" pointerEvents="none">
                          <rect
                            x="-28"
                            y="-7"
                            width="56"
                            height="15"
                            rx="3"
                            fill="#030814"
                            stroke={isSelected ? '#00ffff' : isPrimed ? '#ffaa00' : '#1c4266'}
                            strokeWidth="1"
                            opacity="0.95"
                          />
                          <text
                            x="0"
                            y="4"
                            fill={isSelected ? '#00ffff' : isPrimed ? '#ffaa00' : '#9cd0f5'}
                            fontSize="9"
                            fontFamily="monospace"
                            fontWeight="bold"
                            textAnchor="middle"
                          >
                            {cam.name.split(':')[0]}
                          </text>
                        </g>
                      </g>
                    </g>
                  )
                })}

                {/* ========================================================================= */}
                {/* LIVE SIMULATED PERSONNEL WALKING CAMPUS ROADWAYS                          */}
                {/* ========================================================================= */}
                {pedestrians.map((ped) => {
                  const isSelected = selectedEntity?.id === ped.id
                  const isTracked = ped.status === 'TRACKED'

                  return (
                    <g
                      key={ped.id}
                      transform={`translate(${ped.x}, ${ped.y})`}
                      className="cursor-pointer"
                      onClick={(e) => {
                        e.stopPropagation()
                        setSelectedEntity(ped)
                      }}
                    >
                      {/* Active Tracking Reticle */}
                      {isTracked && (
                        <circle
                          r="11"
                          fill="none"
                          stroke="#00e5ff"
                          strokeWidth="1.5"
                          strokeDasharray="4 2"
                          className="animate-spin"
                          style={{ animationDuration: '4s' }}
                        />
                      )}

                      {/* Personnel Dot */}
                      <circle
                        r="5"
                        fill={ped.role === 'staff' ? '#a855f7' : ped.role === 'security' ? '#00e676' : ped.role === 'visitor' ? '#ffaa00' : '#00b0ff'}
                        stroke="#ffffff"
                        strokeWidth="1.5"
                      />

                      {/* Heading Needle */}
                      <line
                        x1="0"
                        y1="0"
                        x2={10 * Math.sin((ped.headingDeg * Math.PI) / 180)}
                        y2={-10 * Math.cos((ped.headingDeg * Math.PI) / 180)}
                        stroke="#ffffff"
                        strokeWidth="1.5"
                      />

                      {/* Tag on Select */}
                      {isSelected && (
                        <g transform="translate(0, -15)">
                          <rect x="-28" y="-7" width="56" height="14" rx="2" fill="#000000" stroke="#00e5ff" strokeWidth="1.2" opacity="0.95" />
                          <text x="0" y="3.5" fill="#ffffff" fontSize="8" fontFamily="monospace" fontWeight="bold" textAnchor="middle">
                            {ped.id}
                          </text>
                        </g>
                      )}
                    </g>
                  )
                })}

                {/* Handover Circular Perimeter Circuit & Transition Laser */}
                {handover.active && activeHandoverSeq.length >= 2 && (
                  <g pointerEvents="none">
                    {/* Perimeter Ring connecting all cameras in circle */}
                    <polygon
                      points={activeHandoverSeq
                        .map(id => {
                          const c = cameraNodes.find(n => n.id === id)
                          return c ? `${c.x},${c.y}` : ''
                        })
                        .filter(Boolean)
                        .join(' ')}
                      fill="none"
                      stroke="#00e5ff"
                      strokeWidth="1.5"
                      strokeDasharray="6 4"
                      opacity="0.35"
                    />

                    {/* Active Transition Vector Beam from fromCam to toCam */}
                    {handover.stage === 'transition' && (
                      <line
                        x1={cameraNodes.find(c => c.id === handover.fromCamId)?.x ?? handover.x}
                        y1={cameraNodes.find(c => c.id === handover.fromCamId)?.y ?? handover.y}
                        x2={cameraNodes.find(c => c.id === handover.toCamId)?.x ?? handover.x}
                        y2={cameraNodes.find(c => c.id === handover.toCamId)?.y ?? handover.y}
                        stroke="#ffaa00"
                        strokeWidth="2.5"
                        strokeDasharray="6 3"
                        className="animate-pulse"
                      />
                    )}
                  </g>
                )}

                {/* Handover Moving Target Blip */}
                {handover.active && (
                  <g pointerEvents="none">
                    <circle cx={handover.x} cy={handover.y} r="14" fill="none" stroke="#ffaa00" strokeWidth="2.5" className="animate-ping" />
                    <circle cx={handover.x} cy={handover.y} r="7" fill="#ff1744" stroke="#ffffff" strokeWidth="2" />
                    <g transform={`translate(${handover.x}, ${handover.y - 20})`}>
                      <rect x="-38" y="-10" width="76" height="17" rx="3" fill="#000000" stroke="#ff1744" strokeWidth="1.5" opacity="0.95" />
                      <text x="0" y="2" fill="#ffffff" fontSize="8.5" fontFamily="monospace" textAnchor="middle" fontWeight="bold">
                        T-112 (RE-ID)
                      </text>
                    </g>
                  </g>
                )}
              </g>
            </svg>
          ) : (
            /* ========================================================================= */
            /* MODE 3: LIVE GOOGLE MAPS SATELLITE (INTERACTIVE LEAFLET WITH ROTATION)    */
            /* ========================================================================= */
            <div className="relative w-full h-full min-h-[500px] rounded overflow-hidden border border-ops-border bg-black">
              {/* Top Controls Overlay: Search Bar & Rotation Controls */}
              <div className="absolute top-3 left-4 right-4 z-[1000] flex flex-wrap items-center justify-between gap-2 pointer-events-none">
                {/* Search Bar */}
                <div className="flex items-center gap-2 pointer-events-auto">
                  <form onSubmit={handleSearchLocation} className="flex items-center gap-1.5 bg-black/85 backdrop-blur-md p-1 rounded border border-ops-border shadow-xl">
                    <span className="pl-2 text-cyan-400 font-mono text-xs">🔍</span>
                    <input
                      type="text"
                      placeholder="Search College / City (e.g. Stanford, MIT, Delhi)..."
                      value={searchLocationQuery}
                      onChange={(e) => setSearchLocationQuery(e.target.value)}
                      className="bg-transparent text-white px-2 py-1 text-xs font-mono outline-none w-56 placeholder:text-slate-500"
                    />
                    <button
                      type="submit"
                      className="px-2.5 py-1 bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 rounded text-xs font-mono font-bold cursor-pointer"
                    >
                      Go
                    </button>
                  </form>

                  <button
                    onClick={() => setViewMode('college_satellite')}
                    className="px-3 py-1.5 bg-emerald-500/25 hover:bg-emerald-500/40 text-emerald-300 border border-emerald-500/50 rounded font-mono text-xs font-bold shadow-lg cursor-pointer"
                  >
                    ↩ Return to College View
                  </button>
                </div>

                {/* Tactical Rotation Controls Bar */}
                <div className="flex items-center gap-1.5 bg-black/85 backdrop-blur-md p-1 px-2 rounded-lg border border-cyan-500/40 shadow-xl font-mono text-xs text-slate-200 pointer-events-auto">
                  {/* Compass Indicator & Reset to North */}
                  <button
                    onClick={() => setMapRotation(0)}
                    className={`flex items-center gap-1.5 px-2 py-1 rounded border font-bold transition-all cursor-pointer ${
                      mapRotation === 0
                        ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50'
                        : 'bg-amber-500/20 text-amber-300 border-amber-500/50 animate-pulse'
                    }`}
                    title="Click to Reset Bearing to True North (0°)"
                  >
                    <Compass
                      className="w-4 h-4 transition-transform duration-300"
                      style={{ transform: `rotate(${-mapRotation}deg)` }}
                    />
                    <span>{String((mapRotation % 360 + 360) % 360).padStart(3, '0')}°</span>
                    <span className="text-[10px] text-slate-400">
                      {mapRotation === 0 ? 'N' :
                       mapRotation === 90 ? 'E' :
                       mapRotation === 180 ? 'S' :
                       mapRotation === 270 ? 'W' : ''}
                    </span>
                  </button>

                  {/* Rotate Left -15° */}
                  <button
                    onClick={() => setMapRotation(r => (r - 15 + 360) % 360)}
                    className="p-1 rounded bg-ops-surface hover:bg-cyan-500/20 text-slate-300 hover:text-cyan-200 border border-ops-border transition-colors cursor-pointer"
                    title="Rotate Map Left (-15°)"
                  >
                    <RotateCcw className="w-3.5 h-3.5" />
                  </button>

                  {/* Rotate Right +15° */}
                  <button
                    onClick={() => setMapRotation(r => (r + 15) % 360)}
                    className="p-1 rounded bg-ops-surface hover:bg-cyan-500/20 text-slate-300 hover:text-cyan-200 border border-ops-border transition-colors cursor-pointer"
                    title="Rotate Map Right (+15°)"
                  >
                    <RotateCw className="w-3.5 h-3.5" />
                  </button>

                  {/* Quick Cardinal Angles: N, E, S, W */}
                  <div className="flex items-center gap-0.5 border-l border-ops-border/80 pl-1">
                    {[
                      { label: 'N', deg: 0 },
                      { label: 'E', deg: 90 },
                      { label: 'S', deg: 180 },
                      { label: 'W', deg: 270 }
                    ].map(card => (
                      <button
                        key={card.label}
                        onClick={() => setMapRotation(card.deg)}
                        className={`w-5 h-6 rounded text-[10px] font-bold transition-all cursor-pointer ${
                          ((mapRotation % 360 + 360) % 360) === card.deg
                            ? 'bg-cyan-500 text-black font-extrabold'
                            : 'text-slate-400 hover:text-white hover:bg-white/10'
                        }`}
                      >
                        {card.label}
                      </button>
                    ))}
                  </div>

                  {/* Slider for precision angle */}
                  <div className="flex items-center gap-1 border-l border-ops-border/80 pl-2">
                    <input
                      type="range"
                      min="0"
                      max="360"
                      step="5"
                      value={(mapRotation % 360 + 360) % 360}
                      onChange={(e) => setMapRotation(Number(e.target.value))}
                      className="w-16 accent-cyan-400 cursor-pointer h-1"
                      title="Adjust custom angle"
                    />
                  </div>
                </div>
              </div>

              {/* Rotatable Map Viewport */}
              <div
                className="w-full h-full transition-transform duration-300 ease-out origin-center"
                style={{
                  transform: `rotate(${mapRotation}deg) scale(${mapRotation !== 0 ? 1.35 : 1.0})`
                }}
              >
                <div ref={leafletContainerRef} className="w-full h-full" />
              </div>
            </div>
          )}

          {/* Bottom Controls Status Help Bar */}
          <div className="absolute bottom-3 left-4 bg-black/80 px-3 py-1.5 rounded border border-ops-border text-[10px] font-mono text-slate-400 flex items-center gap-3 shadow-md">
            {viewMode === 'gods_eye_live' ? (
              <span className="text-cyan-300 font-bold">
                👁️ God's Eye View Active
              </span>
            ) : (
              <>
                <span className={isLocked ? 'text-red-400 font-bold' : 'text-emerald-400 font-bold'}>
                  {isLocked ? '🔒 Locked' : '🟢 Drag Map to Pan · Drag Nodes or Orange Dial to Move/Aim'}
                </span>
                <span className="text-slate-600">|</span>
                <span>🔍 Scroll to Zoom · Click camera cone to view live feed</span>
              </>
            )}
          </div>
        </div>

        {/* Right Sidebar: Live Video Stream & Selected Camera Telemetry */}
        <div className="col-span-3 p-3 border-l border-ops-border bg-[#070b14]/95 flex flex-col justify-between text-xs space-y-3">
          
          <div className="space-y-3">
            {/* Camera Feed Card */}
            <div className="rounded border border-ops-border bg-black/50 overflow-hidden">
              
              {/* Header */}
              <div className="p-2 bg-ops-panel flex justify-between items-center border-b border-ops-border font-mono text-xs">
                <span className="font-bold text-white flex items-center gap-1.5 truncate">
                  <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
                  <span>{activeCamPreview?.name || 'SELECT CAMERA'}</span>
                </span>
                <span className="px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 text-[10px] font-bold border border-emerald-500/30">
                  {activeCamPreview?.status || 'LIVE'}
                </span>
              </div>

              {/* Video Stream Player or Simulated Canvas Feed */}
              <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden">
                {activeCamPreview ? (
                  <TacticalLiveStreamFeed
                    camera={activeCamPreview}
                    handover={handover}
                    selectedEntity={selectedEntity}
                    isSimRunning={isSimRunning}
                  />
                ) : (
                  <div className="text-slate-500 font-mono text-xs">No Camera Feed Selected</div>
                )}
              </div>

              {/* Bottom camera info bar */}
              <div className="p-2 bg-ops-panel/95 border-t border-ops-border flex justify-between items-center text-[11px] font-mono">
                <span className="text-slate-300 truncate">{activeCamPreview?.location || 'Sector'}</span>
                <button
                  onClick={() => activeCamPreview && onSelectCamera?.(activeCamPreview.camera_id)}
                  className="text-ops-accent hover:text-white underline text-[10px]"
                >
                  Full View ↗
                </button>
              </div>
            </div>

            {/* Selected Subject Telemetry Card */}
            {selectedEntity && (
              <div className="p-2.5 rounded bg-black/50 border border-cyan-500/40 space-y-1 font-mono text-[11px]">
                <div className="flex justify-between items-center">
                  <span className="text-white font-bold">{selectedEntity.id}</span>
                  <span className="text-cyan-300 text-[10px] uppercase font-bold">{selectedEntity.role}</span>
                </div>
                <div className="text-slate-200 text-[11px] font-semibold">{selectedEntity.name}</div>
                <div className="text-slate-400 text-[10px]">Sector: {selectedEntity.sector}</div>
                <div className="text-slate-400 text-[10px]">Velocity: {selectedEntity.speed}</div>
                <div className={selectedEntity.trackingCamName ? 'text-emerald-400 text-[10px] font-bold' : 'text-amber-400 text-[10px] font-bold'}>
                  Status: {selectedEntity.trackingCamName ? `Tracked by ${selectedEntity.trackingCamName}` : 'In Blind Spot'}
                </div>
              </div>
            )}

            {/* Tactical Quick Actions */}
            <div className="space-y-1.5 pt-1 border-t border-ops-border">
              <div className="text-[10px] font-mono uppercase tracking-wider text-ops-accent font-bold">
                TACTICAL COMMAND DISPATCH
              </div>
              <div className="grid grid-cols-1 gap-1 font-mono text-xs">
                <button
                  onClick={() => triggerAction('Campus Ground Patrol Dispatched')}
                  className="py-1.5 px-2 rounded bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/40 text-left flex justify-between items-center"
                >
                  <span>🚨 Dispatch Ground Patrol</span>
                  <span>→</span>
                </button>
                <button
                  onClick={() => triggerAction('Campus PA System Broadcast')}
                  className="py-1.5 px-2 rounded bg-cyan-500/15 hover:bg-cyan-500/25 text-cyan-300 border border-cyan-500/30 text-left flex justify-between items-center"
                >
                  <span>📢 Campus PA Broadcast</span>
                  <span>→</span>
                </button>
                <button
                  onClick={() => triggerAction('Perimeter Gates Lockdown')}
                  className="py-1.5 px-2 rounded bg-amber-500/15 hover:bg-amber-500/25 text-amber-300 border border-amber-500/30 text-left flex justify-between items-center"
                >
                  <span>🔒 Perimeter Gate Lockdown</span>
                  <span>→</span>
                </button>
              </div>
            </div>
          </div>

          {/* Telemetry Footer */}
          <div className="p-2 rounded bg-black/50 border border-ops-border text-[10px] font-mono text-slate-400 space-y-0.5">
            <div className="text-slate-300 font-semibold flex justify-between">
              <span>TACTICAL RADAR VIEW:</span>
              <span className="text-emerald-400 font-bold">ACTIVE</span>
            </div>
            <div>Mode: {viewMode === 'college_satellite' ? 'College Satellite Imagery' : viewMode === 'google_maps' ? 'Live Google Maps' : 'Tactical Blueprint'}</div>
            <div>Sensors: {cameraNodes.length} Active Nodes</div>
          </div>
        </div>
      </div>

      {/* ========================================================================= */}
      {/* HANDOVER SET CAMERAS & MULTI-SYSTEM AUTO-MAPPING MODAL                    */}
      {/* ========================================================================= */}
      {showHandoverModal && (
        <div className="fixed inset-0 z-[9999] bg-black/80 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="tactical-panel bg-[#0b111e] border border-ops-border rounded-xl shadow-2xl w-full max-w-2xl max-h-[88vh] flex flex-col overflow-hidden text-ops-text">
            {/* Modal Header */}
            <div className="p-4 border-b border-ops-border flex items-center justify-between bg-ops-panel">
              <div className="flex items-center gap-2.5">
                <div className="p-2 rounded-lg bg-ops-accent/15 text-ops-accent border border-ops-accent/30">
                  <Compass className="w-5 h-5" />
                </div>
                <div>
                  <h3 className="font-bold text-sm font-display text-white flex items-center gap-2">
                    <span>Perimeter Handover Route & Sensor Circuit</span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-cyan-500/20 text-cyan-300 border border-cyan-500/40 font-bold">
                      {activeHandoverSeq.length} Nodes in Closed Ring
                    </span>
                  </h3>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Configure camera sequence for continuous circular tracking. When multiple systems/cameras are connected, click Auto-Map to arrange them into a perimeter circle.
                  </p>
                </div>
              </div>
              <button
                onClick={() => setShowHandoverModal(false)}
                className="p-1 rounded-lg text-slate-400 hover:text-white hover:bg-white/10 transition-colors"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            {/* Modal Controls & Quick Actions */}
            <div className="p-3.5 bg-ops-surface border-b border-ops-border flex flex-wrap items-center justify-between gap-3">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => {
                    const mapped = autoMapPerimeterCircle(cameraNodes)
                    setHandoverSequence(mapped)
                    try { localStorage.setItem('garuda_handover_sequence', JSON.stringify(mapped)) } catch {}
                    setTacticalActionMsg(`⚡ Auto-Mapped ${mapped.length} Connected Systems into Perimeter Circle`)
                    setTimeout(() => setTacticalActionMsg(null), 3500)
                  }}
                  className="px-3 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 font-mono text-xs font-bold flex items-center gap-1.5 transition-all shadow-sm active:scale-95"
                  title="Automatically compute centroid and arrange all connected cameras into a continuous circular perimeter"
                >
                  <Wand2 className="w-3.5 h-3.5" />
                  <span>Auto-Map Connected Systems (Perimeter Circle)</span>
                </button>

                <button
                  onClick={() => {
                    const mapped = autoMapPerimeterCircle(COLLEGE_CAMPUS_PRESETS)
                    setHandoverSequence(mapped)
                    try { localStorage.setItem('garuda_handover_sequence', JSON.stringify(mapped)) } catch {}
                    setTacticalActionMsg('↺ Handover sequence reset to optimal campus ring')
                    setTimeout(() => setTacticalActionMsg(null), 3000)
                  }}
                  className="px-2.5 py-1.5 rounded-lg bg-ops-card hover:bg-ops-surface text-slate-400 hover:text-slate-200 border border-ops-border font-mono text-xs flex items-center gap-1 transition-all"
                >
                  <RotateCw className="w-3.5 h-3.5" />
                  <span>Reset Circle</span>
                </button>
              </div>

              <div className="text-[11px] font-mono text-slate-400">
                Connected Systems: <span className="text-emerald-400 font-bold">{cameraNodes.length} Online</span>
              </div>
            </div>

            {/* Sequence List Area */}
            <div className="p-4 overflow-y-auto flex-1 space-y-2 max-h-[48vh]">
              <div className="text-xs font-mono text-slate-400 uppercase tracking-wider mb-1 flex items-center justify-between">
                <span>Active Circuit Sequence (Forms Closed Ring):</span>
                <span className="text-[10px] text-cyan-400 font-semibold">
                  Node #{activeHandoverSeq.length} loops back to Node #1
                </span>
              </div>

              {activeHandoverSeq.map((camId, idx) => {
                const cam = cameraNodes.find(c => c.id === camId)
                const nextIdx = (idx + 1) % activeHandoverSeq.length
                const nextCam = cameraNodes.find(c => c.id === activeHandoverSeq[nextIdx])
                const isSelected = activeSelectedCamNode?.id === camId

                return (
                  <div
                    key={camId}
                    className={`p-2.5 rounded-lg border flex items-center justify-between gap-3 font-mono transition-all ${
                      isSelected ? 'bg-cyan-950/30 border-cyan-500/50' : 'bg-black/30 border-ops-border hover:border-slate-600'
                    }`}
                  >
                    <div className="flex items-center gap-3 min-w-0">
                      <span className="w-6 h-6 rounded-full bg-ops-accent/20 text-ops-accent border border-ops-accent/40 flex items-center justify-center text-xs font-bold shrink-0">
                        {idx + 1}
                      </span>
                      <div className="truncate">
                        <div className="text-xs font-bold text-slate-200 flex items-center gap-2 truncate">
                          <span>{cam?.name || camId}</span>
                          {idx === 0 && (
                            <span className="text-[9px] px-1.5 py-0.2 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shrink-0">
                              Ring Origin
                            </span>
                          )}
                        </div>
                        <div className="text-[10px] text-slate-400 flex items-center gap-2 truncate mt-0.5">
                          <span>{cam?.location || 'Campus Perimeter'}</span>
                          <span>•</span>
                          <span>Coord: ({cam?.x}, {cam?.y})</span>
                          <span>•</span>
                          <span className="text-cyan-400 truncate">➔ Next: #{nextIdx + 1} ({nextCam?.name.split(':')[0] || 'Loop'})</span>
                        </div>
                      </div>
                    </div>

                    <div className="flex items-center gap-1 shrink-0">
                      <button
                        disabled={idx === 0}
                        onClick={() => {
                          const newSeq = [...activeHandoverSeq]
                          const temp = newSeq[idx]
                          newSeq[idx] = newSeq[idx - 1]
                          newSeq[idx - 1] = temp
                          setHandoverSequence(newSeq)
                          try { localStorage.setItem('garuda_handover_sequence', JSON.stringify(newSeq)) } catch {}
                        }}
                        className="p-1 rounded bg-ops-surface text-slate-300 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed border border-ops-border transition-colors"
                        title="Move Up in Loop"
                      >
                        <ArrowUp className="w-3.5 h-3.5" />
                      </button>
                      <button
                        disabled={idx === activeHandoverSeq.length - 1}
                        onClick={() => {
                          const newSeq = [...activeHandoverSeq]
                          const temp = newSeq[idx]
                          newSeq[idx] = newSeq[idx + 1]
                          newSeq[idx + 1] = temp
                          setHandoverSequence(newSeq)
                          try { localStorage.setItem('garuda_handover_sequence', JSON.stringify(newSeq)) } catch {}
                        }}
                        className="p-1 rounded bg-ops-surface text-slate-300 hover:text-white disabled:opacity-30 disabled:cursor-not-allowed border border-ops-border transition-colors"
                        title="Move Down in Loop"
                      >
                        <ArrowDown className="w-3.5 h-3.5" />
                      </button>
                      {activeHandoverSeq.length > 2 && (
                        <button
                          onClick={() => {
                            const newSeq = activeHandoverSeq.filter(id => id !== camId)
                            setHandoverSequence(newSeq)
                            try { localStorage.setItem('garuda_handover_sequence', JSON.stringify(newSeq)) } catch {}
                          }}
                          className="p-1 rounded bg-red-500/20 text-red-300 hover:bg-red-500/30 border border-red-500/40 transition-colors"
                          title="Remove from Loop"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </div>
                  </div>
                )
              })}

              {/* Unmapped Connected Cameras */}
              {cameraNodes.filter(c => !activeHandoverSeq.includes(c.id)).length > 0 && (
                <div className="pt-3 border-t border-ops-border">
                  <div className="text-[11px] font-mono text-slate-400 uppercase tracking-wider mb-2">
                    Available Connected Cameras ({cameraNodes.filter(c => !activeHandoverSeq.includes(c.id)).length}):
                  </div>
                  <div className="grid grid-cols-2 gap-2">
                    {cameraNodes
                      .filter(c => !activeHandoverSeq.includes(c.id))
                      .map(cam => (
                        <button
                          key={cam.id}
                          onClick={() => {
                            const newSeq = [...activeHandoverSeq, cam.id]
                            setHandoverSequence(newSeq)
                            try { localStorage.setItem('garuda_handover_sequence', JSON.stringify(newSeq)) } catch {}
                          }}
                          className="p-2 rounded bg-ops-card border border-ops-border hover:border-cyan-500/50 flex items-center justify-between text-left text-xs font-mono group transition-colors"
                        >
                          <div className="truncate">
                            <div className="text-slate-200 font-semibold truncate">{cam.name}</div>
                            <div className="text-[10px] text-slate-400 truncate">{cam.location}</div>
                          </div>
                          <span className="text-cyan-400 group-hover:scale-110 transition-transform ml-2 shrink-0">
                            <Plus className="w-4 h-4" />
                          </span>
                        </button>
                      ))}
                  </div>
                </div>
              )}
            </div>

            {/* Modal Footer */}
            <div className="p-4 border-t border-ops-border bg-ops-panel flex items-center justify-between">
              <div className="text-[11px] font-mono text-cyan-400 flex items-center gap-1.5">
                <span className="w-2 h-2 rounded-full bg-cyan-400 animate-ping" />
                <span>Continuous Ring: Leg #{activeHandoverSeq.length} connects back to #{1}</span>
              </div>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowHandoverModal(false)}
                  className="px-3 py-1.5 rounded-lg border border-ops-border bg-ops-surface text-slate-300 hover:text-white font-mono text-xs transition-colors"
                >
                  Close
                </button>
                <button
                  onClick={() => {
                    setShowHandoverModal(false)
                    startHandoverSimulation(0, true)
                  }}
                  className="px-3.5 py-1.5 rounded-lg bg-cyan-500 hover:bg-cyan-400 text-slate-950 font-mono text-xs font-bold flex items-center gap-1.5 shadow-lg shadow-cyan-500/20 transition-all active:scale-95"
                >
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>Run Circular Handover (Random Start)</span>
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
