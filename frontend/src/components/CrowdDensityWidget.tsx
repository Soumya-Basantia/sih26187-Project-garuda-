import React, { useState, useEffect } from 'react'
import { Users, AlertTriangle, ShieldAlert, TrendingUp, Activity, CheckCircle2, ChevronRight, Siren } from 'lucide-react'

export interface ZoneCrowdData {
  zone_id: string
  zone_name: string
  camera_id: string
  camera_name: string
  current_count: number
  threshold_surge: number
  threshold_mob: number
  status: 'NORMAL' | 'SURGE_WARNING' | 'MOB_CRITICAL'
  trend: 'UP' | 'STABLE' | 'DOWN'
  last_updated: number
}

interface CrowdDensityWidgetProps {
  onDispatchQRT?: (zoneName: string) => void
  compact?: boolean
}

// Realistic operational zones for border outposts & check gates
const INITIAL_ZONES: ZoneCrowdData[] = [
  {
    zone_id: 'zone_north_gate_01',
    zone_name: 'Gate 01 Ingress Corridor',
    camera_id: 'cam_01',
    camera_name: 'North Gate Alpha',
    current_count: 3,
    threshold_surge: 6,
    threshold_mob: 10,
    status: 'NORMAL',
    trend: 'STABLE',
    last_updated: Date.now(),
  },
  {
    zone_id: 'zone_perimeter_bop_02',
    zone_name: 'Zero-Line Neutral Buffer',
    camera_id: 'cam_02',
    camera_name: 'BOP Forward Post',
    current_count: 7,
    threshold_surge: 6,
    threshold_mob: 10,
    status: 'SURGE_WARNING',
    trend: 'UP',
    last_updated: Date.now(),
  },
  {
    zone_id: 'zone_customs_corridor_03',
    zone_name: 'Customs Transit Checkpoint',
    camera_id: 'cam_03',
    camera_name: 'Terminal Transit Hub',
    current_count: 2,
    threshold_surge: 8,
    threshold_mob: 12,
    status: 'NORMAL',
    trend: 'DOWN',
    last_updated: Date.now(),
  },
  {
    zone_id: 'zone_depot_secure_04',
    zone_name: 'Ammunition & Fuel Depot',
    camera_id: 'cam_04',
    camera_name: 'Logistics Depot Cam',
    current_count: 1,
    threshold_surge: 4,
    threshold_mob: 7,
    status: 'NORMAL',
    trend: 'STABLE',
    last_updated: Date.now(),
  },
]

