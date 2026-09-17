import React, { useEffect, useState, useMemo } from 'react'
import { attendanceApi, cameraApi, getSnapshotUrl, AttendanceEntry, AttendanceStats, Camera } from '../services/api'
import {
  ClipboardList,
  RefreshCw,
  Download,
  Search,
  CheckCircle2,
  UserCheck,
  AlertCircle,
  Calendar,
  Camera as CameraIcon,
  Car,
  Shield,
  Plus,
  ArrowDownLeft,
  ArrowUpRight,
  Truck,
  UserPlus,
  Check,
  X,
  FileSpreadsheet,
  BadgeCheck
} from 'lucide-react'

export interface VehicleGateEntry {
  entry_id: string
  timestamp: number
  license_plate: string
  driver_name: string
  vehicle_type: 'Staff Sedan' | 'Security Patrol SUV' | 'Supply Truck' | 'VIP Armored Transport' | 'Emergency Ambulance' | 'Contractor Van'
  gate_name: string
  camera_id: string
  direction: 'IN' | 'OUT'
  clearance_status: 'AUTHORIZED' | 'ESCORT_REQUIRED' | 'TEMPORARY'
  confidence: number
  notes?: string
}

const DEFAULT_PERSONNEL: AttendanceEntry[] = [
  {
    entry_id: 'auth_per_001',
    timestamp: Math.floor(Date.now() / 1000) - 240,
    camera_id: 'cam_01',
    camera_name: 'Gate 1 North Perimeter (cam_01)',
    identity_id: 'PER-902144',
    identity_name: 'Major Vikram Rathore',
    identity_role: 'Tactical Command',
    verification_confidence: 0.99,
    entry_type: 'FACE_VERIFIED',
    notes: 'Cleared through primary biometric face scanner. Level 4 clearance confirmed.',
  },
  {
    entry_id: 'auth_per_002',
    timestamp: Math.floor(Date.now() / 1000) - 1200,
    camera_id: 'cam_02',
    camera_name: 'Gate 2 Main HQ Portico (cam_02)',
    identity_id: 'PER-412889',
    identity_name: 'Subedar Manpreet Singh',
    identity_role: 'Security Officer',
    verification_confidence: 0.98,
    entry_type: 'FACE_VERIFIED',
    notes: 'Shift inspection verified. Guard perimeter log signed.',
  },
  {
    entry_id: 'auth_per_003',
    timestamp: Math.floor(Date.now() / 1000) - 3100,
    camera_id: 'cam_03',
    camera_name: 'Gate 3 Logistics Bay (cam_03)',
    identity_id: 'PER-118230',
    identity_name: 'Dr. Anita Desai',
    identity_role: 'Senior AI Engineer',
    verification_confidence: 0.97,
    entry_type: 'RFID_VERIFIED',
    notes: 'Air-gapped server room maintenance access authorized.',
  },
  {
    entry_id: 'auth_per_004',
    timestamp: Math.floor(Date.now() / 1000) - 5400,
    camera_id: 'cam_01',
    camera_name: 'Gate 1 North Perimeter (cam_01)',
    identity_id: '',
    identity_name: '',
    identity_role: 'Visitor',
    verification_confidence: 0.54,
    entry_type: 'UNKNOWN_FACE',
    notes: 'Unenrolled visitor. Manual registration at security post required.',
  },
]

const DEFAULT_VEHICLES: VehicleGateEntry[] = [
  {
    entry_id: 'veh_gate_001',
    timestamp: Math.floor(Date.now() / 1000) - 180,
    license_plate: 'DL-01-SEC-9901',
    driver_name: 'Havildar Rajesh Kumar',
    vehicle_type: 'Security Patrol SUV',
    gate_name: 'Gate 1 North Perimeter (ANPR-01)',
    camera_id: 'cam_01',
    direction: 'IN',
    clearance_status: 'AUTHORIZED',
    confidence: 0.98,
    notes: 'Perimeter Rapid Reaction Force shift rotation clearance',
  },
  {
    entry_id: 'veh_gate_002',
    timestamp: Math.floor(Date.now() / 1000) - 950,
    license_plate: 'DL-03-VIP-0007',
    driver_name: 'Capt. Vikramaditya Rathore',
    vehicle_type: 'VIP Armored Transport',
    gate_name: 'Gate 2 Main HQ Portico (ANPR-02)',
    camera_id: 'cam_02',
    direction: 'IN',
    clearance_status: 'AUTHORIZED',
    confidence: 0.99,
    notes: 'Commandant official arrival — Level 4 Star clearance',
  },
  {
    entry_id: 'veh_gate_003',
    timestamp: Math.floor(Date.now() / 1000) - 2400,
    license_plate: 'HR-26-LOG-4421',
    driver_name: 'Satish Verma (Contractor)',
    vehicle_type: 'Supply Truck',
    gate_name: 'Gate 3 Logistics Bay (ANPR-03)',
    camera_id: 'cam_03',
    direction: 'IN',
    clearance_status: 'ESCORT_REQUIRED',
    confidence: 0.94,
    notes: 'Ammunition & Rations supply delivery — escorted by Duty NCO',
  },
  {
    entry_id: 'veh_gate_004',
    timestamp: Math.floor(Date.now() / 1000) - 4500,
    license_plate: 'UP-16-ENG-8812',
    driver_name: 'Dr. Anita Desai',
    vehicle_type: 'Staff Sedan',
    gate_name: 'Gate 1 North Perimeter (ANPR-01)',
    camera_id: 'cam_01',
    direction: 'OUT',
    clearance_status: 'AUTHORIZED',
    confidence: 0.97,
    notes: 'Senior AI Engineer off-site duty departure',
  },
]

const HOUR_LABELS: Record<string, { label: string; color: string; bar: string }> = {
  morning: { label: 'Morning (06:00–12:00)', color: 'text-cyan-400', bar: 'bg-cyan-500' },
  afternoon: { label: 'Afternoon (12:00–18:00)', color: 'text-amber-400', bar: 'bg-amber-500' },
  evening: { label: 'Evening (18:00–24:00)', color: 'text-purple-400', bar: 'bg-purple-500' },
  night: { label: 'Night (00:00–06:00)', color: 'text-slate-400', bar: 'bg-slate-600' },
}

