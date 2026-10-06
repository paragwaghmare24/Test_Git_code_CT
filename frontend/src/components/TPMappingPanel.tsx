import React, { useState } from 'react'
import { uploadTPMapping, listTPMappings } from '../api'
import AIAssistBar, { AITabAction } from './AIAssistBar'

const TP_AI_ACTIONS: AITabAction[] = [
  { label: 'Verify Mapping', icon: '⊟', description: 'Verify the trading partner mapping configuration is correct', promptHint: 'Verify this trading partner mapping:' },
  { label: 'Find Gaps', icon: '🔍', description: 'Identify missing or incomplete mapping entries', promptHint: 'Identify mapping gaps in:' },
  { label: 'Suggest Additions', icon: '✎', description: 'Suggest additional mapping rules based on current mappings', promptHint: 'Suggest additional mapping rules for:' },
]

const s: Record<string, React.CSSProperties> = {
  container: { padding: 24 },
  title: { fontSize: 20, fontWeight: 700, marginBottom: 20, color: '#1F4E79' },
  card: { background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 16 },
  label: { display: 'block', marginBottom: 6, fontWeight: 600, color: '#444', fontSize: 14 },
  input: { width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, marginBottom: 12 },
  select: { width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, marginBottom: 12 },
  btn: { padding: '10px 28px', background: '#1F4E79', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 },
  btnSecondary: { padding: '10px 20px', background: '#f5f5f5', color: '#333', border: '1px solid #ddd', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14, marginLeft: 8 },
  success: { color: '#2e7d32', background: '#e8f5e9', padding: '10px 14px', borderRadius: 6, marginBottom: 8 },
  error: { color: '#c62828', background: '#ffebee', padding: '10px 14px', borderRadius: 6, marginBottom: 8 },
  info: { background: '#e3f0fa', borderRadius: 8, padding: '12px 16px', fontSize: 13, color: '#1F4E79', marginBottom: 16 },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: { background: '#1F4E79', color: '#fff', padding: '8px 12px', textAlign: 'left' },
  td: { padding: '8px 12px', borderBottom: '1px solid #f0f2f5' },
}

export default function TPMappingPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [partnerName, setPartnerName] = useState('')
  const [txType, setTxType] = useState('837P')
  const [loading, setLoading] = useState(false)
  const [success, setSuccess] = useState('')
  const [err, setErr] = useState('')
  const [mappings, setMappings] = useState<any[]>([])
  const [showMappings, setShowMappings] = useState(false)

  const upload = async () => {
    if (!file || !partnerName) return
    setLoading(true); setErr(''); setSuccess('')
    try {
      const res = await uploadTPMapping(file, partnerName, txType)
      setSuccess(`${res.data.message} ${res.data.entry_count} entries loaded.`)
    } catch (e: any) {
      setErr(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  const loadMappings = async () => {
    const res = await listTPMappings()
    setMappings(res.data.mappings)
    setShowMappings(true)
  }

  return (
    <div style={s.container}>
      <h1 style={s.title}>Trading Partner Mapping</h1>

      <div style={s.info}>
        Upload TP mapping files (JSON or CSV) to override standard Companion Guide rules for a specific trading partner.
        TP mappings apply during generation, validation, comparison, and export.
      </div>

      <div style={s.card}>
        <label style={s.label}>Mapping File (JSON or CSV)</label>
        <input type="file" accept=".json,.csv"
          onChange={e => setFile(e.target.files?.[0] || null)} style={s.input} />
        <label style={s.label}>Trading Partner Name</label>
        <input value={partnerName} onChange={e => setPartnerName(e.target.value)}
          placeholder="e.g. Aetna, BlueCross, United" style={s.input} />
        <label style={s.label}>Transaction Type</label>
        <select value={txType} onChange={e => setTxType(e.target.value)} style={s.select}>
          {['837P', '837I', '278', '834', '820', '999', '277CA'].map(t => (
            <option key={t}>{t}</option>
          ))}
        </select>
        <button style={{ ...s.btn, opacity: (!file || !partnerName) ? 0.6 : 1 }}
          disabled={!file || !partnerName || loading} onClick={upload}>
          {loading ? 'Uploading…' : 'Upload TP Mapping'}
        </button>
        <button style={s.btnSecondary} onClick={loadMappings}>
          View Loaded Mappings
        </button>
      </div>

      {err && <div style={s.error}>Error: {err}</div>}
      {success && <div style={s.success}>✓ {success}</div>}

      {showMappings && (
        <div style={s.card}>
          <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>Loaded Mappings</h2>
          {mappings.length === 0 ? (
            <p style={{ color: '#888', fontSize: 13 }}>No mappings loaded yet.</p>
          ) : (
            <table style={s.table}>
              <thead><tr>
                {['Partner', 'Transaction', 'Version', 'Entries', 'Source File'].map(h => (
                  <th key={h} style={s.th}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {mappings.map((m: any, i: number) => (
                  <tr key={i}>
                    <td style={s.td}><strong>{m.partner_name}</strong></td>
                    <td style={s.td}>{m.transaction_type}</td>
                    <td style={s.td}>{m.version || '—'}</td>
                    <td style={s.td}>{m.entry_count}</td>
                    <td style={s.td}>{m.source_file}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </div>
      )}

      {/* AI Assist Bar */}
      <AIAssistBar
        tabName="TP Mapping"
        sources={file ? [file] : []}
        context={JSON.stringify({ file: file?.name, partnerName, txType, mappings, success, error: err })}
        actions={TP_AI_ACTIONS}
      />
    </div>
  )
}
