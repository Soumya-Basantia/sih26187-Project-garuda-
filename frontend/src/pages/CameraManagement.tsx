import React, { useEffect, useState } from 'react'
import { cameraApi, Camera } from '../services/api'
import {
  Camera as CameraIcon,
  Radio,
  Flame,
  Fingerprint,
  Shield,
  Activity,
  Plus,
  Trash2,
  CheckCircle2,
  MapPin,
  Lightbulb,
  Cpu,
  Layers,
  Sparkles,
  RotateCw
} from 'lucide-react'

type DeviceCategory = 'webcam' | 'cctv' | 'drone' | 'thermal' | 'biometric' | 'barrier' | 'sensor'

interface CategoryConfig {
  label: string
  icon: React.ComponentType<{ className?: string }>
  badgeBg: string
  badgeText: string
  placeholder: string
  defaultProtocol: string
  defaultSourceType: 'rtsp' | 'webcam' | 'file'
  aiEngine: string
}

const CATEGORIES: Record<DeviceCategory, CategoryConfig> = {
  webcam: {
    label: 'Built-in / USB Webcam',
    icon: CameraIcon,
    badgeBg: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-600 dark:text-emerald-300',
    badgeText: 'LOCAL WEBCAM',
    placeholder: '0 (built-in computer webcam — no HTTP link needed)',
    defaultProtocol: 'DirectShow / USB',
    defaultSourceType: 'webcam',
    aiEngine: 'YOLOv8 Sentinel + High-Cadence ANPR + Facial Auth',
  },
  cctv: {
    label: 'Optical CCTV (Legacy)',
    icon: CameraIcon,
    badgeBg: 'bg-emerald-500/15 border-emerald-500/30 text-emerald-600 dark:text-emerald-300',
    badgeText: 'CCTV CAMERA',
    placeholder: 'rtsp://192.168.1.50:554/stream1 (or 0 for USB / phone IP-Webcam)',
    defaultProtocol: 'RTSP / ONVIF',
    defaultSourceType: 'webcam',
    aiEngine: 'YOLOv8 960px + ByteTrack + Lethal Threat AI',
  },
  drone: {
    label: 'Patrol Drone (Garuda-Air)',
    icon: Radio,
    badgeBg: 'bg-cyan-500/15 border-cyan-500/30 text-cyan-600 dark:text-cyan-300',
    badgeText: 'AERIAL UAV',
    placeholder: 'rtsp://drone-dock-01.local:8554/live (or WebRTC stream)',
    defaultProtocol: 'RTSP / WebRTC',
    defaultSourceType: 'rtsp',
    aiEngine: 'Top-Down Aerial Detection + Slew-to-Cue Tracking',
  },
  thermal: {
    label: 'Thermal / FLIR Night-Vision',
    icon: Flame,
    badgeBg: 'bg-amber-500/15 border-amber-500/30 text-amber-600 dark:text-amber-300',
    badgeText: 'THERMAL FLIR',
    placeholder: 'rtsp://flir-perimeter-north:554/thermal_ch1',
    defaultProtocol: 'ONVIF Profile T',
    defaultSourceType: 'rtsp',
    aiEngine: 'Dual-Spectrum Heat Signature Tracking',
  },
  biometric: {
    label: 'Biometric PACS Terminal',
    icon: Fingerprint,
    badgeBg: 'bg-purple-500/15 border-purple-500/30 text-purple-600 dark:text-purple-300',
    badgeText: 'BIOMETRIC PACS',
    placeholder: 'http://192.168.1.120:8000/api/events (Face/Fingerprint Kiosk)',
    defaultProtocol: 'REST / Wiegand IP',
    defaultSourceType: 'file',
    aiEngine: 'Attendance Ledger + Anti-Tailgating Cross-Verify',
  },
  barrier: {
    label: 'Automated Gate Barrier',
    icon: Shield,
    badgeBg: 'bg-blue-500/15 border-blue-500/30 text-blue-600 dark:text-blue-300',
    badgeText: 'GATE BARRIER',
    placeholder: 'modbus://192.168.1.130:502/relay1 (ANPR Linked Barrier)',
    defaultProtocol: 'Modbus / Dry Relay',
    defaultSourceType: 'file',
    aiEngine: 'ANPR Whitelist + Driver 2FA Actuator',
  },
  sensor: {
    label: 'Fence PIDS / Acoustic Sensor',
    icon: Activity,
    badgeBg: 'bg-rose-500/15 border-rose-500/30 text-rose-600 dark:text-rose-300',
    badgeText: 'PERIMETER PIDS',
    placeholder: 'mqtt://sensor-broker.local:1883/pids/sector2',
    defaultProtocol: 'MQTT / TCP',
    defaultSourceType: 'file',
    aiEngine: 'Boundary Cut & Vibration Triangulation',
  },
}

