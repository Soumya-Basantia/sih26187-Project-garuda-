import axios from 'axios'

const API_BASE = import.meta.env.VITE_API_BASE || 'http://localhost:8000'

export const api = axios.create({ baseURL: API_BASE, timeout: 3500 })

api.interceptors.request.use((config) => {
  const token = sessionStorage.getItem('garude_token') || localStorage.getItem('garude_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

api.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      sessionStorage.removeItem('garude_token')
      sessionStorage.removeItem('garude_role')
      sessionStorage.removeItem('garude_username')
      localStorage.removeItem('garude_token')
      localStorage.removeItem('garude_role')
      localStorage.removeItem('garude_username')
      if (window.location.pathname !== '/login') {
        window.location.href = '/login'
      }
    }
    return Promise.reject(error)
  }
)

export interface Camera {
  camera_id: string
  name: string
  location: string
  source_type: 'rtsp' | 'webcam' | 'file'
  source_uri: string
  status: string
  device_category?: 'webcam' | 'cctv' | 'drone' | 'thermal' | 'biometric' | 'barrier' | 'sensor'
  protocol?: string
  fps?: number
  last_heartbeat?: number
  ai_enabled?: boolean
  rotation?: number
}

export interface Zone {
  zone_id: string
  camera_id: string
  name: string
  zone_type: string
  polygon: number[][]
  threshold_seconds: number
  active_hours?: number[]
  authorized_identity_ids: string[]
  enabled: boolean
  min_rank_stars?: number
  allow_escort?: boolean
  authority_custom_level?: string
}

export interface Alert {
  alert_id: string
  event_type: string
  camera_id: string
  location?: string
  zone_id?: string
  track_id?: number
  person_name?: string
  person_role?: string
  display_name?: string
  rank_stars?: number
  rank_title?: string
  metadata?: Record<string, any>
  severity: 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED' | 'LOW' | 'MEDIUM' | 'HIGH'
  risk_score?: number
  confidence: number
  description: string
  behavioral_evidence?: Array<{ timestamp: number; event_type: string; description: string }>
  snapshot_path?: string
  snapshot_url?: string
  snapshot_data?: string
  timestamp: number
  status: 'NEW' | 'ACKNOWLEDGED' | 'RESOLVED' | 'FALSE_POSITIVE' | 'INVESTIGATING'
}

export function getSnapshotUrl(path?: string): string {
  if (!path) return ''
  if (path.startsWith('data:image/')) return path
  if (path.startsWith('http://') || path.startsWith('https://')) return path
  const clean = path.replace(/^\/?(api\/)?snapshots\//, '')
  return `${API_BASE}/snapshots/${clean}`
}

export interface Identity {
  identity_id: string
  demo_id: string
  name: string
  role: string
  department?: string
  plate_number?: string
  vehicle_type?: string
  has_face_enrolled: boolean
  rank_stars?: number
  rank_title?: string
}

export const authApi = {
  login: (username: string, password: string) =>
    api.post('/api/auth/login', { username, password }),
}

export const cameraApi = {
  list: () => api.get<Camera[]>('/api/cameras'),
  create: (data: Partial<Camera> & { target_fps?: number }) => api.post<Camera>('/api/cameras', data),
  remove: (id: string) => api.delete(`/api/cameras/${id}`),
  streamUrl: (id: string) => {
    const token = sessionStorage.getItem('garude_token') || localStorage.getItem('garude_token')
    return `${API_BASE}/api/cameras/${id}/stream${token ? `?token=${encodeURIComponent(token)}` : ''}`
  },
  snapshotUrl: (id: string, timestamp?: number) => {
    const token = sessionStorage.getItem('garude_token') || localStorage.getItem('garude_token')
    const params = new URLSearchParams()
    if (token) params.set('token', token)
    if (timestamp) params.set('t', String(timestamp))
    const qs = params.toString()
    return `${API_BASE}/api/cameras/${id}/snapshot${qs ? `?${qs}` : ''}`
  },
  toggleAi: (id: string) => api.post<{ camera_id: string; ai_enabled: boolean; message: string }>(`/api/cameras/${id}/toggle-ai`),
  rotate: (id: string, rotation?: number) => api.post<{ camera_id: string; rotation: number; message: string }>(`/api/cameras/${id}/rotate`, rotation !== undefined ? { rotation } : {}),
}

export const zoneApi = {
  list: (cameraId?: string) => api.get<Zone[]>('/api/zones', { params: cameraId ? { camera_id: cameraId } : {} }),
  create: (data: Partial<Zone>) => api.post<Zone>('/api/zones', data),
  update: (id: string, data: Partial<Zone>) => api.patch<Zone>(`/api/zones/${id}`, data),
  remove: (id: string) => api.delete(`/api/zones/${id}`),
}

export const alertApi = {
  list: (status?: string) => api.get<Alert[]>('/api/alerts', { params: status ? { status } : {} }),
  update: (id: string, status: string) => api.patch<Alert>(`/api/alerts/${id}`, { status }),
  clear: () => api.post('/api/alerts/clear'),
  exportPdf: (id: string) => api.get(`/api/alerts/${id}/pdf`, { responseType: 'blob' }),
}

export const identityApi = {
  list: () => api.get<Identity[]>('/api/identities'),
  enroll: (formData: FormData) => api.post<Identity>('/api/identities', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }),
  remove: (id: string) => api.delete(`/api/identities/${id}`),
}

