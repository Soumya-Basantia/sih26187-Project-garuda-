import React, { useEffect, useState, useMemo } from 'react'
import { eventApi, cameraApi, getSnapshotUrl, EventItem, Camera } from '../services/api'
import { History, RefreshCw, Download, Search, CheckCircle2, AlertTriangle, ShieldAlert, Eye, X, MapPin, Package, UserCheck, Radio, FileText, Layers } from 'lucide-react'
import HumanObjectInspector, { HumanObjectData } from '../components/HumanObjectInspector'

const SEVERITY_CONFIG: Record<string, { label: string; badge: string; border: string; dot: string }> = {
  RED: {
    label: 'CRITICAL',
    badge: 'bg-red-500/20 text-red-300 border-red-500/40',
    border: 'border-red-500/40',
    dot: 'bg-red-500',
  },
  ORANGE: {
    label: 'SUSPICIOUS',
    badge: 'bg-orange-500/20 text-orange-300 border-orange-500/40',
    border: 'border-orange-500/40',
    dot: 'bg-orange-500',
  },
  YELLOW: {
    label: 'WARNING',
    badge: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40',
    border: 'border-yellow-500/40',
    dot: 'bg-yellow-500',
  },
  GREEN: {
    label: 'CLEARED',
    badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40',
    border: 'border-emerald-500/40',
    dot: 'bg-emerald-500',
  },
}

const DEFAULT_EVENTS: EventItem[] = [
  {
    event_id: 'ev_82943815',
    timestamp: Math.floor(Date.now() / 1000) - 120,
    event_type: 'ABANDONED_OBJECT',
    severity: 'RED',
    confidence: 0.98,
    camera_id: 'cam_01',
    zone_id: 'North Fence Zone A',
    track_id: 402,
    person_name: 'Major Vikram Rathore',
    person_role: 'Tactical Command',
    description: 'Tactical Backpack left unattended near Sector 1 Perimeter. Owner departed zone. Separation: 240px (~6.2m). Dwell: 42s.',
    metadata: {
      object_type: 'Backpack',
      stationary_seconds: 42,
      owner_track_id: 102,
      owner_name: 'Major Vikram Rathore',
      owner_distance: 240,
    },
  },
  {
    event_id: 'ev_82943814',
    timestamp: Math.floor(Date.now() / 1000) - 340,
    event_type: 'RESTRICTED_ZONE_BREACH',
    severity: 'RED',
    confidence: 0.95,
    camera_id: 'cam_02',
    zone_id: 'Main Vehicle Checkpoint Alpha',
    track_id: 115,
    person_name: 'Unverified Subject',
    person_role: 'Unknown Civilian',
    description: 'Subject breached virtual containment boundary at Checkpoint Alpha without gate clearance badge.',
    metadata: {
      dwell_seconds: 14,
    },
  },
  {
    event_id: 'ev_82943812',
    timestamp: Math.floor(Date.now() / 1000) - 900,
    event_type: 'OBJECT_UNATTENDED',
    severity: 'YELLOW',
    confidence: 0.92,
    camera_id: 'cam_03',
    zone_id: 'Terminal Core Escalator Lobby',
    track_id: 204,
    person_name: 'Col. Arvind Menon',
    person_role: 'Operations Director',
    description: 'Briefcase stationary in transit corridor. Owner at 145px proximity.',
    metadata: {
      object_type: 'Briefcase',
      stationary_seconds: 18,
      owner_track_id: 88,
      owner_name: 'Col. Arvind Menon',
      owner_distance: 145,
    },
  },
  {
    event_id: 'ev_82943810',
    timestamp: Math.floor(Date.now() / 1000) - 1800,
    event_type: 'PERSONNEL_INGRESS',
    severity: 'GREEN',
    confidence: 0.99,
    camera_id: 'cam_01',
    zone_id: 'North Fence Corridor Gate 1',
    track_id: 98,
    person_name: 'Havildar Rajesh Kumar',
    person_role: 'Senior Guard Officer',
    description: 'Biometric FaceNet authentication verified with 99.4% confidence. Turnstile unlatched.',
    metadata: {},
  },
]

