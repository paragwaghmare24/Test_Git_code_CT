import React, { useState } from 'react'
import { exportExcel, downloadExport } from '../api'
import AIAssistBar, { AITabAction } from './AIAssistBar'

const EXPORT_AI_ACTIONS: AITabAction[] = [
  { label: 'Explain Export Data', icon: '🔍', description: 'Explain the exported claim data in plain English', promptHint: 'Explain this EDI export result:' },
  { label: 'Verify Completeness', icon: '✓', description: 'Check if all required claim fields are populated', promptHint: 'Verify completeness of this export:' },
  { label: 'Identify Issues', icon: '◎', description: 'Identify any data quality issues in the export', promptHint: 'Identify data quality issues in:' },
]

const s: Record<string, React.CSSProperties> = {
  container: { padding: 24 },
  title: { fontSize: 20, fontWeight: 700, marginBottom: 20, color: '#1F4E79' },
  card: { background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 16 },
  label: { display: 'block', marginBottom: 8, fontWeight: 600, color: '#444', fontSize: 14 },
  input: { width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, marginBottom: 12 },
  btn: { padding: '10px 28px', background: '#1F4E79', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 },
  btnGreen: { background: '#2e7d32' },
  error: { color: '#c62828', background: '#ffebee', padding: '10px 14px', borderRadius: 6, marginBottom: 8, fontSize: 13 },
  success: { color: '#2e7d32', background: '#e8f5e9', padding: '10px 14px', borderRadius: 6, marginBottom: 8, fontSize: 13 },
  checkbox: { marginRight: 8 },
}

export default function ExportPanel() {
  const [file, setFile] = useState<File | null>(null)
  const [partner, setPartner] = useState('')
  const [runValidation, setRunValidation] = useState(true)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<any>(null)
  const [err, setErr] = useState('')

  const run = async () => {
    if (!file) return
    setLoading(true); setErr(''); setResult(null)
    try {
      const res = await exportExcel(file, partner, runValidation)
      setResult(res.data)
    } catch (e: any) {
      setErr(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  const download = async () => {
    if (!result?.file_name) return
    try {
      const res = await downloadExport(result.file_name)
      const url = URL.createObjectURL(new Blob([res.data]))
      const a = document.createElement('a')
      a.href = url; a.download = result.file_name; a.click()
      URL.revokeObjectURL(url)
    } catch {
      setErr('Download failed.')
    }
  }

  return (
    <div style={s.container}>
      <h1 style={s.title}>Excel Export</h1>

      <div style={s.card}>
        <label style={s.label}>EDI File</label>
        <input type="file" accept=".edi,.txt,.x12"
          onChange={e => setFile(e.target.files?.[0] || null)} style={s.input} />
        <label style={s.label}>Trading Partner (optional)</label>
        <input value={partner} onChange={e => setPartner(e.target.value)}
          placeholder="e.g. Aetna" style={s.input} />
        <label style={{ ...s.label, display: 'flex', alignItems: 'center', cursor: 'pointer' }}>
          <input type="checkbox" checked={runValidation}
            onChange={e => setRunValidation(e.target.checked)} style={s.checkbox} />
          Include Validation Results in Export
        </label>
        <button style={{ ...s.btn, marginTop: 8, opacity: !file ? 0.6 : 1 }}
          disabled={!file || loading} onClick={run}>
          {loading ? 'Exporting…' : 'Export to Excel'}
        </button>
      </div>

      {err && <div style={s.error}>Error: {err}</div>}

      {result && (
        <div style={s.card}>
          <div style={s.success}>
            ✓ Export complete: <strong>{result.file_name}</strong>
          </div>
          <button style={{ ...s.btn, ...s.btnGreen, marginTop: 12 }} onClick={download}>
            Download Excel File
          </button>
          <p style={{ marginTop: 8, fontSize: 13, color: '#666' }}>
            Template includes: Master Output, Validation Report, Error details per ExcelTemplateSchema.
          </p>
        </div>
      )}

      {/* AI Assist Bar */}
      <AIAssistBar
        tabName="Excel Export"
        sources={file ? [file] : []}
        context={JSON.stringify({ file: file?.name, partner, runValidation, deterministic_result: result, error: err })}
        actions={EXPORT_AI_ACTIONS}
      />
    </div>
  )
}