export default function CameraManagement() {
  const [cameras, setCameras] = useState<Camera[]>([])
  const [filterCategory, setFilterCategory] = useState<string>('all')
  const [selectedCategory, setSelectedCategory] = useState<DeviceCategory>('cctv')
  const [name, setName] = useState('')
  const [location, setLocation] = useState('')
  const [sourceType, setSourceType] = useState<'rtsp' | 'webcam' | 'file'>('webcam')
  const [sourceUri, setSourceUri] = useState('')
  const [protocol, setProtocol] = useState('RTSP / ONVIF')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)

  useEffect(() => { load() }, [])

  async function load() {
    try {
      const res = await cameraApi.list()
      setCameras(res.data)
    } catch {
      // Graceful fallback
    }
  }

  function handleCategoryChange(cat: DeviceCategory) {
    setSelectedCategory(cat)
    setProtocol(CATEGORIES[cat].defaultProtocol)
    setSourceType(CATEGORIES[cat].defaultSourceType)
    if (cat === 'webcam') {
      setName('System Webcam')
      setLocation('Local Workstation / Desk')
      setSourceUri('0')
    } else if (!name || Object.values(CATEGORIES).some(c => name.includes(c.badgeText) || name.includes('Node') || name.includes('System Webcam'))) {
      setName(`${CATEGORIES[cat].label.split(' ')[0]} Node 0${cameras.length + 1}`)
      if (sourceUri === '0') {
        setSourceUri('')
      }
    }
  }

  async function handleAdd(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSuccess(null)
    try {
      await cameraApi.create({
        name,
        location,
        source_type: sourceType,
        source_uri: sourceUri,
        target_fps: 35,
        device_category: selectedCategory,
        protocol: protocol,
        ai_enabled: true,
      })
      setSuccess(`Successfully registered ${name}`)
      setName('')
      setLocation('')
      setSourceUri('')
      load()
      setTimeout(() => setSuccess(null), 4000)
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Failed to connect device')
    }
  }

  async function handleRemove(id: string) {
    if (window.confirm('Are you sure you want to disconnect this device?')) {
      await cameraApi.remove(id)
      load()
    }
  }

  async function handleRotate(id: string) {
    try {
      await cameraApi.rotate(id)
      load()
    } catch (err) {
      console.error('Failed to rotate camera', err)
    }
  }

  const filteredDevices = cameras.filter(c => {
    if (filterCategory === 'all') return true
    const cat = c.device_category || 'cctv'
    return cat === filterCategory
  })

  const cctvCount = cameras.filter(c => (c.device_category || 'cctv') === 'cctv').length
  const droneCount = cameras.filter(c => c.device_category === 'drone').length
  const pacsCount = cameras.filter(c => c.device_category === 'biometric' || c.device_category === 'barrier').length

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Top Header & Context Banner */}
      <div className="flex flex-wrap items-center justify-between pb-4 border-b border-ops-border gap-4">
        <div>
          <div className="text-xl font-bold tracking-wide text-ops-text flex items-center gap-2.5 font-display">
            <Shield className="w-6 h-6 text-ops-accent" />
            <span>DEVICE & SENSOR INFRASTRUCTURE</span>
          </div>
          <div className="text-xs text-ops-text-muted mt-1 font-sans">
            Centralized Hardware Hub — Legacy CCTV Retrofit, Drone Feeds, Biometric PACS & Perimeter Barriers
          </div>
        </div>
        <div className="flex items-center gap-2 text-xs">
          <span className="px-3 py-1.5 rounded-full bg-ops-accent/10 text-ops-accent border border-ops-accent/30 font-mono font-medium">
            System Uptime: 99.8% · Zero Hardware Lock-in
          </span>
        </div>
      </div>

      {/* KPI Stats Ribbon */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="tactical-panel p-4 flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-lg bg-ops-accent/15 border border-ops-accent/30 flex items-center justify-center">
            <Radio className="w-5 h-5 text-ops-accent" />
          </div>
          <div>
            <div className="text-2xl font-bold font-display text-ops-text">{cameras.length}</div>
            <div className="text-xs text-ops-text-muted">Total Integrated Nodes</div>
          </div>
        </div>

        <div className="tactical-panel p-4 flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/15 border border-emerald-500/30 flex items-center justify-center">
            <CameraIcon className="w-5 h-5 text-emerald-500" />
          </div>
          <div>
            <div className="text-2xl font-bold font-display text-emerald-500">{cctvCount}</div>
            <div className="text-xs text-ops-text-muted">Legacy CCTV Feeds</div>
          </div>
        </div>

        <div className="tactical-panel p-4 flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-lg bg-cyan-500/15 border border-cyan-500/30 flex items-center justify-center">
            <Radio className="w-5 h-5 text-cyan-500" />
          </div>
          <div>
            <div className="text-2xl font-bold font-display text-cyan-500">{droneCount}</div>
            <div className="text-xs text-ops-text-muted">Patrol Drones (Garuda-Air)</div>
          </div>
        </div>

        <div className="tactical-panel p-4 flex items-center gap-3.5">
          <div className="w-10 h-10 rounded-lg bg-purple-500/15 border border-purple-500/30 flex items-center justify-center">
            <Fingerprint className="w-5 h-5 text-purple-500" />
          </div>
          <div>
            <div className="text-2xl font-bold font-display text-purple-500">{pacsCount}</div>
            <div className="text-xs text-ops-text-muted">Biometric & Barrier Nodes</div>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left Column: Register Device Form */}
        <div className="lg:col-span-4 tactical-panel p-5 space-y-4 h-fit">
          <div className="flex items-center justify-between border-b border-ops-border pb-3">
            <div className="text-xs font-bold text-ops-text uppercase font-display tracking-wider flex items-center gap-2">
              <Plus className="w-4 h-4 text-ops-accent" />
              <span>Register New Sensor Node</span>
            </div>
            <span className="text-[10px] text-ops-accent font-mono uppercase bg-ops-accent/10 px-2 py-0.5 rounded border border-ops-accent/30">
              Open Protocol
            </span>
          </div>

          {error && (
            <div className="p-2.5 rounded-md text-xs bg-red-500/15 border border-red-500/40 text-red-500 font-medium">
              {error}
            </div>
          )}
          {success && (
            <div className="p-2.5 rounded-md text-xs bg-emerald-500/15 border border-emerald-500/40 text-emerald-600 dark:text-emerald-400 font-medium">
              {success}
            </div>
          )}

          <form onSubmit={handleAdd} className="space-y-3.5">
            <div>
              <label className="block text-xs font-semibold text-ops-text mb-1.5 uppercase tracking-wide">
                Device Category
              </label>
              <div className="grid grid-cols-2 gap-1.5">
                {(Object.keys(CATEGORIES) as DeviceCategory[]).map((cat) => {
                  const cfg = CATEGORIES[cat]
                  const Icon = cfg.icon
                  const isSel = selectedCategory === cat
                  return (
                    <button
                      type="button"
                      key={cat}
                      onClick={() => handleCategoryChange(cat)}
                      className={`px-2.5 py-2 rounded-md text-xs font-medium text-left flex items-center gap-2 border transition-all ${
                        isSel
                          ? 'bg-ops-accent/15 border-ops-accent text-ops-accent shadow-sm font-semibold'
                          : 'bg-ops-surface border-ops-border text-ops-text-muted hover:text-ops-text hover:bg-ops-panel'
                      }`}
                    >
                      <Icon className="w-4 h-4 shrink-0" />
                      <span className="truncate">{cfg.label.split(' ')[0]}</span>
                    </button>
                  )
                })}
              </div>
            </div>

            <div>
              <label className="block text-xs font-semibold text-ops-text mb-1 uppercase tracking-wide">
                Device Name
              </label>
              <input
                value={name}
                onChange={(e) => setName(e.target.value)}
                placeholder="e.g. Checkpoint Alpha CCTV"
                className="w-full bg-ops-surface border border-ops-border rounded-md px-3 py-2 text-sm text-ops-text placeholder-ops-text-muted/50 focus:outline-none focus:border-ops-accent"
                required
              />
            </div>

            <div>
              <label className="block text-xs font-semibold text-ops-text mb-1 uppercase tracking-wide">
                Sector / Physical Location
              </label>
              <input
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                placeholder="e.g. North Perimeter Fence, Gate 1"
                className="w-full bg-ops-surface border border-ops-border rounded-md px-3 py-2 text-sm text-ops-text placeholder-ops-text-muted/50 focus:outline-none focus:border-ops-accent"
                required
              />
            </div>

            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-xs font-semibold text-ops-text mb-1 uppercase tracking-wide">
                  Protocol / Bus
                </label>
                <input
                  value={protocol}
                  onChange={(e) => setProtocol(e.target.value)}
                  className="w-full bg-ops-surface border border-ops-border rounded-md px-2.5 py-1.5 text-xs text-ops-text font-mono"
                  required
                />
              </div>
              <div>
                <label className="block text-xs font-semibold text-ops-text mb-1 uppercase tracking-wide">
                  Ingestion Type
                </label>
                <select
                  value={sourceType}
                  onChange={(e) => setSourceType(e.target.value as any)}
                  className="w-full bg-ops-surface border border-ops-border rounded-md px-2 py-1.5 text-xs text-ops-text font-mono"
                >
                  <option value="webcam">Webcam / USB / IP-Phone</option>
                  <option value="rtsp">RTSP Stream (IP Camera/UAV)</option>
                  <option value="file">Video / Mock Loop</option>
                </select>
              </div>
            </div>

            <div>
              <div className="flex items-center justify-between mb-1">
                <label className="block text-xs font-semibold text-ops-text uppercase tracking-wide">
                  Source Stream URI / Device
                </label>
                <span className="text-[10px] text-ops-text-muted font-mono">
                  {sourceType === 'webcam' ? 'Use 0 for computer webcam' : 'RTSP / HTTP'}
                </span>
              </div>
              <input
                value={sourceUri}
                onChange={(e) => setSourceUri(e.target.value)}
                placeholder={CATEGORIES[selectedCategory].placeholder}
                className="w-full bg-ops-surface border border-ops-border rounded-md px-3 py-2 text-xs font-mono text-ops-text placeholder-ops-text-muted/50 focus:outline-none focus:border-ops-accent"
                required
              />

              {/* Quick Presets */}
              <div className="space-y-1.5 mt-2.5">
                <div className="text-[10px] text-ops-text-muted font-medium uppercase tracking-wider">Physical Hardware Presets:</div>
                <div className="flex items-center gap-1.5 flex-wrap">
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedCategory('webcam')
                      setSourceType('webcam')
                      setSourceUri('0')
                      setName('System Webcam')
                      setLocation('Local Workstation / Desk')
                      setProtocol('USB / DirectShow')
                    }}
                    className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/30 hover:bg-emerald-500/20 font-mono transition-colors"
                  >
                    💻 Built-in PC (0)
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedCategory('webcam')
                      setSourceType('webcam')
                      setSourceUri('1')
                      setName('External USB Camera')
                      setLocation('Local Workstation')
                      setProtocol('USB / DirectShow')
                    }}
                    className="px-2 py-0.5 rounded text-[10px] bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 hover:bg-cyan-500/20 font-mono transition-colors"
                  >
                    🔌 USB Webcam (1)
                  </button>
                  <button
                    type="button"
                    onClick={() => {
                      setSelectedCategory('cctv')
                      setSourceType('webcam')
                      setSourceUri('192.168.137.17:8080')
                      setName('Mobile IP Camera')
                      setLocation('Hall / Checkpoint')
                      setProtocol('HTTP Stream')
                    }}
                    className="px-2 py-0.5 rounded text-[10px] bg-purple-500/10 text-purple-400 border border-purple-500/30 hover:bg-purple-500/20 font-mono transition-colors"
                  >
                    📱 Phone IP Camera
                  </button>
                </div>
              </div>

              {sourceType === 'webcam' && (
                <p className="text-[10px] text-slate-400 mt-1.5 leading-relaxed bg-slate-900/60 p-2 rounded border border-slate-800">
                  💡 <strong className="text-ops-accent">No HTTP link needed for your computer webcam!</strong> Type <code className="text-emerald-400 bg-black/40 px-1 py-0.5 rounded font-mono">0</code> to use your laptop's built-in webcam directly.
                </p>
              )}
            </div>

            {/* AI Engine Pipeline preview */}
            <div className="p-3 rounded-md bg-ops-surface border border-ops-border text-[11px] space-y-1">
              <span className="text-ops-text-muted uppercase tracking-wider font-mono text-[10px]">
                Assigned Neural Engine:
              </span>
              <div className="text-ops-accent font-medium">{CATEGORIES[selectedCategory].aiEngine}</div>
            </div>

            <button
              type="submit"
              className="w-full bg-ops-accent hover:opacity-90 text-white font-semibold rounded-md py-2.5 text-xs font-display tracking-wide shadow-sm transition-all flex items-center justify-center gap-2"
            >
              <CheckCircle2 className="w-4 h-4" />
              <span>Connect Device to Garuda Core</span>
            </button>
          </form>
        </div>

        {/* Right Column: Devices Grid & Table */}
        <div className="lg:col-span-8 tactical-panel p-5 space-y-4">
          <div className="flex flex-wrap items-center justify-between border-b border-ops-border pb-3 gap-2">
            <div>
              <div className="text-xs font-bold uppercase font-display text-ops-text tracking-wider">
                Active Infrastructure Inventory
              </div>
              <div className="text-xs text-ops-text-muted">Live hardware nodes monitored by Garuda C2 Hub</div>
            </div>

            {/* Filter Tabs */}
            <div className="flex items-center gap-1 bg-ops-surface p-1 rounded-lg border border-ops-border text-xs font-mono">
              <button
                onClick={() => setFilterCategory('all')}
                className={`px-2.5 py-1 rounded transition-all ${
                  filterCategory === 'all'
                    ? 'bg-ops-panel text-ops-accent font-bold border border-ops-accent'
                    : 'text-ops-text-muted hover:text-ops-text'
                }`}
              >
                All ({cameras.length})
              </button>
              <button
                onClick={() => setFilterCategory('cctv')}
                className={`px-2.5 py-1 rounded transition-all ${
                  filterCategory === 'cctv'
                    ? 'bg-ops-panel text-ops-accent font-bold border border-ops-accent'
                    : 'text-ops-text-muted hover:text-ops-text'
                }`}
              >
                CCTV
              </button>
              <button
                onClick={() => setFilterCategory('drone')}
                className={`px-2.5 py-1 rounded transition-all ${
                  filterCategory === 'drone'
                    ? 'bg-ops-panel text-ops-accent font-bold border border-ops-accent'
                    : 'text-ops-text-muted hover:text-ops-text'
                }`}
              >
                Drones
              </button>
              <button
                onClick={() => setFilterCategory('biometric')}
                className={`px-2.5 py-1 rounded transition-all ${
                  filterCategory === 'biometric'
                    ? 'bg-ops-panel text-ops-accent font-bold border border-ops-accent'
                    : 'text-ops-text-muted hover:text-ops-text'
                }`}
              >
                PACS
              </button>
              <button
                onClick={() => setFilterCategory('thermal')}
                className={`px-2.5 py-1 rounded transition-all ${
                  filterCategory === 'thermal'
                    ? 'bg-ops-panel text-ops-accent font-bold border border-ops-accent'
                    : 'text-ops-text-muted hover:text-ops-text'
                }`}
              >
                Thermal
              </button>
            </div>
          </div>

          {filteredDevices.length === 0 ? (
            <div className="text-center py-12 text-ops-text-muted text-sm">
              No devices found in this category. Register your first device using the panel on the left.
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-ops-text-muted text-xs border-b border-ops-border">
                    <th className="pb-2.5 font-medium">Device & Category</th>
                    <th className="pb-2.5 font-medium">Sector Location</th>
                    <th className="pb-2.5 font-medium">Protocol / URI</th>
                    <th className="pb-2.5 font-medium">Status</th>
                    <th className="pb-2.5 text-right font-medium">Actions</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ops-border">
                  {filteredDevices.map((c) => {
                    const catKey = (c.device_category as DeviceCategory) || 'cctv'
                    const catCfg = CATEGORIES[catKey] || CATEGORIES.cctv
                    const Icon = catCfg.icon
                    const isOnline = c.status === 'ONLINE'
                    const isInit = c.status === 'INITIALIZING' || c.status === 'RECONNECTING'

                    return (
                      <tr key={c.camera_id} className="hover:bg-ops-surface/50 transition-colors">
                        <td className="py-3">
                          <div className="flex items-center gap-2.5">
                            <div className="w-8 h-8 rounded-lg bg-ops-surface border border-ops-border flex items-center justify-center shrink-0">
                              <Icon className="w-4 h-4 text-ops-accent" />
                            </div>
                            <div>
                              <div className="font-medium text-ops-text flex items-center gap-2">
                                {c.name}
                                <span className={`text-[10px] font-mono px-2 py-0.2 rounded border ${catCfg.badgeBg}`}>
                                  {catCfg.badgeText}
                                </span>
                              </div>
                              <div className="text-[11px] text-ops-text-muted font-mono">
                                ID: {c.camera_id}
                              </div>
                            </div>
                          </div>
                        </td>

                        <td className="py-3 text-ops-text text-xs">
                          <span className="flex items-center gap-1">
                            <MapPin className="w-3.5 h-3.5 text-ops-text-muted" />
                            {c.location}
                          </span>
                        </td>

                        <td className="py-3">
                          <div className="text-xs text-ops-text font-mono truncate max-w-[200px]" title={c.source_uri}>
                            {c.source_uri}
                          </div>
                          <div className="text-[10px] text-ops-text-muted">
                            {c.protocol || (c.source_type === 'rtsp' ? 'RTSP Stream' : c.source_type === 'webcam' ? 'Direct Capture' : 'Recorded File')}
                          </div>
                        </td>

                        <td className="py-3">
                          <div className="flex items-center gap-1.5">
                            <span className={`w-2 h-2 rounded-full ${
                              isOnline ? 'bg-emerald-500 animate-pulse' :
                              isInit ? 'bg-amber-500 animate-pulse' : 'bg-red-500'
                            }`} />
                            <span className={`text-xs font-medium font-mono ${
                              isOnline ? 'text-emerald-500' :
                              isInit ? 'text-amber-500' : 'text-red-500'
                            }`}>
                              {isOnline ? 'ARMED / ONLINE' : isInit ? 'CONNECTING...' : 'OFFLINE'}
                            </span>
                          </div>
                        </td>

                        <td className="py-3 text-right">
                          <div className="flex items-center justify-end gap-1.5">
                            <button
                              onClick={() => handleRotate(c.camera_id)}
                              title={`Rotate 90° clockwise (current: ${c.rotation || 0}°)`}
                              className="px-2 py-1 text-xs text-ops-text-muted hover:text-white hover:bg-ops-surface border border-ops-border rounded-md transition-all font-mono flex items-center gap-1"
                            >
                              <RotateCw className="w-3 h-3" />
                              <span>{c.rotation || 0}°</span>
                            </button>
                            <button
                              onClick={() => handleRemove(c.camera_id)}
                              className="px-2.5 py-1 text-xs text-red-500 hover:bg-red-500/15 border border-red-500/30 rounded-md transition-all font-mono"
                            >
                              Disconnect
                            </button>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          )}

          {/* Footnote */}
          <div className="p-3 rounded-lg bg-ops-accent/10 border border-ops-accent/25 flex items-start gap-2.5 text-xs text-ops-text">
            <Lightbulb className="w-4 h-4 text-ops-accent shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold text-ops-accent">Zero Hardware Lock-in:</span> Project Garuda operates seamlessly on <strong>existing CCTV camera infrastructure</strong>. Additional drone streams, thermal FLIR night-vision, and biometric PACS terminals connect over open standard protocols (RTSP / ONVIF / Wiegand) as plug-and-play modular extensions.
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
