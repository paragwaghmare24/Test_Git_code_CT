import React, { useState, useEffect } from 'react'
import { validateEDI } from '../api'
import AIAssistBar, { AITabAction } from './AIAssistBar'

const VALIDATION_AI_ACTIONS: AITabAction[] = [
  { label: 'Explain Errors', icon: '🔍', description: 'Explain each validation error in plain English', promptHint: 'Explain these EDI validation errors:' },
  { label: 'Suggest Corrections', icon: '✎', description: 'Suggest specific corrections for each error', promptHint: 'Suggest corrections for these EDI errors:' },
  { label: 'Interpret Guide Rule', icon: '⊞', description: 'Interpret companion guide requirements for detected issues', promptHint: 'Interpret companion guide rules for:' },
  { label: 'Explain Segment', icon: '◎', description: 'Explain what a specific segment means in business terms', promptHint: 'Explain the business meaning of this EDI segment:' },
]

/* ─── Styles ─────────────────────────────────────────────────────────────── */
const s: Record<string, React.CSSProperties> = {
  container: { padding: 24, fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  title: { fontSize: 20, fontWeight: 700, marginBottom: 20, color: '#1F4E79' },
  card: { background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 16 },
  label: { display: 'block', marginBottom: 8, fontWeight: 600, color: '#444', fontSize: 14 },
  input: { width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, marginBottom: 12 },
  btn: { padding: '10px 28px', background: '#1F4E79', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 },
  btnDisabled: { opacity: 0.6, cursor: 'not-allowed' },

  // Status banners
  bannerPass:    { background: '#e8f5e9', border: '1px solid #a5d6a7', borderRadius: 8, padding: '12px 16px', marginBottom: 16, color: '#1b5e20', fontWeight: 600 },
  bannerWarning: { background: '#fff8e1', border: '1px solid #ffe082', borderRadius: 8, padding: '12px 16px', marginBottom: 16, color: '#e65100', fontWeight: 600 },
  bannerFail:    { background: '#ffebee', border: '1px solid #ef9a9a', borderRadius: 8, padding: '12px 16px', marginBottom: 16, color: '#b71c1c', fontWeight: 600 },

  // Inspector layout
  inspector: { display: 'grid', gridTemplateColumns: '260px 1fr', gap: 16, alignItems: 'start' },
  sidebar: { background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', overflow: 'hidden', position: 'sticky' as const, top: 16 },
  sidebarTitle: { padding: '12px 16px', background: '#1F4E79', color: '#fff', fontSize: 12, fontWeight: 700, letterSpacing: 0.5 },
  sidebarItem: { padding: '8px 16px', cursor: 'pointer', fontSize: 12, borderBottom: '1px solid #f5f5f5', display: 'flex', alignItems: 'center', gap: 6 },
  sidebarItemActive: { background: '#e3f0fa', fontWeight: 700, color: '#1F4E79' },
  dot: { width: 8, height: 8, borderRadius: '50%', flexShrink: 0 },

  // Segment card
  segCard: { background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 12, overflow: 'hidden' },
  segCardError: { boxShadow: '0 0 0 2px #ef5350, 0 1px 4px rgba(0,0,0,0.1)' },
  segCardWarning: { boxShadow: '0 0 0 2px #ffa726, 0 1px 4px rgba(0,0,0,0.1)' },
  segHeader: { padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 10, background: '#f8fafc', borderBottom: '1px solid #eee', cursor: 'pointer' },
  segId: { fontFamily: 'monospace', fontWeight: 800, fontSize: 14, color: '#1F4E79', minWidth: 40 },
  segName: { fontWeight: 600, fontSize: 13, color: '#333' },
  segPurpose: { fontSize: 11, color: '#888', marginLeft: 'auto' },
  segBody: { padding: '12px 16px' },
  segMeaning: { fontSize: 12, color: '#555', marginBottom: 10, lineHeight: 1.5, background: '#f8fafc', padding: '8px 12px', borderRadius: 6 },
  segRaw: { fontFamily: 'monospace', fontSize: 11, color: '#888', background: '#fafafa', padding: '6px 10px', borderRadius: 4, marginBottom: 10, wordBreak: 'break-all' as const },

  // Element table
  elemTable: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 12 },
  elemTh: { background: '#f0f2f5', padding: '6px 10px', textAlign: 'left' as const, fontWeight: 700, color: '#555', fontSize: 11 },
  elemTd: { padding: '6px 10px', borderBottom: '1px solid #f5f5f5', verticalAlign: 'top' as const },
  elemTdError: { background: '#fff8f8' },
  elemId: { fontFamily: 'monospace', color: '#888', fontSize: 11 },
  elemVal: { fontFamily: 'monospace', fontWeight: 700, color: '#1F4E79' },
  elemValEmpty: { color: '#bbb', fontStyle: 'italic' },
  errorTag: { display: 'inline-block', background: '#c62828', color: '#fff', fontSize: 10, fontWeight: 700, borderRadius: 3, padding: '1px 5px', marginLeft: 6 },
  warnTag: { display: 'inline-block', background: '#f57c00', color: '#fff', fontSize: 10, fontWeight: 700, borderRadius: 3, padding: '1px 5px', marginLeft: 6 },
  fix: { color: '#2e7d32', fontSize: 11, marginTop: 4, fontStyle: 'italic' },

  // Issues panel
  issueCard: { background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 16, overflow: 'hidden' },
  issueTh: { background: '#1F4E79', color: '#fff', padding: '8px 12px', fontSize: 12, fontWeight: 700, textAlign: 'left' as const },
  issueTd: { padding: '8px 12px', borderBottom: '1px solid #f5f5f5', fontSize: 12, verticalAlign: 'top' as const },
}

/* ─── Types ──────────────────────────────────────────────────────────────── */
interface ElemDetail { element_id: string; position: number; description: string; value: string; errors: any[] }
interface SegDetail { segment_id: string; name: string; business_meaning: string; purpose: string; position: number; loop: string; raw: string; elements: ElemDetail[]; errors: any[]; warnings: any[]; has_error: boolean; has_warning: boolean }

/* ─── Helpers ────────────────────────────────────────────────────────────── */
function statusDot(seg: SegDetail) {
  if (seg.has_error) return '#ef5350'
  if (seg.has_warning) return '#ffa726'
  return '#66bb6a'
}

/* ─── Component ──────────────────────────────────────────────────────────── */
export default function ValidationPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [partner, setPartner] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')
  const [activeSegIdx, setActiveSegIdx] = useState<number | null>(null)
  const [filterErrors, setFilterErrors] = useState(false)

  const run = async () => {
    if (!file) return
    setLoading(true); setErr(''); setResult(null); setActiveSegIdx(null)
    try {
      const res = await validateEDI(file, partner)
      setResult(res.data)
    } catch (e: any) {
      setErr(e.response?.data?.detail || e.message)
    } finally { setLoading(false) }
  }

  const segments: SegDetail[] = result?.segments_detail || []
  const displaySegs = filterErrors ? segments.filter(s => s.has_error || s.has_warning) : segments
  const activeSeg = activeSegIdx !== null ? (segments[activeSegIdx] ?? null) : null

  // Auto-select a default segment once results load, so the Segment Details
  // panel is never left empty for a clean/valid file — previously it stayed
  // blank until the user manually clicked a row, which only naturally
  // happened for files with visibly flagged (red/amber) segments to
  // investigate. Prefer the first error, then first warning, else the
  // first segment (ISA).
  useEffect(() => {
    if (!segments.length) return
    const firstErrorIdx = segments.findIndex(s => s.has_error)
    const firstWarningIdx = segments.findIndex(s => s.has_warning)
    const defaultIdx = firstErrorIdx !== -1 ? firstErrorIdx : firstWarningIdx !== -1 ? firstWarningIdx : 0
    setActiveSegIdx(defaultIdx)
  }, [segments])

  const banner = !result ? null : result.status === 'PASS' ? s.bannerPass : result.status === 'WARNING' ? s.bannerWarning : s.bannerFail

  return (
    <div style={s.container}>
      <h1 style={s.title}>Validation Workspace</h1>

      {/* Upload form */}
      <div style={s.card}>
        <label style={s.label}>EDI File</label>
        <input type="file" accept=".edi,.txt,.x12,.835,.837,.278,.834,.820"
          onChange={e => setFile(e.target.files?.[0] || null)} style={s.input} />
        <label style={s.label}>Trading Partner Name (optional)</label>
        <input value={partner} onChange={e => setPartner(e.target.value)}
          placeholder="e.g. Aetna" style={s.input} />
        <button style={{ ...s.btn, ...(loading || !file ? s.btnDisabled : {}) }}
          disabled={loading || !file} onClick={run}>
          {loading ? 'Validating…' : 'Run Validation'}
        </button>
      </div>

      {err && <div style={s.bannerFail}>Error: {err}</div>}

      {result && (
        <>
          {/* Status banner */}
          <div style={banner!}>
            {result.status === 'PASS' ? '✓' : result.status === 'WARNING' ? '⚠' : '✗'}&nbsp;
            <strong>{result.status}</strong> — {result.error_count} error(s), {result.warning_count} warning(s)
            &nbsp;|&nbsp; Transaction: <strong>{result.transaction_type}</strong>
            &nbsp;|&nbsp; {result.segment_count} segments
          </div>

          {/* Parallel View: Raw EDI File + Segment Details */}
          {segments.length > 0 && (
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 12 }}>
                <h2 style={{ fontSize: 16, fontWeight: 700, color: '#333', margin: 0 }}>
                  EDI Validation Inspector
                </h2>
                <label style={{ fontSize: 13, display: 'flex', alignItems: 'center', gap: 6, cursor: 'pointer', color: '#555' }}>
                  <input type="checkbox" checked={filterErrors} onChange={e => setFilterErrors(e.target.checked)} />
                  Errors/warnings only
                </label>
                <span style={{ fontSize: 12, color: '#888', marginLeft: 'auto' }}>
                  {displaySegs.length} of {segments.length} segments
                </span>
              </div>

              <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, alignItems: 'start' }}>

                {/* LEFT: Raw EDI file view */}
                <div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', overflow: 'hidden' }}>
                  <div style={{ padding: '10px 16px', background: '#1F4E79', color: '#fff', fontSize: 12, fontWeight: 700, letterSpacing: 0.5 }}>
                    RAW EDI FILE
                  </div>
                  {/* Column header */}
                  <div style={{ display: 'flex', gap: 8, padding: '4px 12px 4px 16px', background: '#f0f4f8', borderBottom: '1px solid #dde4ed', fontSize: 10, color: '#888', fontWeight: 700, letterSpacing: 0.4 }}>
                    <div style={{ minWidth: 30, textAlign: 'right', flexShrink: 0 }}>#</div>
                    <div>SEGMENT</div>
                  </div>
                  <div style={{ maxHeight: '65vh', overflowY: 'auto' }}>
                    {displaySegs.map((seg) => {
                      const realIdx = segments.indexOf(seg)
                      const isSelected = activeSegIdx === realIdx
                      return (
                        <div
                          key={realIdx}
                          onClick={() => setActiveSegIdx(realIdx)}
                          style={{
                            display: 'flex',
                            gap: 8,
                            padding: '8px 12px',
                            borderBottom: '1px solid #f0f0f0',
                            borderLeft: `4px solid ${statusDot(seg)}`,
                            background: isSelected ? '#e3f0fa' : seg.has_error ? '#fff5f5' : seg.has_warning ? '#fffbf0' : '#fff',
                            cursor: 'pointer',
                            alignItems: 'flex-start',
                          }}
                        >
                          {/* Line number */}
                          <div style={{ minWidth: 30, textAlign: 'right', fontFamily: 'monospace', fontSize: 10, color: '#aaa', paddingTop: 2, flexShrink: 0, userSelect: 'none' as const }}>
                            {realIdx + 1}
                          </div>
                          {/* Segment content */}
                          <div style={{ flex: 1, minWidth: 0 }}>
                            {/* Raw segment text */}
                            <div style={{ fontFamily: 'monospace', fontSize: 11, color: seg.has_error ? '#b71c1c' : '#333', wordBreak: 'break-all' as const, lineHeight: 1.4 }}>
                              {seg.raw}
                            </div>
                            {/* Description row */}
                            <div style={{ display: 'flex', alignItems: 'center', gap: 6, marginTop: 5, flexWrap: 'wrap' as const }}>
                              <span style={{ fontFamily: 'monospace', fontWeight: 800, fontSize: 11, color: '#1F4E79' }}>{seg.segment_id}</span>
                              <span style={{ fontSize: 11, color: '#666' }}>—</span>
                              <span style={{ fontSize: 11, color: '#555' }}>{seg.name.split('—')[0].trim()}</span>
                              {seg.loop && (
                                <span style={{ fontSize: 10, background: '#f0f2f5', padding: '1px 5px', borderRadius: 3, color: '#777' }}>
                                  Loop {seg.loop}
                                </span>
                              )}
                              {seg.has_error && (
                                <span style={s.errorTag}>{seg.errors.length} ERROR{seg.errors.length !== 1 ? 'S' : ''}</span>
                              )}
                              {seg.has_warning && (
                                <span style={s.warnTag}>{seg.warnings.length} WARN</span>
                              )}
                            </div>
                          </div>
                        </div>
                      )
                    })}
                  </div>
                </div>

                {/* RIGHT: Segment details panel */}
                <div style={{ background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', overflow: 'hidden', position: 'sticky' as const, top: 16 }}>
                  <div style={{ padding: '10px 16px', background: '#1F4E79', color: '#fff', fontSize: 12, fontWeight: 700, letterSpacing: 0.5 }}>
                    {activeSeg ? `SEGMENT DETAILS — ${activeSeg.segment_id}` : 'SEGMENT DETAILS'}
                  </div>

                  {!activeSeg ? (
                    <div style={{ padding: 32, color: '#bbb', textAlign: 'center' as const, fontSize: 13 }}>
                      ← Click a segment on the left to view details
                    </div>
                  ) : (
                    <div style={{ padding: 16, maxHeight: '65vh', overflowY: 'auto' }}>
                      {/* Segment title */}
                      <div style={{ marginBottom: 12 }}>
                        <span style={{ fontSize: 17, fontWeight: 800, color: '#1F4E79', fontFamily: 'monospace' }}>{activeSeg.segment_id}</span>
                        <span style={{ fontSize: 13, color: '#444', marginLeft: 10, fontWeight: 600 }}>{activeSeg.name.split('—')[0].trim()}</span>
                        {activeSeg.purpose && <div style={{ fontSize: 11, color: '#888', marginTop: 4 }}>{activeSeg.purpose}</div>}
                      </div>

                      {/* Business meaning */}
                      {activeSeg.business_meaning && (
                        <div style={{ ...s.segMeaning, marginBottom: 12 }}>
                          <strong style={{ color: '#1F4E79' }}>Business Meaning:</strong> {activeSeg.business_meaning}
                        </div>
                      )}

                      {/* Raw segment */}
                      <div style={{ ...s.segRaw, marginBottom: 12 }}>
                        <strong>Raw:</strong> {activeSeg.raw}
                      </div>

                      {/* Errors */}
                      {activeSeg.has_error && activeSeg.errors.map((e: any, ei: number) => (
                        <div key={ei} style={{ background: '#ffebee', border: '1px solid #ef9a9a', borderRadius: 6, padding: '10px 14px', marginBottom: 10, fontSize: 12 }}>
                          <strong style={{ color: '#c62828' }}>✗ ERROR</strong>
                          {e.element && <span style={{ fontFamily: 'monospace', fontSize: 11, marginLeft: 6, background: '#fce4ec', padding: '1px 5px', borderRadius: 3 }}>{e.element}</span>}
                          <div style={{ marginTop: 6, color: '#333', lineHeight: 1.5 }}>{e.description}</div>
                          {e.suggested_correction && (
                            <div style={{ marginTop: 6, fontSize: 12, background: '#e8f5e9', padding: '6px 10px', borderRadius: 4, border: '1px solid #a5d6a7', color: '#1b5e20' }}>
                              <strong>Suggested Fix:</strong> {e.suggested_correction}
                            </div>
                          )}
                        </div>
                      ))}

                      {/* Warnings */}
                      {activeSeg.has_warning && activeSeg.warnings.map((w: any, wi: number) => (
                        <div key={wi} style={{ background: '#fff8e1', border: '1px solid #ffe082', borderRadius: 6, padding: '10px 14px', marginBottom: 10, fontSize: 12 }}>
                          <strong style={{ color: '#f57c00' }}>⚠ WARNING</strong>
                          {w.element && <span style={{ fontFamily: 'monospace', fontSize: 11, marginLeft: 6, background: '#fff3cd', padding: '1px 5px', borderRadius: 3 }}>{w.element}</span>}
                          <div style={{ marginTop: 6, color: '#333', lineHeight: 1.5 }}>{w.description}</div>
                          {w.suggested_correction && (
                            <div style={{ marginTop: 6, fontSize: 12, background: '#e8f5e9', padding: '6px 10px', borderRadius: 4, border: '1px solid #a5d6a7', color: '#1b5e20' }}>
                              <strong>Suggested Fix:</strong> {w.suggested_correction}
                            </div>
                          )}
                        </div>
                      ))}

                      {/* OK state */}
                      {!activeSeg.has_error && !activeSeg.has_warning && (
                        <div style={{ background: '#e8f5e9', border: '1px solid #a5d6a7', borderRadius: 6, padding: '10px 14px', marginBottom: 12, fontSize: 12, color: '#1b5e20', fontWeight: 600 }}>
                          ✓ No issues found in this segment
                        </div>
                      )}

                      {/* Element breakdown */}
                      {activeSeg.elements.length > 0 && (
                        <>
                          <div style={{ fontSize: 12, fontWeight: 700, color: '#555', marginBottom: 8, marginTop: 4 }}>Element Breakdown</div>
                          <table style={s.elemTable}>
                            <thead>
                              <tr>
                                {['#', 'Element ID', 'Description', 'Value'].map(h => (
                                  <th key={h} style={s.elemTh}>{h}</th>
                                ))}
                              </tr>
                            </thead>
                            <tbody>
                              {activeSeg.elements.map((elem: ElemDetail) => {
                                const hasErr = elem.errors.length > 0
                                return (
                                  <tr key={elem.element_id} style={hasErr ? { background: '#fff5f5' } : {}}>
                                    <td style={{ ...s.elemTd, ...s.elemId, width: 30 }}>{elem.position}</td>
                                    <td style={{ ...s.elemTd, ...s.elemId, width: 80 }}>{elem.element_id}</td>
                                    <td style={{ ...s.elemTd, color: '#555' }}>
                                      {elem.description}
                                      {hasErr && <span style={s.errorTag}>ERR</span>}
                                    </td>
                                    <td style={s.elemTd}>
                                      {elem.value
                                        ? <span style={{ ...s.elemVal, color: hasErr ? '#c62828' : '#1F4E79' }}>{elem.value}</span>
                                        : <span style={s.elemValEmpty}>(empty)</span>
                                      }
                                    </td>
                                  </tr>
                                )
                              })}
                            </tbody>
                          </table>
                        </>
                      )}
                    </div>
                  )}
                </div>

              </div>
            </div>
          )}
        </>
      )}

      {/* AI Assist Bar — always visible, shows contextual data when results are loaded */}
      <AIAssistBar
        tabName="Validation"
        sources={file ? [file] : []}
        context={JSON.stringify({ file: file?.name, partner, deterministic_result: result, error: err })}
        actions={VALIDATION_AI_ACTIONS}
      />
    </div>
  )
}
