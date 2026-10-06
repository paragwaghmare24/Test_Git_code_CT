import React, { useState } from 'react'
import { analyze999, analyze277ca } from '../api'
import AIAssistBar, { AITabAction } from './AIAssistBar'

const RESPONSE_AI_ACTIONS: AITabAction[] = [
  { label: 'Explain Rejection', icon: '🔍', description: 'Explain rejection reasons in plain English', promptHint: 'Explain these EDI rejection codes:' },
  { label: 'Suggest Fixes', icon: '✎', description: 'Suggest potential fixes for rejected transactions', promptHint: 'Suggest fixes for these rejection reasons:' },
  { label: 'Business Summary', icon: '⊞', description: 'Convert technical response to business-friendly language', promptHint: 'Convert this technical EDI response to business language:' },
]

const s: Record<string, React.CSSProperties> = {
  container: { padding: 24 },
  title: { fontSize: 20, fontWeight: 700, marginBottom: 20, color: '#1F4E79' },
  card: { background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 16 },
  tabs: { display: 'flex', gap: 8, marginBottom: 20 },
  tab: { padding: '8px 20px', borderRadius: 6, border: '1px solid #ddd', cursor: 'pointer', fontWeight: 600, fontSize: 14 },
  label: { display: 'block', marginBottom: 8, fontWeight: 600, color: '#444', fontSize: 14 },
  input: { width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, marginBottom: 12 },
  btn: { padding: '10px 28px', background: '#1F4E79', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: { background: '#1F4E79', color: '#fff', padding: '8px 12px', textAlign: 'left' },
  td: { padding: '8px 12px', borderBottom: '1px solid #f0f2f5' },
  accepted: { color: '#2e7d32', background: '#e8f5e9', padding: '10px 14px', borderRadius: 6, fontWeight: 700 },
  rejected: { color: '#c62828', background: '#ffebee', padding: '10px 14px', borderRadius: 6, fontWeight: 700 },
  error: { color: '#c62828', background: '#ffebee', padding: '10px 14px', borderRadius: 6, marginBottom: 8, fontSize: 13 },
}

export default function ResponsePanel() {
  const [mode, setMode] = useState<'999' | '277CA'>('999')
  const [file, setFile] = useState<File | null>(null)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')

  const run = async () => {
    if (!file) return
    setLoading(true); setErr(''); setResult(null)
    try {
      const res = mode === '999' ? await analyze999(file) : await analyze277ca(file)
      setResult(res.data)
    } catch (e: any) {
      setErr(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div style={s.container}>
      <h1 style={s.title}>Response Analysis</h1>

      <div style={s.tabs}>
        {(['999', '277CA'] as const).map(m => (
          <button key={m} style={{
            ...s.tab,
            background: mode === m ? '#1F4E79' : '#fff',
            color: mode === m ? '#fff' : '#333',
          }} onClick={() => { setMode(m); setResult(null); setFile(null) }}>
            {m} Analysis
          </button>
        ))}
      </div>

      <div style={s.card}>
        <label style={s.label}>{mode} File</label>
        <input type="file" accept=".edi,.txt,.x12"
          onChange={e => setFile(e.target.files?.[0] || null)} style={s.input} />
        <button style={{ ...s.btn, opacity: !file ? 0.6 : 1 }}
          disabled={!file || loading} onClick={run}>
          {loading ? 'Analyzing…' : `Analyze ${mode}`}
        </button>
      </div>

      {err && <div style={s.error}>Error: {err}</div>}

      {result && mode === '999' && (
        <div style={s.card}>
          <div style={result.overall_status === 'Accepted' ? s.accepted : s.rejected}>
            Overall Status: {result.overall_status}
          </div>

          {result.transaction_analyses?.map((a: any, i: number) => (
            <div key={i} style={{ marginTop: 16, padding: 16, border: '1px solid #eee', borderRadius: 8 }}>
              <strong>Transaction Set: {a.transaction_set_id}</strong>
              <p style={{ color: '#555', marginTop: 4 }}>{a.human_readable_summary}</p>
              {a.errors?.length > 0 && (
                <table style={{ ...s.table, marginTop: 12 }}>
                  <thead><tr>
                    {['Segment', 'Element', 'Description', 'Rule Ref'].map(h => (
                      <th key={h} style={s.th}>{h}</th>
                    ))}
                  </tr></thead>
                  <tbody>
                    {a.errors.map((e: any, j: number) => (
                      <tr key={j}><td style={s.td}>{e.segment}</td><td style={s.td}>{e.element}</td>
                        <td style={s.td}>{e.description}</td><td style={s.td}>{e.rule_reference}</td></tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          ))}
        </div>
      )}

      {result && mode === '277CA' && (
        <div style={s.card}>
          <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12 }}>
            Claim Status ({result.claim_analyses?.length} claims)
          </h2>
          <table style={s.table}>
            <thead><tr>
              {['Claim #', 'Member ID', 'Provider NPI', 'Status', 'Summary'].map(h => (
                <th key={h} style={s.th}>{h}</th>
              ))}
            </tr></thead>
            <tbody>
              {result.claim_analyses?.map((c: any, i: number) => (
                <tr key={i} style={{ background: i % 2 === 0 ? '#fafafa' : '#fff' }}>
                  <td style={s.td}>{c.claim_number}</td>
                  <td style={s.td}>{c.member_id}</td>
                  <td style={s.td}>{c.provider_npi}</td>
                  <td style={s.td}>{c.status}</td>
                  <td style={s.td}>{c.human_readable_summary}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* AI Assist Bar */}
      <AIAssistBar
        tabName={`${mode} Analysis`}
        sources={file ? [file] : []}
        context={JSON.stringify({ file: file?.name, mode, deterministic_result: result, error: err })}
        actions={RESPONSE_AI_ACTIONS}
      />
    </div>
  )
}
