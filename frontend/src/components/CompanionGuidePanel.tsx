import React, { useEffect, useState } from 'react'
import { listCompanionGuides, getGuideRules, searchGuideRules } from '../api'
import AIAssistBar, { AITabAction } from './AIAssistBar'

const GUIDE_AI_ACTIONS: AITabAction[] = [
  { label: 'Interpret Rule', icon: '⊞', description: 'Explain a companion guide rule in plain English with examples', promptHint: 'Interpret this companion guide rule:' },
  { label: 'Check Compliance', icon: '✓', description: 'Check if a transaction meets the loaded guide requirements', promptHint: 'Check compliance with companion guide rules:' },
  { label: 'Explain Requirement', icon: '🔍', description: 'Explain what a mandatory requirement means for EDI creation', promptHint: 'Explain this companion guide requirement:' },
]

const s: Record<string, React.CSSProperties> = {
  container: { padding: 24 },
  title: { fontSize: 20, fontWeight: 700, marginBottom: 20, color: '#1F4E79' },
  card: { background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 16 },
  label: { display: 'block', marginBottom: 8, fontWeight: 600, color: '#444', fontSize: 14 },
  input: { padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, marginRight: 8, minWidth: 260 },
  select: { padding: '8px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, marginRight: 8 },
  btn: { padding: '8px 20px', background: '#1F4E79', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 },
  badge: { padding: '3px 10px', borderRadius: 12, fontSize: 12, fontWeight: 600 },
  table: { width: '100%', borderCollapse: 'collapse', fontSize: 13 },
  th: { background: '#1F4E79', color: '#fff', padding: '8px 12px', textAlign: 'left' },
  td: { padding: '8px 12px', borderBottom: '1px solid #f0f2f5', verticalAlign: 'top' },
  guideCard: {
    padding: '12px 16px', borderRadius: 8, border: '1px solid #ddd', display: 'flex',
    justifyContent: 'space-between', alignItems: 'center', marginBottom: 8, background: '#fafafa',
  },
}

export default function CompanionGuidePanel() {
  const [guides, setGuides] = useState<any[]>([])
  const [selectedType, setSelectedType] = useState('')
  const [query, setQuery] = useState('')
  const [rules, setRules] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    listCompanionGuides().then(r => setGuides(r.data.guides))
  }, [])

  const loadRules = async () => {
    if (!selectedType) return
    setLoading(true)
    try {
      if (query.trim()) {
        const r = await searchGuideRules(selectedType, query)
        setRules(r.data.results)
      } else {
        const r = await getGuideRules(selectedType)
        setRules(r.data.rules || [])
      }
    } catch { setRules([]) }
    setLoading(false)
  }

  return (
    <div style={s.container}>
      <h1 style={s.title}>Companion Guide Workspace</h1>

      {/* AI Assist Bar */}
      <AIAssistBar
        tabName="Companion Guide"
        context={JSON.stringify({ selectedType, query, rules, guides, source_note: 'Configured companion guide source texts are available through server tools. Loaded rules may be search-filtered; consult source texts and report coverage.' })}
        actions={GUIDE_AI_ACTIONS}
      />

      <div style={s.card}>
        <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12, color: '#333' }}>Available Guides</h2>
        {guides.map((g: any) => (
          <div key={g.transaction_type} style={s.guideCard}>
            <div>
              <strong>{g.transaction_type}</strong>
              <span style={{ marginLeft: 8, color: '#666', fontSize: 13 }}>{g.file_name}</span>
            </div>
            <div>
              <span style={{
                ...s.badge,
                background: g.available ? '#e8f5e9' : '#ffebee',
                color: g.available ? '#2e7d32' : '#c62828',
              }}>
                {g.available ? '● Available' : '● Missing'}
              </span>
              {g.cached && (
                <span style={{ ...s.badge, background: '#e3f0fa', color: '#1F4E79', marginLeft: 8 }}>
                  Cached ({g.rule_count} rules)
                </span>
              )}
            </div>
          </div>
        ))}
      </div>

      <div style={s.card}>
        <h2 style={{ fontSize: 15, fontWeight: 700, marginBottom: 12, color: '#333' }}>Browse / Search Rules</h2>
        <div style={{ display: 'flex', alignItems: 'center', flexWrap: 'wrap', gap: 8, marginBottom: 12 }}>
          <select value={selectedType} onChange={e => setSelectedType(e.target.value)} style={s.select}>
            <option value="">Select Transaction</option>
            {['837P', '837I', '278', '834', '820', '999', '277CA'].map(t => (
              <option key={t}>{t}</option>
            ))}
          </select>
          <input value={query} onChange={e => setQuery(e.target.value)}
            placeholder="Search keyword (optional)" style={s.input} />
          <button onClick={loadRules} disabled={!selectedType || loading} style={s.btn}>
            {loading ? 'Loading…' : 'Load Rules'}
          </button>
        </div>

        {rules.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={s.table}>
              <thead><tr>
                {['Segment', 'Element', 'Loop', 'Mandatory', 'Rule Text'].map(h => (
                  <th key={h} style={s.th}>{h}</th>
                ))}
              </tr></thead>
              <tbody>
                {rules.map((r: any, i: number) => (
                  <tr key={i} style={{ background: i % 2 === 0 ? '#fafafa' : '#fff' }}>
                    <td style={s.td}><strong>{r.segment}</strong></td>
                    <td style={s.td}>{r.element}</td>
                    <td style={s.td}>{r.loop}</td>
                    <td style={s.td}>
                      <span style={{
                        ...s.badge,
                        background: r.mandatory ? '#ffebee' : '#e8f5e9',
                        color: r.mandatory ? '#c62828' : '#2e7d32',
                      }}>
                        {r.mandatory ? 'Mandatory' : 'Optional'}
                      </span>
                    </td>
                    <td style={s.td}>{r.rule_text}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : selectedType && !loading && (
          <p style={{ color: '#888', fontSize: 13 }}>
            No rules loaded. Click "Load Rules" to extract rules from the guide.
          </p>
        )}
      </div>
    </div>
  )
}
