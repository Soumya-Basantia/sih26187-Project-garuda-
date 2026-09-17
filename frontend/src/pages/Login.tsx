import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import { api } from '../services/api'
import TacticalBackground from '../components/TacticalBackground'
import {
  ShieldCheck,
  Lock,
  User,
  Eye,
  EyeOff,
  Zap,
  Radio,
  Sun,
  Moon,
  AlertTriangle,
  Fingerprint,
  ArrowRight,
  Shield,
  Activity,
  Cpu,
  Radar,
  Globe2,
  Clock,
  KeyRound
} from 'lucide-react'

export default function Login() {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [rememberMe, setRememberMe] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  const [isSubmitting, setIsSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [backendStatus, setBackendStatus] = useState<'checking' | 'online' | 'starting'>('checking')
  const [timeString, setTimeString] = useState({ utc: '', local: '' })
  const { token, username: currentUsername, login, logout } = useAuth()
  const { resolvedTheme, toggleTheme } = useTheme()
  const navigate = useNavigate()

  // Live Mission Clock
  useEffect(() => {

    const updateTime = () => {
      const now = new Date()
      setTimeString({
        utc: now.toISOString().substring(11, 19) + ' UTC',
        local: now.toLocaleTimeString('en-US', { hour12: false }),
      })
    }
    updateTime()
    const timer = setInterval(updateTime, 1000)
    return () => clearInterval(timer)
  }, [])

  useEffect(() => {
    let mounted = true
    async function checkHealth() {
      try {
        await api.get('/api/system/health', { timeout: 3000 })
        if (mounted) setBackendStatus('online')
      } catch {
        if (mounted) setBackendStatus('starting')
      }
    }
    checkHealth()
    const interval = setInterval(checkHealth, 3000)
    return () => {
      mounted = false
      clearInterval(interval)
    }
  }, [])

  function handleQuickFill() {
    setUsername('admin')
    setPassword('admin')
    setError(null)
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!username.trim() || !password) {
      setError('Please enter both Operator ID and Security Key.')
      return
    }

    setError(null)
    setIsSubmitting(true)

    try {
      await login(username.trim(), password, rememberMe)
      navigate('/')
    } catch (err: any) {
      if (err?.code === 'ECONNABORTED' || err?.message?.includes('Network Error')) {
        setError('Cannot reach GARUDA Core API (port 8000). Verify the backend service is running.')
      } else {
        setError(err?.response?.data?.detail || 'Authentication failed. Check your Operator ID and Security Key.')
      }
    } finally {
      setIsSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen flex flex-col justify-between bg-ops-bg text-ops-text relative overflow-x-hidden cyber-grid select-none">
      {/* Dynamic Animated Radar & Constellation Canvas Background */}
      <TacticalBackground />

      {/* Atmospheric Ambient Light Glows */}
      <div className="absolute top-1/4 left-1/4 -translate-x-1/2 -translate-y-1/2 w-[850px] h-[450px] bg-ops-accent/10 blur-[170px] pointer-events-none rounded-full" />
      <div className="absolute bottom-1/4 right-1/4 translate-x-1/2 translate-y-1/2 w-[600px] h-[350px] bg-cyan-500/10 blur-[150px] pointer-events-none rounded-full" />

      {/* 1. Top High-Tech Command Bar */}
      <header className="relative z-20 w-full px-6 sm:px-10 py-5 flex items-center justify-between border-b border-ops-border/70 backdrop-blur-md bg-ops-panel/40">
        <div className="flex items-center gap-3.5">
          <div className="relative h-12 w-14 flex items-center justify-center shrink-0">
            <img src="/garuda-emblem.png" alt="Garuda Emblem" className="w-full h-full object-contain filter drop-shadow-[0_0_12px_rgba(6,182,212,0.85)] hover:scale-105 transition-transform" />
          </div>
          <div>
            <div className="font-display font-black tracking-widest text-lg text-ops-text flex items-center gap-2">
              PROJECT GARUD<span className="text-ops-accent">▲</span> <span className="text-[10px] font-mono font-bold px-2 py-0.5 rounded bg-ops-accent/20 text-ops-accent border border-ops-accent/30">C4ISR STRATEGIC DEFENSE</span>
            </div>
            <div className="text-[11px] text-ops-text-muted font-mono tracking-wider">
              INTELLIGENT EYES FOR A SAFER TOMORROW
            </div>
          </div>
        </div>

        {/* Right Station Metrics & Quick Toggles */}
        <div className="flex items-center gap-3">
          {/* Mission Time */}
          <div className="hidden md:flex items-center gap-3 px-3 py-1.5 rounded-lg bg-ops-surface/80 border border-ops-border text-xs font-mono">
            <Clock className="w-3.5 h-3.5 text-ops-accent" />
            <span className="text-ops-text-muted">{timeString.utc || '--:--:--'}</span>
            <span className="text-ops-border">|</span>
            <span className="text-ops-text font-semibold">{timeString.local || '--:--:--'} LOC</span>
          </div>

          {/* Classification Badge */}
          <span className="hidden sm:inline-flex px-3 py-1 rounded-full text-[11px] font-mono font-bold uppercase tracking-wider bg-red-500/15 text-red-500 border border-red-500/30">
            RESTRICTED // DEFCON 2
          </span>

          {/* Theme Switcher Button */}
          <button
            onClick={toggleTheme}
            className="p-2.5 rounded-lg border border-ops-border bg-ops-surface/80 hover:border-ops-border-hover hover:bg-ops-panel text-ops-text transition-all shadow-sm"
            title={`Switch to ${resolvedTheme === 'dark' ? 'Ops Light' : 'Tactical Dark'} mode`}
          >
            {resolvedTheme === 'dark' ? (
              <Sun className="w-4 h-4 text-amber-400 hover:rotate-90 transition-transform duration-300" />
            ) : (
              <Moon className="w-4 h-4 text-cyan-600 hover:-rotate-12 transition-transform duration-300" />
            )}
          </button>
        </div>
      </header>

      {/* 2. Main Center Content: Spacious Widescreen Command Console */}
      <main className="relative z-10 w-full max-w-7xl mx-auto px-4 sm:px-8 py-6 sm:py-8 lg:py-12 flex-1 flex items-center">
        <div className="w-full grid grid-cols-1 lg:grid-cols-12 gap-8 lg:gap-14 items-center">
          
          {/* LEFT WING: Strategic Briefing & Live Defense Telemetry (7 Cols) */}
          <div className="order-2 lg:order-1 lg:col-span-7 flex flex-col justify-center space-y-6 lg:space-y-8">
            <div className="space-y-3">
              <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-mono font-bold tracking-widest uppercase bg-ops-accent/15 text-ops-accent border border-ops-accent/30">

                <span className="w-2 h-2 rounded-full bg-ops-accent animate-ping" />
                TACTICAL DEFENSE SURVEILLANCE MATRIX
              </div>

              <h1 className="text-4xl sm:text-5xl lg:text-6xl font-display font-black tracking-tight text-ops-text leading-tight">
                DEFEND. DETECT. <br />
                <span className="text-transparent bg-clip-text bg-gradient-to-r from-ops-accent via-cyan-400 to-emerald-400 drop-shadow-[0_0_25px_var(--color-ops-accent-glow)]">
                  INTERCEPT IN REAL-TIME.
                </span>
              </h1>

              <p className="text-base sm:text-lg text-ops-text-muted font-normal max-w-2xl leading-relaxed pt-1">
                Project GARUDA integrates real-time optical surveillance, thermal signature feeds, drone radar telemetry, and autonomous neural threat assessment across mission-critical facilities.
              </p>
            </div>

            {/* Strategic Telemetry Cards - Generous Breathing Room */}
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-2">
              {/* Card 1: Core Status */}
              <div className="tactical-panel p-4.5 rounded-xl border border-ops-border/80 shadow-sm flex flex-col justify-between space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono text-ops-text-muted uppercase tracking-wider font-semibold">
                    Core Engine
                  </span>
                  <Activity className="w-4 h-4 text-emerald-400" />
                </div>
                <div>
                  <div className="text-xl font-bold font-display text-ops-text flex items-center gap-2">
                    {backendStatus === 'online' ? (
                      <>
                        <span className="w-2.5 h-2.5 rounded-full bg-emerald-500 animate-pulse" />
                        ONLINE
                      </>
                    ) : (
                      <>
                        <span className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse" />
                        STARTING
                      </>
                    )}
                  </div>
                  <div className="text-[11px] font-mono text-ops-text-muted mt-0.5">
                    FastAPI · WebSocket Telemetry
                  </div>
                </div>
              </div>

              {/* Card 2: Neural Tracker */}
              <div className="tactical-panel p-4.5 rounded-xl border border-ops-border/80 shadow-sm flex flex-col justify-between space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono text-ops-text-muted uppercase tracking-wider font-semibold">
                    Threat Detection
                  </span>
                  <Radar className="w-4 h-4 text-ops-accent" />
                </div>
                <div>
                  <div className="text-xl font-bold font-display text-ops-text">
                    60.0 FPS
                  </div>
                  <div className="text-[11px] font-mono text-ops-text-muted mt-0.5">
                    Multi-Spectral YOLOv8 + XAI
                  </div>
                </div>
              </div>

              {/* Card 3: Security Clearance */}
              <div className="tactical-panel p-4.5 rounded-xl border border-ops-border/80 shadow-sm flex flex-col justify-between space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-[11px] font-mono text-ops-text-muted uppercase tracking-wider font-semibold">
                    Zero-Trust Link
                  </span>
                  <ShieldCheck className="w-4 h-4 text-cyan-400" />
                </div>
                <div>
                  <div className="text-xl font-bold font-display text-ops-text">
                    AES-256
                  </div>
                  <div className="text-[11px] font-mono text-ops-text-muted mt-0.5">
                    Air-Gapped Token Vault
                  </div>
                </div>
              </div>
            </div>

            {/* Quick Demo Access Bar */}
            <div className="p-4 rounded-xl bg-ops-surface/80 border border-ops-border flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3">
              <div className="flex items-center gap-3">
                <div className="w-8 h-8 rounded-lg bg-ops-accent/15 border border-ops-accent/30 flex items-center justify-center shrink-0">
                  <KeyRound className="w-4 h-4 text-ops-accent" />
                </div>
                <div>
                  <span className="text-xs font-semibold text-ops-text">Demonstration Station Credentials</span>
                  <div className="text-[11px] font-mono text-ops-text-muted">
                    Operator ID: <span className="text-ops-text font-bold">admin</span> · Passkey: <span className="text-ops-text font-bold">admin</span>
                  </div>
                </div>
              </div>

              <button
                type="button"
                onClick={handleQuickFill}
                className="px-3.5 py-1.5 rounded-lg text-xs font-mono font-bold tracking-wide bg-ops-accent/15 text-ops-accent hover:bg-ops-accent/25 border border-ops-accent/35 transition flex items-center gap-1.5 shadow-sm active:scale-95 shrink-0"
              >
                <Zap className="w-3.5 h-3.5" />
                AUTO-FILL CREDENTIALS
              </button>
            </div>
          </div>

          {/* RIGHT WING: Tactical Authentication Terminal (5 Cols) */}
          <div className="order-1 lg:order-2 lg:col-span-5 w-full flex justify-center">
            <div className="w-full max-w-lg tactical-panel hud-corner p-6 sm:p-9 rounded-2xl shadow-2xl relative border border-ops-border/90 bg-ops-panel/90 backdrop-blur-xl">

              {/* Project Garuda Brand Emblem Header */}
              <div className="flex items-center justify-center pb-4 mb-5 border-b border-ops-border/60">
                <div className="flex items-center gap-3">
                  <img src="/garuda-emblem.png" alt="Garuda" className="h-10 object-contain drop-shadow-[0_0_12px_rgba(6,182,212,0.8)]" />
                  <div className="flex flex-col">
                    <span className="font-display font-black tracking-widest text-base text-ops-text">PROJECT GARUD<span className="text-ops-accent">▲</span></span>
                    <span className="text-[9px] font-mono text-ops-accent uppercase tracking-widest font-bold">See · Secure · Protect</span>
                  </div>
                </div>
              </div>

              {/* Biometric Holographic Scanner Module */}
              <div className="relative mb-6 pb-6 border-b border-ops-border/70 flex items-center gap-4">
                {/* Scanning Fingerprint Icon with Animated Laser Beam */}
                <div className="relative w-16 h-16 rounded-xl bg-ops-surface border border-ops-accent/40 flex items-center justify-center overflow-hidden shrink-0 shadow-[0_0_20px_var(--color-ops-accent-glow)]">
                  <Fingerprint className="w-9 h-9 text-ops-accent/80" />
                  {/* Glowing Laser Scan Bar */}
                  <div className="absolute left-0 right-0 h-0.5 bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_8px_#38bdf8] animate-laser pointer-events-none" />
                </div>

                <div>
                  <h2 className="text-base font-bold font-display uppercase tracking-wider text-ops-text flex items-center gap-2">
                    Terminal Gateway
                  </h2>
                  <p className="text-xs text-ops-text-muted mt-0.5">
                    Biometric validation & encrypted C2 operator clearance
                  </p>
                </div>
              </div>

              {/* Active Session Indicator if already authenticated */}
              {token && (
                <div className="mb-5 p-3.5 rounded-xl bg-ops-accent/15 border border-ops-accent/35 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2.5">
                  <div className="text-xs">
                    <span className="text-ops-accent font-bold">Active Session:</span>
                    <span className="text-ops-text ml-1.5 font-mono">Operator {currentUsername || 'admin'}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      onClick={() => navigate('/')}
                      className="px-2.5 py-1 text-xs font-mono font-bold bg-ops-accent text-white rounded-md hover:opacity-90 flex items-center gap-1 shadow-sm"
                    >
                      Dashboard <ArrowRight className="w-3 h-3" />
                    </button>
                    <button
                      type="button"
                      onClick={() => logout()}
                      className="px-2.5 py-1 text-xs font-mono text-ops-text-muted hover:text-red-400 border border-ops-border rounded-md hover:bg-red-500/10 transition"
                    >
                      Sign Out
                    </button>
                  </div>
                </div>
              )}

              {/* Error Message Toast */}
              {error && (
                <div className="severity-high border rounded-lg px-4 py-3 text-xs mb-5 flex items-start gap-2.5 animate-fadeIn">
                  <AlertTriangle className="w-4 h-4 text-red-400 shrink-0 mt-0.5" />
                  <div className="flex-1 font-medium leading-snug">{error}</div>
                </div>
              )}


              {/* Authentication Form */}
              <form onSubmit={handleSubmit} className="space-y-5">
                {/* Operator ID Field */}
                <div>
                  <label className="block text-xs font-semibold text-ops-text uppercase tracking-wider mb-2 font-mono">
                    Operator Identifier / Call Sign
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-ops-text-muted">
                      <User className="w-4 h-4" />
                    </div>
                    <input
                      type="text"
                      autoComplete="username"
                      required
                      placeholder="e.g. admin"
                      className="w-full pl-11 pr-4 py-3 bg-ops-surface border border-ops-border rounded-lg text-sm text-ops-text placeholder-ops-text-muted/40 outline-none focus:border-ops-accent focus:ring-2 focus:ring-ops-accent/30 transition font-mono"
                      value={username}
                      onChange={(e) => setUsername(e.target.value)}
                    />
                  </div>
                </div>

                {/* Security Passkey Field */}
                <div>
                  <div className="flex items-center justify-between mb-2">
                    <label className="block text-xs font-semibold text-ops-text uppercase tracking-wider font-mono">
                      Security Passkey
                    </label>
                    <button
                      type="button"
                      onClick={() => setShowPassword(!showPassword)}
                      className="text-[11px] text-ops-accent hover:underline flex items-center gap-1 font-mono"
                    >
                      {showPassword ? <EyeOff className="w-3.5 h-3.5" /> : <Eye className="w-3.5 h-3.5" />}
                      <span>{showPassword ? 'Hide Key' : 'Show Key'}</span>
                    </button>
                  </div>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3.5 flex items-center pointer-events-none text-ops-text-muted">
                      <Lock className="w-4 h-4" />
                    </div>
                    <input
                      type={showPassword ? 'text' : 'password'}
                      autoComplete="current-password"
                      required
                      placeholder="••••••••"
                      className="w-full pl-11 pr-11 py-3 bg-ops-surface border border-ops-border rounded-lg text-sm text-ops-text placeholder-ops-text-muted/40 outline-none focus:border-ops-accent focus:ring-2 focus:ring-ops-accent/30 transition font-mono"
                      value={password}
                      onChange={(e) => setPassword(e.target.value)}
                    />
                  </div>
                </div>

                {/* Session Persistence & Cryptographic Spec */}
                <div className="flex items-center justify-between pt-1">
                  <label className="flex items-center gap-2.5 cursor-pointer text-xs text-ops-text-muted hover:text-ops-text select-none">
                    <input
                      type="checkbox"
                      checked={rememberMe}
                      onChange={(e) => setRememberMe(e.target.checked)}
                      className="w-4 h-4 rounded border-ops-border bg-ops-surface text-ops-accent focus:ring-ops-accent"
                    />
                    <span>Persist Station Session</span>
                  </label>

                  <span className="text-[11px] font-mono text-ops-text-muted">
                    SHA-256 AES-GCM
                  </span>
                </div>

                {/* Submit Action Button */}
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="w-full py-3.5 px-5 rounded-xl bg-ops-accent hover:opacity-90 text-white font-bold text-sm tracking-wider shadow-[0_0_20px_var(--color-ops-accent-glow)] transition-all flex items-center justify-center gap-2 disabled:opacity-50 disabled:cursor-not-allowed font-display active:scale-[0.99] mt-3"
                >
                  {isSubmitting ? (
                    <>
                      <div className="w-4 h-4 rounded-full border-2 border-white/30 border-t-white animate-spin" />
                      <span>AUTHENTICATING NODE ACCESS...</span>
                    </>
                  ) : (
                    <>
                      <ShieldCheck className="w-5 h-5" />
                      <span>INITIALIZE COMMAND ACCESS</span>
                      <ArrowRight className="w-4 h-4 ml-1" />
                    </>
                  )}
                </button>
              </form>

              {/* Terminal Footer Indicator */}
              <div className="mt-8 pt-4 border-t border-ops-border/60 flex items-center justify-between text-[11px] font-mono text-ops-text-muted">
                <span className="flex items-center gap-1.5">
                  <span className="w-1.5 h-1.5 rounded-full bg-ops-accent animate-ping" />
                  GATEWAY: #GARUDA-NODE-01
                </span>
                <span>WS TELEMETRY: READY</span>
              </div>
            </div>
          </div>

        </div>
      </main>

      {/* 3. Bottom Minimalist Security Footer */}
      <footer className="relative z-10 w-full px-6 sm:px-10 py-4 border-t border-ops-border/60 backdrop-blur-md bg-ops-panel/40 flex flex-col sm:flex-row items-center justify-between gap-2 text-xs font-mono text-ops-text-muted">
        <div className="flex items-center gap-2">
          <Shield className="w-3.5 h-3.5 text-ops-accent" />
          <span>PROJECT GARUDA v2.4.0 · CLASSIFIED C4ISR DEFENSE PLATFORM</span>
        </div>
        <div className="flex items-center gap-4">
          <span>AIR-GAPPED COMPLIANT</span>
          <span>·</span>
          <span>ALL TRANSACTIONS AUDITED</span>
        </div>
      </footer>
    </div>
  )
}
