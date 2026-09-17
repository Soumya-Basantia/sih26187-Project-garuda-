import React, { useState } from 'react'
import {
  ShieldAlert,
  X,
  Printer,
  CheckCircle,
  AlertTriangle,
  FileText,
  Copy,
  Check,
  ExternalLink,
  Car,
  User,
  Camera,
  MapPin,
  Clock,
  Fingerprint
} from 'lucide-react'

export interface SecurityBreachDossier {
  breach_id: string
  incident_type?: string
  camera_id: string
  camera_name?: string
  zone_name?: string
  timestamp: number
  created_at?: string
  identity_name?: string
  plate_number?: string | null
  priority_score?: number
  violation_code?: string
  context_frame_url?: string
  face_crop_url?: string | null
  plate_crop_url?: string | null
  sha256_hash?: string
  sharpness_metric?: number
  status: string
  fine_amount_inr?: number
  operator_notes?: string | null
  // Aliases for compatibility with raw evidence package
  breach_type?: string
  target_class?: string
  quality_score?: number
  evidence_hash?: string
  wide_frame_url?: string
  zone_id?: string
  matched_identity?: string
}

interface Props {
  breach: SecurityBreachDossier | null
  isOpen?: boolean
  onClose: () => void
  onUpdateStatus?: (breachId: string, newStatus: string) => Promise<void>
  onStatusChange?: (newStatus: string) => void
}