export default function CrowdDensityWidget({ onDispatchQRT, compact = false }: CrowdDensityWidgetProps) {
  const [zones, setZones] = useState<ZoneCrowdData[]>(INITIAL_ZONES)
  const [selectedZone, setSelectedZone] = useState<string | null>(null)
  const [dispatchedZone, setDispatchedZone] = useState<string | null>(null)

  // Dynamic simulation / heartbeat for live crowd oscillations
  useEffect(() => {
    const interval = setInterval(() => {
      setZones((prev) =>
        prev.map((z) => {
          // Slight oscillation to simulate real movement
          const delta = (Math.random() > 0.6 ? 1 : 0) - (Math.random() > 0.65 ? 1 : 0)
          const newCount = Math.max(0, Math.min(16, z.current_count + delta))
          let status: 'NORMAL' | 'SURGE_WARNING' | 'MOB_CRITICAL' = 'NORMAL'
          if (newCount >= z.threshold_mob) {
            status = 'MOB_CRITICAL'
          } else if (newCount >= z.threshold_surge) {
            status = 'SURGE_WARNING'
          }
          const trend: 'UP' | 'STABLE' | 'DOWN' =
            newCount > z.current_count ? 'UP' : newCount < z.current_count ? 'DOWN' : 'STABLE'

          return {
            ...z,
            current_count: newCount,
            status,
            trend,
            last_updated: Date.now(),
          }
        })
      )
    }, 4500)

    return () => clearInterval(interval)
  }, [])

  const totalPeople = zones.reduce((acc, z) => acc + z.current_count, 0)
  const surgeCount = zones.filter((z) => z.status !== 'NORMAL').length

  function handleDispatch(zone: ZoneCrowdData) {
    setDispatchedZone(zone.zone_id)
    if (onDispatchQRT) {
      onDispatchQRT(zone.zone_name)
    } else {
      alert(`🚨 Quick Reaction Team (QRT) dispatched to ${zone.zone_name} (Camera ${zone.camera_name}). Code: CROWD_DISPERSAL`)
    }
    setTimeout(() => setDispatchedZone(null), 4000)
  }

  return (
    <div className="tactical-panel hud-corner p-4 rounded-xl border border-ops-border/70 bg-slate-900/80 backdrop-blur flex flex-col space-y-3">
      {/* Header */}
      <div className="flex items-center justify-between pb-2.5 border-b border-slate-800">
        <div className="flex items-center gap-2">
          <Users className="w-4 h-4 text-cyan-400" />
          <span className="text-xs font-bold font-display uppercase tracking-wider text-slate-200">
            Perimeter Crowd Density
          </span>
          {surgeCount > 0 && (
            <span className="px-1.5 py-0.5 rounded text-[10px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40 animate-pulse flex items-center gap-1">
              <AlertTriangle className="w-2.5 h-2.5" />
              {surgeCount} ZONE SURGE
            </span>
          )}
        </div>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-mono text-slate-400">
            Total Ingress: <strong className="text-cyan-300">{totalPeople}</strong>
          </span>
          <span className="w-2 h-2 rounded-full bg-emerald-500 animate-ping" title="Live Neural Counter Active" />
        </div>
      </div>

      {/* Zone Bars */}
      <div className="space-y-2.5">
        {zones.map((zone) => {
          const pct = Math.min(100, Math.round((zone.current_count / zone.threshold_mob) * 100))
          const isSurge = zone.status === 'SURGE_WARNING'
          const isCritical = zone.status === 'MOB_CRITICAL'

          const barColor = isCritical
            ? 'bg-gradient-to-r from-orange-500 to-red-500 shadow-red-500/50 shadow-sm'
            : isSurge
            ? 'bg-gradient-to-r from-amber-500 to-orange-500'
            : 'bg-gradient-to-r from-cyan-500 to-emerald-500'

          const statusBadge = isCritical ? (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-red-500/20 text-red-300 border border-red-500/40 animate-pulse">
              MOB ALERT
            </span>
          ) : isSurge ? (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono font-bold bg-amber-500/20 text-amber-300 border border-amber-500/40">
              CROWD SURGE
            </span>
          ) : (
            <span className="px-1.5 py-0.5 rounded text-[9px] font-mono text-emerald-400 bg-emerald-500/10 border border-emerald-500/20">
              CLEAR
            </span>
          )

          return (
            <div
              key={zone.zone_id}
              className={`p-2 rounded-lg border transition cursor-pointer ${
                selectedZone === zone.zone_id
                  ? 'bg-slate-800/80 border-cyan-500/60 shadow-md'
                  : 'bg-black/30 border-slate-800/80 hover:bg-slate-800/40'
              }`}
              onClick={() => setSelectedZone(selectedZone === zone.zone_id ? null : zone.zone_id)}
            >
              <div className="flex items-center justify-between text-xs mb-1">
                <div className="flex items-center gap-1.5 truncate max-w-[200px]">
                  <span className="font-semibold text-slate-200 truncate">{zone.zone_name}</span>
                  <span className="text-[10px] font-mono text-slate-500">({zone.camera_id})</span>
                </div>
                <div className="flex items-center gap-2">
                  <span className="text-xs font-mono font-bold text-slate-100">
                    {zone.current_count}{' '}
                    <span className="text-[10px] font-normal text-slate-400">/ max {zone.threshold_mob}</span>
                  </span>
                  {statusBadge}
                </div>
              </div>

              {/* Progress Bar with Surge Markers */}
              <div className="relative w-full h-2 rounded-full bg-slate-800 overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${barColor}`}
                  style={{ width: `${pct}%` }}
                />
                {/* Surge Marker Line */}
                <div
                  className="absolute top-0 bottom-0 w-0.5 bg-amber-400/80 z-10"
                  style={{ left: `${(zone.threshold_surge / zone.threshold_mob) * 100}%` }}
                  title={`Surge threshold: ${zone.threshold_surge}`}
                />
              </div>

              {/* Expanded Action details */}
              {selectedZone === zone.zone_id && !compact && (
                <div className="mt-2 pt-2 border-t border-slate-800 flex items-center justify-between text-[10px] font-mono text-slate-400">
                  <div className="flex items-center gap-2">
                    <span>
                      Trend: <strong className={zone.trend === 'UP' ? 'text-amber-400' : 'text-slate-300'}>{zone.trend}</strong>
                    </span>
                    <span>Surge Threshold: {zone.threshold_surge}</span>
                  </div>
                  <button
                    onClick={(e) => {
                      e.stopPropagation()
                      handleDispatch(zone)
                    }}
                    disabled={dispatchedZone === zone.zone_id}
                    className={`px-2 py-1 rounded text-[10px] font-bold font-sans flex items-center gap-1 transition ${
                      dispatchedZone === zone.zone_id
                        ? 'bg-emerald-700 text-white'
                        : isCritical || isSurge
                        ? 'bg-red-600 hover:bg-red-500 text-white shadow-sm'
                        : 'bg-slate-700 hover:bg-slate-600 text-slate-200'
                    }`}
                  >
                    <Siren className="w-3 h-3" />
                    <span>{dispatchedZone === zone.zone_id ? 'QRT DISPATCHED ✓' : 'Dispatch QRT'}</span>
                  </button>
                </div>
              )}
            </div>
          )
        })}
      </div>

      {/* Footer Info */}
      <div className="pt-2 border-t border-slate-800/80 flex items-center justify-between text-[10px] font-mono text-slate-500">
        <span className="flex items-center gap-1">
          <Activity className="w-3 h-3 text-cyan-400" />
          <span>ALGORITHM: YOLOv8 + ByteTrack Zone Clustering</span>
        </span>
        <span>Auto-Cooldown: 120s</span>
      </div>
    </div>
  )
}
