import React, { useState, useEffect } from 'react'
import {
  ShieldAlert,
  AlertTriangle,
  User,
  Package,
  Clock,
  MapPin,
  ArrowRight,
  Radio,
  CheckCircle2,
  X,
  Footprints,
  Compass,
  FileText,
  Shield,
  Zap,
  Target,
  Camera
} from 'lucide-react'
import { cameraApi, getSnapshotUrl } from '../services/api'

export interface HumanObjectData {
  event_id: string
  object_type: 'Backpack' | 'Suitcase' | 'Briefcase' | 'Package' | 'Duffle Bag'
  object_track_id: number
  camera_id: string
  camera_name?: string
  location?: string
  stationary_seconds: number
  owner_track_id?: number
  owner_name?: string
  owner_role?: string
  owner_stars?: number
  separation_distance_px: number
  separation_distance_meters?: number
  severity: 'RED' | 'ORANGE' | 'YELLOW'
  timestamp: number
  snapshot_url?: string
  snapshot_data?: string
  description?: string
  current_status: 'STATIONARY_HAZARD' | 'UNATTENDED_MONITORED' | 'OWNER_REUNITED' | 'SECURED_BY_PATROL'
}

interface HumanObjectInspectorProps {
  data: HumanObjectData
  onClose: () => void
  onDispatchPatrol?: (trackId: number, location: string) => void
  onTraceOwner?: (ownerTrackId?: number, ownerName?: string) => void
}

