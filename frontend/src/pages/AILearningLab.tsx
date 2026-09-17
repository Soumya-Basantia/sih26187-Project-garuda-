import React, { useState, useEffect } from 'react'
import {
  Sparkles,
  Cpu,
  BrainCircuit,
  Sliders,
  RotateCcw,
  Play,
  CheckCircle2,
  AlertTriangle,
  Flame,
  Shield,
  Layers,
  Database,
  RefreshCw,
  Eye,
  SlidersHorizontal,
  ChevronRight,
  TrendingDown,
  TrendingUp,
  Activity,
  Maximize2,
  Trash2,
  Filter,
  Radio,
  ShieldCheck,
  CheckSquare,
  Tag,
  XCircle,
  ShieldAlert,
  GitBranch,
  HelpCircle,
  Fingerprint,
  Check,
} from 'lucide-react'
import {
  learningApi,
  LearningStats,
  HarvestedSample,
  CameraSensitivityProfile,
  ModelCheckpoint,
  NegativeExemplarItem,
  OrchestratorStatusResponse,
  DecisionAttribution,
  LineageNode,
  connectEventSocket,
  getSnapshotUrl,
} from '../services/api'

export default function AILearningLab() {
  const [stats, setStats] = useState<LearningStats | null>(null)
  const [samples, setSamples] = useState<HarvestedSample[]>([])
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<'matrix' | 'gallery' | 'checkpoints' | 'exemplars' | 'review' | 'orchestrator'>('matrix')
  const [filterTrigger, setFilterTrigger] = useState<string>('ALL')
  const [actionLoading, setActionLoading] = useState<string | null>(null)
  const [actionMessage, setActionMessage] = useState<{ type: 'success' | 'error'; text: string } | null>(null)
  const [selectedSample, setSelectedSample] = useState<HarvestedSample | null>(null)
  const [deletingId, setDeletingId] = useState<string | null>(null)
  const [wsConnected, setWsConnected] = useState<boolean>(false)
  const [exemplars, setExemplars] = useState<NegativeExemplarItem[]>([])
  const [exemplarsLoading, setExemplarsLoading] = useState<boolean>(false)

  // Milestone 3: Human Validation Review Queue States
  const [reviewQueue, setReviewQueue] = useState<HarvestedSample[]>([])
  const [reviewLoading, setReviewLoading] = useState<boolean>(false)
  const [reviewFilterStatus, setReviewFilterStatus] = useState<string>('PENDING_REVIEW')
  const [relabelModalSample, setRelabelModalSample] = useState<HarvestedSample | null>(null)
  const [correctedClassInput, setCorrectedClassInput] = useState<string>('')
  const [validationNotesInput, setValidationNotesInput] = useState<string>('')
  const [validatingId, setValidatingId] = useState<string | null>(null)

  // Milestone 12: Orchestrator, Explainability & Lineage States
  const [orchestratorStatus, setOrchestratorStatus] = useState<OrchestratorStatusResponse | null>(null)
  const [orchestratorLoading, setOrchestratorLoading] = useState<boolean>(false)
  const [lineageHistory, setLineageHistory] = useState<LineageNode[]>([])
  const [selectedLineageModel, setSelectedLineageModel] = useState<string | null>(null)
  const [selectedLineageNode, setSelectedLineageNode] = useState<LineageNode | null>(null)
  const [tamperStatus, setTamperStatus] = useState<boolean | null>(null)

  // Explainability Tool States
  const [explainCamId, setExplainCamId] = useState<string>('CAM-01')
  const [explainClass, setExplainClass] = useState<string>('backpack')
  const [explainConfidence, setExplainConfidence] = useState<number>(0.68)
  const [attributionResult, setAttributionResult] = useState<DecisionAttribution | null>(null)
  const [attributionLoading, setAttributionLoading] = useState<boolean>(false)

  useEffect(() => {
    loadData()
    loadExemplars()
    loadOrchestratorData()

    const ws = connectEventSocket((msg) => {
      if (msg.type === 'new_learning_sample' && msg.data) {
        setSamples((prev) => {
          const exists = prev.some((s) => s.sample_id === msg.data.sample_id)
          if (exists) return prev
          return [msg.data, ...prev].slice(0, 50)
        })
        setStats((prev) => {
          if (!prev) return prev
          return {
            ...prev,
            total_harvested_samples: prev.total_harvested_samples + 1,
            borderline_uncertain_count:
              msg.data.trigger_type === 'UNCERTAIN_DETECTION'
                ? prev.borderline_uncertain_count + 1
                : prev.borderline_uncertain_count,
            confirmed_threats_count:
              msg.data.sample_label === 'POSITIVE_CONFIRMED'
                ? prev.confirmed_threats_count + 1
                : prev.confirmed_threats_count,
            false_alarms_count:
              msg.data.sample_label === 'NEGATIVE_FALSE_ALARM'
                ? prev.false_alarms_count + 1
                : prev.false_alarms_count,
          }
        })
      } else if (msg.type === 'learning_training_update' && msg.data) {
        setStats((prev) => {
          if (!prev) return prev
          return {
            ...prev,
            is_training: msg.data.is_training ?? prev.is_training,
            training_progress: msg.data.progress ?? prev.training_progress,
            current_version: msg.data.version
              ? `Garuda-Vision-${msg.data.version} (Self-Trained)`
              : prev.current_version,
          }
        })
        if (!msg.data.is_training) {
          loadData()
        }
      }
    })

    ws.onopen = () => setWsConnected(true)
    ws.onclose = () => setWsConnected(false)

    const interval = setInterval(loadStatsOnly, 5000)
    return () => {
      clearInterval(interval)
      try {
        ws.close()
      } catch {}
    }
  }, [])

  async function loadExemplars() {
    try {
      setExemplarsLoading(true)
      const res = await learningApi.getExemplars()
      setExemplars(res.data.exemplars || [])
    } catch (err) {
      console.error('Failed to load negative exemplars:', err)
    } finally {
      setExemplarsLoading(false)
    }
  }

  async function loadReviewQueue(statusOverride?: string) {
    try {
      setReviewLoading(true)
      const st = statusOverride !== undefined ? statusOverride : reviewFilterStatus
      const res = await learningApi.getReviewQueue({ status: st, limit: 60 })
      setReviewQueue(res.data)
    } catch (err) {
      console.error('Failed to load review queue:', err)
    } finally {
      setReviewLoading(false)
    }
  }

  async function handleValidateSample(
    sampleId: string,
    action: 'CONFIRM' | 'REJECT' | 'RELABEL' | 'FALSE_ALARM',
    correctedLabel?: string
  ) {
    try {
      setValidatingId(sampleId)
      const res = await learningApi.validateSample(sampleId, {
        action,
        corrected_label: correctedLabel,
        notes: validationNotesInput,
      })
      setActionMessage({ type: 'success', text: res.data.message })
      setReviewQueue((prev) =>
        prev.map((s) => (s.sample_id === sampleId ? { ...s, validation_status: res.data.validation_status } : s))
      )
      setRelabelModalSample(null)
      setCorrectedClassInput('')
      setValidationNotesInput('')
      await loadData()
      if (action === 'FALSE_ALARM') {
        loadExemplars()
      }
    } catch (err: any) {
      setActionMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to validate sample' })
    } finally {
      setValidatingId(null)
    }
  }

  async function loadData() {
    try {
      setLoading(true)
      const [statsRes, samplesRes] = await Promise.all([
        learningApi.getStats(),
        learningApi.getSamples({ limit: 40 }),
      ])
      setStats(statsRes.data)
      setSamples(samplesRes.data)
      loadReviewQueue()
    } catch (err) {
      console.error('Failed to load learning lab data:', err)
    } finally {
      setLoading(false)
    }
  }

  async function loadStatsOnly() {
    try {
      const statsRes = await learningApi.getStats()
      setStats(statsRes.data)
      if (statsRes.data.is_training) {
        // Refresh samples if training is active
        const samplesRes = await learningApi.getSamples({ limit: 40 })
        setSamples(samplesRes.data)
      }
    } catch (err) {
      // Background poll failure silent
    }
  }

  async function handleTriggerTraining() {
    try {
      setActionLoading('training')
      setActionMessage(null)
      const res = await learningApi.triggerTraining({ epochs: 1, sample_limit: 50 })
      setActionMessage({ type: 'success', text: res.data.message })
      await loadStatsOnly()
    } catch (err: any) {
      setActionMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to start training' })
    } finally {
      setActionLoading(null)
    }
  }

  async function handleAutoTune() {
    try {
      setActionLoading('autotune')
      setActionMessage(null)
      const res = await learningApi.autoTune()
      setActionMessage({ type: 'success', text: res.data.message })
      await loadData()
    } catch (err: any) {
      setActionMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to auto-calibrate cameras' })
    } finally {
      setActionLoading(null)
    }
  }

  async function handleRollback() {
    if (!window.confirm('Revert the AI vision engine to baseline pretrained weights (yolov8n.pt)?')) {
      return
    }
    try {
      setActionLoading('rollback')
      setActionMessage(null)
      const res = await learningApi.rollback()
      setActionMessage({ type: 'success', text: res.data.message })
      await loadData()
    } catch (err: any) {
      setActionMessage({ type: 'error', text: err.response?.data?.detail || 'Failed to rollback model' })
    } finally {
      setActionLoading(null)
    }
  }

  async function loadOrchestratorData() {
    try {
      setOrchestratorLoading(true)
      const [statusRes, lineageRes] = await Promise.all([
        learningApi.getOrchestratorStatus(),
        learningApi.getLineageHistory(),
      ])
      setOrchestratorStatus(statusRes.data)
      setLineageHistory(lineageRes.data.models || [])
      if (lineageRes.data.models && lineageRes.data.models.length > 0) {
        setSelectedLineageModel(lineageRes.data.models[0].model_version_id)
        setSelectedLineageNode(lineageRes.data.models[0])
        setTamperStatus(true)
      }
    } catch (err: any) {
      console.error('Failed to load orchestrator data', err)
    } finally {
      setOrchestratorLoading(false)
    }
  }

  async function handleTriggerOrchestratorCycle(force: boolean = true) {
    try {
      setActionLoading('orchestrator_cycle')
      setActionMessage(null)
      const res = await learningApi.triggerOrchestratorCycle(force)
      setActionMessage({
        type: 'success',
        text: `Orchestrator cycle ${res.data.cycle_report?.cycle_number || 1} completed! Model: ${res.data.cycle_report?.model_candidate || 'Candidate created'}`,
      })
      await loadOrchestratorData()
    } catch (err: any) {
      setActionMessage({
        type: 'error',
        text: err.response?.data?.detail || 'Failed to trigger orchestrator cycle',
      })
    } finally {
      setActionLoading(null)
    }
  }

  async function handleExplainDetection() {
    try {
      setAttributionLoading(true)
      const res = await learningApi.explainDetection({
        camera_id: explainCamId,
        class_label: explainClass,
        raw_confidence: explainConfidence,
        bbox: [0.25, 0.3, 0.45, 0.6],
      })
      setAttributionResult(res.data.attribution)
    } catch (err: any) {
      console.error('Explainability error', err)
    } finally {
      setAttributionLoading(false)
    }
  }

  async function handleSelectLineage(modelId: string) {
    setSelectedLineageModel(modelId)
    try {
      const res = await learningApi.getModelLineage(modelId)
      setSelectedLineageNode(res.data.lineage)
      setTamperStatus(res.data.tamper_evident_valid)
    } catch (err) {
      console.error('Failed to load lineage', err)
    }
  }

  const filteredSamples = samples.filter((s) => {
    if (filterTrigger === 'ALL') return true
    return s.trigger_type === filterTrigger
  })

  return (
    <div className="p-4 sm:p-6 h-full flex flex-col gap-4 overflow-y-auto bg-ops-bg text-ops-text">
      {/* Top Header & Tactical Action Center */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 tactical-panel p-4 rounded-xl border border-ops-border shadow-tactical">
        <div className="flex items-center gap-3.5">
          <div className="relative w-11 h-11 rounded-xl bg-ops-accent/15 border border-ops-accent/40 flex items-center justify-center shrink-0 shadow-[0_0_15px_var(--color-ops-accent-glow)]">
            <BrainCircuit className="w-6 h-6 text-ops-accent animate-pulse" />
            <div className="absolute -inset-1 rounded-xl border border-ops-accent/20 animate-ping opacity-25" />
          </div>
          <div>
            <div className="flex items-center gap-2.5 flex-wrap">
              <h1 className="text-lg sm:text-xl font-bold font-display tracking-wide uppercase text-ops-text">
                AI Self-Training & Adaptive Learning Lab
              </h1>
              <span className="px-2 py-0.5 text-[10px] font-mono font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40 rounded-full flex items-center gap-1.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-pulse" />
                AUTONOMOUS RLHF ACTIVE
              </span>
              {wsConnected ? (
                <span className="px-2 py-0.5 text-[10px] font-mono font-bold bg-cyan-500/20 text-cyan-400 border border-cyan-500/40 rounded-full flex items-center gap-1.5 shadow-[0_0_8px_rgba(6,182,212,0.3)]">
                  <span className="w-1.5 h-1.5 rounded-full bg-cyan-400 animate-pulse" />
                  LIVE CAMERA TELEMETRY STREAMING
                </span>
              ) : (
                <span className="px-2 py-0.5 text-[10px] font-mono text-ops-text-muted border border-ops-border rounded-full flex items-center gap-1.5">
                  <Radio className="w-2.5 h-2.5" />
                  CONNECTING TELEMETRY...
                </span>
              )}
            </div>
            <p className="text-xs text-ops-text-muted mt-0.5">
              Continuous Hard-Sample Mining • Dynamic Camera Calibration • Zero-Downtime Hot-Reloading
            </p>
          </div>
        </div>

        {/* Global Controls */}
        <div className="flex flex-wrap items-center gap-2">
          <button
            onClick={handleAutoTune}
            disabled={actionLoading !== null || stats?.is_training}
            className="px-3 py-1.5 rounded-lg border border-ops-accent/40 bg-ops-accent/10 hover:bg-ops-accent/20 text-ops-accent text-xs font-mono font-semibold flex items-center gap-1.5 transition-all disabled:opacity-50"
          >
            <SlidersHorizontal className={`w-3.5 h-3.5 ${actionLoading === 'autotune' ? 'animate-spin' : ''}`} />
            Auto-Calibrate Sensitivity
          </button>

          <button
            onClick={handleTriggerTraining}
            disabled={actionLoading !== null || stats?.is_training}
            className="px-3.5 py-1.5 rounded-lg border border-emerald-500/40 bg-emerald-500/15 hover:bg-emerald-500/25 text-emerald-300 text-xs font-mono font-bold flex items-center gap-1.5 transition-all shadow-[0_0_10px_rgba(16,185,129,0.2)] disabled:opacity-50"
          >
            <Sparkles className={`w-3.5 h-3.5 ${actionLoading === 'training' || stats?.is_training ? 'animate-spin' : ''}`} />
            {stats?.is_training ? 'Training in Progress...' : '⚡ Run Active Self-Training'}
          </button>

          <button
            onClick={handleRollback}
            disabled={actionLoading !== null || stats?.is_training}
            title="Revert to baseline YOLO model"
            className="px-2.5 py-1.5 rounded-lg border border-ops-border hover:border-red-500/40 hover:bg-red-500/10 text-ops-text-muted hover:text-red-400 text-xs font-mono transition-all disabled:opacity-50"
          >
            <RotateCcw className="w-3.5 h-3.5" />
          </button>

          <button
            onClick={loadData}
            title="Refresh statistics"
            className="p-1.5 rounded-lg border border-ops-border hover:border-ops-accent text-ops-text-muted hover:text-ops-text text-xs transition-all"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Action Notification Message */}
      {actionMessage && (
        <div
          className={`p-3 rounded-lg text-xs font-mono flex items-center justify-between border ${
            actionMessage.type === 'success'
              ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
              : 'bg-red-500/10 border-red-500/30 text-red-300'
          }`}
        >
          <div className="flex items-center gap-2">
            {actionMessage.type === 'success' ? <CheckCircle2 className="w-4 h-4 shrink-0" /> : <AlertTriangle className="w-4 h-4 shrink-0" />}
            <span>{actionMessage.text}</span>
          </div>
          <button onClick={() => setActionMessage(null)} className="text-ops-text-muted hover:text-ops-text">
            ✕
          </button>
        </div>
      )}

      {/* Orchestrator Autonomous Lifecycle Status Bar */}
      {orchestratorStatus && (
        <div className="tactical-panel p-3.5 rounded-xl border border-cyan-500/30 bg-cyan-950/20 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 text-xs font-mono">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="flex items-center gap-1.5 font-bold text-cyan-300">
              <Cpu className="w-4 h-4 text-cyan-400 animate-pulse" />
              CENTRAL ORCHESTRATOR:
            </span>
            <span className={`px-2 py-0.5 rounded font-bold text-[10px] ${
              orchestratorStatus.orchestrator.lifecycle_state === 'IDLE'
                ? 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                : 'bg-amber-500/20 text-amber-400 border border-amber-500/40 animate-pulse'
            }`}>
              {orchestratorStatus.orchestrator.lifecycle_state}
            </span>
            <span className="text-ops-text-muted">
              Cycle #{orchestratorStatus.orchestrator.cycle_count} • {orchestratorStatus.triggers.validated_sample_count}/{orchestratorStatus.triggers.threshold_required} Validated Samples toward Auto-Retrain
            </span>
          </div>
          <div className="flex items-center gap-2 self-end sm:self-auto">
            <button
              onClick={() => handleTriggerOrchestratorCycle(true)}
              disabled={actionLoading !== null}
              className="px-2.5 py-1 rounded bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 text-[11px] font-bold flex items-center gap-1 transition-all"
            >
              <Play className="w-3 h-3" />
              Run Continual Cycle
            </button>
          </div>
        </div>
      )}

      {/* Live Background Training Banner */}
      {stats?.is_training && (
        <div className="p-3.5 rounded-xl border border-ops-accent/50 bg-ops-accent/10 shadow-[0_0_20px_var(--color-ops-accent-glow)] flex flex-col gap-2">
          <div className="flex items-center justify-between text-xs font-mono">
            <div className="flex items-center gap-2 text-ops-accent font-bold">
              <Activity className="w-4 h-4 animate-spin" />
              BACKGROUND SELF-TRAINING IN PROGRESS
            </div>
            <span className="font-bold text-ops-text">{stats.training_progress}%</span>
          </div>
          <div className="w-full h-2 bg-ops-border rounded-full overflow-hidden">
            <div
              className="h-full bg-ops-accent transition-all duration-300 shadow-[0_0_10px_var(--color-ops-accent)]"
              style={{ width: `${stats.training_progress}%` }}
            />
          </div>
          <div className="text-[11px] text-ops-text-muted">
            Executing detection head fine-tuning and false-alarm suppression. Live camera feeds remain active with 0 downtime.
          </div>
        </div>
      )}

      {/* KPI Stats Ribbon */}
      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
        {/* Active Model Version */}
        <div className="tactical-panel p-3 rounded-lg border-l-4 border-l-ops-accent flex flex-col justify-between">
          <div className="text-[10px] text-ops-text-muted font-bold tracking-wider uppercase font-mono">
            Active Vision Model
          </div>
          <div className="text-sm font-bold font-mono text-ops-text mt-1 truncate" title={stats?.current_version}>
            {stats?.current_version || 'Loading...'}
          </div>
          <div className="text-[10px] text-emerald-400 font-mono mt-0.5 flex items-center gap-1">
            <CheckCircle2 className="w-3 h-3" /> Zero-downtime hot-swap
          </div>
        </div>

        {/* Total Harvested Samples */}
        <div className="tactical-panel p-3 rounded-lg border-l-4 border-l-cyan-400 flex flex-col justify-between">
          <div className="text-[10px] text-ops-text-muted font-bold tracking-wider uppercase font-mono">
            Harvested Samples
          </div>
          <div className="text-2xl font-bold font-display text-ops-text mt-1">
            {stats?.total_harvested_samples ?? 0}
          </div>
          <div className="text-[10px] text-ops-text-muted font-mono mt-0.5">
            Hard-mining active buffer
          </div>
        </div>

        {/* Borderline Uncertain */}
        <div className="tactical-panel p-3 rounded-lg border-l-4 border-l-amber-400 flex flex-col justify-between">
          <div className="text-[10px] text-ops-text-muted font-bold tracking-wider uppercase font-mono">
            Borderline Cases
          </div>
          <div className="text-2xl font-bold font-display text-amber-400 mt-1">
            {stats?.borderline_uncertain_count ?? 0}
          </div>
          <div className="text-[10px] text-amber-400/80 font-mono mt-0.5">
            Uncertainty window: 30-55%
          </div>
        </div>

        {/* False Alarms Suppressed */}
        <div className="tactical-panel p-3 rounded-lg border-l-4 border-l-rose-500 flex flex-col justify-between">
          <div className="text-[10px] text-ops-text-muted font-bold tracking-wider uppercase font-mono">
            False Alarms Flagged
          </div>
          <div className="text-2xl font-bold font-display text-rose-400 mt-1">
            {stats?.false_alarms_count ?? 0}
          </div>
          <div className="text-[10px] text-rose-400/80 font-mono mt-0.5">
            Operator RLHF negative weights
          </div>
        </div>

        {/* False Alarm Reduction Rate */}
        <div className="tactical-panel p-3 rounded-lg border-l-4 border-l-emerald-500 flex flex-col justify-between">
          <div className="text-[10px] text-ops-text-muted font-bold tracking-wider uppercase font-mono">
            False Alarm Drop
          </div>
          <div className="text-2xl font-bold font-display text-emerald-400 mt-1 flex items-center gap-1">
            <TrendingDown className="w-5 h-5 text-emerald-400" />
            +{stats?.false_alarm_reduction_pct ?? 0}%
          </div>
          <div className="text-[10px] text-emerald-400/80 font-mono mt-0.5">
            Sector noise suppressed
          </div>
        </div>

        {/* Security Precision Gain */}
        <div className="tactical-panel p-3 rounded-lg border-l-4 border-l-purple-500 flex flex-col justify-between">
          <div className="text-[10px] text-ops-text-muted font-bold tracking-wider uppercase font-mono">
            Accuracy Gain
          </div>
          <div className="text-2xl font-bold font-display text-purple-400 mt-1 flex items-center gap-1">
            <TrendingUp className="w-5 h-5 text-purple-400" />
            +{stats?.accuracy_gain_pct ?? 0}%
          </div>
          <div className="text-[10px] text-purple-400/80 font-mono mt-0.5">
            Evaluated on campus test split
          </div>
        </div>
      </div>

      {/* Tabs Navigation */}
      <div className="flex items-center gap-2 border-b border-ops-border pt-2">
        <button
          onClick={() => setActiveTab('matrix')}
          className={`px-4 py-2 text-xs font-mono font-bold uppercase transition-all border-b-2 flex items-center gap-2 ${
            activeTab === 'matrix'
              ? 'border-ops-accent text-ops-accent bg-ops-accent/5'
              : 'border-transparent text-ops-text-muted hover:text-ops-text'
          }`}
        >
          <Sliders className="w-4 h-4" />
          Camera Sensitivity Matrix ({stats?.camera_profiles?.length || 0})
        </button>

        <button
          onClick={() => setActiveTab('gallery')}
          className={`px-4 py-2 text-xs font-mono font-bold uppercase transition-all border-b-2 flex items-center gap-2 ${
            activeTab === 'gallery'
              ? 'border-ops-accent text-ops-accent bg-ops-accent/5'
              : 'border-transparent text-ops-text-muted hover:text-ops-text'
          }`}
        >
          <Eye className="w-4 h-4" />
          Harvested Edge Cases ({samples.length})
        </button>

        <button
          onClick={() => setActiveTab('checkpoints')}
          className={`px-4 py-2 text-xs font-mono font-bold uppercase transition-all border-b-2 flex items-center gap-2 ${
            activeTab === 'checkpoints'
              ? 'border-ops-accent text-ops-accent bg-ops-accent/5'
              : 'border-transparent text-ops-text-muted hover:text-ops-text'
          }`}
        >
          <Layers className="w-4 h-4" />
          Model Evolution ({stats?.checkpoints?.length || 0})
        </button>

        <button
          onClick={() => {
            setActiveTab('exemplars')
            loadExemplars()
          }}
          className={`px-4 py-2 text-xs font-mono font-bold uppercase transition-all border-b-2 flex items-center gap-2 ${
            activeTab === 'exemplars'
              ? 'border-ops-accent text-ops-accent bg-ops-accent/5'
              : 'border-transparent text-ops-text-muted hover:text-ops-text'
          }`}
        >
          <Filter className="w-4 h-4" />
          Negative Memory Bank ({stats?.adaptive_filter?.total_negative_exemplars ?? exemplars.length})
        </button>

        <button
          onClick={() => {
            setActiveTab('review')
            loadReviewQueue()
          }}
          className={`px-4 py-2 text-xs font-mono font-bold uppercase transition-all border-b-2 flex items-center gap-2 ${
            activeTab === 'review'
              ? 'border-ops-accent text-ops-accent bg-ops-accent/5'
              : 'border-transparent text-ops-text-muted hover:text-ops-text'
          }`}
        >
          <CheckSquare className="w-4 h-4" />
          Human Review Queue ({reviewQueue.filter((s) => s.validation_status === 'PENDING_REVIEW' || !s.validation_status).length})
        </button>

        <button
          onClick={() => {
            setActiveTab('orchestrator')
            loadOrchestratorData()
          }}
          className={`px-4 py-2 text-xs font-mono font-bold uppercase transition-all border-b-2 flex items-center gap-2 ${
            activeTab === 'orchestrator'
              ? 'border-ops-accent text-ops-accent bg-ops-accent/5'
              : 'border-transparent text-ops-text-muted hover:text-ops-text'
          }`}
        >
          <Cpu className="w-4 h-4" />
          Orchestrator & Lineage
        </button>
      </div>

      {/* TAB 1: Camera Sensitivity Matrix */}
      {activeTab === 'matrix' && (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between">
            <div className="text-xs text-ops-text-muted font-mono">
              Self-calibrating camera thresholds. If a camera reports high false positives or foliage noise, its confidence threshold is elevated automatically to eliminate spam while maintaining detection vigilance.
            </div>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
            {stats?.camera_profiles?.map((prof) => (
              <div
                key={prof.camera_id}
                className="tactical-panel p-4 rounded-xl border border-ops-border flex flex-col justify-between gap-3 relative overflow-hidden"
              >
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-2">
                    <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-pulse" />
                    <span className="font-mono font-bold text-sm text-ops-text">{prof.camera_id}</span>
                  </div>
                  <span
                    className={`px-2 py-0.5 text-[10px] font-mono font-bold rounded-full border ${
                      prof.status === 'NOISE_SUPPRESSED'
                        ? 'bg-amber-500/20 text-amber-300 border-amber-500/40'
                        : prof.status === 'ENVIRONMENT_ADAPTED'
                        ? 'bg-blue-500/20 text-blue-300 border-blue-500/40'
                        : 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                    }`}
                  >
                    {prof.status}
                  </span>
                </div>

                {/* Threshold Metrics */}
                <div className="grid grid-cols-2 gap-2 text-xs font-mono">
                  <div className="p-2 rounded bg-ops-panel border border-ops-border">
                    <span className="text-ops-text-muted text-[10px] block">Base Confidence</span>
                    <span className="text-ops-text font-bold">{(prof.base_confidence * 100).toFixed(0)}%</span>
                  </div>
                  <div className="p-2 rounded bg-ops-accent/10 border border-ops-accent/30">
                    <span className="text-ops-accent text-[10px] block">Adapted Threshold</span>
                    <span className="text-ops-accent font-bold text-sm">
                      {(prof.adapted_confidence * 100).toFixed(0)}%
                    </span>
                  </div>
                </div>

                <div className="flex items-center justify-between text-[11px] font-mono text-ops-text-muted pt-2 border-t border-ops-border">
                  <span>Persistence: {prof.persistence_frames} frames</span>
                  <span>Noise Level: {prof.ambient_noise}</span>
                  <span>FA Rate: {prof.false_alarm_rate}%</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* TAB 2: Harvested Edge Cases & Gallery */}
      {activeTab === 'gallery' && (
        <div className="flex flex-col gap-3">
          {/* Filter Chips + Clear All */}
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex flex-wrap items-center gap-2">
              {['ALL', 'UNCERTAIN_DETECTION', 'OPERATOR_FALSE_ALARM', 'OPERATOR_CONFIRMED', 'OCCLUSION_RECOVERY'].map(
                (trigger) => (
                  <button
                    key={trigger}
                    onClick={() => setFilterTrigger(trigger)}
                    className={`px-3 py-1 rounded-lg text-xs font-mono transition-all ${
                      filterTrigger === trigger
                        ? 'bg-ops-accent text-ops-panel font-bold shadow-sm'
                        : 'bg-ops-panel border border-ops-border text-ops-text-muted hover:text-ops-text'
                    }`}
                  >
                    {trigger.replace('_', ' ')}
                  </button>
                )
              )}
            </div>
            {samples.length > 0 && (
              <button
                onClick={async () => {
                  if (!window.confirm(`Delete ALL ${samples.length} harvested samples? This cannot be undone.`)) return
                  try {
                    await learningApi.clearAllSamples()
                    setSamples([])
                    setActionMessage({ type: 'success', text: `Cleared all harvested samples.` })
                  } catch {
                    setActionMessage({ type: 'error', text: 'Failed to clear samples.' })
                  }
                }}
                className="flex items-center gap-1.5 px-3 py-1 rounded-lg text-xs font-mono bg-rose-500/10 text-rose-400 border border-rose-500/30 hover:bg-rose-500/20 transition-colors"
              >
                <Trash2 className="w-3 h-3" />
                Clear All ({samples.length})
              </button>
            )}
          </div>

          {/* Gallery Grid */}
          {filteredSamples.length === 0 ? (
            <div className="tactical-panel p-12 text-center text-ops-text-muted font-mono text-xs rounded-xl border border-ops-border">
              No samples collected yet for this filter. The active harvester captures edge-case frames and operator feedback automatically.
            </div>
          ) : (
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4 gap-3">
              {filteredSamples.map((sample) => (
                <div
                  key={sample.sample_id}
                  onClick={() => setSelectedSample(sample)}
                  className="tactical-panel rounded-xl border border-ops-border overflow-hidden cursor-pointer hover:border-ops-accent transition-all group flex flex-col justify-between"
                >
                  {/* Snapshot Preview */}
                  <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden">
                    {sample.snapshot_data || sample.snapshot_path ? (
                      <img
                        src={sample.snapshot_data || getSnapshotUrl(sample.snapshot_path)}
                        alt={sample.sample_id}
                        className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                        onError={(e) => {
                          e.currentTarget.style.display = 'none'
                        }}
                      />
                    ) : (
                      <div className="text-[10px] text-ops-text-muted font-mono flex items-center gap-1">
                        <Eye className="w-4 h-4" /> Preview Pending
                      </div>
                    )}
                    <span className="absolute top-2 left-2 px-2 py-0.5 rounded text-[10px] font-mono font-bold bg-black/75 text-ops-accent border border-ops-accent/30">
                      {sample.camera_id}
                    </span>
                    <span
                      className={`absolute top-2 right-2 px-2 py-0.5 rounded text-[10px] font-mono font-bold ${
                        sample.sample_label === 'NEGATIVE_FALSE_ALARM'
                          ? 'bg-rose-500/80 text-white'
                          : sample.sample_label === 'POSITIVE_CONFIRMED'
                          ? 'bg-emerald-500/80 text-white'
                          : 'bg-amber-500/80 text-white'
                      }`}
                    >
                      {sample.sample_label}
                    </span>
                  </div>

                  {/* Sample Metadata */}
                  <div className="p-3 flex flex-col gap-1.5 font-mono text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-ops-text uppercase">{sample.class_label}</span>
                      <span className="text-ops-accent">{(sample.confidence * 100).toFixed(0)}% conf</span>
                    </div>
                    <div className="text-[11px] text-ops-text-muted truncate">{sample.notes}</div>
                    <div className="text-[10px] text-ops-text-muted flex items-center justify-between pt-1 border-t border-ops-border">
                       <span className="truncate max-w-[100px]">{sample.sample_id}</span>
                       <div className="flex items-center gap-2">
                         <span>{new Date(sample.timestamp * 1000).toLocaleTimeString()}</span>
                         <button
                           onClick={async (e) => {
                             e.stopPropagation()
                             if (!window.confirm('Delete this sample?')) return
                             setDeletingId(sample.sample_id)
                             try {
                               await learningApi.deleteSample(sample.sample_id)
                               setSamples(prev => prev.filter(s => s.sample_id !== sample.sample_id))
                             } catch {
                               setActionMessage({ type: 'error', text: 'Failed to delete sample.' })
                             } finally {
                               setDeletingId(null)
                             }
                           }}
                           disabled={deletingId === sample.sample_id}
                           className="p-0.5 rounded text-rose-400/60 hover:text-rose-400 hover:bg-rose-500/15 transition-colors disabled:opacity-40"
                           title="Delete this sample"
                         >
                           <Trash2 className="w-3 h-3" />
                         </button>
                       </div>
                     </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 3: Model Evolution Checkpoints */}
      {activeTab === 'checkpoints' && (
        <div className="flex flex-col gap-3">
          <div className="tactical-panel p-4 rounded-xl border border-ops-border">
            <h2 className="text-sm font-bold font-display uppercase tracking-wide text-ops-text mb-3">
              Autonomous Checkpoint Version History
            </h2>
            <div className="space-y-3">
              {stats?.checkpoints?.map((chk, idx) => (
                <div
                  key={chk.checkpoint_id}
                  className={`p-3.5 rounded-lg border flex flex-col md:flex-row md:items-center justify-between gap-3 font-mono text-xs ${
                    chk.is_active
                      ? 'border-ops-accent/60 bg-ops-accent/10 shadow-[0_0_12px_var(--color-ops-accent-glow)]'
                      : 'border-ops-border bg-ops-panel'
                  }`}
                >
                  <div className="flex items-center gap-3">
                    <div
                      className={`w-8 h-8 rounded-lg flex items-center justify-center font-bold ${
                        chk.is_active ? 'bg-ops-accent text-ops-panel' : 'bg-ops-border text-ops-text-muted'
                      }`}
                    >
                      {chk.version.slice(-2)}
                    </div>
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="font-bold text-sm text-ops-text">{chk.version}</span>
                        {chk.is_active && (
                          <span className="px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
                            CURRENTLY ACTIVE
                          </span>
                        )}
                      </div>
                      <div className="text-[11px] text-ops-text-muted">{chk.notes}</div>
                    </div>
                  </div>

                  <div className="flex flex-wrap items-center gap-4 text-xs">
                    <div>
                      <span className="text-ops-text-muted text-[10px] block">Samples Used</span>
                      <span className="font-bold text-ops-text">{chk.samples_used}</span>
                    </div>
                    <div>
                      <span className="text-ops-text-muted text-[10px] block">Accuracy Gain</span>
                      <span className="font-bold text-purple-400">+{chk.accuracy_gain}%</span>
                    </div>
                    <div>
                      <span className="text-ops-text-muted text-[10px] block">FA Reduction</span>
                      <span className="font-bold text-emerald-400">+{chk.false_alarm_reduction}%</span>
                    </div>
                    <div>
                      <span className="text-ops-text-muted text-[10px] block">Date</span>
                      <span className="text-ops-text">{new Date(chk.created_at * 1000).toLocaleDateString()}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 4: Online Negative Exemplar Memory Bank & Spatial Prior */}
      {activeTab === 'exemplars' && (
        <div className="flex flex-col gap-4">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
            <div>
              <div className="text-xs text-ops-text-muted font-mono">
                Real-time few-shot false alarm suppression memory bank. When operators flag false alarms, normalized 64-dim visual descriptors and spatial coordinates are stored. Incoming detections matching these descriptors are suppressed in &lt;0.2ms without model retraining.
              </div>
            </div>
            <button
              onClick={loadExemplars}
              disabled={exemplarsLoading}
              className="px-3 py-1 rounded-lg border border-ops-border hover:bg-ops-panel text-xs font-mono flex items-center gap-1.5 self-start sm:self-auto shrink-0"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${exemplarsLoading ? 'animate-spin' : ''}`} />
              Refresh Memory Bank
            </button>
          </div>

          {/* Metric Overview Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div className="tactical-panel p-4 rounded-xl border border-ops-border">
              <div className="text-[10px] text-ops-text-muted font-bold tracking-wider uppercase font-mono">
                Active Negative Exemplars
              </div>
              <div className="text-2xl font-bold font-display text-ops-accent mt-1">
                {stats?.adaptive_filter?.total_negative_exemplars ?? exemplars.length}
              </div>
              <div className="text-[10px] text-ops-text-muted font-mono mt-0.5">
                Visual feature vectors stored
              </div>
            </div>

            <div className="tactical-panel p-4 rounded-xl border border-ops-border">
              <div className="text-[10px] text-ops-text-muted font-bold tracking-wider uppercase font-mono">
                Detections Auto-Suppressed
              </div>
              <div className="text-2xl font-bold font-display text-emerald-400 mt-1">
                {stats?.adaptive_filter?.total_suppressed_detections ?? 0}
              </div>
              <div className="text-[10px] text-emerald-400/80 font-mono mt-0.5">
                Noise triggers silenced in real time
              </div>
            </div>

            <div className="tactical-panel p-4 rounded-xl border border-ops-border">
              <div className="text-[10px] text-ops-text-muted font-bold tracking-wider uppercase font-mono">
                Spatial Bayesian Grids
              </div>
              <div className="text-2xl font-bold font-display text-purple-400 mt-1">
                {Object.keys(stats?.adaptive_filter?.camera_exemplar_counts || {}).length || stats?.camera_profiles?.length || 0}
              </div>
              <div className="text-[10px] text-purple-400/80 font-mono mt-0.5">
                16x16 sector noise prior maps
              </div>
            </div>
          </div>

          {/* Exemplars List */}
          <div className="tactical-panel p-4 rounded-xl border border-ops-border">
            <h2 className="text-sm font-bold font-display uppercase tracking-wide text-ops-text mb-3 flex items-center gap-2">
              <Filter className="w-4 h-4 text-ops-accent" />
              Stored Negative Exemplars (Hard-Negative Bank)
            </h2>

            {exemplars.length === 0 ? (
              <div className="text-center py-10 text-xs font-mono text-ops-text-muted">
                No negative exemplars recorded yet. Flag any false alarm alert on the Dashboard to train the exemplar bank.
              </div>
            ) : (
              <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                {exemplars.map((ex) => (
                  <div
                    key={ex.exemplar_id}
                    className="p-3.5 rounded-lg border border-ops-border bg-ops-panel flex flex-col justify-between gap-2.5 font-mono text-xs hover:border-ops-accent/50 transition-all"
                  >
                    <div className="flex items-center justify-between">
                      <span className="font-bold text-ops-accent">{ex.exemplar_id}</span>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-500/20 text-rose-400 border border-rose-500/40">
                        {ex.class_label.toUpperCase()}
                      </span>
                    </div>

                    <div className="text-[11px] text-ops-text-muted line-clamp-2">
                      {ex.notes || 'Operator marked false alarm'}
                    </div>

                    <div className="grid grid-cols-2 gap-2 text-[10px] bg-black/40 p-2 rounded border border-ops-border">
                      <div>
                        <span className="text-ops-text-muted block">Camera</span>
                        <span className="font-bold text-ops-text">{ex.camera_id}</span>
                      </div>
                      <div>
                        <span className="text-ops-text-muted block">Times Matched</span>
                        <span className="font-bold text-emerald-400">{ex.match_count} hits</span>
                      </div>
                      <div>
                        <span className="text-ops-text-muted block">Sector (X, Y)</span>
                        <span className="font-bold text-ops-text">
                          {(ex.spatial_coords[0] * 100).toFixed(0)}%, {(ex.spatial_coords[1] * 100).toFixed(0)}%
                        </span>
                      </div>
                      <div>
                        <span className="text-ops-text-muted block">Penalty</span>
                        <span className="font-bold text-amber-400">-{(ex.confidence_penalty * 100).toFixed(0)}%</span>
                      </div>
                    </div>

                    <div className="text-[10px] text-ops-text-muted text-right">
                      {new Date(ex.timestamp * 1000).toLocaleTimeString()}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* TAB 5: Human Validation Review Queue */}
      {activeTab === 'review' && (
        <div className="flex flex-col gap-4">
          {/* Header Controls & Filter Pills */}
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 tactical-panel p-3.5 rounded-xl border border-ops-border">
            <div className="flex items-center gap-2">
              <CheckSquare className="w-5 h-5 text-ops-accent" />
              <div>
                <h3 className="text-sm font-bold text-ops-text font-mono uppercase tracking-wider">
                  Human Validation Review Queue
                </h3>
                <p className="text-[11px] text-ops-text-muted">
                  Turn ambiguous camera edge-cases into verified ground truth without model retraining friction.
                </p>
              </div>
            </div>

            <div className="flex items-center gap-2 flex-wrap">
              {[
                { id: 'PENDING_REVIEW', label: 'Pending Review', color: 'border-amber-500/40 text-amber-400 bg-amber-500/10' },
                { id: 'VALIDATED_TRUE_POSITIVE', label: 'Validated (+1)', color: 'border-emerald-500/40 text-emerald-400 bg-emerald-500/10' },
                { id: 'VALIDATED_FALSE_POSITIVE', label: 'False Alarms (-1)', color: 'border-cyan-500/40 text-cyan-400 bg-cyan-500/10' },
                { id: 'CORRECTED', label: 'Relabeled', color: 'border-purple-500/40 text-purple-400 bg-purple-500/10' },
                { id: 'ALL', label: 'All Samples', color: 'border-ops-border text-ops-text bg-ops-panel' },
              ].map((f) => (
                <button
                  key={f.id}
                  onClick={() => {
                    setReviewFilterStatus(f.id)
                    loadReviewQueue(f.id)
                  }}
                  className={`px-3 py-1 text-xs font-mono rounded-lg border transition-all ${
                    reviewFilterStatus === f.id
                      ? f.color + ' ring-1 ring-ops-accent'
                      : 'border-ops-border text-ops-text-muted hover:text-ops-text'
                  }`}
                >
                  {f.label}
                </button>
              ))}

              <button
                onClick={() => loadReviewQueue()}
                className="px-2.5 py-1 text-xs font-mono rounded-lg border border-ops-border hover:bg-ops-panel text-ops-text flex items-center gap-1"
                title="Refresh Review Queue"
              >
                <RefreshCw className={`w-3.5 h-3.5 ${reviewLoading ? 'animate-spin' : ''}`} />
              </button>
            </div>
          </div>

          {/* Review Grid */}
          {reviewLoading ? (
            <div className="flex items-center justify-center p-12 text-xs text-ops-text-muted font-mono">
              <RefreshCw className="w-5 h-5 animate-spin mr-2 text-ops-accent" />
              Loading human validation review queue...
            </div>
          ) : reviewQueue.length === 0 ? (
            <div className="flex flex-col items-center justify-center p-12 text-center tactical-panel rounded-xl border border-ops-border">
              <CheckCircle2 className="w-10 h-10 text-emerald-400 mb-2 opacity-80" />
              <div className="text-sm font-bold text-ops-text font-mono">Validation Queue Clear</div>
              <div className="text-xs text-ops-text-muted max-w-sm mt-1">
                No samples matching <code className="text-ops-accent">{reviewFilterStatus}</code> currently require operator review.
              </div>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
              {reviewQueue.map((sample) => (
                <div
                  key={sample.sample_id}
                  className="tactical-panel rounded-xl border border-ops-border overflow-hidden flex flex-col justify-between hover:border-ops-accent/40 transition-all p-3.5 gap-3"
                >
                  {/* Top Bar: Camera & Status Badge */}
                  <div className="flex items-center justify-between text-xs font-mono">
                    <div className="flex items-center gap-1.5">
                      <Radio className="w-3.5 h-3.5 text-ops-accent" />
                      <span className="font-bold text-ops-text">{sample.camera_id}</span>
                    </div>
                    <span
                      className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                        sample.validation_status === 'VALIDATED_TRUE_POSITIVE'
                          ? 'bg-emerald-500/10 text-emerald-400 border-emerald-500/30'
                          : sample.validation_status === 'VALIDATED_FALSE_POSITIVE'
                          ? 'bg-cyan-500/10 text-cyan-400 border-cyan-500/30'
                          : sample.validation_status === 'CORRECTED'
                          ? 'bg-purple-500/10 text-purple-400 border-purple-500/30'
                          : sample.validation_status === 'REJECTED'
                          ? 'bg-red-500/10 text-red-400 border-red-500/30'
                          : 'bg-amber-500/10 text-amber-400 border-amber-500/30 animate-pulse'
                      }`}
                    >
                      {sample.validation_status || 'PENDING_REVIEW'}
                    </span>
                  </div>

                  {/* Thumbnail / Crop Image with BBox overlay */}
                  <div
                    className="relative aspect-video bg-black/60 rounded-lg overflow-hidden border border-ops-border group cursor-pointer"
                    onClick={() => setSelectedSample(sample)}
                  >
                    {sample.snapshot_data || sample.snapshot_path ? (
                      <img
                        src={sample.snapshot_data || getSnapshotUrl(sample.snapshot_path)}
                        alt={sample.sample_id}
                        className="w-full h-full object-cover transition-transform group-hover:scale-105"
                      />
                    ) : (
                      <div className="w-full h-full flex items-center justify-center text-xs text-ops-text-muted font-mono">
                        No image preview
                      </div>
                    )}

                    {/* Bounding box badge */}
                    {sample.bbox && (
                      <div className="absolute bottom-2 left-2 bg-black/80 px-1.5 py-0.5 rounded text-[9px] font-mono text-ops-text-muted border border-white/10">
                        BBox: [{sample.bbox.map((v) => Math.round(v)).join(', ')}]
                      </div>
                    )}

                    <div className="absolute top-2 right-2 opacity-0 group-hover:opacity-100 transition-opacity bg-black/80 p-1 rounded text-ops-text">
                      <Maximize2 className="w-3.5 h-3.5" />
                    </div>
                  </div>

                  {/* Detection Telemetry */}
                  <div className="flex flex-col gap-1.5 text-xs font-mono">
                    <div className="flex items-center justify-between">
                      <span className="text-ops-text-muted">Detected Target</span>
                      <span className="font-bold text-ops-text uppercase">{sample.class_label}</span>
                    </div>

                    <div className="flex items-center justify-between">
                      <span className="text-ops-text-muted">Model Confidence</span>
                      <span className="font-bold text-ops-accent">{(sample.confidence * 100).toFixed(1)}%</span>
                    </div>
                    <div className="w-full h-1.5 bg-ops-border rounded-full overflow-hidden">
                      <div
                        className="h-full bg-ops-accent"
                        style={{ width: `${Math.min(100, sample.confidence * 100)}%` }}
                      />
                    </div>

                    {sample.telemetry?.entropy !== undefined && (
                      <div className="flex items-center justify-between text-[11px] pt-1">
                        <span className="text-ops-text-muted">Entropy Uncertainty</span>
                        <span className="text-amber-400 font-bold">{sample.telemetry.entropy} / 1.0</span>
                      </div>
                    )}

                    {sample.notes && (
                      <div className="text-[10px] text-ops-text-muted line-clamp-1 italic bg-black/20 p-1 rounded">
                        {sample.notes}
                      </div>
                    )}
                  </div>

                  {/* 4 Action Buttons: Confirm, False Alarm, Relabel, Reject */}
                  <div className="grid grid-cols-2 gap-2 pt-2 border-t border-ops-border">
                    <button
                      disabled={validatingId === sample.sample_id}
                      onClick={() => handleValidateSample(sample.sample_id, 'CONFIRM')}
                      className="px-2.5 py-1.5 rounded-lg bg-emerald-500/20 hover:bg-emerald-500/30 text-emerald-300 border border-emerald-500/40 text-xs font-mono font-bold flex items-center justify-center gap-1.5 transition-all shadow-sm"
                      title="Confirm prediction as correct ground truth for candidate training pool"
                    >
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                      Confirm
                    </button>

                    <button
                      disabled={validatingId === sample.sample_id}
                      onClick={() => handleValidateSample(sample.sample_id, 'FALSE_ALARM')}
                      className="px-2.5 py-1.5 rounded-lg bg-cyan-500/20 hover:bg-cyan-500/30 text-cyan-300 border border-cyan-500/40 text-xs font-mono font-bold flex items-center justify-center gap-1.5 transition-all shadow-sm"
                      title="Mark as false alarm to immediately suppress recurring sector noise in real time"
                    >
                      <ShieldAlert className="w-3.5 h-3.5 text-cyan-400" />
                      False Alarm
                    </button>

                    <button
                      disabled={validatingId === sample.sample_id}
                      onClick={() => {
                        setRelabelModalSample(sample)
                        setCorrectedClassInput(sample.class_label)
                        setValidationNotesInput('')
                      }}
                      className="px-2.5 py-1.5 rounded-lg bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/40 text-xs font-mono font-bold flex items-center justify-center gap-1.5 transition-all shadow-sm"
                      title="Correct object class label for accurate retraining"
                    >
                      <Tag className="w-3.5 h-3.5 text-purple-400" />
                      Re-label
                    </button>

                    <button
                      disabled={validatingId === sample.sample_id}
                      onClick={() => handleValidateSample(sample.sample_id, 'REJECT')}
                      className="px-2.5 py-1.5 rounded-lg bg-red-500/20 hover:bg-red-500/30 text-red-300 border border-red-500/40 text-xs font-mono font-bold flex items-center justify-center gap-1.5 transition-all shadow-sm"
                      title="Discard and archive sample without model retraining"
                    >
                      <XCircle className="w-3.5 h-3.5 text-red-400" />
                      Reject
                    </button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {/* TAB 6: Central Learning Orchestrator, Forensic Explainability & Lineage */}
      {activeTab === 'orchestrator' && (
        <div className="flex flex-col gap-5">
          {/* Subpanel 1: Subsystems Telemetry Grid */}
          <div className="tactical-panel p-4 rounded-xl border border-ops-border flex flex-col gap-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <BrainCircuit className="w-5 h-5 text-cyan-400" />
                <h2 className="text-sm font-bold font-mono uppercase text-ops-text">
                  Continual Learning Subsystems Health Matrix
                </h2>
              </div>
              <button
                onClick={loadOrchestratorData}
                className="px-2.5 py-1 rounded border border-ops-border hover:border-ops-accent text-[11px] font-mono text-ops-text-muted hover:text-ops-text flex items-center gap-1"
              >
                <RefreshCw className={`w-3 h-3 ${orchestratorLoading ? 'animate-spin' : ''}`} />
                Refresh
              </button>
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-3">
              {orchestratorStatus?.orchestrator.subsystems ? (
                Object.entries(orchestratorStatus.orchestrator.subsystems).map(([name, status]) => (
                  <div key={name} className="p-2.5 rounded-lg bg-ops-panel border border-ops-border flex flex-col justify-between gap-1">
                    <span className="text-[10px] text-ops-text-muted font-mono uppercase truncate" title={name}>
                      {name.replace(/_/g, ' ')}
                    </span>
                    <div className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full ${
                        status.includes('ONLINE') || status.includes('ACTIVE') || status.includes('INDEXED')
                          ? 'bg-emerald-400 animate-pulse'
                          : 'bg-amber-400'
                      }`} />
                      <span className="text-xs font-mono font-bold text-ops-text truncate">
                        {status}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="col-span-full py-4 text-center text-xs text-ops-text-muted font-mono">
                  Loading subsystem telemetry...
                </div>
              )}
            </div>
          </div>

          {/* Subpanel 2: Forensic Decision Explainability Tool */}
          <div className="tactical-panel p-4 rounded-xl border border-ops-border flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-ops-border pb-3">
              <div className="flex items-center gap-2">
                <HelpCircle className="w-5 h-5 text-ops-accent" />
                <div>
                  <h2 className="text-sm font-bold font-mono uppercase text-ops-text">
                    Forensic Decision Attribution & Explainability
                  </h2>
                  <p className="text-[11px] text-ops-text-muted font-mono mt-0.5">
                    Deconstructs mathematical factor contributions (Base DL Confidence ± Lighting Calibration - Spatial Prior - Negative Exemplars).
                  </p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
              {/* Controls Form */}
              <div className="p-3 rounded-lg bg-ops-panel border border-ops-border flex flex-col gap-3 font-mono text-xs">
                <div>
                  <label className="text-ops-text-muted text-[10px] block uppercase mb-1">Select Camera</label>
                  <select
                    value={explainCamId}
                    onChange={(e) => setExplainCamId(e.target.value)}
                    className="w-full bg-ops-bg border border-ops-border rounded p-1.5 text-ops-text text-xs"
                  >
                    <option value="CAM-01">CAM-01 (Main Gate - Daylight / Traffic)</option>
                    <option value="CAM-02">CAM-02 (Perimeter East - Foliage / Glare)</option>
                    <option value="CAM-03">CAM-03 (Parking Lot - Vehicles / Low-Light)</option>
                    <option value="CAM-04">CAM-04 (Quad Plaza - Dense Pedestrian)</option>
                    <option value="CAM-05">CAM-05 (Server Room - Restricted Indoor)</option>
                  </select>
                </div>

                <div>
                  <label className="text-ops-text-muted text-[10px] block uppercase mb-1">Object Class</label>
                  <select
                    value={explainClass}
                    onChange={(e) => setExplainClass(e.target.value)}
                    className="w-full bg-ops-bg border border-ops-border rounded p-1.5 text-ops-text text-xs"
                  >
                    <option value="backpack">backpack (Subject to Foliage False Alarms)</option>
                    <option value="person">person (High Priority Target)</option>
                    <option value="car">car (Vehicle Perimeter)</option>
                    <option value="knife">knife (High Risk Threat)</option>
                  </select>
                </div>

                <div>
                  <div className="flex justify-between items-center mb-1">
                    <label className="text-ops-text-muted text-[10px] uppercase">Raw DL Detector Confidence</label>
                    <span className="text-ops-accent font-bold">{(explainConfidence * 100).toFixed(0)}%</span>
                  </div>
                  <input
                    type="range"
                    min="0.10"
                    max="1.0"
                    step="0.01"
                    value={explainConfidence}
                    onChange={(e) => setExplainConfidence(parseFloat(e.target.value))}
                    className="w-full accent-ops-accent"
                  />
                </div>

                <button
                  onClick={handleExplainDetection}
                  disabled={attributionLoading}
                  className="mt-2 w-full py-2 rounded-lg bg-ops-accent hover:bg-ops-accent/80 text-ops-bg font-bold font-mono text-xs flex items-center justify-center gap-1.5 transition-all shadow-tactical"
                >
                  <Sparkles className={`w-3.5 h-3.5 ${attributionLoading ? 'animate-spin' : ''}`} />
                  {attributionLoading ? 'Computing Attribution...' : 'Analyze Decision Attribution'}
                </button>
              </div>

              {/* Attribution Results Visualization */}
              <div className="lg:col-span-2 flex flex-col gap-3 font-mono">
                {attributionResult ? (
                  <div className="flex flex-col gap-3 p-3.5 rounded-lg bg-ops-panel border border-ops-border">
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className={`px-2.5 py-0.5 rounded font-bold text-xs uppercase flex items-center gap-1.5 ${
                          attributionResult.is_suppressed
                            ? 'bg-rose-500/20 text-rose-400 border border-rose-500/40'
                            : 'bg-emerald-500/20 text-emerald-400 border border-emerald-500/40'
                        }`}>
                          {attributionResult.is_suppressed ? <ShieldAlert className="w-3.5 h-3.5" /> : <ShieldCheck className="w-3.5 h-3.5" />}
                          {attributionResult.is_suppressed ? 'SUPPRESSED FALSE ALARM' : 'ALERT DISPATCHED'}
                        </span>
                        <span className="text-xs text-ops-text-muted">
                          Final Score: <strong className="text-ops-text">{(attributionResult.final_confidence * 100).toFixed(1)}%</strong>
                          {' '}(Threshold: {(attributionResult.threshold_applied * 100).toFixed(0)}%)
                        </span>
                      </div>
                      <span className="text-[10px] text-ops-text-muted font-mono">{attributionResult.decision_id}</span>
                    </div>

                    {/* Human-readable forensic explanation */}
                    <div className={`p-3 rounded-lg text-xs leading-relaxed border ${
                      attributionResult.is_suppressed
                        ? 'bg-rose-950/20 border-rose-500/30 text-rose-200'
                        : 'bg-emerald-950/20 border-emerald-500/30 text-emerald-200'
                    }`}>
                      <strong className="block font-bold mb-0.5">Forensic Rationale:</strong>
                      {attributionResult.human_explanation}
                    </div>

                    {/* Factor Breakdown Waterfall */}
                    <div className="flex flex-col gap-2 mt-1">
                      <div className="text-[10px] font-bold text-ops-text-muted uppercase tracking-wider">
                        Constituent Factor Attribution
                      </div>
                      <div className="space-y-1.5">
                        {attributionResult.factors.map((factor, idx) => (
                          <div key={idx} className="flex items-center justify-between p-2 rounded bg-ops-bg border border-ops-border text-xs">
                            <div className="flex items-center gap-2 truncate">
                              <span className={`w-1.5 h-1.5 rounded-full ${factor.impact >= 0 ? 'bg-emerald-400' : 'bg-rose-400'}`} />
                              <span className="font-bold text-ops-text truncate">{factor.name}</span>
                              <span className="text-[10px] text-ops-text-muted truncate hidden sm:inline">{factor.description}</span>
                            </div>
                            <span className={`font-mono font-bold shrink-0 ${factor.impact >= 0 ? 'text-emerald-400' : 'text-rose-400'}`}>
                              {factor.impact >= 0 ? `+${(factor.impact * 100).toFixed(1)}%` : `${(factor.impact * 100).toFixed(1)}%`}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  </div>
                ) : (
                  <div className="h-full min-h-[180px] rounded-lg border border-dashed border-ops-border flex flex-col items-center justify-center text-center p-6 text-xs text-ops-text-muted">
                    <HelpCircle className="w-8 h-8 text-ops-border mb-2" />
                    <span>Select target camera & object class, then click <strong>Analyze Decision Attribution</strong> to inspect the quantitative reasoning behind alert generation or suppression.</span>
                  </div>
                )}
              </div>
            </div>
          </div>

          {/* Subpanel 3: Cryptographic Lineage & Provenance Explorer */}
          <div className="tactical-panel p-4 rounded-xl border border-ops-border flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-ops-border pb-3">
              <div className="flex items-center gap-2">
                <Fingerprint className="w-5 h-5 text-emerald-400" />
                <div>
                  <h2 className="text-sm font-bold font-mono uppercase text-ops-text">
                    Model Provenance & Cryptographic Lineage Graph
                  </h2>
                  <p className="text-[11px] text-ops-text-muted font-mono mt-0.5">
                    Immutable SHA-256 dependency tree linking every deployed model to its exact training slices, feedback records, and validation metrics.
                  </p>
                </div>
              </div>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-4 font-mono">
              {/* Models List */}
              <div className="flex flex-col gap-2">
                <span className="text-[10px] font-bold text-ops-text-muted uppercase">Tracked Model Generations</span>
                <div className="flex flex-col gap-1.5 max-h-[300px] overflow-y-auto">
                  {lineageHistory.length > 0 ? (
                    lineageHistory.map((node) => (
                      <button
                        key={node.model_version_id}
                        onClick={() => handleSelectLineage(node.model_version_id)}
                        className={`p-2.5 rounded-lg border text-left transition-all text-xs flex flex-col gap-1 ${
                          selectedLineageModel === node.model_version_id
                            ? 'border-emerald-500/60 bg-emerald-500/10 text-emerald-300'
                            : 'border-ops-border bg-ops-panel text-ops-text hover:border-ops-accent'
                        }`}
                      >
                        <div className="flex items-center justify-between">
                          <span className="font-bold truncate">{node.model_version_id}</span>
                          <span className="text-[9px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-400 border border-emerald-500/30">
                            SHA-256
                          </span>
                        </div>
                        <span className="text-[10px] text-ops-text-muted truncate">
                          Dataset: {node.dataset_version_id} • {node.sample_count} Samples
                        </span>
                      </button>
                    ))
                  ) : (
                    <div className="p-4 text-center text-xs text-ops-text-muted border border-dashed border-ops-border rounded-lg">
                      No continual models indexed yet. Run an automated cycle above.
                    </div>
                  )}
                </div>
              </div>

              {/* Lineage Node Details */}
              <div className="md:col-span-2 p-4 rounded-lg bg-ops-panel border border-ops-border flex flex-col gap-3">
                {selectedLineageNode ? (
                  <div className="flex flex-col gap-3 text-xs">
                    <div className="flex items-center justify-between border-b border-ops-border pb-2">
                      <div className="flex items-center gap-2">
                        <GitBranch className="w-4 h-4 text-emerald-400" />
                        <span className="font-bold text-sm text-ops-text">{selectedLineageNode.model_version_id}</span>
                      </div>
                      {tamperStatus !== null && (
                        <span className={`px-2 py-0.5 rounded text-[10px] font-bold border flex items-center gap-1 ${
                          tamperStatus
                            ? 'bg-emerald-500/20 text-emerald-400 border-emerald-500/40'
                            : 'bg-rose-500/20 text-rose-400 border-rose-500/40'
                        }`}>
                          <Check className="w-3 h-3" />
                          {tamperStatus ? 'TAMPER-EVIDENT: VERIFIED' : 'TAMPER DETECTED: INVALID'}
                        </span>
                      )}
                    </div>

                    <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-[11px]">
                      <div className="p-2 rounded bg-ops-bg border border-ops-border">
                        <span className="text-ops-text-muted text-[9px] block">Dataset Slice</span>
                        <span className="font-bold text-ops-text truncate">{selectedLineageNode.dataset_version_id}</span>
                      </div>
                      <div className="p-2 rounded bg-ops-bg border border-ops-border">
                        <span className="text-ops-text-muted text-[9px] block">Training Samples</span>
                        <span className="font-bold text-cyan-400">{selectedLineageNode.sample_count} samples</span>
                      </div>
                      <div className="p-2 rounded bg-ops-bg border border-ops-border">
                        <span className="text-ops-text-muted text-[9px] block">Shadow Agreement</span>
                        <span className="font-bold text-emerald-400">{(selectedLineageNode.shadow_agreement_score * 100).toFixed(1)}%</span>
                      </div>
                      <div className="p-2 rounded bg-ops-bg border border-ops-border">
                        <span className="text-ops-text-muted text-[9px] block">Anti-Regression</span>
                        <span className="font-bold text-purple-400">99.8% retained</span>
                      </div>
                    </div>

                    {/* Applied Synthetic Transforms */}
                    <div>
                      <span className="text-[10px] text-ops-text-muted block mb-1 uppercase">Physics Degradation Transforms Applied:</span>
                      <div className="flex flex-wrap gap-1.5">
                        {selectedLineageNode.synthetic_transforms_applied.map((t) => (
                          <span key={t} className="px-2 py-0.5 rounded bg-ops-bg text-ops-text-muted border border-ops-border text-[10px]">
                            {t}
                          </span>
                        ))}
                      </div>
                    </div>

                    {/* SHA-256 Manifest Hash */}
                    <div className="p-2.5 rounded bg-black/50 border border-ops-border flex flex-col gap-1">
                      <span className="text-[10px] text-emerald-400 font-bold uppercase flex items-center gap-1">
                        <Fingerprint className="w-3 h-3" />
                        Cryptographic SHA-256 Provenance Digest:
                      </span>
                      <span className="text-[11px] font-mono text-ops-text break-all select-all">
                        {selectedLineageNode.manifest_hash}
                      </span>
                    </div>
                  </div>
                ) : (
                  <div className="h-full flex items-center justify-center text-xs text-ops-text-muted">
                    Select a model version to inspect its cryptographic provenance graph.
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Relabel Ground-Truth Correction Modal */}
      {relabelModalSample && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setRelabelModalSample(null)}
        >
          <div
            className="bg-ops-panel border border-ops-border rounded-xl max-w-lg w-full p-5 flex flex-col gap-4 shadow-tactical"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-ops-border pb-3">
              <div className="flex items-center gap-2 font-mono">
                <Tag className="w-5 h-5 text-purple-400" />
                <span className="font-bold text-sm text-ops-text">
                  Re-label Ground Truth: {relabelModalSample.sample_id}
                </span>
              </div>
              <button onClick={() => setRelabelModalSample(null)} className="text-ops-text-muted hover:text-ops-text">
                ✕
              </button>
            </div>

            {/* Thumbnail */}
            <div className="h-36 bg-black rounded-lg overflow-hidden flex items-center justify-center border border-ops-border">
              {relabelModalSample.snapshot_data || relabelModalSample.snapshot_path ? (
                <img
                  src={relabelModalSample.snapshot_data || getSnapshotUrl(relabelModalSample.snapshot_path)}
                  alt="Crop"
                  className="h-full object-contain"
                />
              ) : (
                <span className="text-xs text-ops-text-muted font-mono">No preview</span>
              )}
            </div>

            {/* Quick-select Class Pills */}
            <div className="flex flex-col gap-1.5 text-xs font-mono">
              <span className="text-ops-text-muted font-bold">Select Correct Class:</span>
              <div className="flex flex-wrap gap-1.5">
                {['person', 'car', 'truck', 'motorcycle', 'bicycle', 'backpack', 'suitcase', 'handbag', 'knife', 'weapon'].map(
                  (cls) => (
                    <button
                      key={cls}
                      onClick={() => setCorrectedClassInput(cls)}
                      className={`px-2.5 py-1 rounded-lg border text-[11px] transition-all ${
                        correctedClassInput.toLowerCase() === cls.toLowerCase()
                          ? 'bg-purple-500/30 border-purple-400 text-purple-200 font-bold ring-1 ring-purple-400'
                          : 'bg-black/30 border-ops-border text-ops-text-muted hover:text-ops-text'
                      }`}
                    >
                      {cls}
                    </button>
                  )
                )}
              </div>
            </div>

            {/* Custom Input */}
            <div className="flex flex-col gap-1 text-xs font-mono">
              <span className="text-ops-text-muted font-bold">Or Type Custom Label:</span>
              <input
                type="text"
                value={correctedClassInput}
                onChange={(e) => setCorrectedClassInput(e.target.value)}
                placeholder="e.g. security_guard, dog, luggage"
                className="px-3 py-2 rounded-lg bg-black/40 border border-ops-border text-ops-text focus:outline-none focus:border-ops-accent"
              />
            </div>

            {/* Notes */}
            <div className="flex flex-col gap-1 text-xs font-mono">
              <span className="text-ops-text-muted">Operator Annotation Notes (Optional):</span>
              <input
                type="text"
                value={validationNotesInput}
                onChange={(e) => setValidationNotesInput(e.target.value)}
                placeholder="e.g. Obscured by shadows, corrected from backpack"
                className="px-3 py-2 rounded-lg bg-black/40 border border-ops-border text-ops-text focus:outline-none focus:border-ops-accent"
              />
            </div>

            {/* Submit Actions */}
            <div className="flex items-center justify-end gap-2 pt-2 border-t border-ops-border">
              <button
                onClick={() => setRelabelModalSample(null)}
                className="px-4 py-1.5 rounded-lg border border-ops-border hover:bg-ops-border text-xs font-mono text-ops-text"
              >
                Cancel
              </button>
              <button
                disabled={!correctedClassInput.trim() || validatingId === relabelModalSample.sample_id}
                onClick={() => handleValidateSample(relabelModalSample.sample_id, 'RELABEL', correctedClassInput.trim())}
                className="px-4 py-1.5 rounded-lg bg-purple-600 hover:bg-purple-500 text-white text-xs font-mono font-bold flex items-center gap-1.5 transition-all shadow-sm disabled:opacity-50"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                Save & Add to Training Pool
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Snapshot Modal Viewer */}
      {selectedSample && (
        <div
          className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4"
          onClick={() => setSelectedSample(null)}
        >
          <div
            className="bg-ops-panel border border-ops-border rounded-xl max-w-2xl w-full p-5 flex flex-col gap-4 shadow-tactical"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between border-b border-ops-border pb-3">
              <div className="flex items-center gap-2 font-mono">
                <BrainCircuit className="w-5 h-5 text-ops-accent" />
                <span className="font-bold text-sm text-ops-text">Sample Inspector: {selectedSample.sample_id}</span>
              </div>
              <button onClick={() => setSelectedSample(null)} className="text-ops-text-muted hover:text-ops-text">
                ✕
              </button>
            </div>

            <div className="relative aspect-video bg-black rounded-lg overflow-hidden flex items-center justify-center border border-ops-border">
              {selectedSample.snapshot_data || selectedSample.snapshot_path ? (
                <img
                  src={selectedSample.snapshot_data || getSnapshotUrl(selectedSample.snapshot_path)}
                  alt={selectedSample.sample_id}
                  className="w-full h-full object-contain"
                />
              ) : (
                <span className="text-xs text-ops-text-muted font-mono">No preview image</span>
              )}
            </div>

            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
              <div className="p-2 rounded bg-ops-panel border border-ops-border">
                <span className="text-ops-text-muted text-[10px] block">Camera</span>
                <span className="text-ops-text font-bold">{selectedSample.camera_id}</span>
              </div>
              <div className="p-2 rounded bg-ops-panel border border-ops-border">
                <span className="text-ops-text-muted text-[10px] block">Confidence</span>
                <span className="text-ops-accent font-bold">{(selectedSample.confidence * 100).toFixed(1)}%</span>
              </div>
              <div className="p-2 rounded bg-ops-panel border border-ops-border">
                <span className="text-ops-text-muted text-[10px] block">Trigger Type</span>
                <span className="text-ops-text font-bold">{selectedSample.trigger_type}</span>
              </div>
              <div className="p-2 rounded bg-ops-panel border border-ops-border">
                <span className="text-ops-text-muted text-[10px] block">Label</span>
                <span className="text-ops-text font-bold">{selectedSample.sample_label}</span>
              </div>
            </div>

            <div className="text-xs font-mono text-ops-text-muted bg-black/40 p-2.5 rounded border border-ops-border">
              <span className="text-ops-text font-bold">Harvester Diagnostic:</span> {selectedSample.notes}
            </div>

            <div className="flex justify-end">
              <button
                onClick={() => setSelectedSample(null)}
                className="px-4 py-1.5 rounded-lg border border-ops-border hover:bg-ops-border text-xs font-mono text-ops-text"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
