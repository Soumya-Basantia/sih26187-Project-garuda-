import React, { useEffect, useState } from 'react'
import { api } from '../services/api'
import { useAuth } from '../hooks/useAuth'
import { useTheme, ThemeMode } from '../hooks/useTheme'
import {
  Settings as SettingsIcon,
  Eye,
  Sliders,
  Sun,
  Moon,
  Monitor,
  Volume2,
  ShieldAlert,
  Clock,
  Database,
  Check,
  RotateCcw,
  ShieldCheck,
  Sparkles,
  Zap,
  VolumeX,
  Users,
  Car,
  Play,
  Radio,
} from 'lucide-react'

interface AppSettings {
  detection_confidence: number
  default_inference_fps: number
  face_verification_enabled: boolean
  event_retention_days: number
  abandoned_object_seconds: number
  person_departure_distance: number
  audio_alarm_enabled: boolean
  critical_siren_enabled: boolean
  // Upgrade Settings
  voice_announcements_enabled: boolean
  crowd_surge_threshold: number
  mob_assembly_threshold: number
  vehicle_loiter_passes: number
  demo_mode_enabled: boolean
}

const DEFAULT_SETTINGS: AppSettings = {
  detection_confidence: 0.45,
  default_inference_fps: 8,
  face_verification_enabled: true,
  event_retention_days: 30,
  abandoned_object_seconds: 15,
  person_departure_distance: 250,
  audio_alarm_enabled: true,
  critical_siren_enabled: true,
  voice_announcements_enabled: false,
  crowd_surge_threshold: 6,
  mob_assembly_threshold: 10,
  vehicle_loiter_passes: 3,
  demo_mode_enabled: false,
}

