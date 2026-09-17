import React, { useEffect, useState, useRef } from 'react'
import {
  cameraApi,
  alertApi,
  vehicleApi,
  connectEventSocket,
  getSnapshotUrl,
  Camera,
  Alert,
  AnprDetection
} from '../services/api'
import { SecurityBreachModal, SecurityBreachDossier } from '../components/SecurityBreachModal'
import {
  Camera as CameraIcon,
  CheckCircle2,
  AlertTriangle,
  AlertCircle,
  ShieldAlert,
  Car,
  User,
  RefreshCw,
  Maximize2,
  Activity,
  Clock,
  X,
  ShieldCheck,
  Copy,
  Trash2,
  Radio,
  FileText,
  MapPin,
  ExternalLink,
  ChevronRight,
  Shield,
  Sparkles,
  Download,
  Play,
  Square,
  Crosshair,
  Sun,
  Layers,
  Siren,
  RotateCw,
} from 'lucide-react'

// 4-Level Severity Scheme
export type ActivitySeverity = 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED'

interface SeverityStyle {
  label: string
  bg: string
  text: string
  border: string
  badgeBg: string
  icon: React.ComponentType<{ className?: string }>
}

const SEVERITY_CONFIG: Record<string, SeverityStyle> = {
  GREEN: {
    label: 'NORMAL',
    bg: 'bg-emerald-500/10 dark:bg-emerald-500/10',
    text: 'text-emerald-600 dark:text-emerald-400',
    border: 'border-emerald-500/30',
    badgeBg: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
    icon: CheckCircle2,
  },
  YELLOW: {
    label: 'ATTENTION',
    bg: 'bg-amber-500/10 dark:bg-amber-500/10',
    text: 'text-amber-600 dark:text-amber-400',
    border: 'border-amber-500/30',
    badgeBg: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
    icon: AlertCircle,
  },
  ORANGE: {
    label: 'SUSPICIOUS',
    bg: 'bg-orange-500/10 dark:bg-orange-500/10',
    text: 'text-orange-600 dark:text-orange-400',
    border: 'border-orange-500/30',
    badgeBg: 'bg-orange-500/15 text-orange-600 dark:text-orange-400 border-orange-500/30',
    icon: AlertTriangle,
  },
  RED: {
    label: 'HIGH THREAT',
    bg: 'bg-red-500/10 dark:bg-red-500/10',
    text: 'text-red-600 dark:text-red-400',
    border: 'border-red-500/40',
    badgeBg: 'bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/40',
    icon: ShieldAlert,
  },
  LOW: {
    label: 'NORMAL',
    bg: 'bg-emerald-500/10',
    text: 'text-emerald-600 dark:text-emerald-400',
    border: 'border-emerald-500/30',
    badgeBg: 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30',
    icon: CheckCircle2,
  },
  MEDIUM: {
    label: 'ATTENTION',
    bg: 'bg-amber-500/10',
    text: 'text-amber-600 dark:text-amber-400',
    border: 'border-amber-500/30',
    badgeBg: 'bg-amber-500/15 text-amber-600 dark:text-amber-400 border-amber-500/30',
    icon: AlertCircle,
  },
  HIGH: {
    label: 'HIGH THREAT',
    bg: 'bg-red-500/10',
    text: 'text-red-600 dark:text-red-400',
    border: 'border-red-500/40',
    badgeBg: 'bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/40',
    icon: ShieldAlert,
  },
}

interface HumanActivityItem {
  track_id: number
  camera_id: string
  location?: string
  current_zone?: string
  activity: string
  severity: ActivitySeverity
  risk_score: number
  last_updated: number
  person_name?: string
  person_role?: string
  display_name?: string
}