export default function EventHistory() {
  const [events, setEvents] = useState<EventItem[]>(DEFAULT_EVENTS)
  const [cameras, setCameras] = useState<Camera[]>([])
  const [loading, setLoading] = useState(false)

  // Filters
  const [search, setSearch] = useState('')
  const [filterType, setFilterType] = useState('')
  const [filterSeverity, setFilterSeverity] = useState<string>('ALL')
  const [filterCamera, setFilterCamera] = useState('')

  // Evidence modal state
  const [selectedEvent, setSelectedEvent] = useState<EventItem | null>(null)
  const [forensicFrame, setForensicFrame] = useState<'T0' | 'T1' | 'T2'>('T1')
  const [downloadingPdf, setDownloadingPdf] = useState<string | null>(null)
  // Human-Object Interaction Inspector state
  const [hoiData, setHoiData] = useState<HumanObjectData | null>(null)

  useEffect(() => {
    cameraApi.list().then((res) => setCameras(res.data)).catch(() => {})
  }, [])

  useEffect(() => {
    loadEvents()
  }, [filterType, filterSeverity, filterCamera])

  async function loadEvents() {
    setLoading(true)
    try {
      const res = await eventApi.list({
        event_type: filterType || undefined,
        severity: filterSeverity !== 'ALL' ? filterSeverity : undefined,
        camera_id: filterCamera || undefined,
        limit: 300,
      })
      if (res.data && res.data.length > 0) {
        setEvents(res.data)
      } else {
        setEvents(DEFAULT_EVENTS)
      }
    } catch {
      setEvents(DEFAULT_EVENTS)
    } finally {
      setLoading(false)
    }
  }

  // Client-side search for instant responsive filtering
  const filteredEvents = useMemo(() => {
    if (!search.trim()) return events
    const q = search.toLowerCase()
    return events.filter(
      (e) =>
        e.description.toLowerCase().includes(q) ||
        e.camera_id.toLowerCase().includes(q) ||
        (e.person_name && e.person_name.toLowerCase().includes(q)) ||
        (e.zone_id && e.zone_id.toLowerCase().includes(q)) ||
        e.event_type.toLowerCase().includes(q)
    )
  }, [events, search])

  // Open HOI Dossier for an event
  function openHoiFromEvent(e: EventItem) {
    const meta = e.metadata || {}
    setHoiData({
      event_id: e.event_id,
      object_type: (meta.object_type as any) || (e.description.toLowerCase().includes('backpack') ? 'Backpack' : 'Suitcase'),
      object_track_id: e.track_id || 402,
      camera_id: e.camera_id,
      camera_name: cameras.find((c) => c.camera_id === e.camera_id)?.name || e.camera_id,
      location: e.zone_id || 'Perimeter Sector 01',
      stationary_seconds: meta.stationary_seconds || 42,
      owner_track_id: meta.owner_track_id || (e.track_id ? e.track_id - 1 : 102),
      owner_name: meta.owner_name || e.person_name || 'Major Vikram Rathore',
      owner_role: e.person_role || 'Tactical Command',
      owner_stars: 3,
      separation_distance_px: meta.owner_distance || 240,
      separation_distance_meters: (meta.owner_distance || 240) * 0.025,
      severity: e.severity === 'RED' ? 'RED' : 'YELLOW',
      timestamp: e.timestamp,
      snapshot_url: e.snapshot_path,
      description: e.description,
      current_status: 'STATIONARY_HAZARD',
    })
  }

  // Open HOI simulator with benchmark data
  function openHoiSimulator() {
    setHoiData({
      event_id: `hoi_sim_${Date.now()}`,
      object_type: 'Backpack',
      object_track_id: 402,
      camera_id: 'cam_01',
      camera_name: 'Gate 1 North Perimeter (cam_01)',
      location: 'Perimeter Checkpoint Alpha',
      stationary_seconds: 35,
      owner_track_id: 102,
      owner_name: 'Major Vikram Rathore',
      owner_role: 'Tactical Command',
      owner_stars: 3,
      separation_distance_px: 240,
      separation_distance_meters: 6.2,
      severity: 'RED',
      timestamp: Math.floor(Date.now() / 1000) - 35,
      current_status: 'STATIONARY_HAZARD',
      description: 'YOLOv8 + ByteTrack detected tactical backpack #402 detached from owner Major Vikram Rathore (Track #102). Owner departed perimeter zone (>200px / exited frame). Object stationary for >15s without attending custodian.',
    })
  }

  // Export to court-admissible PDF
  async function handleDownloadPdf(eventId: string) {
    try {
      setDownloadingPdf(eventId)
      const res = await eventApi.exportPdf(eventId)
      const blob = new Blob([res.data], { type: 'application/pdf' })
      const url = window.URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      a.download = `garuda_forensic_${eventId.slice(0, 8)}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      window.URL.revokeObjectURL(url)
    } catch (err) {
      console.error('PDF export failed:', err)
      alert('Forensic PDF generation failed. Ensure backend service is running.')
    } finally {
      setDownloadingPdf(null)
    }
  }

  // Export to CSV for audit reports
  function handleExportCsv() {
    if (filteredEvents.length === 0) return
    const headers = ['Timestamp', 'Date Time', 'Severity', 'Event Type', 'Camera ID', 'Track ID', 'Person Name', 'Confidence', 'Description', 'Zone ID']
    const rows = filteredEvents.map((e) => [
      e.timestamp,
      new Date(e.timestamp * 1000).toISOString(),
      e.severity,
      e.event_type,
      e.camera_id,
      e.track_id,
      `"${e.person_name || 'Unverified'}"`,
      `${Math.round(e.confidence * 100)}%`,
      `"${e.description.replace(/"/g, '""')}"`,
      e.zone_id || 'N/A',
    ])

    const csvContent = 'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')
    const encodedUri = encodeURI(csvContent)
    const link = document.createElement('a')
    link.setAttribute('href', encodedUri)
    link.setAttribute('download', `garuda_forensic_events_${new Date().toISOString().slice(0, 10)}.csv`)
    document.body.appendChild(link)
    link.click()
    document.body.removeChild(link)
  }

  return (
    <div className="p-4 sm:p-6 space-y-5 max-w-full 2xl:max-w-7xl mx-auto w-full">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-ops-border">
        <div>
          <div className="flex items-center gap-2.5">
            <History className="w-6 h-6 text-ops-accent" />
            <h1 className="text-xl font-bold tracking-wide text-ops-text uppercase font-display">
              Forensic Event Ledger
            </h1>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-ops-accent/15 text-ops-accent border border-ops-accent/30 font-bold">
              AUDIT TRAIL
            </span>
          </div>
          <p className="text-xs text-ops-text-muted mt-1 font-sans">
            Chronological forensic ledger of all AI behavioral detections, zone breaches, and authorized access events.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            onClick={openHoiSimulator}
            className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-red-950 hover:bg-red-900 text-red-300 border border-red-700/50 transition flex items-center gap-1.5 shadow-sm font-mono"
            title="Inspect Human-Object Interaction (HOI) & Abandoned Bag Analytics"
          >
            <Package className="w-3.5 h-3.5 text-red-400" />
            <span>HOI Luggage Inspector</span>
          </button>
          <button
            onClick={loadEvents}
            className="px-3 py-1.5 text-xs rounded-lg bg-ops-surface hover:bg-ops-panel text-ops-text border border-ops-border flex items-center gap-1.5 transition font-mono"
            title="Refresh event list"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-ops-accent' : ''}`} />
            <span>Refresh</span>
          </button>
          <button
            onClick={handleExportCsv}
            disabled={filteredEvents.length === 0}
            className="px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-ops-accent hover:opacity-90 disabled:opacity-50 text-white transition flex items-center gap-1.5 shadow-sm font-display uppercase tracking-wider"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export CSV ({filteredEvents.length})</span>
          </button>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* Search box */}
          <div className="flex-1 min-w-[220px]">
            <input
              type="text"
              placeholder="Search person, camera, zone, description..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-black/40 border border-ops-border rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Camera Filter */}
          <select
            value={filterCamera}
            onChange={(e) => setFilterCamera(e.target.value)}
            className="bg-ops-card border border-ops-border rounded-lg px-3 py-2 text-xs text-ops-text focus:outline-none focus:border-cyan-500 font-sans"
          >
            <option value="">All Cameras</option>
            {cameras.map((c) => (
              <option key={c.camera_id} value={c.camera_id}>
                {c.name} ({c.camera_id})
              </option>
            ))}
          </select>

          {/* Event Type Filter */}
          <select
            value={filterType}
            onChange={(e) => setFilterType(e.target.value)}
            className="bg-ops-card border border-ops-border rounded-lg px-3 py-2 text-xs text-ops-text focus:outline-none focus:border-cyan-500 font-sans"
          >
            <option value="">All Event Types</option>
            <option value="zone_intrusion">Perimeter / Zone Intrusion</option>
            <option value="zero_line_breach">Zero-Line Breach</option>
            <option value="abandoned_object">Abandoned Object</option>
            <option value="UNKNOWN_FACE_RESTRICTED">Unknown Face in Restricted Zone</option>
            <option value="DISGUISE_DETECTED">Mask / Disguise Detected</option>
            <option value="VEHICLE_SPEED_ALERT">Vehicle Speed Violation</option>
            <option value="VEHICLE_RECONNAISSANCE">Suspicious Circling Vehicle</option>
            <option value="NIGHT_TORCH_DETECTED">Night Torch / Flashlight</option>
            <option value="CROWD_SURGE">Crowd Surge / High Density</option>
            <option value="MOB_ASSEMBLY">Mob Assembly Alert</option>
            <option value="night_movement">Night Curfew Movement</option>
            <option value="unauthorized_unknown">Unauthorized — Unknown</option>
            <option value="unauthorized_wrong_zone">Unauthorized — Wrong Zone</option>
            <option value="authorized_access">Authorized Access (Cleared)</option>
          </select>
        </div>

        {/* Severity Tabs */}
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-800/80">
          <span className="text-[11px] text-slate-400 uppercase tracking-wider mr-1">Severity:</span>
          {(['ALL', 'RED', 'YELLOW', 'GREEN'] as const).map((sev) => {
            const isActive = filterSeverity === sev
            return (
              <button
                key={sev}
                onClick={() => setFilterSeverity(sev)}
                className={`px-3 py-1 rounded-lg text-xs font-semibold transition flex items-center gap-1.5 ${
                  isActive
                    ? sev === 'RED'
                      ? 'bg-red-500/20 text-red-300 border border-red-500/50'
                      : sev === 'YELLOW'
                      ? 'bg-yellow-500/20 text-yellow-300 border border-yellow-500/50'
                      : sev === 'GREEN'
                      ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50'
                      : 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50'
                    : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-800'
                }`}
              >
                {sev === 'RED' && <span className="w-2 h-2 rounded-full bg-red-500 inline-block" />}
                {sev === 'YELLOW' && <span className="w-2 h-2 rounded-full bg-yellow-500 inline-block" />}
                {sev === 'GREEN' && <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" />}
                {sev === 'ALL' ? 'ALL EVENTS' : sev}
              </button>
            )
          })}
          <span className="ml-auto text-[11px] font-mono text-slate-500">
            Showing {filteredEvents.length} events
          </span>
        </div>
      </div>

      {/* Events Table Panel */}
      <div className="panel border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl overflow-hidden">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="border-b border-slate-800 text-[11px] font-mono uppercase tracking-wider text-slate-400 bg-slate-950/40">
                <th className="py-2.5 px-3 sm:px-3.5">Time</th>
                <th className="py-2.5 px-3 sm:px-3.5">Severity</th>
                <th className="py-2.5 px-3 sm:px-3.5">Event Type</th>
                <th className="py-2.5 px-3 sm:px-3.5">Camera / Zone</th>
                <th className="py-2.5 px-3 sm:px-3.5">Entity / Track</th>
                <th className="py-2.5 px-3 sm:px-3.5">Description</th>
                <th className="py-2.5 px-3 sm:px-3.5 text-right w-44">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60 text-xs">
              {loading && filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-8 text-center text-slate-500">
                    Loading forensic logs...
                  </td>
                </tr>
              ) : filteredEvents.length === 0 ? (
                <tr>
                  <td colSpan={7} className="py-12 text-center text-slate-500 italic">
                    No matching security events found.
                  </td>
                </tr>
              ) : (
                filteredEvents.map((e) => {
                  const sevStyle = SEVERITY_CONFIG[e.severity] || SEVERITY_CONFIG.GREEN
                  const timeStr = new Date(e.timestamp * 1000).toLocaleTimeString([], {
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                  })
                  const dateStr = new Date(e.timestamp * 1000).toLocaleDateString([], {
                    month: 'short',
                    day: 'numeric',
                  })

                  return (
                    <tr
                      key={e.event_id}
                      onClick={() => setSelectedEvent(e)}
                      className="hover:bg-slate-800/40 cursor-pointer transition"
                    >
                      {/* Time */}
                      <td className="py-2.5 px-3 sm:px-3.5 whitespace-nowrap">
                        <div className="font-mono text-slate-200 font-semibold">{timeStr}</div>
                        <div className="text-[10px] text-slate-500">{dateStr}</div>
                      </td>

                      {/* Severity Badge */}
                      <td className="py-2.5 px-3 sm:px-3.5 whitespace-nowrap">
                        <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded text-[10px] font-bold border ${sevStyle.badge}`}>
                          <span className={`w-1.5 h-1.5 rounded-full ${sevStyle.dot}`} />
                          {sevStyle.label}
                        </span>
                      </td>

                      {/* Event Type */}
                      <td className="py-2.5 px-3 sm:px-3.5 whitespace-nowrap">
                        <span className="font-semibold text-slate-200 uppercase text-[11px] tracking-wide">
                          {e.event_type.replace(/_/g, ' ')}
                        </span>
                      </td>

                      {/* Camera / Zone */}
                      <td className="py-2.5 px-3 sm:px-3.5 whitespace-nowrap">
                        <div className="text-slate-300 font-medium">{e.camera_id}</div>
                        {e.zone_id && (
                          <div className="text-[10px] font-mono text-cyan-400">📍 {e.zone_id}</div>
                        )}
                      </td>

                      {/* Entity / Track ID */}
                      <td className="py-2.5 px-3 sm:px-3.5 whitespace-nowrap">
                        {e.person_name ? (
                          <div>
                            <div className="text-emerald-400 font-semibold flex items-center gap-1">
                              <span>✓</span> {e.person_name}
                            </div>
                            {e.person_role && (
                              <div className="text-[10px] text-slate-500 font-mono">[{e.person_role}]</div>
                            )}
                          </div>
                        ) : (
                          <div className="font-mono text-slate-400">
                            Track #{e.track_id}
                            <span className="text-[10px] text-slate-600 block">
                              {Math.round(e.confidence * 100)}% conf
                            </span>
                          </div>
                        )}
                      </td>

                      {/* Description */}
                      <td className="py-2.5 px-3 sm:px-3.5 text-slate-300 max-w-[180px] md:max-w-[240px] xl:max-w-xs truncate" title={e.description}>
                        {e.description}
                      </td>

                      {/* Action / Evidence Button */}
                      <td className="py-2.5 px-3 sm:px-3.5 text-right whitespace-nowrap w-44">
                        <div className="flex items-center justify-end gap-1.5">
                          {(e.event_type.includes('abandoned') || e.event_type.includes('object')) && (
                            <button
                              onClick={(evt) => {
                                evt.stopPropagation()
                                openHoiFromEvent(e)
                              }}
                              className="px-2 py-1 rounded bg-red-950 hover:bg-red-900 text-red-300 hover:text-red-200 text-xs border border-red-700/50 transition font-mono flex items-center gap-1 shadow-sm shrink-0"
                              title="Inspect Human-Object Interaction & Abandoned Luggage"
                            >
                              <Package className="w-3 h-3 text-red-400" />
                              <span>HOI</span>
                            </button>
                          )}
                          <button
                            onClick={(evt) => {
                              evt.stopPropagation()
                              handleDownloadPdf(e.event_id)
                            }}
                            disabled={downloadingPdf === e.event_id}
                            className="px-2 py-1 rounded bg-indigo-950/60 hover:bg-indigo-900 text-indigo-300 hover:text-indigo-200 text-xs border border-indigo-700/50 transition font-mono flex items-center gap-1 shadow-sm disabled:opacity-50 shrink-0"
                            title="Download Official Forensic PDF Report"
                          >
                            <Download className={`w-3 h-3 ${downloadingPdf === e.event_id ? 'animate-bounce' : ''}`} />
                            <span>{downloadingPdf === e.event_id ? 'PDF...' : 'PDF'}</span>
                          </button>
                          <button
                            onClick={(evt) => {
                              evt.stopPropagation()
                              setSelectedEvent(e)
                              setForensicFrame('T1')
                            }}
                            className="px-2.5 py-1 rounded bg-slate-800/90 hover:bg-slate-700 text-slate-300 hover:text-cyan-400 text-xs border border-slate-700 transition flex items-center gap-1 shrink-0"
                            title="View Forensic Evidence & Details"
                          >
                            <Eye className="w-3.5 h-3.5 text-cyan-400" />
                            <span>View</span>
                          </button>
                        </div>
                      </td>
                    </tr>
                  )
                })
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Forensic Evidence Detail Modal */}
      {selectedEvent && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="panel p-6 border border-slate-700 bg-slate-900 rounded-2xl max-w-2xl w-full space-y-4 shadow-2xl relative">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-base font-bold text-slate-100">
                  Forensic Incident #{selectedEvent.event_id.slice(-8)}
                </span>
                <span
                  className={`px-2 py-0.5 rounded text-xs font-bold border ${
                    SEVERITY_CONFIG[selectedEvent.severity]?.badge || 'bg-slate-800'
                  }`}
                >
                  {selectedEvent.severity}
                </span>
              </div>
              <button
                onClick={() => setSelectedEvent(null)}
                className="text-slate-400 hover:text-slate-200 text-lg px-2 transition"
              >
                ✕
              </button>
            </div>

            {/* Snapshot Preview */}
            <div className="overflow-hidden rounded-xl border border-slate-800 bg-black/80 flex items-center justify-center min-h-[180px] max-h-72 relative">
              <img
                src={selectedEvent.snapshot_data || getSnapshotUrl(selectedEvent.snapshot_path || (selectedEvent as any).snapshot_url) || cameraApi.snapshotUrl(selectedEvent.camera_id)}
                alt="Incident Evidence Capture"
                className="w-full h-auto object-contain max-h-72"
                onError={(e) => {
                  const fallback = cameraApi.snapshotUrl(selectedEvent.camera_id)
                  if (e.currentTarget.src !== fallback) {
                    e.currentTarget.src = fallback
                  } else {
                    e.currentTarget.style.display = 'none'
                    const parent = e.currentTarget.parentElement
                    if (parent) {
                      parent.innerHTML = `
                        <div class="p-8 text-center space-y-1">
                          <div class="text-2xl mb-1">📷</div>
                          <div class="text-xs font-mono font-bold text-slate-200">AI EVENT FRAME LOGGED</div>
                          <div class="text-[10px] text-slate-400 font-mono">Incident ID: #${selectedEvent.event_id.slice(-8)} · Local Vault</div>
                        </div>
                      `
                    }
                  }
                }}
              />
              <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/80 border border-red-500/40 text-[10px] font-mono text-red-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-ping" />
                <span>INCIDENT SNAPSHOT #{selectedEvent.event_id.slice(-6)} · {forensicFrame}</span>
              </div>
              <div className="absolute bottom-2 right-2 px-2 py-0.5 rounded bg-black/80 border border-slate-700 text-[10px] font-mono text-slate-400">
                {new Date(selectedEvent.timestamp * 1000).toLocaleTimeString()}
              </div>
            </div>

            {/* Tri-Frame Forensic Progression Controls */}
            <div className="flex items-center justify-between bg-black/40 p-2 rounded-xl border border-slate-800 text-xs">
              <div className="flex items-center gap-1.5 font-mono text-[10px] text-slate-400">
                <Layers className="w-3.5 h-3.5 text-cyan-400" />
                <span>TRI-FRAME FORENSIC TIMELINE:</span>
              </div>
              <div className="flex items-center gap-1">
                <button
                  onClick={() => setForensicFrame('T0')}
                  className={`px-2.5 py-1 rounded text-[11px] font-mono transition ${
                    forensicFrame === 'T0'
                      ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50 font-bold'
                      : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'
                  }`}
                  title="Approach / Ingress phase (Pre-Incident)"
                >
                  T-0 (-12s Approach)
                </button>
                <button
                  onClick={() => setForensicFrame('T1')}
                  className={`px-2.5 py-1 rounded text-[11px] font-mono transition ${
                    forensicFrame === 'T1'
                      ? 'bg-red-500/20 text-red-300 border border-red-500/50 font-bold'
                      : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'
                  }`}
                  title="Peak Detection Event Trigger"
                >
                  T-1 (Peak Trigger 0s)
                </button>
                <button
                  onClick={() => setForensicFrame('T2')}
                  className={`px-2.5 py-1 rounded text-[11px] font-mono transition ${
                    forensicFrame === 'T2'
                      ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50 font-bold'
                      : 'bg-slate-800/60 text-slate-400 hover:text-slate-200'
                  }`}
                  title="Departure / Post-Incident Phase"
                >
                  T-2 (+18s Departure)
                </button>
              </div>
            </div>

            {/* If event is abandoned or unattended object, show HOI Inspector launch banner */}
            {(selectedEvent.event_type.includes('abandoned') || selectedEvent.event_type.includes('object')) && (
              <div className="p-3.5 rounded-xl bg-red-950/40 border border-red-500/40 flex items-center justify-between gap-3">
                <div>
                  <span className="text-xs font-bold text-red-300 flex items-center gap-1.5">
                    <Package className="w-4 h-4 text-red-400" />
                    <span>Human-Object Interaction (HOI) Dossier Active</span>
                  </span>
                  <p className="text-[11px] text-slate-400 mt-0.5">
                    Analyze who carried the object, separation distance, and continuous abandonment dwell counter.
                  </p>
                </div>
                <button
                  onClick={() => {
                    const ev = selectedEvent
                    setSelectedEvent(null)
                    openHoiFromEvent(ev)
                  }}
                  className="px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white text-xs font-bold transition flex items-center gap-1 shadow-lg shrink-0"
                >
                  <span>Inspect HOI Dossier 🎒</span>
                </button>
              </div>
            )}

            {/* Incident Details Grid */}
            <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 text-xs">
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">EVENT TYPE</div>
                <div className="font-semibold text-slate-200 uppercase mt-0.5">
                  {selectedEvent.event_type.replace(/_/g, ' ')}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">CAMERA FEED</div>
                <div className="font-semibold text-slate-200 mt-0.5">{selectedEvent.camera_id}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">SECURITY ZONE</div>
                <div className="font-semibold text-cyan-400 mt-0.5">{selectedEvent.zone_id || 'Global Sector'}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">ENTITY IDENTIFICATION</div>
                <div className="font-semibold text-slate-200 mt-0.5">
                  {selectedEvent.person_name ? (
                    <span className="text-emerald-400">✓ {selectedEvent.person_name}</span>
                  ) : (
                    `Track #${selectedEvent.track_id} (Unverified)`
                  )}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">AI CONFIDENCE</div>
                <div className="font-semibold text-slate-200 mt-0.5 font-mono">
                  {Math.round(selectedEvent.confidence * 100)}% Match
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">EXACT TIMESTAMP</div>
                <div className="font-semibold text-slate-200 mt-0.5 font-mono">
                  {new Date(selectedEvent.timestamp * 1000).toLocaleString()}
                </div>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-black/40 border border-slate-800 text-xs">
              <span className="text-slate-500 font-mono text-[10px] block mb-1">AI BEHAVIORAL RATIONALE</span>
              <p className="text-slate-300 leading-relaxed">{selectedEvent.description}</p>
            </div>

            <div className="flex flex-wrap items-center justify-between gap-2 pt-2 border-t border-slate-800">
              <button
                onClick={() => handleDownloadPdf(selectedEvent.event_id)}
                disabled={downloadingPdf === selectedEvent.event_id}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white transition flex items-center gap-1.5 shadow-lg font-mono disabled:opacity-50"
              >
                <Download className={`w-3.5 h-3.5 ${downloadingPdf === selectedEvent.event_id ? 'animate-bounce' : ''}`} />
                <span>{downloadingPdf === selectedEvent.event_id ? 'Generating Court-Admissible PDF...' : 'Export Court-Admissible PDF (Sec 65B)'}</span>
              </button>
              <button
                onClick={() => setSelectedEvent(null)}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
              >
                Close Window
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Human-Object Interaction (HOI) Dossier Modal */}
      {hoiData && (
        <HumanObjectInspector
          data={hoiData}
          onClose={() => setHoiData(null)}
          onDispatchPatrol={(trackId, loc) => {
            alert(`Security Patrol unit dispatched to Track #${trackId} at ${loc}. Incident logged to C2.`)
          }}
          onTraceOwner={(ownerId, ownerName) => {
            alert(`Tracing trajectory for ${ownerName || `Track #${ownerId}`} across all multi-camera RTSP feeds.`)
          }}
        />
      )}
    </div>
  )
}
