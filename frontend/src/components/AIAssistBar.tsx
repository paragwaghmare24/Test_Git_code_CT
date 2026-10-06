import { useEffect, useRef, useState } from 'react'
import { actAITask, AIDataPolicy, AITask, AITaskAction, createAITask, getAITask } from '../api'
import AIConsentDialog from './AIConsentDialog'
import AITaskCard, { displayValue, TaskDetails } from './AITaskCard'
import './ai-assist.css'

export interface AITabAction { label: string; icon: string; description: string; promptHint: string }
interface Props {
  tabName: string
  context?: string
  sources?: File[]
  actions?: AITabAction[]
  initialExpanded?: boolean
}
interface Snapshot {
  panel: string
  context: string
  files: readonly File[]
  instruction: string
  data_policy: AIDataPolicy
}
interface Session {
  snapshot: Snapshot
  task: AITask | null
  history: { action: string; message?: string; task: AITask }[]
}
interface Pending {
  action: 'create' | AITaskAction
  snapshot: Snapshot
  task: AITask | null
  message: string
  policy: AIDataPolicy
  // Also track live panel/draft inputs so consent is invalidated, not silently reused.
  liveContext: string
  livePanel: string
  liveFiles: readonly File[]
  draft: string
}

const fileManifest = (files: readonly File[]) => files.map(file => ({ name: file.name, size: file.size, type: file.type, lastModified: file.lastModified }))
const sameFiles = (a: readonly File[], b: readonly File[]) => a.length === b.length && a.every((file, i) => file === b[i])
const errorMessage = (error: unknown) => {
  const e = error as { response?: { data?: { detail?: unknown } }; message?: string }
  return displayValue(e.response?.data?.detail ?? e.message ?? error)
}