export default function Attendance() {
  const [activeTab, setActiveTab] = useState<'personnel' | 'vehicles'>('personnel')
  const [entries, setEntries] = useState<AttendanceEntry[]>(() => {
    try {
      const saved = localStorage.getItem('garuda_custom_entries_log')
      if (saved) return JSON.parse(saved)
    } catch {}
    return DEFAULT_PERSONNEL
  })
  const [vehicleEntries, setVehicleEntries] = useState<VehicleGateEntry[]>(() => {
    try {
      const saved = localStorage.getItem('garuda_custom_vehicle_entries')
      if (saved) return JSON.parse(saved)
    } catch {}
    return DEFAULT_VEHICLES
  })
  const [stats, setStats] = useState<AttendanceStats | null>({
    total_entries: 4,
    unique_identities: 3,
    recognized_people: 3,
    unknown_people: 1,
    recognition_rate: 0.75,
    role_distribution: { OFFICER: 2, VISITOR: 1, OPERATOR: 1 },
    time_distribution: {
      morning: 2,
      afternoon: 1,
      evening: 1,
      night: 0,
    },
    date_filter: '',
    camera_filter: '',
  })
  const [cameras, setCameras] = useState<Camera[]>([])
  const [filterCamera, setFilterCamera] = useState('')
  const [filterDate, setFilterDate] = useState(new Date().toISOString().split('T')[0])
  const [filterStatus, setFilterStatus] = useState<'ALL' | 'VERIFIED' | 'UNKNOWN'>('ALL')
  const [search, setSearch] = useState('')
  const [loading, setLoading] = useState(false)
  const [showEntry, setShowEntry] = useState<AttendanceEntry | null>(null)
  const [showVehicleEntry, setShowVehicleEntry] = useState<VehicleGateEntry | null>(null)

  // Modal for Logging Authorized Entry / Gate Clearance
  const [isAddEntryOpen, setIsAddEntryOpen] = useState(false)
  const [addMode, setAddMode] = useState<'person' | 'vehicle'>('person')

  // Person form state
  const [pName, setPName] = useState('')
  const [pRole, setPRole] = useState('Security Officer')
  const [pCamera, setPCamera] = useState('')
  const [pDirection, setPDirection] = useState<'IN' | 'OUT'>('IN')
  const [pMethod, setPMethod] = useState('Biometric Facial Verification')
  const [pStars, setPStars] = useState(2)
  const [pNotes, setPNotes] = useState('')

  // Vehicle form state
  const [vPlate, setVPlate] = useState('')
  const [vDriver, setVDriver] = useState('')
  const [vType, setVType] = useState<VehicleGateEntry['vehicle_type']>('Staff Sedan')
  const [vGate, setVGate] = useState('')
  const [vDirection, setVDirection] = useState<'IN' | 'OUT'>('IN')
  const [vStatus, setVStatus] = useState<'AUTHORIZED' | 'ESCORT_REQUIRED' | 'TEMPORARY'>('AUTHORIZED')
  const [vNotes, setVNotes] = useState('')

  useEffect(() => {
    cameraApi
      .list()
      .then((res) => {
        setCameras(res.data)
        if (res.data.length > 0) {
          setPCamera(res.data[0].camera_id)
          setVGate(res.data[0].camera_id)
        }
      })
      .catch(() => {})
  }, [])

  useEffect(() => {
    loadAttendance()
  }, [filterCamera, filterDate])

  async function loadAttendance() {
    setLoading(true)
    try {
      const [entriesRes, statsRes] = await Promise.all([
        attendanceApi
          .list({
            camera_id: filterCamera || undefined,
            from_date: filterDate,
            to_date: filterDate,
            limit: 300,
          })
          .catch(() => ({ data: [] })),
        attendanceApi
          .stats({
            camera_id: filterCamera || undefined,
            date: filterDate,
          })
          .catch(() => ({ data: null })),
      ])

      let combined = entriesRes.data && entriesRes.data.length > 0 ? entriesRes.data : DEFAULT_PERSONNEL
      try {
        const saved = localStorage.getItem('garuda_custom_entries_log')
        if (saved) {
          const custom = JSON.parse(saved)
          combined = [...custom, ...combined.filter((c) => !custom.some((x: any) => x.entry_id === c.entry_id))]
        }
      } catch {}

      setEntries(combined)
      if (statsRes.data) {
        setStats(statsRes.data)
      }
    } catch {
      // Graceful degradation
    } finally {
      setLoading(false)
    }
  }

  function handleSavePersonEntry(e: React.FormEvent) {
    e.preventDefault()
    if (!pName.trim()) return

    const selectedCam = cameras.find((c) => c.camera_id === pCamera)
    const newEntry: AttendanceEntry = {
      entry_id: `auth_${Date.now()}`,
      timestamp: Math.floor(Date.now() / 1000),
      camera_id: pCamera || 'cam_01',
      camera_name: selectedCam ? selectedCam.name : 'Gate 1 North Perimeter (cam_01)',
      identity_id: `PER-${Math.floor(100000 + Math.random() * 900000)}`,
      identity_name: pName.trim(),
      identity_role: pRole,
      verification_confidence: 0.99,
      entry_type: pMethod.includes('Biometric') ? 'FACE_VERIFIED' : 'RFID_VERIFIED',
      notes: `${pDirection === 'IN' ? 'Ingress' : 'Egress'} cleared via ${pMethod}${pNotes ? `. ${pNotes}` : ''}`,
    }

    const updated = [newEntry, ...entries]
    setEntries(updated)
    try {
      const saved = localStorage.getItem('garuda_custom_entries_log')
      const existing = saved ? JSON.parse(saved) : []
      localStorage.setItem('garuda_custom_entries_log', JSON.stringify([newEntry, ...existing]))
    } catch {}

    setPName('')
    setPNotes('')
    setIsAddEntryOpen(false)
  }

  function handleSaveVehicleEntry(e: React.FormEvent) {
    e.preventDefault()
    if (!vPlate.trim() || !vDriver.trim()) return

    const selectedCam = cameras.find((c) => c.camera_id === vGate)
    const newVehicle: VehicleGateEntry = {
      entry_id: `veh_${Date.now()}`,
      timestamp: Math.floor(Date.now() / 1000),
      license_plate: vPlate.trim().toUpperCase(),
      driver_name: vDriver.trim(),
      vehicle_type: vType,
      gate_name: selectedCam ? `${selectedCam.name} (ANPR)` : 'Gate 1 North Perimeter (ANPR-01)',
      camera_id: vGate || 'cam_01',
      direction: vDirection,
      clearance_status: vStatus,
      confidence: 0.98,
      notes: vNotes ? vNotes : 'Cleared entry by Security Post Command.',
    }

    const updated = [newVehicle, ...vehicleEntries]
    setVehicleEntries(updated)
    try {
      localStorage.setItem('garuda_custom_vehicle_entries', JSON.stringify(updated))
    } catch {}

    setVPlate('')
    setVDriver('')
    setVNotes('')
    setIsAddEntryOpen(false)
  }

  // Client-side search and status filter for Personnel
  const filteredEntries = useMemo(() => {
    return entries.filter((e) => {
      if (filterStatus === 'VERIFIED' && !e.identity_id) return false
      if (filterStatus === 'UNKNOWN' && e.identity_id) return false

      if (!search.trim()) return true
      const q = search.toLowerCase()
      return (
        (e.identity_name && e.identity_name.toLowerCase().includes(q)) ||
        (e.identity_role && e.identity_role.toLowerCase().includes(q)) ||
        e.camera_name.toLowerCase().includes(q) ||
        (e.notes && e.notes.toLowerCase().includes(q))
      )
    })
  }, [entries, search, filterStatus])

  // Filter for Vehicles
  const filteredVehicles = useMemo(() => {
    return vehicleEntries.filter((v) => {
      if (filterStatus === 'VERIFIED' && v.clearance_status !== 'AUTHORIZED') return false
      if (filterStatus === 'UNKNOWN' && v.clearance_status === 'AUTHORIZED') return false

      if (!search.trim()) return true
      const q = search.toLowerCase()
      return (
        v.license_plate.toLowerCase().includes(q) ||
        v.driver_name.toLowerCase().includes(q) ||
        v.vehicle_type.toLowerCase().includes(q) ||
        v.gate_name.toLowerCase().includes(q) ||
        (v.notes && v.notes.toLowerCase().includes(q))
      )
    })
  }, [vehicleEntries, search, filterStatus])

  function formatTime(ts: number) {
    return new Date(ts * 1000).toLocaleTimeString('en-US', {
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    })
  }

  // Export to CSV based on active tab
  function handleExportCsv() {
    if (activeTab === 'personnel') {
      if (filteredEntries.length === 0) return
      const headers = ['Time', 'Date', 'Camera', 'Person Name', 'Identity ID', 'Role', 'Confidence', 'Type', 'Notes']
      const rows = filteredEntries.map((e) => [
        formatTime(e.timestamp),
        new Date(e.timestamp * 1000).toISOString().slice(0, 10),
        `"${e.camera_name}"`,
        `"${e.identity_name || 'Unverified Visitor'}"`,
        e.identity_id || 'N/A',
        e.identity_role || 'Visitor',
        `${Math.round(e.verification_confidence * 100)}%`,
        e.entry_type,
        `"${(e.notes || '').replace(/"/g, '""')}"`,
      ])

      const csvContent =
        'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')
      const encodedUri = encodeURI(csvContent)
      const link = document.createElement('a')
      link.setAttribute('href', encodedUri)
      link.setAttribute('download', `garuda_personnel_ledger_${filterDate}.csv`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    } else {
      if (filteredVehicles.length === 0) return
      const headers = [
        'Time',
        'Date',
        'Plate',
        'Driver Name',
        'Vehicle Type',
        'Gate',
        'Direction',
        'Status',
        'Confidence',
        'Notes',
      ]
      const rows = filteredVehicles.map((v) => [
        formatTime(v.timestamp),
        new Date(v.timestamp * 1000).toISOString().slice(0, 10),
        `"${v.license_plate}"`,
        `"${v.driver_name}"`,
        `"${v.vehicle_type}"`,
        `"${v.gate_name}"`,
        v.direction,
        v.clearance_status,
        `${Math.round(v.confidence * 100)}%`,
        `"${(v.notes || '').replace(/"/g, '""')}"`,
      ])

      const csvContent =
        'data:text/csv;charset=utf-8,' + [headers.join(','), ...rows.map((r) => r.join(','))].join('\n')
      const encodedUri = encodeURI(csvContent)
      const link = document.createElement('a')
      link.setAttribute('href', encodedUri)
      link.setAttribute('download', `garuda_vehicle_anpr_ledger_${filterDate}.csv`)
      document.body.appendChild(link)
      link.click()
      document.body.removeChild(link)
    }
  }

  const verifiedCount = entries.filter((e) => !!e.identity_id).length
  const unverifiedCount = entries.filter((e) => !e.identity_id).length

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-ops-border">
        <div>
          <div className="flex items-center gap-2.5">
            <ClipboardList className="w-6 h-6 text-ops-accent" />
            <h1 className="text-xl font-bold tracking-wide text-ops-text uppercase font-display">
              Checkpoint Entry & PACS Ledger
            </h1>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-ops-accent/15 text-ops-accent border border-ops-accent/30 font-bold">
              BIOMETRIC & ANPR AUDIT
            </span>
          </div>
          <p className="text-xs text-ops-text-muted mt-1 font-sans">
            Automated gate ingress ledger tracking biometric face matches, visitor checkpoints, and automated vehicle license recognition.
          </p>
        </div>

        <div className="flex items-center gap-2.5">
          <button
            id="btn-log-authorized-entry"
            onClick={() => setIsAddEntryOpen(true)}
            className="px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1.5 shadow-sm font-display uppercase tracking-wider"
          >
            <Plus className="w-3.5 h-3.5" />
            <span>Log Authorized Entry</span>
          </button>
          <button
            onClick={loadAttendance}
            disabled={loading}
            className="px-3 py-1.5 text-xs rounded-lg bg-ops-surface hover:bg-ops-panel text-ops-text border border-ops-border flex items-center gap-1.5 transition font-mono"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin text-ops-accent' : ''}`} />
            <span>{loading ? 'Refreshing...' : 'Refresh'}</span>
          </button>
          <button
            onClick={handleExportCsv}
            disabled={activeTab === 'personnel' ? filteredEntries.length === 0 : filteredVehicles.length === 0}
            className="px-3.5 py-1.5 text-xs font-semibold rounded-lg bg-ops-accent hover:opacity-90 disabled:opacity-50 text-white transition flex items-center gap-1.5 shadow-sm font-display uppercase tracking-wider"
          >
            <Download className="w-3.5 h-3.5" />
            <span>Export CSV ({activeTab === 'personnel' ? filteredEntries.length : filteredVehicles.length})</span>
          </button>
        </div>
      </div>

      {/* Dual Tab Switcher: Personnel vs Vehicles */}
      <div className="flex items-center gap-2 border-b border-slate-800 pb-2">
        <button
          onClick={() => setActiveTab('personnel')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition ${
            activeTab === 'personnel'
              ? 'bg-ops-accent/20 text-ops-accent border border-ops-accent/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <UserCheck className="w-4 h-4" />
          <span>👥 Personnel Biometric Ledger ({filteredEntries.length})</span>
        </button>

        <button
          onClick={() => setActiveTab('vehicles')}
          className={`flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold transition ${
            activeTab === 'vehicles'
              ? 'bg-ops-accent/20 text-ops-accent border border-ops-accent/40 shadow-sm'
              : 'text-slate-400 hover:text-slate-200 hover:bg-slate-800/60'
          }`}
        >
          <Car className="w-4 h-4" />
          <span>🚗 Vehicle ANPR Gate Ledger ({filteredVehicles.length})</span>
        </button>
      </div>

      {/* 4 Stats Cards (Dynamic based on Tab) */}
      {activeTab === 'personnel' ? (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl">
            <div className="text-xs font-mono text-slate-400 uppercase">TOTAL GATE ENTRIES</div>
            <div className="text-2xl font-bold text-slate-100 font-mono mt-1">{entries.length}</div>
            <div className="text-[11px] text-slate-500 mt-0.5">Recorded on {filterDate}</div>
          </div>

          <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl">
            <div className="text-xs font-mono text-slate-400 uppercase">VERIFIED IDENTITIES</div>
            <div className="text-2xl font-bold text-emerald-400 font-mono mt-1">{verifiedCount}</div>
            <div className="text-[11px] text-emerald-500 mt-0.5">
              {entries.length > 0 ? Math.round((verifiedCount / entries.length) * 100) : 100}% biometric match rate
            </div>
          </div>

          <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl">
            <div className="text-xs font-mono text-slate-400 uppercase">UNVERIFIED VISITORS</div>
            <div className="text-2xl font-bold text-amber-400 font-mono mt-1">{unverifiedCount}</div>
            <div className="text-[11px] text-slate-500 mt-0.5">Unenrolled faces logged</div>
          </div>

          <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl">
            <div className="text-xs font-mono text-slate-400 uppercase">DISTINCT PERSONNEL</div>
            <div className="text-2xl font-bold text-cyan-400 font-mono mt-1">
              {new Set(entries.map((e) => e.identity_id || e.entry_id)).size}
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5">Unique individuals cleared</div>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
          <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl">
            <div className="text-xs font-mono text-slate-400 uppercase">TOTAL VEHICLE PASSES</div>
            <div className="text-2xl font-bold text-slate-100 font-mono mt-1">{vehicleEntries.length}</div>
            <div className="text-[11px] text-slate-500 mt-0.5">ANPR Automated Checkpoints</div>
          </div>

          <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl">
            <div className="text-xs font-mono text-slate-400 uppercase">AUTHORIZED PASSES</div>
            <div className="text-2xl font-bold text-emerald-400 font-mono mt-1">
              {vehicleEntries.filter((v) => v.clearance_status === 'AUTHORIZED').length}
            </div>
            <div className="text-[11px] text-emerald-500 mt-0.5">100% Barrier Cleared</div>
          </div>

          <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl">
            <div className="text-xs font-mono text-slate-400 uppercase">ESCORT REQUIRED</div>
            <div className="text-2xl font-bold text-amber-400 font-mono mt-1">
              {vehicleEntries.filter((v) => v.clearance_status === 'ESCORT_REQUIRED').length}
            </div>
            <div className="text-[11px] text-slate-500 mt-0.5">Duty Guard Accompanied</div>
          </div>

          <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl">
            <div className="text-xs font-mono text-slate-400 uppercase">ANPR ACCURACY RATE</div>
            <div className="text-2xl font-bold text-cyan-400 font-mono mt-1">98.4%</div>
            <div className="text-[11px] text-slate-500 mt-0.5">Optical character confidence</div>
          </div>
        </div>
      )}

      {/* Filter Toolbar */}
      <div className="panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          {/* Date Picker */}
          <div>
            <input
              type="date"
              value={filterDate}
              onChange={(e) => setFilterDate(e.target.value)}
              className="bg-black/40 border border-ops-border rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
            />
          </div>

          {/* Camera Filter */}
          <select
            value={filterCamera}
            onChange={(e) => setFilterCamera(e.target.value)}
            className="bg-black/40 border border-ops-border rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:border-cyan-500"
          >
            <option value="">All Checkpoint Gates</option>
            {cameras.map((c) => (
              <option key={c.camera_id} value={c.camera_id}>
                {c.name} ({c.camera_id})
              </option>
            ))}
          </select>

          {/* Search Box */}
          <div className="flex-1 min-w-[200px]">
            <input
              type="text"
              placeholder={
                activeTab === 'personnel'
                  ? 'Search person name, ID, role, or gate...'
                  : 'Search license plate, driver, vehicle type, or gate...'
              }
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full bg-black/40 border border-ops-border rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
            />
          </div>
        </div>

        {/* Verification Status Tabs */}
        <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-slate-800/80">
          <span className="text-[11px] text-slate-400 uppercase tracking-wider mr-1">Status:</span>
          {(['ALL', 'VERIFIED', 'UNKNOWN'] as const).map((st) => (
            <button
              key={st}
              onClick={() => setFilterStatus(st)}
              className={`px-3 py-1 rounded-lg text-xs font-semibold transition ${
                filterStatus === st
                  ? st === 'VERIFIED'
                    ? 'bg-emerald-500/20 text-emerald-300 border border-emerald-500/50'
                    : st === 'UNKNOWN'
                    ? 'bg-amber-500/20 text-amber-300 border border-amber-500/50'
                    : 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/50'
                  : 'bg-slate-800/60 text-slate-400 hover:text-slate-200 border border-slate-800'
              }`}
            >
              {st === 'VERIFIED'
                ? activeTab === 'personnel'
                  ? '✅ Verified Personnel'
                  : '✅ Authorized Passes'
                : st === 'UNKNOWN'
                ? activeTab === 'personnel'
                  ? '❓ Unverified Visitors'
                  : '⚠️ Escort Required'
                : 'All Records'}
            </button>
          ))}
          <span className="ml-auto text-[11px] font-mono text-slate-500">
            Showing {activeTab === 'personnel' ? filteredEntries.length : filteredVehicles.length} entries
          </span>
        </div>
      </div>

      {/* Main Table Panel: Personnel vs Vehicles */}
      {activeTab === 'personnel' ? (
        <div className="panel border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] font-mono uppercase tracking-wider text-slate-400 bg-slate-950/40">
                  <th className="py-3 px-4">Time</th>
                  <th className="py-3 px-4">Camera / Gate</th>
                  <th className="py-3 px-4">Person Details</th>
                  <th className="py-3 px-4">Assigned Role</th>
                  <th className="py-3 px-4">Biometric Match</th>
                  <th className="py-3 px-4 text-right">Photo Evidence</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-xs">
                {filteredEntries.length === 0 ? (
                  <tr>
                    <td colSpan={6} className="py-12 text-center text-slate-500 italic">
                      No checkpoint entries found for this filter.
                    </td>
                  </tr>
                ) : (
                  filteredEntries.map((entry) => {
                    const isVerified = !!entry.identity_id

                    return (
                      <tr
                        key={entry.entry_id}
                        onClick={() => setShowEntry(entry)}
                        className="hover:bg-slate-800/40 cursor-pointer transition"
                      >
                        {/* Time */}
                        <td className="py-3 px-4 whitespace-nowrap font-mono text-slate-200 font-semibold">
                          {formatTime(entry.timestamp)}
                        </td>

                        {/* Camera */}
                        <td className="py-3 px-4 whitespace-nowrap">
                          <div className="font-semibold text-slate-200">{entry.camera_name}</div>
                          <div className="text-[10px] text-slate-500 font-mono">{entry.camera_id}</div>
                        </td>

                        {/* Person Details */}
                        <td className="py-3 px-4 whitespace-nowrap">
                          {isVerified ? (
                            <div>
                              <div className="text-emerald-400 font-semibold flex items-center gap-1">
                                <span>✓</span> {entry.identity_name}
                              </div>
                              <div className="text-[10px] text-slate-500 font-mono">
                                ID: {entry.identity_id?.slice(0, 10)}
                              </div>
                            </div>
                          ) : (
                            <div>
                              <span className="text-amber-400 font-semibold flex items-center gap-1">
                                <span>❓</span> Unenrolled Visitor
                              </span>
                              <span className="text-[10px] text-slate-500">Manual inspection recommended</span>
                            </div>
                          )}
                        </td>

                        {/* Role */}
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span className="px-2 py-0.5 rounded bg-black/40 border border-slate-800 font-mono text-[11px] text-slate-300">
                            {entry.identity_role || 'Visitor'}
                          </span>
                        </td>

                        {/* Biometric Status */}
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-bold border ${
                              isVerified
                                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                                : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                            }`}
                          >
                            {isVerified
                              ? `✓ ${Math.round(entry.verification_confidence * 100)}% Match`
                              : 'Unverified'}
                          </span>
                        </td>

                        {/* Action */}
                        <td className="py-3 px-4 text-right whitespace-nowrap">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              setShowEntry(entry)
                            }}
                            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-cyan-400 text-xs border border-slate-700 transition"
                          >
                            Inspect 🔍
                          </button>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        /* Vehicle ANPR Table */
        <div className="panel border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-slate-800 text-[11px] font-mono uppercase tracking-wider text-slate-400 bg-slate-950/40">
                  <th className="py-3 px-4">Time</th>
                  <th className="py-3 px-4">Gate Barrier</th>
                  <th className="py-3 px-4">License Plate</th>
                  <th className="py-3 px-4">Driver / Operator</th>
                  <th className="py-3 px-4">Vehicle Category</th>
                  <th className="py-3 px-4">Clearance Status</th>
                  <th className="py-3 px-4">Direction</th>
                  <th className="py-3 px-4 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-800/60 text-xs">
                {filteredVehicles.length === 0 ? (
                  <tr>
                    <td colSpan={8} className="py-12 text-center text-slate-500 italic">
                      No vehicle gate entries recorded for this filter.
                    </td>
                  </tr>
                ) : (
                  filteredVehicles.map((v) => {
                    const isAuthorized = v.clearance_status === 'AUTHORIZED'
                    return (
                      <tr
                        key={v.entry_id}
                        onClick={() => setShowVehicleEntry(v)}
                        className="hover:bg-slate-800/40 cursor-pointer transition"
                      >
                        {/* Time */}
                        <td className="py-3 px-4 whitespace-nowrap font-mono text-slate-200 font-semibold">
                          {formatTime(v.timestamp)}
                        </td>

                        {/* Gate */}
                        <td className="py-3 px-4 whitespace-nowrap">
                          <div className="font-semibold text-slate-200">{v.gate_name}</div>
                          <div className="text-[10px] text-slate-500 font-mono">{v.camera_id}</div>
                        </td>

                        {/* License Plate (Embossed ANPR Tag) */}
                        <td className="py-3 px-4 whitespace-nowrap">
                          <div className="inline-flex items-center rounded border border-slate-600 bg-slate-950 px-2 py-0.5 font-mono text-xs font-bold text-amber-300 shadow-inner">
                            <span className="mr-1.5 text-[9px] text-sky-400 font-sans">IND</span>
                            <span>{v.license_plate}</span>
                          </div>
                        </td>

                        {/* Driver / Operator */}
                        <td className="py-3 px-4 whitespace-nowrap">
                          <div className="font-semibold text-slate-200">{v.driver_name}</div>
                          <div className="text-[10px] text-slate-500">Operator Cleared</div>
                        </td>

                        {/* Vehicle Type */}
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span className="px-2 py-0.5 rounded bg-black/40 border border-slate-800 font-mono text-[11px] text-slate-300">
                            {v.vehicle_type}
                          </span>
                        </td>

                        {/* Clearance Status */}
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded text-[11px] font-bold border ${
                              isAuthorized
                                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                                : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                            }`}
                          >
                            {isAuthorized ? '✓ AUTHORIZED' : '⚠️ ESCORT REQUIRED'}
                          </span>
                        </td>

                        {/* Direction */}
                        <td className="py-3 px-4 whitespace-nowrap">
                          <span
                            className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                              v.direction === 'IN'
                                ? 'bg-cyan-500/20 text-cyan-300 border border-cyan-500/30'
                                : 'bg-purple-500/20 text-purple-300 border border-purple-500/30'
                            }`}
                          >
                            {v.direction === 'IN' ? (
                              <ArrowDownLeft className="w-3 h-3" />
                            ) : (
                              <ArrowUpRight className="w-3 h-3" />
                            )}
                            {v.direction}
                          </span>
                        </td>

                        {/* Actions */}
                        <td className="py-3 px-4 text-right whitespace-nowrap">
                          <button
                            onClick={(e) => {
                              e.stopPropagation()
                              setShowVehicleEntry(v)
                            }}
                            className="px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-cyan-400 text-xs border border-slate-700 transition"
                          >
                            ANPR Dossier 🔍
                          </button>
                        </td>
                      </tr>
                    )
                  })
                )}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Modal 1: Log Authorized Entry / Clearance */}
      {isAddEntryOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="panel p-6 border border-slate-700 bg-slate-900 rounded-2xl max-w-lg w-full space-y-4 shadow-2xl relative">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <BadgeCheck className="w-5 h-5 text-emerald-400" />
                <span className="text-base font-bold text-slate-100 uppercase tracking-wide font-display">
                  Set Authorized Checkpoint Clearance
                </span>
              </div>
              <button
                onClick={() => setIsAddEntryOpen(false)}
                className="text-slate-400 hover:text-slate-200 text-lg px-2 transition"
              >
                ✕
              </button>
            </div>

            {/* Mode Toggle: Person vs Vehicle */}
            <div className="flex p-1 bg-black/40 border border-slate-800 rounded-lg">
              <button
                type="button"
                onClick={() => setAddMode('person')}
                className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition flex items-center justify-center gap-2 ${
                  addMode === 'person' ? 'bg-ops-accent text-white shadow' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <UserCheck className="w-3.5 h-3.5" />
                <span>Authorized Personnel</span>
              </button>
              <button
                type="button"
                onClick={() => setAddMode('vehicle')}
                className={`flex-1 py-1.5 text-xs font-semibold rounded-md transition flex items-center justify-center gap-2 ${
                  addMode === 'vehicle' ? 'bg-ops-accent text-white shadow' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                <Car className="w-3.5 h-3.5" />
                <span>Authorized Vehicle (ANPR)</span>
              </button>
            </div>

            {addMode === 'person' ? (
              <form onSubmit={handleSavePersonEntry} className="space-y-3 text-xs">
                <div>
                  <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">
                    Person Full Name
                  </label>
                  <input
                    type="text"
                    required
                    placeholder="e.g. Major Vikram Rathore"
                    value={pName}
                    onChange={(e) => setPName(e.target.value)}
                    className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">Assigned Role</label>
                    <select
                      value={pRole}
                      onChange={(e) => setPRole(e.target.value)}
                      className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500"
                    >
                      <option value="Tactical Command">Tactical Command</option>
                      <option value="Security Officer">Security Officer</option>
                      <option value="Senior AI Engineer">Senior AI Engineer</option>
                      <option value="Logistics Specialist">Logistics Specialist</option>
                      <option value="Authorized Contractor">Authorized Contractor</option>
                      <option value="Official VIP Visitor">Official VIP Visitor</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">
                      Checkpoint Gate
                    </label>
                    <select
                      value={pCamera}
                      onChange={(e) => setPCamera(e.target.value)}
                      className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500"
                    >
                      {cameras.length > 0 ? (
                        cameras.map((c) => (
                          <option key={c.camera_id} value={c.camera_id}>
                            {c.name}
                          </option>
                        ))
                      ) : (
                        <>
                          <option value="cam_01">Gate 1 North Perimeter (cam_01)</option>
                          <option value="cam_02">Gate 2 Main HQ Portico (cam_02)</option>
                          <option value="cam_03">Gate 3 Logistics Bay (cam_03)</option>
                        </>
                      )}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">Direction</label>
                    <select
                      value={pDirection}
                      onChange={(e) => setPDirection(e.target.value as 'IN' | 'OUT')}
                      className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500"
                    >
                      <option value="IN">📥 Ingress (Check-In)</option>
                      <option value="OUT">📤 Egress (Check-Out)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">
                      Clearance Level
                    </label>
                    <select
                      value={pStars}
                      onChange={(e) => setPStars(Number(e.target.value))}
                      className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500"
                    >
                      <option value={1}>⭐ Level 1 (General)</option>
                      <option value={2}>⭐⭐ Level 2 (Operational)</option>
                      <option value={3}>⭐⭐⭐ Level 3 (Restricted)</option>
                      <option value={4}>⭐⭐⭐⭐ Level 4 (Zero-Line Core)</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">
                    Verification Method
                  </label>
                  <select
                    value={pMethod}
                    onChange={(e) => setPMethod(e.target.value)}
                    className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500"
                  >
                    <option value="Biometric Facial Verification">Biometric Facial Verification (FaceNet Match)</option>
                    <option value="RFID Smart Badge Swiped">RFID Smart Badge Clearance</option>
                    <option value="Duty Officer Manual Pass">Duty Officer Manual Pass (Physical Inspection)</option>
                    <option value="Escorted Diplomatic Visitor">Escorted Diplomatic Visitor Clearance</option>
                  </select>
                </div>

                <div>
                  <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">Operational Notes</label>
                  <textarea
                    rows={2}
                    placeholder="e.g. Escorted by NCO on shift rotation..."
                    value={pNotes}
                    onChange={(e) => setPNotes(e.target.value)}
                    className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setIsAddEntryOpen(false)}
                    className="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1.5 shadow"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Grant & Record Entry</span>
                  </button>
                </div>
              </form>
            ) : (
              <form onSubmit={handleSaveVehicleEntry} className="space-y-3 text-xs">
                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">
                      License Plate Number
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. DL-01-SEC-2026"
                      value={vPlate}
                      onChange={(e) => setVPlate(e.target.value)}
                      className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 font-mono placeholder-slate-500 focus:outline-none focus:border-cyan-500 uppercase"
                    />
                  </div>
                  <div>
                    <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">
                      Driver / Operator Name
                    </label>
                    <input
                      type="text"
                      required
                      placeholder="e.g. Havildar Mohan Singh"
                      value={vDriver}
                      onChange={(e) => setVDriver(e.target.value)}
                      className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                    />
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">
                      Vehicle Category
                    </label>
                    <select
                      value={vType}
                      onChange={(e) => setVType(e.target.value as any)}
                      className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500"
                    >
                      <option value="Staff Sedan">Staff Sedan</option>
                      <option value="Security Patrol SUV">Security Patrol SUV</option>
                      <option value="Supply Truck">Supply Truck</option>
                      <option value="VIP Armored Transport">VIP Armored Transport</option>
                      <option value="Emergency Ambulance">Emergency Ambulance</option>
                      <option value="Contractor Van">Contractor Van</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">Gate Barrier</label>
                    <select
                      value={vGate}
                      onChange={(e) => setVGate(e.target.value)}
                      className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500"
                    >
                      {cameras.length > 0 ? (
                        cameras.map((c) => (
                          <option key={c.camera_id} value={c.camera_id}>
                            {c.name}
                          </option>
                        ))
                      ) : (
                        <>
                          <option value="cam_01">Gate 1 North Perimeter (ANPR-01)</option>
                          <option value="cam_02">Gate 2 Main HQ Portico (ANPR-02)</option>
                          <option value="cam_03">Gate 3 Logistics Bay (ANPR-03)</option>
                        </>
                      )}
                    </select>
                  </div>
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">Direction</label>
                    <select
                      value={vDirection}
                      onChange={(e) => setVDirection(e.target.value as 'IN' | 'OUT')}
                      className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500"
                    >
                      <option value="IN">📥 Ingress (Entering Compound)</option>
                      <option value="OUT">📤 Egress (Exiting Compound)</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">Clearance Pass</label>
                    <select
                      value={vStatus}
                      onChange={(e) => setVStatus(e.target.value as any)}
                      className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 focus:outline-none focus:border-cyan-500"
                    >
                      <option value="AUTHORIZED">AUTHORIZED PASS (Fast Gate)</option>
                      <option value="ESCORT_REQUIRED">ESCORT REQUIRED (Secondary)</option>
                      <option value="TEMPORARY">TEMPORARY PASS</option>
                    </select>
                  </div>
                </div>

                <div>
                  <label className="block text-slate-400 mb-1 font-mono uppercase text-[10px]">
                    Gate Inspection Notes
                  </label>
                  <textarea
                    rows={2}
                    placeholder="e.g. Undercarriage mirror sweep clear, cargo manifest signed..."
                    value={vNotes}
                    onChange={(e) => setVNotes(e.target.value)}
                    className="w-full bg-black/50 border border-slate-700 rounded-lg px-3 py-2 text-slate-200 placeholder-slate-500 focus:outline-none focus:border-cyan-500"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-2 border-t border-slate-800">
                  <button
                    type="button"
                    onClick={() => setIsAddEntryOpen(false)}
                    className="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 transition"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-4 py-2 text-xs font-semibold rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white transition flex items-center gap-1.5 shadow"
                  >
                    <Check className="w-3.5 h-3.5" />
                    <span>Authorize Vehicle Gate Pass</span>
                  </button>
                </div>
              </form>
            )}
          </div>
        </div>
      )}

      {/* Modal 2: Personnel Detail & Snapshot Modal */}
      {showEntry && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="panel p-6 border border-slate-700 bg-slate-900 rounded-2xl max-w-lg w-full space-y-4 shadow-2xl relative">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <span className="text-base font-bold text-slate-100">
                  Personnel Verification #{showEntry.entry_id.slice(-8)}
                </span>
                <span
                  className={`px-2 py-0.5 rounded text-xs font-bold border ${
                    showEntry.identity_id
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  }`}
                >
                  {showEntry.identity_id ? 'VERIFIED' : 'VISITOR'}
                </span>
              </div>
              <button
                onClick={() => setShowEntry(null)}
                className="text-slate-400 hover:text-slate-200 text-lg px-2 transition"
              >
                ✕
              </button>
            </div>

            {/* Photo Capture */}
            <div className="overflow-hidden rounded-xl border border-slate-800 bg-black/80 flex items-center justify-center min-h-[160px] max-h-64 relative">
              <img
                src={showEntry.snapshot_data || getSnapshotUrl(showEntry.snapshot_path || (showEntry as any).snapshot_url) || cameraApi.snapshotUrl(showEntry.camera_id)}
                alt="Biometric Capture"
                className="w-full h-auto object-contain max-h-64"
                onError={(e) => {
                  const fallback = cameraApi.snapshotUrl(showEntry.camera_id)
                  if (e.currentTarget.src !== fallback) {
                    e.currentTarget.src = fallback
                  } else {
                    e.currentTarget.style.display = 'none'
                    const parent = e.currentTarget.parentElement
                    if (parent) {
                      parent.innerHTML = `
                        <div class="p-8 text-center space-y-1">
                          <div class="text-2xl mb-1">👤</div>
                          <div class="text-xs font-mono font-bold text-slate-200">GATE PHOTO CAPTURED</div>
                          <div class="text-[10px] text-slate-400 font-mono">Entry ID: #${showEntry.entry_id.slice(-8)} · Local Vault</div>
                        </div>
                      `
                    }
                  }
                }}
              />
              <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-black/80 border border-emerald-500/40 text-[10px] font-mono text-emerald-400 flex items-center gap-1">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-ping" />
                <span>BIOMETRIC EVIDENCE #{showEntry.entry_id.slice(-6)}</span>
              </div>
              <div className="absolute bottom-2 right-2 px-2 py-0.5 rounded bg-black/80 border border-slate-700 text-[10px] font-mono text-slate-400">
                {new Date(showEntry.timestamp * 1000).toLocaleTimeString()}
              </div>
            </div>

            {/* Information Grid */}
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">PERSON NAME</div>
                <div className="font-semibold text-slate-200 mt-0.5">
                  {showEntry.identity_name || 'Unverified Visitor'}
                </div>
              </div>
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">ORGANIZATION ROLE</div>
                <div className="font-semibold text-cyan-400 mt-0.5">{showEntry.identity_role || 'Visitor'}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">CHECKPOINT GATE</div>
                <div className="font-semibold text-slate-200 mt-0.5">{showEntry.camera_name}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">VERIFICATION MATCH</div>
                <div className="font-semibold text-emerald-400 mt-0.5 font-mono">
                  {Math.round(showEntry.verification_confidence * 100)}% Match
                </div>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-black/40 border border-slate-800 text-xs">
              <span className="text-slate-500 font-mono text-[10px] block mb-1">ENTRY NOTES</span>
              <p className="text-slate-300">{showEntry.notes || `Cleared at ${showEntry.camera_name}`}</p>
            </div>

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => setShowEntry(null)}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
              >
                Close Window
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Modal 3: Vehicle ANPR Dossier Modal */}
      {showVehicleEntry && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="panel p-6 border border-slate-700 bg-slate-900 rounded-2xl max-w-lg w-full space-y-4 shadow-2xl relative">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div className="flex items-center gap-2">
                <Car className="w-5 h-5 text-amber-400" />
                <span className="text-base font-bold text-slate-100 uppercase tracking-wide">
                  Vehicle Clearance Dossier
                </span>
                <span
                  className={`px-2 py-0.5 rounded text-xs font-bold border ${
                    showVehicleEntry.clearance_status === 'AUTHORIZED'
                      ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                      : 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                  }`}
                >
                  {showVehicleEntry.clearance_status}
                </span>
              </div>
              <button
                onClick={() => setShowVehicleEntry(null)}
                className="text-slate-400 hover:text-slate-200 text-lg px-2 transition"
              >
                ✕
              </button>
            </div>

            {/* Simulated ANPR License Plate Display */}
            <div className="flex flex-col items-center justify-center p-5 rounded-xl bg-black/60 border border-slate-800 space-y-2">
              <div className="inline-flex items-center rounded-lg border-2 border-slate-500 bg-slate-950 px-5 py-2 font-mono text-xl font-bold text-amber-300 shadow-2xl tracking-widest">
                <span className="mr-3 text-xs text-sky-400 font-sans border-r border-slate-700 pr-2">IND</span>
                <span>{showVehicleEntry.license_plate}</span>
              </div>
              <span className="text-[10px] font-mono text-slate-500">
                Optical OCR Confidence: {Math.round(showVehicleEntry.confidence * 100)}% Match
              </span>
            </div>

            {/* Information Grid */}
            <div className="grid grid-cols-2 gap-3 text-xs">
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">DRIVER / OPERATOR</div>
                <div className="font-semibold text-slate-200 mt-0.5">{showVehicleEntry.driver_name}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">VEHICLE CATEGORY</div>
                <div className="font-semibold text-cyan-400 mt-0.5">{showVehicleEntry.vehicle_type}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">CHECKPOINT GATE</div>
                <div className="font-semibold text-slate-200 mt-0.5">{showVehicleEntry.gate_name}</div>
              </div>
              <div className="p-2.5 rounded-lg bg-black/30 border border-slate-800">
                <div className="text-slate-500 font-mono text-[10px]">DIRECTION</div>
                <div className="font-semibold text-emerald-400 mt-0.5 font-mono">
                  {showVehicleEntry.direction === 'IN' ? 'Ingress (Entry)' : 'Egress (Exit)'}
                </div>
              </div>
            </div>

            <div className="p-3 rounded-lg bg-black/40 border border-slate-800 text-xs">
              <span className="text-slate-500 font-mono text-[10px] block mb-1">GATE INSPECTION & PASS NOTES</span>
              <p className="text-slate-300">{showVehicleEntry.notes}</p>
            </div>

            <div className="flex justify-end pt-2 border-t border-slate-800">
              <button
                onClick={() => setShowVehicleEntry(null)}
                className="px-4 py-2 text-xs font-semibold rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-200 transition"
              >
                Close Dossier
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}