export interface AuthorizationRule {
  rule_id: string
  name: string
  tag_colors: string[]
  allowed_zones: string[]
  forbidden_zones: string[]
  time_restrictions?: {
    weekdays?: { start: string; end: string }
    weekends?: { start: string; end: string }
    all_days?: { start: string; end: string }
  }
  allowed_objects: string[]
  forbidden_objects: string[]
  priority: number
  override_all_rules: boolean
  escort_privileges: boolean
  requires_escort: boolean
  created_by: string
  created_at: string
  active: boolean
}

export interface AuthTestResult {
  authorized: boolean
  reason: string
  matched_rule?: string
  violated_rule?: string
  severity: string
  actions_required: string[]
  can_be_escorted: boolean
  escort_required: boolean
}

export const authorizationApi = {
  listRules: () => api.get<AuthorizationRule[]>('/api/authorization/rules'),
  createRule: (data: Partial<AuthorizationRule>) => api.post<AuthorizationRule>('/api/authorization/rules', data),
  updateRule: (id: string, data: Partial<AuthorizationRule>) => api.put<AuthorizationRule>(`/api/authorization/rules/${id}`, data),
  deleteRule: (id: string) => api.delete(`/api/authorization/rules/${id}`),
  toggleRule: (id: string) => api.post(`/api/authorization/rules/${id}/toggle`),
  getTemplates: () => api.get('/api/authorization/templates'),
  testRule: (data: { tag_color: string; zone: string; current_time?: string; objects_carried?: string[] }) =>
    api.post<AuthTestResult>('/api/authorization/test', data),
}

export function connectEventSocket(onMessage: (msg: any) => void): WebSocket {
  const wsBase = API_BASE.replace(/^http/, 'ws')
  const token = sessionStorage.getItem('garude_token') || localStorage.getItem('garude_token')
  const wsUrl = token ? `${wsBase}/ws/events?token=${encodeURIComponent(token)}` : `${wsBase}/ws/events`
  const ws = new WebSocket(wsUrl)
  ws.onmessage = (event) => {
    try { onMessage(JSON.parse(event.data)) } catch { /* ignore malformed */ }
  }
  return ws
}

export interface Vehicle {
  vehicle_id: string
  plate_number: string
  vehicle_type?: string
  owner_name?: string
  owner_ref?: string
  watchlist_flag: boolean
  notes?: string
}

export interface SystemStats {
  cameras_total: number
  cameras_online: number
  zones_total: number
  identities_total: number
  vehicles_total: number
  alerts_total: number
  alerts_new: number
  alerts_24h: number
  events_total: number
  events_24h: number
}

export interface SystemHealth {
  status: string
  cameras: Record<string, {
    camera_id: string
    name: string
    source_type: string
    location: string
    status: string
    fps: number
    latency_ms: number
    is_alive: boolean
  }>
  active_alerts: number
  disk?: {
    total_gb: number
    used_gb: number
    free_gb: number
    percent_used: number
  }
  timestamp?: number
}

export interface AnprDetection {
  detection_id: string
  camera_id: string
  camera_name?: string
  plate_number: string
  vehicle_type?: string
  owner_name?: string
  status: string
  driver_2fa?: string
  is_fuzzy?: boolean
  confidence: number
  timestamp: number
  snapshot_path?: string
  snapshot_url?: string
  snapshot_data?: string
}

export interface ScanResult {
  plate_text: string | null
  status: string
  confidence: number
  is_fuzzy: boolean
  match?: {
    owner_name?: string
    watchlist_flag?: boolean
    notes?: string
    vehicle_type?: string
  }
}