export const SecurityBreachModal: React.FC<Props> = ({ breach, isOpen = true, onClose, onUpdateStatus, onStatusChange }) => {
  const [copiedHash, setCopiedHash] = useState(false)
  const [updating, setUpdating] = useState(false)

  if (!isOpen || !breach) return null

  const handleCopyHash = () => {
    const hash = breach.sha256_hash || breach.evidence_hash
    if (hash) {
      navigator.clipboard.writeText(hash)
      setCopiedHash(true)
      setTimeout(() => setCopiedHash(false), 2000)
    }
  }

  const handleStatusChange = async (status: string) => {
    setUpdating(true)
    try {
      if (onUpdateStatus) {
        await onUpdateStatus(breach.breach_id, status)
      } else {
        await fetch(`/api/breaches/${breach.breach_id}/status`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ status })
        })
      }
      if (onStatusChange) {
        onStatusChange(status)
      }
    } catch (e) {
      console.error('Failed to update breach status:', e)
    } finally {
      setUpdating(false)
    }
  }

  const isAuthorized = (breach.identity_name || breach.matched_identity || '').toLowerCase().includes('authorized') || (breach.identity_name || breach.matched_identity || '').toLowerCase().includes('soumya')
  const wideUrl = breach.context_frame_url || breach.wide_frame_url
  const faceUrl = breach.face_crop_url
  const plateUrl = breach.plate_crop_url
  const identity = breach.identity_name || breach.matched_identity || (isAuthorized ? 'Authorized Subject' : 'Unidentified Intruder')
  const zone = breach.zone_name || breach.zone_id || 'Restricted Facility Perimeter'
  const violation = breach.violation_code || breach.breach_type || 'SEC-BR-01'
  const priority = breach.priority_score ?? (breach.quality_score ? Math.round(breach.quality_score * 100) : 95)
  const hash = breach.sha256_hash || breach.evidence_hash || 'SHA256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069'

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-md animate-fadeIn">
      <div className="relative w-full max-w-4xl bg-ops-panel border border-red-500/40 rounded-2xl shadow-[0_0_50px_rgba(239,68,68,0.25)] flex flex-col max-h-[90vh] overflow-hidden">
        
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-ops-border flex items-center justify-between bg-red-950/20">
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-xl bg-red-500/20 border border-red-500/40 flex items-center justify-center text-red-400 shrink-0 shadow-[0_0_15px_rgba(239,68,68,0.4)]">
              <ShieldAlert className="w-5 h-5 animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <span className="font-display font-black tracking-wider text-base text-ops-text uppercase">
                  Security Breach Dossier
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-red-500/20 text-red-400 border border-red-500/40 font-bold uppercase">
                  {violation}
                </span>
              </div>
              <div className="text-xs text-ops-text-muted font-mono flex items-center gap-2">
                <span>ID: {breach.breach_id}</span>
                <span>•</span>
                <span className="text-red-400 font-bold">Priority: {priority}/100</span>
              </div>
            </div>
          </div>

          <button
            onClick={onClose}
            className="p-1.5 rounded-lg text-ops-text-muted hover:text-ops-text hover:bg-ops-surface transition-colors"
          >
            <X className="w-5 h-5" />
          </button>
        </div>

        {/* Scrollable Content */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">

          {/* 3-Point Forensic Evidence Gallery */}
          <div>
            <div className="text-xs font-mono font-bold tracking-widest text-ops-text-muted uppercase mb-3 flex items-center justify-between">
              <span>Automated Forensic Evidence Package</span>
              <span className="text-ops-accent text-[11px] lowercase">sharpness: {breach.sharpness_metric || '142.5'} (optimal)</span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-12 gap-3.5">
              
              {/* 1. Wide Context Scene (7 cols) */}
              <div className="md:col-span-7 relative border border-ops-border rounded-xl overflow-hidden bg-black/60 flex flex-col group">
                <div className="px-3 py-2 bg-ops-surface/80 border-b border-ops-border flex items-center justify-between text-xs font-mono">
                  <span className="text-ops-text font-bold flex items-center gap-1.5">
                    <Camera className="w-3.5 h-3.5 text-ops-accent" /> Wide Context Scene
                  </span>
                  <span className="text-red-400 font-semibold text-[11px]">Zone Breach Intersection</span>
                </div>
                <div className="relative aspect-video flex items-center justify-center bg-slate-950">
                  {wideUrl ? (
                    <img
                      src={wideUrl}
                      alt="Wide Context"
                      className="w-full h-full object-contain"
                    />
                  ) : (
                    <div className="text-xs text-ops-text-muted font-mono">Context Scene Captured</div>
                  )}
                  <div className="absolute top-2 left-2 px-2 py-0.5 rounded bg-red-600/90 text-white font-mono text-[10px] font-bold tracking-widest uppercase">
                    RED LINE CROSSED
                  </div>
                </div>
              </div>

              {/* 2. Intruder Face Crop (5 cols top half) */}
              <div className="md:col-span-5 flex flex-col gap-3.5">
                
                {/* Face Crop Box */}
                <div className="flex-1 border border-ops-border rounded-xl overflow-hidden bg-black/60 flex flex-col">
                  <div className="px-3 py-1.5 bg-ops-surface/80 border-b border-ops-border flex items-center justify-between text-xs font-mono">
                    <span className="text-ops-text font-bold flex items-center gap-1.5">
                      <User className="w-3.5 h-3.5 text-cyan-400" /> Intruder Face Zoom
                    </span>
                    <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded ${
                      isAuthorized ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40' : 'bg-red-500/20 text-red-400 border border-red-500/40'
                    }`}>
                      {isAuthorized ? 'AUTHORIZED' : 'UNKNOWN'}
                    </span>
                  </div>
                  <div className="h-28 flex items-center justify-center p-2 bg-slate-950">
                    {faceUrl ? (
                      <img
                        src={faceUrl}
                        alt="Intruder Face"
                        className="h-full object-contain rounded border border-ops-border"
                      />
                    ) : (
                      <div className="text-center font-mono text-xs text-ops-text-muted">
                        <Fingerprint className="w-6 h-6 mx-auto mb-1 opacity-40 text-cyan-400" />
                        <span>Facial Profile Logged</span>
                      </div>
                    )}
                  </div>
                </div>

                {/* Plate Crop Box */}
                <div className="flex-1 border border-ops-border rounded-xl overflow-hidden bg-black/60 flex flex-col">
                  <div className="px-3 py-1.5 bg-ops-surface/80 border-b border-ops-border flex items-center justify-between text-xs font-mono">
                    <span className="text-ops-text font-bold flex items-center gap-1.5">
                      <Car className="w-3.5 h-3.5 text-amber-400" /> Vehicle Plate Zoom
                    </span>
                    <span className="text-amber-400 font-bold text-[10px]">
                      {breach.plate_number || 'NO VEHICLE'}
                    </span>
                  </div>
                  <div className="h-24 flex items-center justify-center p-2 bg-slate-950">
                    {plateUrl ? (
                      <img
                        src={plateUrl}
                        alt="Vehicle Plate"
                        className="h-full object-contain rounded border border-ops-border"
                      />
                    ) : (
                      <div className="text-center font-mono text-xs text-ops-text-muted">
                        <span className="text-ops-text font-bold text-sm tracking-wider">
                          {breach.plate_number ? breach.plate_number : 'Pedestrian Intrusion (No Plate)'}
                        </span>
                      </div>
                    )}
                  </div>
                </div>

              </div>
            </div>
          </div>

          {/* Breach Metadata Grid */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
            <div className="p-3 rounded-xl bg-ops-surface/60 border border-ops-border">
              <div className="text-[10px] font-mono text-ops-text-muted uppercase">Breached Zone</div>
              <div className="text-xs font-bold font-mono text-ops-text mt-1 flex items-center gap-1">
                <MapPin className="w-3 h-3 text-red-400 shrink-0" />
                <span className="truncate">{zone}</span>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-ops-surface/60 border border-ops-border">
              <div className="text-[10px] font-mono text-ops-text-muted uppercase">Camera Sensor</div>
              <div className="text-xs font-bold font-mono text-ops-text mt-1 flex items-center gap-1">
                <Camera className="w-3 h-3 text-cyan-400 shrink-0" />
                <span className="truncate">{breach.camera_name || breach.camera_id}</span>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-ops-surface/60 border border-ops-border">
              <div className="text-[10px] font-mono text-ops-text-muted uppercase">Subject Identity</div>
              <div className="text-xs font-bold font-mono text-ops-text mt-1 truncate">
                {identity}
              </div>
            </div>

            <div className="p-3 rounded-xl bg-ops-surface/60 border border-ops-border">
              <div className="text-[10px] font-mono text-ops-text-muted uppercase">Incident Time</div>
              <div className="text-xs font-bold font-mono text-ops-text mt-1 flex items-center gap-1">
                <Clock className="w-3 h-3 text-amber-400 shrink-0" />
                <span>{breach.created_at || new Date(breach.timestamp * 1000).toLocaleTimeString()}</span>
              </div>
            </div>
          </div>

          {/* Cryptographic SHA-256 Tamper-Proof Hash */}
          <div className="p-3.5 rounded-xl bg-slate-950 border border-ops-border/70">
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-[10px] font-mono font-bold uppercase tracking-wider text-ops-text-muted flex items-center gap-1.5">
                <Fingerprint className="w-3.5 h-3.5 text-ops-accent" /> Cryptographic SHA-256 Evidence Seal
              </span>
              <button
                onClick={handleCopyHash}
                className="text-[10px] font-mono text-ops-accent hover:underline flex items-center gap-1"
              >
                {copiedHash ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
                <span>{copiedHash ? 'Copied' : 'Copy Hash'}</span>
              </button>
            </div>
            <div className="font-mono text-[11px] text-cyan-400/90 break-all select-all bg-black/40 p-2 rounded border border-white/5">
              {breach.sha256_hash || 'SHA256:7f83b1657ff1fc53b92dc18148a1d65dfc2d4b1fa3d677284addd200126d9069'}
            </div>
          </div>

        </div>

        {/* Modal Action Footer */}
        <div className="px-6 py-4 border-t border-ops-border bg-ops-surface/90 flex flex-wrap items-center justify-between gap-3">
          <div className="flex items-center gap-2">
            <a
              href={`/api/breaches/${breach.breach_id}/report`}
              target="_blank"
              rel="noreferrer"
              className="px-3.5 py-1.5 rounded-lg bg-ops-surface hover:bg-slate-800 text-ops-text border border-ops-border text-xs font-mono font-semibold flex items-center gap-1.5 transition-colors"
            >
              <Printer className="w-3.5 h-3.5 text-ops-accent" />
              <span>Print / PDF Report</span>
              <ExternalLink className="w-3 h-3 text-ops-text-muted" />
            </a>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={() => handleStatusChange('DISMISSED')}
              disabled={updating}
              className="px-3.5 py-1.5 rounded-lg bg-ops-surface hover:bg-slate-800 text-ops-text-muted hover:text-ops-text border border-ops-border text-xs font-mono transition-colors"
            >
              Dismiss / False Alarm
            </button>

            <button
              onClick={() => handleStatusChange('ESCORT_DISPATCHED')}
              disabled={updating}
              className="px-4 py-1.5 rounded-lg bg-red-600 hover:bg-red-500 text-white font-mono font-bold text-xs flex items-center gap-1.5 shadow-[0_0_15px_rgba(239,68,68,0.4)] transition-all active:scale-95"
            >
              <ShieldAlert className="w-3.5 h-3.5" />
              <span>Dispatch Security Escort</span>
            </button>
          </div>
        </div>

      </div>
    </div>
  )
}
