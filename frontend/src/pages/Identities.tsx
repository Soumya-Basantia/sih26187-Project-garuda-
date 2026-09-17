import React, { useEffect, useState, useRef } from 'react'
import { identityApi, Identity, vehicleApi, Vehicle, AnprDetection, ScanResult, getSnapshotUrl, systemApi } from '../services/api'

import { Users, Car, ClipboardList, Shield, UserCheck } from 'lucide-react'

type Tab = 'persons' | 'vehicles' | 'gatelog'

export default function Identities() {
  const [tab, setTab] = useState<Tab>('persons')

  return (
    <div className="p-6 space-y-5 max-w-7xl mx-auto">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between border-b border-ops-border pb-4 gap-4">
        <div>
          <h1 className="text-xl font-bold text-ops-text flex items-center gap-2.5 font-display">
            <Shield className="w-6 h-6 text-ops-accent" />
            <span>Identity & Access Dossiers</span>
          </h1>
          <p className="text-xs text-ops-text-muted mt-1 font-sans">
            Authorized personnel vault, biometric face enrollments, vehicle plate whitelist, and 2FA gate access verification.
          </p>
        </div>
        <div className="flex items-center gap-1.5 bg-ops-surface border border-ops-border p-1 rounded-lg">
          <button
            onClick={() => setTab('persons')}
            className={`px-3.5 py-1.5 rounded-md text-xs font-semibold transition-all flex items-center gap-1.5 font-display ${
              tab === 'persons'
                ? 'bg-ops-accent text-white shadow-sm'
                : 'text-ops-text-muted hover:text-ops-text'
            }`}
          >
            <Users className="w-3.5 h-3.5" />
            <span>Personnel & Biometrics</span>
          </button>
          <button
            onClick={() => setTab('vehicles')}
            className={`px-3.5 py-1.5 rounded-md text-xs font-semibold transition-all flex items-center gap-1.5 font-display ${
              tab === 'vehicles'
                ? 'bg-ops-accent text-white shadow-sm'
                : 'text-ops-text-muted hover:text-ops-text'
            }`}
          >
            <Car className="w-3.5 h-3.5" />
            <span>Vehicle Registry</span>
          </button>
          <button
            onClick={() => setTab('gatelog')}
            className={`px-3.5 py-1.5 rounded-md text-xs font-semibold transition-all flex items-center gap-1.5 font-display ${
              tab === 'gatelog'
                ? 'bg-ops-accent text-white shadow-sm'
                : 'text-ops-text-muted hover:text-ops-text'
            }`}
          >
            <ClipboardList className="w-3.5 h-3.5" />
            <span>Gate & ANPR Log</span>
          </button>
        </div>
      </div>

      {tab === 'persons' && <PersonTab />}
      {tab === 'vehicles' && <VehicleTab />}
      {tab === 'gatelog' && <GateLogTab />}
    </div>
  )
}

