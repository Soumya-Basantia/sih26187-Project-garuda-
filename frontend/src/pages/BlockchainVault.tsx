import React, { useState, useEffect } from 'react'
import {
  blockchainApi,
  BlockchainBlock,
  BlockchainStats,
  BlockchainTransaction,
  Section65BCertificate,
} from '../services/api'
import {
  ShieldCheck,
  ShieldAlert,
  Link,
  Layers,
  FileCheck,
  RefreshCw,
  AlertTriangle,
  FileText,
  Key,
  CheckCircle2,
  XCircle,
  Database,
  Cpu,
  Fingerprint,
  Download,
  Eye,
  Terminal,
  Clock,
  Sparkles,
  Lock,
} from 'lucide-react'

export default function BlockchainVault() {
  const [stats, setStats] = useState<BlockchainStats | null>(null)
  const [blocks, setBlocks] = useState<BlockchainBlock[]>([])
  const [loading, setLoading] = useState(true)
  const [auditResult, setAuditResult] = useState<{
    valid: boolean
    total_blocks_verified?: number
    tampered_block_index?: number
    error_type?: string
    details: string
  } | null>(null)
  const [auditing, setAuditing] = useState(false)
  const [selectedCert, setSelectedCert] = useState<Section65BCertificate | null>(null)
  const [certLoading, setCertLoading] = useState(false)
  const [expandedBlockIndex, setExpandedBlockIndex] = useState<number | null>(null)
  const [actionMessage, setActionMessage] = useState<string | null>(null)

  useEffect(() => {
    loadData()
    const interval = setInterval(loadData, 10000)
    return () => clearInterval(interval)
  }, [])

  async function loadData() {
    try {
      const [statsRes, ledgerRes] = await Promise.all([
        blockchainApi.getStats(),
        blockchainApi.getLedger(30),
      ])
      setStats(statsRes.data)
      setBlocks(ledgerRes.data.blocks)
      if (expandedBlockIndex === null && ledgerRes.data.blocks.length > 0) {
        setExpandedBlockIndex(ledgerRes.data.blocks[0].index)
      }
    } catch (err) {
      console.error('Failed to load blockchain ledger:', err)
    } finally {
      setLoading(false)
    }
  }

  async function handleAuditChain() {
    setAuditing(true)
    try {
      const res = await blockchainApi.verifyChain()
      setAuditResult(res.data)
      await loadData()
    } catch (err) {
      console.error('Verification failed:', err)
    } finally {
      setAuditing(false)
    }
  }

  async function handleSimulateTamper() {
    try {
      const res = await blockchainApi.simulateTamper()
      setActionMessage(res.data.message)
      await loadData()
      await handleAuditChain()
    } catch (err) {
      console.error('Tamper simulation failed:', err)
    }
  }

  async function handleRestoreLedger() {
    try {
      const res = await blockchainApi.restoreLedger()
      setActionMessage(res.data.message)
      setAuditResult(null)
      await loadData()
    } catch (err) {
      console.error('Restore failed:', err)
    }
  }

  async function openCertificate(alertId: string) {
    setCertLoading(true)
    try {
      const res = await blockchainApi.getCertificate(alertId)
      setSelectedCert(res.data)
    } catch (err) {
      console.error('Failed to load certificate:', err)
    } finally {
      setCertLoading(false)
    }
  }

  const isTampered = stats?.is_tampered_for_demo || (auditResult && !auditResult.valid)

  return (
    <div className="space-y-6">
      {/* Top Header */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-white/10 pb-5">
        <div>
          <div className="flex items-center gap-3">
            <div className="p-2.5 rounded-lg bg-emerald-500/10 border border-emerald-500/30 text-emerald-400">
              <Layers className="w-6 h-6" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-xl md:text-2xl font-black tracking-wider text-white font-mono">
                  GARUDA-CHAIN // EVIDENCE VAULT
                </h1>
                <span className="px-2 py-0.5 text-xs font-mono rounded font-semibold bg-emerald-500/20 text-emerald-300 border border-emerald-500/40">
                  SEC 65B CERTIFIED
                </span>
              </div>
              <p className="text-sm text-slate-400 mt-0.5">
                Military-Grade Cryptographic Evidence Chain-of-Custody & Indian Evidence Act Digital Ledger
              </p>
            </div>
          </div>
        </div>

        {/* Global Chain Status Badge & Actions */}
        <div className="flex items-center gap-3">
          <div
            className={`px-4 py-2 rounded-lg border flex items-center gap-2.5 font-mono text-xs font-bold ${
              isTampered
                ? 'bg-rose-500/10 border-rose-500/40 text-rose-300 animate-pulse'
                : 'bg-emerald-500/10 border-emerald-500/40 text-emerald-300'
            }`}
          >
            {isTampered ? (
              <>
                <ShieldAlert className="w-4 h-4 text-rose-400" />
                <span>🚨 TAMPER DETECTED — CHAIN COMPROMISED</span>
              </>
            ) : (
              <>
                <ShieldCheck className="w-4 h-4 text-emerald-400" />
                <span>100% CRYPTOGRAPHICALLY VALID</span>
              </>
            )}
          </div>

          <button
            onClick={loadData}
            disabled={loading}
            className="p-2.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-white/10 transition-colors"
            title="Refresh Ledger"
          >
            <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
          </button>
        </div>
      </div>

      {/* Action Notification Banner */}
      {actionMessage && (
        <div className="p-4 rounded-xl bg-cyan-950/40 border border-cyan-500/30 flex items-center justify-between text-cyan-200 text-sm">
          <div className="flex items-center gap-2.5">
            <Terminal className="w-4 h-4 text-cyan-400" />
            <span className="font-mono">{actionMessage}</span>
          </div>
          <button
            onClick={() => setActionMessage(null)}
            className="text-xs text-cyan-400 hover:text-cyan-200 underline font-mono"
          >
            Dismiss
          </button>
        </div>
      )}

      {/* Top Telemetry Stats Cards */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <div className="p-4 rounded-xl bg-slate-900/60 border border-white/10 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Chain Height</span>
            <Database className="w-4 h-4 text-indigo-400" />
          </div>
          <div className="text-3xl font-black font-mono text-white mt-2">
            #{stats?.chain_height ?? '—'}
          </div>
          <p className="text-xs text-slate-500 mt-1 font-mono">Immutable Blocks Sealed</p>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-white/10 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Anchored Evidence</span>
            <FileCheck className="w-4 h-4 text-emerald-400" />
          </div>
          <div className="text-3xl font-black font-mono text-emerald-400 mt-2">
            {stats?.total_evidence_transactions ?? '—'}
          </div>
          <p className="text-xs text-slate-500 mt-1 font-mono">SHA-256 Verified Snapshots</p>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-white/10 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Consensus Engine</span>
            <Cpu className="w-4 h-4 text-amber-400" />
          </div>
          <div className="text-base font-bold font-mono text-amber-300 mt-2">
            PoA Edge Sentry
          </div>
          <p className="text-xs text-slate-500 mt-1 font-mono">Zero-Mining Edge Latency</p>
        </div>

        <div className="p-4 rounded-xl bg-slate-900/60 border border-white/10 relative overflow-hidden">
          <div className="flex items-center justify-between">
            <span className="text-xs font-mono text-slate-400 uppercase tracking-wider">Validator Node</span>
            <Fingerprint className="w-4 h-4 text-cyan-400" />
          </div>
          <div className="text-sm font-bold font-mono text-cyan-300 mt-2 truncate">
            {stats?.validator_node ?? 'GARUDA-HQ-01'}
          </div>
          <p className="text-xs text-slate-500 mt-1 font-mono">Cryptographic Sentry ID</p>
        </div>
      </div>

      {/* SIH Hackathon Jury Tamper Verification Lab */}
      <div className="p-5 rounded-xl bg-gradient-to-r from-slate-900/90 via-slate-900/70 to-slate-900/90 border border-indigo-500/30 shadow-xl">
        <div className="flex flex-col lg:flex-row items-start lg:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-2 text-indigo-400 font-mono text-xs uppercase tracking-widest font-bold">
              <Sparkles className="w-4 h-4" />
              <span>SIH Grand Jury Interactive Testbed</span>
            </div>
            <h2 className="text-lg font-bold text-white mt-1">
              Cryptographic Integrity Verification & Tamper Simulation Lab
            </h2>
            <p className="text-xs text-slate-400 mt-0.5 max-w-2xl">
              Demonstrate unassailable mathematical proof: Test the chain with legitimate audits, or simulate a covert
              database intrusion altering 1 byte of evidence data to watch the Merkle cascade immediately flag corruption.
            </p>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              onClick={handleAuditChain}
              disabled={auditing}
              className="px-4 py-2.5 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-mono text-xs font-bold flex items-center gap-2 transition-all shadow-lg shadow-indigo-600/20 disabled:opacity-50"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${auditing ? 'animate-spin' : ''}`} />
              <span>Verify Cryptographic Chain</span>
            </button>

            {!isTampered ? (
              <button
                onClick={handleSimulateTamper}
                className="px-4 py-2.5 rounded-lg bg-rose-600/20 hover:bg-rose-600/30 text-rose-300 border border-rose-500/40 font-mono text-xs font-bold flex items-center gap-2 transition-all"
                title="Simulate modifying 1 byte of transaction data without block re-hash"
              >
                <AlertTriangle className="w-3.5 h-3.5 text-rose-400" />
                <span>Simulate 1-Byte Tampering</span>
              </button>
            ) : (
              <button
                onClick={handleRestoreLedger}
                className="px-4 py-2.5 rounded-lg bg-emerald-600 hover:bg-emerald-500 text-white font-mono text-xs font-bold flex items-center gap-2 transition-all shadow-lg shadow-emerald-600/20"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
                <span>Restore & Resync Ledger</span>
              </button>
            )}
          </div>
        </div>

        {/* Audit Result Display */}
        {auditResult && (
          <div
            className={`mt-4 p-4 rounded-lg border font-mono text-xs ${
              auditResult.valid
                ? 'bg-emerald-950/30 border-emerald-500/40 text-emerald-200'
                : 'bg-rose-950/40 border-rose-500/50 text-rose-200'
            }`}
          >
            <div className="flex items-center gap-2 font-bold text-sm">
              {auditResult.valid ? (
                <>
                  <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  <span>AUDIT PASSED: {auditResult.details}</span>
                </>
              ) : (
                <>
                  <XCircle className="w-4 h-4 text-rose-400" />
                  <span>TAMPER AUDIT FAILED: {auditResult.error_type}</span>
                </>
              )}
            </div>
            {!auditResult.valid && (
              <div className="mt-2 text-rose-300/90 pl-6 space-y-1">
                <p>• {auditResult.details}</p>
                <p>• Infiltration target: Block #{auditResult.tampered_block_index}</p>
                <p className="text-amber-300 font-bold">
                  ⚖️ Judicial Consequence: Evidence inadmissible in court due to hash mismatch. The system automatically isolated the compromised node!
                </p>
              </div>
            )}
          </div>
        )}
      </div>

      {/* Main Ledger Section */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left Column: Visual Blocks List */}
        <div className="lg:col-span-1 space-y-3">
          <div className="flex items-center justify-between">
            <h3 className="text-sm font-bold font-mono text-slate-300 uppercase tracking-wider flex items-center gap-2">
              <Database className="w-4 h-4 text-indigo-400" />
              <span>Chained Blocks ({blocks.length})</span>
            </h3>
            <span className="text-xs font-mono text-slate-500">Chronological Order</span>
          </div>

          <div className="space-y-2.5 max-h-[720px] overflow-y-auto pr-1">
            {blocks.map((block) => {
              const isSelected = expandedBlockIndex === block.index
              const blockHasTamper = block.transactions.some((t) => t.tampered_flag)

              return (
                <div
                  key={block.index}
                  onClick={() => setExpandedBlockIndex(block.index)}
                  className={`p-3.5 rounded-xl border transition-all cursor-pointer ${
                    blockHasTamper
                      ? 'bg-rose-950/30 border-rose-500/50 hover:border-rose-400'
                      : isSelected
                      ? 'bg-indigo-950/40 border-indigo-500 shadow-lg shadow-indigo-500/10'
                      : 'bg-slate-900/60 border-white/10 hover:border-white/20'
                  }`}
                >
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2">
                      <span className="px-2 py-0.5 text-xs font-mono font-bold rounded bg-slate-800 text-white border border-white/10">
                        BLOCK #{block.index}
                      </span>
                      {block.index === 0 && (
                        <span className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-amber-500/20 text-amber-300 border border-amber-500/40">
                          GENESIS
                        </span>
                      )}
                      {blockHasTamper && (
                        <span className="px-1.5 py-0.2 text-[10px] font-mono rounded bg-rose-500/30 text-rose-300 border border-rose-500/50 animate-pulse font-bold">
                          TAMPERED
                        </span>
                      )}
                    </div>
                    <span className="text-[11px] font-mono text-slate-400">
                      {new Date(block.timestamp * 1000).toLocaleTimeString()}
                    </span>
                  </div>

                  <div className="mt-2 text-xs font-mono text-slate-300 truncate">
                    <span className="text-slate-500">Hash: </span>
                    <span className="text-indigo-300 font-semibold">{block.hash.substring(0, 20)}...</span>
                  </div>

                  <div className="mt-2 flex items-center justify-between text-[11px] font-mono text-slate-400 border-t border-white/5 pt-2">
                    <span>TXs: {block.transactions.length}</span>
                    <span className="text-slate-500">Nonce: {block.nonce}</span>
                  </div>
                </div>
              )
            })}
          </div>
        </div>

        {/* Right Column: Selected Block Details & Transactions */}
        <div className="lg:col-span-2 space-y-4">
          {(() => {
            const activeBlock = blocks.find((b) => b.index === expandedBlockIndex) || blocks[0]
            if (!activeBlock) return null

            const blockHasTamper = activeBlock.transactions.some((t) => t.tampered_flag)

            return (
              <div className="p-5 rounded-xl bg-slate-900/60 border border-white/10 space-y-5">
                {/* Block Header Info */}
                <div className="border-b border-white/10 pb-4">
                  <div className="flex items-center justify-between">
                    <div className="flex items-center gap-2.5">
                      <span className="px-2.5 py-1 text-xs font-mono font-bold rounded-md bg-indigo-600 text-white">
                        BLOCK #{activeBlock.index}
                      </span>
                      <h3 className="text-base font-bold text-white font-mono">
                        Block Header & Merkle Root
                      </h3>
                    </div>
                    <span className="text-xs font-mono text-slate-400">
                      UTC: {activeBlock.timestamp_iso || new Date(activeBlock.timestamp * 1000).toISOString()}
                    </span>
                  </div>

                  {/* Hashes Grid */}
                  <div className="mt-4 grid grid-cols-1 gap-2.5 text-xs font-mono">
                    <div className="p-2.5 rounded-lg bg-black/40 border border-white/5">
                      <span className="text-slate-500 block text-[11px] uppercase">Current Block SHA-256 Hash:</span>
                      <span className={`font-bold break-all ${blockHasTamper ? 'text-rose-400' : 'text-emerald-400'}`}>
                        {activeBlock.hash}
                      </span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-black/40 border border-white/5">
                      <span className="text-slate-500 block text-[11px] uppercase">Previous Block Hash (Parent Link):</span>
                      <span className="text-slate-300 break-all">{activeBlock.prev_hash}</span>
                    </div>

                    <div className="p-2.5 rounded-lg bg-black/40 border border-white/5">
                      <span className="text-slate-500 block text-[11px] uppercase">Merkle Tree Root:</span>
                      <span className="text-amber-300 break-all">{activeBlock.merkle_root}</span>
                    </div>
                  </div>
                </div>

                {/* Evidence Transactions in this Block */}
                <div>
                  <div className="flex items-center justify-between mb-3">
                    <h4 className="text-xs font-mono font-bold text-slate-300 uppercase tracking-wider flex items-center gap-2">
                      <FileCheck className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Sealed Evidence Transactions ({activeBlock.transactions.length})</span>
                    </h4>
                    <span className="text-xs font-mono text-slate-500">Sec 65B Admissible</span>
                  </div>

                  <div className="space-y-3">
                    {activeBlock.transactions.map((tx, txIdx) => (
                      <div
                        key={tx.tx_id || txIdx}
                        className={`p-4 rounded-xl border transition-all ${
                          tx.tampered_flag
                            ? 'bg-rose-950/40 border-rose-500/60 text-rose-200'
                            : 'bg-black/30 border-white/10 text-slate-200'
                        }`}
                      >
                        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 border-b border-white/5 pb-2.5">
                          <div className="flex items-center gap-2 font-mono text-xs">
                            <span className="text-slate-400 font-semibold">{tx.tx_id}</span>
                            <span
                              className={`px-2 py-0.5 rounded text-[10px] font-bold ${
                                tx.severity === 'RED'
                                  ? 'bg-rose-500/20 text-rose-300 border border-rose-500/30'
                                  : tx.severity === 'ORANGE'
                                  ? 'bg-amber-500/20 text-amber-300 border border-amber-500/30'
                                  : 'bg-indigo-500/20 text-indigo-300 border border-indigo-500/30'
                              }`}
                            >
                              {tx.severity} // {tx.event_type}
                            </span>
                            {tx.tampered_flag && (
                              <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-600 text-white animate-pulse">
                                TAMPERED
                              </span>
                            )}
                          </div>

                          <button
                            onClick={() => openCertificate(tx.alert_id || tx.tx_id)}
                            className="px-2.5 py-1 rounded bg-indigo-600/30 hover:bg-indigo-600/50 text-indigo-200 border border-indigo-500/40 text-xs font-mono flex items-center gap-1.5 transition-colors self-start sm:self-auto"
                          >
                            <FileText className="w-3.5 h-3.5" />
                            <span>Sec 65B Certificate</span>
                          </button>
                        </div>

                        <div className="mt-3 grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
                          <div>
                            <span className="text-slate-500">Camera Origin: </span>
                            <span className="text-white font-semibold">{tx.camera_id} ({tx.camera_name || 'Optical'})</span>
                          </div>
                          <div>
                            <span className="text-slate-500">Operator Signer: </span>
                            <span className="text-emerald-300">{tx.operator_action}</span>
                          </div>
                        </div>

                        <div className="mt-2.5 p-2 rounded bg-black/40 border border-white/5 text-[11px] font-mono break-all space-y-1">
                          <div>
                            <span className="text-slate-500">Snapshot SHA-256 Digest: </span>
                            <span className="text-indigo-300">{tx.snapshot_sha256}</span>
                          </div>
                          <div>
                            <span className="text-slate-500">Digital Signature: </span>
                            <span className="text-slate-400">{tx.cryptographic_signature}</span>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )
          })()}
        </div>
      </div>

      {/* Section 65B Certificate Modal */}
      {selectedCert && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm animate-fade-in">
          <div className="bg-slate-900 border border-indigo-500/40 rounded-2xl max-w-2xl w-full p-6 shadow-2xl relative max-h-[90vh] overflow-y-auto font-mono text-xs">
            {/* Certificate Watermark Header */}
            <div className="text-center border-b border-white/10 pb-4">
              <div className="inline-flex p-2 rounded-full bg-indigo-500/10 border border-indigo-500/30 text-indigo-400 mb-2">
                <ShieldCheck className="w-6 h-6" />
              </div>
              <h3 className="text-base font-bold text-white uppercase tracking-wider">
                Certificate of Electronic Evidence Authenticity
              </h3>
              <p className="text-[11px] text-amber-300 font-semibold mt-0.5">
                {selectedCert.statutory_act}
              </p>
              <p className="text-[10px] text-slate-400">
                Issued by: {selectedCert.issuing_authority}
              </p>
            </div>

            {/* Certificate Body */}
            <div className="mt-4 space-y-3.5 text-slate-300">
              <div className="p-3 rounded-lg bg-black/40 border border-white/10 grid grid-cols-2 gap-2 text-[11px]">
                <div>
                  <span className="text-slate-500 block">Certificate Identifier:</span>
                  <span className="text-indigo-300 font-bold">{selectedCert.certificate_id}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Judicial Status:</span>
                  <span className="text-emerald-400 font-bold">{selectedCert.verification_status}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Incident Reference:</span>
                  <span className="text-white">{selectedCert.evidence_details.alert_id}</span>
                </div>
                <div>
                  <span className="text-slate-500 block">Event Classification:</span>
                  <span className="text-white">{selectedCert.evidence_details.event_type} ({selectedCert.evidence_details.severity})</span>
                </div>
              </div>

              {/* Cryptographic Anchor Details */}
              <div className="p-3 rounded-lg bg-black/40 border border-white/10 space-y-1.5 text-[11px]">
                <div className="font-bold text-slate-200 border-b border-white/5 pb-1 flex items-center justify-between">
                  <span>GARUDA-CHAIN ON-LEDGER PROOF</span>
                  <span className="text-indigo-400">BLOCK #{selectedCert.blockchain_anchor.block_index}</span>
                </div>
                <p className="break-all">
                  <span className="text-slate-500">Block SHA-256 Hash: </span>
                  <span className="text-emerald-300">{selectedCert.blockchain_anchor.block_hash}</span>
                </p>
                <p className="break-all">
                  <span className="text-slate-500">Merkle Tree Root: </span>
                  <span className="text-amber-300">{selectedCert.blockchain_anchor.merkle_root}</span>
                </p>
                <p className="break-all">
                  <span className="text-slate-500">Raw Evidence Snapshot Hash: </span>
                  <span className="text-indigo-300">{selectedCert.evidence_details.snapshot_sha256_digest}</span>
                </p>
              </div>

              {/* Statutory Attestation Statement */}
              <div className="p-3 rounded-lg bg-indigo-950/20 border border-indigo-500/30 text-indigo-200 text-[11px] leading-relaxed">
                <p className="italic font-sans">
                  "{selectedCert.legal_attestation_text}"
                </p>
              </div>

              {/* Digital Seal */}
              <div className="flex items-center justify-between border-t border-white/10 pt-3 text-[11px]">
                <div>
                  <span className="text-slate-500 block">Cryptographic Seal Digest:</span>
                  <span className="text-slate-400">{selectedCert.digital_seal.substring(0, 32)}...</span>
                </div>
                <div className="text-right">
                  <span className="text-emerald-400 font-bold flex items-center gap-1">
                    <CheckCircle2 className="w-3.5 h-3.5" />
                    TAMPER-PROOF VERIFIED
                  </span>
                </div>
              </div>
            </div>

            {/* Modal Actions */}
            <div className="mt-5 flex items-center justify-end gap-3 border-t border-white/10 pt-4">
              <button
                onClick={() => window.print()}
                className="px-4 py-2 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 border border-white/10 font-bold flex items-center gap-1.5 transition-colors"
              >
                <Download className="w-3.5 h-3.5" />
                <span>Print Legal Certificate</span>
              </button>
              <button
                onClick={() => setSelectedCert(null)}
                className="px-4 py-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white font-bold transition-colors"
              >
                Close Certificate
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
