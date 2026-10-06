import React, { useEffect, useState } from 'react'
import axios from 'axios'
import AIAssistBar from './AIAssistBar'

interface DashboardStats {
  total: number
  pass: number
  fail: number
  warnings: number
}

const styles: Record<string, React.CSSProperties> = {
  container: { padding: 24 },
  title: { fontSize: 24, fontWeight: 700, marginBottom: 24, color: '#1F4E79' },
  grid: { display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: 16, marginBottom: 32 },
  card: { background: '#fff', borderRadius: 8, padding: 20, boxShadow: '0 1px 4px rgba(0,0,0,0.1)' },
  cardLabel: { fontSize: 13, color: '#666', marginBottom: 8 },
  cardValue: { fontSize: 32, fontWeight: 700 },
  health: { display: 'inline-block', padding: '4px 12px', borderRadius: 12, fontSize: 13 },
}

export default function Dashboard() {
  const [stats] = useState<DashboardStats>({ total: 0, pass: 0, fail: 0, warnings: 0 })
  const [health, setHealth] = useState<'healthy' | 'error' | 'checking'>('checking')

  useEffect(() => {
    axios.get('/health').then(() => setHealth('healthy')).catch(() => setHealth('error'))
  }, [])

  const cards = [
    { label: 'Total Files Processed', value: stats.total, color: '#1F4E79' },
    { label: 'Pass', value: stats.pass, color: '#2e7d32' },
    { label: 'Fail', value: stats.fail, color: '#c62828' },
    { label: 'Warnings', value: stats.warnings, color: '#f57c00' },
  ]

  return (
    <div style={styles.container}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 16, marginBottom: 24 }}>
        <h1 style={styles.title}>EDI Accelerator Platform</h1>
        <span style={{
          ...styles.health,
          background: health === 'healthy' ? '#e8f5e9' : health === 'error' ? '#ffebee' : '#fff8e1',
          color: health === 'healthy' ? '#2e7d32' : health === 'error' ? '#c62828' : '#f57c00',
        }}>
          {health === 'healthy' ? '● Backend Online' : health === 'error' ? '● Backend Offline' : '● Checking...'}
        </span>
      </div>

      <div style={styles.grid}>
        {cards.map(c => (
          <div key={c.label} style={styles.card}>
            <div style={styles.cardLabel}>{c.label}</div>
            <div style={{ ...styles.cardValue, color: c.color }}>{c.value}</div>
          </div>
        ))}
      </div>

      <div style={{ background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.1)' }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 16, color: '#333' }}>Supported Transactions</h2>
        <div style={{ display: 'flex', gap: 12, flexWrap: 'wrap' }}>
          {['837P', '837I', '278', '834', '820', '999', '277CA'].map(t => (
            <span key={t} style={{
              padding: '6px 16px', background: '#e3f0fa', color: '#1F4E79',
              borderRadius: 20, fontWeight: 600, fontSize: 13,
            }}>{t}</span>
          ))}
        </div>
      </div>

      <div style={{ marginTop: 24, background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.1)' }}>
        <h2 style={{ fontSize: 16, fontWeight: 600, marginBottom: 12, color: '#333' }}>Platform Capabilities</h2>
        <ul style={{ listStyle: 'none', display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: 8 }}>
          {[
            'EDI Generation (837P, 837I, 278)',
            'EDI Parsing (all transaction types)',
            'HIPAA + Companion Guide Validation',
            'File-to-File Comparison',
            'Auto Correction (user approval required)',
            '999 Acknowledgment Analysis',
            '277CA Claim Status Analysis',
            'Excel Export (full template)',
            'Batch Processing',
            'Audit Trail',
            'Trading Partner Mapping',
            'AI Assistance (Gemini external API — explicit consent)',
          ].map(cap => (
            <li key={cap} style={{ padding: '6px 0', borderBottom: '1px solid #f0f2f5', color: '#444', fontSize: 14 }}>
              ✓ {cap}
            </li>
          ))}
        </ul>
      </div>
      <AIAssistBar tabName="Dashboard"
        context={JSON.stringify({ stats, health, stats_note: 'These dashboard counters are initialized to zero, not populated from a live statistics API.', supported_transactions: ['837P', '837I', '278', '834', '820', '999', '277CA'] })}
        actions={[{ label: 'Explain dashboard', icon: '◎', description: 'Review the current dashboard snapshot', promptHint: 'Explain this dashboard snapshot, distinguish placeholders from measured data, and identify limitations.' }]} />
    </div>
  )
}