export default function AIAssistBar({ tabName, context = '', sources = [], actions = [], initialExpanded = false }: Props) {
  const [expanded, setExpanded] = useState(initialExpanded)
  const [enabled, setEnabled] = useState(false)
  const [instruction, setInstruction] = useState('')
  const [reply, setReply] = useState('')
  const [policy, setPolicy] = useState<AIDataPolicy>('undecided')
  const [attachments, setAttachments] = useState<File[]>([])
  const [session, setSession] = useState<Session | null>(null)
  const [archive, setArchive] = useState<Session[]>([])
  const [pending, setPending] = useState<Pending | null>(null)
  const [busy, setBusy] = useState('')
  const [error, setError] = useState('')
  const [needsRefresh, setNeedsRefresh] = useState(false)
  const inFlight = useRef(false)
  const mounted = useRef(true)
  const files = [...sources, ...attachments]
  const task = session?.task ?? null
  const live = useRef({ context, tabName, files, instruction, reply, policy, enabled, pending, task })
  live.current = { context, tabName, files, instruction, reply, policy, enabled, pending, task }

  useEffect(() => { mounted.current = true; return () => { mounted.current = false } }, [])
  const valid = (p: Pending) => {
    const now = live.current
    return mounted.current && now.enabled && now.pending === p && now.context === p.liveContext
      && now.tabName === p.livePanel && sameFiles(now.files, p.liveFiles) && now.policy === p.policy
      && (p.action === 'create' ? now.instruction : now.reply) === p.draft
      && now.task?.id === p.task?.id && now.task?.revision === p.task?.revision
  }
  useEffect(() => {
    if (pending && !valid(pending)) {
      setPending(null)
      setError('Inputs or task revision changed. Previous consent was discarded; review and approve again.')
    }
  })

  const remember = (updated: AITask, action: string, message?: string) => {
    setSession(current => current ? { ...current, task: updated, history: [...current.history, { action, message, task: updated }] } : current)
    setPolicy(updated.data_policy)
    setNeedsRefresh(false)
  }

  const openConsent = (action: Pending['action'], customInstruction?: string) => {
    if (!enabled || inFlight.current || pending || needsRefresh) return
    if (task && action !== 'reply' && action !== 'create' && policy !== task.data_policy) {
      setError('Send an approved follow-up to change the data policy before continuing, retrieving, or executing the current scope.')
      return
    }
    const message = action === 'create' ? (customInstruction ?? instruction).trim() : reply.trim()
    if ((action === 'reply' || action === 'create') && !message) return
    if (action !== 'create' && !task) return
    const snapshot = action === 'create'
      ? { panel: tabName, context, files: [...files], instruction: message, data_policy: policy }
      : session!.snapshot
    setError('')
    setPending({ action, snapshot, task: task ? structuredClone(task) : null, message, policy,
      liveContext: context, livePanel: tabName, liveFiles: [...files], draft: action === 'create' ? instruction : reply })
  }

  const approved = async (p: Pending, requestId: string) => {
    if (!valid(p) || inFlight.current) return
    // Never retain requestId for follow-ups or retry it after any error.
    inFlight.current = true
    setPending(null)
    setBusy(p.action === 'create' ? 'Gemini is reviewing approved sources…' : `Processing ${p.action}…`)
    setError('')
    try {
      if (p.action === 'create') {
        setSession({ snapshot: p.snapshot, task: null, history: [] })
        const response = await createAITask({ ...p.snapshot, request_id: requestId })
        if (mounted.current) remember(response.data, 'create', p.snapshot.instruction)
      } else if (p.task) {
        const response = await actAITask(p.task.id, { revision: p.task.revision, action: p.action,
          request_id: requestId, message: p.action === 'reply' ? p.message : undefined, data_policy: p.policy })
        if (mounted.current) {
          remember(response.data, p.action, p.action === 'reply' ? p.message : undefined)
          if (p.action === 'reply') setReply('')
        }
      }
    } catch (e) {
      if (mounted.current) {
        setError(`${errorMessage(e)} No fallback was run. Approval will not be reused.`)
        setNeedsRefresh(!!p.task)
      }
    } finally {
      inFlight.current = false
      if (mounted.current) setBusy('')
    }
  }

  const localAction = async (action: 'adopt' | 'reject') => {
    if (!enabled || !task || pending || inFlight.current || needsRefresh) return
    inFlight.current = true; setBusy(`Saving ${action} decision (no Gemini call)…`); setError('')
    try {
      const response = await actAITask(task.id, { revision: task.revision, action })
      if (mounted.current) remember(response.data, action)
    } catch (e) {
      if (mounted.current) { setError(errorMessage(e)); setNeedsRefresh(true) }
    } finally { inFlight.current = false; if (mounted.current) setBusy('') }
  }

  const refresh = async () => {
    if (!task || pending || inFlight.current) return
    inFlight.current = true; setBusy('Retrieving saved task status (no Gemini call)…'); setError('')
    try {
      const response = await getAITask(task.id)
      if (mounted.current) remember(response.data, 'refresh')
    } catch (e) { if (mounted.current) setError(errorMessage(e)) }
    finally { inFlight.current = false; if (mounted.current) setBusy('') }
  }

  const startNew = () => {
    if (inFlight.current || pending) return
    if (session) setArchive(previous => [session, ...previous])
    setEnabled(false)
    setSession(null); setInstruction(''); setReply(''); setAttachments([]); setPolicy('undecided')
    setError(''); setNeedsRefresh(false)
  }
  const locked = !enabled || !!busy || !!pending
  const inputChanged = session && (session.snapshot.context !== context || session.snapshot.panel !== tabName || !sameFiles(session.snapshot.files, files))
  const approvalContext = pending ? JSON.stringify({
    action: pending.action, task_id: pending.task?.id, revision: pending.task?.revision,
    instruction: pending.action === 'create' ? pending.snapshot.instruction : pending.message,
    data_policy: pending.policy, original_context: pending.snapshot.context,
    original_sources: fileManifest(pending.snapshot.files), current_task: pending.task,
  }, null, 2) : ''

  return <section className="ai-assist" aria-label={`AI Assist — ${tabName}`}>
    <button className="ai-heading" aria-expanded={expanded} onClick={() => setExpanded(value => !value)}>
      ✦ AI Assist — {tabName} <span>Gemini · {expanded ? 'Collapse' : 'Expand'}</span>
    </button>
    {expanded && <div className="ai-body">
      <label className="ai-row"><input type="checkbox" checked={enabled} disabled={!!busy || !!pending} onChange={e => setEnabled(e.target.checked)} />
        <strong>AI {enabled ? 'ENABLED' : 'DISABLED'}</strong> · Separate explicit approval per invocation
      </label>
      <p className="ai-notice">Gemini is an external API. Approved sources and context may contain sensitive data and are retained in local task snapshots.
        Initial approval does not authorize file creation, assessment adoption or external retrieval. AI results never replace the original deterministic panel. No deterministic fallback.</p>
      <p>Supported source formats: EDI/text, CSV, JSON, XLSX, DOCX and text-extractable PDF. Outputs: EDI, text, CSV, JSON and XLSX.
        Each task supports up to 10 MB of input and output; larger work must be split. Long reviews pause at the step/context limits rather than silently claiming full coverage.</p>
      {session && <p className="ai-notice">This task uses its immutable original sources and context for all follow-ups.
        {inputChanged ? ' Panel inputs have changed and are NOT part of this task.' : ''} Start a new task to change inputs.
        Changing the data policy requires a new approved reply; synthetic data is never assumed.</p>}
      <fieldset disabled={locked}>
        <legend>{session ? 'Same-task follow-up' : 'New AI task'}</legend>
        <label>Data population policy
          <select aria-label="Data population policy" value={policy} onChange={e => setPolicy(e.target.value as AIDataPolicy)}>
            <option value="undecided" disabled={!!task && task.data_policy !== 'undecided'}>Undecided — ask before populating missing data</option>
            <option value="supplied">Supplied — use supplied values only</option>
            <option value="duplicate">Duplicate — allow copying supplied records</option>
            <option value="synthetic">Synthetic — explicitly allow artificial test data</option>
          </select>
        </label>
        {!session ? <>
          <label>Instruction<textarea aria-label="AI instruction" value={instruction} onChange={e => setInstruction(e.target.value)} placeholder="Ask for an assessment, explanation, comparison, or file proposal…" /></label>
          <label>Additional uploaded sources (optional)<input type="file" multiple onChange={e => {
            const selected = Array.from(e.currentTarget.files ?? [])
            setAttachments(previous => [...previous, ...selected])
            e.currentTarget.value = ''
          }} /></label>
          <p>{sources.length} panel source(s), {attachments.length} additional source(s). Full context: {context.length.toLocaleString()} characters.</p>
          {attachments.map((file, i) => <div className="ai-row" key={i}><span>{file.name} ({file.size} bytes)</span><button onClick={() => setAttachments(previous => previous.filter((_, index) => index !== i))}>Remove {file.name}</button></div>)}
          <TaskDetails title="Review all source metadata and full panel context" value={{ sources: fileManifest(files), context }} />
          <div className="ai-row"><button disabled={!instruction.trim()} onClick={() => openConsent('create')}>Request AI task…</button>
            {actions.map(action => <button key={action.label} title={action.description} onClick={() => openConsent('create', [action.promptHint, instruction.trim()].filter(Boolean).join('\n\n'))}>{action.icon} {action.label}</button>)}
          </div>
        </> : <>
          <label>Follow-up instruction / clarification<textarea aria-label="AI follow-up" value={reply} onChange={e => setReply(e.target.value)} placeholder="Reply to this task using the original sources…" /></label>
          <button disabled={!reply.trim() || !task || needsRefresh} onClick={() => openConsent('reply')}>Send follow-up with fresh approval…</button>
        </>}
      </fieldset>
      {busy && <p role="status" aria-live="polite">⟳ {busy} Original results remain visible.</p>}
      {error && <div role="alert" className="ai-error">{error}</div>}
      {needsRefresh && <button disabled={!!busy || !!pending} onClick={refresh}>Refresh after error before a new approval</button>}
      {session && !task && !busy && <p className="ai-notice">No task ID was received. The server outcome may be unknown; check the Audit tab before creating another task. The original snapshot is retained below.</p>}
      {task && <AITaskCard task={task} disabled={locked || needsRefresh} policyChanged={policy !== task.data_policy || (!!task.plan && policy !== task.plan.data_policy)}
        onAction={action => action === 'adopt' || action === 'reject' ? void localAction(action) : openConsent(action)} onRefresh={refresh} />}
      {session && <>
        <TaskDetails title="Immutable original snapshot / deterministic results" value={{ ...session.snapshot, files: fileManifest(session.snapshot.files) }} />
        <TaskDetails title="Full conversation and revision history (rationale / evidence, not model reasoning)" value={session.history} />
      </>}
      <div className="ai-row"><button disabled={!!busy || !!pending} onClick={startNew}>Clear inputs / start new task (retain history)</button>
        {!!archive.length && <button disabled={!!busy || !!pending} onClick={() => setArchive([])}>Clear archived history from this view</button>}</div>
      {archive.map((previous, i) => <TaskDetails key={i} title={`Previous task — ${previous.task?.id || 'no ID received'} · ${previous.task?.state || 'unknown outcome'}`}
        value={{ ...previous, snapshot: { ...previous.snapshot, files: fileManifest(previous.snapshot.files) } }} />)}
      <small>Tab navigation retains this view in memory; a browser reload clears it. Clearing this view does not delete server-retained snapshots or audit records.</small>
    </div>}
    {pending && <AIConsentDialog action={pending.action === 'create' ? `Start ${pending.snapshot.panel} AI task (review only)` : `${pending.action} task ${pending.task?.id} revision ${pending.task?.revision}`}
      context={approvalContext} purpose={pending.action} onClose={() => setPending(null)} onApproved={requestId => void approved(pending, requestId)} />}
  </section>
}
