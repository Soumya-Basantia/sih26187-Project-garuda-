import React, { useEffect, useState } from 'react'
import { cameraApi, alertApi, connectEventSocket, Camera, Alert } from '../services/api'
import TacticalRadarMap from '../components/TacticalRadarMap'
import { Radar, Camera as CameraIcon, ShieldAlert, X, Radio, Eye } from 'lucide-react'

export default function TacticalRadarPage() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [fullscreenCamera, setFullscreenCamera] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    loadData().finally(() => setLoading(false))
    const ws = connectEventSocket((msg) => {
      if (msg.type === 'new_alert') {
        const alert = msg.data
        setAlerts((prev) => [alert, ...prev].slice(0, 50))
      }
    })
    const interval = setInterval(loadData, 15000)
    return () => { ws.close(); clearInterval(interval) }
  }, [])

  async function loadData() {
    try {
      const [camRes, alertRes] = await Promise.all([
        cameraApi.list(),
        alertApi.list()
      ])
      setCameras(camRes.data)
      setAlerts(alertRes.data)
    } catch (e) {
      console.error('Failed to load radar data', e)
    }
  }

  const activeThreats = alerts.filter(a => a.severity === 'RED' || a.severity === 'ORANGE').length

  return (
    <div className="p-4 h-full overflow-hidden flex flex-col gap-3 bg-ops-bg text-ops-text">
      {/* Top Banner */}
      <div className="tactical-panel px-4 py-3 flex flex-wrap items-center justify-between gap-3 shrink-0">
        <div className="flex items-center gap-3">
          <div className="w-9 h-9 rounded-lg bg-ops-accent/15 border border-ops-accent/40 flex items-center justify-center shrink-0">
            <Radar className="w-5 h-5 text-ops-accent animate-pulse" />
          </div>
          <div>
            <div className="text-sm font-bold tracking-wider font-display text-ops-text flex items-center gap-2">
              <span>2D TACTICAL RADAR & C2 PERIMETER MAP</span>
              <span className="w-2 h-2 rounded-full bg-red-500 animate-ping" />
            </div>
            <div className="text-[11px] text-ops-text-muted font-mono mt-0.5">
              Multi-Sensor FOV Cones · Spatial Entity Trajectories · Automated Handover Prediction
            </div>
          </div>
        </div>

        <div className="flex items-center gap-3 text-xs font-mono">
          <div className="flex items-center gap-1.5 bg-ops-surface px-3 py-1.5 rounded-md border border-ops-border">
            <CameraIcon className="w-3.5 h-3.5 text-ops-accent" />
            <span className="text-ops-text-muted">Sensors:</span>
            <span className="text-emerald-500 font-bold">{cameras.length} Nodes</span>
          </div>

          <div className="flex items-center gap-1.5 bg-ops-surface px-3 py-1.5 rounded-md border border-ops-border">
            <ShieldAlert className="w-3.5 h-3.5 text-red-400" />
            <span className="text-ops-text-muted">Threats:</span>
            <span className="text-red-500 font-bold">{activeThreats} Active</span>
          </div>

          <div className="flex items-center gap-1.5 bg-red-500/15 px-3 py-1.5 rounded-md border border-red-500/40 text-red-500 font-bold">
            <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
            <span>DEFCON 2</span>
          </div>
        </div>
      </div>

      {/* Main Radar Component */}
      <div className="flex-1 min-h-0 rounded-xl overflow-hidden border border-ops-border shadow-tactical">
        <TacticalRadarMap
          cameras={cameras}
          alerts={alerts}
          onSelectCamera={(id) => setFullscreenCamera(id)}
        />
      </div>

      {/* Fullscreen Video Modal if clicked */}
      {fullscreenCamera && (
        <div
          className="fixed inset-0 bg-black/85 backdrop-blur-sm z-50 flex items-center justify-center p-6"
          onClick={() => setFullscreenCamera(null)}
        >
          <div className="tactical-panel bg-ops-panel border border-ops-border rounded-xl max-w-5xl w-full overflow-hidden shadow-2xl" onClick={e => e.stopPropagation()}>
            <div className="p-3.5 border-b border-ops-border flex items-center justify-between bg-ops-panel-alt">
              <div className="flex items-center gap-2">
                <CameraIcon className="w-4 h-4 text-ops-accent" />
                <span className="font-semibold text-sm text-ops-text font-display">
                  LIVE SENSOR FEED: {fullscreenCamera}
                </span>
              </div>
              <button
                onClick={() => setFullscreenCamera(null)}
                className="p-1 rounded-md text-ops-text-muted hover:text-ops-text hover:bg-ops-surface"
              >
                <X className="w-5 h-5" />
              </button>
            </div>
            <div className="relative bg-black flex items-center justify-center min-h-[450px]">
              <img
                src={cameraApi.streamUrl(fullscreenCamera)}
                alt="Fullscreen Camera"
                className="max-h-[75vh] w-auto object-contain"
                onError={(e) => {
                  e.currentTarget.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjI0MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjMTEyMjMzIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJtb25vc3BhY2UiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM2NjgiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj5DYW1lcmEgT2ZmbGluZTwvdGV4dD48L3N2Zz4='
                }}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