export const vehicleApi = {
  list: (watchlistOnly?: boolean) =>
    api.get<Vehicle[]>('/api/vehicles', { params: watchlistOnly ? { watchlist_only: true } : {} }),
  create: (data: Partial<Vehicle>) => api.post<Vehicle>('/api/vehicles', data),
  remove: (id: string) => api.delete(`/api/vehicles/${id}`),
  detections: (limit?: number) => api.get<AnprDetection[]>('/api/vehicles/anpr-detections', { params: { limit: limit || 50 } }),
  stats: () => api.get('/api/vehicles/stats'),
  scan: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<ScanResult>('/api/vehicles/scan', form)
  },
}

export interface EventItem {
  event_id: string
  event_type: string
  track_id: number
  camera_id: string
  zone_id?: string
  timestamp: number
  severity: 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED'
  risk_score?: number
  confidence: number
  description: string
  person_name?: string
  person_role?: string
  display_name?: string
  rank_stars?: number
  rank_title?: string
  snapshot_path?: string
  snapshot_url?: string
  snapshot_data?: string
  metadata?: Record<string, any>
}

export const systemApi = {
  health: () => api.get<SystemHealth>('/api/system/health'),
  stats: () => api.get<SystemStats>('/api/system/stats'),
  reconnectCamera: (cameraId: string) => api.post(`/api/system/cameras/${cameraId}/reconnect`),
  cleanupSnapshots: (days: number = 7) => api.post('/api/system/cleanup-snapshots', { days }),
  clearAllSnapshots: () => api.post<{ status: string; removed_files: number; cleared_records: number; message: string }>('/api/system/clear-all-snapshots').then((r) => r.data),
}

export const eventApi = {
  list: (params?: { camera_id?: string; event_type?: string; severity?: string; search?: string; from_ts?: number; to_ts?: number; limit?: number }) =>
    api.get<EventItem[]>('/api/events', { params }),
  exportPdf: (id: string) => api.get(`/api/events/${id}/pdf`, { responseType: 'blob' }),
}

export interface AttendanceEntry {
  entry_id: string
  camera_id: string
  camera_name: string
  identity_id?: string
  identity_name?: string
  identity_role?: string
  rank_stars?: number
  rank_title?: string
  verification_confidence: number
  snapshot_path?: string
  snapshot_url?: string
  snapshot_data?: string
  timestamp: number
  entry_type: string
  notes?: string
}

export interface AttendanceStats {
  total_entries: number
  recognized_people: number
  unknown_people: number
  recognition_rate: number
  unique_identities: number
  role_distribution: Record<string, number>
  time_distribution: { morning: number; afternoon: number; evening: number; night: number }
  date_filter: string
  camera_filter: string
}

export const attendanceApi = {
  list: (params?: { camera_id?: string; identity_id?: string; entry_type?: string; from_date?: string; to_date?: string; limit?: number }) =>
    api.get<AttendanceEntry[]>('/api/attendance/entries', { params }),
  stats: (params?: { camera_id?: string; date?: string }) =>
    api.get<AttendanceStats>('/api/attendance/stats', { params }),
}

export interface NegativeExemplarItem {
  exemplar_id: string
  camera_id: string
  class_label: string
  spatial_coords: [number, number, number, number]
  timestamp: number
  alert_id?: string
  notes: string
  match_count: number
  confidence_penalty: number
}

export interface LearningStats {
  current_version: string
  current_model_path: string
  is_training: boolean
  training_progress: number
  total_harvested_samples: number
  false_alarms_count: number
  confirmed_threats_count: number
  borderline_uncertain_count: number
  accuracy_gain_pct: number
  false_alarm_reduction_pct: number
  camera_profiles: CameraSensitivityProfile[]
  checkpoints: ModelCheckpoint[]
  adaptive_filter?: {
    total_negative_exemplars: number
    total_suppressed_detections: number
    camera_exemplar_counts: Record<string, number>
  }
}

export interface CameraSensitivityProfile {
  camera_id: string
  base_confidence: number
  adapted_confidence: number
  persistence_frames: number
  false_alarm_rate: number
  ambient_noise: number
  status: 'OPTIMAL' | 'NOISE_SUPPRESSED' | 'BALANCED' | 'ENVIRONMENT_ADAPTED'
  last_calibrated: number
}

export interface ModelCheckpoint {
  version: string
  checkpoint_id: string
  created_at: number
  samples_used: number
  false_alarm_reduction: number
  accuracy_gain: number
  model_path: string
  is_active: boolean
  notes: string
}

