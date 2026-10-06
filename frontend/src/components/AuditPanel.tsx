import React, { useEffect, useState } from 'react'
import { getAuditLog } from '../api'
import AIAssistBar from './AIAssistBar'

const s: Record<string, React.CSSProperties> = {
  container: { padding: 24 },
  title: { fontSize: 20, fontWeight: 700, marginBottom: 20, color: '#1F4E79' },
  card: { background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 16 },
  label: { fontWeight: 600, color: '#444', fontSize: 14, marginRight: 8 },
  input: { padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, marginRight: 8 },
  btn: { padding: '8px 20px', background: '#1F4E79', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: { background: '#1F4E79', color: '#fff', padding: '8px 12px', textAlign: 'left' },
  td: { padding: '8px 12px', borderBottom: '1px solid #f0f2f5' },
  badge: { padding: '2px 10px', borderRadius: 12, fontWeight: 600, fontSize: 12 },
}

export default function AuditPanel() {
  const [date, setDate] = useState(new Date().toISOString().slice(0, 10))
  const [entries, setEntries] = useState<any[]>([])
  const [loading, setLoading] = useState(false)
  const [loadedDate, setLoadedDate] = useState<string | null>(null)
  const [error, setError] = useState('')

  const load = async () => {
    setLoading(true)
    setError('')
    try {
      const res = await getAuditLog(date)
      setEntries(res.data.entries)
      setLoadedDate(date)
    } catch { setError('Audit log could not be loaded. Previously loaded entries are retained.') }
    setLoading(false)
  }

  useEffect(() => { load() }, [])

  return (
    <div style={s.container}>
      <h1 style={s.title}>Audit Trail</h1>
      {error && <p role="alert">{error}</p>}

      <div style={s.card}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 16 }}>
          <label style={s.label}>Date:</label>
          <input type="date" value={date}
            onChange={e => setDate(e.target.value)} style={s.input} />
          <button onClick={load} style={s.btn} disabled={loading}>
            {loading ? 'Loading…' : 'Load Log'}
          </button>
          <span style={{ marginLeft: 16, color: '#666', fontSize: 13 }}>
            {entries.length} entries
          </span>
        </div>

        {entries.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={s.table}>
              <thead><tr>
                {['Timestamp', 'User', 'Action', 'Module', 'Input', 'Result', 'AI Used'].map(h => (
                  <th key={h} style={s.th}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {entries.map((e: any, i: number) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? '#fafafa' : '#fff' }}>
                    <td style={s.td}>{new Date(e.timestamp).toLocaleTimeString()}</td>
                    <td style={s.td}>{e.user}</td>
                    <td style={s.td}><strong>{e.action}</strong></td>
                    <td style={s.td}>{e.module}</td>
                    <td style={{ ...s.td, maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis' }}>
                      {e.input_summary}
                    </td>
                    <td style={s.td}>{e.result}</td>
                    <td style={s.td}>
                      <span style={{
                        ...s.badge,
                        background: e.ai_used ? '#fff8e1' : '#e8f5e9',
                        color: e.ai_used ? '#f57c00' : '#2e7d32',
                      }}>
                        {e.ai_used ? 'AI Used' : 'Deterministic'}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <p style={{ color: '#888', fontSize: 13 }}>No audit entries loaded{loadedDate ? ` for ${loadedDate}` : ''}.</p>
        )}
      </div>
      <AIAssistBar tabName="Audit Trail" context={JSON.stringify({ selectedDate: date, loadedDate, entries, error })}
        actions={[{ label: 'Review audit log', icon: '◎', description: 'Review the full loaded log with explicit consent', promptHint: 'Review these audit entries and summarize activity, approvals and issues with evidence. Distinguish empty logs from load errors.' }]} />
    </div>
  )
}
