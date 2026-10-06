import React, { useState } from 'react'
import Dashboard from './components/Dashboard'
import ValidationPanel from './components/ValidationPanel'
import GeneratePanel from './components/GeneratePanel'
import ComparisonPanel from './components/ComparisonPanel'
import ResponsePanel from './components/ResponsePanel'
import ExportPanel from './components/ExportPanel'
import CompanionGuidePanel from './components/CompanionGuidePanel'
import TPMappingPanel from './components/TPMappingPanel'
import AuditPanel from './components/AuditPanel'
import AIPanel from './components/AIPanel'

type Page =
  | 'dashboard'
  | 'generate'
  | 'validate'
  | 'compare'
  | 'response'
  | 'export'
  | 'companion'
  | 'tpmapping'
  | 'audit'
  | 'ai'

const NAV_ITEMS: { id: Page; label: string; icon: string }[] = [
  { id: 'dashboard', label: 'Dashboard', icon: '◉' },
  { id: 'generate', label: 'Generate EDI', icon: '⊕' },
  { id: 'validate', label: 'Validate', icon: '✓' },
  { id: 'compare', label: 'Compare', icon: '⇄' },
  { id: 'response', label: '999 / 277CA', icon: '↩' },
  { id: 'export', label: 'Excel Export', icon: '↗' },
  { id: 'companion', label: 'Companion Guides', icon: '⊞' },
  { id: 'tpmapping', label: 'TP Mapping', icon: '⊟' },
  { id: 'audit', label: 'Audit Trail', icon: '▤' },
  { id: 'ai', label: 'AI Assistance', icon: '✦' },
]

const SIDEBAR_WIDTH = 220

const styles: Record<string, React.CSSProperties> = {
  root: { display: 'flex', height: '100vh', overflow: 'hidden', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  sidebar: {
    width: SIDEBAR_WIDTH,
    background: '#1F4E79',
    display: 'flex',
    flexDirection: 'column',
    flexShrink: 0,
    overflowY: 'auto',
  },
  brand: {
    padding: '20px 16px 12px',
    color: '#fff',
    fontSize: 14,
    fontWeight: 800,
    letterSpacing: 0.5,
    borderBottom: '1px solid rgba(255,255,255,0.1)',
    lineHeight: 1.4,
  },
  brandSub: { fontSize: 11, fontWeight: 400, color: 'rgba(255,255,255,0.6)', marginTop: 2 },
  nav: { padding: '12px 0', flex: 1 },
  navItem: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '10px 16px',
    color: 'rgba(255,255,255,0.8)',
    cursor: 'pointer',
    fontSize: 13,
    fontWeight: 500,
    borderLeft: '3px solid transparent',
    transition: 'all 0.15s',
  },
  navItemActive: {
    background: 'rgba(255,255,255,0.15)',
    color: '#fff',
    borderLeft: '3px solid #fff',
    fontWeight: 700,
  },
  navIcon: { fontSize: 16, width: 20, textAlign: 'center' },
  content: {
    flex: 1,
    overflowY: 'auto',
    background: '#f0f2f5',
  },
  footer: {
    padding: '12px 16px',
    borderTop: '1px solid rgba(255,255,255,0.1)',
    color: 'rgba(255,255,255,0.5)',
    fontSize: 11,
  },
}

export default function App() {
  const [page, setPage] = useState<Page>('dashboard')
  const [visited, setVisited] = useState<Page[]>(['dashboard'])

  const navigate = (next: Page) => {
    setVisited(current => current.includes(next) ? current : [...current, next])
    setPage(next)
  }

  const renderPage = (current: Page) => {
    switch (current) {
      case 'dashboard': return <Dashboard />
      case 'generate': return <GeneratePanel />
      case 'validate': return <ValidationPanel />
      case 'compare': return <ComparisonPanel />
      case 'response': return <ResponsePanel />
      case 'export': return <ExportPanel />
      case 'companion': return <CompanionGuidePanel />
      case 'tpmapping': return <TPMappingPanel />
      case 'audit': return <AuditPanel />
      case 'ai': return <AIPanel />
    }
  }

  return (
    <div style={styles.root}>
      {/* Sidebar */}
      <nav style={styles.sidebar}>
        <div style={styles.brand}>
          EDI Accelerator
          <div style={styles.brandSub}>Healthcare EDI Platform</div>
        </div>

        <div style={styles.nav}>
          {NAV_ITEMS.map(item => (
            <div
              key={item.id}
              style={{
                ...styles.navItem,
                ...(page === item.id ? styles.navItemActive : {}),
              }}
              role="button"
              tabIndex={0}
              aria-current={page === item.id ? 'page' : undefined}
              onClick={() => navigate(item.id)}
              onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); navigate(item.id) } }}
            >
              <span style={styles.navIcon}>{item.icon}</span>
              {item.label}
            </div>
          ))}
        </div>

        <div style={styles.footer}>
          v1.0.0 · B.L.A.S.T Protocol<br />
          AI: Gemini external API · Consent required · Disabled by default
        </div>
      </nav>

      {/* Main Content */}
      <main style={styles.content}>
        {/* Preserve original panel results and task snapshots across tab navigation.
          Nothing is persisted in browser storage; a reload clears this view. */}
        {visited.map(current => <div key={current} hidden={page !== current}>{renderPage(current)}</div>)}
      </main>
    </div>
  )
}
