import React, { useEffect, useState, useMemo } from 'react'
import { authorizationApi, zoneApi, AuthorizationRule, AuthTestResult, Zone } from '../services/api'
import { Award, ShieldCheck, Play, Star, MapPin, Check, X, ShieldAlert, Users } from 'lucide-react'

export interface RankTier {
  stars: number
  title: string
  code: string
  badge: string
  color: string
  border: string
  bg: string
  description: string
  typicalZones: string[]
}

export const MILITARY_RANK_TIERS: RankTier[] = [
  {
    stars: 5,
    title: 'Supreme Commander / General',
    code: 'star_5',
    badge: '⭐⭐⭐⭐⭐',
    color: 'text-amber-300',
    border: 'border-amber-500/40',
    bg: 'bg-amber-500/15',
    description: 'Supreme Command Authority. Unrestricted master access across all defense sectors, War Room Alpha, Command Bunker, and Vault.',
    typicalZones: ['War Room Alpha', 'Command Bunker', 'Vault', 'Tactical HQ', 'All Zones'],
  },
  {
    stars: 4,
    title: 'Division Commander / Brigadier',
    code: 'star_4',
    badge: '⭐⭐⭐⭐',
    color: 'text-purple-300',
    border: 'border-purple-500/40',
    bg: 'bg-purple-500/15',
    description: 'Division Level Authority. Directs tactical ops, perimeter defenses, communications center, and master armory logistics.',
    typicalZones: ['Tactical Operations', 'Main Armory', 'Perimeter HQ', 'Communications Bay'],
  },
  {
    stars: 3,
    title: 'Field Officer / Colonel / Major',
    code: 'star_3',
    badge: '⭐⭐⭐',
    color: 'text-blue-300',
    border: 'border-blue-500/40',
    bg: 'bg-blue-500/15',
    description: 'Field Command Authority. Authorized inside armory facilities, sector checkpoints, and duty operation rooms.',
    typicalZones: ['Armory Access', 'Sector Checkpoints', 'Duty Room', 'General Quarters'],
  },
  {
    stars: 2,
    title: 'Duty Officer / Captain / Lieutenant',
    code: 'star_2',
    badge: '⭐⭐',
    color: 'text-emerald-300',
    border: 'border-emerald-500/40',
    bg: 'bg-emerald-500/15',
    description: 'Tactical Duty Authority. Stationed at primary entry checkpoints, patrol stations, and supply depots.',
    typicalZones: ['Primary Checkpoints', 'Patrol Station', 'Supply Depot', 'General Facility'],
  },
  {
    stars: 1,
    title: 'Patrol Guard / Sentry',
    code: 'star_1',
    badge: '⭐',
    color: 'text-cyan-300',
    border: 'border-cyan-500/40',
    bg: 'bg-cyan-500/15',
    description: 'Perimeter Sentry Authority. Assigned to outer perimeter lines, watchtowers, and vehicle lanes. Restricted from armory without escort.',
    typicalZones: ['Outer Perimeter', 'Watchtowers', 'Vehicle Gates', 'Entry Post'],
  },
  {
    stars: 0,
    title: 'Civilian / Contractor / Visitor',
    code: 'civilian',
    badge: '🌐 Civilian',
    color: 'text-slate-300',
    border: 'border-slate-600',
    bg: 'bg-slate-800/40',
    description: 'Unenrolled or visiting personnel. Strictly confined to reception and entry checkpoints; escort mandatory in all secure zones.',
    typicalZones: ['Entry Gate Reception', 'Visitor Holding'],
  },
]