export default function HumanObjectInspector({
  data,
  onClose,
  onDispatchPatrol,
  onTraceOwner,
}: HumanObjectInspectorProps) {
  const [elapsedSeconds, setElapsedSeconds] = useState(data.stationary_seconds || 15)
  const [patrolDispatched, setPatrolDispatched] = useState(false)
  const [tracingActive, setTracingActive] = useState(false)

  // Live ticking abandonment timer
  useEffect(() => {
    const timer = setInterval(() => {
      setElapsedSeconds((prev) => prev + 1)
    }, 1000)
    return () => clearInterval(timer)
  }, [])

  const formatDwell = (sec: number) => {
    const m = Math.floor(sec / 60)
    const s = sec % 60
    return `${m.toString().padStart(2, '0')}m ${s.toString().padStart(2, '0')}s`
  }

  const handleDispatch = () => {
    setPatrolDispatched(true)
    if (onDispatchPatrol) {
      onDispatchPatrol(data.object_track_id, data.location || data.camera_id)
    }
  }

  const handleTrace = () => {
    setTracingActive(true)
    if (onTraceOwner) {
      onTraceOwner(data.owner_track_id, data.owner_name)
    }
  }

  const isCritical = data.severity === 'RED' || elapsedSeconds > 15

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/85 backdrop-blur-md animate-fade-in">
      <div className="panel p-6 border border-slate-700 bg-slate-900/95 rounded-2xl max-w-2xl w-full space-y-5 shadow-2xl relative max-h-[90vh] overflow-y-auto">
        {/* Header Bar */}
        <div className="flex items-center justify-between border-b border-slate-800 pb-3">
          <div className="flex items-center gap-2.5">
            <ShieldAlert className={`w-6 h-6 ${isCritical ? 'text-red-500 animate-pulse' : 'text-amber-400'}`} />
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-bold text-slate-100 uppercase tracking-wide font-display">
                  Human-Object Forensic Dossier (HOI)
                </h2>
                <span
                  className={`text-[10px] font-mono font-bold px-2 py-0.5 rounded border ${
                    isCritical
                      ? 'bg-red-500/20 text-red-300 border-red-500/40'
                      : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  }`}
                >
                  {isCritical ? '🚨 ABANDONED HAZARD' : '⚠️ UNATTENDED OBJECT'}
                </span>
              </div>
              <p className="text-[11px] text-slate-400 font-mono mt-0.5">
                INCIDENT ID: #{data.event_id.slice(-8)} · CAMERA: {data.camera_name || data.camera_id}
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            className="text-slate-400 hover:text-slate-200 text-lg px-2 py-1 rounded transition"
          >
            ✕
          </button>
        </div>

        {/* Live Abandonment Dwell Counter Banner */}
        <div className="p-3.5 rounded-xl bg-gradient-to-r from-red-950/40 via-black/60 to-slate-950 border border-red-500/30 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-lg bg-red-500/20 border border-red-500/40 flex items-center justify-center">
              <Clock className="w-5 h-5 text-red-400 animate-spin" style={{ animationDuration: '6s' }} />
            </div>
            <div>
              <span className="text-[10px] font-mono text-red-300 uppercase tracking-wider block">
                Continuous Abandoned Dwell Duration
              </span>
              <div className="text-2xl font-bold font-mono text-slate-100 flex items-center gap-2">
                <span>{formatDwell(elapsedSeconds)}</span>
                <span className="text-xs font-normal text-slate-400 font-sans">
                  (Hazard Threshold: 15.0s)
                </span>
              </div>
            </div>
          </div>

          <div className="text-right">
            <span className="text-[10px] font-mono text-slate-400 block uppercase">Spatial Separation</span>
            <span className="text-lg font-bold font-mono text-amber-400">
              {data.separation_distance_px > 0 ? `${data.separation_distance_px} px` : 'Out of Frame'}
              {data.separation_distance_meters && (
                <span className="text-xs text-slate-400 font-normal ml-1">
                  (~{data.separation_distance_meters.toFixed(1)}m)
                </span>
              )}
            </span>
          </div>
        </div>

        {/* Optical Evidence Snapshot Card */}
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs">
            <span className="text-slate-400 uppercase tracking-wider font-mono text-[11px] flex items-center gap-1.5">
              <Camera className="w-3.5 h-3.5 text-cyan-400" />
              <span>Optical Evidence Snapshot (T₁ Separation Frame)</span>
            </span>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-black/60 border border-slate-700 text-amber-300">
              SENSOR: {data.camera_id}
            </span>
          </div>

          <div className="relative border border-slate-800 rounded-xl bg-black/80 overflow-hidden flex items-center justify-center min-h-[190px] max-h-72">
            <img
              src={data.snapshot_data || getSnapshotUrl(data.snapshot_url) || cameraApi.snapshotUrl(data.camera_id)}
              alt="HOI Incident Snapshot"
              className="w-full h-auto max-h-72 object-contain"
              onError={(e) => {
                const fallback = cameraApi.snapshotUrl(data.camera_id)
                if (e.currentTarget.src !== fallback) {
                  e.currentTarget.src = fallback
                } else {
                  e.currentTarget.style.display = 'none'
                  const parent = e.currentTarget.parentElement
                  if (parent) {
                    parent.innerHTML = `
                      <div class="p-8 text-center space-y-1">
                        <div class="text-2xl mb-1">🎒</div>
                        <div class="text-xs font-mono font-bold text-slate-200">HOI TARGET FRAME LOGGED</div>
                        <div class="text-[10px] text-slate-400 font-mono">Incident: #${data.event_id.slice(-8)} · Separation: ${data.separation_distance_px}px</div>
                      </div>
                    `
                  }
                }
              }}
            />
            <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/80 border border-red-500/40 text-[10px] font-mono text-red-400 flex items-center gap-1">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-ping" />
              <span>INCIDENT SNAPSHOT #{data.event_id.slice(-6)}</span>
            </div>
            <div className="absolute bottom-2 right-2 px-2 py-0.5 rounded bg-black/80 border border-slate-700 text-[10px] font-mono text-slate-400">
              {new Date(data.timestamp * 1000).toLocaleTimeString()}
            </div>
          </div>
        </div>

        {/* 3-Stage Forensic Lifecycle Timeline */}
        <div className="p-4 rounded-xl bg-black/40 border border-slate-800 space-y-3">
          <div className="text-xs font-bold uppercase tracking-wider text-slate-300 flex items-center justify-between">
            <span>🔄 3-Stage Human-Object Interaction Lifecycle</span>
            <span className="text-[10px] font-mono text-cyan-400">AI TEMPORAL STATE MACHINE</span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-3 gap-3 text-xs">
            {/* Stage 0 */}
            <div className="p-2.5 rounded-lg bg-emerald-950/20 border border-emerald-500/30 space-y-1">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-bold text-emerald-400 flex items-center gap-1">
                  <span>✓</span> T₀: In-Possession
                </span>
                <span className="text-[9px] font-mono text-slate-500">&le;140px</span>
              </div>
              <p className="text-[11px] text-slate-300">
                Object carried by person. Spatial trajectory and gait velocity coupled.
              </p>
            </div>

            {/* Stage 1 */}
            <div className="p-2.5 rounded-lg bg-amber-950/20 border border-amber-500/30 space-y-1">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-bold text-amber-400 flex items-center gap-1">
                  <span>⚠️</span> T₁: Separation
                </span>
                <span className="text-[9px] font-mono text-slate-500">130–200px</span>
              </div>
              <p className="text-[11px] text-slate-300">
                Object placed stationary. Owner moves beyond direct reach.
              </p>
            </div>

            {/* Stage 2 */}
            <div className="p-2.5 rounded-lg bg-red-950/30 border border-red-500/50 space-y-1 shadow-sm">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-bold text-red-400 flex items-center gap-1">
                  <span>🚨</span> T₂: Abandoned
                </span>
                <span className="text-[9px] font-mono text-red-400">&gt;15s / &gt;200px</span>
              </div>
              <p className="text-[11px] text-slate-300">
                Owner departs scene. Stationary dwell exceeds 15s safety envelope.
              </p>
            </div>
          </div>
        </div>

        {/* Dual Forensic Attribution Cards: Object vs Owner */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Object Dossier */}
          <div className="p-4 rounded-xl bg-black/40 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="text-xs font-bold text-slate-200 uppercase flex items-center gap-1.5">
                <Package className="w-4 h-4 text-cyan-400" />
                <span>Object Characteristics</span>
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                Track #{data.object_track_id}
              </span>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">Object Category:</span>
                <span className="text-slate-200 font-semibold">{data.object_type}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Camera / Sensor:</span>
                <span className="text-slate-200 font-mono">{data.camera_id}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Stationary Since:</span>
                <span className="text-slate-200 font-mono">
                  {new Date(data.timestamp * 1000).toLocaleTimeString()}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Current Threat State:</span>
                <span className="text-red-400 font-bold font-mono">HIGH_PRIORITY_HAZARD</span>
              </div>
            </div>
          </div>

          {/* Owner Attribution Dossier */}
          <div className="p-4 rounded-xl bg-black/40 border border-slate-800 space-y-3">
            <div className="flex items-center justify-between border-b border-slate-800 pb-2">
              <span className="text-xs font-bold text-slate-200 uppercase flex items-center gap-1.5">
                <User className="w-4 h-4 text-amber-400" />
                <span>Owner Attribution</span>
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20">
                {data.owner_track_id ? `Track #${data.owner_track_id}` : 'Unpaired'}
              </span>
            </div>

            <div className="space-y-2 text-xs">
              <div className="flex justify-between">
                <span className="text-slate-400">Identified Owner:</span>
                <span className="text-emerald-400 font-semibold">
                  {data.owner_name ? `✓ ${data.owner_name}` : 'Unenrolled Visitor / Suspect'}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Organization Role:</span>
                <span className="text-slate-200">{data.owner_role || 'Visitor (Unenrolled)'}</span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Clearance Level:</span>
                <span className="text-slate-200 font-mono">
                  {'⭐'.repeat(data.owner_stars || 1)} Level {data.owner_stars || 1}
                </span>
              </div>
              <div className="flex justify-between">
                <span className="text-slate-400">Owner Status:</span>
                <span className="text-amber-400 font-bold font-mono">
                  {data.separation_distance_px > 200 || data.separation_distance_px === -1
                    ? 'DEPARTED SECTOR / EXITED'
                    : 'IN VICINITY'}
                </span>
              </div>
            </div>
          </div>
        </div>

        {/* Forensic Behavioral Rationale */}
        <div className="p-3 rounded-lg bg-black/50 border border-slate-800 text-xs">
          <span className="text-slate-500 font-mono text-[10px] block mb-1">AI BEHAVIORAL EXPLANATION</span>
          <p className="text-slate-300 leading-relaxed">
            {data.description ||
              `YOLOv8 + ByteTrack spatial homography engine correlated object #${data.object_track_id} (${data.object_type}) with ${
                data.owner_name ? data.owner_name : `Person #${data.owner_track_id}`
              }. Object placed at location and owner departed the safety boundary (${data.separation_distance_px}px separation). Continuous stationary dwell time exceeded 15.0-second security perimeter protocol.`}
          </p>
        </div>

        {/* Tactical Actions Dispatch Row */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-3 border-t border-slate-800">
          <div className="flex items-center gap-2">
            <button
              onClick={handleDispatch}
              disabled={patrolDispatched}
              className={`px-3.5 py-2 rounded-lg text-xs font-semibold flex items-center gap-2 transition ${
                patrolDispatched
                  ? 'bg-emerald-600/30 text-emerald-300 border border-emerald-500/50'
                  : 'bg-red-600 hover:bg-red-500 text-white shadow-lg'
              }`}
            >
              <Radio className="w-3.5 h-3.5" />
              <span>{patrolDispatched ? '✓ Patrol Unit Dispatched' : '🚨 Dispatch Security Intercept'}</span>
            </button>

            <button
              onClick={handleTrace}
              disabled={tracingActive}
              className="px-3.5 py-2 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-cyan-300 border border-slate-700 flex items-center gap-1.5 transition"
            >
              <Compass className="w-3.5 h-3.5" />
              <span>{tracingActive ? 'Tracing Trajectory...' : 'Trace Owner Movement'}</span>
            </button>
          </div>

          <button
            onClick={onClose}
            className="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
          >
            Close Dossier
          </button>
        </div>
      </div>
    </div>
  )
}
