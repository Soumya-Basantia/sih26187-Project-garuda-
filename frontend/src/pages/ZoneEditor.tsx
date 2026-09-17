import React, { useEffect, useRef, useState, useCallback } from 'react'
import { cameraApi, zoneApi, identityApi, Camera, Zone, Identity } from '../services/api'
import { Star } from 'lucide-react'

const ZONE_COLORS: Record<string, { stroke: string; fill: string; badgeBg: string; label: string }> = {
  high_security: { stroke: '#ef4444', fill: 'rgba(239, 68, 68, 0.25)', badgeBg: 'bg-red-500/15 text-red-500 border-red-500/30', label: 'High-Security (Zero Line)' },
  restricted: { stroke: '#f97316', fill: 'rgba(249, 115, 22, 0.22)', badgeBg: 'bg-orange-500/15 text-orange-500 border-orange-500/30', label: 'Restricted (Buffer Zone)' },
  monitored: { stroke: '#eab308', fill: 'rgba(234, 179, 8, 0.20)', badgeBg: 'bg-yellow-500/15 text-yellow-500 border-yellow-500/30', label: 'Monitored (Approach)' },
  general: { stroke: '#94a3b8', fill: 'rgba(148, 163, 184, 0.15)', badgeBg: 'bg-slate-500/15 text-slate-400 border-slate-500/30', label: 'General Patrol' },
  entry: { stroke: '#10b981', fill: 'rgba(16, 185, 129, 0.20)', badgeBg: 'bg-emerald-500/15 text-emerald-500 border-emerald-500/30', label: 'Entry Checkpost' },
  exit: { stroke: '#06b6d4', fill: 'rgba(6, 182, 212, 0.20)', badgeBg: 'bg-cyan-500/15 text-cyan-500 border-cyan-500/30', label: 'Exit Gate' },
  sensitive: { stroke: '#d946ef', fill: 'rgba(217, 70, 239, 0.22)', badgeBg: 'bg-fuchsia-500/15 text-fuchsia-500 border-fuchsia-500/30', label: 'Sensitive Facility' },
  vehicle_only: { stroke: '#38bdf8', fill: 'rgba(56, 189, 248, 0.20)', badgeBg: 'bg-sky-500/15 text-sky-500 border-sky-500/30', label: 'Vehicle Lane' },
}

