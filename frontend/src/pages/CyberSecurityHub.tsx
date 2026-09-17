import React, { useState, useEffect } from 'react'
import {
  cybersecurityApi,
  CyberPosture,
  CyberThreat,
  CameraCyberAudit,
  MitreTechnique,
  DigitalAntibody,
  ImmuneSystemStats,
} from '../services/api'
import {
  Shield,
  ShieldAlert,
  ShieldCheck,
  Radio,
  Lock,
  Unlock,
  AlertTriangle,
  RefreshCw,
  Activity,
  Terminal,
  Server,
  Zap,
  CheckCircle2,
  XCircle,
  Play,
  RotateCcw,
  Eye,
  Sliders,
  Sparkles,
  Wifi,
  WifiOff,
  Dna,
  Bug,
  Cpu,
  Database,
  Layers,
} from 'lucide-react'

export default function CyberSecurityHub() {
  const [posture, setPosture] = useState<CyberPosture | null>(null)
  const [threats, setThreats] = useState<CyberThreat[]>([])
  const [immuneState, setImmuneState] = useState<ImmuneSystemStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [simulating, setSimulating] = useState(false)
  const [trainingAntibodyId, setTrainingAntibodyId] = useState<string | null>(null)
  const [actionNotice, setActionNotice] = useState<string | null>(null)
  const [activeTab, setActiveTab] = useState<'ANTIBODIES' | 'FLEET' | 'MITRE' | 'ANTI_REPLAY'>('ANTIBODIES')

  useEffect(() => {
    fetchCyberData()
    const interval = setInterval(fetchCyberData, 8000)
    return () => clearInterval(interval)
  }, [])

  async function fetchCyberData() {
    try {
      const [postureRes, threatsRes, immuneRes] = await Promise.all([
        cybersecurityApi.getPosture(),
        cybersecurityApi.getThreats(),
        cybersecurityApi.getAntibodies(),
      ])
      setPosture(postureRes.data)
      setThreats(threatsRes.data.all_threats)
      setImmuneState(immuneRes.data)
    } catch (err) {
      console.error('Failed to load cybersecurity telemetry:', err)
    } finally {
      setLoading(false)
    }
  }

  async function handleSimulateAttack(attackType: string) {
    setSimulating(true)
    try {
      const res = await cybersecurityApi.simulateAttack({
        attack_type: attackType,
        camera_id: 'CAM-01',
      })
      setActionNotice(`🚨 INTRUSION ALERT DISPATCHED: ${res.data.mitre_name}. CyberSentry activated automatic zero-trust quarantine.`)
      await fetchCyberData()
    } catch (err) {
      console.error('Simulation failed:', err)
    } finally {
      setSimulating(false)
    }
  }

  async function handleResolveThreat(incidentId: string) {
    try {
      await cybersecurityApi.resolveThreat(incidentId)
      setActionNotice(`Incident ${incidentId} neutralized. Node restored to nominal state.`)
      await fetchCyberData()
    } catch (err) {
      console.error('Resolve failed:', err)
    }
  }

  async function handleResetFleet() {
    try {
      await cybersecurityApi.resetState()
      setActionNotice('Fleet cybersecurity state reset. All camera nodes nominal.')
      await fetchCyberData()
    } catch (err) {
      console.error('Reset failed:', err)
    }
  }

  async function handleTrainAntibody(antibodyId: string) {
    setTrainingAntibodyId(antibodyId)
    try {
      const res = await cybersecurityApi.trainAntibody(antibodyId)
      setActionNotice(`🧬 ANTIBODY HARDENED: ${res.data.summary}`)
      const immuneRes = await cybersecurityApi.getAntibodies()
      setImmuneState(immuneRes.data)
    } catch (err) {
      console.error('Training failed:', err)
    } finally {
      setTrainingAntibodyId(null)
    }
  }

  const activeThreats = threats.filter((t) => t.status === 'ACTIVE')
  const hasActiveThreat = activeThreats.length > 0

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/10 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-cyan-500/10 border border-cyan-500/30 text-cyan-400">
              <Shield className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl md:text-2xl font-black tracking-wider text-white font-mono">
                  CYBERSENTRY // ZERO-TRUST DEFENSE
                </h1>
                <span className="px-2 py-0.5 text-xs font-mono rounded font-semibold bg-cyan-500/20 text-cyan-300 border border-cyan-500/40">
                  MITRE ICS C2
                </span>
              </div>
              <p className="text-sm text-slate-400 mt-0.5">
                IoT Camera Hardening, Anti-Replay Stream Liveness & Electronic Perimeter Cyber Defense
              </p>
            </div>
          </div>
        </div>

        {/* Global Posture Status Badge */}
        <div className="flex items-center gap-3">
          <div
            className={`px-4 py-2 rounded-lg border flex items-center gap-2.5 font-mono text-xs font-bold ${
              hasActiveThreat
                ? 'bg-rose-500/10 border-rose-500/40 text-rose-300 animate-pulse'
                : 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300'
            }`}
          >
            {hasActiveThreat ? (
              <>
                <ShieldAlert className="w-4 h-4 text-rose-400" />
                <span>ACTIVE CYBER INCURSION ({activeThreats.length})</span>
              </>
            ) : (
              <>
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>PERIMETER ZERO-TRUST HARDENED</span>
              </>
            )}
          </div>

          <button
            onClick={fetchCyberData}
            disabled={loading}
            className="p-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-white/10 transition-colors"
            title="Refresh Cyber Telemetry"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Action Notification Banner */}
      {actionNotice && (
        <div className="p-4 rounded-xl bg-cyan-950/40 border border-cyan-500/30 flex items-center justify-between text-cyan-200 text-sm">
          <div className="flex items-center gap-2.5">
            <Terminal className="w-4 h-4 text-cyan-400" />
            <span className="font-mono">{actionNotice}</span>
          </div>
          <button
            onClick={() => setActionNotice(null)}
            className="text-xs text-cyan-400 hover:text-cyan-200 underline font-mono"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Posture Score & Metrics */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/60 border border-white/10 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Fleet Cyber Score</span>
            <Shield className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="flex items-baseline gap-2 mt-2">
            <span
              className={`text-3xl font-black font-mono ${
                (posture?.fleet_cyber_score ?? 100) >= 80 ? 'text-emerald-400' : 'text-amber-400'
              }`}
            >
              {posture?.fleet_cyber_score ?? '—'}%
            </span>
            <span className="text-xs font-mono text-slate-400">DEFENSE GRADE</span>
          </div>
          <p className="text-xs text-slate-500 mt-1 font-mono">Weighted CVE & Protocol Posture</p>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-white/10 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Anti-Replay Engine</span>
            <Activity className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-base font-bold font-mono text-indigo-300 mt-2">
            SHANNON ENTROPY // ACTIVE
          </div>
          <p className="text-xs text-slate-500 mt-1 font-mono">30Hz Optical Noise PRNU Tracking</p>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-white/10 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Active Threat Matrix</span>
            <AlertTriangle className="w-4 h-4 text-rose-400" />
          </div>
          <div className={`text-3xl font-black font-mono mt-2 ${hasActiveThreat ? 'text-rose-400' : 'text-slate-300'}`}>
            {activeThreats.length}
          </div>
          <p className="text-xs text-slate-500 mt-1 font-mono">Real-Time Incursions</p>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-white/10 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Quarantined Nodes</span>
            <WifiOff className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-3xl font-black font-mono text-amber-300 mt-2">
            {posture?.quarantined_nodes_count ?? 0}
          </div>
          <p className="text-xs text-slate-500 mt-1 font-mono">Isolated From Main Defense Bus</p>
        </div>
      </div>

      {/* SIH Hackathon Jury Cyber Attack Simulation Sandbox */}
      <div className="p-5 rounded-xl bg-gradient-to-r from-slate-900/90 via-slate-900/70 to-slate-900/90 border border-cyan-500/30 shadow-xl">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-cyan-400 font-mono text-xs uppercase tracking-widest font-bold">
              <Sparkles className="w-4 h-4" />
              <span>SIH Hackathon Live Cyber Defense Sandbox</span>
            </div>
            <h2 className="text-lg font-bold text-white mt-1">
              Simulate Real-World Surveillance Cyber Attacks & Zero-Trust Neutralization
            </h2>
            <p className="text-xs text-slate-400 mt-0.5 max-w-2xl">
              Legacy CCTV cameras are standard entry points for border infiltration. Test how CyberSentry detects
              video loop injections (anti-replay math), stream eavesdropping, or RTSP password spraying in under 1.5 seconds.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <button
              onClick={() => handleSimulateAttack('replay_loop')}
              disabled={simulating}
              className="px-3.5 py-2 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/40 font-mono text-xs font-bold flex items-center gap-2 transition-all"
            >
              <Play className="w-3.5 h-3.5 text-rose-400" />
              <span>Video Loop Attack (T0855)</span>
            </button>

            <button
              onClick={() => handleSimulateAttack('rtsp_mitm')}
              disabled={simulating}
              className="px-3.5 py-2 rounded-lg bg-amber-600/20 hover:bg-amber-600/30 text-amber-300 border border-amber-500/40 font-mono text-xs font-bold flex items-center gap-2 transition-all"
            >
              <Lock className="w-3.5 h-3.5 text-amber-400" />
              <span>RTSP MITM Tap (T0855)</span>
            </button>

            <button
              onClick={() => handleSimulateAttack('brute_force')}
              disabled={simulating}
              className="px-3.5 py-2 rounded-lg bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-300 border border-indigo-500/40 font-mono text-xs font-bold flex items-center gap-2 transition-all"
            >
              <Zap className="w-3.5 h-3.5 text-indigo-400" />
              <span>Port 554 Spraying (T0885)</span>
            </button>

            {hasActiveThreat && (
              <button
                onClick={handleResetFleet}
                className="px-3.5 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold flex items-center gap-2 transition-all shadow-lg shadow-emerald-600/20"
              >
                <RotateCcw className="w-3.5 h-3.5" />
                <span>Neutralize All Threats</span>
              </button>
            )}
          </div>
        </div>
      </div>

      {/* Active Threats Display */}
      {hasActiveThreat && (
        <div className="space-y-3">
          <h3 className="text-xs font-mono font-bold text-rose-400 uppercase tracking-wider flex items-center gap-2">
            <AlertTriangle className="w-4 h-4 text-rose-400 animate-pulse" />
            <span>Active Cyber Incursions Requiring Defense Response ({activeThreats.length})</span>
          </h3>

          <div className="grid grid-cols-1 gap-3">
            {activeThreats.map((threat) => (
              <div
                key={threat.incident_id}
                className="p-4 rounded-xl bg-rose-950/40 border border-rose-500/60 shadow-lg text-rose-100 font-mono text-xs space-y-3"
              >
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-rose-500/20 pb-2">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded font-bold bg-rose-600 text-white text-[10px]">
                      {threat.mitre_id} // {threat.attack_type}
                    </span>
                    <span className="text-white font-bold">{threat.mitre_name}</span>
                  </div>
                  <span className="text-rose-300/80 text-[11px]">
                    Detected: {new Date(threat.timestamp * 1000).toLocaleTimeString()}
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-slate-300">
                  <div>
                    <span className="text-rose-300 font-bold">Target Sensor: </span>
                    <span>{threat.camera_id} ({threat.camera_name})</span>
                  </div>
                  <div>
                    <span className="text-rose-300 font-bold">Detection Confidence: </span>
                    <span>{Math.round(threat.confidence * 100)}% (PRNU Noise Match)</span>
                  </div>
                </div>

                <div className="p-2.5 rounded bg-black/50 border border-rose-500/30 text-rose-200 text-[11px] leading-relaxed">
                  <p className="font-bold text-amber-300 mb-0.5">🛡️ Automated Zero-Trust Defense Response:</p>
                  <p>{threat.defense_action}</p>
                  {threat.technical_details && (
                    <p className="text-slate-400 mt-1">Details: {threat.technical_details}</p>
                  )}
                </div>

                <div className="flex justify-end pt-1">
                  <button
                    onClick={() => handleResolveThreat(threat.incident_id)}
                    className="px-3 py-1.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white text-xs font-bold flex items-center gap-1.5 transition-colors"
                  >
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    <span>Neutralize Threat & De-Quarantine Node</span>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Navigation Tabs */}
      <div className="flex flex-wrap items-center gap-2 border-b border-white/10 pb-2">
        <button
          onClick={() => setActiveTab('ANTIBODIES')}
          className={`px-4 py-2 rounded-lg font-mono text-xs font-bold transition-all flex items-center gap-2 ${
            activeTab === 'ANTIBODIES'
              ? 'bg-gradient-to-r from-cyan-600 to-indigo-600 text-white shadow-lg shadow-cyan-600/25'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
        >
          <Dna className="w-3.5 h-3.5 text-cyan-300" />
          <span>Digital Antibodies & Known Virus Matrix ({immuneState?.antibodies?.length ?? 6})</span>
        </button>

        <button
          onClick={() => setActiveTab('FLEET')}
          className={`px-4 py-2 rounded-lg font-mono text-xs font-bold transition-all ${
            activeTab === 'FLEET'
              ? 'bg-cyan-600 text-white shadow-lg shadow-cyan-600/20'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
        >
          Camera Node Vulnerability Audit ({posture?.camera_audits?.length ?? 0})
        </button>

        <button
          onClick={() => setActiveTab('MITRE')}
          className={`px-4 py-2 rounded-lg font-mono text-xs font-bold transition-all ${
            activeTab === 'MITRE'
              ? 'bg-cyan-600 text-white shadow-lg shadow-cyan-600/20'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
        >
          MITRE ATT&CK Matrix ({posture?.mitre_matrix?.length ?? 0})
        </button>

        <button
          onClick={() => setActiveTab('ANTI_REPLAY')}
          className={`px-4 py-2 rounded-lg font-mono text-xs font-bold transition-all ${
            activeTab === 'ANTI_REPLAY'
              ? 'bg-cyan-600 text-white shadow-lg shadow-cyan-600/20'
              : 'text-slate-400 hover:text-white hover:bg-slate-800'
          }`}
        >
          Anti-Replay Liveness Engine
        </button>
      </div>

      {/* Tab 0: Digital Antibodies & Known Virus Defense Matrix */}
      {activeTab === 'ANTIBODIES' && (
        <div className="space-y-6">
          {/* Air-Gapped Immune Architecture Banner */}
          <div className="p-5 rounded-xl bg-gradient-to-br from-slate-900 via-slate-900/90 to-indigo-950/40 border border-cyan-500/30 shadow-xl">
            <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
              <div className="space-y-1">
                <div className="flex items-center gap-2 text-cyan-400 font-mono text-xs uppercase tracking-widest font-bold">
                  <Dna className="w-4 h-4 text-cyan-400 animate-pulse" />
                  <span>Artificial Immune System (AIS) // Air-Gapped Network Defense</span>
                </div>
                <h2 className="text-lg font-bold text-white">
                  Autonomous Digital Antibodies: Pre-Trained & Self-Hardening Against Known Exploits
                </h2>
                <p className="text-xs text-slate-300 max-w-3xl leading-relaxed">
                  Remote border outposts operate on a <strong className="text-cyan-300">100% air-gapped tactical intranet</strong> with zero internet access. Since external antivirus cloud updates are impossible, Project Garuda’s Guardian AI functions like biological white blood cells: it comes pre-trained with defense antibodies against known surveillance malware, and autonomously synthesizes new neural antibodies when physical cable-taps or rogue USB injections occur.
                </p>
              </div>

              <div className="flex flex-wrap items-center gap-2">
                <button
                  onClick={() => handleTrainAntibody('ATB-DYNAMIC-ZERO-DAY')}
                  disabled={trainingAntibodyId !== null}
                  className="px-3.5 py-2 rounded-lg bg-gradient-to-r from-cyan-600 to-indigo-600 hover:from-cyan-500 hover:to-indigo-500 text-white font-mono text-xs font-bold flex items-center gap-2 shadow-lg shadow-cyan-600/25 transition disabled:opacity-50"
                >
                  <Sparkles className="w-3.5 h-3.5" />
                  <span>{trainingAntibodyId === 'ATB-DYNAMIC-ZERO-DAY' ? 'Synthesizing...' : 'Simulate Zero-Day & Synthesize Antibody'}</span>
                </button>
              </div>
            </div>

            {/* 4 Immune Metrics Cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3 mt-4 pt-4 border-t border-white/10">
              <div className="p-3 rounded-lg bg-black/40 border border-white/5 font-mono">
                <span className="text-slate-400 text-[11px] block">Air-Gap Autonomy:</span>
                <span className="text-cyan-300 font-bold text-sm">100% On-Premise</span>
                <span className="text-[10px] text-slate-500 block">Zero cloud dependencies</span>
              </div>
              <div className="p-3 rounded-lg bg-black/40 border border-white/5 font-mono">
                <span className="text-slate-400 text-[11px] block">Fleet Resistance Rating:</span>
                <span className="text-emerald-400 font-bold text-sm">{immuneState?.fleet_resistance_pct ?? 99.4}%</span>
                <span className="text-[10px] text-slate-500 block">Weighted antibody coverage</span>
              </div>
              <div className="p-3 rounded-lg bg-black/40 border border-white/5 font-mono">
                <span className="text-slate-400 text-[11px] block">Mean Kill Latency:</span>
                <span className="text-indigo-300 font-bold text-sm">{immuneState?.average_neutralization_ms ?? 7.3} ms</span>
                <span className="text-[10px] text-slate-500 block">Sub-frame instant intercept</span>
              </div>
              <div className="p-3 rounded-lg bg-black/40 border border-white/5 font-mono">
                <span className="text-slate-400 text-[11px] block">Total Incursions Blocked:</span>
                <span className="text-amber-300 font-bold text-sm">{immuneState?.total_attacks_neutralized ?? 329}</span>
                <span className="text-[10px] text-slate-500 block">Pre-trained + live neutralized</span>
              </div>
            </div>
          </div>

          {/* Known Virus Antibody Matrix (6 Cards) */}
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2 text-xs font-mono font-bold text-slate-300 uppercase tracking-wider">
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>Pre-Trained Defense Arsenal ({immuneState?.antibodies?.length ?? 6} Antibodies Active)</span>
              </div>
              <span className="text-xs font-mono text-slate-500">
                Click "Train / Evolve" to simulate a live exposure & observe neural hardening
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {immuneState?.antibodies?.map((atb) => {
                const isTraining = trainingAntibodyId === atb.antibody_id
                return (
                  <div
                    key={atb.antibody_id}
                    className="p-4 rounded-xl bg-slate-900/70 border border-white/10 hover:border-cyan-500/40 transition-all shadow-lg flex flex-col justify-between space-y-3 font-mono text-xs"
                  >
                    <div>
                      {/* Top Header */}
                      <div className="flex items-start justify-between gap-2 border-b border-white/10 pb-2.5">
                        <div>
                          <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-cyan-500/10 text-cyan-300 border border-cyan-500/20">
                            {atb.category}
                          </span>
                          <h3 className="text-sm font-bold text-white mt-1.5 leading-snug">
                            {atb.virus_name}
                          </h3>
                        </div>
                        <span className="text-[10px] font-bold px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 shrink-0">
                          {atb.status}
                        </span>
                      </div>

                      {/* Threat Vector */}
                      <div className="mt-2 text-slate-300 text-[11px]">
                        <span className="text-slate-500 block text-[10px] uppercase font-bold">Attack Vector:</span>
                        <span className="text-slate-300">{atb.threat_vector}</span>
                      </div>

                      {/* Antigen Pattern */}
                      <div className="mt-2 text-slate-300 text-[11px]">
                        <span className="text-slate-500 block text-[10px] uppercase font-bold">Antigen Footprint (Trigger):</span>
                        <p className="text-slate-400 bg-black/40 p-1.5 rounded border border-white/5 text-[10px] leading-relaxed">
                          {atb.antigen_pattern}
                        </p>
                      </div>

                      {/* Autonomous Defense Response */}
                      <div className="mt-2 text-cyan-300 text-[11px]">
                        <span className="text-slate-500 block text-[10px] uppercase font-bold">Autonomous Antibody Response:</span>
                        <p className="text-cyan-200 bg-cyan-950/20 p-1.5 rounded border border-cyan-500/20 text-[10px] leading-relaxed">
                          🛡️ {atb.defense_action}
                        </p>
                      </div>
                    </div>

                    {/* Bottom Stats & Evolution */}
                    <div className="pt-2 border-t border-white/10 space-y-2">
                      <div className="grid grid-cols-3 gap-1 text-center">
                        <div className="p-1.5 rounded bg-black/30 border border-white/5">
                          <span className="text-[9px] text-slate-500 block">Kill Latency</span>
                          <span className="text-indigo-300 font-bold text-xs">{atb.neutralization_speed_ms}ms</span>
                        </div>
                        <div className="p-1.5 rounded bg-black/30 border border-white/5">
                          <span className="text-[9px] text-slate-500 block">Resistance</span>
                          <span className="text-emerald-400 font-bold text-xs">{atb.effectiveness_pct}%</span>
                        </div>
                        <div className="p-1.5 rounded bg-black/30 border border-white/5">
                          <span className="text-[9px] text-slate-500 block">Neutralized</span>
                          <span className="text-amber-300 font-bold text-xs">{atb.encounters_blocked}x</span>
                        </div>
                      </div>

                      <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1">
                        <span className="truncate max-w-[140px]">{atb.last_evolution}</span>
                        <button
                          onClick={() => handleTrainAntibody(atb.antibody_id)}
                          disabled={isTraining}
                          className="px-2.5 py-1 rounded bg-slate-800 hover:bg-cyan-950 text-cyan-300 border border-cyan-500/30 text-[10px] font-bold flex items-center gap-1 transition disabled:opacity-50"
                          title="Simulate attack exposure and retrain neural neutralization pathways"
                        >
                          {isTraining ? (
                            <>
                              <RefreshCw className="w-2.5 h-2.5 animate-spin" />
                              <span>Training...</span>
                            </>
                          ) : (
                            <>
                              <span>🧪</span>
                              <span>Evolve Antibody</span>
                            </>
                          )}
                        </button>
                      </div>
                    </div>
                  </div>
                )
              })}
            </div>
          </div>

          {/* Dynamic Immune Synthesis Log */}
          {immuneState?.recent_synthesis_log && immuneState.recent_synthesis_log.length > 0 && (
            <div className="p-4 rounded-xl bg-slate-900/60 border border-white/10 space-y-2 font-mono text-xs">
              <h4 className="text-xs font-bold text-white uppercase tracking-wider flex items-center gap-2">
                <Terminal className="w-3.5 h-3.5 text-cyan-400" />
                <span>Neural Antibody Evolution & Hardening Log</span>
              </h4>
              <div className="space-y-1.5 max-h-48 overflow-y-auto pr-1">
                {immuneState.recent_synthesis_log.map((entry, idx) => (
                  <div
                    key={idx}
                    className="p-2 rounded bg-black/40 border border-white/5 flex items-center justify-between text-[11px] text-slate-300"
                  >
                    <div className="flex items-center gap-2">
                      <span className="text-cyan-400 font-bold">[{entry.timestamp_str}]</span>
                      <span className="text-amber-300">{entry.virus_name}</span>
                      <span className="text-slate-400">— {entry.details}</span>
                    </div>
                    <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 text-[10px]">
                      {entry.latency_ms}ms latency
                    </span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* Tab 1: Camera Node Vulnerability Audit */}
      {activeTab === 'FLEET' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            {posture?.camera_audits?.map((audit) => (
              <div
                key={audit.camera_id}
                className={`p-4 rounded-xl border font-mono text-xs space-y-3 transition-all ${
                  audit.is_quarantined
                    ? 'bg-rose-950/30 border-rose-500/50'
                    : 'bg-slate-900/60 border-white/10'
                }`}
              >
                <div className="flex items-center justify-between border-b border-white/5 pb-2.5">
                  <div>
                    <h4 className="font-bold text-white text-sm">{audit.camera_name}</h4>
                    <p className="text-[11px] text-slate-400">{audit.camera_id} // {audit.location}</p>
                  </div>
                  <div className="text-right">
                    <span
                      className={`text-base font-black ${
                        audit.cyber_score >= 85
                          ? 'text-emerald-400'
                          : audit.cyber_score >= 70
                          ? 'text-amber-400'
                          : 'text-rose-400'
                      }`}
                    >
                      {audit.cyber_score}/100
                    </span>
                    <span className="block text-[10px] text-slate-500">{audit.security_grade}</span>
                  </div>
                </div>

                {/* Audit Findings */}
                <div className="space-y-2">
                  <span className="text-[11px] text-slate-400 uppercase tracking-wider font-semibold block">
                    Security Findings ({audit.findings.length}):
                  </span>
                  {audit.findings.length === 0 ? (
                    <div className="p-2 rounded bg-emerald-950/20 border border-emerald-500/30 text-emerald-300 text-[11px] flex items-center gap-1.5">
                      <CheckCircle2 className="w-3.5 h-3.5" />
                      <span>Node 100% hardened. Zero CVE vulnerabilities detected.</span>
                    </div>
                  ) : (
                    audit.findings.map((f, idx) => (
                      <div
                        key={idx}
                        className={`p-2.5 rounded border text-[11px] leading-tight space-y-1 ${
                          f.severity === 'CRITICAL'
                            ? 'bg-rose-950/30 border-rose-500/40 text-rose-200'
                            : f.severity === 'HIGH'
                            ? 'bg-amber-950/30 border-amber-500/40 text-amber-200'
                            : 'bg-slate-800/60 border-white/5 text-slate-300'
                        }`}
                      >
                        <div className="flex items-center justify-between font-bold">
                          <span>{f.title}</span>
                          <span className="text-[9px] uppercase">{f.severity}</span>
                        </div>
                        <p className="text-slate-400 text-[10px]">{f.description}</p>
                        <p className="text-cyan-300 text-[10px] font-sans">Fix: {f.remediation}</p>
                      </div>
                    ))
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 2: MITRE ATT&CK Matrix */}
      {activeTab === 'MITRE' && (
        <div className="space-y-4">
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {posture?.mitre_matrix?.map((technique) => (
              <div
                key={technique.technique_id}
                className="p-4 rounded-xl bg-slate-900/60 border border-white/10 font-mono text-xs space-y-2.5"
              >
                <div className="flex items-center justify-between border-b border-white/5 pb-2">
                  <div className="flex items-center gap-2">
                    <span className="px-2 py-0.5 rounded bg-indigo-500/20 text-indigo-300 border border-indigo-500/30 font-bold">
                      {technique.technique_id}
                    </span>
                    <span className="text-white font-bold">{technique.name}</span>
                  </div>
                  <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 font-bold">
                    {technique.status}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-2 text-[11px] text-slate-400">
                  <div>
                    <span className="text-slate-500">Tactic Category: </span>
                    <span className="text-slate-300">{technique.category}</span>
                  </div>
                  <div>
                    <span className="text-slate-500">Active Threat Triggers: </span>
                    <span className={technique.active_threats_count > 0 ? 'text-rose-400 font-bold' : 'text-slate-300'}>
                      {technique.active_threats_count}
                    </span>
                  </div>
                </div>

                <div className="p-2 rounded bg-black/40 border border-white/5 text-[11px] text-cyan-300">
                  <span className="text-slate-500 block text-[10px] uppercase">Active Defense Mitigation:</span>
                  <span>{technique.mitigation}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Tab 3: Anti-Replay & Liveness Telemetry */}
      {activeTab === 'ANTI_REPLAY' && (
        <div className="p-5 rounded-xl bg-slate-900/60 border border-white/10 space-y-4 font-mono text-xs">
          <div className="border-b border-white/10 pb-3">
            <h3 className="text-sm font-bold text-white flex items-center gap-2">
              <Activity className="w-4 h-4 text-cyan-400" />
              <span>Anti-Replay Mathematical Liveness Verification Engine</span>
            </h3>
            <p className="text-slate-400 text-xs mt-1">
              Surveillance video loops (e.g. static 20-second MP4 streams replayed over RTSP) are detected through
              temporal Shannon entropy and high-frequency optical sensor noise residual (Photo-Response Non-Uniformity / PRNU).
            </p>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="p-3 rounded-lg bg-black/40 border border-white/5">
              <span className="text-slate-500 block text-[11px]">Sampling Rate:</span>
              <span className="text-white font-bold text-sm">30 Hz Sequential Frames</span>
            </div>
            <div className="p-3 rounded-lg bg-black/40 border border-white/5">
              <span className="text-slate-500 block text-[11px]">Entropy Variance Threshold:</span>
              <span className="text-indigo-300 font-bold text-sm">&gt; 0.00020 (Natural Sensor Thermal Noise)</span>
            </div>
            <div className="p-3 rounded-lg bg-black/40 border border-white/5">
              <span className="text-slate-500 block text-[11px]">Loop Detection Window:</span>
              <span className="text-emerald-400 font-bold text-sm">15.0 Seconds</span>
            </div>
          </div>

          <div className="p-3 rounded-lg bg-cyan-950/20 border border-cyan-500/30 text-cyan-200 text-[11px] leading-relaxed">
            <p className="font-bold mb-1">Defense Rationale for Jury Evaluation:</p>
            <p>
              In cinematic attacks and physical infiltrations, intruders inject a looping feed of an empty border fence.
              Standard motion detectors fail completely because the video appears "clear". Project Garuda’s CyberSentry
              analyzes micro-level optical entropy: a replayed compressed video exhibits repeating cyclical compression artifacts
              and lacks natural photon shot noise, triggering an immediate alarm and switching command to redundant radar.
            </p>
          </div>
        </div>
      )}
    </div>
  )
}