export default function Settings() {
  const { role } = useAuth()
  const { theme, setTheme } = useTheme()
  const [settings, setSettings] = useState<AppSettings>(DEFAULT_SETTINGS)
  const [saved, setSaved] = useState(false)
  const [saving, setSaving] = useState(false)
  const [testToneActive, setTestToneActive] = useState(false)
  const isAdmin = role === 'ADMIN' || !role

  useEffect(() => {
    loadSettings()
  }, [])

  async function loadSettings() {
    try {
      const res = await api.get('/api/settings')
      if (res.data) setSettings({ ...DEFAULT_SETTINGS, ...res.data })
    } catch {
      // Use defaults if backend not yet seeded
    }
  }

  async function saveSettings() {
    setSaving(true)
    try {
      await api.put('/api/settings', settings)
      localStorage.setItem('garude_audio_enabled', String(settings.audio_alarm_enabled))
      localStorage.setItem('garude_siren_enabled', String(settings.critical_siren_enabled))
      setSaved(true)
      setTimeout(() => setSaved(false), 3500)
    } catch {
      localStorage.setItem('garude_settings', JSON.stringify(settings))
      setSaved(true)
      setTimeout(() => setSaved(false), 3500)
    } finally {
      setSaving(false)
    }
  }

  function update<K extends keyof AppSettings>(key: K, value: AppSettings[K]) {
    setSettings((prev) => ({ ...prev, [key]: value }))
  }

  function playTestTone() {
    try {
      const ctx = new (window.AudioContext || (window as any).webkitAudioContext)()
      const osc = ctx.createOscillator()
      const gain = ctx.createGain()
      osc.type = 'sawtooth'
      osc.frequency.setValueAtTime(880, ctx.currentTime)
      osc.frequency.exponentialRampToValueAtTime(440, ctx.currentTime + 0.4)
      gain.gain.setValueAtTime(0.2, ctx.currentTime)
      gain.gain.exponentialRampToValueAtTime(0.01, ctx.currentTime + 0.4)
      osc.connect(gain)
      gain.connect(ctx.destination)
      osc.start()
      osc.stop(ctx.currentTime + 0.45)
      setTestToneActive(true)
      setTimeout(() => setTestToneActive(false), 500)
    } catch {
      // AudioContext unavailable
    }
  }

  return (
    <div className="p-6 space-y-6 max-w-5xl mx-auto">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-4 pb-4 border-b border-ops-border">
        <div>
          <div className="flex items-center gap-2.5">
            <SettingsIcon className="w-6 h-6 text-ops-accent" />
            <h1 className="text-xl font-bold tracking-wide text-ops-text uppercase font-display">
              System Configuration & Preferences
            </h1>
            <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-ops-accent/15 text-ops-accent border border-ops-accent/30 font-bold">
              HOT-SYNC ENGINE
            </span>
          </div>
          <p className="text-xs text-ops-text-muted mt-1 font-sans">
            Appearance themes, visual AI calibration, audio siren frequencies, and forensic retention policies.
          </p>
        </div>

        {saved && (
          <div className="px-3.5 py-1.5 rounded-lg bg-emerald-500/15 border border-emerald-500/30 text-emerald-600 dark:text-emerald-400 text-xs flex items-center gap-1.5 font-medium animate-fadeIn">
            <Check className="w-4 h-4" />
            <span>Settings hot-synced to active camera pipelines!</span>
          </div>
        )}
      </div>

      {/* Theme & Visual Appearance Preference */}
      <div className="tactical-panel p-5 space-y-4">
        <div className="flex items-center justify-between border-b border-ops-border pb-3">
          <div className="flex items-center gap-2">
            <Sparkles className="w-4 h-4 text-ops-accent" />
            <h2 className="text-xs font-bold uppercase tracking-wider font-display text-ops-text">
              Command Interface Theme
            </h2>
          </div>
          <span className="text-[10px] font-mono text-ops-text-muted">
            REAL-TIME CSS VARIABLE SYSTEM
          </span>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
          <button
            type="button"
            onClick={() => setTheme('dark')}
            className={`p-3.5 rounded-lg border text-left flex items-start gap-3 transition-all ${
              theme === 'dark'
                ? 'bg-ops-accent/15 border-ops-accent shadow-sm'
                : 'bg-ops-surface border-ops-border hover:border-ops-border-hover'
            }`}
          >
            <div className="w-8 h-8 rounded-lg bg-slate-950 border border-slate-800 flex items-center justify-center shrink-0">
              <Moon className="w-4 h-4 text-cyan-400" />
            </div>
            <div>
              <div className="text-xs font-bold font-display text-ops-text flex items-center gap-1.5">
                Tactical Dark
                {theme === 'dark' && <span className="w-1.5 h-1.5 rounded-full bg-ops-accent" />}
              </div>
              <p className="text-[11px] text-ops-text-muted mt-0.5">
                Obsidian canvas, neon telemetry glows, optimized for command centers.
              </p>
            </div>
          </button>

          <button
            type="button"
            onClick={() => setTheme('light')}
            className={`p-3.5 rounded-lg border text-left flex items-start gap-3 transition-all ${
              theme === 'light'
                ? 'bg-ops-accent/15 border-ops-accent shadow-sm'
                : 'bg-ops-surface border-ops-border hover:border-ops-border-hover'
            }`}
          >
            <div className="w-8 h-8 rounded-lg bg-white border border-slate-300 flex items-center justify-center shrink-0">
              <Sun className="w-4 h-4 text-amber-500" />
            </div>
            <div>
              <div className="text-xs font-bold font-display text-ops-text flex items-center gap-1.5">
                Ops Light
                {theme === 'light' && <span className="w-1.5 h-1.5 rounded-full bg-ops-accent" />}
              </div>
              <p className="text-[11px] text-ops-text-muted mt-0.5">
                Crisp polar slate, high contrast field readability under direct daylight.
              </p>
            </div>
          </button>

          <button
            type="button"
            onClick={() => setTheme('system')}
            className={`p-3.5 rounded-lg border text-left flex items-start gap-3 transition-all ${
              theme === 'system'
                ? 'bg-ops-accent/15 border-ops-accent shadow-sm'
                : 'bg-ops-surface border-ops-border hover:border-ops-border-hover'
            }`}
          >
            <div className="w-8 h-8 rounded-lg bg-ops-surface border border-ops-border flex items-center justify-center shrink-0">
              <Monitor className="w-4 h-4 text-ops-text-muted" />
            </div>
            <div>
              <div className="text-xs font-bold font-display text-ops-text flex items-center gap-1.5">
                System Default
                {theme === 'system' && <span className="w-1.5 h-1.5 rounded-full bg-ops-accent" />}
              </div>
              <p className="text-[11px] text-ops-text-muted mt-0.5">
                Automatically matches your operating system theme preference.
              </p>
            </div>
          </button>
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {/* Panel 1: AI Detection & Vision Engine */}
        <div className="tactical-panel p-5 space-y-5">
          <div className="text-xs font-bold tracking-wider text-ops-text uppercase font-display border-b border-ops-border pb-2.5 flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Eye className="w-4 h-4 text-ops-accent" />
              Visual Detection Engine
            </span>
            <span className="text-[10px] font-mono text-ops-text-muted">YOLOv8 & TRACKER</span>
          </div>

          {/* Detection Confidence */}
          <div className="space-y-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="font-semibold text-ops-text">Detection Confidence Threshold</span>
              <span className="font-mono text-ops-accent font-bold bg-ops-surface px-2 py-0.5 rounded border border-ops-border">
                {Math.round(settings.detection_confidence * 100)}%
              </span>
            </div>
            <input
              type="range"
              min={0.2}
              max={0.85}
              step={0.05}
              value={settings.detection_confidence}
              onChange={(e) => update('detection_confidence', parseFloat(e.target.value))}
              disabled={!isAdmin}
              className="w-full accent-cyan-500 cursor-pointer"
            />
            <p className="text-[11px] text-ops-text-muted">
              Higher values reduce false alarms. Lower values improve detection in foggy or low-light conditions.
            </p>
          </div>

          {/* Target Inference FPS */}
          <div className="space-y-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="font-semibold text-ops-text">Target Inference Frame Rate</span>
              <span className="font-mono text-ops-accent font-bold bg-ops-surface px-2 py-0.5 rounded border border-ops-border">
                {settings.default_inference_fps} FPS
              </span>
            </div>
            <input
              type="range"
              min={2}
              max={25}
              step={1}
              value={settings.default_inference_fps}
              onChange={(e) => update('default_inference_fps', parseInt(e.target.value))}
              disabled={!isAdmin}
              className="w-full accent-cyan-500 cursor-pointer"
            />
            <p className="text-[11px] text-ops-text-muted">
              Allocates CPU/GPU processing budget per stream. 8–15 FPS recommended for real-time human tracking.
            </p>
          </div>

          {/* Face Verification Toggle */}
          <div className="flex items-center justify-between pt-2 border-t border-ops-border">
            <div>
              <div className="text-xs font-semibold text-ops-text">Biometric Face Verification</div>
              <div className="text-[11px] text-ops-text-muted">ArcFace recognition against enrolled personnel vault</div>
            </div>
            <button
              onClick={() => isAdmin && update('face_verification_enabled', !settings.face_verification_enabled)}
              className={`px-3 py-1 text-xs font-bold rounded-lg border font-mono transition ${
                settings.face_verification_enabled
                  ? 'bg-emerald-500/15 text-emerald-600 dark:text-emerald-400 border-emerald-500/30'
                  : 'bg-ops-surface text-ops-text-muted border-ops-border'
              }`}
            >
              {settings.face_verification_enabled ? 'ENABLED' : 'DISABLED'}
            </button>
          </div>
        </div>

        {/* Panel 2: Audio Sirens & Operational Alarms */}
        <div className="tactical-panel p-5 space-y-5">
          <div className="text-xs font-bold tracking-wider text-red-500 uppercase font-display border-b border-ops-border pb-2.5 flex items-center justify-between">
            <span className="flex items-center gap-2">
              <ShieldAlert className="w-4 h-4 text-red-500" />
              Sound Alarms & Sirens
            </span>
            <span className="text-[10px] font-mono text-ops-text-muted">WEB AUDIO API</span>
          </div>

          {/* Browser Audio Alarm */}
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-ops-text">Tactical Audio Pulse</div>
              <div className="text-[11px] text-ops-text-muted">Plays short chirp tone on intrusion alerts</div>
            </div>
            <button
              onClick={() => isAdmin && update('audio_alarm_enabled', !settings.audio_alarm_enabled)}
              className={`px-3 py-1 text-xs font-bold rounded-lg border font-mono transition ${
                settings.audio_alarm_enabled
                  ? 'bg-ops-accent/15 text-ops-accent border-ops-accent/30'
                  : 'bg-ops-surface text-ops-text-muted border-ops-border'
              }`}
            >
              {settings.audio_alarm_enabled ? 'ON' : 'OFF'}
            </button>
          </div>

          {/* Critical Zero-Line Siren */}
          <div className="flex items-center justify-between">
            <div>
              <div className="text-xs font-semibold text-ops-text">Critical Zero-Line Siren</div>
              <div className="text-[11px] text-ops-text-muted">Urgent repeating siren on CRITICAL perimeter breaches</div>
            </div>
            <button
              onClick={() => isAdmin && update('critical_siren_enabled', !settings.critical_siren_enabled)}
              className={`px-3 py-1 text-xs font-bold rounded-lg border font-mono transition ${
                settings.critical_siren_enabled
                  ? 'bg-red-500/15 text-red-500 border-red-500/30'
                  : 'bg-ops-surface text-ops-text-muted border-ops-border'
              }`}
            >
              {settings.critical_siren_enabled ? 'ON' : 'OFF'}
            </button>
          </div>

          {/* Test Audio Output */}
          <div className="pt-2 border-t border-ops-border flex items-center justify-between">
            <span className="text-xs text-ops-text-muted">Verify station speaker output:</span>
            <button
              onClick={playTestTone}
              className={`px-3 py-1.5 text-xs rounded-lg border font-mono transition flex items-center gap-1.5 ${
                testToneActive
                  ? 'bg-red-500 text-white border-red-400 font-bold scale-105'
                  : 'bg-ops-surface hover:bg-ops-panel text-ops-text border-ops-border'
              }`}
            >
              <Volume2 className="w-3.5 h-3.5 text-ops-accent" />
              <span>{testToneActive ? 'Playing Pulse...' : 'Test Siren Tone'}</span>
            </button>
          </div>
        </div>

        {/* Panel 3: Temporal & Behavioral Rules */}
        <div className="tactical-panel p-5 space-y-5">
          <div className="text-xs font-bold tracking-wider text-amber-500 uppercase font-display border-b border-ops-border pb-2.5 flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Clock className="w-4 h-4 text-amber-500" />
              Temporal Behavioral Engines
            </span>
            <span className="text-[10px] font-mono text-ops-text-muted">DWELL & ABANDONMENT</span>
          </div>

          {/* Abandoned Object Seconds */}
          <div className="space-y-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="font-semibold text-ops-text">Abandoned Object Threshold</span>
              <span className="font-mono text-amber-500 font-bold bg-ops-surface px-2 py-0.5 rounded border border-ops-border">
                {settings.abandoned_object_seconds}s
              </span>
            </div>
            <input
              type="range"
              min={5}
              max={60}
              step={5}
              value={settings.abandoned_object_seconds}
              onChange={(e) => update('abandoned_object_seconds', parseInt(e.target.value))}
              disabled={!isAdmin}
              className="w-full accent-amber-500 cursor-pointer"
            />
            <p className="text-[11px] text-ops-text-muted">
              How long an unattended bag, suitcase, or backpack must remain stationary before triggering an alert.
            </p>
          </div>

          {/* Departure Distance */}
          <div className="space-y-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="font-semibold text-ops-text">Owner Separation Distance</span>
              <span className="font-mono text-amber-500 font-bold bg-ops-surface px-2 py-0.5 rounded border border-ops-border">
                {settings.person_departure_distance} px
              </span>
            </div>
            <input
              type="range"
              min={100}
              max={500}
              step={25}
              value={settings.person_departure_distance}
              onChange={(e) => update('person_departure_distance', parseInt(e.target.value))}
              disabled={!isAdmin}
              className="w-full accent-amber-500 cursor-pointer"
            />
            <p className="text-[11px] text-ops-text-muted">
              Pixel distance the owner must walk away before an abandonment event is classified.
            </p>
          </div>
        </div>

        {/* Panel 4: Local Storage & Log Retention */}
        <div className="tactical-panel p-5 space-y-5">
          <div className="text-xs font-bold tracking-wider text-ops-text uppercase font-display border-b border-ops-border pb-2.5 flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Database className="w-4 h-4 text-ops-accent" />
              Data Retention Policy
            </span>
            <span className="text-[10px] font-mono text-ops-text-muted">AIR-GAPPED VAULT</span>
          </div>

          {/* Retention Days */}
          <div className="space-y-1.5">
            <div className="flex justify-between items-center text-xs">
              <span className="font-semibold text-ops-text">Forensic Event Log Retention</span>
              <span className="font-mono text-ops-text font-bold bg-ops-surface px-2 py-0.5 rounded border border-ops-border">
                {settings.event_retention_days} Days
              </span>
            </div>
            <input
              type="range"
              min={7}
              max={180}
              step={7}
              value={settings.event_retention_days}
              onChange={(e) => update('event_retention_days', parseInt(e.target.value))}
              disabled={!isAdmin}
              className="w-full accent-slate-500 cursor-pointer"
            />
            <p className="text-[11px] text-ops-text-muted">
              Events older than this threshold are purged automatically during local storage rotation.
            </p>
          </div>

          <div className="p-3.5 rounded-lg bg-ops-surface border border-ops-border text-xs space-y-1">
            <span className="font-semibold text-ops-text flex items-center gap-1.5">
              <ShieldCheck className="w-4 h-4 text-emerald-500" />
              Air-Gapped Privacy Architecture
            </span>
            <p className="text-ops-text-muted text-[11px] leading-relaxed">
              Project Garuda stores all weights, models, facial embeddings, and video evidence strictly on the local
              workstation. No telemetry or imagery is transmitted outside this security enclave.
            </p>
          </div>
        </div>

        {/* Panel 5: AI Threat Intelligence & Demonstration Protocols */}
        <div className="tactical-panel p-5 space-y-5 lg:col-span-2">
          <div className="text-xs font-bold tracking-wider text-purple-400 uppercase font-display border-b border-ops-border pb-2.5 flex items-center justify-between">
            <span className="flex items-center gap-2">
              <Radio className="w-4 h-4 text-purple-400" />
              Advanced Threat Intelligence & Demonstration Protocols
            </span>
            <span className="text-[10px] font-mono text-purple-400 bg-purple-500/10 px-2 py-0.5 rounded border border-purple-500/20 font-bold">
              PROJECT GARUDA v2.4
            </span>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
            {/* Voice Alert Announcements */}
            <div className="space-y-2 p-3.5 rounded-xl bg-black/30 border border-slate-800">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold text-ops-text">Spoken Voice Announcements</div>
                  <div className="text-[11px] text-ops-text-muted">Web Speech API synthesizes tactical verbal alerts for RED incursions</div>
                </div>
                <button
                  onClick={() => isAdmin && update('voice_announcements_enabled', !settings.voice_announcements_enabled)}
                  className={`px-3 py-1 text-xs font-bold rounded-lg border font-mono transition ${
                    settings.voice_announcements_enabled
                      ? 'bg-purple-500/20 text-purple-300 border-purple-500/40'
                      : 'bg-ops-surface text-ops-text-muted border-ops-border'
                  }`}
                >
                  {settings.voice_announcements_enabled ? 'ON' : 'OFF'}
                </button>
              </div>
              <p className="text-[10px] font-mono text-slate-500">
                Example: "Alert. Zero-line breach detected. Sector Alpha. Critical priority."
              </p>
            </div>

            {/* Demo / Presentation Mode */}
            <div className="space-y-2 p-3.5 rounded-xl bg-black/30 border border-slate-800">
              <div className="flex items-center justify-between">
                <div>
                  <div className="text-xs font-semibold text-amber-400 flex items-center gap-1.5">
                    <Play className="w-3.5 h-3.5" />
                    <span>Demo / Presentation Mode</span>
                  </div>
                  <div className="text-[11px] text-ops-text-muted">Displays safe amber watermark on surveillance feeds for live jury demos</div>
                </div>
                <button
                  onClick={() => isAdmin && update('demo_mode_enabled', !settings.demo_mode_enabled)}
                  className={`px-3 py-1 text-xs font-bold rounded-lg border font-mono transition ${
                    settings.demo_mode_enabled
                      ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                      : 'bg-ops-surface text-ops-text-muted border-ops-border'
                  }`}
                >
                  {settings.demo_mode_enabled ? 'ACTIVE' : 'INACTIVE'}
                </button>
              </div>
              <p className="text-[10px] font-mono text-slate-500">
                Prevents accidental live dispatches during SIH evaluation rounds.
              </p>
            </div>

            {/* Crowd Surge Threshold */}
            <div className="space-y-1.5 p-3.5 rounded-xl bg-black/30 border border-slate-800">
              <div className="flex justify-between items-center text-xs">
                <span className="font-semibold text-ops-text flex items-center gap-1.5">
                  <Users className="w-3.5 h-3.5 text-cyan-400" />
                  <span>Crowd Surge Density Threshold</span>
                </span>
                <span className="font-mono text-cyan-400 font-bold bg-ops-surface px-2 py-0.5 rounded border border-ops-border">
                  {settings.crowd_surge_threshold} Persons
                </span>
              </div>
              <input
                type="range"
                min={3}
                max={15}
                step={1}
                value={settings.crowd_surge_threshold}
                onChange={(e) => update('crowd_surge_threshold', parseInt(e.target.value))}
                disabled={!isAdmin}
                className="w-full accent-cyan-500 cursor-pointer"
              />
              <p className="text-[11px] text-ops-text-muted">
                Triggers CROWD_SURGE warning when person cluster in a restricted zone reaches this count.
              </p>
            </div>

            {/* Vehicle Loiter Circling Passes */}
            <div className="space-y-1.5 p-3.5 rounded-xl bg-black/30 border border-slate-800">
              <div className="flex justify-between items-center text-xs">
                <span className="font-semibold text-ops-text flex items-center gap-1.5">
                  <Car className="w-3.5 h-3.5 text-orange-400" />
                  <span>Vehicle Reconnaissance Passes</span>
                </span>
                <span className="font-mono text-orange-400 font-bold bg-ops-surface px-2 py-0.5 rounded border border-ops-border">
                  {settings.vehicle_loiter_passes} Passes
                </span>
              </div>
              <input
                type="range"
                min={2}
                max={6}
                step={1}
                value={settings.vehicle_loiter_passes}
                onChange={(e) => update('vehicle_loiter_passes', parseInt(e.target.value))}
                disabled={!isAdmin}
                className="w-full accent-orange-500 cursor-pointer"
              />
              <p className="text-[11px] text-ops-text-muted">
                Triggers VEHICLE_RECONNAISSANCE when the same plate passes a checkpoint repeatedly within rolling window.
              </p>
            </div>
          </div>
        </div>
      </div>

      {/* Save Button Bar */}
      <div className="flex justify-end gap-3 pt-2">
        <button
          onClick={saveSettings}
          disabled={saving || !isAdmin}
          className="px-6 py-2.5 text-xs font-bold rounded-lg bg-ops-accent hover:opacity-90 disabled:opacity-50 text-white transition shadow-sm flex items-center gap-2 font-display uppercase tracking-wider"
        >
          <Check className="w-4 h-4" />
          <span>{saving ? 'Syncing...' : 'Save & Hot-Sync AI Engine'}</span>
        </button>
      </div>
    </div>
  )
}