function PersonTab() {
  const [identities, setIdentities] = useState<Identity[]>([])
  const [demoId, setDemoId] = useState('')
  const [name, setName] = useState('')
  const [role, setRole] = useState('Officer')
  const [department, setDepartment] = useState('')
  const [plateNumber, setPlateNumber] = useState('')
  const [vehicleType, setVehicleType] = useState('Car')
  const [rankStars, setRankStars] = useState<number>(3)
  const [rankTitle, setRankTitle] = useState<string>('Field Officer / Colonel / Major')
  const [photo, setPhoto] = useState<File | null>(null)
  const [photoPreview, setPhotoPreview] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)

  // Camera Capture State
  const [captureMode, setCaptureMode] = useState<'upload' | 'camera'>('upload')
  const [isCameraActive, setIsCameraActive] = useState(false)
  const [cameraError, setCameraError] = useState<string | null>(null)
  const [availableDevices, setAvailableDevices] = useState<MediaDeviceInfo[]>([])
  const [selectedDeviceId, setSelectedDeviceId] = useState<string>('')
  const [facingMode, setFacingMode] = useState<'user' | 'environment'>('user')
  const videoRef = useRef<HTMLVideoElement | null>(null)
  const canvasRef = useRef<HTMLCanvasElement | null>(null)
  const streamRef = useRef<MediaStream | null>(null)

  useEffect(() => {
    load()
    refreshDevices()
    if (navigator.mediaDevices?.addEventListener) {
      const handler = () => refreshDevices()
      navigator.mediaDevices.addEventListener('devicechange', handler)
      return () => {
        navigator.mediaDevices.removeEventListener('devicechange', handler)
        stopCamera()
      }
    }
    return () => {
      stopCamera()
    }
  }, [])

  useEffect(() => {
    if (isCameraActive && videoRef.current && streamRef.current) {
      videoRef.current.srcObject = streamRef.current
      videoRef.current.play().catch((e) => console.warn('Video play caught:', e))
    }
  }, [isCameraActive])

  async function load() {
    try {
      const res = await identityApi.list()
      setIdentities(res.data)
    } catch (err: any) {
      setError('Failed to fetch enrolled personnel.')
    }
  }

  async function refreshDevices(activeId?: string) {
    try {
      if (!navigator.mediaDevices?.enumerateDevices) return []
      const allDevices = await navigator.mediaDevices.enumerateDevices()
      const videoInputs = allDevices.filter((d) => d.kind === 'videoinput')
      setAvailableDevices(videoInputs)
      if (activeId) {
        setSelectedDeviceId(activeId)
      } else if (videoInputs.length > 0 && !selectedDeviceId) {
        setSelectedDeviceId(videoInputs[0].deviceId)
      }
      return videoInputs
    } catch (e) {
      console.warn('Could not enumerate devices:', e)
      return []
    }
  }

  async function startCamera(targetDeviceId?: string, targetFacing?: 'user' | 'environment') {
    setCameraError(null)

    if (!navigator?.mediaDevices?.getUserMedia) {
      setCameraError(
        'Camera API is not supported in this browser context (requires HTTPS or http://localhost). Please use the File upload option.'
      )
      setIsCameraActive(false)
      return
    }

    stopCamera()

    const deviceToUse = targetDeviceId || selectedDeviceId
    let stream: MediaStream | null = null

    // Attempt 1: Target specific deviceId if provided
    if (deviceToUse) {
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            deviceId: { exact: deviceToUse },
            width: { ideal: 640 },
            height: { ideal: 480 },
          },
        })
      } catch (e1: any) {
        console.warn(`Attempt 1 with deviceId ${deviceToUse} failed:`, e1)
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: { deviceId: { exact: deviceToUse } },
          })
        } catch {
          // Continue to generic attempts
        }
      }
    }

    // Attempt 2: Preferred resolution with ideal facingMode (not strict/mandatory)
    if (!stream) {
      const facing = targetFacing || facingMode
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          video: {
            width: { ideal: 640 },
            height: { ideal: 480 },
            facingMode: { ideal: facing },
          },
        })
      } catch (e2: any) {
        console.warn('Attempt 2 with ideal facingMode failed:', e2)
        // Attempt 3: Without facingMode constraint (essential for desktop/USB webcams)
        try {
          stream = await navigator.mediaDevices.getUserMedia({
            video: {
              width: { ideal: 640 },
              height: { ideal: 480 },
            },
          })
        } catch (e3: any) {
          console.warn('Attempt 3 with ideal resolution failed:', e3)
          // Attempt 4: Absolute basic fallback
          try {
            stream = await navigator.mediaDevices.getUserMedia({ video: true })
          } catch (errFallback: any) {
            console.error('All camera attempts failed:', errFallback)
            handleCameraError(errFallback)
            setIsCameraActive(false)
            return
          }
        }
      }
    }

    if (stream) {
      streamRef.current = stream
      setIsCameraActive(true)

      const track = stream.getVideoTracks()[0]
      const activeId = track?.getSettings()?.deviceId || deviceToUse
      if (activeId) {
        setSelectedDeviceId(activeId)
      }

      if (videoRef.current) {
        videoRef.current.srcObject = stream
        videoRef.current.play().catch(() => {})
      }

      await refreshDevices(activeId)
    }
  }

  async function handleSwitchCamera() {
    let devices = availableDevices
    if (devices.length <= 1) {
      devices = await refreshDevices()
    }

    if (devices.length > 1) {
      const currentIndex = devices.findIndex((d) => d.deviceId === selectedDeviceId)
      const nextIndex = (currentIndex + 1) % devices.length
      const nextDevice = devices[nextIndex]
      if (nextDevice) {
        setSelectedDeviceId(nextDevice.deviceId)
        await startCamera(nextDevice.deviceId)
        return
      }
    }

    // If only 1 device known or labels missing, toggle front/back facing mode
    const nextFacing = facingMode === 'user' ? 'environment' : 'user'
    setFacingMode(nextFacing)
    await startCamera(undefined, nextFacing)
  }

  function handleCameraError(err: any) {
    const name = err?.name || ''
    const msg = err?.message || ''
    console.error('Camera error:', name, msg, err)

    if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
      setCameraError(
        'Camera permission was blocked by your browser. Please click the 🔒 lock or camera icon in your browser URL bar and set Camera to "Allow", then click Start Live Camera.'
      )
    } else if (name === 'NotReadableError' || name === 'TrackStartError') {
      setCameraError(
        'Camera is busy or in use by another application (or video pipeline). If you have another camera connected, click "Switch Camera" below or close other apps using the webcam.'
      )
    } else if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
      setCameraError(
        'No camera device detected on this system. Please connect a webcam or switch to "File" upload.'
      )
    } else if (name === 'OverconstrainedError') {
      setCameraError(
        `Camera resolution constraints not supported by device (${err?.constraint || 'unknown'}). Retrying with basic video settings...`
      )
    } else {
      setCameraError(
        `Unable to access webcam (${msg || name || 'Device error'}). Please check camera permissions or use the File upload option.`
      )
    }
    setIsCameraActive(false)
  }

  function stopCamera() {
    if (streamRef.current) {
      streamRef.current.getTracks().forEach((track) => track.stop())
      streamRef.current = null
    }
    if (videoRef.current) {
      videoRef.current.srcObject = null
    }
    setIsCameraActive(false)
  }

  function switchMode(mode: 'upload' | 'camera') {
    setCaptureMode(mode)
    setCameraError(null)
    if (mode === 'upload') {
      stopCamera()
    } else if (mode === 'camera') {
      if (!photoPreview) {
        startCamera(selectedDeviceId || undefined)
      }
    }
  }

  function handleCaptureSnapshot() {
    const video = videoRef.current
    const canvas = canvasRef.current
    if (!video || !canvas) return

    const width = video.videoWidth || 640
    const height = video.videoHeight || 480
    canvas.width = width
    canvas.height = height

    const ctx = canvas.getContext('2d')
    if (!ctx) return

    ctx.drawImage(video, 0, 0, width, height)

    canvas.toBlob(
      (blob) => {
        if (!blob) return
        const filename = `face_capture_${Date.now()}.jpg`
        const file = new File([blob], filename, { type: 'image/jpeg' })
        setPhoto(file)
        setPhotoPreview(URL.createObjectURL(blob))
        stopCamera()
      },
      'image/jpeg',
      0.95
    )
  }

  function handleRetake() {
    setPhoto(null)
    if (photoPreview && photoPreview.startsWith('blob:')) {
      URL.revokeObjectURL(photoPreview)
    }
    setPhotoPreview(null)
    if (captureMode === 'camera') {
      startCamera(selectedDeviceId || undefined)
    }
  }

  function handlePhotoChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0] || null
    setPhoto(file)
    if (file) {
      const reader = new FileReader()
      reader.onloadend = () => setPhotoPreview(reader.result as string)
      reader.readAsDataURL(file)
    } else {
      setPhotoPreview(null)
    }
  }

  async function handleEnroll(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSuccess(null)
    if (!photo) {
      setError('Please attach or capture a clear, front-facing reference photo for facial biometrics.')
      return
    }

    setLoading(true)
    const form = new FormData()
    form.append('demo_id', demoId)
    form.append('name', name)
    form.append('role', role)
    form.append('department', department)
    form.append('rank_stars', rankStars.toString())
    form.append('rank_title', rankTitle)
    form.append('consent_given', 'true')
    form.append('photo', photo)

    if (plateNumber.trim()) {
      form.append('plate_number', plateNumber.trim().toUpperCase().replace(/\s/g, ''))
      form.append('vehicle_type', vehicleType)
    }

    try {
      await identityApi.enroll(form)
      setSuccess(`Successfully enrolled ${name}${plateNumber ? ` and linked vehicle ${plateNumber.toUpperCase()}` : ''}!`)
      setDemoId('')
      setName('')
      setDepartment('')
      setPlateNumber('')
      setPhoto(null)
      setPhotoPreview(null)
      stopCamera()
      load()
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Enrollment failed. Ensure face is clearly visible.')
    } finally {
      setLoading(false)
    }
  }

  async function handleDelete(identityId: string, personName: string) {
    if (!confirm(`Revoke and unenroll ${personName}? Associated vehicle access will also be unlinked.`)) return
    try {
      await identityApi.remove(identityId)
      load()
    } catch (err: any) {
      setError('Failed to delete identity.')
    }
  }

  return (
    <div className="grid grid-cols-3 gap-6">
      {/* Enrollment Form */}
      <form onSubmit={handleEnroll} className="panel p-5 space-y-4 h-fit border border-ops-border/60">
        <div>
          <div className="text-sm font-bold text-slate-200 tracking-wide">ENROLL AUTHORIZED PERSONNEL</div>
          <div className="text-xs text-slate-400 mt-1">
            Enrolls face biometrics and optionally binds their vehicle plate for automated 2-Factor gate clearance.
          </div>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/40 text-red-300 rounded px-3 py-2 text-xs">
            {error}
          </div>
        )}
        {success && (
          <div className="bg-green-500/10 border border-green-500/40 text-green-300 rounded px-3 py-2 text-xs">
            {success}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">Badge / Service ID *</label>
            <input
              placeholder="e.g. BSF-8842 / OFF-102"
              value={demoId}
              onChange={(e) => setDemoId(e.target.value)}
              className="w-full bg-black/40 border border-ops-border rounded px-2.5 py-1.5 text-sm font-mono"
              required
            />
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Full Name *</label>
            <input
              placeholder="e.g. Capt. Rajesh Sharma"
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="w-full bg-black/40 border border-ops-border rounded px-2.5 py-1.5 text-sm"
              required
            />
          </div>

          {/* Military Star Rank & Clearance Level */}
          <div className="border border-amber-500/30 bg-amber-950/15 rounded-xl p-3 space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-bold text-amber-400 flex items-center gap-1.5 uppercase tracking-wide">
                <span>⭐</span> Military Star Rank Clearance
              </label>
              <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                {'⭐'.repeat(rankStars)} LEVEL {rankStars}
              </span>
            </div>

            <div className="space-y-1.5">
              {[
                { stars: 5, title: 'Supreme Commander / General', badge: '⭐⭐⭐⭐⭐' },
                { stars: 4, title: 'Division Commander / Brigadier', badge: '⭐⭐⭐⭐' },
                { stars: 3, title: 'Field Officer / Colonel / Major', badge: '⭐⭐⭐' },
                { stars: 2, title: 'Duty Officer / Captain / Lt', badge: '⭐⭐' },
                { stars: 1, title: 'Patrol Guard / Sentry', badge: '⭐' },
              ].map((tier) => (
                <button
                  key={tier.stars}
                  type="button"
                  onClick={() => {
                    setRankStars(tier.stars)
                    setRankTitle(tier.title)
                  }}
                  className={`w-full flex items-center justify-between px-2.5 py-1.5 rounded-lg border text-xs transition-all text-left ${
                    rankStars === tier.stars
                      ? 'bg-amber-500/25 border-amber-400 text-amber-200 shadow-sm shadow-amber-500/20'
                      : 'bg-black/30 border-slate-800 text-slate-400 hover:border-slate-700 hover:text-slate-300'
                  }`}
                >
                  <span className="font-semibold">{tier.title}</span>
                  <span className="font-mono text-[11px]">{tier.badge}</span>
                </button>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Operational Role</label>
              <select
                value={role}
                onChange={(e) => setRole(e.target.value)}
                className="w-full bg-black/40 border border-ops-border rounded px-2 py-1.5 text-sm"
              >
                <option>Officer</option>
                <option>Security Staff</option>
                <option>Patrol Unit</option>
                <option>Logistics / Driver</option>
                <option>Civilian Contractor</option>
                <option>Administrator</option>
                <option>Visitor</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Unit / Wing</label>
              <input
                placeholder="e.g. Sector-3 Gate"
                value={department}
                onChange={(e) => setDepartment(e.target.value)}
                className="w-full bg-black/40 border border-ops-border rounded px-2 py-1.5 text-sm"
              />
            </div>
          </div>

          {/* Optional Vehicle Binding */}
          <div className="border border-ops-border/60 bg-black/20 p-3 rounded-lg space-y-2">
            <div className="text-xs font-semibold text-ops-accent flex items-center gap-1.5">
              <span>🚗</span> Assigned Vehicle (Optional)
            </div>
            <div className="text-[11px] text-slate-400">
              When this vehicle approaches the gate, the AI cross-matches the driver's face to this owner profile.
            </div>
            <div className="grid grid-cols-2 gap-2">
              <div>
                <label className="block text-[10px] text-slate-400 mb-1">License Plate Number</label>
                <input
                  placeholder="e.g. MH12AB1234"
                  value={plateNumber}
                  onChange={(e) => setPlateNumber(e.target.value.toUpperCase())}
                  className="w-full bg-black/40 border border-ops-border rounded px-2 py-1.5 text-xs font-mono tracking-wider uppercase"
                />
              </div>
              <div>
                <label className="block text-[10px] text-slate-400 mb-1">Vehicle Type</label>
                <select
                  value={vehicleType}
                  onChange={(e) => setVehicleType(e.target.value)}
                  className="w-full bg-black/40 border border-ops-border rounded px-2 py-1.5 text-xs"
                >
                  <option>Car</option>
                  <option>Motorcycle</option>
                  <option>Truck</option>
                  <option>Van</option>
                  <option>Bus</option>
                  <option>Armored Vehicle</option>
                </select>
              </div>
            </div>
          </div>

          {/* Biometrics Photo Section */}
          <div className="space-y-2 border border-ops-border/70 bg-black/20 p-3 rounded-lg">
            <div className="flex items-center justify-between">
              <label className="block text-xs font-semibold text-slate-300">
                Biometric Facial Reference *
              </label>
              {/* Toggle Mode Buttons */}
              <div className="flex gap-1 bg-black/50 p-0.5 rounded border border-ops-border">
                <button
                  type="button"
                  onClick={() => switchMode('upload')}
                  className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${
                    captureMode === 'upload'
                      ? 'bg-ops-accent text-black font-semibold shadow-sm'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  📁 File
                </button>
                <button
                  type="button"
                  onClick={() => switchMode('camera')}
                  className={`px-2 py-0.5 rounded text-[11px] font-medium transition-all ${
                    captureMode === 'camera'
                      ? 'bg-ops-accent text-black font-semibold shadow-sm'
                      : 'text-slate-400 hover:text-white'
                  }`}
                >
                  📸 Live Camera
                </button>
              </div>
            </div>

            {/* Hidden canvas for taking snapshot */}
            <canvas ref={canvasRef} className="hidden" />

            {/* Camera Error alert with quick action buttons */}
            {cameraError && (
              <div className="text-[11px] text-red-300 bg-red-500/15 border border-red-500/40 p-2.5 rounded-lg space-y-2">
                <div className="flex items-start gap-1.5">
                  <span className="text-red-400 font-bold shrink-0">⚠️</span>
                  <span>{cameraError}</span>
                </div>
                <div className="flex items-center gap-2 pt-1 border-t border-red-500/20">
                  <button
                    type="button"
                    onClick={handleSwitchCamera}
                    className="px-2.5 py-1 bg-red-500/20 hover:bg-red-500/30 text-red-200 border border-red-500/40 rounded text-[10px] font-semibold flex items-center gap-1 transition-colors"
                  >
                    <span>🔄</span> Switch / Try Next Camera
                  </button>
                  <button
                    type="button"
                    onClick={() => switchMode('upload')}
                    className="px-2.5 py-1 bg-black/40 hover:bg-black/60 text-slate-300 border border-ops-border rounded text-[10px] flex items-center gap-1 transition-colors"
                  >
                    <span>📁</span> Use File Upload
                  </button>
                </div>
              </div>
            )}

            {/* Mode 1: File Upload */}
            {captureMode === 'upload' && !photoPreview && (
              <div>
                <input
                  type="file"
                  accept="image/*"
                  onChange={handlePhotoChange}
                  className="w-full text-xs text-slate-400 file:mr-2 file:py-1 file:px-2.5 file:rounded file:border-0 file:text-xs file:bg-ops-border file:text-slate-200 hover:file:bg-slate-700 cursor-pointer"
                  required={!photo}
                />
                <p className="text-[10px] text-slate-500 mt-1">
                  Upload a clear, front-facing JPEG or PNG portrait.
                </p>
              </div>
            )}

            {/* Mode 2: Live Camera View */}
            {captureMode === 'camera' && !photoPreview && (
              <div className="space-y-2">
                {!isCameraActive ? (
                  <div className="space-y-2">
                    <button
                      type="button"
                      onClick={() => startCamera(selectedDeviceId || undefined)}
                      className="w-full py-3 bg-black/40 hover:bg-black/60 border border-dashed border-ops-accent/70 hover:border-ops-accent rounded-lg flex flex-col items-center justify-center gap-1.5 transition-all group"
                    >
                      <span className="text-2xl group-hover:scale-110 transition-transform">📷</span>
                      <span className="text-xs font-semibold text-ops-accent">Start Live Camera</span>
                      <span className="text-[10px] text-slate-400">
                        Snap face photo directly using your webcam
                      </span>
                    </button>

                    {availableDevices.length > 1 && (
                      <div className="flex items-center justify-between p-2 rounded bg-black/30 border border-ops-border/50 text-xs">
                        <span className="text-[11px] text-slate-400 flex items-center gap-1">
                          <span>📹</span> Select Camera:
                        </span>
                        <select
                          value={selectedDeviceId}
                          onChange={(e) => {
                            setSelectedDeviceId(e.target.value)
                            startCamera(e.target.value)
                          }}
                          className="bg-black border border-ops-border rounded px-2 py-0.5 text-xs text-slate-200 max-w-[200px] truncate"
                        >
                          {availableDevices.map((d, i) => (
                            <option key={d.deviceId || i} value={d.deviceId}>
                              {d.label || `Camera ${i + 1}`}
                            </option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                ) : (
                  <div className="relative bg-black rounded-lg overflow-hidden border border-ops-accent shadow-lg">
                    {/* Live Video Feed */}
                    <video
                      ref={videoRef}
                      autoPlay
                      playsInline
                      muted
                      className="w-full h-52 object-cover"
                    />

                    {/* Live Badge & Switch Camera Header Overlay */}
                    <div className="absolute top-2 left-2 right-2 flex items-center justify-between pointer-events-auto">
                      <div className="flex items-center gap-1.5 px-2 py-0.5 rounded bg-black/75 border border-emerald-500/40 text-[10px] text-emerald-300 font-mono shadow">
                        <span className="w-2 h-2 rounded-full bg-emerald-400 animate-ping"></span>
                        <span>LIVE FEED</span>
                      </div>

                      <button
                        type="button"
                        onClick={handleSwitchCamera}
                        className="px-2.5 py-1 rounded bg-black/85 hover:bg-black border border-ops-accent/70 hover:border-ops-accent text-[11px] text-ops-accent font-semibold flex items-center gap-1.5 shadow transition-transform active:scale-95 cursor-pointer"
                        title="Switch to next camera device"
                      >
                        <span>🔄</span>
                        <span>Switch Camera</span>
                        {availableDevices.length > 1 && (
                          <span className="text-[9px] text-slate-400 font-normal">
                            ({availableDevices.findIndex((d) => d.deviceId === selectedDeviceId) + 1}/{availableDevices.length})
                          </span>
                        )}
                      </button>
                    </div>

                    {/* Tactical Corner Brackets */}
                    <div className="absolute top-2 right-2 w-4 h-4 border-t-2 border-r-2 border-ops-accent pointer-events-none"></div>
                    <div className="absolute bottom-12 left-2 w-4 h-4 border-b-2 border-l-2 border-ops-accent pointer-events-none"></div>
                    <div className="absolute bottom-12 right-2 w-4 h-4 border-b-2 border-r-2 border-ops-accent pointer-events-none"></div>

                    {/* Face Alignment Oval Guide */}
                    <div className="absolute inset-0 bottom-10 flex flex-col items-center justify-center pointer-events-none">
                      <div className="w-24 h-32 border-2 border-dashed border-ops-accent/80 rounded-full shadow-[0_0_15px_rgba(0,255,180,0.3)] flex items-center justify-center">
                        <span className="text-[8px] text-ops-accent font-mono tracking-widest uppercase bg-black/70 px-1 py-0.5 rounded">
                          FACE GUIDE
                        </span>
                      </div>
                      <div className="text-[9px] text-slate-300 bg-black/70 px-2 py-0.5 rounded mt-1 font-mono">
                        Center face inside oval
                      </div>
                    </div>

                    {/* Camera Control Bar */}
                    <div className="p-2 bg-black/80 border-t border-ops-border flex items-center gap-2">
                      <button
                        type="button"
                        onClick={handleCaptureSnapshot}
                        className="flex-1 bg-ops-accent hover:bg-ops-accent/90 text-black font-bold py-1.5 px-3 rounded text-xs flex items-center justify-center gap-1.5 shadow-md active:scale-95 transition-all"
                      >
                        <span>📸</span>
                        <span>Capture Snapshot</span>
                      </button>

                      {availableDevices.length > 1 && (
                        <button
                          type="button"
                          onClick={handleSwitchCamera}
                          className="px-2.5 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-600 rounded text-xs flex items-center gap-1"
                          title="Switch to next camera"
                        >
                          <span>🔄</span> Switch
                        </button>
                      )}

                      <button
                        type="button"
                        onClick={stopCamera}
                        className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded text-xs transition-colors"
                      >
                        Cancel
                      </button>
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* Photo Captured Preview (both modes) */}
            {photoPreview && (
              <div className="space-y-2">
                <div className="flex items-center gap-3 p-2.5 bg-black/40 border border-emerald-500/40 rounded-lg">
                  <div className="relative">
                    <img
                      src={photoPreview}
                      alt="Biometric Reference"
                      className="w-16 h-16 rounded-md object-cover border-2 border-emerald-400 shadow-sm"
                    />
                    <span className="absolute -top-1 -right-1 bg-emerald-500 text-black text-[9px] font-bold rounded-full w-4 h-4 flex items-center justify-center shadow">
                      ✓
                    </span>
                  </div>
                  <div className="flex-1 min-w-0">
                    <div className="text-xs font-semibold text-emerald-400 flex items-center gap-1">
                      <span>✓</span>
                      <span>
                        Face Photo Ready ({captureMode === 'camera' ? 'Camera Snapshot' : 'Uploaded File'})
                      </span>
                    </div>
                    <div className="text-[10px] text-slate-400 mt-0.5">
                      FaceNet-512 neural embedding will be computed upon enrollment
                    </div>
                    <button
                      type="button"
                      onClick={handleRetake}
                      className="mt-1.5 text-[11px] text-ops-accent hover:underline font-medium flex items-center gap-1"
                    >
                      <span>🔄</span> Retake / Choose another photo
                    </button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-ops-accent text-black font-semibold rounded py-2 text-sm disabled:opacity-50 transition-transform active:scale-[0.99]"
        >
          {loading ? 'Processing Biometrics…' : 'Enroll Personnel & Bind Vehicle'}
        </button>
      </form>

      {/* Enrolled Personnel Table */}
      <div className="col-span-2 panel p-5 space-y-4 border border-ops-border/60">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-bold text-slate-200 tracking-wide">
              ENROLLED PERSONNEL ({identities.length})
            </div>
            <div className="text-xs text-slate-400 mt-0.5">
              Authorized personnel with active face biometrics and cross-referenced vehicles.
            </div>
          </div>
          <button
            onClick={load}
            className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded border border-ops-border"
          >
            🔄 Refresh
          </button>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 text-xs border-b border-ops-border pb-2">
                <th className="pb-2">Personnel</th>
                <th>Clearance Level</th>
                <th>Role</th>
                <th>Unit / Wing</th>
                <th>Assigned Vehicle</th>
                <th>Biometrics</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {identities.map((id) => (
                <tr key={id.identity_id} className="border-b border-ops-border/40 hover:bg-white/[0.02]">
                  <td className="py-2.5">
                    <div className="font-semibold text-slate-200">{id.name}</div>
                    <div className="text-[11px] font-mono text-slate-500">{id.demo_id}</div>
                  </td>
                  <td>
                    <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-mono font-bold bg-amber-500/15 text-amber-300 border border-amber-500/30">
                      <span>{'⭐'.repeat(id.rank_stars || 1)}</span>
                      <span>L{id.rank_stars || 1}</span>
                    </span>
                    <div className="text-[10px] text-slate-400 truncate max-w-[140px]">
                      {id.rank_title || id.role}
                    </div>
                  </td>
                  <td className="text-slate-300">
                    <span className="px-2 py-0.5 rounded bg-slate-800 text-xs border border-slate-700">
                      {id.role}
                    </span>
                  </td>
                  <td className="text-slate-400 text-xs">{id.department || '—'}</td>
                  <td>
                    {id.plate_number ? (
                      <span className="inline-flex items-center gap-1.5 text-xs font-mono font-bold text-ops-accent bg-ops-accent/10 border border-ops-accent/30 rounded px-2 py-0.5">
                        <span>🚗</span>
                        <span>{id.plate_number}</span>
                        {id.vehicle_type && (
                          <span className="text-[10px] text-slate-400 font-sans font-normal">
                            ({id.vehicle_type})
                          </span>
                        )}
                      </span>
                    ) : (
                      <span className="text-slate-600 italic text-xs">None</span>
                    )}
                  </td>
                  <td>
                    {id.has_face_enrolled ? (
                      <span className="text-emerald-400 text-xs font-medium inline-flex items-center gap-1">
                        <span>✅</span> Enrolled
                      </span>
                    ) : (
                      <span className="text-amber-400 text-xs">⚠️ Pending</span>
                    )}
                  </td>
                  <td className="text-right">
                    <button
                      onClick={() => handleDelete(id.identity_id, id.name)}
                      className="text-red-400 hover:text-red-300 text-xs px-2 py-1 rounded hover:bg-red-500/10 transition-colors"
                    >
                      Revoke
                    </button>
                  </td>
                </tr>
              ))}
              {identities.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-slate-500 text-xs py-8 text-center">
                    No personnel enrolled yet. Use the form on the left to add authorized staff.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function VehicleTab() {
  const [vehicles, setVehicles] = useState<Vehicle[]>([])
  const [enrolledOwners, setEnrolledOwners] = useState<Identity[]>([])
  const [plate, setPlate] = useState('')
  const [vehicleType, setVehicleType] = useState('Car')
  const [ownerName, setOwnerName] = useState('')
  const [watchlist, setWatchlist] = useState(false)
  const [notes, setNotes] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [success, setSuccess] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [filterWatchlist, setFilterWatchlist] = useState(false)

  useEffect(() => {
    load()
    loadOwners()
  }, [filterWatchlist])

  async function load() {
    try {
      const res = await vehicleApi.list(filterWatchlist)
      setVehicles(res.data)
    } catch (err: any) {
      setError('Failed to fetch vehicle registry.')
    }
  }

  async function loadOwners() {
    try {
      const res = await identityApi.list()
      setEnrolledOwners(res.data)
    } catch (err: any) {
      // Non-blocking
    }
  }

  async function handleRegister(e: React.FormEvent) {
    e.preventDefault()
    setError(null)
    setSuccess(null)
    setLoading(true)

    const cleanPlate = plate.toUpperCase().replace(/\s/g, '')
    const matchedOwner = enrolledOwners.find(
      (o) => o.name.toLowerCase() === ownerName.trim().toLowerCase()
    )

    try {
      await vehicleApi.create({
        plate_number: cleanPlate,
        vehicle_type: vehicleType,
        owner_name: ownerName.trim() || undefined,
        owner_ref: matchedOwner?.identity_id,
        watchlist_flag: watchlist,
        notes: notes.trim() || undefined,
      })
      setSuccess(`Vehicle ${cleanPlate} registered successfully!`)
      setPlate('')
      setOwnerName('')
      setNotes('')
      setWatchlist(false)
      load()
    } catch (err: any) {
      setError(err?.response?.data?.detail || 'Registration failed. Plate may already exist.')
    } finally {
      setLoading(false)
    }
  }

  async function handleRemove(id: string, plateNum: string) {
    if (!confirm(`Remove vehicle ${plateNum} from the registry?`)) return
    try {
      await vehicleApi.remove(id)
      load()
    } catch (err: any) {
      setError('Failed to remove vehicle.')
    }
  }

  return (
    <div className="grid grid-cols-3 gap-6">
      {/* Registration Form */}
      <form onSubmit={handleRegister} className="panel p-5 space-y-4 h-fit border border-ops-border/60">
        <div>
          <div className="text-sm font-bold text-slate-200 tracking-wide">REGISTER VEHICLE</div>
          <div className="text-xs text-slate-400 mt-1">
            Register a license plate with owner details or flag it on the Threat Watchlist for immediate alert generation.
          </div>
        </div>

        {error && (
          <div className="bg-red-500/10 border border-red-500/40 text-red-300 rounded px-3 py-2 text-xs">
            {error}
          </div>
        )}
        {success && (
          <div className="bg-green-500/10 border border-green-500/40 text-green-300 rounded px-3 py-2 text-xs">
            {success}
          </div>
        )}

        <div className="space-y-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">License Plate Number *</label>
            <input
              placeholder="e.g. MH12AB1234"
              value={plate}
              onChange={(e) => setPlate(e.target.value.toUpperCase())}
              className="w-full bg-black/40 border border-ops-border rounded px-2.5 py-1.5 text-sm font-mono tracking-widest uppercase"
              required
            />
          </div>

          <div className="grid grid-cols-2 gap-2">
            <div>
              <label className="block text-xs text-slate-400 mb-1">Vehicle Type</label>
              <select
                value={vehicleType}
                onChange={(e) => setVehicleType(e.target.value)}
                className="w-full bg-black/40 border border-ops-border rounded px-2 py-1.5 text-sm"
              >
                <option>Car</option>
                <option>Truck</option>
                <option>Motorcycle</option>
                <option>Van</option>
                <option>Bus</option>
                <option>Armored Vehicle</option>
                <option>Unknown</option>
              </select>
            </div>
            <div>
              <label className="block text-xs text-slate-400 mb-1">Owner / Driver</label>
              <input
                list="enrolled-owners-list"
                placeholder="Type or select owner"
                value={ownerName}
                onChange={(e) => setOwnerName(e.target.value)}
                className="w-full bg-black/40 border border-ops-border rounded px-2 py-1.5 text-sm"
              />
              <datalist id="enrolled-owners-list">
                {enrolledOwners.map((o) => (
                  <option key={o.identity_id} value={o.name}>
                    {o.name} ({o.role})
                  </option>
                ))}
              </datalist>
            </div>
          </div>

          <div>
            <label className="block text-xs text-slate-400 mb-1">Notes (optional)</label>
            <textarea
              placeholder="e.g. Authorized logistics vehicle, Suspect in cross-border smuggling..."
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              rows={2}
              className="w-full bg-black/40 border border-ops-border rounded px-2 py-1.5 text-sm resize-none"
            />
          </div>

          {/* Threat Watchlist Toggle */}
          <label
            className={`flex items-center gap-3 p-3 rounded-lg border cursor-pointer transition-all ${
              watchlist
                ? 'border-red-500 bg-red-500/15 shadow-sm shadow-red-500/20'
                : 'border-ops-border/60 bg-black/20 hover:border-slate-500'
            }`}
          >
            <input
              type="checkbox"
              checked={watchlist}
              onChange={(e) => setWatchlist(e.target.checked)}
              className="w-4 h-4 accent-red-500 cursor-pointer"
            />
            <div>
              <div className={`text-sm font-bold ${watchlist ? 'text-red-400' : 'text-slate-300'}`}>
                🚨 Add to Threat Watchlist
              </div>
              <div className="text-xs text-slate-400">
                Instantly fires a RED priority alert on the dashboard when detected on any camera.
              </div>
            </div>
          </label>
        </div>

        <button
          type="submit"
          disabled={loading}
          className="w-full bg-ops-accent text-black font-semibold rounded py-2 text-sm disabled:opacity-50 transition-transform active:scale-[0.99]"
        >
          {loading ? 'Registering…' : watchlist ? 'Register Threat Vehicle' : 'Register Vehicle'}
        </button>
      </form>

      {/* Vehicle Registry Table */}
      <div className="col-span-2 panel p-5 space-y-4 border border-ops-border/60">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-bold text-slate-200 tracking-wide">
              VEHICLE REGISTRY ({vehicles.length})
            </div>
            <div className="text-xs text-slate-400 mt-0.5">
              Live ANPR database. Color-coded overlays will appear on active camera streams.
            </div>
          </div>
          <div className="flex items-center gap-3">
            <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={filterWatchlist}
                onChange={(e) => setFilterWatchlist(e.target.checked)}
                className="accent-red-500"
              />
              Show watchlist only
            </label>
            <button
              onClick={load}
              className="text-xs text-slate-400 hover:text-white px-2 py-1 rounded border border-ops-border"
            >
              🔄 Refresh
            </button>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 text-xs border-b border-ops-border pb-2">
                <th className="pb-2">Plate Number</th>
                <th>Type</th>
                <th>Owner / Driver</th>
                <th>Access Status</th>
                <th>Notes</th>
                <th className="text-right">Action</th>
              </tr>
            </thead>
            <tbody>
              {vehicles.map((v) => (
                <tr
                  key={v.vehicle_id}
                  className={`border-b border-ops-border/40 hover:bg-white/[0.02] ${
                    v.watchlist_flag ? 'bg-red-500/[0.04]' : ''
                  }`}
                >
                  <td className="py-2.5">
                    <span className="font-mono font-bold text-ops-accent tracking-wider text-sm bg-black/40 px-2 py-0.5 rounded border border-ops-border/60">
                      {v.plate_number}
                    </span>
                  </td>
                  <td className="text-slate-300 text-xs">{v.vehicle_type || '—'}</td>
                  <td>
                    {v.owner_name ? (
                      <span className="font-medium text-slate-200 text-xs flex items-center gap-1">
                        <span>👤</span> {v.owner_name}
                      </span>
                    ) : (
                      <span className="text-slate-600 italic text-xs">Unregistered</span>
                    )}
                  </td>
                  <td>
                    {v.watchlist_flag ? (
                      <span className="inline-flex items-center gap-1 text-red-400 font-bold text-[11px] px-2 py-0.5 bg-red-500/20 border border-red-500/40 rounded">
                        🚨 WATCHLIST
                      </span>
                    ) : (
                      <span className="inline-flex items-center gap-1 text-emerald-400 font-medium text-[11px] px-2 py-0.5 bg-emerald-500/15 border border-emerald-500/30 rounded">
                        ✓ Cleared
                      </span>
                    )}
                  </td>
                  <td className="text-slate-400 text-xs max-w-[150px] truncate" title={v.notes}>
                    {v.notes || '—'}
                  </td>
                  <td className="text-right">
                    <button
                      onClick={() => handleRemove(v.vehicle_id, v.plate_number)}
                      className="text-red-400 hover:text-red-300 text-xs px-2 py-1 rounded hover:bg-red-500/10 transition-colors"
                    >
                      Remove
                    </button>
                  </td>
                </tr>
              ))}
              {vehicles.length === 0 && (
                <tr>
                  <td colSpan={6} className="text-slate-500 text-xs py-8 text-center">
                    {filterWatchlist ? 'No threat watchlist vehicles registered.' : 'No vehicles registered yet.'}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  )
}

function GateLogTab() {
  const [detections, setDetections] = useState<AnprDetection[]>([])
  const [search, setSearch] = useState('')
  const [filter2fa, setFilter2fa] = useState('ALL')
  const [autoRefresh, setAutoRefresh] = useState(true)
  const [loading, setLoading] = useState(false)
  const [stats, setStats] = useState<{ total_vehicles: number; watchlist_count: number; total_detections: number } | null>(null)
  const [scanResult, setScanResult] = useState<ScanResult | null>(null)
  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState<string | null>(null)
  const [selectedSnapshot, setSelectedSnapshot] = useState<AnprDetection | null>(null)
  const [clearingSnapshots, setClearingSnapshots] = useState(false)
  const [clearMsg, setClearMsg] = useState<string | null>(null)
  const fileInputRef = useRef<HTMLInputElement>(null)

  async function handleClearSnapshots() {
    if (!window.confirm("Are you sure you want to delete all stored snapshots to free up space? This will delete all physical snapshot image files and clear DBMS snapshot records.")) {
      return
    }
    setClearingSnapshots(true)
    try {
      const res = await systemApi.clearAllSnapshots()
      setClearMsg(res.message || 'All snapshots successfully cleared.')
      setSelectedSnapshot(null)
      await load()
      await loadStats()
      setTimeout(() => setClearMsg(null), 6000)
    } catch (err: any) {
      alert(err?.response?.data?.detail || 'Failed to clear snapshots.')
    } finally {
      setClearingSnapshots(false)
    }
  }

  async function handleFileScan(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0]
    if (!file) return
    setScanning(true)
    setScanError(null)
    setScanResult(null)
    try {
      const res = await vehicleApi.scan(file)
      setScanResult(res.data)
      load()
      loadStats()
    } catch (err: any) {
      setScanError(err?.response?.data?.detail || 'ANPR scan failed.')
    } finally {
      setScanning(false)
      if (fileInputRef.current) fileInputRef.current.value = ''
    }
  }

  useEffect(() => {
    load()
    loadStats()
    if (!autoRefresh) return
    const interval = setInterval(() => {
      load()
      loadStats()
    }, 4000)
    return () => clearInterval(interval)
  }, [autoRefresh])

  async function load() {
    setLoading(true)
    try {
      const res = await vehicleApi.detections(100)
      setDetections(res.data)
    } catch {
      // Non-blocking
    } finally {
      setLoading(false)
    }
  }

  async function loadStats() {
    try {
      const res = await vehicleApi.stats()
      setStats(res.data)
    } catch {
      // Non-blocking
    }
  }

  const filtered = detections.filter((d) => {
    const matchSearch =
      !search ||
      d.plate_number.toLowerCase().includes(search.toLowerCase()) ||
      (d.owner_name && d.owner_name.toLowerCase().includes(search.toLowerCase())) ||
      (d.camera_name && d.camera_name.toLowerCase().includes(search.toLowerCase()))

    if (!matchSearch) return false

    if (filter2fa === 'VERIFIED') return d.driver_2fa === 'VERIFIED'
    if (filter2fa === 'MISMATCH') return d.driver_2fa === 'MISMATCH'
    if (filter2fa === 'WATCHLIST') return d.status === 'WATCHLIST'
    if (filter2fa === 'CLEARED') return d.status === 'CLEARED'
    return true
  })

  return (
    <div className="space-y-4">
      {/* Metric Cards */}
      <div className="grid grid-cols-4 gap-4">
        <div className="panel p-4 border border-ops-border/60 bg-black/30">
          <div className="text-[11px] text-slate-400 font-semibold tracking-wide">TOTAL DETECTIONS</div>
          <div className="text-2xl font-bold text-slate-100 mt-1">
            {stats ? stats.total_detections : detections.length}
          </div>
          <div className="text-[10px] text-slate-500 mt-0.5">Live ANPR vehicle gate events</div>
        </div>

        <div className="panel p-4 border border-red-500/40 bg-red-500/[0.05]">
          <div className="text-[11px] text-red-400 font-semibold tracking-wide flex items-center gap-1.5">
            <span>🚨</span> THREAT WATCHLIST INTERCEPTS
          </div>
          <div className="text-2xl font-bold text-red-300 mt-1">
            {detections.filter((d) => d.status === 'WATCHLIST').length}
          </div>
          <div className="text-[10px] text-red-400/70 mt-0.5">Flagged suspect vehicles</div>
        </div>

        <div className="panel p-4 border border-emerald-500/40 bg-emerald-500/[0.05]">
          <div className="text-[11px] text-emerald-400 font-semibold tracking-wide flex items-center gap-1.5">
            <span>🛡️</span> 2FA DRIVER VERIFIED
          </div>
          <div className="text-2xl font-bold text-emerald-300 mt-1">
            {detections.filter((d) => d.driver_2fa === 'VERIFIED').length}
          </div>
          <div className="text-[10px] text-emerald-400/70 mt-0.5">Face biometrics match registered owner</div>
        </div>

        <div className="panel p-4 border border-orange-500/40 bg-orange-500/[0.05]">
          <div className="text-[11px] text-orange-400 font-semibold tracking-wide flex items-center gap-1.5">
            <span>⚠️</span> DRIVER MISMATCHES
          </div>
          <div className="text-2xl font-bold text-orange-300 mt-1">
            {detections.filter((d) => d.driver_2fa === 'MISMATCH').length}
          </div>
          <div className="text-[10px] text-orange-400/70 mt-0.5">Unauthorized driver in registered car</div>
        </div>
      </div>

      {/* Controls */}
      <div className="panel p-4 border border-ops-border/60 flex items-center justify-between gap-4">
        <div className="flex items-center gap-3 flex-1">
          <input
            placeholder="Search by license plate, owner, or camera..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            className="bg-black/40 border border-ops-border rounded px-3 py-1.5 text-xs w-72"
          />
          <select
            value={filter2fa}
            onChange={(e) => setFilter2fa(e.target.value)}
            className="bg-black/40 border border-ops-border rounded px-2.5 py-1.5 text-xs"
          >
            <option value="ALL">All Event Types</option>
            <option value="VERIFIED">✓ 2FA Verified Drivers</option>
            <option value="MISMATCH">🚨 2FA Driver Mismatches</option>
            <option value="WATCHLIST">🚨 Watchlist Intercepts</option>
            <option value="CLEARED">✓ Cleared Vehicles</option>
          </select>
        </div>

        <div className="flex items-center gap-3">
          <label className="flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer select-none">
            <input
              type="checkbox"
              checked={autoRefresh}
              onChange={(e) => setAutoRefresh(e.target.checked)}
              className="accent-ops-accent"
            />
            Live Polling (4s)
          </label>
          <button
            onClick={() => {
              load()
              loadStats()
            }}
            disabled={loading}
            className="text-xs text-slate-300 hover:text-white px-3 py-1.5 rounded border border-ops-border hover:bg-white/5 transition-colors"
          >
            {loading ? 'Refreshing…' : '🔄 Refresh Now'}
          </button>

          <input
            type="file"
            ref={fileInputRef}
            onChange={handleFileScan}
            accept="image/*"
            className="hidden"
          />
          <button
            onClick={() => fileInputRef.current?.click()}
            disabled={scanning}
            className="text-xs bg-ops-accent/20 border border-ops-accent text-ops-accent hover:bg-ops-accent/30 px-3 py-1.5 rounded transition-colors font-medium flex items-center gap-1.5"
          >
            <span>📷</span> {scanning ? 'Scanning Plate…' : 'Test Scan Plate Image'}
          </button>

          <button
            onClick={handleClearSnapshots}
            disabled={clearingSnapshots}
            className="text-xs bg-red-500/15 border border-red-500/40 text-red-300 hover:bg-red-500/25 px-3 py-1.5 rounded transition-colors font-medium flex items-center gap-1.5 cursor-pointer shadow-sm"
            title="Delete all snapshot image files and DBMS snapshot records to free up disk space"
          >
            <span>🗑️</span> {clearingSnapshots ? 'Clearing…' : 'Clear Snapshots (Free Space)'}
          </button>
        </div>
      </div>

      {/* Clear Snapshots Status Alert */}
      {clearMsg && (
        <div className="bg-emerald-500/15 border border-emerald-500/40 text-emerald-200 text-xs p-3 rounded flex items-center justify-between animate-fadeIn">
          <span className="flex items-center gap-2">
            <span>✓</span> {clearMsg}
          </span>
          <button onClick={() => setClearMsg(null)} className="text-emerald-400 hover:text-white text-xs">✕</button>
        </div>
      )}

      {/* Interactive Scan Result Banner */}
      {scanResult && (
        <div className={`p-4 rounded border text-xs flex items-center justify-between transition-all ${
          scanResult.status === 'WATCHLIST_HIT'
            ? 'bg-red-500/15 border-red-500/40 text-red-200'
            : scanResult.status === 'REGISTERED'
            ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-200'
            : 'bg-sky-500/15 border-sky-500/40 text-sky-200'
        }`}>
          <div className="space-y-1">
            <div className="font-bold text-sm flex items-center gap-2">
              {scanResult.status === 'WATCHLIST_HIT' ? (
                <span className="text-red-400">🚨 THREAT WATCHLIST INTERCEPT DETECTED</span>
              ) : scanResult.status === 'REGISTERED' ? (
                <span className="text-emerald-400">✓ REGISTERED &amp; CLEARED VEHICLE</span>
              ) : (
                <span className="text-sky-400">ℹ️ VEHICLE PLATE DETECTED</span>
              )}
              <span className="font-mono bg-black/40 px-2 py-0.5 rounded text-white border border-white/20">
                {scanResult.plate_text || 'NO_PLATE'}
              </span>
              <span className="text-[11px] text-slate-300 font-normal">
                ({scanResult.confidence}% confidence {scanResult.is_fuzzy ? '• Fuzzy OCR Match' : ''})
              </span>
            </div>
            {scanResult.match && (
              <div className="text-slate-300 text-[11px] flex items-center gap-4">
                <span><strong>Owner:</strong> {scanResult.match.owner_name || 'N/A'}</span>
                <span><strong>Type:</strong> {scanResult.match.vehicle_type || 'Vehicle'}</span>
                {scanResult.match.notes && <span><strong>Notes:</strong> {scanResult.match.notes}</span>}
              </div>
            )}
          </div>
          <button
            onClick={() => setScanResult(null)}
            className="text-slate-400 hover:text-white text-xs px-2 py-1"
          >
            ✕ Close
          </button>
        </div>
      )}

      {scanError && (
        <div className="bg-red-500/10 border border-red-500/30 text-red-300 text-xs p-3 rounded flex items-center justify-between">
          <span>⚠️ {scanError}</span>
          <button onClick={() => setScanError(null)} className="text-red-400 hover:text-red-200">✕</button>
        </div>
      )}

      {/* Detection Table */}
      <div className="panel p-5 border border-ops-border/60">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-500 text-xs border-b border-ops-border pb-2">
                <th className="pb-2">Snapshot</th>
                <th className="pb-2">Timestamp</th>
                <th>Checkpoint / Camera</th>
                <th>License Plate</th>
                <th>Vehicle Type</th>
                <th>Registered Owner</th>
                <th>2-Factor Driver Verification</th>
                <th>Confidence</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((d) => {
                const dateStr = new Date(d.timestamp * 1000).toLocaleTimeString([], {
                  hour: '2-digit',
                  minute: '2-digit',
                  second: '2-digit',
                })
                return (
                  <tr key={d.detection_id} className="border-b border-ops-border/40 hover:bg-white/[0.02]">
                    <td className="py-2.5">
                      {d.snapshot_data || d.snapshot_url || d.snapshot_path ? (
                        <button
                          onClick={() => setSelectedSnapshot(d)}
                          className="group relative block w-14 h-9 rounded border border-ops-border/80 overflow-hidden bg-black/50 hover:border-ops-accent transition-all cursor-pointer shadow-sm hover:scale-105"
                          title="Click to view full snapshot & vehicle telemetry"
                        >
                          <img
                            src={d.snapshot_data || getSnapshotUrl(d.snapshot_url || d.snapshot_path)}
                            alt={d.plate_number}
                            className="w-full h-full object-cover"
                            loading="lazy"
                            onError={(e) => {
                              (e.target as HTMLElement).style.display = 'none'
                            }}
                          />
                          <div className="absolute inset-0 bg-black/20 group-hover:bg-transparent transition-colors flex items-center justify-center">
                            <span className="text-[10px] opacity-0 group-hover:opacity-100 transition-opacity drop-shadow">🔍</span>
                          </div>
                        </button>
                      ) : (
                        <div className="w-14 h-9 rounded border border-ops-border/40 bg-white/[0.02] flex items-center justify-center text-slate-600 text-[10px]">
                          <span>📷 None</span>
                        </div>
                      )}
                    </td>
                    <td className="py-3 font-mono text-xs text-slate-400">{dateStr}</td>
                    <td>
                      <span className="text-xs text-slate-300 font-medium">
                        {d.camera_name || d.camera_id}
                      </span>
                    </td>
                    <td>
                      <div className="inline-flex items-center gap-1.5">
                        <span className="font-mono font-bold text-ops-accent tracking-wider text-xs bg-black/40 px-2 py-0.5 rounded border border-ops-border/60">
                          {d.plate_number}
                        </span>
                        {d.is_fuzzy && (
                          <span className="text-[10px] text-amber-400 bg-amber-500/10 px-1.5 py-0.2 rounded border border-amber-500/30">
                            ~ Fuzzy Match
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="text-xs text-slate-400">{d.vehicle_type || 'Vehicle'}</td>
                    <td>
                      {d.owner_name ? (
                        <span className="text-xs text-slate-200 font-medium">👤 {d.owner_name}</span>
                      ) : (
                        <span className="text-slate-600 italic text-xs">Unregistered</span>
                      )}
                    </td>
                    <td>
                      {d.status === 'WATCHLIST' ? (
                        <span className="inline-flex items-center gap-1 text-red-400 font-bold text-[11px] px-2 py-0.5 bg-red-500/20 border border-red-500/40 rounded">
                          🚨 WATCHLIST INTERCEPT
                        </span>
                      ) : d.driver_2fa === 'VERIFIED' ? (
                        <span className="inline-flex items-center gap-1 text-emerald-400 font-bold text-[11px] px-2 py-0.5 bg-emerald-500/20 border border-emerald-500/40 rounded">
                          ✓ 2FA Verified (Driver = Owner)
                        </span>
                      ) : d.driver_2fa === 'MISMATCH' ? (
                        <span className="inline-flex items-center gap-1 text-orange-400 font-bold text-[11px] px-2 py-0.5 bg-orange-500/20 border border-orange-500/40 rounded animate-pulse">
                          🚨 Driver Mismatch
                        </span>
                      ) : d.driver_2fa === 'UNVERIFIED' ? (
                        <span className="inline-flex items-center gap-1 text-amber-400 font-medium text-[11px] px-2 py-0.5 bg-amber-500/10 border border-amber-500/30 rounded">
                          ⚠️ Unverified Driver
                        </span>
                      ) : d.status === 'CLEARED' ? (
                        <span className="inline-flex items-center gap-1 text-emerald-400 font-medium text-[11px] px-2 py-0.5 bg-emerald-500/15 border border-emerald-500/30 rounded">
                          ✓ Cleared Vehicle
                        </span>
                      ) : (
                        <span className="text-slate-500 text-xs">Detected</span>
                      )}
                    </td>
                    <td>
                      <span className="text-xs font-mono text-slate-400">
                        {Math.round((d.confidence || 0.85) * 100)}%
                      </span>
                    </td>
                  </tr>
                )
              })}
              {filtered.length === 0 && (
                <tr>
                  <td colSpan={8} className="text-slate-500 text-xs py-8 text-center">
                    No gate access events recorded yet. Once vehicles are detected on camera, their entry/exit logs will populate here.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* High-Resolution Vehicle Snapshot Modal */}
      {selectedSnapshot && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 animate-fade-in">
          <div className="bg-ops-surface border border-ops-border/80 rounded-lg max-w-2xl w-full overflow-hidden shadow-2xl space-y-4 p-6">
            <div className="flex items-center justify-between pb-3 border-b border-ops-border/60">
              <div className="flex items-center gap-2">
                <span className="text-lg">📷</span>
                <div>
                  <h3 className="text-sm font-bold text-slate-100">Vehicle Gate Snapshot</h3>
                  <div className="text-[11px] text-slate-400">
                    Detection ID: <span className="font-mono text-ops-accent">{selectedSnapshot.detection_id}</span>
                  </div>
                </div>
              </div>
              <button
                onClick={() => setSelectedSnapshot(null)}
                className="text-slate-400 hover:text-white text-sm p-1.5 rounded hover:bg-white/10 transition-colors"
              >
                ✕ Close
              </button>
            </div>

            {/* Snapshot Image with Status Glow */}
            <div className="relative rounded-lg overflow-hidden border border-ops-border bg-black/60 flex items-center justify-center min-h-[260px] max-h-[420px]">
              {selectedSnapshot.snapshot_data || selectedSnapshot.snapshot_url ? (
                <img
                  src={selectedSnapshot.snapshot_data || getSnapshotUrl(selectedSnapshot.snapshot_url || selectedSnapshot.snapshot_path)}
                  alt={selectedSnapshot.plate_number}
                  className="w-full h-full object-contain"
                  onError={(e) => {
                    const target = e.target as HTMLImageElement
                    target.style.display = 'none'
                    const fallback = document.getElementById(`modal-fallback-${selectedSnapshot.detection_id}`)
                    if (fallback) fallback.style.display = 'flex'
                  }}
                />
              ) : null}
              <div
                id={`modal-fallback-${selectedSnapshot.detection_id}`}
                className={`${selectedSnapshot.snapshot_data || selectedSnapshot.snapshot_url ? 'hidden' : 'flex'} text-slate-500 text-sm py-12 flex-col items-center gap-2`}
              >
                <span className="text-3xl">📷</span>
                <span>No high-resolution snapshot available for this record</span>
              </div>
              {/* Corner Tag */}
              <div className="absolute top-3 left-3 bg-black/70 backdrop-blur-md px-2.5 py-1 rounded border border-white/15 text-xs font-mono font-bold text-ops-accent">
                {selectedSnapshot.plate_number}
              </div>
            </div>

            {/* Metadata Grid */}
            <div className="grid grid-cols-3 gap-3 text-xs bg-black/30 p-3.5 rounded border border-ops-border/60">
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Verification Status</span>
                <span className={`font-bold mt-0.5 inline-block ${
                  selectedSnapshot.status === 'WATCHLIST' ? 'text-red-400' :
                  selectedSnapshot.driver_2fa === 'VERIFIED' ? 'text-emerald-400' :
                  selectedSnapshot.driver_2fa === 'MISMATCH' ? 'text-orange-400' : 'text-slate-300'
                }`}>
                  {selectedSnapshot.status === 'WATCHLIST' ? '🚨 WATCHLIST HIT' :
                   selectedSnapshot.driver_2fa === 'VERIFIED' ? '✓ 2FA VERIFIED' :
                   selectedSnapshot.driver_2fa === 'MISMATCH' ? '🚨 2FA MISMATCH' :
                   selectedSnapshot.status === 'CLEARED' ? '✓ CLEARED' : 'DETECTED'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Registered Owner</span>
                <span className="text-slate-200 font-medium mt-0.5 block">
                  {selectedSnapshot.owner_name || 'Unregistered Vehicle'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Checkpoint / Camera</span>
                <span className="text-slate-300 mt-0.5 block">
                  {selectedSnapshot.camera_name || selectedSnapshot.camera_id}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Vehicle Type</span>
                <span className="text-slate-300 mt-0.5 block">
                  {selectedSnapshot.vehicle_type || 'Vehicle'}
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Detection Confidence</span>
                <span className="font-mono text-slate-300 mt-0.5 block">
                  {Math.round((selectedSnapshot.confidence || 0.85) * 100)}%
                </span>
              </div>
              <div>
                <span className="text-slate-500 block text-[10px] uppercase font-semibold">Timestamp</span>
                <span className="font-mono text-slate-300 mt-0.5 block">
                  {new Date(selectedSnapshot.timestamp * 1000).toLocaleString()}
                </span>
              </div>
            </div>

            {/* Actions */}
            <div className="flex items-center justify-end gap-2.5 pt-2">
              {(selectedSnapshot.snapshot_data || selectedSnapshot.snapshot_url) && (
                <a
                  href={selectedSnapshot.snapshot_data || getSnapshotUrl(selectedSnapshot.snapshot_url || selectedSnapshot.snapshot_path)}
                  download={`gate_snapshot_${selectedSnapshot.plate_number}.jpg`}
                  target="_blank"
                  rel="noreferrer"
                  className="px-3 py-1.5 rounded border border-ops-border text-xs text-slate-300 hover:text-white hover:bg-white/5 transition-colors flex items-center gap-1.5 cursor-pointer"
                >
                  <span>⬇️</span> Download Image
                </a>
              )}
              <button
                onClick={() => setSelectedSnapshot(null)}
                className="px-4 py-1.5 rounded bg-ops-accent/20 border border-ops-accent text-ops-accent hover:bg-ops-accent/30 text-xs font-medium transition-colors cursor-pointer"
              >
                Close Modal
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