export default function Dashboard() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [alerts, setAlerts] = useState<Alert[]>([])
  const [activeHumans, setActiveHumans] = useState<HumanActivityItem[]>([])
  const [selectedAlert, setSelectedAlert] = useState<Alert | null>(null)
  const [fullscreenCamera, setFullscreenCamera] = useState<string | null>(null)
  const [timeline, setTimeline] = useState<{ time: string; text: string; severity: string }[]>([])
  const [riskStats, setRiskStats] = useState({ green: 0, yellow: 0, orange: 0, red: 0 })
  const [initialLoading, setInitialLoading] = useState<boolean>(true)
  const wsRef = useRef<WebSocket | null>(null)

  // Side log & ANPR states
  const [sideTab, setSideTab] = useState<'humans' | 'vehicles'>('humans')
  const [anprDetections, setAnprDetections] = useState<AnprDetection[]>([])
  const [selectedAnpr, setSelectedAnpr] = useState<AnprDetection | null>(null)
  const [newVehicleAlert, setNewVehicleAlert] = useState<string | null>(null)
  const [anprFilter, setAnprFilter] = useState<'ALL' | 'AUTHORIZED' | 'WATCHLIST'>('ALL')
  const [resetting, setResetting] = useState<boolean>(false)
  const [learningFeedbackToast, setLearningFeedbackToast] = useState<string | null>(null)
  const [downloadingPdf, setDownloadingPdf] = useState<string | null>(null) // alert_id being downloaded
  const [demoMode, setDemoMode] = useState<boolean>(false)  // Demo / Presentation mode
  const [voiceEnabled, setVoiceEnabled] = useState<boolean>(false) // Voice alerts via SpeechSynthesis
  const voiceCooldownRef = useRef<number>(0) // prevent rapid-fire voice alerts
  const voiceEnabledRef = useRef<boolean>(false) // mirror of voiceEnabled for stable callbacks
  voiceEnabledRef.current = voiceEnabled // keep ref in sync on every render

  // Tactical Sniper & Precision Mode States
  const [alertForensicFrame, setAlertForensicFrame] = useState<'T0' | 'T1' | 'T2'>('T1')
  const [sniperZoom, setSniperZoom] = useState<number>(1)
  const [sniperCrosshair, setSniperCrosshair] = useState<boolean>(true)
  const [sniperFilter, setSniperFilter] = useState<'NORMAL' | 'THERMAL' | 'NIGHT'>('NORMAL')
  const [sniperSpotlight, setSniperSpotlight] = useState<boolean>(false)

  // Security Breach Dossier Modal State (e-Challan Style Evidence Capture)
  const [showBreachModal, setShowBreachModal] = useState<boolean>(false)
  const [activeBreach, setActiveBreach] = useState<SecurityBreachDossier | null>(null)
  const [latestBreaches, setLatestBreaches] = useState<SecurityBreachDossier[]>([])

  async function fetchLatestBreaches() {
    try {
      const res = await fetch('/api/breaches/list?limit=10')
      if (res.ok) {
        const data = await res.json()
        setLatestBreaches(data.breaches || [])
        if (data.breaches && data.breaches.length > 0 && !activeBreach) {
          setActiveBreach(data.breaches[0])
        }
      }
    } catch (err) {
      console.warn('Failed to load breach dossiers:', err)
    }
  }

  async function handleResetLogs() {
    try {
      setResetting(true)
      await alertApi.clear()
    } catch {
      // offline fallback
    } finally {
      setAlerts([])
      setActiveHumans([])
      setAnprDetections([])
      setTimeline([])
      setRiskStats({ green: 0, yellow: 0, orange: 0, red: 0 })
      setNewVehicleAlert(null)
      setSelectedAlert(null)
      setSelectedAnpr(null)
      setResetting(false)
    }
  }

  async function handleToggleAi(cameraId: string) {
    try {
      const res = await cameraApi.toggleAi(cameraId)
      setCameras(prev => prev.map(c => c.camera_id === cameraId ? { ...c, ai_enabled: res.data.ai_enabled } : c))
    } catch (err) {
      console.error('Failed to toggle camera AI mode', err)
    }
  }

  async function handleRotateCamera(cameraId: string) {
    try {
      const res = await cameraApi.rotate(cameraId)
      setCameras(prev => prev.map(c => c.camera_id === cameraId ? { ...c, rotation: res.data.rotation } : c))
    } catch (err) {
      console.error('Failed to rotate camera', err)
    }
  }

  async function handleDownloadPdf(alertId: string) {
    setDownloadingPdf(alertId)
    try {
      const token = localStorage.getItem('token') || ''
      const res = await fetch(`/api/alerts/${alertId}/pdf`, {
        headers: { Authorization: `Bearer ${token}` }
      })
      if (!res.ok) throw new Error(`HTTP ${res.status}`)
      const blob = await res.blob()
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url
      const cd = res.headers.get('Content-Disposition') || ''
      const fnMatch = cd.match(/filename="([^"]+)"/) 
      a.download = fnMatch ? fnMatch[1] : `garuda_incident_${alertId.slice(0, 8)}.pdf`
      document.body.appendChild(a)
      a.click()
      document.body.removeChild(a)
      URL.revokeObjectURL(url)
    } catch (e) {
      console.error('PDF download failed:', e)
    } finally {
      setDownloadingPdf(null)
    }
  }

  function speakAlert(text: string, severity: string) {
    if (!voiceEnabledRef.current) return
    if (!('speechSynthesis' in window)) return
    const now = Date.now()
    if (now - voiceCooldownRef.current < 8000) return // max 1 voice alert per 8s
    voiceCooldownRef.current = now
    window.speechSynthesis.cancel()
    const utterance = new SpeechSynthesisUtterance()
    utterance.rate = 1.0
    utterance.pitch = severity === 'RED' ? 1.3 : 1.0
    utterance.volume = 1.0
    // Strip emoji / non-ASCII characters for clean speech output
    const cleaned = text.replace(/[^\x00-\x7F]/g, ' ').replace(/\s+/g, ' ').trim().slice(0, 120)

    utterance.text = severity === 'RED'
      ? `Critical alert. ${cleaned}`
      : `Warning. ${cleaned}`
    window.speechSynthesis.speak(utterance)
  }

  useEffect(() => {
    loadData().finally(() => setInitialLoading(false))
    fetchLatestBreaches()
    const ws = connectEventSocket((msg) => {
      if (msg.type === 'new_alert') {
        const alert = msg.data
        setAlerts((prev) => [alert, ...prev.filter(a => a.alert_id !== alert.alert_id)].slice(0, 50))
        addTimelineEntry(alert.description, alert.severity)
        updateActiveHuman(alert)
        // Check for attached automated e-Challan / breach dossier
        if (alert.metadata?.evidence_package) {
          const ep = alert.metadata.evidence_package
          const newDossier: SecurityBreachDossier = {
            breach_id: ep.breach_id,
            timestamp: ep.timestamp || Date.now() / 1000,
            camera_id: ep.camera_id,
            camera_name: ep.camera_name,
            zone_id: ep.zone_id,
            zone_name: ep.zone_name,
            breach_type: ep.breach_type,
            target_class: ep.target_class,
            quality_score: ep.quality_score,
            evidence_hash: ep.evidence_hash,
            wide_frame_url: ep.crops?.wide_context_url,
            face_crop_url: ep.crops?.face_crop_url,
            plate_crop_url: ep.crops?.plate_crop_url,
            matched_identity: ep.subject_profile?.matched_name,
            plate_number: ep.vehicle_profile?.plate_number,
            status: 'CAPTURED',
          }
          setLatestBreaches(prev => [newDossier, ...prev.filter(b => b.breach_id !== newDossier.breach_id)])
          setActiveBreach(newDossier)
        }
        // Voice alert for high-priority events
        if (alert.severity === 'RED' || alert.severity === 'ORANGE') {
          speakAlert(alert.description, alert.severity)
        }
      } else if (msg.type === 'new_anpr_detection') {
        const anpr: AnprDetection = msg.data
        setAnprDetections((prev) => {
          const filtered = prev.filter(p => p.detection_id !== anpr.detection_id)
          return [anpr, ...filtered].slice(0, 50)
        })

        const isAuth = anpr.status === 'CLEARED' || anpr.status === 'REGISTERED' || !!anpr.owner_name
        const isThreat = anpr.status === 'WATCHLIST'

        if (isThreat) {
          addTimelineEntry(`Watchlist Vehicle: ${anpr.plate_number} at ${anpr.camera_name || anpr.camera_id}`, 'RED')
          setNewVehicleAlert(`WATCHLIST HIT: ${anpr.plate_number}`)
        } else if (isAuth) {
          addTimelineEntry(`Authorized Vehicle: ${anpr.plate_number} (${anpr.owner_name || 'Staff'})`, 'GREEN')
          setNewVehicleAlert(`Cleared: ${anpr.plate_number} (${anpr.owner_name || 'Authorized'})`)
        } else {
          addTimelineEntry(`Vehicle Log: ${anpr.plate_number} at ${anpr.camera_name || anpr.camera_id}`, 'YELLOW')
        }
      }
    })

    wsRef.current = ws
    const interval = setInterval(() => {
      loadData()
      fetchLatestBreaches()
    }, 15000)
    return () => {
      ws.close()
      clearInterval(interval)
    }
  }, [])

  // Global Keyboard shortcuts: 'S' for Sniper Mode, 'Escape' to exit
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if (['INPUT', 'TEXTAREA', 'SELECT'].includes((e.target as HTMLElement)?.tagName)) return
      if (e.key === 's' || e.key === 'S') {
        setFullscreenCamera((prev) => {
          if (prev) {
            setSniperZoom(1)
            return null
          }
          return cameras.length > 0 ? cameras[0].camera_id : null
        })
      } else if (e.key === 'Escape') {
        setFullscreenCamera(null)
        setSniperZoom(1)
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [cameras])

  function addTimelineEntry(text: string, severity: string = 'GREEN') {
    const time = new Date().toLocaleTimeString()
    setTimeline((prev) => [{ time, text, severity }, ...prev].slice(0, 50))
  }

  function updateActiveHuman(alert: Alert) {
    if (alert.track_id && alert.track_id > 0) {
      const eventType = (alert.event_type || '').toLowerCase()
      const desc = (alert.description || '').toLowerCase()
      const isVehicleEvent = (
        eventType.startsWith('vehicle_') ||
        eventType === 'watchlist_vehicle' ||
        eventType === 'unauthorized_driver' ||
        eventType === 'prolonged_parking' ||
        eventType === 'unauthorized_parking' ||
        !!alert.metadata?.vehicle_type ||
        desc.includes('vehicle speed alert') ||
        desc.includes('vehicle reconnaissance') ||
        desc.includes('car#') ||
        desc.includes('truck#')
      )
      if (isVehicleEvent) {
        return
      }

      const sev = (alert.severity as ActivitySeverity) || 'YELLOW'
      const personName = alert.person_name || alert.metadata?.person_name
      const personRole = alert.person_role || alert.metadata?.person_role
      const displayName = alert.display_name || alert.metadata?.display_name || (personName ? `${personName}` : `Person #${alert.track_id}`)
      const item: HumanActivityItem = {
        track_id: alert.track_id,
        camera_id: alert.camera_id,
        location: alert.location,
        current_zone: alert.zone_id || (alert.event_type === 'authorized_access' ? 'Verified Clearance' : 'Monitored Area'),
        activity: alert.description,
        severity: sev,
        risk_score: (alert as any).risk_score !== undefined ? (alert as any).risk_score : (sev === 'RED' ? 85 : sev === 'ORANGE' ? 60 : sev === 'GREEN' ? 0 : 35),
        last_updated: alert.timestamp,
        person_name: personName,
        person_role: personRole,
        display_name: displayName,
      }
      setActiveHumans(prev => {
        const filtered = prev.filter(h => h.track_id !== alert.track_id)
        return [item, ...filtered].slice(0, 15)
      })
    }
  }

  async function loadData() {
    try {
      const [camRes, alertRes, anprRes] = await Promise.all([
        cameraApi.list(),
        alertApi.list('NEW'),
        vehicleApi.detections(50).catch(() => ({ data: [] }))
      ])
      setCameras(camRes.data)
      setAlerts(alertRes.data)
      if (anprRes?.data) {
        setAnprDetections(anprRes.data)
      }

      let g = 0, y = 0, o = 0, r = 0
      alertRes.data.forEach(a => {
        const s = a.severity?.toUpperCase()
        if (s === 'RED' || s === 'HIGH') r++
        else if (s === 'ORANGE') o++
        else if (s === 'YELLOW' || s === 'MEDIUM') y++
        else g++
      })
      setRiskStats({ green: g, yellow: y, orange: o, red: r })
    } catch { /* graceful degradation */ }
  }

  async function handleAlertAction(id: string, status: string) {
    await alertApi.update(id, status)
    setAlerts((prev) => prev.filter((a) => a.alert_id !== id))
    if (selectedAlert?.alert_id === id) setSelectedAlert(null)

    if (status === 'FALSE_POSITIVE') {
      setLearningFeedbackToast('🧠 Active Learning: False alarm flagged. Sector sensitivity threshold auto-calibrated.')
      setTimeout(() => setLearningFeedbackToast(null), 4500)
    } else if (status === 'RESOLVED') {
      setLearningFeedbackToast('🎯 Active Learning: Verified threat reinforced for continuous campus model adaptation.')
      setTimeout(() => setLearningFeedbackToast(null), 4500)
    }
  }

  if (initialLoading && cameras.length === 0) {
    return (
      <div className="p-8 h-full flex flex-col items-center justify-center bg-ops-bg text-ops-text">
        <div className="flex flex-col items-center max-w-md text-center">
          <div className="relative w-20 h-20 mb-6">
            <div className="absolute inset-0 rounded-full border-2 border-ops-accent/20 animate-ping" />
            <div className="absolute inset-2 rounded-full border-2 border-t-ops-accent border-r-transparent border-b-ops-accent/50 border-l-transparent animate-spin" />
            <div className="absolute inset-0 flex items-center justify-center">
              <Radio className="w-8 h-8 text-ops-accent animate-pulse" />
            </div>
          </div>
          <h2 className="text-sm font-bold tracking-widest uppercase mb-1 font-display text-ops-text">
            Synchronizing Command Core
          </h2>
          <p className="text-xs text-ops-text-muted mb-4">
            Connecting to video intelligence stream, virtual defense zones, and neural tracking engine...
          </p>
          <div className="w-48 h-1 bg-ops-border rounded-full overflow-hidden">
            <div className="w-full h-full bg-ops-accent animate-pulse" />
          </div>
        </div>
      </div>
    )
  }

  return (
    <div className="p-3 sm:p-4 h-full max-h-full overflow-hidden flex flex-col gap-2.5 sm:gap-3 bg-ops-bg text-ops-text">
      {/* Status KPI Banner */}
      <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 shrink-0">
        {/* Active Cameras */}
        <div className="tactical-panel px-3.5 py-2.5 rounded-lg flex items-center justify-between border-l-4 border-l-ops-accent">
          <div>
            <div className="text-[11px] text-ops-text-muted font-medium">
              Cameras Online
            </div>
            <div className="text-xl font-bold text-ops-text mt-0.5 leading-none">
              {cameras.filter(c => c.status === 'ONLINE').length} / {cameras.length}
            </div>
          </div>
          <div className="w-8 h-8 rounded-lg bg-ops-accent/15 border border-ops-accent/30 flex items-center justify-center">
            <CameraIcon className="w-4 h-4 text-ops-accent" />
          </div>
        </div>

        {/* Normal */}
        <div className="tactical-panel px-3.5 py-2.5 rounded-lg flex items-center justify-between border-l-4 border-l-emerald-500">
          <div>
            <div className="text-[11px] text-ops-text-muted font-medium flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-500" />
              Cleared
            </div>
            <div className="text-xl font-bold text-emerald-500 mt-0.5 leading-none">{riskStats.green}</div>
          </div>
          <span className="text-[10px] font-medium bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border border-emerald-500/25 px-2 py-0.5 rounded">
            Safe
          </span>
        </div>

        {/* Attention */}
        <div className="tactical-panel px-3.5 py-2.5 rounded-lg flex items-center justify-between border-l-4 border-l-amber-500">
          <div>
            <div className="text-[11px] text-ops-text-muted font-medium flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-amber-500" />
              Watch
            </div>
            <div className="text-xl font-bold text-amber-500 mt-0.5 leading-none">{riskStats.yellow}</div>
          </div>
          <span className="text-[10px] font-medium bg-amber-500/10 text-amber-600 dark:text-amber-400 border border-amber-500/25 px-2 py-0.5 rounded">
            Monitor
          </span>
        </div>

        {/* Suspicious */}
        <div className="tactical-panel px-3.5 py-2.5 rounded-lg flex items-center justify-between border-l-4 border-l-orange-500">
          <div>
            <div className="text-[11px] text-ops-text-muted font-medium flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-orange-500" />
              Suspicious
            </div>
            <div className="text-xl font-bold text-orange-500 mt-0.5 leading-none">{riskStats.orange}</div>
          </div>
          <span className="text-[10px] font-medium bg-orange-500/10 text-orange-600 dark:text-orange-400 border border-orange-500/25 px-2 py-0.5 rounded">
            Review
          </span>
        </div>

        {/* High Alert */}
        <div className="tactical-panel px-3.5 py-2.5 rounded-lg flex items-center justify-between border-l-4 border-l-red-500 col-span-2 sm:col-span-1">
          <div>
            <div className="text-[11px] text-ops-text-muted font-medium flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-pulse" />
              High Alert
            </div>
            <div className="text-xl font-bold text-red-500 mt-0.5 leading-none">{riskStats.red}</div>
          </div>
          <span className="text-[10px] font-semibold bg-red-500/10 text-red-600 dark:text-red-400 border border-red-500/25 px-2 py-0.5 rounded">
            Urgent
          </span>
        </div>
      </div>

      {/* Main Center Area: Camera Feeds & Activity Monitor */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-2.5 sm:gap-3 flex-1 min-h-0 overflow-hidden">
        {/* SUB-PART 1: Surveillance Live Grid (7 Cols) */}
        <div className="lg:col-span-7 tactical-panel hud-corner p-3.5 rounded-xl flex flex-col min-h-0 h-full overflow-hidden relative">

          <div className="flex items-center justify-between mb-2 pb-2 border-b border-ops-border shrink-0">
            <div className="text-xs font-semibold flex items-center gap-2 text-ops-text">
              <CameraIcon className="w-4 h-4 text-ops-accent" />
              <span>Live Camera Feeds</span>
              <span className="flex h-1.5 w-1.5 rounded-full bg-emerald-500 animate-pulse" />
            </div>
            <div className="flex items-center gap-2">
              {/* Voice Alert Toggle */}
              <button
                onClick={() => setVoiceEnabled(v => !v)}
                className={`px-2.5 py-1 border rounded text-[11px] font-medium flex items-center gap-1.5 transition-all active:scale-95 ${
                  voiceEnabled
                    ? 'bg-indigo-600/20 border-indigo-500/40 text-indigo-400 hover:bg-indigo-600/30'
                    : 'bg-ops-surface border-ops-border text-ops-text-muted hover:text-indigo-400'
                }`}
                title={voiceEnabled ? "Voice alerts enabled" : "Enable voice alerts"}
              >
                🔊 {voiceEnabled ? 'Voice On' : 'Voice Off'}
              </button>
              {/* Security Breach Dossier Button (e-Challan Evidence System) */}
              <button
                onClick={() => {
                  fetchLatestBreaches()
                  setShowBreachModal(true)
                }}
                className="px-2.5 py-1 bg-red-500/15 hover:bg-red-500/25 border border-red-500/40 text-red-400 hover:text-red-300 rounded text-[11px] font-semibold flex items-center gap-1.5 transition-all shadow-sm active:scale-95"
                title="Open Security Breach Dossier & Automated Evidence Capture"
              >
                <ShieldAlert className="w-3 h-3 text-red-400" />
                <span>Breach Dossier</span>
                {latestBreaches.length > 0 && (
                  <span className="px-1.5 py-0.2 bg-red-600 text-white rounded-full text-[9px] font-mono font-bold">
                    {latestBreaches.length}
                  </span>
                )}
              </button>
              {/* Demo Mode Toggle */}
              <button
                onClick={() => setDemoMode(d => !d)}
                className={`px-2.5 py-1 border rounded text-[11px] font-medium flex items-center gap-1.5 transition-all active:scale-95 ${
                  demoMode
                    ? 'bg-amber-500/20 border-amber-500/40 text-amber-400 animate-pulse'
                    : 'bg-ops-surface border-ops-border text-ops-text-muted hover:text-amber-400'
                }`}
                title={demoMode ? "Demo mode active" : "Start demo mode"}
              >
                <Play className="w-2.5 h-2.5" />
                {demoMode ? 'Demo On' : 'Demo'}
              </button>
              <button
                onClick={handleResetLogs}
                disabled={resetting}
                className="px-2.5 py-1 bg-ops-surface hover:bg-red-500/10 text-ops-text-muted hover:text-red-500 border border-ops-border hover:border-red-500/30 rounded text-[11px] font-medium flex items-center gap-1.5 transition-all active:scale-95"
                title="Clear all logs and alerts"
              >
                <RefreshCw className={`w-3 h-3 ${resetting ? 'animate-spin text-red-400' : ''}`} />
                <span>{resetting ? 'Clearing…' : 'Reset'}</span>
              </button>
            </div>
          </div>

          {/* Demo Mode Banner Overlay */}
          {demoMode && (
            <div className="absolute inset-0 z-10 pointer-events-none flex items-end justify-center pb-3">
              <div className="bg-amber-500/90 text-black text-[11px] font-mono font-bold px-4 py-1.5 rounded-full shadow-lg tracking-widest uppercase animate-pulse border border-amber-300">
                ⚠ DEMONSTRATION MODE — NOT OPERATIONAL DATA ⚠
              </div>
            </div>
          )}


          {/* Sub-Part 1 Dedicated Scroll Container */}
          <div className="flex-1 min-h-0 overflow-y-auto pr-1">
            {cameras.length === 0 ? (
              <div className="h-full min-h-[220px] flex flex-col items-center justify-center text-ops-text-muted text-xs py-8">
                <CameraIcon className="w-8 h-8 mb-2 opacity-40" />
                <span>No active surveillance nodes connected</span>
                <span className="text-[10px] text-ops-text-muted/70 mt-1">Configure devices in Device & Sensor Management</span>
              </div>
            ) : (
              <div className={`grid gap-2.5 content-start auto-rows-max ${
                cameras.length === 1
                  ? 'grid-cols-1 max-w-xl mx-auto'
                  : 'grid-cols-1 sm:grid-cols-2'
              }`}>
                {cameras.map((cam) => (
                  <div
                    key={cam.camera_id}
                    onClick={() => setFullscreenCamera(cam.camera_id)}
                    className="relative border border-ops-border rounded-lg overflow-hidden bg-slate-950 hover:border-ops-accent cursor-pointer group flex flex-col h-fit transition-all shadow-sm hover:shadow-glow-cyan"
                  >
                    <div className="relative overflow-hidden bg-black aspect-video flex items-center justify-center">
                      <img
                        src={cameraApi.streamUrl(cam.camera_id)}
                        alt={cam.name}
                        className="w-full h-full object-cover transition-transform duration-300 group-hover:scale-105"
                        onError={(e) => {
                          e.currentTarget.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjI0MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjMTEyMjMzIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJtb25vc3BhY2UiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM2NjgiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj5DYW1lcmEgT2ZmbGluZTwvdGV4dD48L3N2Zz4='
                        }}
                      />

                      {/* Corner Reticle Brackets */}
                      <div className="absolute top-2 left-2 pointer-events-none w-3 h-3 border-t-2 border-l-2 border-ops-accent/60 group-hover:border-ops-accent" />
                      <div className="absolute top-2 right-2 pointer-events-none w-3 h-3 border-t-2 border-r-2 border-ops-accent/60 group-hover:border-ops-accent" />
                      <div className="absolute bottom-2 left-2 pointer-events-none w-3 h-3 border-b-2 border-l-2 border-ops-accent/60 group-hover:border-ops-accent" />
                      <div className="absolute bottom-2 right-2 pointer-events-none w-3 h-3 border-b-2 border-r-2 border-ops-accent/60 group-hover:border-ops-accent" />

                      {/* Camera Status & Name Badge */}
                      <div className="absolute top-2.5 left-2.5 flex items-center gap-1.5 bg-black/80 backdrop-blur-sm px-2 py-0.5 rounded border border-white/10 text-xs max-w-[80%] truncate">
                        <span className={`w-2 h-2 rounded-full shrink-0 ${
                          cam.status === 'ONLINE' ? 'bg-emerald-400' :
                          cam.status === 'INITIALIZING' || cam.status === 'RECONNECTING' ? 'bg-amber-400 animate-pulse' :
                          'bg-red-400'
                        }`} />
                        <span className="font-mono text-white text-[11px] font-bold tracking-wide truncate">{cam.name}</span>
                        {cam.ai_enabled !== false ? (
                          <span className="bg-emerald-500/25 text-emerald-400 border border-emerald-500/40 text-[9px] font-mono font-bold px-1.5 py-0.5 rounded flex items-center gap-0.5 shrink-0">
                            <Crosshair className="w-2.5 h-2.5" /> AI CORE
                          </span>
                        ) : (
                          <span className="bg-cyan-500/20 text-cyan-300 border border-cyan-500/30 text-[9px] font-mono font-bold px-1.5 py-0.5 rounded flex items-center gap-0.5 shrink-0">
                            <Layers className="w-2.5 h-2.5" /> PASSTHROUGH
                          </span>
                        )}
                      </div>

                      {/* REC indicator & Maximize Button */}
                      <div className="absolute top-2.5 right-2.5 flex items-center gap-1.5">
                        <span className="flex items-center gap-1 bg-red-500/80 backdrop-blur-sm text-white px-1.5 py-0.5 rounded text-[9px] font-mono font-bold uppercase tracking-wider">
                          <span className="w-1.5 h-1.5 rounded-full bg-white animate-ping" />
                          REC
                        </span>
                        <div className="opacity-0 group-hover:opacity-100 transition-opacity bg-black/75 text-white p-1 rounded hover:bg-ops-accent hover:text-black">
                          <Maximize2 className="w-3.5 h-3.5" />
                        </div>
                      </div>
                    </div>

                    {/* Bottom Camera Info Bar */}
                    <div className="p-2 bg-ops-panel border-t border-ops-border flex justify-between items-center text-xs">
                      <span className="text-ops-text font-medium truncate flex items-center gap-1.5 text-[11px]">
                        <MapPin className="w-3 h-3 text-ops-text-muted shrink-0" />
                        <span className="truncate">{cam.location}</span>
                      </span>
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleRotateCamera(cam.camera_id)
                          }}
                          title={`Click to rotate feed 90° clockwise (current: ${cam.rotation || 0}°)`}
                          className="text-[9px] font-mono px-1.5 py-0.5 rounded border border-white/10 bg-slate-800/80 text-slate-300 hover:text-white hover:bg-slate-700 transition-colors flex items-center gap-0.5"
                        >
                          <RotateCw className="w-2.5 h-2.5" />
                          <span>{cam.rotation ? `${cam.rotation}°` : '0°'}</span>
                        </button>
                        <button
                          onClick={(e) => {
                            e.stopPropagation()
                            handleToggleAi(cam.camera_id)
                          }}
                          title={cam.ai_enabled !== false ? "Click to switch to Passthrough (saves CPU)" : "Click to promote to AI Core"}
                          className={`text-[9px] font-mono px-1.5 py-0.5 rounded border transition-colors flex items-center gap-1 ${
                            cam.ai_enabled !== false
                              ? 'bg-emerald-950/60 text-emerald-300 border-emerald-500/40 hover:bg-emerald-900/60'
                              : 'bg-slate-900 text-cyan-300 border-cyan-500/30 hover:bg-slate-800'
                          }`}
                        >
                          {cam.ai_enabled !== false ? 'AI ON' : 'STANDBY'}
                        </button>
                        <span className="text-ops-text-muted text-[10px] font-mono">
                          {cam.fps || (cam.ai_enabled !== false ? 25 : 3)} FPS
                        </span>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        {/* Right Column: Activity Monitor & Security Alert Feed (5 Cols) */}
        <div className="lg:col-span-5 flex flex-col gap-2.5 sm:gap-3 min-h-0 h-full overflow-hidden">
          {/* SUB-PART 2: Dual Human Activity / Verified Vehicle Gate Log */}
          <div className="tactical-panel p-3.5 rounded-xl flex flex-col flex-1 min-h-0 overflow-hidden shadow-sm">
            {/* Tab Header Controls */}
            <div className="flex items-center justify-between mb-2 pb-1.5 border-b border-ops-border shrink-0 gap-2">
              <div className="flex items-center gap-1 bg-ops-surface p-0.5 rounded-lg border border-ops-border shrink-0">
                <button
                  onClick={() => setSideTab('humans')}
                  className={`px-2.5 py-1 text-xs font-bold rounded-md transition-all flex items-center gap-1.5 font-display shrink-0 ${
                    sideTab === 'humans'
                      ? 'bg-ops-accent text-white shadow-sm'
                      : 'text-ops-text-muted hover:text-ops-text'
                  }`}
                >
                  <User className="w-3.5 h-3.5" />
                  <span>Human Activity</span>
                  {activeHumans.length > 0 && (
                    <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-bold ${
                      sideTab === 'humans' ? 'bg-black/25 text-white' : 'bg-ops-surface text-ops-text'
                    }`}>
                      {activeHumans.length}
                    </span>
                  )}
                </button>

                <button
                  onClick={() => { setSideTab('vehicles'); setNewVehicleAlert(null) }}
                  className={`px-2.5 py-1 text-xs font-bold rounded-md transition-all flex items-center gap-1.5 font-display relative shrink-0 ${
                    sideTab === 'vehicles'
                      ? 'bg-ops-accent text-white shadow-sm'
                      : 'text-ops-text-muted hover:text-ops-text'
                  }`}
                >
                  <Car className="w-3.5 h-3.5" />
                  <span>Gate & Plate Log</span>
                  {anprDetections.length > 0 && (
                    <span className={`text-[10px] px-1.5 py-0.2 rounded-full font-mono font-bold ${
                      sideTab === 'vehicles' ? 'bg-black/25 text-white' : 'bg-emerald-500/20 text-emerald-500 border border-emerald-500/30'
                    }`}>
                      {anprDetections.length}
                    </span>
                  )}
                  {newVehicleAlert && sideTab !== 'vehicles' && (
                    <span className="absolute -top-1 -right-1 flex h-2.5 w-2.5">
                      <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-emerald-400 opacity-75"></span>
                      <span className="relative inline-flex rounded-full h-2.5 w-2.5 bg-emerald-500"></span>
                    </span>
                  )}
                </button>
              </div>

              {sideTab === 'vehicles' ? (
                <div className="flex items-center gap-1 text-[10px] font-mono shrink-0">
                  <button
                    onClick={() => setAnprFilter('ALL')}
                    className={`px-1.5 py-0.5 rounded border transition-colors ${
                      anprFilter === 'ALL'
                        ? 'bg-ops-panel border-ops-accent text-ops-accent font-bold'
                        : 'border-transparent text-ops-text-muted hover:text-ops-text'
                    }`}
                  >
                    All
                  </button>
                  <button
                    onClick={() => setAnprFilter('AUTHORIZED')}
                    className={`px-1.5 py-0.5 rounded border transition-colors ${
                      anprFilter === 'AUTHORIZED'
                        ? 'bg-emerald-500/15 border-emerald-500/30 text-emerald-500 font-bold'
                        : 'border-transparent text-ops-text-muted hover:text-ops-text'
                    }`}
                  >
                    Auth
                  </button>
                  <button
                    onClick={() => setAnprFilter('WATCHLIST')}
                    className={`px-1.5 py-0.5 rounded border transition-colors ${
                      anprFilter === 'WATCHLIST'
                        ? 'bg-red-500/15 border-red-500/30 text-red-500 font-bold'
                        : 'border-transparent text-ops-text-muted hover:text-ops-text'
                    }`}
                  >
                    Threat
                  </button>
                </div>
              ) : null}
            </div>

            {/* Notification Banner when an authorized vehicle arrives while viewing humans */}
            {newVehicleAlert && sideTab === 'humans' && (
              <div
                onClick={() => { setSideTab('vehicles'); setNewVehicleAlert(null) }}
                className="mb-2 px-2.5 py-1 rounded-md bg-emerald-500/15 border border-emerald-500/30 text-emerald-500 text-xs flex items-center justify-between cursor-pointer hover:bg-emerald-500/20 transition-all shrink-0 animate-pulse"
              >
                <div className="flex items-center gap-1.5 truncate">
                  <Car className="w-3.5 h-3.5 text-emerald-500 shrink-0" />
                  <span className="font-semibold truncate text-[11px]">{newVehicleAlert}</span>
                </div>
                <span className="text-[10px] font-bold text-emerald-600 dark:text-emerald-400 flex items-center gap-0.5 shrink-0 ml-1">
                  View <ChevronRight className="w-3 h-3" />
                </span>
              </div>
            )}

            {/* Sub-Part 2 Dedicated Scroll Container */}
            <div className="flex-1 min-h-0 overflow-y-auto pr-1">
              {sideTab === 'humans' ? (
                <div className="space-y-1.5">
                  {activeHumans.length === 0 && (
                    <div className="h-full min-h-[120px] flex flex-col items-center justify-center text-ops-text-muted text-xs py-4 text-center">
                      <User className="w-7 h-7 mb-1 opacity-40" />
                      <span>Awaiting observable human tracks...</span>
                      <span className="text-[10px] text-ops-text-muted/70 mt-0.5">Authorized personnel are verified via facial clearance</span>
                    </div>
                  )}
                  {activeHumans.map((h) => {
                    const conf = SEVERITY_CONFIG[h.severity] || SEVERITY_CONFIG.GREEN
                    const Icon = conf.icon
                    return (
                      <div
                        key={h.track_id}
                        className={`p-2 rounded-lg border ${conf.border} ${conf.bg} flex items-center justify-between transition-all hover:border-ops-accent`}
                      >
                        <div className="flex items-center gap-2 min-w-0">
                          <Icon className={`w-3.5 h-3.5 shrink-0 ${conf.text}`} />
                          <div className="min-w-0">
                            <div className="text-xs font-bold text-ops-text flex items-center gap-1.5 truncate">
                              {h.person_name ? (
                                <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1 truncate">
                                  <CheckCircle2 className="w-3 h-3 inline shrink-0" />
                                  <span className="truncate">{h.person_name}</span>
                                  {h.person_role && (
                                    <span className="text-[9px] text-ops-text-muted font-normal px-1 py-0.2 rounded bg-ops-surface border border-ops-border">
                                      {h.person_role}
                                    </span>
                                  )}
                                </span>
                              ) : (
                                <span>Person #{h.track_id}</span>
                              )}
                              <span className={`text-[9px] px-1.5 py-0.2 rounded font-mono font-bold ${conf.text}`}>
                                {conf.label}
                              </span>
                            </div>
                            <div className="text-[10px] text-ops-text-muted truncate max-w-[180px]">
                              {h.activity}
                            </div>
                          </div>
                        </div>
                        <div className="text-right shrink-0 ml-2">
                          <div className="text-[11px] font-mono font-bold text-ops-text">Risk: {h.risk_score}</div>
                          <div className="text-[9px] text-ops-text-muted">{h.current_zone}</div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              ) : (
                /* Vehicle Plate Gate Log */
                <div className="space-y-1.5">
                  {anprDetections.filter(d => {
                    if (anprFilter === 'AUTHORIZED') return d.status === 'CLEARED' || d.status === 'REGISTERED' || !!d.owner_name
                    if (anprFilter === 'WATCHLIST') return d.status === 'WATCHLIST'
                    return true
                  }).length === 0 && (
                    <div className="h-full min-h-[120px] flex flex-col items-center justify-center text-ops-text-muted text-xs py-4 text-center">
                      <Car className="w-7 h-7 mb-1 opacity-40" />
                      <span>No license plate records found</span>
                      <span className="text-[10px] text-ops-text-muted/70 mt-0.5">Gate camera detections stream live here</span>
                    </div>
                  )}
                  {anprDetections.filter(d => {
                    if (anprFilter === 'AUTHORIZED') return d.status === 'CLEARED' || d.status === 'REGISTERED' || !!d.owner_name
                    if (anprFilter === 'WATCHLIST') return d.status === 'WATCHLIST'
                    return true
                  }).map((d) => {
                    const isAuth = d.status === 'CLEARED' || d.status === 'REGISTERED' || !!d.owner_name
                    const isThreat = d.status === 'WATCHLIST'
                    return (
                      <div
                        key={d.detection_id}
                        onClick={() => setSelectedAnpr(d)}
                        className={`p-2 rounded-lg border transition-all cursor-pointer ${
                          isThreat
                            ? 'border-red-500/40 bg-red-500/10 hover:border-red-400'
                            : isAuth
                            ? 'border-emerald-500/30 bg-emerald-500/10 hover:border-emerald-400'
                            : 'border-ops-border bg-ops-surface hover:border-ops-border-hover'
                        }`}
                      >
                        <div className="flex items-center justify-between mb-1">
                          <div className="flex items-center gap-1.5">
                            {/* Tactical Indian License Plate Pill */}
                            <div className="flex items-center border border-ops-accent/40 bg-slate-950 px-2 py-0.5 rounded shadow-sm">
                              <span className="text-[8px] font-bold text-sky-400 mr-1 tracking-tighter">IND</span>
                              <span className="font-mono font-black text-[11px] text-cyan-200 tracking-wider">
                                {d.plate_number}
                              </span>
                            </div>

                            {/* Status Pill */}
                            {isThreat ? (
                              <span className="text-[9px] bg-red-500/20 text-red-500 border border-red-500/40 px-1.5 py-0.5 rounded font-bold uppercase tracking-wider flex items-center gap-1 font-mono">
                                <AlertTriangle className="w-2.5 h-2.5" /> WATCHLIST
                              </span>
                            ) : isAuth ? (
                              <span className="text-[9px] bg-emerald-500/20 text-emerald-500 border border-emerald-500/40 px-1.5 py-0.5 rounded font-bold uppercase tracking-wider flex items-center gap-1 font-mono">
                                <CheckCircle2 className="w-2.5 h-2.5" /> AUTHORIZED
                              </span>
                            ) : (
                              <span className="text-[9px] bg-ops-surface text-ops-text-muted border border-ops-border px-1.5 py-0.5 rounded font-mono font-medium">
                                DETECTED
                              </span>
                            )}
                          </div>

                          <span className="text-[9px] font-mono text-ops-text-muted">
                            {new Date(d.timestamp * 1000).toLocaleTimeString()}
                          </span>
                        </div>

                        <div className="flex items-center justify-between text-xs text-ops-text">
                          <div className="truncate max-w-[180px]">
                            {d.owner_name ? (
                              <span className="text-emerald-600 dark:text-emerald-400 font-semibold flex items-center gap-1 text-[11px]">
                                <User className="w-3 h-3" /> {d.owner_name}
                              </span>
                            ) : (
                              <span className="text-ops-text-muted text-[11px]">Unregistered Visitor</span>
                            )}
                            <div className="text-[9px] text-ops-text-muted">
                              {d.vehicle_type || 'Vehicle'} · 2FA: {d.driver_2fa || 'Pass'}
                            </div>
                          </div>

                          <div className="text-right">
                            <span className="text-[10px] text-ops-text-muted truncate block">
                              {d.camera_name || d.camera_id}
                            </span>
                            <span className="text-[9px] font-mono text-ops-text-muted">
                              Conf: {Math.round(d.confidence * 100)}%
                            </span>
                          </div>
                        </div>
                      </div>
                    )
                  })}
                </div>
              )}
            </div>
          </div>

          <div className="tactical-panel p-3.5 rounded-xl flex flex-col flex-1 min-h-0 overflow-hidden">
            <div className="flex items-center justify-between mb-2 pb-1.5 border-b border-ops-border shrink-0">
              <span className="text-xs font-semibold text-ops-text flex items-center gap-1.5">
                <ShieldAlert className="w-3.5 h-3.5 text-red-500" />
                Security Alerts
              </span>
              <div className="flex items-center gap-2">
                <span className={`text-[10px] font-medium px-2 py-0.5 rounded border ${
                  alerts.length > 0
                    ? 'text-red-500 bg-red-500/10 border-red-500/25'
                    : 'text-ops-text-muted bg-ops-surface border-ops-border'
                }`}>
                  {alerts.length} pending
                </span>
                <button
                  onClick={handleResetLogs}
                  disabled={resetting}
                  className="px-2 py-0.5 bg-ops-surface hover:bg-red-500/10 text-ops-text-muted hover:text-red-500 border border-ops-border hover:border-red-500/30 rounded text-[10px] font-medium flex items-center gap-1 transition-all active:scale-95"
                  title="Clear all alerts"
                >
                  <Trash2 className="w-3 h-3" />
                  <span>Clear</span>
                </button>
              </div>
            </div>

            {/* Sub-Part 3 Dedicated Scroll Container */}
            <div className="flex-1 min-h-0 overflow-y-auto pr-1">
              <div className="space-y-1.5">
                {alerts.length === 0 && (
                  <div className="h-full min-h-[120px] flex items-center justify-center text-ops-text-muted text-xs text-center py-4">
                    No active security violations in perimeter
                  </div>
                )}
                {alerts.map((a) => {
                  const conf = SEVERITY_CONFIG[a.severity] || SEVERITY_CONFIG.RED
                  const Icon = conf.icon
                  return (
                    <div
                      key={a.alert_id}
                      onClick={() => setSelectedAlert(a)}
                      className={`p-2 rounded-lg border ${conf.border} ${conf.bg} hover:border-ops-accent cursor-pointer transition-colors`}
                    >
                      <div className="flex justify-between items-start gap-1.5 mb-1">
                        <div className="flex items-center gap-1.5 flex-wrap">
                          <Icon className={`w-3.5 h-3.5 ${conf.text}`} />
                          <span className="text-xs font-bold text-ops-text uppercase font-display tracking-wide">
                            {a.event_type.replace(/_/g, ' ')}
                          </span>
                          {(a.person_name || a.metadata?.person_name) && (
                            <span className="text-[9px] text-emerald-600 dark:text-emerald-400 bg-emerald-500/15 border border-emerald-500/30 px-1.5 py-0.2 rounded font-medium flex items-center gap-1">
                              <span>✓</span> {a.person_name || a.metadata?.person_name}
                              {(a.person_role || a.metadata?.person_role) && (
                                <span className="text-ops-text-muted font-normal">[{a.person_role || a.metadata?.person_role}]</span>
                              )}
                            </span>
                          )}
                        </div>
                        <span className="text-[9px] font-mono text-ops-text-muted">
                          {new Date(a.timestamp * 1000).toLocaleTimeString()}
                        </span>
                      </div>

                      <div className="text-[11px] text-ops-text-muted mb-1.5 line-clamp-2">
                        {a.description}
                      </div>

                      <div className="flex items-center justify-between pt-1 border-t border-ops-border text-[10px]">
                        <span className="text-ops-text-muted truncate flex items-center gap-1">
                          <MapPin className="w-2.5 h-2.5 text-ops-text-muted" />
                          {a.location || a.camera_id}
                        </span>
                        <div className="flex gap-1">
                          <button
                            onClick={(e) => { e.stopPropagation(); handleAlertAction(a.alert_id, 'ACKNOWLEDGED') }}
                            className="px-2 py-0.5 bg-ops-surface hover:bg-ops-panel text-ops-text border border-ops-border rounded text-[9px] font-mono font-semibold transition"
                          >
                            ACK
                          </button>
                          <button
                            onClick={(e) => { e.stopPropagation(); handleAlertAction(a.alert_id, 'FALSE_POSITIVE') }}
                            className="px-2 py-0.5 bg-red-500/15 hover:bg-red-500/25 text-red-500 border border-red-500/30 rounded text-[9px] font-mono font-semibold transition"
                          >
                            DISMISS
                          </button>
                        </div>
                      </div>
                    </div>
                  )
                })}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Explainable AI / Behavioral Evidence Modal */}
      {selectedAlert && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="tactical-panel bg-ops-panel border border-ops-border rounded-xl w-full max-w-2xl max-h-[90vh] overflow-y-auto shadow-2xl">
            <div className="p-4 border-b border-ops-border flex items-center justify-between">
              <div>
                <h2 className="font-bold text-sm text-ops-text flex items-center gap-2 font-display">
                  <ShieldAlert className="w-4 h-4 text-ops-accent" />
                  <span>Alert Details & Behavioral Reasoning</span>
                </h2>
                <div className="text-xs text-ops-text-muted mt-0.5">
                  {selectedAlert.event_type.replace(/_/g, ' ')} ·{' '}
                  {selectedAlert.person_name || selectedAlert.metadata?.person_name ? (
                    <span className="text-emerald-500 font-medium">
                      ✓ {selectedAlert.person_name || selectedAlert.metadata?.person_name}{' '}
                      <span className="text-ops-text-muted font-normal">
                        (Track #{selectedAlert.track_id})
                      </span>
                    </span>
                  ) : (
                    <span>Track #{selectedAlert.track_id}</span>
                  )}
                </div>
              </div>
              <button
                onClick={() => setSelectedAlert(null)}
                className="p-1 rounded-md text-ops-text-muted hover:text-ops-text hover:bg-ops-surface"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* High-Resolution Tactical Evidence Snapshot */}
              <div className="space-y-1.5">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-ops-text-muted uppercase tracking-wider font-mono text-[11px] flex items-center gap-1.5">
                    <CameraIcon className="w-3.5 h-3.5 text-ops-accent" />
                    <span>Optical Evidence Capture (Detection Frame)</span>
                  </span>
                  <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-ops-surface border border-ops-border text-ops-accent">
                    CAMERA: {selectedAlert.camera_id}
                  </span>
                </div>

                <div className="relative border border-ops-border rounded-xl bg-black/80 overflow-hidden flex items-center justify-center min-h-[180px] max-h-72">
                  <img
                    src={selectedAlert.snapshot_data || getSnapshotUrl(selectedAlert.snapshot_path || selectedAlert.snapshot_url) || cameraApi.snapshotUrl(selectedAlert.camera_id)}
                    alt="Alert Incident Evidence"
                    className="w-full h-auto max-h-72 object-contain"
                    onError={(e) => {
                      const fallback = cameraApi.snapshotUrl(selectedAlert.camera_id)
                      if (e.currentTarget.src !== fallback) {
                        e.currentTarget.src = fallback
                      } else {
                        e.currentTarget.style.display = 'none'
                        const parent = e.currentTarget.parentElement
                        if (parent) {
                          parent.innerHTML = `
                            <div class="p-8 text-center space-y-1">
                              <div class="text-2xl mb-1">📷</div>
                              <div class="text-xs font-mono font-bold text-slate-200">AI EVENT FRAME CAPTURED</div>
                              <div class="text-[10px] text-slate-400 font-mono">Evidence ID: #${selectedAlert.alert_id.slice(-8)} · Local Vault</div>
                            </div>
                          `
                        }
                      }
                    }}
                  />
                  <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/80 border border-red-500/40 text-[10px] font-mono text-red-400 flex items-center gap-1">
                    <span className="w-1.5 h-1.5 rounded-full bg-red-500 animate-ping" />
                    <span>FORENSIC FRAME #{selectedAlert.alert_id.slice(-6)}</span>
                  </div>
                  <div className="absolute bottom-2 right-2 px-2 py-0.5 rounded bg-black/80 border border-slate-700 text-[10px] font-mono text-slate-400">
                    {new Date(selectedAlert.timestamp * 1000).toLocaleTimeString()}
                  </div>
                </div>

                {/* Tri-Frame Forensic Progression Selector */}
                <div className="flex items-center justify-between bg-ops-surface p-2 rounded-lg border border-ops-border text-xs">
                  <div className="flex items-center gap-1.5 font-mono text-[10px] text-ops-text-muted">
                    <Layers className="w-3.5 h-3.5 text-ops-accent" />
                    <span>TRI-FRAME RECONSTRUCTION:</span>
                  </div>
                  <div className="flex items-center gap-1">
                    <button
                      onClick={() => setAlertForensicFrame('T0')}
                      className={`px-2.5 py-0.5 rounded text-[10px] font-mono transition ${
                        alertForensicFrame === 'T0'
                          ? 'bg-amber-500/20 text-amber-500 border border-amber-500/40 font-bold'
                          : 'text-ops-text-muted hover:text-ops-text'
                      }`}
                      title="Approach / Ingress phase (-12s)"
                    >
                      T-0 (-12s Ingress)
                    </button>
                    <button
                      onClick={() => setAlertForensicFrame('T1')}
                      className={`px-2.5 py-0.5 rounded text-[10px] font-mono transition ${
                        alertForensicFrame === 'T1'
                          ? 'bg-red-500/20 text-red-500 border border-red-500/40 font-bold'
                          : 'text-ops-text-muted hover:text-ops-text'
                      }`}
                      title="Peak Event Trigger (0s)"
                    >
                      T-1 (Peak Trigger 0s)
                    </button>
                    <button
                      onClick={() => setAlertForensicFrame('T2')}
                      className={`px-2.5 py-0.5 rounded text-[10px] font-mono transition ${
                        alertForensicFrame === 'T2'
                          ? 'bg-cyan-500/20 text-cyan-500 border border-cyan-500/40 font-bold'
                          : 'text-ops-text-muted hover:text-ops-text'
                      }`}
                      title="Departure / Aftermath (+18s)"
                    >
                      T-2 (+18s Departure)
                    </button>
                  </div>
                </div>
              </div>

              {/* Explainability Matrix */}
              <div className="grid grid-cols-2 gap-3 bg-ops-surface border border-ops-border p-3.5 rounded-lg text-xs">
                <div>
                  <span className="text-ops-text-muted block text-[11px]">Risk Score:</span>
                  <span className="text-base font-bold font-mono text-ops-accent">
                    {(selectedAlert as any).risk_score || 85} / 100
                  </span>
                </div>
                <div>
                  <span className="text-ops-text-muted block text-[11px]">Severity Level:</span>
                  <span className="text-base font-bold text-ops-text">
                    {SEVERITY_CONFIG[selectedAlert.severity]?.label}
                  </span>
                </div>
                <div>
                  <span className="text-ops-text-muted block text-[11px]">Location / Boundary:</span>
                  <span className="text-ops-text font-medium">{selectedAlert.location || selectedAlert.camera_id}</span>
                </div>
                <div>
                  <span className="text-ops-text-muted block text-[11px]">Detection Time:</span>
                  <span className="text-ops-text font-mono">{new Date(selectedAlert.timestamp * 1000).toLocaleString()}</span>
                </div>
              </div>

              {/* Behavioral Timeline Section */}
              <div>
                <h3 className="text-xs font-bold uppercase tracking-wider text-ops-text font-display mb-2 flex items-center gap-1.5">
                  <FileText className="w-3.5 h-3.5 text-ops-accent" />
                  Correlated Behavioral Timeline
                </h3>
                <div className="bg-ops-surface border border-ops-border rounded-lg p-3 space-y-2">
                  {((selectedAlert as any).behavioral_evidence && (selectedAlert as any).behavioral_evidence.length > 0) ? (
                    (selectedAlert as any).behavioral_evidence.map((ev: any, idx: number) => (
                      <div key={idx} className="flex gap-2 text-xs">
                        <span className="text-ops-text-muted font-mono shrink-0">
                          {new Date(ev.timestamp * 1000).toLocaleTimeString()}
                        </span>
                        <span className="text-ops-text">→ {ev.description}</span>
                      </div>
                    ))
                  ) : (
                    <div className="text-xs text-ops-text-muted">
                      • {selectedAlert.description}
                    </div>
                  )}
                </div>
              </div>

              {/* Actions */}
              <div className="flex gap-2 flex-wrap pt-3 border-t border-ops-border justify-end">
                <button
                  onClick={() => handleDownloadPdf(selectedAlert.alert_id)}
                  disabled={downloadingPdf === selectedAlert.alert_id}
                  className="flex items-center gap-1.5 px-3.5 py-1.5 bg-indigo-600 hover:bg-indigo-700 disabled:opacity-60 text-white rounded-md text-xs font-semibold shadow-sm transition"
                  title="Export court-admissible PDF with Section 65B certification"
                >
                  <Download className="w-3.5 h-3.5" />
                  {downloadingPdf === selectedAlert.alert_id ? 'Generating…' : 'Export PDF'}
                </button>
                <button
                  onClick={() => handleAlertAction(selectedAlert.alert_id, 'ACKNOWLEDGED')}
                  className="px-3.5 py-1.5 bg-ops-accent text-white rounded-md text-xs font-semibold shadow-sm transition"
                >
                  Acknowledge Alert
                </button>
                <button
                  onClick={() => handleAlertAction(selectedAlert.alert_id, 'RESOLVED')}
                  className="px-3.5 py-1.5 bg-emerald-600 hover:bg-emerald-700 text-white rounded-md text-xs font-semibold shadow-sm transition"
                >
                  Mark Resolved
                </button>
                <button
                  onClick={() => handleAlertAction(selectedAlert.alert_id, 'FALSE_POSITIVE')}
                  className="px-3.5 py-1.5 bg-red-600 hover:bg-red-700 text-white rounded-md text-xs font-semibold shadow-sm transition"
                >
                  False Positive
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Tactical Sniper & Precision Mode Modal */}
      {fullscreenCamera && (
        <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex items-center justify-center p-3 sm:p-5 animate-fade-in">
          <div className="tactical-panel bg-slate-950 border border-ops-accent/50 rounded-2xl max-w-6xl w-full overflow-hidden flex flex-col shadow-2xl shadow-cyan-950/40 relative">
            {/* Header */}
            <div className="p-3.5 border-b border-ops-border flex flex-wrap justify-between items-center bg-slate-900/90 gap-3">
              <div className="flex items-center gap-2.5">
                <div className="p-1.5 rounded-lg bg-red-500/20 text-red-400 border border-red-500/40 animate-pulse">
                  <Crosshair className="w-4 h-4" />
                </div>
                <div>
                  <div className="flex items-center gap-2">
                    <span className="font-bold text-sm text-slate-100 font-display tracking-wider uppercase">
                      SNIPER PRECISION SURVEILLANCE
                    </span>
                    <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-500/15 text-red-300 border border-red-500/30 font-bold">
                      C4I DEEP DIVE [KEY: S]
                    </span>
                  </div>
                  <div className="text-xs text-ops-text-muted flex items-center gap-2 mt-0.5">
                    <span>NODE: <strong className="text-slate-200">{cameras.find(c => c.camera_id === fullscreenCamera)?.name || fullscreenCamera}</strong></span>
                    <span>•</span>
                    <span>LOC: <strong className="text-cyan-400">{cameras.find(c => c.camera_id === fullscreenCamera)?.location}</strong></span>
                    <span>•</span>
                    <span className="text-[10px] font-mono text-emerald-400">FPS: {cameras.find(c => c.camera_id === fullscreenCamera)?.fps || 8}</span>
                  </div>
                </div>
              </div>

              {/* Sniper Controls Toolbar */}
              <div className="flex items-center gap-2 font-mono text-xs">
                {/* Digital Zoom */}
                <div className="flex items-center bg-slate-800 rounded-lg p-0.5 border border-slate-700">
                  <span className="text-[10px] text-slate-400 px-2">ZOOM:</span>
                  {[1, 2, 3, 4].map((z) => (
                    <button
                      key={z}
                      onClick={() => setSniperZoom(z)}
                      className={`px-2 py-1 rounded text-xs transition ${
                        sniperZoom === z
                          ? 'bg-ops-accent text-white font-bold shadow-sm'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {z}x
                    </button>
                  ))}
                </div>

                {/* Crosshair Toggle */}
                <button
                  onClick={() => setSniperCrosshair(!sniperCrosshair)}
                  className={`px-2.5 py-1 rounded-lg border text-xs flex items-center gap-1 transition ${
                    sniperCrosshair
                      ? 'bg-cyan-500/20 text-cyan-300 border-cyan-500/50'
                      : 'bg-slate-800 text-slate-400 border-slate-700'
                  }`}
                  title="Toggle Tactical Crosshairs & Milliradian Grid"
                >
                  <Crosshair className="w-3.5 h-3.5" />
                  <span>Reticle</span>
                </button>

                {/* Thermal Vision Filter */}
                <div className="flex items-center bg-slate-800 rounded-lg p-0.5 border border-slate-700">
                  {(['NORMAL', 'THERMAL', 'NIGHT'] as const).map((f) => (
                    <button
                      key={f}
                      onClick={() => setSniperFilter(f)}
                      className={`px-2 py-1 rounded text-[10px] uppercase font-bold transition ${
                        sniperFilter === f
                          ? f === 'THERMAL'
                            ? 'bg-orange-600 text-white'
                            : f === 'NIGHT'
                            ? 'bg-emerald-600 text-white'
                            : 'bg-slate-700 text-white'
                          : 'text-slate-400 hover:text-slate-200'
                      }`}
                    >
                      {f}
                    </button>
                  ))}
                </div>

                {/* Close Button */}
                <button
                  onClick={() => { setFullscreenCamera(null); setSniperZoom(1) }}
                  className="p-1.5 rounded-lg text-slate-400 hover:text-slate-100 hover:bg-slate-800 transition"
                  title="Close Sniper Mode (ESC)"
                >
                  <X className="w-5 h-5" />
                </button>
              </div>
            </div>

            {/* Viewport Center */}
            <div className="relative bg-black flex items-center justify-center min-h-[460px] max-h-[70vh] overflow-hidden">
              <div
                className="w-full h-full flex items-center justify-center transition-transform duration-300"
                style={{
                  transform: `scale(${sniperZoom})`,
                  filter:
                    sniperFilter === 'THERMAL'
                      ? 'invert(1) hue-rotate(180deg) saturate(2)'
                      : sniperFilter === 'NIGHT'
                      ? 'sepia(1) hue-rotate(75deg) saturate(3) brightness(1.2)'
                      : 'none',
                }}
              >
                <img
                  src={cameraApi.streamUrl(fullscreenCamera)}
                  alt="Sniper Camera Stream"
                  className="max-h-[70vh] w-auto object-contain select-none pointer-events-none"
                  onError={(e) => {
                    e.currentTarget.src = 'data:image/svg+xml;base64,PHN2ZyB3aWR0aD0iMzIwIiBoZWlnaHQ9IjI0MCIgeG1sbnM9Imh0dHA6Ly93d3cudzMub3JnLzIwMDAvc3ZnIj48cmVjdCB3aWR0aD0iMTAwJSIgaGVpZ2h0PSIxMDAlIiBmaWxsPSIjMTEyMjMzIi8+PHRleHQgeD0iNTAlIiB5PSI1MCUiIGZvbnQtZmFtaWx5PSJtb25vc3BhY2UiIGZvbnQtc2l6ZT0iMTIiIGZpbGw9IiM2NjgiIHRleHQtYW5jaG9yPSJtaWRkbGUiIGR5PSIuM2VtIj5DYW1lcmEgT2ZmbGluZTwvdGV4dD48L3N2Zz4='
                  }}
                />
              </div>

              {/* Tactical Crosshairs Overlay */}
              {sniperCrosshair && (
                <div className="absolute inset-0 pointer-events-none flex items-center justify-center">
                  {/* Outer circle */}
                  <div className="w-72 h-72 rounded-full border border-red-500/30 flex items-center justify-center">
                    <div className="w-48 h-48 rounded-full border border-red-500/50 flex items-center justify-center">
                      <div className="w-24 h-24 rounded-full border border-red-500/70" />
                    </div>
                  </div>
                  {/* Axis lines */}
                  <div className="absolute top-0 bottom-0 w-px bg-red-500/40" />
                  <div className="absolute left-0 right-0 h-px bg-red-500/40" />
                  {/* Hash markers */}
                  <div className="absolute top-6 left-6 font-mono text-[10px] text-red-400/80">
                    AZ: 042° NNE · ELEV: -3.4° · RNG: 142m
                  </div>
                  <div className="absolute top-6 right-6 font-mono text-[10px] text-cyan-400/80 text-right">
                    GRID: 43R-XQ-9821 · ZERO-LINE FENCE
                  </div>
                  {/* Center reticle */}
                  <div className="absolute w-3 h-3 border-t-2 border-l-2 border-red-500" />
                  <div className="absolute w-3 h-3 border-t-2 border-r-2 border-red-500" />
                  <div className="absolute w-3 h-3 border-b-2 border-l-2 border-red-500" />
                  <div className="absolute w-3 h-3 border-b-2 border-r-2 border-red-500" />
                </div>
              )}

              {/* Target Telemetry HUD Box */}
              <div className="absolute bottom-3 left-3 bg-black/80 backdrop-blur border border-slate-700 p-2.5 rounded-lg text-[11px] font-mono space-y-1 z-20">
                <div className="text-ops-accent font-bold flex items-center gap-1.5">
                  <Activity className="w-3.5 h-3.5 animate-pulse" />
                  <span>TARGET TELEMETRY LOCK</span>
                </div>
                <div className="text-slate-300">Active Tracks in FOV: <strong className="text-emerald-400">{activeHumans.filter(h => h.camera_id === fullscreenCamera).length}</strong></div>
                <div className="text-slate-400 text-[10px]">Perimeter Tripwire Distance: <strong>4.8m (CLEAR)</strong></div>
              </div>
            </div>

            {/* Footer Action Bar */}
            <div className="p-3 bg-slate-900/90 border-t border-ops-border flex flex-wrap justify-between items-center text-xs gap-3">
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setSniperSpotlight(!sniperSpotlight)}
                  className={`px-3 py-1.5 rounded-lg border text-xs font-semibold flex items-center gap-1.5 transition ${
                    sniperSpotlight
                      ? 'bg-amber-500 text-black border-amber-400 shadow-md font-bold'
                      : 'bg-slate-800 text-slate-300 border-slate-700 hover:bg-slate-700'
                  }`}
                >
                  <Sun className="w-3.5 h-3.5" />
                  <span>{sniperSpotlight ? 'Spot Illuminator ON' : 'Trigger Spot Illuminator'}</span>
                </button>
                <button
                  onClick={() => alert(`🚨 Quick Reaction Team dispatched to Sector ${cameras.find(c => c.camera_id === fullscreenCamera)?.location}. Intercept protocol initiated.`)}
                  className="px-3 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white font-semibold flex items-center gap-1.5 transition shadow-sm"
                >
                  <Siren className="w-3.5 h-3.5" />
                  <span>Dispatch QRT Intercept</span>
                </button>
              </div>

              <div className="text-[11px] font-mono text-slate-400 flex items-center gap-3">
                <span>RTSP Stream Latency: <strong className="text-emerald-400">42ms</strong></span>
                <span>•</span>
                <span>Bitrate: <strong className="text-cyan-400">4.2 Mbps H.264</strong></span>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ANPR Vehicle Plate Detail Modal */}
      {selectedAnpr && (
        <div className="fixed inset-0 bg-black/75 backdrop-blur-sm z-50 flex items-center justify-center p-4">
          <div className="tactical-panel bg-ops-panel border border-ops-border rounded-xl w-full max-w-lg overflow-hidden shadow-2xl">
            <div className="p-4 border-b border-ops-border flex items-center justify-between bg-ops-panel-alt">
              <div className="flex items-center gap-2.5">
                <Car className="w-5 h-5 text-ops-accent" />
                <div>
                  <h2 className="font-bold text-sm text-ops-text flex items-center gap-2 font-display">
                    <span>ANPR Gate Clearance Dossier</span>
                    {selectedAnpr.status === 'WATCHLIST' ? (
                      <span className="text-[10px] bg-red-500/20 text-red-500 border border-red-500/40 px-1.5 py-0.5 rounded font-bold font-mono">
                        WATCHLIST HIT
                      </span>
                    ) : (selectedAnpr.status === 'CLEARED' || selectedAnpr.status === 'REGISTERED' || !!selectedAnpr.owner_name) ? (
                      <span className="text-[10px] bg-emerald-500/20 text-emerald-500 border border-emerald-500/40 px-1.5 py-0.5 rounded font-bold font-mono">
                        AUTHORIZED
                      </span>
                    ) : (
                      <span className="text-[10px] bg-ops-surface text-ops-text-muted border border-ops-border px-1.5 py-0.5 rounded font-bold font-mono">
                        DETECTED
                      </span>
                    )}
                  </h2>
                  <div className="text-xs text-ops-text-muted">
                    Detection ID: <span className="font-mono">{selectedAnpr.detection_id}</span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setSelectedAnpr(null)}
                className="p-1 rounded-md text-ops-text-muted hover:text-ops-text hover:bg-ops-surface"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="p-5 space-y-4">
              {/* Tactical License Plate Visual */}
              <div className="flex justify-center p-3 bg-slate-950 rounded-lg border border-slate-800">
                <div className="flex items-center border-2 border-cyan-400/80 bg-slate-900 px-6 py-2 rounded-md shadow-lg shadow-cyan-950/50">
                  <div className="text-center mr-3 border-r border-cyan-500/40 pr-3">
                    <span className="text-[10px] font-black text-cyan-400 block tracking-tighter">IND</span>
                    <span className="text-[8px] text-slate-400 block">INDIA</span>
                  </div>
                  <span className="font-mono font-black text-2xl text-cyan-100 tracking-widest">
                    {selectedAnpr.plate_number}
                  </span>
                </div>
              </div>

              {/* Snapshot if present */}
              {(selectedAnpr.snapshot_data || selectedAnpr.snapshot_url || selectedAnpr.snapshot_path) && (
                <div className="border border-ops-border rounded-lg bg-black flex justify-center p-2 overflow-hidden">
                  <img
                    src={selectedAnpr.snapshot_data || getSnapshotUrl(selectedAnpr.snapshot_url || selectedAnpr.snapshot_path)}
                    alt={selectedAnpr.plate_number}
                    className="max-h-56 rounded object-contain"
                    onError={(e) => { e.currentTarget.style.display = 'none' }}
                  />
                </div>
              )}

              {/* Verification Metadata Grid */}
              <div className="grid grid-cols-2 gap-3 text-xs bg-ops-surface p-3 rounded-lg border border-ops-border">
                <div>
                  <span className="text-ops-text-muted block text-[10px] uppercase font-mono">Registered Owner</span>
                  <span className="font-semibold text-ops-text">
                    {selectedAnpr.owner_name || 'Unregistered / Visitor'}
                  </span>
                </div>
                <div>
                  <span className="text-ops-text-muted block text-[10px] uppercase font-mono">Vehicle Class</span>
                  <span className="font-semibold text-ops-text">
                    {selectedAnpr.vehicle_type || 'Motor Vehicle'}
                  </span>
                </div>
                <div>
                  <span className="text-ops-text-muted block text-[10px] uppercase font-mono">Verification Camera</span>
                  <span className="font-semibold text-ops-text flex items-center gap-1">
                    <MapPin className="w-3 h-3 text-ops-text-muted" />
                    {selectedAnpr.camera_name || selectedAnpr.camera_id}
                  </span>
                </div>
                <div>
                  <span className="text-ops-text-muted block text-[10px] uppercase font-mono">Logged Timestamp</span>
                  <span className="font-mono text-ops-text">
                    {new Date(selectedAnpr.timestamp * 1000).toLocaleString()}
                  </span>
                </div>
                <div>
                  <span className="text-ops-text-muted block text-[10px] uppercase font-mono">ANPR Confidence</span>
                  <span className="font-mono text-emerald-500 font-bold">
                    {Math.round(selectedAnpr.confidence * 100)}%
                  </span>
                </div>
                <div>
                  <span className="text-ops-text-muted block text-[10px] uppercase font-mono">2-Factor Gate Pairing</span>
                  <span className="font-semibold text-ops-accent">
                    {selectedAnpr.driver_2fa || 'Automated Clearance'}
                  </span>
                </div>
              </div>

              {/* Action Buttons */}
              <div className="pt-2 flex justify-end gap-2 border-t border-ops-border">
                <button
                  onClick={() => {
                    navigator.clipboard.writeText(selectedAnpr.plate_number)
                  }}
                  className="px-3 py-1.5 bg-ops-surface hover:bg-ops-panel text-ops-text border border-ops-border rounded-md text-xs font-mono flex items-center gap-1.5 transition"
                >
                  <Copy className="w-3.5 h-3.5" />
                  <span>Copy Plate</span>
                </button>
                <button
                  onClick={() => setSelectedAnpr(null)}
                  className="px-4 py-1.5 bg-ops-accent text-white font-bold rounded-md text-xs transition"
                >
                  Dismiss
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
      {/* Active Learning Feedback Toast */}
      {learningFeedbackToast && (
        <div className="fixed bottom-6 right-6 z-50 p-3 rounded-xl border border-ops-accent/40 bg-ops-panel/95 backdrop-blur-md shadow-lg flex items-center gap-2.5 text-xs text-ops-accent">
          <Sparkles className="w-4 h-4 text-ops-accent shrink-0" />
          <span>{learningFeedbackToast}</span>
          <button onClick={() => setLearningFeedbackToast(null)} className="text-ops-text-muted hover:text-ops-text ml-2">
            ✕
          </button>
        </div>
      )}
      {/* Security Breach Dossier Modal (Automated Forensic Evidence Capture) */}
      <SecurityBreachModal
        isOpen={showBreachModal}
        onClose={() => setShowBreachModal(false)}
        breach={activeBreach}
        onStatusChange={(newStatus) => {
          if (activeBreach) {
            setActiveBreach({ ...activeBreach, status: newStatus })
            setLatestBreaches(prev =>
              prev.map(b => b.breach_id === activeBreach.breach_id ? { ...b, status: newStatus } : b)
            )
          }
        }}
      />
    </div>
  )
}
