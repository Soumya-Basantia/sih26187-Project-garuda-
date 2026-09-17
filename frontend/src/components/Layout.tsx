import React, { useState, useEffect } from 'react'
import { Link, useLocation } from 'react-router-dom'
import { useAuth } from '../hooks/useAuth'
import { useTheme } from '../hooks/useTheme'
import {
  LayoutDashboard,
  Radar,
  Camera,
  ShieldAlert,
  Users,
  Award,
  ClipboardList,
  History,
  BarChart3,
  Cpu,
  Settings,
  LogOut,
  Sun,
  Moon,
  Volume2,
  VolumeX,
  ChevronLeft,
  ChevronRight,
  Shield,
  Radio,
  Clock,
  Sparkles,
  BrainCircuit,
  Layers,
  Lock,
} from 'lucide-react'

interface NavGroup {
  group: string
  items: {
    path: string
    label: string
    shortLabel: string
    icon: React.ComponentType<{ className?: string }>
    badge?: string
  }[]
}

const NAV_GROUPS: NavGroup[] = [
  {
    group: 'Operations',
    items: [
      { path: '/', label: 'Live Dashboard', shortLabel: 'Dashboard', icon: LayoutDashboard },
      { path: '/tactical-map', label: '2D Perimeter Radar', shortLabel: 'Radar', icon: Radar, badge: 'LIVE' },
      { path: '/cameras', label: 'Camera & Sensors', shortLabel: 'Sensors', icon: Camera },
    ],
  },
  {
    group: 'Access & Identity',
    items: [
      { path: '/zones', label: 'Zone Management', shortLabel: 'Zones', icon: Shield },
      { path: '/authorization', label: 'Clearance Levels', shortLabel: 'Clearance', icon: Award },
      { path: '/identities', label: 'Personnel Records', shortLabel: 'Identities', icon: Users },
      { path: '/attendance', label: 'Entry & Access Log', shortLabel: 'Log', icon: ClipboardList },
    ],
  },
  {
    group: 'Evidence & Security',
    items: [
      { path: '/blockchain', label: 'Evidence Vault', shortLabel: 'Vault', icon: Layers, badge: 'Sec-65B' },
      { path: '/cybersecurity', label: 'Cyber Security Hub', shortLabel: 'CyberSentry', icon: Lock },
    ],
  },
  {
    group: 'Intelligence & Logs',
    items: [
      { path: '/learning-lab', label: 'AI Learning Lab', shortLabel: 'Learning', icon: BrainCircuit },
      { path: '/history', label: 'Incident History', shortLabel: 'History', icon: History },
      { path: '/analytics', label: 'Analytics & Reports', shortLabel: 'Analytics', icon: BarChart3 },
      { path: '/system-health', label: 'System Health', shortLabel: 'Health', icon: Cpu },
      { path: '/settings', label: 'Settings', shortLabel: 'Settings', icon: Settings },
    ],
  },
]

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const { username, role, logout } = useAuth()
  const { resolvedTheme, toggleTheme } = useTheme()
  const [collapsed, setCollapsed] = useState(false)
  const [sirenMuted, setSirenMuted] = useState(() => {
    return localStorage.getItem('garude_audio_muted') === 'true'
  })
  const [currentTime, setCurrentTime] = useState({
    utc: '',
    local: '',
  })

  // Live Mission Clock (UTC & Station Local)
  useEffect(() => {
    function updateClock() {
      const now = new Date()
      setCurrentTime({
        utc: now.toISOString().substring(11, 19) + ' Z',
        local: now.toLocaleTimeString('en-US', { hour12: false }),
      })
    }
    updateClock()
    const timer = setInterval(updateClock, 1000)
    return () => clearInterval(timer)
  }, [])

  function toggleSiren() {
    setSirenMuted((prev) => {
      const next = !prev
      localStorage.setItem('garude_audio_muted', String(next))
      return next
    })
  }

  return (
    <div className="flex h-screen bg-ops-bg text-ops-text overflow-hidden transition-colors duration-200">
      {/* High-Tech Tactical Sidebar */}
      <aside
        className={`${
          collapsed ? 'w-20' : 'w-72'
        } shrink-0 border-r border-ops-border bg-ops-panel flex flex-col z-30 transition-all duration-300 relative shadow-tactical select-none`}
      >
        {/* Top Garuda Branding */}
        <div className="h-16 px-5 border-b border-ops-border flex items-center justify-between">
          <div className="flex items-center gap-3 overflow-hidden">
            <div className="relative h-10 w-12 flex items-center justify-center shrink-0">
              <img
                src="/garuda-emblem.png"
                alt="Garuda Emblem"
                className="w-full h-full object-contain filter drop-shadow-[0_0_10px_rgba(6,182,212,0.8)] hover:scale-110 transition-transform duration-300"
              />
            </div>
            {!collapsed && (
              <div className="flex flex-col truncate">
                <span className="font-display font-black tracking-wider text-base text-ops-text flex items-center gap-1">
                  PROJECT GARUD<span className="text-ops-accent">▲</span>
                </span>
                <span className="text-[10px] text-ops-text-muted tracking-wide truncate">
                  Intelligent Video Platform
                </span>
              </div>
            )}
          </div>

          <button
            onClick={() => setCollapsed(!collapsed)}
            className="p-1.5 rounded-md text-ops-text-muted hover:text-ops-text hover:bg-ops-surface border border-transparent hover:border-ops-border transition-all"
            title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
          >
            {collapsed ? <ChevronRight className="w-4 h-4" /> : <ChevronLeft className="w-4 h-4" />}
          </button>
        </div>

        {/* Navigation Groups */}
        <nav className="flex-1 overflow-y-auto px-3 py-5 space-y-6">
          {NAV_GROUPS.map((group) => (
            <div key={group.group} className="space-y-1.5">
              {!collapsed && (
                <div className="px-3 text-[10px] font-semibold text-ops-text-muted/60 tracking-wider uppercase">
                  {group.group}
                </div>
              )}
              <div className="space-y-0.5">
                {group.items.map((item) => {
                  const Icon = item.icon
                  const isActive = location.pathname === item.path
                  return (
                    <Link
                      key={item.path}
                      to={item.path}
                      title={collapsed ? item.label : undefined}
                      className={`group flex items-center gap-3 px-3 py-2 rounded-lg text-[13px] font-medium transition-all duration-150 relative ${
                        isActive
                          ? 'bg-ops-accent/12 text-ops-accent font-semibold'
                          : 'text-ops-text-muted hover:text-ops-text hover:bg-ops-surface'
                      }`}
                    >
                      {isActive && (
                        <span className="absolute left-0 top-1/2 -translate-y-1/2 w-0.5 h-5 rounded-r bg-ops-accent" />
                      )}
                      <Icon
                        className={`w-4 h-4 shrink-0 ${
                          isActive ? 'text-ops-accent' : 'text-ops-text-muted group-hover:text-ops-text'
                        }`}
                      />
                      {!collapsed && (
                        <div className="flex-1 flex items-center justify-between truncate">
                          <span className="truncate">{item.label}</span>
                          {item.badge && (
                            <span className="text-[9px] font-mono font-bold px-1.5 py-0.5 rounded bg-ops-accent/15 text-ops-accent border border-ops-accent/25">
                              {item.badge}
                            </span>
                          )}
                        </div>
                      )}
                    </Link>
                  )
                })}
              </div>
            </div>
          ))}

        </nav>

        {/* Bottom Operator Info */}
        <div className="p-3 border-t border-ops-border">
          {!collapsed ? (
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2.5 truncate">
                <div className="w-8 h-8 rounded-full bg-ops-accent/15 border border-ops-accent/30 flex items-center justify-center font-semibold text-sm text-ops-accent shrink-0">
                  {username?.charAt(0).toUpperCase() || 'O'}
                </div>
                <div className="truncate">
                  <div className="text-xs font-semibold text-ops-text truncate">{username || 'Operator'}</div>
                  <div className="text-[10px] text-ops-text-muted capitalize">{(role || 'operator').toLowerCase().replace('_', ' ')}</div>
                </div>
              </div>
              <button
                onClick={logout}
                className="p-1.5 text-ops-text-muted hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
                title="Sign Out"
              >
                <LogOut className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <button
              onClick={logout}
              className="w-full flex justify-center p-2 text-ops-text-muted hover:text-red-400 hover:bg-red-500/10 rounded transition-colors"
              title="Sign Out"
            >
              <LogOut className="w-4 h-4" />
            </button>
          )}
        </div>
      </aside>

      {/* Main Content Area with Top Mission Control Bar */}
      <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
        {/* Top Bar */}
        <header className="h-14 shrink-0 border-b border-ops-border bg-ops-panel/95 backdrop-blur-md px-6 sm:px-8 flex items-center justify-between z-20">
          {/* Left: Status & page context */}
          <div className="flex items-center gap-3">
            <div className="flex items-center gap-2 px-2.5 py-1 rounded-full bg-emerald-500/10 border border-emerald-500/25 text-emerald-500 text-xs">
              <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
              <span className="font-semibold">All Systems Active</span>
            </div>

            <div className="hidden md:flex items-center gap-2 text-xs text-ops-text-muted">
              <span className="text-ops-text font-medium">AI Tracking</span>
              <span className="text-ops-border">·</span>
              <span>Real-time monitoring</span>
            </div>
          </div>

          {/* Right: Clocks, Audio & Theme */}
          <div className="flex items-center gap-2.5">
            {/* Mission Clocks */}
            <div className="hidden lg:flex items-center gap-3 px-3 py-1.5 rounded-md bg-ops-surface border border-ops-border text-xs font-mono">
              <Clock className="w-3.5 h-3.5 text-ops-accent" />
              <div className="flex items-center gap-1.5">
                <span className="text-ops-text-muted">UTC</span>
                <span className="text-ops-text font-semibold">{currentTime.utc || '--:--:--'}</span>
              </div>
              <span className="text-ops-border">|</span>
              <div className="flex items-center gap-1.5">
                <span className="text-ops-text-muted">Local</span>
                <span className="text-ops-text font-semibold">{currentTime.local || '--:--:--'}</span>
              </div>
            </div>

            {/* Audio Toggle */}
            <button
              onClick={toggleSiren}
              className={`p-2 rounded-md border flex items-center gap-1.5 transition-all text-xs ${
                sirenMuted
                  ? 'bg-ops-surface border-ops-border text-ops-text-muted hover:text-ops-text'
                  : 'bg-ops-accent/10 border-ops-accent/30 text-ops-accent'
              }`}
              title={sirenMuted ? 'Audio muted' : 'Audio on'}
            >
              {sirenMuted ? <VolumeX className="w-4 h-4" /> : <Volume2 className="w-4 h-4" />}
            </button>

            {/* Theme Toggle */}
            <button
              onClick={toggleTheme}
              className="p-2 rounded-md border border-ops-border bg-ops-surface hover:bg-ops-panel text-ops-text transition-all duration-200"
              title={`Switch to ${resolvedTheme === 'dark' ? 'light' : 'dark'} mode`}
            >
              {resolvedTheme === 'dark' ? (
                <Sun className="w-4 h-4 text-amber-400" />
              ) : (
                <Moon className="w-4 h-4 text-slate-500" />
              )}
            </button>
          </div>
        </header>

        {/* Content Viewport */}
        <main className={`flex-1 min-h-0 cyber-grid relative flex flex-col ${location.pathname === '/' ? 'overflow-hidden' : 'overflow-y-auto'}`}>
          {children}
        </main>
      </div>
    </div>
  )
}