const RANK_TAG_MAP: Record<string, { label: string; badge: string; stars: number }> = {
  star_5: { label: '⭐⭐⭐⭐⭐ Supreme Commander', badge: 'bg-amber-500/20 text-amber-300 border-amber-500/40', stars: 5 },
  star_4: { label: '⭐⭐⭐⭐ Division Commander', badge: 'bg-purple-500/20 text-purple-300 border-purple-500/40', stars: 4 },
  star_3: { label: '⭐⭐⭐ Field Officer', badge: 'bg-blue-500/20 text-blue-300 border-blue-500/40', stars: 3 },
  star_2: { label: '⭐⭐ Duty Officer', badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40', stars: 2 },
  star_1: { label: '⭐ Patrol Guard', badge: 'bg-cyan-500/20 text-cyan-300 border-cyan-500/40', stars: 1 },
  yellow: { label: 'Contractor / Visitor', badge: 'bg-yellow-500/20 text-yellow-300 border-yellow-500/40', stars: 0 },
  red: { label: 'Red Tag (Restricted)', badge: 'bg-red-500/20 text-red-300 border-red-500/40', stars: 1 },
  blue: { label: 'Blue Tag (Officer)', badge: 'bg-blue-500/20 text-blue-300 border-blue-500/40', stars: 3 },
  green: { label: 'Green Tag (Patrol)', badge: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40', stars: 2 },
}

const DEFAULT_DEFENSE_ZONES = [
  { name: 'War Room Alpha', type: 'high_security', min_rank_stars: 5, allow_escort: false },
  { name: 'Command Bunker Vault', type: 'high_security', min_rank_stars: 5, allow_escort: false },
  { name: 'Tactical Operations Center', type: 'restricted', min_rank_stars: 4, allow_escort: true },
  { name: 'Communications Bay', type: 'restricted', min_rank_stars: 4, allow_escort: true },
  { name: 'Central Armory Depot', type: 'sensitive', min_rank_stars: 3, allow_escort: true },
  { name: 'Perimeter Checkpoint Alpha', type: 'monitored', min_rank_stars: 2, allow_escort: true },
  { name: 'Outer Watchtower Grid', type: 'general', min_rank_stars: 1, allow_escort: true },
  { name: 'Main Vehicle & Personnel Gate', type: 'entry', min_rank_stars: 0, allow_escort: true },
]

const emptyRule = (): Partial<AuthorizationRule> => ({
  name: '',
  tag_colors: [],
  allowed_zones: [],
  forbidden_zones: [],
  allowed_objects: [],
  forbidden_objects: [],
  priority: 2,
  override_all_rules: false,
  escort_privileges: false,
  requires_escort: false,
  time_restrictions: undefined,
})

type ActiveTab = 'matrix' | 'rules' | 'simulator'

export default function AuthorizationManagement() {
  const [tab, setTab] = useState<ActiveTab>('matrix')
  const [rules, setRules] = useState<AuthorizationRule[]>([])
  const [activeZones, setActiveZones] = useState<Zone[]>([])
  const [editing, setEditing] = useState<Partial<AuthorizationRule> | null>(null)
  const [editingId, setEditingId] = useState<string | null>(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState<string | null>(null)

  // Sentry Simulator state
  const [testStars, setTestStars] = useState<number>(3)
  const [testZone, setTestZone] = useState<string>('')
  const [testHasEscort, setTestHasEscort] = useState<boolean>(false)
  const [testObjects, setTestObjects] = useState<string>('')
  const [testResult, setTestResult] = useState<{
    authorized: boolean
    badge: string
    reason: string
    action: string
    requiredStars: number
  } | null>(null)
  const [testing, setTesting] = useState(false)

  // Inputs for editing rules
  const [zoneInput, setZoneInput] = useState('')
  const [forbidZoneInput, setForbidZoneInput] = useState('')
  const [allowObjInput, setAllowObjInput] = useState('')
  const [forbidObjInput, setForbidObjInput] = useState('')

  useEffect(() => {
    loadRules()
    zoneApi.list().then((r) => {
      setActiveZones(r.data)
      if (r.data.length > 0 && !testZone) {
        setTestZone(r.data[0].name)
      }
    }).catch(() => {})
  }, [])

  async function loadRules() {
    try {
      const res = await authorizationApi.listRules()
      setRules(res.data || [])
    } catch {
      // fallback
    }
  }

  // Combined unique zone list
  const combinedZones = useMemo(() => {
    const list: Array<{ name: string; type: string; min_rank_stars: number; allow_escort: boolean }> = []
    const seen = new Set<string>()

    activeZones.forEach((z) => {
      seen.add(z.name.toLowerCase())
      list.push({
        name: z.name,
        type: z.zone_type,
        min_rank_stars: z.min_rank_stars ?? (z.zone_type === 'high_security' ? 5 : z.zone_type === 'restricted' ? 3 : 0),
        allow_escort: z.allow_escort ?? true,
      })
    })

    DEFAULT_DEFENSE_ZONES.forEach((dz) => {
      if (!seen.has(dz.name.toLowerCase())) {
        list.push(dz)
      }
    })

    return list
  }, [activeZones])

  function startNew() {
    setEditing(emptyRule())
    setEditingId(null)
    setZoneInput('')
    setForbidZoneInput('')
    setAllowObjInput('')
    setForbidObjInput('')
    setError(null)
  }

  function startEdit(rule: AuthorizationRule) {
    setEditing({ ...rule })
    setEditingId(rule.rule_id)
    setZoneInput('')
    setForbidZoneInput('')
    setAllowObjInput('')
    setForbidObjInput('')
    setError(null)
  }

  function cancelEdit() {
    setEditing(null)
    setEditingId(null)
    setError(null)
  }

  async function loadTemplate(key: string) {
    try {
      const res = await authorizationApi.getTemplates()
      const tpl = res.data[key]
      if (tpl) {
        setEditing({ ...emptyRule(), ...tpl })
        setTab('rules')
      }
    } catch {
      // fallback
    }
  }

  async function saveRule() {
    if (!editing || !editing.name?.trim()) {
      setError('Directive / Rule name is required.')
      return
    }
    if (!editing.tag_colors || editing.tag_colors.length === 0) {
      setError('Please select at least one Rank Tier or Clearance Tag.')
      return
    }

    setSaving(true)
    setError(null)
    try {
      if (editingId) {
        await authorizationApi.updateRule(editingId, editing)
      } else {
        await authorizationApi.createRule(editing)
      }
      await loadRules()
      cancelEdit()
    } catch (e: any) {
      setError(e?.response?.data?.detail || 'Failed to save clearance rule')
    } finally {
      setSaving(false)
    }
  }

  async function deleteRule(id: string) {
    if (!confirm('Permanently delete this clearance policy rule?')) return
    try {
      await authorizationApi.deleteRule(id)
      setRules((prev) => prev.filter((r) => r.rule_id !== id))
    } catch {
      // fallback
    }
  }

  async function toggleRule(id: string) {
    try {
      const res = await authorizationApi.toggleRule(id)
      setRules((prev) =>
        prev.map((r) => (r.rule_id === id ? { ...r, active: res.data.active } : r))
      )
    } catch {
      // fallback
    }
  }

  function runSimulation() {
    setTesting(true)
    setTimeout(() => {
      const targetZoneObj = combinedZones.find((z) => z.name === testZone) || combinedZones[0]
      const reqStars = targetZoneObj ? targetZoneObj.min_rank_stars : 0
      const escortAllowed = targetZoneObj ? targetZoneObj.allow_escort : false
      const carried = testObjects.toLowerCase()

      const hasWeapon = carried.includes('weapon') || carried.includes('knife') || carried.includes('gun') || carried.includes('explosive')

      let authorized = false
      let reason = ''
      let action = ''

      if (hasWeapon) {
        authorized = false
        reason = `Lethal contraband / unauthorized weapon detected: "${testObjects}". High-priority sentry lockdown engaged.`
        action = '🚨 TRIGGER RED SENTRY ALARM: Seal security blast doors, initiate immediate physical containment.'
      } else if (testStars >= reqStars) {
        authorized = true
        reason = `Cleared by Rank Clearance: Officer holds Level ${testStars} Stars (Required: Level ${reqStars} Stars for '${targetZoneObj.name}').`
        action = '✓ VERIFIED: Deactivate perimeter interlocks and grant biometric turnstile clearance.'
      } else if (escortAllowed && testHasEscort) {
        authorized = true
        reason = `Cleared via Military Escort Protocol: Subject has Level ${testStars} Stars but is accompanied by an authorized Officer in an escort-permitted zone.`
        action = '✓ ESCORT AUTHORIZED: Log dual-person sentry entry in checkpoint ledger.'
      } else {
        authorized = false
        reason = `INSUFFICIENT STAR CLEARANCE: Subject holds Level ${testStars} Stars, but '${targetZoneObj.name}' requires Level ${reqStars} Stars.${escortAllowed ? ' (Escort protocol was not active).' : ' (Escorts prohibited in this zero-line sector).'}`
        action = '⛔ ACCESS DENIED: Hold at perimeter gate, sound audio chime warning, log breach attempt.'
      }

      setTestResult({
        authorized,
        badge: authorized ? 'CLEARANCE GRANTED' : 'CLEARANCE DENIED',
        reason,
        action,
        requiredStars: reqStars,
      })
      setTesting(false)
    }, 250)
  }

  function toggleTag(color: string) {
    if (!editing) return
    const curr = editing.tag_colors || []
    setEditing({
      ...editing,
      tag_colors: curr.includes(color) ? curr.filter((c) => c !== color) : [...curr, color],
    })
  }

  function addToList(field: keyof AuthorizationRule, value: string, setter: (v: string) => void) {
    if (!value.trim() || !editing) return
    const curr = (editing[field] as string[]) || []
    if (!curr.includes(value.trim())) {
      setEditing({ ...editing, [field]: [...curr, value.trim()] })
    }
    setter('')
  }

  function removeFromList(field: keyof AuthorizationRule, value: string) {
    if (!editing) return
    const curr = (editing[field] as string[]) || []
    setEditing({ ...editing, [field]: curr.filter((v) => v !== value) })
  }

  return (
    <div className="p-6 space-y-6 max-w-7xl mx-auto">
      {/* Header bar */}
      <div className="flex flex-wrap items-center justify-between gap-4 border-b border-ops-border pb-4">
        <div>
          <div className="flex items-center gap-2.5">
            <Award className="w-6 h-6 text-amber-500" />
            <h1 className="text-xl font-bold tracking-wide text-ops-text uppercase font-display flex items-center gap-2">
              Military Rank & Star Clearance Matrix
            </h1>
            <span className="text-[10px] font-mono px-2.5 py-0.5 rounded-full bg-amber-500/15 text-amber-500 border border-amber-500/30 font-bold">
              DEFENSE CLEARANCE v2.4
            </span>
          </div>
          <p className="text-xs text-ops-text-muted mt-1 font-sans">
            Autonomous defense perimeter access control. Enforces ⭐ to ⭐⭐⭐⭐⭐ rank clearance, custom perimeter zones, and sentry escort protocols.
          </p>
        </div>

        {/* Tab Navigation */}
        <div className="flex items-center gap-1.5 bg-ops-surface border border-ops-border p-1 rounded-lg font-display">
          <button
            onClick={() => setTab('matrix')}
            className={`px-3.5 py-1.5 rounded-md text-xs font-semibold transition-all flex items-center gap-1.5 ${
              tab === 'matrix' ? 'bg-amber-500 text-slate-950 font-bold shadow-sm' : 'text-ops-text-muted hover:text-ops-text'
            }`}
          >
            <Award className="w-3.5 h-3.5" />
            <span>Clearance Matrix Grid</span>
          </button>
          <button
            onClick={() => setTab('rules')}
            className={`px-3.5 py-1.5 rounded-md text-xs font-semibold transition-all flex items-center gap-1.5 ${
              tab === 'rules' ? 'bg-amber-500 text-slate-950 font-bold shadow-sm' : 'text-ops-text-muted hover:text-ops-text'
            }`}
          >
            <ShieldCheck className="w-3.5 h-3.5" />
            <span>Directives ({rules.length})</span>
          </button>
          <button
            onClick={() => setTab('simulator')}
            className={`px-3.5 py-1.5 rounded-md text-xs font-semibold transition-all flex items-center gap-1.5 ${
              tab === 'simulator' ? 'bg-amber-500 text-slate-950 font-bold shadow-sm' : 'text-ops-text-muted hover:text-ops-text'
            }`}
          >
            <Play className="w-3.5 h-3.5" />
            <span>Sentry Pre-Flight Sim</span>
          </button>
        </div>
      </div>

      {/* TAB 1: CLEARANCE MATRIX GRID */}
      {tab === 'matrix' && (
        <div className="space-y-6">
          {/* Top 5-Star Rank Cards */}
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3.5">
            {MILITARY_RANK_TIERS.filter((t) => t.stars > 0).map((tier) => (
              <div
                key={tier.stars}
                className={`panel p-4 rounded-xl border ${tier.border} ${tier.bg} backdrop-blur space-y-2 relative overflow-hidden flex flex-col justify-between`}
              >
                <div className="flex items-center justify-between">
                  <span className="text-xs font-mono font-bold tracking-widest text-amber-400">
                    LEVEL {tier.stars}
                  </span>
                  <span className="text-xs tracking-wider">{tier.badge}</span>
                </div>
                <div>
                  <div className={`font-bold text-sm ${tier.color}`}>{tier.title}</div>
                  <p className="text-[11px] text-slate-400 mt-1 leading-relaxed">{tier.description}</p>
                </div>
                <div className="pt-2 border-t border-white/10 text-[10px] text-slate-400">
                  <div className="font-semibold text-slate-300">Authorized Sectors:</div>
                  <div className="truncate text-slate-400 mt-0.5">{tier.typicalZones.join(', ')}</div>
                </div>
              </div>
            ))}
          </div>

          {/* Dynamic Matrix Table */}
          <div className="panel p-5 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl space-y-4">
            <div className="flex items-center justify-between border-b border-slate-800 pb-3">
              <div>
                <div className="text-sm font-bold text-slate-200 tracking-wide uppercase flex items-center gap-2">
                  <span>🗺️</span> Defense Zone vs. Rank Clearance Access Matrix
                </div>
                <div className="text-xs text-slate-400 mt-0.5">
                  Live access rights computed per zone polygon. Cameras visually verify person identity and cross-reference this matrix.
                </div>
              </div>
              <div className="flex items-center gap-3 text-xs text-slate-400">
                <span className="flex items-center gap-1"><span className="text-emerald-400 font-bold">✓</span> Cleared</span>
                <span className="flex items-center gap-1"><span className="text-red-400 font-bold">🚫</span> Restricted</span>
                <span className="flex items-center gap-1"><span className="text-amber-400 font-bold">🤝</span> Escort OK</span>
              </div>
            </div>

            <div className="overflow-x-auto">
              <table className="w-full text-xs">
                <thead>
                  <tr className="text-left text-slate-500 border-b border-ops-border pb-2">
                    <th className="pb-3 text-slate-300 font-bold">Zone Name & Type</th>
                    <th className="pb-3 text-center whitespace-nowrap min-w-[140px]">Required Star Level</th>
                    <th className="pb-3 text-center">⭐ Level 1 (Guard)</th>
                    <th className="pb-3 text-center">⭐⭐ Level 2 (Duty Off)</th>
                    <th className="pb-3 text-center">⭐⭐⭐ Level 3 (Field Off)</th>
                    <th className="pb-3 text-center">⭐⭐⭐⭐ Level 4 (Division)</th>
                    <th className="pb-3 text-center">⭐⭐⭐⭐⭐ Level 5 (Supreme)</th>
                    <th className="pb-3 text-center">Civilian / Visitor</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800/60">
                  {combinedZones.map((z, idx) => {
                    const req = z.min_rank_stars
                    return (
                      <tr key={idx} className="hover:bg-white/[0.02] transition">
                        <td className="py-3 pr-4">
                          <div className="font-bold text-slate-200 text-sm">{z.name}</div>
                          <div className="flex items-center gap-2 mt-0.5">
                            <span className="text-[10px] font-mono uppercase text-slate-500">[{z.type}]</span>
                            {z.allow_escort ? (
                              <span className="text-[9px] text-emerald-400 bg-emerald-500/10 px-1.5 py-0.2 rounded border border-emerald-500/20">
                                Escort Protocol Enabled
                              </span>
                            ) : (
                              <span className="text-[9px] text-red-400 bg-red-500/10 px-1.5 py-0.2 rounded border border-red-500/20">
                                Strict Lockout (No Escort)
                              </span>
                            )}
                          </div>
                        </td>
                        <td className="text-center font-mono py-2.5 px-3">
                          {req === 0 ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700 whitespace-nowrap text-[11px]">
                              Open Patrol
                            </span>
                          ) : (
                            <span className="inline-flex items-center gap-1.5 whitespace-nowrap px-2.5 py-1 rounded-md bg-amber-500/15 text-amber-300 border border-amber-500/35 text-xs font-bold">
                              <span className="inline-flex items-center gap-0.5">
                                {Array.from({ length: req }).map((_, i) => (
                                  <Star key={i} className="w-3 h-3 fill-amber-400 text-amber-400" />
                                ))}
                              </span>
                              <span>Level {req}</span>
                            </span>
                          )}
                        </td>
                        {/* 1-Star */}
                        <td className="text-center">
                          {1 >= req ? (
                            <span className="text-emerald-400 font-bold text-sm">✓</span>
                          ) : z.allow_escort ? (
                            <span className="text-amber-400 text-[10px] font-mono bg-amber-500/10 px-1.5 py-0.5 rounded">🤝 Escort</span>
                          ) : (
                            <span className="text-red-400 font-bold text-sm">🚫</span>
                          )}
                        </td>
                        {/* 2-Star */}
                        <td className="text-center">
                          {2 >= req ? (
                            <span className="text-emerald-400 font-bold text-sm">✓</span>
                          ) : z.allow_escort ? (
                            <span className="text-amber-400 text-[10px] font-mono bg-amber-500/10 px-1.5 py-0.5 rounded">🤝 Escort</span>
                          ) : (
                            <span className="text-red-400 font-bold text-sm">🚫</span>
                          )}
                        </td>
                        {/* 3-Star */}
                        <td className="text-center">
                          {3 >= req ? (
                            <span className="text-emerald-400 font-bold text-sm">✓</span>
                          ) : z.allow_escort ? (
                            <span className="text-amber-400 text-[10px] font-mono bg-amber-500/10 px-1.5 py-0.5 rounded">🤝 Escort</span>
                          ) : (
                            <span className="text-red-400 font-bold text-sm">🚫</span>
                          )}
                        </td>
                        {/* 4-Star */}
                        <td className="text-center">
                          {4 >= req ? (
                            <span className="text-emerald-400 font-bold text-sm">✓</span>
                          ) : z.allow_escort ? (
                            <span className="text-amber-400 text-[10px] font-mono bg-amber-500/10 px-1.5 py-0.5 rounded">🤝 Escort</span>
                          ) : (
                            <span className="text-red-400 font-bold text-sm">🚫</span>
                          )}
                        </td>
                        {/* 5-Star */}
                        <td className="text-center">
                          <span className="text-emerald-400 font-bold text-sm">✓</span>
                        </td>
                        {/* Civilian */}
                        <td className="text-center">
                          {req === 0 ? (
                            <span className="text-emerald-400 font-bold text-sm">✓</span>
                          ) : z.allow_escort ? (
                            <span className="text-amber-400 text-[10px] font-mono bg-amber-500/10 px-1.5 py-0.5 rounded">🤝 Escort</span>
                          ) : (
                            <span className="text-red-400 font-bold text-sm">🚫</span>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </div>
          </div>
        </div>
      )}

      {/* TAB 2: ACTIVE RULES & CLEARANCE DIRECTIVES */}
      {tab === 'rules' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Left 2 Cols: Rules List or Editor */}
          <div className="lg:col-span-2 space-y-4">
            {editing ? (
              <div className="panel p-5 border border-ops-border/70 bg-slate-900/80 backdrop-blur rounded-xl space-y-4 shadow-xl">
                <div className="flex items-center justify-between border-b border-slate-800 pb-3">
                  <span className="font-bold text-slate-100 text-sm uppercase flex items-center gap-2">
                    <span>✏️</span> {editingId ? 'Edit Clearance Directive' : 'Create New Clearance Directive'}
                  </span>
                  <button onClick={cancelEdit} className="text-xs text-slate-400 hover:text-white">✕ Cancel</button>
                </div>

                {error && (
                  <div className="p-2.5 rounded-lg bg-red-500/15 border border-red-500/30 text-red-300 text-xs">
                    {error}
                  </div>
                )}

                <div className="space-y-3">
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1">Directive Name *</label>
                    <input
                      placeholder="e.g. ⭐⭐⭐ Field Officer Armory & Checkpoint Protocol"
                      value={editing.name || ''}
                      onChange={(e) => setEditing({ ...editing, name: e.target.value })}
                      className="w-full bg-black/40 border border-ops-border rounded-lg px-3 py-2 text-sm text-slate-200 focus:outline-none focus:border-amber-400"
                    />
                  </div>

                  {/* Rank Tiers selector */}
                  <div>
                    <label className="block text-xs font-semibold text-slate-300 mb-1.5">Applicable Rank Tiers *</label>
                    <div className="grid grid-cols-2 sm:grid-cols-3 gap-2">
                      {Object.entries(RANK_TAG_MAP).map(([key, info]) => {
                        const isSelected = editing.tag_colors?.includes(key)
                        return (
                          <button
                            key={key}
                            type="button"
                            onClick={() => toggleTag(key)}
                            className={`p-2 rounded-lg border text-left text-xs transition-all ${
                              isSelected
                                ? `${info.badge} font-bold shadow-md shadow-amber-500/10`
                                : 'bg-black/40 border-slate-800 text-slate-400 hover:border-slate-700'
                            }`}
                          >
                            <div>{info.label}</div>
                          </button>
                        )
                      })}
                    </div>
                  </div>

                  {/* Privileges & Overrides */}
                  <div className="grid grid-cols-1 sm:grid-cols-3 gap-2.5 pt-2 border-t border-slate-800">
                    <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer p-2 rounded bg-black/30 border border-slate-800">
                      <input
                        type="checkbox"
                        checked={editing.override_all_rules || false}
                        onChange={(e) => setEditing({ ...editing, override_all_rules: e.target.checked })}
                        className="rounded border-slate-700 text-amber-500 focus:ring-0"
                      />
                      <span>⭐ Master Override Access</span>
                    </label>
                    <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer p-2 rounded bg-black/30 border border-slate-800">
                      <input
                        type="checkbox"
                        checked={editing.escort_privileges || false}
                        onChange={(e) => setEditing({ ...editing, escort_privileges: e.target.checked })}
                        className="rounded border-slate-700 text-amber-500 focus:ring-0"
                      />
                      <span>🤝 Can Escort Lower Ranks</span>
                    </label>
                    <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer p-2 rounded bg-black/30 border border-slate-800">
                      <input
                        type="checkbox"
                        checked={editing.requires_escort || false}
                        onChange={(e) => setEditing({ ...editing, requires_escort: e.target.checked })}
                        className="rounded border-slate-700 text-amber-500 focus:ring-0"
                      />
                      <span>⚠️ Requires Officer Escort</span>
                    </label>
                  </div>

                  {/* Allowed / Forbidden Zones */}
                  <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 pt-2">
                    <div className="space-y-1.5">
                      <label className="block text-xs font-semibold text-emerald-400">Authorized Zones</label>
                      <div className="flex gap-2">
                        <input
                          placeholder="e.g. armory, war_room_alpha"
                          value={zoneInput}
                          onChange={(e) => setZoneInput(e.target.value)}
                          className="flex-1 bg-black/40 border border-ops-border rounded px-2.5 py-1.5 text-xs text-slate-200"
                        />
                        <button
                          type="button"
                          onClick={() => addToList('allowed_zones', zoneInput, setZoneInput)}
                          className="px-3 bg-emerald-500/20 text-emerald-300 border border-emerald-500/40 rounded text-xs"
                        >
                          +
                        </button>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {editing.allowed_zones?.map((z) => (
                          <span key={z} className="px-2 py-0.5 rounded bg-emerald-500/10 text-emerald-300 text-[11px] border border-emerald-500/30 flex items-center gap-1">
                            <span>{z}</span>
                            <button onClick={() => removeFromList('allowed_zones', z)}>✕</button>
                          </span>
                        ))}
                      </div>
                    </div>

                    <div className="space-y-1.5">
                      <label className="block text-xs font-semibold text-red-400">Prohibited / Restricted Zones</label>
                      <div className="flex gap-2">
                        <input
                          placeholder="e.g. war_room_alpha, vault"
                          value={forbidZoneInput}
                          onChange={(e) => setForbidZoneInput(e.target.value)}
                          className="flex-1 bg-black/40 border border-ops-border rounded px-2.5 py-1.5 text-xs text-slate-200"
                        />
                        <button
                          type="button"
                          onClick={() => addToList('forbidden_zones', forbidZoneInput, setForbidZoneInput)}
                          className="px-3 bg-red-500/20 text-red-300 border border-red-500/40 rounded text-xs"
                        >
                          +
                        </button>
                      </div>
                      <div className="flex flex-wrap gap-1 mt-1">
                        {editing.forbidden_zones?.map((z) => (
                          <span key={z} className="px-2 py-0.5 rounded bg-red-500/10 text-red-300 text-[11px] border border-red-500/30 flex items-center gap-1">
                            <span>{z}</span>
                            <button onClick={() => removeFromList('forbidden_zones', z)}>✕</button>
                          </span>
                        ))}
                      </div>
                    </div>
                  </div>

                  {/* Action buttons */}
                  <div className="flex gap-3 pt-3 border-t border-slate-800">
                    <button
                      type="button"
                      onClick={cancelEdit}
                      className="flex-1 bg-slate-800 hover:bg-slate-700 text-slate-300 font-semibold rounded-lg py-2 text-xs transition"
                    >
                      Cancel
                    </button>
                    <button
                      type="button"
                      onClick={saveRule}
                      disabled={saving}
                      className="flex-2 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-lg py-2 text-xs transition shadow-lg shadow-amber-500/20"
                    >
                      {saving ? 'Saving Directive...' : '✓ Save Clearance Directive'}
                    </button>
                  </div>
                </div>
              </div>
            ) : (
              <div className="space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs font-bold uppercase tracking-wider text-slate-400">
                    Active Clearance Directives ({rules.length})
                  </span>
                  <button
                    onClick={startNew}
                    className="px-3 py-1.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-lg text-xs shadow-md shadow-amber-500/15"
                  >
                    + Add New Directive
                  </button>
                </div>

                {rules.length === 0 && (
                  <div className="panel p-8 text-center border border-ops-border/60 bg-slate-900/60 rounded-xl space-y-3">
                    <p className="text-slate-400 text-xs">
                      No custom directives created. Click an official Military Template on the right to load pre-configured Star Clearances.
                    </p>
                  </div>
                )}

                {rules.map((rule) => (
                  <div
                    key={rule.rule_id}
                    className={`panel p-4 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl transition ${
                      !rule.active ? 'opacity-50' : 'hover:border-slate-700'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="font-bold text-slate-100 text-sm">{rule.name}</span>
                          <span className="text-[10px] font-mono px-1.5 py-0.5 rounded bg-black/40 border border-slate-800 text-slate-400">
                            Priority {rule.priority}
                          </span>
                          {rule.override_all_rules && (
                            <span className="px-1.5 py-0.5 bg-purple-500/20 text-purple-300 border border-purple-500/40 rounded text-[10px] font-bold">
                              ⭐ Master Override
                            </span>
                          )}
                          {rule.escort_privileges && (
                            <span className="px-1.5 py-0.5 bg-sky-500/20 text-sky-300 border border-sky-500/40 rounded text-[10px] font-semibold">
                              🤝 Escort Officer
                            </span>
                          )}
                          {rule.requires_escort && (
                            <span className="px-1.5 py-0.5 bg-amber-500/20 text-amber-300 border border-amber-500/40 rounded text-[10px] font-semibold">
                              ⚠️ Escort Required
                            </span>
                          )}
                          <span
                            className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                              rule.active
                                ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                                : 'bg-slate-800 text-slate-400 border-slate-700'
                            }`}
                          >
                            {rule.active ? 'ACTIVE' : 'DISABLED'}
                          </span>
                        </div>

                        {/* Tag badges */}
                        <div className="flex flex-wrap gap-1">
                          {rule.tag_colors.map((c) => (
                            <span
                              key={c}
                              className={`px-2 py-0.5 rounded text-[10px] font-bold border ${
                                RANK_TAG_MAP[c]?.badge || 'bg-slate-800 text-slate-300 border-slate-700'
                              }`}
                            >
                              {RANK_TAG_MAP[c]?.label || c}
                            </span>
                          ))}
                        </div>

                        {/* Zone conditions */}
                        <div className="text-xs text-slate-400 space-y-1">
                          {rule.allowed_zones?.length > 0 && (
                            <div className="flex items-center gap-1.5">
                              <span className="text-emerald-400 font-semibold">✅ Permitted:</span>
                              <span className="text-slate-300">{rule.allowed_zones.join(', ')}</span>
                            </div>
                          )}
                          {rule.forbidden_zones?.length > 0 && (
                            <div className="flex items-center gap-1.5">
                              <span className="text-red-400 font-semibold">🚫 Prohibited:</span>
                              <span className="text-red-300">{rule.forbidden_zones.join(', ')}</span>
                            </div>
                          )}
                        </div>
                      </div>

                      {/* Actions */}
                      <div className="flex items-center gap-1.5 shrink-0">
                        <button
                          onClick={() => startEdit(rule)}
                          className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-cyan-300 rounded-lg border border-slate-700 transition"
                        >
                          ✏️ Edit
                        </button>
                        <button
                          onClick={() => toggleRule(rule.rule_id)}
                          className="px-2.5 py-1 text-xs bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg border border-slate-700 transition"
                        >
                          {rule.active ? 'Disable' : 'Enable'}
                        </button>
                        <button
                          onClick={() => deleteRule(rule.rule_id)}
                          className="px-2.5 py-1 text-xs bg-red-500/10 hover:bg-red-500/20 text-red-400 rounded-lg border border-red-500/30 transition"
                        >
                          🗑️
                        </button>
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>

          {/* Right Col: Official Star Templates */}
          <div className="space-y-4">
            <div className="panel p-5 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl space-y-3">
              <div className="text-xs font-bold uppercase tracking-wider text-amber-400 flex items-center gap-1.5 border-b border-slate-800 pb-2">
                <span>⭐</span> Pre-Configured Defense Templates
              </div>
              <p className="text-xs text-slate-400">
                1-click instant provisioning of standardized military clearance profiles into the active AI engine:
              </p>

              {[
                { key: 'star_5_supreme_command', label: '⭐⭐⭐⭐⭐ Level 5: Supreme Commander', desc: 'Master override across all facility zones and War Room' },
                { key: 'star_4_division_officer', label: '⭐⭐⭐⭐ Level 4: Division Commander', desc: 'Tactical Center, Perimeter Ops, and Main Armory' },
                { key: 'star_3_field_officer', label: '⭐⭐⭐ Level 3: Field Officer / Major', desc: 'Armory Access, Checkpoints, and Field HQ' },
                { key: 'star_2_duty_officer', label: '⭐⭐ Level 2: Duty Officer', desc: 'Checkpoints, Duty Room, and Supply Depot' },
                { key: 'star_1_sentry_guard', label: '⭐ Level 1: Patrol Guard / Sentry', desc: 'Main Gates, Watchtowers, and Outer Patrol' },
                { key: 'civilian_contractor', label: 'Civilian / Contractor (Escort Req.)', desc: 'Entry gates only; military escort strictly required' },
              ].map((t) => (
                <button
                  key={t.key}
                  onClick={() => loadTemplate(t.key)}
                  className="w-full text-left p-2.5 rounded-lg border border-slate-800 bg-black/40 hover:border-amber-400/70 hover:bg-amber-950/20 transition group"
                >
                  <div className="font-bold text-xs text-slate-200 group-hover:text-amber-300">{t.label}</div>
                  <div className="text-[11px] text-slate-500 mt-0.5">{t.desc}</div>
                </button>
              ))}
            </div>
          </div>
        </div>
      )}

      {/* TAB 3: SENTRY PRE-FLIGHT SIMULATOR */}
      {tab === 'simulator' && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Simulator Controls */}
          <div className="panel p-5 border border-ops-border/60 bg-slate-900/60 backdrop-blur rounded-xl space-y-4">
            <div className="text-sm font-bold tracking-wide text-amber-400 uppercase flex items-center justify-between border-b border-slate-800 pb-2">
              <span>🧪 Pre-Flight Sentry Simulator</span>
              <span className="text-[10px] font-mono text-slate-400">CLEARANCE TEST</span>
            </div>
            <p className="text-xs text-slate-400">
              Simulate an officer or contractor presenting at a physical zone. Evaluates clearance stars, prohibited items, and escort conditions instantly.
            </p>

            {/* Officer Rank Selector */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300 block">Personnel Rank / Star Level</label>
              <div className="space-y-1">
                {MILITARY_RANK_TIERS.map((tier) => (
                  <button
                    key={tier.stars}
                    type="button"
                    onClick={() => setTestStars(tier.stars)}
                    className={`w-full flex items-center justify-between px-3 py-2 rounded-lg border text-xs transition-all text-left ${
                      testStars === tier.stars
                        ? 'bg-amber-500/25 border-amber-400 text-amber-200 font-bold shadow-sm shadow-amber-500/20'
                        : 'bg-black/40 border-slate-800 text-slate-400 hover:border-slate-700'
                    }`}
                  >
                    <span>{tier.title}</span>
                    <span className="font-mono text-[11px]">{tier.badge}</span>
                  </button>
                ))}
              </div>
            </div>

            {/* Target Zone */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300 block">Destination Zone</label>
              <select
                value={testZone}
                onChange={(e) => setTestZone(e.target.value)}
                className="w-full bg-ops-card border border-ops-border rounded-lg px-3 py-2 text-xs text-ops-text focus:outline-none focus:border-amber-400 font-sans"
              >
                {combinedZones.map((z) => (
                  <option key={z.name} value={z.name}>
                    {z.name} (Required: {z.min_rank_stars === 0 ? 'Open' : `${z.min_rank_stars} Stars`})
                  </option>
                ))}
              </select>
            </div>

            {/* Escort status */}
            <div className="space-y-1.5">
              <label className="flex items-center gap-2 text-xs text-slate-300 cursor-pointer p-2.5 rounded bg-black/30 border border-slate-800">
                <input
                  type="checkbox"
                  checked={testHasEscort}
                  onChange={(e) => setTestHasEscort(e.target.checked)}
                  className="rounded border-slate-700 text-amber-500 focus:ring-0"
                />
                <span>🤝 Accompanied by Authorized Higher-Rank Escort</span>
              </label>
            </div>

            {/* Objects / Contraband */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-slate-300 block">Carried Objects / Equipment (Optional)</label>
              <input
                value={testObjects}
                onChange={(e) => setTestObjects(e.target.value)}
                placeholder="e.g. standard_radio, knife, concealed_weapon"
                className="w-full bg-black/40 border border-ops-border rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-600 focus:outline-none focus:border-amber-400"
              />
            </div>

            <button
              onClick={runSimulation}
              disabled={testing}
              className="w-full py-2.5 bg-amber-500 hover:bg-amber-400 text-slate-950 font-bold rounded-xl text-xs transition shadow-lg shadow-amber-500/20"
            >
              {testing ? 'Evaluating Clearance...' : '⚡ Run Pre-Flight Simulation'}
            </button>
          </div>

          {/* Simulator Readout Output */}
          <div className="lg:col-span-2 space-y-4">
            {testResult ? (
              <div
                className={`panel p-6 rounded-xl border space-y-4 shadow-xl ${
                  testResult.authorized
                    ? 'bg-emerald-950/20 border-emerald-500/40'
                    : 'bg-red-950/20 border-red-500/40'
                }`}
              >
                <div className="flex items-center justify-between border-b border-white/10 pb-3">
                  <div className="flex items-center gap-2">
                    <span className="text-2xl">{testResult.authorized ? '✅' : '🚨'}</span>
                    <div>
                      <div
                        className={`font-black text-lg tracking-wider uppercase ${
                          testResult.authorized ? 'text-emerald-400' : 'text-red-400'
                        }`}
                      >
                        {testResult.badge}
                      </div>
                      <div className="text-xs text-slate-400">
                        Evaluated by Project Garuda Temporal Access Engine
                      </div>
                    </div>
                  </div>
                  <span
                    className={`px-3 py-1 rounded-full text-xs font-mono font-bold border ${
                      testResult.authorized
                        ? 'bg-emerald-500/20 text-emerald-300 border-emerald-500/40'
                        : 'bg-red-500/20 text-red-300 border-red-500/40'
                    }`}
                  >
                    STATUS: {testResult.authorized ? 'CLEARED' : 'BREACH BLOCKED'}
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-3 text-xs">
                  <div className="p-3 bg-black/40 rounded-lg border border-slate-800">
                    <div className="text-slate-400 font-semibold">Subject Star Level:</div>
                    <div className="text-amber-300 font-mono font-bold text-sm mt-1 inline-flex items-center gap-1.5 whitespace-nowrap">
                      <span className="inline-flex items-center gap-0.5">
                        {Array.from({ length: testStars || 1 }).map((_, i) => (
                          <Star key={i} className="w-3.5 h-3.5 fill-amber-400 text-amber-400" />
                        ))}
                      </span>
                      <span>Level {testStars}</span>
                    </div>
                  </div>
                  <div className="p-3 bg-black/40 rounded-lg border border-slate-800">
                    <div className="text-slate-400 font-semibold">Zone Requirement:</div>
                    <div className="text-cyan-300 font-mono font-bold text-sm mt-1 inline-flex items-center gap-1.5 whitespace-nowrap">
                      {testResult.requiredStars === 0 ? (
                        'Open Access (0 Stars)'
                      ) : (
                        <>
                          <span className="inline-flex items-center gap-0.5">
                            {Array.from({ length: testResult.requiredStars }).map((_, i) => (
                              <Star key={i} className="w-3.5 h-3.5 fill-cyan-400 text-cyan-400" />
                            ))}
                          </span>
                          <span>Level {testResult.requiredStars}</span>
                        </>
                      )}
                    </div>
                  </div>
                </div>

                <div className="space-y-1">
                  <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    AI Decision Analysis & Rationale
                  </div>
                  <p className="text-xs text-slate-200 bg-black/40 p-3 rounded-lg border border-slate-800 leading-relaxed font-mono">
                    {testResult.reason}
                  </p>
                </div>

                <div className="space-y-1">
                  <div className="text-xs font-semibold text-slate-300 uppercase tracking-wider">
                    Required Sentry Protocol
                  </div>
                  <p
                    className={`text-xs p-3 rounded-lg border font-mono font-semibold ${
                      testResult.authorized
                        ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-300'
                        : 'bg-red-500/10 border-red-500/30 text-red-300'
                    }`}
                  >
                    {testResult.action}
                  </p>
                </div>
              </div>
            ) : (
              <div className="panel p-12 text-center border border-ops-border/60 bg-slate-900/60 rounded-xl space-y-3">
                <span className="text-4xl">🛡️</span>
                <div className="text-sm font-bold text-slate-200">Sentry Simulator Idle</div>
                <p className="text-xs text-slate-400 max-w-md mx-auto">
                  Select an officer star clearance tier and a perimeter zone on the left, then click "Run Pre-Flight Simulation" to inspect real-time enforcement.
                </p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