export default function ZoneEditor() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [identities, setIdentities] = useState<Identity[]>([])
  const [selectedCamera, setSelectedCamera] = useState<string>('')
  const [zones, setZones] = useState<Zone[]>([])

  // Polygon state
  const [points, setPoints] = useState<[number, number][]>([])
  const [editingZoneId, setEditingZoneId] = useState<string | null>(null)
  const [draggedVertexIndex, setDraggedVertexIndex] = useState<number | null>(null)
  const [hoveredVertexIndex, setHoveredVertexIndex] = useState<number | null>(null)

  // Form states
  const [zoneName, setZoneName] = useState('')
  const [zoneType, setZoneType] = useState('high_security')
  const [threshold, setThreshold] = useState(5)
  const [openAccess, setOpenAccess] = useState(true)
  const [selectedIdentities, setSelectedIdentities] = useState<string[]>([])
  const [nightOnly, setNightOnly] = useState(false)

  // Military Star Authority Clearance states
  const [minRankStars, setMinRankStars] = useState<number>(0)
  const [allowEscort, setAllowEscort] = useState<boolean>(false)
  const [authorityCustomLevel, setAuthorityCustomLevel] = useState<string>('')

  // Visual/UI states
  const [snapshotTimestamp, setSnapshotTimestamp] = useState<number>(Date.now())
  const [hoveredZoneId, setHoveredZoneId] = useState<string | null>(null)
  const [saveSuccessMsg, setSaveSuccessMsg] = useState<string | null>(null)
  const [imgDims, setImgDims] = useState<{ width: number; height: number }>({ width: 640, height: 480 })
  const [imgLoaded, setImgLoaded] = useState(false)
  const [imgError, setImgError] = useState(false)
  const [feedMode, setFeedMode] = useState<'snapshot' | 'live'>('snapshot')

  const imgRef = useRef<HTMLImageElement>(null)
  const containerRef = useRef<HTMLDivElement>(null)
  const wasDraggingRef = useRef(false)

  useEffect(() => {
    cameraApi.list().then((r) => {
      setCameras(r.data)
      if (r.data.length > 0 && !selectedCamera) {
        setSelectedCamera(r.data[0].camera_id)
      }
    })
    identityApi.list().then((r) => setIdentities(r.data))
  }, [])

  useEffect(() => {
    if (selectedCamera) {
      zoneApi.list(selectedCamera).then((r) => setZones(r.data))
      handleCancelEdit()
      setImgError(false)
      setImgLoaded(false)
      setSnapshotTimestamp(Date.now())
    }
  }, [selectedCamera])

  // Coordinate conversion helper
  const getCoordsFromEvent = useCallback((e: MouseEvent | React.MouseEvent): [number, number] | null => {
    const el = containerRef.current
    if (!el) return null
    const rect = el.getBoundingClientRect()
    if (rect.width === 0 || rect.height === 0) return null

    const scaleX = imgDims.width / rect.width
    const scaleY = imgDims.height / rect.height
    const rawX = (e.clientX - rect.left) * scaleX
    const rawY = (e.clientY - rect.top) * scaleY
    const x = Math.max(0, Math.min(imgDims.width, Math.round(rawX)))
    const y = Math.max(0, Math.min(imgDims.height, Math.round(rawY)))
    return [x, y]
  }, [imgDims])

  // Dragging vertex listener attached to window so mouse doesn't get lost
  useEffect(() => {
    if (draggedVertexIndex === null) return

    function onMouseMove(e: MouseEvent) {
      wasDraggingRef.current = true
      const coords = getCoordsFromEvent(e)
      if (coords && draggedVertexIndex !== null) {
        setPoints((prev) => {
          const next = [...prev]
          next[draggedVertexIndex] = coords
          return next
        })
      }
    }

    function onMouseUp() {
      setDraggedVertexIndex(null)
      // Allow a brief moment before clicks register as new point
      setTimeout(() => {
        wasDraggingRef.current = false
      }, 50)
    }

    window.addEventListener('mousemove', onMouseMove)
    window.addEventListener('mouseup', onMouseUp)
    return () => {
      window.removeEventListener('mousemove', onMouseMove)
      window.removeEventListener('mouseup', onMouseUp)
    }
  }, [draggedVertexIndex, getCoordsFromEvent])

  function handleImageClick(e: React.MouseEvent) {
    // If we were dragging a vertex, do not append a new point
    if (wasDraggingRef.current || draggedVertexIndex !== null) return

    const coords = getCoordsFromEvent(e)
    if (!coords) return
    setPoints((prev) => [...prev, coords])
  }

  function handleVertexMouseDown(idx: number, e: React.MouseEvent) {
    e.stopPropagation()
    e.preventDefault()
    wasDraggingRef.current = true
    setDraggedVertexIndex(idx)
  }

  function handleVertexContextMenu(idx: number, e: React.MouseEvent) {
    e.stopPropagation()
    e.preventDefault()
    if (points.length <= 3) return // Keep at least 3 vertices
    setPoints((prev) => prev.filter((_, i) => i !== idx))
  }

  function handleInsertEdgePoint(edgeIndex: number, e: React.MouseEvent) {
    e.stopPropagation()
    const p1 = points[edgeIndex]
    const p2 = points[(edgeIndex + 1) % points.length]
    const midX = Math.round((p1[0] + p2[0]) / 2)
    const midY = Math.round((p1[1] + p2[1]) / 2)

    setPoints((prev) => {
      const next = [...prev]
      next.splice(edgeIndex + 1, 0, [midX, midY])
      return next
    })
  }

  function handleUndoPoint() {
    setPoints((prev) => prev.slice(0, -1))
  }

  function handleClearPoints() {
    setPoints([])
  }

  function handleCancelEdit() {
    setEditingZoneId(null)
    setPoints([])
    setZoneName('')
    setZoneType('high_security')
    setThreshold(5)
    setOpenAccess(true)
    setSelectedIdentities([])
    setNightOnly(false)
    setMinRankStars(0)
    setAllowEscort(false)
    setAuthorityCustomLevel('')
  }

  function handleStartEditZone(z: Zone) {
    setEditingZoneId(z.zone_id)
    setPoints(z.polygon.map((p) => [p[0], p[1]] as [number, number]))
    setZoneName(z.name)
    setZoneType(z.zone_type)
    setThreshold(z.threshold_seconds)
    setNightOnly(!!z.active_hours)
    setMinRankStars(z.min_rank_stars ?? 0)
    setAllowEscort(z.allow_escort ?? false)
    setAuthorityCustomLevel(z.authority_custom_level ?? '')
    const hasWhitelist = z.authorized_identity_ids && z.authorized_identity_ids.length > 0
    setOpenAccess(!hasWhitelist)
    setSelectedIdentities(z.authorized_identity_ids || [])
  }

  function applyPreset(presetType: 'full' | 'left' | 'right' | 'center' | 'bottom') {
    const w = imgDims.width
    const h = imgDims.height
    if (presetType === 'full') {
      setPoints([[10, 10], [w - 10, 10], [w - 10, h - 10], [10, h - 10]])
    } else if (presetType === 'left') {
      setPoints([[10, 10], [Math.round(w / 2), 10], [Math.round(w / 2), h - 10], [10, h - 10]])
    } else if (presetType === 'right') {
      setPoints([[Math.round(w / 2), 10], [w - 10, 10], [w - 10, h - 10], [Math.round(w / 2), h - 10]])
    } else if (presetType === 'center') {
      const padX = Math.round(w * 0.25)
      const padY = Math.round(h * 0.20)
      setPoints([[padX, padY], [w - padX, padY], [w - padX, h - padY], [padX, h - padY]])
    } else if (presetType === 'bottom') {
      setPoints([[10, Math.round(h * 0.55)], [w - 10, Math.round(h * 0.55)], [w - 10, h - 10], [10, h - 10]])
    }
  }

  async function handleSaveZone() {
    if (points.length < 3 || !selectedCamera || !zoneName.trim()) return

    const payload = {
      camera_id: selectedCamera,
      name: zoneName.trim(),
      zone_type: zoneType,
      polygon: points,
      threshold_seconds: threshold,
      active_hours: nightOnly ? ([22, 6] as [number, number]) : undefined,
      authorized_identity_ids: openAccess ? [] : selectedIdentities,
      min_rank_stars: minRankStars,
      allow_escort: allowEscort,
      authority_custom_level: authorityCustomLevel.trim() || undefined,
      enabled: true,
    }

    if (editingZoneId) {
      await zoneApi.update(editingZoneId, payload)
      setSaveSuccessMsg(`Zone '${zoneName}' updated successfully!`)
    } else {
      await zoneApi.create(payload)
      setSaveSuccessMsg(`Zone '${zoneName}' created successfully!`)
    }

    setTimeout(() => setSaveSuccessMsg(null), 3500)
    handleCancelEdit()
    zoneApi.list(selectedCamera).then((r) => setZones(r.data))
  }

  async function handleDeleteZone(id: string) {
    await zoneApi.remove(id)
    if (editingZoneId === id) {
      handleCancelEdit()
    }
    zoneApi.list(selectedCamera).then((r) => setZones(r.data))
  }

  const naturalW = imgDims.width
  const naturalH = imgDims.height
  const activeStyle = ZONE_COLORS[zoneType] || ZONE_COLORS.high_security

  return (
    <div className="p-6 grid grid-cols-1 lg:grid-cols-3 gap-6 max-w-7xl mx-auto">
      {/* Left 2 Cols: Interactive Canvas */}
      <div className="lg:col-span-2 space-y-4">
        <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl">
          <div className="flex items-center justify-between mb-3">
            <div>
              <div className="text-sm font-bold tracking-wide text-cyan-400 uppercase flex items-center gap-2">
                <span>🛡️ Virtual Security Zones</span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                  {editingZoneId ? '✏️ EDITING MODE' : 'POLYGON ENGINE'}
                </span>
              </div>
              <p className="text-xs text-slate-400 mt-0.5">
                {editingZoneId
                  ? 'Drag the circular handles to move edges/corners. Click the "+" icons on lines to add corners. Right-click a handle to delete it.'
                  : 'Click on the camera frame to place points, or drag existing corners to adjust. Select any saved zone to edit its shape.'}
              </p>
            </div>
          </div>

          {/* Camera Feed & Stream Mode Bar */}
          <div className="flex flex-wrap items-center gap-2 mb-3">
            <select
              value={selectedCamera}
              onChange={(e) => setSelectedCamera(e.target.value)}
              className="flex-1 min-w-[200px] bg-ops-card border border-ops-border rounded-lg px-3 py-2 text-sm text-ops-text focus:outline-none focus:border-cyan-500 font-sans"
            >
              <option value="">Select camera feed...</option>
              {cameras.map((c) => (
                <option key={c.camera_id} value={c.camera_id}>
                  {c.name} ({c.camera_id})
                </option>
              ))}
            </select>

            <div className="flex items-center bg-slate-800/80 p-0.5 rounded-lg border border-slate-700/60 text-xs">
              <button
                type="button"
                onClick={() => {
                  setFeedMode('snapshot')
                  setImgError(false)
                  setSnapshotTimestamp(Date.now())
                }}
                className={`px-2.5 py-1.5 rounded-md transition flex items-center gap-1 font-medium ${
                  feedMode === 'snapshot'
                    ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>📸</span> Snapshot
              </button>
              <button
                type="button"
                onClick={() => {
                  setFeedMode('live')
                  setImgError(false)
                }}
                className={`px-2.5 py-1.5 rounded-md transition flex items-center gap-1 font-medium ${
                  feedMode === 'live'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30 shadow-sm'
                    : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <span>🔴</span> Live Video
              </button>
            </div>

            {feedMode === 'snapshot' && (
              <button
                type="button"
                onClick={() => {
                  setImgError(false)
                  setSnapshotTimestamp(Date.now())
                }}
                className="px-2.5 py-1.5 text-xs rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 flex items-center gap-1.5 transition"
                title="Capture fresh frame from stream"
              >
                <span>🔄</span> Refresh
              </button>
            )}

            {editingZoneId && (
              <button
                type="button"
                onClick={handleCancelEdit}
                className="px-3 py-1.5 text-xs rounded-lg bg-slate-800 hover:bg-slate-700 text-amber-400 border border-amber-500/30 flex items-center gap-1.5"
              >
                ✕ Cancel Editing
              </button>
            )}
          </div>

          {/* Success Banner */}
          {saveSuccessMsg && (
            <div className="mb-3 px-3 py-2 rounded-lg bg-emerald-500/20 border border-emerald-500/40 text-emerald-300 text-xs flex items-center gap-2">
              <span>✓</span>
              <span>{saveSuccessMsg}</span>
            </div>
          )}

          {/* Camera Frame with Interactive SVG Overlay */}
          {selectedCamera && (
            <div
              ref={containerRef}
              onClick={handleImageClick}
              className={`relative overflow-hidden rounded-xl border border-slate-800 bg-slate-950 aspect-video w-full flex items-center justify-center select-none shadow-2xl ${
                draggedVertexIndex !== null ? 'cursor-grabbing' : 'cursor-crosshair'
              }`}
            >
              {/* Subtle tactical grid background */}
              <div
                className="absolute inset-0 pointer-events-none opacity-20"
                style={{
                  backgroundImage: 'radial-gradient(circle at 1px 1px, #38bdf8 1px, transparent 0)',
                  backgroundSize: '24px 24px',
                }}
              />

              {/* Camera Frame Image */}
              <img
                ref={imgRef}
                key={`${selectedCamera}-${feedMode}-${snapshotTimestamp}`}
                src={
                  feedMode === 'live'
                    ? cameraApi.streamUrl(selectedCamera)
                    : cameraApi.snapshotUrl(selectedCamera, snapshotTimestamp)
                }
                onLoad={(e) => {
                  const target = e.currentTarget
                  setImgError(false)
                  setImgLoaded(true)
                  if (target.naturalWidth > 0 && target.naturalHeight > 0) {
                    setImgDims({ width: target.naturalWidth, height: target.naturalHeight })
                  }
                }}
                onError={() => {
                  setImgError(true)
                  setImgLoaded(false)
                }}
                className={`w-full h-full object-contain pointer-events-none select-none transition-opacity duration-300 ${
                  imgError ? 'opacity-0 hidden' : 'opacity-100'
                }`}
                alt="Camera surveillance frame"
                draggable={false}
              />

              {/* Offline / Calibration Mode Overlay (Prevents collapsed UI) */}
              {imgError && (
                <div className="absolute inset-0 flex flex-col items-center justify-center p-6 text-center bg-slate-950/95 pointer-events-none select-none">
                  <div className="w-12 h-12 rounded-xl bg-cyan-500/10 border border-cyan-500/20 flex items-center justify-center text-cyan-400 mb-2 shadow-inner">
                    <span className="text-xl">🛡️</span>
                  </div>
                  <h4 className="text-xs font-semibold text-slate-200">
                    Camera Feed Standby / Calibration Grid
                  </h4>
                  <p className="text-[11px] text-slate-400 max-w-sm mt-1">
                    Camera hardware is offline or stream is initializing ({imgDims.width}×{imgDims.height}px). You can click or drag to draw and calibrate zones right now.
                  </p>
                  <div className="mt-3 flex items-center gap-2 pointer-events-auto">
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setImgError(false)
                        setSnapshotTimestamp(Date.now())
                      }}
                      className="px-2.5 py-1 text-xs rounded bg-cyan-600 hover:bg-cyan-500 text-white font-medium shadow transition"
                    >
                      Retry Frame
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation()
                        setImgError(false)
                        setFeedMode(feedMode === 'live' ? 'snapshot' : 'live')
                      }}
                      className="px-2.5 py-1 text-xs rounded bg-slate-800 hover:bg-slate-700 text-slate-300 border border-slate-700 transition"
                    >
                      Switch to {feedMode === 'live' ? 'Snapshot' : 'Live Video'}
                    </button>
                  </div>
                </div>
              )}

              {/* Status Pill on Top-Left of Frame */}
              <div className="absolute top-2.5 left-2.5 z-10 pointer-events-none flex items-center gap-2 bg-slate-950/80 backdrop-blur border border-slate-700/60 rounded-md px-2.5 py-1 text-[11px] font-mono">
                <span className={`w-2 h-2 rounded-full ${imgError ? 'bg-amber-400' : 'bg-emerald-400 animate-pulse'}`} />
                <span className="text-slate-200 font-semibold">{selectedCamera}</span>
                <span className="text-slate-500">|</span>
                <span className="text-cyan-400">{feedMode.toUpperCase()}</span>
                <span className="text-slate-500 text-[10px]">({imgDims.width}×{imgDims.height})</span>
              </div>

              <svg
                className="absolute inset-0 w-full h-full"
                viewBox={`0 0 ${naturalW} ${naturalH}`}
                preserveAspectRatio="none"
                style={{ pointerEvents: 'none' }}
              >
                {/* 1. Existing Saved Zones (Exclude currently edited one) */}
                {zones
                  .filter((z) => z.zone_id !== editingZoneId)
                  .map((z) => {
                    const style = ZONE_COLORS[z.zone_type] || ZONE_COLORS.general
                    const isHovered = hoveredZoneId === z.zone_id
                    const ptsStr = z.polygon.map((p) => `${p[0]},${p[1]}`).join(' ')
                    const topPt = z.polygon.reduce((min, p) => (p[1] < min[1] ? p : min), z.polygon[0])

                    const minStars = z.min_rank_stars || 0
                    const starBadge = minStars > 0 ? '⭐'.repeat(minStars) + ' ' : ''
                    const displayText = `${starBadge}${z.name}`

                    return (
                      <g key={z.zone_id} className="cursor-pointer" style={{ pointerEvents: 'auto' }}>
                        <polygon
                          points={ptsStr}
                          fill={isHovered ? 'rgba(34, 211, 238, 0.35)' : style.fill}
                          stroke={isHovered ? '#22d3ee' : style.stroke}
                          strokeWidth={isHovered ? 3 : 2}
                          strokeDasharray={z.zone_type === 'high_security' ? '4 2' : 'none'}
                          onClick={() => handleStartEditZone(z)}
                          onMouseEnter={() => setHoveredZoneId(z.zone_id)}
                          onMouseLeave={() => setHoveredZoneId(null)}
                        />
                        {topPt && (
                          <g onClick={() => handleStartEditZone(z)}>
                            <rect
                              x={topPt[0] + 4}
                              y={Math.max(4, topPt[1] - 22)}
                              width={Math.max(70, displayText.length * 7.5 + 16)}
                              height={18}
                              rx={4}
                              fill="rgba(0,0,0,0.85)"
                              stroke={minStars > 0 ? '#f59e0b' : style.stroke}
                              strokeWidth={1}
                            />
                            <text
                              x={topPt[0] + 10}
                              y={Math.max(16, topPt[1] - 9)}
                              fill={minStars > 0 ? '#fde68a' : style.stroke}
                              fontSize={11}
                              fontWeight="bold"
                              fontFamily="monospace"
                            >
                              {displayText}
                            </text>
                          </g>
                        )}
                      </g>
                    )
                  })}

                {/* 2. Active Polygon (Being Drawn or Edited) */}
                {points.length >= 2 && (
                  <polygon
                    points={points.map((p) => `${p[0]},${p[1]}`).join(' ')}
                    fill={activeStyle.fill}
                    stroke={activeStyle.stroke}
                    strokeWidth={2.5}
                    strokeDasharray={editingZoneId ? 'none' : '4 2'}
                  />
                )}

                {/* Edge Midpoint Insert Buttons ("+" handles to subdivide lines) */}
                {points.length >= 3 &&
                  points.map((p1, idx) => {
                    const p2 = points[(idx + 1) % points.length]
                    const midX = (p1[0] + p2[0]) / 2
                    const midY = (p1[1] + p2[1]) / 2

                    return (
                      <g
                        key={`edge-${idx}`}
                        className="cursor-pointer group"
                        style={{ pointerEvents: 'auto' }}
                        onClick={(e) => handleInsertEdgePoint(idx, e)}
                      >
                        <circle
                          cx={midX}
                          cy={midY}
                          r={6}
                          fill="rgba(15, 23, 42, 0.85)"
                          stroke={activeStyle.stroke}
                          strokeWidth={1.5}
                          className="transition-transform hover:scale-125"
                        />
                        <text
                          x={midX}
                          y={midY + 3.5}
                          textAnchor="middle"
                          fill="#ffffff"
                          fontSize={10}
                          fontWeight="bold"
                          className="select-none"
                        >
                          +
                        </text>
                      </g>
                    )
                  })}

                {/* 3. Draggable Vertices */}
                {points.map((p, idx) => {
                  const isHovered = hoveredVertexIndex === idx
                  const isBeingDragged = draggedVertexIndex === idx

                  return (
                    <g
                      key={`vertex-${idx}`}
                      style={{ pointerEvents: 'auto' }}
                      onMouseDown={(e) => handleVertexMouseDown(idx, e)}
                      onContextMenu={(e) => handleVertexContextMenu(idx, e)}
                      onMouseEnter={() => setHoveredVertexIndex(idx)}
                      onMouseLeave={() => setHoveredVertexIndex(null)}
                      className="cursor-grab active:cursor-grabbing"
                    >
                      {/* Halo ring when hovered/dragged */}
                      <circle
                        cx={p[0]}
                        cy={p[1]}
                        r={isBeingDragged ? 14 : isHovered ? 12 : 9}
                        fill={isBeingDragged ? 'rgba(34, 211, 238, 0.6)' : isHovered ? 'rgba(34, 211, 238, 0.35)' : 'rgba(15, 23, 42, 0.7)'}
                        stroke={activeStyle.stroke}
                        strokeWidth={2}
                      />
                      {/* Center handle */}
                      <circle cx={p[0]} cy={p[1]} r={3.5} fill="#ffffff" />

                      {/* Vertex Index & Coordinate Pill */}
                      <g pointerEvents="none">
                        <rect
                          x={p[0] + 10}
                          y={p[1] - 16}
                          width={isHovered || isBeingDragged ? 76 : 22}
                          height={16}
                          rx={3}
                          fill="rgba(0,0,0,0.85)"
                          stroke={isBeingDragged ? '#22d3ee' : activeStyle.stroke}
                          strokeWidth={1}
                        />
                        <text
                          x={p[0] + 13}
                          y={p[1] - 4}
                          fill={isBeingDragged ? '#22d3ee' : '#ffffff'}
                          fontSize={10}
                          fontWeight="bold"
                          fontFamily="monospace"
                        >
                          {isHovered || isBeingDragged ? `#${idx + 1} (${p[0]},${p[1]})` : `${idx + 1}`}
                        </text>
                      </g>
                    </g>
                  )
                })}
              </svg>
            </div>
          )}

          {/* Point Counter & Interactive Controls */}
          <div className="flex flex-wrap items-center justify-between gap-3 mt-3 pt-2 border-t border-slate-800/80 text-xs">
            <div className="flex items-center gap-2">
              <span
                className={`px-2 py-0.5 rounded font-mono ${
                  points.length >= 3
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/30'
                    : 'bg-slate-800 text-slate-400'
                }`}
              >
                {points.length} vertices {points.length >= 3 ? '✓ (Ready)' : '(Min 3 required)'}
              </span>
              {points.length > 0 && (
                <>
                  <button
                    onClick={handleUndoPoint}
                    className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
                    title="Remove last vertex"
                  >
                    ↺ Undo Point
                  </button>
                  <button
                    onClick={handleClearPoints}
                    className="px-2 py-1 rounded bg-slate-800 hover:bg-red-950/40 text-red-400 transition"
                    title="Clear all vertices"
                  >
                    🗑️ Clear
                  </button>
                </>
              )}
            </div>

            {/* Quick Boundary Presets */}
            <div className="flex items-center gap-1.5 text-slate-400">
              <span className="text-[11px] uppercase tracking-wider text-slate-500 mr-1">Presets:</span>
              <button
                onClick={() => applyPreset('full')}
                className="px-2 py-0.5 rounded bg-slate-800/80 hover:bg-slate-700 text-slate-300"
              >
                Full Frame
              </button>
              <button
                onClick={() => applyPreset('left')}
                className="px-2 py-0.5 rounded bg-slate-800/80 hover:bg-slate-700 text-slate-300"
              >
                Left 50%
              </button>
              <button
                onClick={() => applyPreset('right')}
                className="px-2 py-0.5 rounded bg-slate-800/80 hover:bg-slate-700 text-slate-300"
              >
                Right 50%
              </button>
              <button
                onClick={() => applyPreset('center')}
                className="px-2 py-0.5 rounded bg-slate-800/80 hover:bg-slate-700 text-slate-300"
              >
                Center Box
              </button>
              <button
                onClick={() => applyPreset('bottom')}
                className="px-2 py-0.5 rounded bg-slate-800/80 hover:bg-slate-700 text-slate-300"
              >
                Lower Half
              </button>
            </div>
          </div>

          {/* Quick instructions pill */}
          <div className="mt-2 text-[11px] text-slate-500 flex items-center gap-3">
            <span>💡 <b>Tip:</b> Click & drag any numbered circle to move the corner.</span>
            <span>Click <b>+</b> on any line to add a new corner.</span>
            <span><b>Right-click</b> a corner to delete it.</span>
          </div>
        </div>
      </div>

      {/* Right Col: Zone Configurator */}
      <div className="space-y-4">
        <div className="panel p-5 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl space-y-4">
          <div className="text-sm font-bold tracking-wide text-slate-200 uppercase border-b border-slate-800 pb-2 flex items-center justify-between">
            <span>{editingZoneId ? '✏️ Edit Zone Geometry' : '⚙️ Configure New Zone'}</span>
            <span className="text-[11px] font-mono text-cyan-400">
              {editingZoneId ? 'UPDATING' : 'Step 2 of 2'}
            </span>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1 font-medium">Zone Name</label>
            <input
              placeholder="e.g., Perimeter Zero-Line, Server Bay"
              value={zoneName}
              onChange={(e) => setZoneName(e.target.value)}
              className="w-full bg-black/40 border border-ops-border rounded-lg px-3 py-2 text-sm text-slate-200 placeholder-slate-600 focus:outline-none focus:border-cyan-500"
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1 font-medium">Security Zone Level</label>
            <select
              value={zoneType}
              onChange={(e) => setZoneType(e.target.value)}
              className="w-full bg-ops-card border border-ops-border rounded-lg px-3 py-2 text-sm text-ops-text focus:outline-none focus:border-cyan-500 font-sans"
            >
              <option value="high_security">🔴 High-Security (Zero Line - Instant Critical Red Alert)</option>
              <option value="restricted">🟠 Restricted (Perimeter Buffer - High Alert)</option>
              <option value="monitored">🟡 Monitored (Approach Sector - Medium Alert)</option>
              <option value="sensitive">🔒 Sensitive Facility (Strict Role Clearance)</option>
              <option value="entry">🚪 Entry Gate / Checkpost (Attendance & Face Log)</option>
              <option value="exit">🚪 Exit Gate</option>
              <option value="vehicle_only">🚗 Vehicle-Only Lane (No Pedestrians)</option>
              <option value="general">🟢 General (Patrol Track)</option>
            </select>
          </div>

          {/* Military Star Clearance & Authority Level */}
          <div className="border border-amber-500/30 bg-amber-950/15 rounded-xl p-3.5 space-y-3 shadow-inner">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-amber-400 flex items-center gap-1.5 uppercase tracking-wider">
                <span>⭐</span> Star Authority Clearance Level
              </label>
              <span className="text-[10px] px-2 py-0.5 rounded font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
                {minRankStars === 0 ? 'OPEN / UNRESTRICTED' : `${'⭐'.repeat(minRankStars)} LEVEL ${minRankStars}`}
              </span>
            </div>

            <div className="grid grid-cols-3 gap-1.5">
              {[
                { stars: 0, label: '0 — Open Patrol', desc: 'No star restriction' },
                { stars: 1, label: '⭐ Level 1', desc: 'Sentry / Guard' },
                { stars: 2, label: '⭐⭐ Level 2', desc: 'Duty Officer' },
                { stars: 3, label: '⭐⭐⭐ Level 3', desc: 'Field Officer / Major' },
                { stars: 4, label: '⭐⭐⭐⭐ Level 4', desc: 'Division Cmd' },
                { stars: 5, label: '⭐⭐⭐⭐⭐ Level 5', desc: 'Supreme Command' },
              ].map((tier) => (
                <button
                  key={tier.stars}
                  type="button"
                  onClick={() => setMinRankStars(tier.stars)}
                  className={`p-2 rounded-lg border text-left transition-all ${
                    minRankStars === tier.stars
                      ? 'bg-amber-500/25 border-amber-400 text-amber-200 shadow-md shadow-amber-500/15'
                      : 'bg-black/40 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-300'
                  }`}
                >
                  <div className="text-[11px] font-bold">{tier.label}</div>
                  <div className="text-[9px] text-slate-500 truncate">{tier.desc}</div>
                </button>
              ))}
            </div>

            {/* Custom Boundary & Escort Rules */}
            <div className="pt-2 border-t border-amber-500/20 space-y-2.5">
              <label className="flex items-center gap-2.5 text-xs text-slate-300 cursor-pointer">
                <input
                  type="checkbox"
                  checked={allowEscort}
                  onChange={(e) => setAllowEscort(e.target.checked)}
                  className="rounded border-amber-700 bg-slate-900 text-amber-500 focus:ring-0"
                />
                <span>🤝 Allow Lower Ranks if Escorted by an Authorized Officer</span>
              </label>

              <div>
                <label className="block text-[11px] text-slate-400 mb-1">
                  Custom Authority Perimeter Tag (Optional)
                </label>
                <input
                  placeholder="e.g. WAR_ROOM_ALPHA, ARMORY_ZONE_B, ZERO_LINE"
                  value={authorityCustomLevel}
                  onChange={(e) => setAuthorityCustomLevel(e.target.value.toUpperCase())}
                  className="w-full bg-black/40 border border-ops-border rounded-lg px-2.5 py-1.5 text-xs font-mono text-amber-300 placeholder-slate-600 uppercase"
                />
              </div>
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1 font-medium">
              Linger / Dwell Alert Threshold (seconds)
            </label>
            <input
              type="number"
              min={0}
              max={300}
              value={threshold}
              onChange={(e) => setThreshold(Number(e.target.value))}
              className="w-full bg-black/40 border border-ops-border rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-cyan-500"
            />
            <p className="text-[11px] text-slate-500 mt-1">
              {threshold === 0
                ? 'Instant intrusion alarm upon stepping inside.'
                : `Alarms if target stays stationary inside for > ${threshold} seconds.`}
            </p>
          </div>

          <div className="space-y-2.5 pt-1">
            <label className="flex items-center gap-2.5 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={nightOnly}
                onChange={(e) => setNightOnly(e.target.checked)}
                className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0"
              />
              <span>🌙 Restricted after-hours only (10:00 PM – 6:00 AM)</span>
            </label>

            <label className="flex items-center gap-2.5 text-xs text-slate-300 cursor-pointer">
              <input
                type="checkbox"
                checked={openAccess}
                onChange={(e) => setOpenAccess(e.target.checked)}
                className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0"
              />
              <span>🌐 Open to all personnel (no specific access list)</span>
            </label>
          </div>

          {!openAccess && (
            <div className="border border-slate-800 rounded-lg p-3 bg-black/20 space-y-2">
              <label className="block text-xs font-semibold text-cyan-400">
                Authorized Personnel Whitelist ({selectedIdentities.length} selected)
              </label>
              <div className="max-h-36 overflow-y-auto space-y-1 pr-1 custom-scrollbar">
                {identities.length === 0 ? (
                  <p className="text-xs text-slate-500 italic">No registered identities found.</p>
                ) : (
                  identities.map((id) => (
                    <label
                      key={id.identity_id}
                      className="flex items-center gap-2 text-xs text-slate-300 hover:bg-slate-800/40 p-1 rounded cursor-pointer"
                    >
                      <input
                        type="checkbox"
                        checked={selectedIdentities.includes(id.identity_id)}
                        onChange={(e) =>
                          setSelectedIdentities((prev) =>
                            e.target.checked
                              ? [...prev, id.identity_id]
                              : prev.filter((x) => x !== id.identity_id)
                          )
                        }
                        className="rounded border-slate-700 bg-slate-900 text-cyan-500 focus:ring-0"
                      />
                      <span>{id.name}</span>
                      <span className="text-[10px] text-slate-500 font-mono">[{id.role}]</span>
                    </label>
                  ))
                )}
              </div>
            </div>
          )}

          <div className="flex gap-2">
            {editingZoneId && (
              <button
                type="button"
                onClick={handleCancelEdit}
                className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300 font-medium rounded-lg py-2.5 text-sm transition"
              >
                Cancel
              </button>
            )}
            <button
              onClick={handleSaveZone}
              disabled={points.length < 3 || !selectedCamera || !zoneName.trim()}
              className={`${
                editingZoneId ? 'flex-2 bg-emerald-500 hover:bg-emerald-400 text-slate-950' : 'w-full bg-cyan-500 hover:bg-cyan-400 text-slate-950'
              } disabled:bg-slate-800 disabled:text-slate-600 font-bold rounded-lg py-2.5 text-sm transition shadow-lg shadow-cyan-500/20 disabled:shadow-none`}
            >
              {points.length < 3
                ? 'Draw at least 3 points'
                : editingZoneId
                ? '✓ Update Virtual Zone'
                : '✓ Save Virtual Zone'}
            </button>
          </div>
        </div>

        {/* Existing Zones on Camera */}
        <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-400 mb-3 flex items-center justify-between">
            <span>Existing Zones ({zones.length})</span>
            <span className="text-[10px] text-slate-500">Live AI Monitored</span>
          </div>

          {zones.length === 0 ? (
            <p className="text-xs text-slate-500 italic py-2">No virtual zones drawn on this camera yet.</p>
          ) : (
            <div className="space-y-2 max-h-56 overflow-y-auto pr-1">
              {zones.map((z) => {
                const badge = ZONE_COLORS[z.zone_type] || ZONE_COLORS.general
                const isCurrent = editingZoneId === z.zone_id

                return (
                  <div
                    key={z.zone_id}
                    onMouseEnter={() => setHoveredZoneId(z.zone_id)}
                    onMouseLeave={() => setHoveredZoneId(null)}
                    className={`flex items-center justify-between p-2.5 rounded-lg border text-xs transition ${
                      isCurrent
                        ? 'border-cyan-500 bg-cyan-950/20 text-cyan-200 shadow-md shadow-cyan-500/10'
                        : 'border-slate-800 hover:border-slate-700 bg-black/30 text-slate-300'
                    }`}
                  >
                    <div>
                      <div className="font-semibold text-slate-200 flex items-center gap-1.5">
                        <span>{z.name}</span>
                        {isCurrent && (
                          <span className="text-[9px] bg-cyan-500 text-slate-950 font-bold px-1 rounded">
                            ACTIVE EDIT
                          </span>
                        )}
                      </div>
                      <div className="flex items-center gap-1.5 mt-0.5 flex-wrap">
                        <span className={`text-[10px] font-mono px-1.5 py-0.2 rounded border ${badge.badgeBg}`}>
                          {z.zone_type.toUpperCase()}
                        </span>
                        {z.min_rank_stars && z.min_rank_stars > 0 ? (
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded border bg-amber-500/20 text-amber-300 border-amber-500/40 inline-flex items-center gap-1 whitespace-nowrap">
                            <span className="inline-flex items-center gap-0.5">
                              {Array.from({ length: z.min_rank_stars }).map((_, i) => (
                                <Star key={i} className="w-2.5 h-2.5 fill-amber-400 text-amber-400" />
                              ))}
                            </span>
                            <span>L{z.min_rank_stars}</span>
                          </span>
                        ) : (
                          <span className="text-[10px] font-mono px-1.5 py-0.2 rounded border bg-slate-800 text-slate-400 border-slate-700">
                            OPEN
                          </span>
                        )}
                        {z.allow_escort && (
                          <span className="text-[9px] text-emerald-300 bg-emerald-500/15 border border-emerald-500/30 px-1 rounded">
                            Escort OK
                          </span>
                        )}
                        {z.authority_custom_level && (
                          <span className="text-[9px] text-cyan-300 bg-cyan-500/15 border border-cyan-500/30 px-1 rounded font-mono">
                            {z.authority_custom_level}
                          </span>
                        )}
                        <span className="text-slate-500 text-[10px]">{z.threshold_seconds}s dwell</span>
                        <span className="text-slate-500 text-[10px]">• {z.polygon.length} pts</span>
                      </div>
                    </div>
                    <div className="flex items-center gap-1">
                      <button
                        onClick={() => handleStartEditZone(z)}
                        className="px-2 py-1 text-cyan-400 hover:text-cyan-300 hover:bg-cyan-500/10 rounded transition"
                        title="Edit zone edges & parameters"
                      >
                        ✏️ Edit
                      </button>
                      <button
                        onClick={() => handleDeleteZone(z.zone_id)}
                        className="px-2 py-1 text-red-400 hover:text-red-300 hover:bg-red-500/10 rounded transition"
                        title="Delete zone"
                      >
                        🗑️
                      </button>
                    </div>
                  </div>
                )
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
