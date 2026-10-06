import React, { useState, useRef, useMemo, useCallback } from 'react'
import { compareEDI, exportComparisonExcel } from '../api'
import AIAssistBar, { AITabAction } from './AIAssistBar'

/* â”€â”€â”€ AI Actions for Compare tab â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
const COMPARE_AI_ACTIONS: AITabAction[] = [
  { label: 'Explain Differences', icon: 'ðŸ”', description: 'Explain detected differences in plain English', promptHint: 'Explain these EDI file differences:' },
  { label: 'Root Cause Analysis', icon: 'â—Ž', description: 'Identify likely root causes of the differences', promptHint: 'Identify root causes for these EDI differences:' },
  { label: 'Suggest Corrections', icon: 'âœŽ', description: 'Suggest corrective actions for each difference', promptHint: 'Suggest corrections for these EDI differences:' },
]

/* â”€â”€â”€ Status colours â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
const STATUS_BG: Record<string, string> = {
  same: 'transparent', modified: '#fff8e1', removed: '#ffebee', added: '#e8f5e9',
}
const STATUS_BORDER: Record<string, string> = {
  same: 'transparent', modified: '#ffe082', removed: '#ef9a9a', added: '#a5d6a7',
}
const STATUS_TEXT: Record<string, string> = {
  same: '#333', modified: '#7b3f00', removed: '#b71c1c', added: '#1b5e20',
}
const STATUS_LABEL: Record<string, { label: string; bg: string; color: string }> = {
  modified: { label: 'MODIFIED', bg: '#fff8e1', color: '#e65100' },
  removed:  { label: 'REMOVED IN B',  bg: '#ffebee', color: '#c62828' },
  added:    { label: 'ADDED IN B',    bg: '#e8f5e9', color: '#2e7d32' },
}
const DIFF_TYPE_BG: Record<string, string> = {
  MISSING: '#ffebee', EXTRA: '#e8f5e9', MISMATCH: '#fff8e1', VALUE_CHANGE: '#e3f0fa',
}
const DIFF_TYPE_COLOR: Record<string, string> = {
  MISSING: '#c62828', EXTRA: '#2e7d32', MISMATCH: '#e65100', VALUE_CHANGE: '#1F4E79',
}

type LevelFilter = 'all' | 'segment' | 'element' | 'mismatch_only'
type RecordFilter = 'all' | 'with_diffs' | 'without_diffs' | 'missing_a' | 'missing_b'
type RecordSort   = 'id' | 'diff_count'

/* â”€â”€â”€ Styles â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
const s: Record<string, React.CSSProperties> = {
  container: { padding: 24, fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif' },
  title: { fontSize: 20, fontWeight: 700, marginBottom: 20, color: '#1F4E79' },
  card: { background: '#fff', borderRadius: 8, padding: 24, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 16 },
  grid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 16, marginBottom: 16 },
  label: { display: 'block', marginBottom: 8, fontWeight: 600, color: '#444', fontSize: 14 },
  input: { width: '100%', padding: '10px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 14, boxSizing: 'border-box' as const },
  btn: { padding: '10px 28px', background: '#1F4E79', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 14 },
  btnSecondary: { padding: '8px 18px', background: '#2366a8', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 13 },
  btnOutline: { padding: '6px 14px', background: '#fff', color: '#1F4E79', border: '1.5px solid #1F4E79', borderRadius: 6, cursor: 'pointer', fontWeight: 600, fontSize: 12 },
  err: { color: '#c62828', background: '#ffebee', padding: '10px 14px', borderRadius: 6, marginBottom: 8, fontSize: 13 },

  // Dashboard stats
  statsRow: { display: 'flex', gap: 12, marginBottom: 16, flexWrap: 'wrap' as const },
  statChip: {
    background: '#fff', borderRadius: 8, padding: '12px 18px',
    boxShadow: '0 1px 4px rgba(0,0,0,0.1)', textAlign: 'center' as const, minWidth: 120,
    cursor: 'pointer', transition: 'box-shadow 0.15s, transform 0.1s',
    border: '2px solid transparent',
  },
  statVal: { fontSize: 24, fontWeight: 800, color: '#1F4E79', lineHeight: 1 },
  statLbl: { fontSize: 11, color: '#888', marginTop: 4 },

  // Record matching section
  recCard: { background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 16, overflow: 'hidden' },
  recHeader: { background: '#1F4E79', color: '#fff', padding: '10px 16px', fontSize: 14, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 10 },
  recBody: { padding: 16 },
  recStats: { display: 'flex', gap: 12, marginBottom: 14, flexWrap: 'wrap' as const },
  recChip: { borderRadius: 8, padding: '10px 16px', textAlign: 'center' as const, minWidth: 100, border: '1px solid', cursor: 'pointer', transition: 'opacity 0.15s' },
  recChipVal: { fontSize: 20, fontWeight: 800, lineHeight: 1 },
  recChipLbl: { fontSize: 11, marginTop: 3 },
  recMissingGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12 },
  recMissingBox: { borderRadius: 6, padding: '10px 14px', fontSize: 12 },
  recKey: { fontFamily: 'monospace', background: 'rgba(0,0,0,0.06)', padding: '2px 6px', borderRadius: 3, marginBottom: 4, display: 'block', wordBreak: 'break-all' as const },

  // Matching key badge
  keyBadge: {
    display: 'inline-flex', alignItems: 'center', gap: 6,
    background: '#e3f0fa', color: '#1F4E79', borderRadius: 20,
    padding: '4px 12px', fontSize: 12, fontWeight: 600, marginBottom: 12,
    border: '1px solid #b3cee8',
  },

  // Record list panel
  recListCard: { background: '#fff', borderRadius: 8, boxShadow: '0 1px 4px rgba(0,0,0,0.1)', marginBottom: 16, overflow: 'hidden' },
  recListHeader: { background: '#1F4E79', color: '#fff', padding: '10px 16px', fontSize: 14, fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'space-between' },
  recListBody: { padding: 16 },
  recListControls: { display: 'flex', gap: 10, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap' as const },
  searchInput: { flex: 1, minWidth: 180, padding: '7px 12px', border: '1px solid #ddd', borderRadius: 6, fontSize: 13 },
  recListScroll: { maxHeight: 320, overflowY: 'auto' as const, border: '1px solid #eee', borderRadius: 6 },
  recListRow: {
    display: 'flex', alignItems: 'center', gap: 12,
    padding: '8px 14px', borderBottom: '1px solid #f0f2f5',
    cursor: 'pointer', transition: 'background 0.12s', fontSize: 13,
  },
  recListRowId: { fontFamily: 'monospace', fontWeight: 700, flex: 1, color: '#1F4E79' },
  recListRowBadge: { padding: '2px 8px', borderRadius: 10, fontSize: 11, fontWeight: 700 },

  // Filter tabs
  filterRow: { display: 'flex', gap: 8, marginBottom: 12, alignItems: 'center', flexWrap: 'wrap' as const },
  filterTab: { padding: '5px 14px', borderRadius: 20, border: '1px solid #ddd', cursor: 'pointer', fontWeight: 600, fontSize: 12, transition: 'all 0.15s' },

  // Record-level SBS view
  recViewCard: { background: '#fff', borderRadius: 8, boxShadow: '0 2px 8px rgba(0,0,0,0.12)', marginBottom: 16, overflow: 'hidden', border: '2px solid #1F4E79' },
  recViewHeader: { background: '#1F4E79', color: '#fff', padding: '10px 16px', display: 'flex', alignItems: 'center', gap: 12 },
  recViewBody: { padding: 16 },

  // Summary panel for selected record
  sumGrid: { display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(160px,1fr))', gap: 10, marginBottom: 14 },
  sumChip: { background: '#f5f7fa', borderRadius: 8, padding: '10px 14px', textAlign: 'center' as const, border: '1px solid #e0e4ea' },
  sumVal: { fontSize: 22, fontWeight: 800, color: '#1F4E79', lineHeight: 1 },
  sumLbl: { fontSize: 11, color: '#888', marginTop: 3 },
  sumTagGroup: { display: 'flex', gap: 6, flexWrap: 'wrap' as const },
  sumTag: { fontFamily: 'monospace', background: '#e3f0fa', color: '#1F4E79', padding: '2px 8px', borderRadius: 4, fontSize: 12, fontWeight: 600 },

  // Navigation bar
  navBar: { display: 'flex', alignItems: 'center', gap: 10, marginBottom: 12, padding: '8px 12px', background: '#f5f7fa', borderRadius: 6, border: '1px solid #e0e4ea' },

  // Side-by-side viewer
  sbsWrap: { border: '1px solid #e0e0e0', borderRadius: 8, overflow: 'hidden', marginBottom: 16 },
  sbsGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr' },
  sbsDivider: { borderRight: '2px solid #e0e0e0' },
  sbsPane: { overflow: 'auto', maxHeight: 450, background: '#fafafa' },
  sbsPaneB: { overflow: 'auto', maxHeight: 450, background: '#fafafa' },
  sbsHeader: {
    padding: '8px 12px', background: '#1F4E79', color: '#fff',
    fontSize: 12, fontWeight: 700, display: 'flex', alignItems: 'center',
    justifyContent: 'space-between', position: 'sticky' as const, top: 0, zIndex: 3,
  },
  sbsHeaderB: { background: '#2366a8' },
  sbsRow: {
    display: 'flex', alignItems: 'stretch', minHeight: 24,
    cursor: 'pointer', borderBottom: '1px solid transparent',
    transition: 'filter 0.1s',
  },
  sbsLineNum: {
    width: 38, minWidth: 38, textAlign: 'right' as const,
    padding: '3px 8px', color: '#bbb', fontSize: 11,
    fontFamily: 'monospace', userSelect: 'none' as const,
    flexShrink: 0, borderRight: '1px solid #e8e8e8',
    background: '#f0f0f0',
  },
  sbsContent: {
    padding: '3px 8px', fontSize: 12, fontFamily: 'monospace',
    flex: 1, wordBreak: 'break-all' as const, lineHeight: 1.5,
    whiteSpace: 'pre-wrap' as const,
  },

  // Detail panel
  detailCard: {
    background: '#fff', borderRadius: 8, marginBottom: 16,
    boxShadow: '0 1px 4px rgba(0,0,0,0.1)', overflow: 'hidden',
    border: '2px solid #1F4E79',
  },
  detailHdr: {
    background: '#1F4E79', color: '#fff', padding: '10px 16px',
    fontSize: 13, fontWeight: 700, display: 'flex', alignItems: 'center', gap: 8,
  },
  detailClose: {
    marginLeft: 'auto', background: 'rgba(255,255,255,0.2)', border: 'none',
    color: '#fff', borderRadius: 4, cursor: 'pointer', padding: '2px 8px', fontSize: 12,
  },
  detailBody: { padding: 16 },
  detailGrid2: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 12, marginBottom: 12 },
  detailField: { marginBottom: 0 },
  detailLbl: { fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase' as const, marginBottom: 4 },
  detailVal: {
    fontSize: 12, fontFamily: 'monospace', background: '#f5f7fa',
    padding: '6px 10px', borderRadius: 4, wordBreak: 'break-all' as const,
    minHeight: 28, color: '#1F4E79',
  },
  detailValA: { borderLeft: '3px solid #c62828' },
  detailValB: { borderLeft: '3px solid #2e7d32' },
  detailResolution: {
    background: '#e8f5e9', borderRadius: 6, padding: '10px 14px',
    fontSize: 12, color: '#1b5e20', lineHeight: 1.6,
  },

  // Differences table
  tableWrap: { overflowX: 'auto' as const },
  table: { width: '100%', borderCollapse: 'collapse' as const, fontSize: 12 },
  th: { background: '#1F4E79', color: '#fff', padding: '7px 10px', textAlign: 'left' as const, fontWeight: 700, whiteSpace: 'nowrap' as const },
  td: { padding: '7px 10px', borderBottom: '1px solid #f0f2f5', verticalAlign: 'top' as const },
  badge: { padding: '2px 8px', borderRadius: 10, fontWeight: 700, fontSize: 11, display: 'inline-block' },
  mono: { fontFamily: 'monospace', fontSize: 11 },
  identical: { color: '#2e7d32', fontWeight: 700, padding: '16px', textAlign: 'center' as const },
}

/* â”€â”€â”€ Component â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
export default function ComparisonPanel() {
  const [fileA, setFileA]                   = useState<File | null>(null)
  const [fileB, setFileB]                   = useState<File | null>(null)
  const [loading, setLoading]               = useState(false)
  const [exportingExcel, setExportingExcel] = useState(false)
  const [result, setResult]                 = useState<any>(null)
  const [err, setErr]                       = useState('')

  // Global SBS state
  const [selectedRow, setSelectedRow]   = useState<number | null>(null)
  const [levelFilter, setLevelFilter]   = useState<LevelFilter>('all')

  // Record list panel state
  const [selectedRecordId, setSelectedRecordId] = useState<string | null>(null)
  const [recordSearch, setRecordSearch]         = useState('')
  const [recordFilter, setRecordFilter]         = useState<RecordFilter>('all')
  const [recordSort, setRecordSort]             = useState<RecordSort>('id')

  // Record-level SBS state
  const [recSelectedRow, setRecSelectedRow] = useState<number | null>(null)
  const [diffNavIdx, setDiffNavIdx]         = useState(0)

  // Refs for scroll sync
  const paneARef    = useRef<HTMLDivElement>(null)
  const paneBRef    = useRef<HTMLDivElement>(null)
  const recPaneARef = useRef<HTMLDivElement>(null)
  const recPaneBRef = useRef<HTMLDivElement>(null)
  const syncingRef  = useRef(false)
  const recSyncRef  = useRef(false)
  const diffRowRefs = useRef<Record<number, HTMLDivElement | null>>({})
  const recordListRef = useRef<HTMLDivElement>(null)

  const onScrollA = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    if (syncingRef.current) return
    syncingRef.current = true
    if (paneBRef.current) paneBRef.current.scrollTop = e.currentTarget.scrollTop
    syncingRef.current = false
  }, [])

  const onScrollB = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    if (syncingRef.current) return
    syncingRef.current = true
    if (paneARef.current) paneARef.current.scrollTop = e.currentTarget.scrollTop
    syncingRef.current = false
  }, [])

  const onRecScrollA = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    if (recSyncRef.current) return
    recSyncRef.current = true
    if (recPaneBRef.current) recPaneBRef.current.scrollTop = e.currentTarget.scrollTop
    recSyncRef.current = false
  }, [])

  const onRecScrollB = useCallback((e: React.UIEvent<HTMLDivElement>) => {
    if (recSyncRef.current) return
    recSyncRef.current = true
    if (recPaneARef.current) recPaneARef.current.scrollTop = e.currentTarget.scrollTop
    recSyncRef.current = false
  }, [])

  /* â”€â”€ Compare â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
  const run = async () => {
    if (!fileA || !fileB) return
    setLoading(true); setErr(''); setResult(null)
    setSelectedRow(null); setSelectedRecordId(null); setRecSelectedRow(null)
    setRecordSearch(''); setRecordFilter('all'); setDiffNavIdx(0)
    try {
      const res = await compareEDI(fileA, fileB)
      setResult(res.data)
    } catch (e: any) {
      setErr(e.response?.data?.detail || e.message)
    } finally {
      setLoading(false)
    }
  }

  /* â”€â”€ Excel Export â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
  const handleExportExcel = async () => {
    if (!fileA || !fileB) return
    setExportingExcel(true)
    try {
      const res = await exportComparisonExcel(fileA, fileB)
      const url = URL.createObjectURL(new Blob([res.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      }))
      const a = document.createElement('a')
      a.href = url
      a.download = `comparison_report_${fileA.name}_vs_${fileB.name}.xlsx`
      a.click()
      URL.revokeObjectURL(url)
    } catch (e: any) {
      setErr('Excel export failed: ' + (e.response?.data?.detail || e.message))
    } finally {
      setExportingExcel(false)
    }
  }

  /* â”€â”€ Derived data â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
  // Selected row detail (global SBS)
  const selectedDetail = useMemo(() => {
    if (selectedRow === null || !result) return null
    const lineA: string = result.lines_a[selectedRow] ?? ''
    const lineB: string = result.lines_b[selectedRow] ?? ''
    const status: string = result.statuses[selectedRow] ?? 'same'
    const segId = (lineA || lineB).split('*')[0]
    const matchingDiffs = (result.differences ?? []).filter((d: any) => d.segment === segId)
    return { lineA, lineB, status, segId, matchingDiffs }
  }, [selectedRow, result])

  // Filtered differences table (global, or scoped to selected record)
  const filteredDiffs = useMemo(() => {
    if (!result) return []
    const source: any[] = selectedRecordId
      ? (result.record_comparisons?.[selectedRecordId]?.differences ?? [])
      : (result.differences ?? [])
    if (levelFilter === 'mismatch_only') return source.filter((d: any) => d.difference_type !== 'VALUE_CHANGE' || d.field.endsWith('_COUNT'))
    if (levelFilter === 'segment')      return source.filter((d: any) => ['MISSING', 'EXTRA', 'MISMATCH'].includes(d.difference_type) || d.field.endsWith('_COUNT'))
    if (levelFilter === 'element')      return source.filter((d: any) => d.difference_type === 'VALUE_CHANGE' && !d.field.endsWith('_COUNT'))
    return source
  }, [result, levelFilter, selectedRecordId])

  // Selected record's comparison data
  const selectedRecord = useMemo(() => {
    if (!selectedRecordId || !result?.record_comparisons) return null
    return result.record_comparisons[selectedRecordId] ?? null
  }, [selectedRecordId, result])

  // Diff indices in record SBS for navigation
  const recDiffIndices = useMemo(() => {
    if (!selectedRecord) return []
    return (selectedRecord.statuses as string[])
      .map((s: string, i: number) => (s !== 'same' ? i : -1))
      .filter((i: number) => i >= 0)
  }, [selectedRecord])

  // Filtered + sorted record list
  const visibleRecords = useMemo(() => {
    if (!result) return []
    const matched: string[] = result.matched_record_ids ?? []
    const onlyA: string[]   = result.only_in_a ?? []
    const onlyB: string[]   = result.only_in_b ?? []

    type Row = { id: string; kind: 'matched' | 'only_a' | 'only_b'; diffCount: number }
    let rows: Row[] = []

    if (recordFilter === 'all' || recordFilter === 'with_diffs' || recordFilter === 'without_diffs') {
      rows = matched.map(id => {
        const rc = result.record_comparisons?.[id]
        return { id, kind: 'matched' as const, diffCount: rc?.total_differences ?? 0 }
      })
      if (recordFilter === 'with_diffs')    rows = rows.filter(r => r.diffCount > 0)
      if (recordFilter === 'without_diffs') rows = rows.filter(r => r.diffCount === 0)
    }
    if (recordFilter === 'missing_a') rows = onlyB.map(id => ({ id, kind: 'only_b' as const, diffCount: 0 }))
    if (recordFilter === 'missing_b') rows = onlyA.map(id => ({ id, kind: 'only_a' as const, diffCount: 0 }))

    if (recordSearch.trim()) {
      const q = recordSearch.trim().toLowerCase()
      rows = rows.filter(r => r.id.toLowerCase().includes(q))
    }
    if (recordSort === 'diff_count') rows = [...rows].sort((a, b) => b.diffCount - a.diffCount)
    else rows = [...rows].sort((a, b) => a.id.localeCompare(b.id))

    return rows
  }, [result, recordFilter, recordSearch, recordSort])

  // Navigate to next/prev diff in record SBS
  const goToDiff = useCallback((direction: 1 | -1) => {
    if (!recDiffIndices.length) return
    const next = (diffNavIdx + direction + recDiffIndices.length) % recDiffIndices.length
    setDiffNavIdx(next)
    const target = recDiffIndices[next]
    const el = diffRowRefs.current[target]
    if (el) el.scrollIntoView({ block: 'center', behavior: 'smooth' })
    setRecSelectedRow(target)
  }, [diffNavIdx, recDiffIndices])

  const FILTER_TABS: { id: LevelFilter; label: string }[] = [
    { id: 'all',          label: 'All Differences' },
    { id: 'segment',      label: 'Segment Level' },
    { id: 'element',      label: 'Element Level' },
    { id: 'mismatch_only', label: 'Mismatches Only' },
  ]

  const RECORD_FILTER_TABS: { id: RecordFilter; label: string; color?: string }[] = [
    { id: 'all',           label: 'All Matched' },
    { id: 'with_diffs',    label: 'With Differences', color: '#c62828' },
    { id: 'without_diffs', label: 'Identical', color: '#2e7d32' },
    { id: 'missing_a',     label: 'Missing in File A', color: '#e65100' },
    { id: 'missing_b',     label: 'Missing in File B', color: '#e65100' },
  ]

  /* â”€â”€â”€ Render â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
  return (
    <div style={s.container}>
      <h1 style={s.title}>Comparison Workspace</h1>

      {/* â”€â”€ 1. File Upload â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
      <div style={s.card}>
        <div style={s.grid2}>
          <div>
            <label style={s.label}>File A (Reference / Original)</label>
            <input type="file" accept=".edi,.txt,.x12,.dat"
              onChange={e => setFileA(e.target.files?.[0] || null)} style={s.input} />
          </div>
          <div>
            <label style={s.label}>File B (Compare / Received)</label>
            <input type="file" accept=".edi,.txt,.x12,.dat"
              onChange={e => setFileB(e.target.files?.[0] || null)} style={s.input} />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
          <button style={{ ...s.btn, opacity: (!fileA || !fileB) ? 0.6 : 1 }}
            disabled={!fileA || !fileB || loading} onClick={run}>
            {loading ? 'Comparingâ€¦' : 'Compare Files'}
          </button>
          {result && (
            <button style={{ ...s.btnSecondary, opacity: exportingExcel ? 0.6 : 1 }}
              disabled={exportingExcel} onClick={handleExportExcel}>
              {exportingExcel ? 'Generatingâ€¦' : 'â¬‡ Download Comparison Report'}
            </button>
          )}
        </div>
      </div>

      {err && <div style={s.err}>Error: {err}</div>}

      {result && (
        <>
          {/* â”€â”€ 2. Comparison Dashboard (8 metrics, clickable) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
          <div style={{ ...s.card, paddingBottom: 10 }}>
            <div style={{ fontWeight: 700, fontSize: 14, color: '#1F4E79', marginBottom: 12 }}>
              Comparison Dashboard
              {result.matching_key_used && (
                <span style={{ ...s.keyBadge, marginLeft: 14 }}>
                  ðŸ”‘ Matching Key: {result.matching_key_used}
                </span>
              )}
            </div>

            {/* Record-level metrics */}
            {result.record_level_used && (
              <>
                <div style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase', marginBottom: 8 }}>
                  {result.record_label} / Business Record Level
                </div>
                <div style={s.statsRow}>
                  {[
                    { val: result.record_a_count,          lbl: `${result.record_label}s in File A`,    filter: null,            accent: false },
                    { val: result.record_b_count,          lbl: `${result.record_label}s in File B`,    filter: null,            accent: false },
                    { val: result.matched_records_count,   lbl: 'Matched Records',                      filter: 'all' as RecordFilter,            accent: false },
                    { val: (result.only_in_b ?? []).length, lbl: 'Missing in File A',                  filter: 'missing_a' as RecordFilter,      accent: (result.only_in_b ?? []).length > 0 },
                    { val: (result.only_in_a ?? []).length, lbl: 'Missing in File B',                  filter: 'missing_b' as RecordFilter,      accent: (result.only_in_a ?? []).length > 0 },
                    { val: result.records_with_differences,   lbl: 'With Differences',                 filter: 'with_diffs' as RecordFilter,     accent: result.records_with_differences > 0 },
                    { val: result.records_without_differences, lbl: 'Without Differences',             filter: 'without_diffs' as RecordFilter,  accent: false },
                    { val: result.total_record_differences,   lbl: 'Total Record Differences',         filter: null,            accent: result.total_record_differences > 0 },
                  ].map(({ val, lbl, filter, accent }) => (
                    <div
                      key={lbl}
                      style={{
                        ...s.statChip,
                        border: filter && recordFilter === filter ? '2px solid #1F4E79' : '2px solid transparent',
                      }}
                      onClick={() => {
                        if (filter) {
                          setRecordFilter(filter)
                          recordListRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
                        }
                      }}
                      title={filter ? `Click to filter record list` : undefined}
                    >
                      <div style={{ ...s.statVal, color: accent ? '#c62828' : '#1F4E79' }}>{val}</div>
                      <div style={s.statLbl}>{lbl}</div>
                    </div>
                  ))}
                </div>
              </>
            )}

            {/* Segment-level metrics */}
            <div style={{ fontSize: 11, fontWeight: 700, color: '#888', textTransform: 'uppercase', marginBottom: 8 }}>
              Segment / Element Level
            </div>
            <div style={s.statsRow}>
              {[
                { val: result.total_segments_compared, lbl: 'Segments Compared', accent: false },
                { val: result.total_differences,       lbl: 'Total Differences', accent: result.total_differences > 0 },
                { val: result.missing_segments_count,  lbl: 'Missing Segments',  accent: result.missing_segments_count > 0 },
                { val: result.extra_segments_count,    lbl: 'Extra Segments',    accent: result.extra_segments_count > 0 },
                { val: result.modified_values_count,   lbl: 'Modified Values',   accent: result.modified_values_count > 0 },
              ].map(({ val, lbl, accent }) => (
                <div key={lbl} style={{ ...s.statChip, cursor: 'default' }}>
                  <div style={{ ...s.statVal, color: accent ? '#c62828' : '#1F4E79' }}>{val}</div>
                  <div style={s.statLbl}>{lbl}</div>
                </div>
              ))}
            </div>
          </div>

                    {/* ── Download Report Banner ───────────────────────────── */}
          <div style={{ ...s.card, display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '14px 20px', background: '#f0f7ff', borderLeft: '4px solid #1F4E79' }}>
            <div>
              <div style={{ fontWeight: 700, color: '#1F4E79', fontSize: 14 }}>Download Comparison Report</div>
              <div style={{ fontSize: 12, color: '#555', marginTop: 3 }}>
                Excel format — Claim/Auth Reference ID, Transaction Type, Segment, Element,
                File A &amp; B Values, Difference Description, Source File Names and Timestamp.
                Suitable for Developers, QA Teams, Business Analysts and SMEs.
              </div>
            </div>
            <button
              style={{ ...s.btn, background: '#217346', minWidth: 260, opacity: exportingExcel ? 0.6 : 1, whiteSpace: 'nowrap' as const }}
              disabled={exportingExcel}
              onClick={handleExportExcel}
            >
              {exportingExcel ? 'Generating…' : '⬇ Download Comparison Report (.xlsx)'}
            </button>
          </div>