export interface HarvestedSample {
  sample_id: string
  camera_id: string
  timestamp: number
  trigger_type: string
  sample_label: string
  confidence: number
  class_label: string
  bbox: [number, number, number, number]
  snapshot_data?: string
  snapshot_path?: string
  frame_ref?: string
  notes?: string
  reinforcement_score: number
  validation_status?: string
  selection_reason?: string
  telemetry?: Record<string, any>
  metadata?: Record<string, any>
}

export interface ValidateSamplePayload {
  action: 'CONFIRM' | 'REJECT' | 'RELABEL' | 'FALSE_ALARM'
  corrected_label?: string
  notes?: string
}

export interface DecisionFactor {
  name: string
  impact: number
  description: string
  metadata?: Record<string, any>
}

export interface DecisionAttribution {
  decision_id: string
  camera_id: string
  class_label: string
  raw_confidence: number
  final_confidence: number
  is_suppressed: boolean
  threshold_applied: number
  factors: DecisionFactor[]
  human_explanation: string
  timestamp: number
}

export interface LineageNode {
  model_version_id: string
  dataset_version_id: string
  parent_model_id: string | null
  sample_count: number
  sample_ids: string[]
  feedback_ids: string[]
  synthetic_transforms_applied: string[]
  validation_metrics: Record<string, number>
  shadow_agreement_score: number
  created_at: number
  manifest_hash: string
}

export interface OrchestratorStatusResponse {
  status: string
  orchestrator: {
    lifecycle_state: string
    cycle_count: number
    last_cycle_timestamp: number
    subsystems: Record<string, string>
    last_cycle_report: Record<string, any>
  }
  triggers: {
    sample_volume_trigger: boolean
    time_elapsed_trigger: boolean
    should_run_cycle: boolean
    validated_sample_count: number
    threshold_required: number
  }
}

export const learningApi = {
  getStats: () => api.get<LearningStats>('/api/learning/stats'),
  getSamples: (params?: { limit?: number; trigger_type?: string }) =>
    api.get<HarvestedSample[]>('/api/learning/samples', { params }),
  getReviewQueue: (params?: { status?: string; camera_id?: string; limit?: number }) =>
    api.get<HarvestedSample[]>('/api/learning/review-queue', { params }),
  validateSample: (sampleId: string, payload: ValidateSamplePayload) =>
    api.post<{ status: string; message: string; sample_id: string; action: string; validation_status: string }>(
      `/api/learning/samples/${sampleId}/validate`,
      payload
    ),
  getExemplars: (cameraId?: string) =>
    api.get<{ exemplars: NegativeExemplarItem[]; total: number; summary: any }>('/api/learning/exemplars', { params: { camera_id: cameraId } }),
  getHeatmap: (cameraId: string) =>
    api.get<{ camera_id: string; grid_size: number; matrix: number[][] }>(`/api/learning/heatmap/${cameraId}`),
  submitFeedback: (payload: { alert_id: string; is_false_alarm: boolean; notes?: string }) =>
    api.post<{ status: string; message: string; sample_id: string; adapted_camera_threshold: number }>('/api/learning/feedback', payload),
  triggerTraining: (payload?: { epochs?: number; sample_limit?: number }) =>
    api.post<{ status: string; message: string }>('/api/learning/trigger-training', payload || {}),
  autoTune: () =>
    api.post<{ status: string; message: string; profiles: Record<string, CameraSensitivityProfile> }>('/api/learning/auto-tune'),
  rollback: () =>
    api.post<{ status: string; message: string; active_version: string }>('/api/learning/rollback'),
  deleteSample: (sampleId: string) =>
    api.delete<{ status: string; sample_id: string }>(`/api/learning/samples/${sampleId}`),
  clearAllSamples: () =>
    api.delete<{ status: string; deleted_count: number }>('/api/learning/samples'),
  getOrchestratorStatus: () =>
    api.get<OrchestratorStatusResponse>('/api/learning/orchestrator/status'),
  triggerOrchestratorCycle: (force: boolean = false) =>
    api.post<{ status: string; cycle_report: Record<string, any> }>('/api/learning/orchestrator/cycle', { force }),
  explainDetection: (payload: {
    camera_id: string
    class_label: string
    raw_confidence: number
    bbox?: number[]
    visual_descriptor?: number[]
  }) =>
    api.post<{ status: string; attribution: DecisionAttribution }>('/api/learning/explain', payload),
  getModelLineage: (modelVersionId: string) =>
    api.get<{ status: string; model_version_id: string; tamper_evident_valid: boolean; lineage: LineageNode }>(
      `/api/learning/lineage/model/${modelVersionId}`
    ),
  getLineageHistory: () =>
    api.get<{ status: string; count: number; models: LineageNode[] }>('/api/learning/lineage/history'),
}

// ---- Blockchain & Cybersecurity APIs -----------------------------------

export interface BlockchainTransaction {
  tx_id: string
  alert_id: string
  camera_id: string
  camera_name?: string
  timestamp: number
  timestamp_iso: string
  event_type: string
  severity: string
  snapshot_sha256: string
  metadata_sha256: string
  operator_action: string
  cryptographic_signature: string
  tampered_flag?: boolean
}

export interface BlockchainBlock {
  index: number
  timestamp: number
  timestamp_iso: string
  prev_hash: string
  merkle_root: string
  transactions: BlockchainTransaction[]
  nonce: number
  validator_node: string
  hash: string
}

export interface BlockchainStats {
  chain_height: number
  total_evidence_transactions: number
  pending_pool: number
  validator_node: string
  consensus_algorithm: string
  tamper_proof_status: string
  is_tampered_for_demo: boolean
  latest_block_hash: string
  genesis_hash: string
}

export interface Section65BCertificate {
  certificate_id: string
  statutory_act: string
  jurisdiction: string
  issuing_authority: string
  validator_node: string
  evidence_details: {
    alert_id: string
    transaction_id: string
    event_type: string
    severity: string
    camera_id: string
    timestamp_utc: string
    snapshot_sha256_digest: string
    metadata_sha256_digest: string
  }
  blockchain_anchor: {
    block_index: number
    block_hash: string
    merkle_root: string
    leaf_index: number
    chain_validity: boolean
  }
  legal_attestation_text: string
  verification_status: string
  digital_seal: string
}

export interface CameraCyberAudit {
  camera_id: string
  camera_name: string
  location: string
  source_type: string
  cyber_score: number
  security_grade: 'MILITARY_GRADE' | 'HARDENED' | 'VULNERABLE'
  is_quarantined: boolean
  findings: {
    severity: 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
    title: string
    description: string
    remediation: string
  }[]
  findings_count: number
  last_audited: number
}

export interface MitreTechnique {
  technique_id: string
  name: string
  category: string
  status: string
  mitigation: string
  active_threats_count: number
}

export interface CyberPosture {
  fleet_cyber_score: number
  overall_status: 'SECURE_NOMINAL' | 'HIGH_ALERT'
  total_nodes_audited: number
  quarantined_nodes_count: number
  active_threats_count: number
  camera_audits: CameraCyberAudit[]
  mitre_matrix: MitreTechnique[]
  anti_replay_engine: {
    status: string
    entropy_sampling_rate_hz: number
    noise_variance_algorithm: string
    loop_detection_window_seconds: number
  }
  last_scan_timestamp: number
}

export interface CyberThreat {
  incident_id: string
  timestamp: number
  timestamp_iso: string
  camera_id: string
  camera_name: string
  attack_type: string
  mitre_id: string
  mitre_name: string
  severity: string
  status: 'ACTIVE' | 'NEUTRALIZED'
  defense_action: string
  technical_details?: string
  confidence: number
}

export const blockchainApi = {
  getStats: () => api.get<BlockchainStats>('/api/blockchain/stats'),
  getLedger: (limit?: number) => api.get<{ total_blocks: number; blocks: BlockchainBlock[] }>('/api/blockchain/ledger', { params: { limit } }),
  verifyChain: () => api.get<{ valid: boolean; total_blocks_verified?: number; tampered_block_index?: number; error_type?: string; details: string }>('/api/blockchain/verify'),
  simulateTamper: (blockIndex?: number) => api.post<{ status: string; tampered_block_index: number; message: string }>('/api/blockchain/simulate-tamper', { block_index: blockIndex }),
  restoreLedger: () => api.post<{ status: string; message: string }>('/api/blockchain/restore'),
  getCertificate: (alertId: string) => api.get<Section65BCertificate>(`/api/blockchain/certificate/${alertId}`),
  verifyEvidence: (alertId: string, imageHash?: string) => api.post<{ alert_id: string; is_valid: boolean; block_index: number; block_hash: string; recorded_snapshot_sha256: string; tamper_detected: boolean; status: string }>('/api/blockchain/verify-evidence', { alert_id: alertId, image_hash: imageHash }),
}