{/* â”€â”€ 3. Matching Record List Panel â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
          {result.record_level_used && (
            <div style={s.recListCard} ref={recordListRef}>
              <div style={s.recListHeader}>
                <span>âŠž {result.record_label} Matching List</span>
                <span style={{ fontSize: 12, fontWeight: 400, opacity: 0.8 }}>
                  {result.matched_records_count} matched Â· click any ID to compare
                </span>
              </div>
              <div style={s.recListBody}>
                {/* Controls: search + filter + sort */}
                <div style={s.recListControls}>
                  <input
                    style={s.searchInput}
                    placeholder={`Search ${result.record_label} IDâ€¦`}
                    value={recordSearch}
                    onChange={e => setRecordSearch(e.target.value)}
                  />
                  <select
                    style={{ padding: '7px 10px', borderRadius: 6, border: '1px solid #ddd', fontSize: 13 }}
                    value={recordSort}
                    onChange={e => setRecordSort(e.target.value as RecordSort)}
                  >
                    <option value="id">Sort: ID Aâ†’Z</option>
                    <option value="diff_count">Sort: Most Differences</option>
                  </select>
                </div>

                {/* Filter tabs */}
                <div style={s.filterRow}>
                  {RECORD_FILTER_TABS.map(t => (
                    <button key={t.id}
                      style={{
                        ...s.filterTab,
                        background: recordFilter === t.id ? (t.color || '#1F4E79') : '#fff',
                        color: recordFilter === t.id ? '#fff' : (t.color || '#444'),
                        borderColor: recordFilter === t.id ? (t.color || '#1F4E79') : '#ddd',
                      }}
                      onClick={() => setRecordFilter(t.id)}>
                      {t.label}
                    </button>
                  ))}
                </div>

                {/* Record rows */}
                {visibleRecords.length === 0 ? (
                  <div style={{ padding: 16, color: '#888', fontSize: 13, textAlign: 'center' }}>
                    No records match this filter.
                  </div>
                ) : (
                  <div style={s.recListScroll}>
                    {visibleRecords.map(row => {
                      const isSelected = selectedRecordId === row.id
                      const isOnly = row.kind === 'only_a' || row.kind === 'only_b'
                      const hasDiffs = row.kind === 'matched' && row.diffCount > 0
                      return (
                        <div
                          key={row.id}
                          style={{
                            ...s.recListRow,
                            background: isSelected ? '#e3f0fa' : (isOnly ? '#fffde7' : '#fff'),
                            borderLeft: isSelected ? '3px solid #1F4E79' : '3px solid transparent',
                          }}
                          onClick={() => {
                            if (isOnly) return
                            setSelectedRecordId(isSelected ? null : row.id)
                            setRecSelectedRow(null)
                            setDiffNavIdx(0)
                          }}
                          title={isOnly ? `Only in ${row.kind === 'only_a' ? 'File A' : 'File B'} â€” not available for comparison` : `Click to view record comparison`}
                        >
                          <span style={s.recListRowId}>{row.id}</span>
                          {row.kind === 'matched' && (
                            <span style={{
                              ...s.recListRowBadge,
                              background: hasDiffs ? '#ffebee' : '#e8f5e9',
                              color: hasDiffs ? '#c62828' : '#2e7d32',
                            }}>
                              {hasDiffs ? `${row.diffCount} diff${row.diffCount > 1 ? 's' : ''}` : 'âœ“ Identical'}
                            </span>
                          )}
                          {isOnly && (
                            <span style={{ ...s.recListRowBadge, background: '#fff8e1', color: '#e65100' }}>
                              {row.kind === 'only_a' ? 'Only A' : 'Only B'}
                            </span>
                          )}
                          {row.kind === 'matched' && !isOnly && (
                            <span style={{ color: '#1F4E79', fontSize: 12 }}>
                              {isSelected ? 'â–¾ Close' : 'â–¸ View'}
                            </span>
                          )}
                        </div>
                      )
                    })}
                  </div>
                )}

              </div>
            </div>
          )}

          {/* â”€â”€ 4. Record-Level Comparison View (when record selected) â”€â”€â”€ */}
          {selectedRecord && (
            <div style={s.recViewCard}>
              <div style={s.recViewHeader}>
                <span style={{ fontWeight: 700, fontSize: 14 }}>
                  {result.record_label} Detail: <span style={{ fontFamily: 'monospace' }}>{selectedRecordId}</span>
                </span>
                <button
                  style={{ ...s.detailClose, marginLeft: 'auto' }}
                  onClick={() => { setSelectedRecordId(null); setRecSelectedRow(null) }}>
                  âœ• Close
                </button>
              </div>
              <div style={s.recViewBody}>

                {/* 3. Difference Summary Panel */}
                <div style={s.sumGrid}>
                  <div style={s.sumChip}>
                    <div style={{ ...s.sumVal, color: selectedRecord.total_differences > 0 ? '#c62828' : '#2e7d32' }}>
                      {selectedRecord.total_differences}
                    </div>
                    <div style={s.sumLbl}>Differences Found</div>
                  </div>
                  <div style={s.sumChip}>
                    <div style={{ ...s.sumVal, color: '#e65100' }}>{selectedRecord.modified_segments?.length ?? 0}</div>
                    <div style={s.sumLbl}>Modified Segments</div>
                  </div>
                  <div style={s.sumChip}>
                    <div style={{ ...s.sumVal, color: '#1F4E79' }}>{selectedRecord.modified_elements?.length ?? 0}</div>
                    <div style={s.sumLbl}>Modified Elements</div>
                  </div>
                  <div style={{ ...s.sumChip, gridColumn: '4 / -1' }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#888', marginBottom: 6 }}>Modified Segments</div>
                    <div style={s.sumTagGroup}>
                      {(selectedRecord.modified_segments ?? []).length === 0
                        ? <span style={{ color: '#2e7d32', fontSize: 12 }}>âœ“ None</span>
                        : (selectedRecord.modified_segments ?? []).map((seg: string) => (
                            <span key={seg} style={s.sumTag}>{seg}</span>
                          ))
                      }
                    </div>
                  </div>
                  <div style={{ ...s.sumChip, gridColumn: '1 / -1' }}>
                    <div style={{ fontSize: 12, fontWeight: 700, color: '#888', marginBottom: 6 }}>Modified Elements</div>
                    <div style={s.sumTagGroup}>
                      {(selectedRecord.modified_elements ?? []).length === 0
                        ? <span style={{ color: '#2e7d32', fontSize: 12 }}>âœ“ None</span>
                        : (selectedRecord.modified_elements ?? []).map((el: string) => (
                            <span key={el} style={{ ...s.sumTag, background: '#fff0e0', color: '#e65100' }}>{el}</span>
                          ))
                      }
                    </div>
                  </div>
                </div>

                {/* Navigation bar */}
                {recDiffIndices.length > 0 && (
                  <div style={s.navBar}>
                    <span style={{ fontSize: 12, color: '#555', marginRight: 4 }}>
                      Difference {diffNavIdx + 1} of {recDiffIndices.length}
                    </span>
                    <button style={s.btnOutline} onClick={() => goToDiff(-1)}>â†‘ Prev</button>
                    <button style={s.btnOutline} onClick={() => goToDiff(1)}>â†“ Next</button>
                    <span style={{ fontSize: 11, color: '#888', marginLeft: 8 }}>
                      Highlighted in red Â· Identical lines unhighlighted
                    </span>
                  </div>
                )}

                {/* Record-level SBS Viewer */}
                <div style={s.sbsWrap}>
                  <div style={s.sbsGrid}>
                    <div style={s.sbsDivider}>
                      <div style={s.sbsHeader}>
                        <span>File A â€” {result.file_a}</span>
                        <span style={{ fontSize: 11, opacity: 0.8 }}>
                          {(selectedRecord.lines_a ?? []).filter((l: string) => l).length} segments
                        </span>
                      </div>
                      <div ref={recPaneARef} style={s.sbsPane} onScroll={onRecScrollA}>
                        {(selectedRecord.lines_a ?? []).map((line: string, i: number) => {
                          const status = selectedRecord.statuses[i] ?? 'same'
                          const isSelected = recSelectedRow === i
                          return (
                            <div
                              key={i}
                              ref={(el) => { diffRowRefs.current[i] = el }}
                              style={{
                                ...s.sbsRow,
                                background: isSelected ? '#e3f0fa' : STATUS_BG[status],
                                borderBottom: `1px solid ${isSelected ? '#1F4E79' : STATUS_BORDER[status]}`,
                                outline: isSelected ? '2px solid #1F4E79' : 'none',
                                outlineOffset: -2,
                              }}
                              onClick={() => setRecSelectedRow(status !== 'same' ? i : null)}
                            >
                              <div style={s.sbsLineNum}>{i + 1}</div>
                              <div style={{ ...s.sbsContent, color: STATUS_TEXT[status] }}>
                                {line || <span style={{ color: '#ddd', fontStyle: 'italic' }}>â€” no segment â€”</span>}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                    <div>
                      <div style={{ ...s.sbsHeader, ...s.sbsHeaderB }}>
                        <span>File B â€” {result.file_b}</span>
                        <span style={{ fontSize: 11, opacity: 0.8 }}>
                          {(selectedRecord.lines_b ?? []).filter((l: string) => l).length} segments
                        </span>
                      </div>
                      <div ref={recPaneBRef} style={s.sbsPaneB} onScroll={onRecScrollB}>
                        {(selectedRecord.lines_b ?? []).map((line: string, i: number) => {
                          const status = selectedRecord.statuses[i] ?? 'same'
                          const isSelected = recSelectedRow === i
                          return (
                            <div
                              key={i}
                              style={{
                                ...s.sbsRow,
                                background: isSelected ? '#e3f0fa' : STATUS_BG[status],
                                borderBottom: `1px solid ${isSelected ? '#1F4E79' : STATUS_BORDER[status]}`,
                                outline: isSelected ? '2px solid #1F4E79' : 'none',
                                outlineOffset: -2,
                              }}
                              onClick={() => setRecSelectedRow(status !== 'same' ? i : null)}
                            >
                              <div style={s.sbsLineNum}>{i + 1}</div>
                              <div style={{ ...s.sbsContent, color: STATUS_TEXT[status] }}>
                                {line || <span style={{ color: '#ddd', fontStyle: 'italic' }}>â€” no segment â€”</span>}
                              </div>
                            </div>
                          )
                        })}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Legend */}
                <div style={{ display: 'flex', gap: 16, fontSize: 11, color: '#666', marginBottom: 4 }}>
                  {Object.entries(STATUS_LABEL).map(([k, v]) => (
                    <span key={k} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                      <span style={{ width: 12, height: 12, borderRadius: 2, background: v.bg, border: `1px solid ${v.color}`, display: 'inline-block' }} />
                      {v.label}
                    </span>
                  ))}
                </div>

                {/* Record-level differences table */}</div>
            </div>
          )}

          {/* â”€â”€ Global SBS Diff Viewer (when no record selected) â”€â”€â”€â”€â”€â”€â”€â”€ */}
          {!selectedRecordId && (
            <div style={s.card}>
              <div style={{ fontWeight: 700, fontSize: 14, color: '#1F4E79', marginBottom: 12 }}>
                Full File â€” Side-by-Side Diff Viewer
                <span style={{ fontWeight: 400, fontSize: 12, color: '#888', marginLeft: 10 }}>
                  Click a highlighted row for details Â· Scroll is synchronized
                </span>
              </div>

              <div style={s.sbsWrap}>
                <div style={s.sbsGrid}>
                  <div style={s.sbsDivider}>
                    <div style={s.sbsHeader}>
                      <span>File A â€” {result.file_a}</span>
                      <span style={{ fontSize: 11, opacity: 0.8 }}>
                        {(result.lines_a ?? []).filter((l: string) => l).length} segments
                      </span>
                    </div>
                    <div ref={paneARef} style={s.sbsPane} onScroll={onScrollA}>
                      {(result.lines_a ?? []).map((line: string, i: number) => {
                        const status = result.statuses[i] ?? 'same'
                        const isSelected = selectedRow === i
                        return (
                          <div
                            key={i}
                            style={{
                              ...s.sbsRow,
                              background: isSelected ? '#e3f0fa' : STATUS_BG[status],
                              borderBottom: `1px solid ${isSelected ? '#1F4E79' : STATUS_BORDER[status]}`,
                              outline: isSelected ? '2px solid #1F4E79' : 'none',
                              outlineOffset: -2,
                            }}
                            onClick={() => setSelectedRow(status !== 'same' ? i : null)}
                            title={status !== 'same' ? `Click for details â€” ${status.toUpperCase()}` : undefined}
                          >
                            <div style={s.sbsLineNum}>{i + 1}</div>
                            <div style={{ ...s.sbsContent, color: STATUS_TEXT[status] }}>
                              {line || <span style={{ color: '#ddd', fontStyle: 'italic' }}>â€” no segment â€”</span>}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                  <div>
                    <div style={{ ...s.sbsHeader, ...s.sbsHeaderB }}>
                      <span>File B â€” {result.file_b}</span>
                      <span style={{ fontSize: 11, opacity: 0.8 }}>
                        {(result.lines_b ?? []).filter((l: string) => l).length} segments
                      </span>
                    </div>
                    <div ref={paneBRef} style={s.sbsPaneB} onScroll={onScrollB}>
                      {(result.lines_b ?? []).map((line: string, i: number) => {
                        const status = result.statuses[i] ?? 'same'
                        const isSelected = selectedRow === i
                        return (
                          <div
                            key={i}
                            style={{
                              ...s.sbsRow,
                              background: isSelected ? '#e3f0fa' : STATUS_BG[status],
                              borderBottom: `1px solid ${isSelected ? '#1F4E79' : STATUS_BORDER[status]}`,
                              outline: isSelected ? '2px solid #1F4E79' : 'none',
                              outlineOffset: -2,
                            }}
                            onClick={() => setSelectedRow(status !== 'same' ? i : null)}
                          >
                            <div style={s.sbsLineNum}>{i + 1}</div>
                            <div style={{ ...s.sbsContent, color: STATUS_TEXT[status] }}>
                              {line || <span style={{ color: '#ddd', fontStyle: 'italic' }}>â€” no segment â€”</span>}
                            </div>
                          </div>
                        )
                      })}
                    </div>
                  </div>
                </div>
              </div>

              {/* Legend */}
              <div style={{ display: 'flex', gap: 16, fontSize: 11, color: '#666', marginTop: 8 }}>
                {Object.entries(STATUS_LABEL).map(([k, v]) => (
                  <span key={k} style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                    <span style={{ width: 12, height: 12, borderRadius: 2, background: v.bg, border: `1px solid ${v.color}`, display: 'inline-block' }} />
                    {v.label}
                  </span>
                ))}
                <span style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
                  <span style={{ width: 12, height: 12, borderRadius: 2, background: 'transparent', border: '1px solid #ddd', display: 'inline-block' }} />
                  SAME
                </span>
              </div>
            </div>
          )}

          {/* â”€â”€ Selected Row Detail Panel (global SBS) â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
          {!selectedRecordId && selectedDetail && selectedDetail.status !== 'same' && (
            <div style={s.detailCard}>
              <div style={s.detailHdr}>
                <span>Segment Detail â€” <strong>{selectedDetail.segId}</strong></span>
                <span style={{
                  ...s.badge,
                  background: STATUS_LABEL[selectedDetail.status]?.bg ?? '#f5f5f5',
                  color: STATUS_LABEL[selectedDetail.status]?.color ?? '#333',
                  marginLeft: 8,
                }}>
                  {STATUS_LABEL[selectedDetail.status]?.label ?? selectedDetail.status.toUpperCase()}
                </span>
                <button style={s.detailClose} onClick={() => setSelectedRow(null)}>âœ• Close</button>
              </div>
              <div style={s.detailBody}>
                <div style={s.detailGrid2}>
                  <div style={s.detailField}>
                    <div style={s.detailLbl}>File A â€” {result.file_a}</div>
                    <div style={{ ...s.detailVal, ...s.detailValA }}>
                      {selectedDetail.lineA || 'â€” missing â€”'}
                    </div>
                  </div>
                  <div style={s.detailField}>
                    <div style={s.detailLbl}>File B â€” {result.file_b}</div>
                    <div style={{ ...s.detailVal, ...s.detailValB }}>
                      {selectedDetail.lineB || 'â€” missing â€”'}
                    </div>
                  </div>
                </div>
                {selectedDetail.matchingDiffs.length > 0 && (
                  <table style={{ ...s.table, marginBottom: 12 }}>
                    <thead>
                      <tr>
                        {['Element', 'Name', 'File A Value', 'File B Value', 'Description'].map(h => (
                          <th key={h} style={s.th}>{h}</th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {selectedDetail.matchingDiffs.map((d: any, i: number) => (
                        <tr key={i}>
                          <td style={{ ...s.td, ...s.mono }}>{d.field}</td>
                          <td style={s.td}>{d.element_name || 'â€”'}</td>
                          <td style={{ ...s.td, ...s.mono, color: '#c62828' }}>{d.file_a_value || 'â€”'}</td>
                          <td style={{ ...s.td, ...s.mono, color: '#2e7d32' }}>{d.file_b_value || 'â€”'}</td>
                          <td style={s.td}>{d.description}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
                {selectedDetail.matchingDiffs[0]?.suggested_resolution && (
                  <div style={s.detailResolution}>
                    <strong>Suggested Resolution:</strong>{' '}
                    {selectedDetail.matchingDiffs[0].suggested_resolution}
                  </div>
                )}
              </div>
            </div>
          )}

          {/* â”€â”€ AI Assist â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */}
        </>
      )}
      <AIAssistBar tabName="Comparison" sources={[fileA, fileB].filter((file): file is File => file !== null)}
        context={JSON.stringify({ fileA: fileA?.name, fileB: fileB?.name, deterministic_result: result, error: err })}
        actions={COMPARE_AI_ACTIONS} />
    </div>
  )
}