export interface DigitalAntibody {
  antibody_id: string
  virus_name: string
  category: string
  threat_vector: string
  neutralization_speed_ms: number
  effectiveness_pct: number
  status: string
  antigen_pattern: string
  defense_action: string
  last_evolution: string
  encounters_blocked: number
}

export interface ImmuneSystemStats {
  status: string
  fleet_resistance_pct: number
  average_neutralization_ms: number
  total_antibodies_count: number
  total_attacks_neutralized: number
  air_gap_integrity: string
  antibodies: DigitalAntibody[]
  recent_synthesis_log: {
    timestamp: number
    timestamp_str: string
    antibody_id: string
    virus_name: string
    event: string
    latency_ms: number
    details: string
  }[]
}

export const cybersecurityApi = {
  getPosture: () => api.get<CyberPosture>('/api/cybersecurity/posture'),
  getThreats: () => api.get<{ active_threats: CyberThreat[]; all_threats: CyberThreat[]; quarantined_cameras: string[] }>('/api/cybersecurity/threats'),
  simulateAttack: (payload: { attack_type: string; camera_id: string }) => api.post<CyberThreat>('/api/cybersecurity/simulate-attack', payload),
  resolveThreat: (incidentId: string) => api.post<{ status: string; message: string }>(`/api/cybersecurity/threats/${incidentId}/resolve`),
  resetState: () => api.post<{ status: string; message: string }>('/api/cybersecurity/reset'),
  getAntibodies: () => api.get<ImmuneSystemStats>('/api/cybersecurity/antibodies'),
  trainAntibody: (antibodyId: string) => api.post<{ status: string; evolved_antibody: DigitalAntibody; log: any; summary: string }>('/api/cybersecurity/antibodies/train', { antibody_id: antibodyId }),
}

// ---- Incidents & Explainability (Pillar 2) -------------------------------

export interface ExplainabilitySignal {
  signal_name: string
  confidence: number
  description: string
  evidence_timestamp: number
  supporting_camera?: string
}

export interface IncidentTimelineItem {
  timestamp: number
  event_type: string
  description: string
}

export interface Incident {
  incident_id: string
  incident_type: string
  title: string
  status: 'DETECTED' | 'CORRELATED' | 'PRIORITIZED' | 'ACKNOWLEDGED' | 'INVESTIGATED' | 'RESOLVED' | 'FALSE_ALARM'
  priority_score: number
  severity: 'GREEN' | 'YELLOW' | 'ORANGE' | 'RED'
  start_time: number
  last_update_time: number
  cameras_involved: string[]
  primary_track_ids: number[]
  timeline: IncidentTimelineItem[]
  explainability_signals: ExplainabilitySignal[]
  evidence_snapshots: { snapshot_data?: string; sha256_hash?: string; timestamp?: number; camera_id?: string }[]
  operator_notes?: string
  acknowledged_by?: string
  resolved_at?: number
  metadata?: Record<string, any>
}

export const incidentApi = {
  list: (status?: string) => api.get<Incident[]>('/api/incidents', { params: { status } }),
  get: (incidentId: string) => api.get<Incident>(`/api/incidents/${incidentId}`),
  update: (incidentId: string, payload: { status?: string; operator_notes?: string }) =>
    api.patch<Incident>(`/api/incidents/${incidentId}`, payload),
}

// ---- Edge & Bandwidth Telemetry (Pillar 4) -------------------------------

export interface EdgeTelemetry {
  timestamp: number
  uptime_seconds: number
  cpu_percent: number
  ram_used_mb: number
  ram_budget_mb: number
  ram_within_budget: boolean
  active_cameras: number
  pipeline_fps: number
  inference_latency_ms: number
  frame_drop_count: number
  network: {
    network_status: 'ONLINE' | 'OFFLINE' | 'DEGRADED'
    spooled_queue_depth: number
    max_buffer_capacity: number
    total_transmitted: number
    total_spooled_historical: number
    total_synced_on_reconnect: number
    is_simulation_active: boolean
  }
}

export const edgeApi = {
  getTelemetry: () => api.get<EdgeTelemetry>('/api/edge/telemetry'),
  simulateDisconnect: (durationSec: number = 10) =>
    api.post<{ status: string; duration_sec: number; message: string }>('/api/edge/simulate-disconnect', null, { params: { duration_sec: durationSec } }),
  reconnect: () => api.post<{ status: string; synced_events_count: number; message: string }>('/api/edge/reconnect'),
}


