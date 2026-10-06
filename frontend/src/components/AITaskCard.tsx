import { AIAssessment, AITask, AITaskAction } from '../api'

export const displayValue = (value: unknown): string =>
  typeof value === 'string' ? value : JSON.stringify(value, null, 2) ?? '(not provided)'

export function TaskDetails({ title, value }: { title: string; value: unknown }) {
  return <details className="ai-details"><summary>{title}</summary><pre>{displayValue(value)}</pre></details>
}

function Assessment({ assessment, title }: { assessment: AIAssessment; title: string }) {
  return <section className="ai-assessment" aria-label={title}>
    <h3>{title} — {assessment.verdict}</h3>
    <p className="ai-text">{assessment.message}</p>
    <h4>Findings, rationale and evidence</h4>
    {assessment.findings?.map((finding, i) => <div className="ai-finding" key={i}>
      <strong>{finding.classification}</strong><p className="ai-text">{finding.description}</p>
      <TaskDetails title="Evidence" value={finding.evidence} />
    </div>)}
    <TaskDetails title="Limitations" value={assessment.limitations} />
  </section>
}

const nextStep: Record<string, string> = {
  answered: 'Review the answer or send a follow-up on this same task.',
  clarification: 'Answer the questions below; each reply needs fresh Gemini approval.',
  assessment_pending: 'Review the proposed assessment, then explicitly adopt or reject it. Adoption does not change the deterministic panel.',
  plan_pending: 'Review every output, change, assumption and data policy. Only Approve file proposal opens execution consent.',
  external_pending: 'Review the exact URL and reason. Only Retrieve this URL opens retrieval consent.',
  paused: 'Review progress and approve Continue to resume the existing scope.',
  failed: 'Review the error. Refresh task status before approving Continue; there is no deterministic fallback.',
  completed: 'Download available artifacts or send a follow-up. Further file work needs a new proposal.',
  adopted: 'The adopted assessment is the primary AI result. The original deterministic results remain unchanged.',
  rejected: 'The proposal was rejected. Send a revised instruction or start a new task.',
}

// Artifacts must remain local task downloads, never model-supplied external links.
function artifactURL(taskId: string, value: string): string | null {
  try {
    const url = new URL(value, window.location.origin)
    if (url.origin !== window.location.origin || url.search || url.hash) return null
    const prefix = `/api/ai/tasks/${encodeURIComponent(taskId)}/artifacts/`
    return url.pathname.startsWith(prefix) ? url.pathname : null
  } catch { return null }
}

interface Props {
  task: AITask
  disabled: boolean
  policyChanged: boolean
  onAction: (action: AITaskAction) => void
  onRefresh: () => void
}

export default function AITaskCard({ task, disabled, policyChanged, onAction, onRefresh }: Props) {
  return <article className="ai-task" aria-label="AI task result">
    <header className="ai-row">
      <strong>Gemini task · {task.state.replace(/_/g, ' ')}</strong>
      <span>{task.ai_model || 'Model not reported'} · revision {task.revision}</span>
      <button type="button" disabled={disabled} onClick={onRefresh}>Refresh status (no AI call)</button>
    </header>
    <small>Task ID: {task.id} · Data policy: {task.data_policy}</small>
    {task.adopted_assessment && <Assessment title="Primary AI result — adopted assessment" assessment={task.adopted_assessment} />}
    <p className="ai-text">{task.message}</p>
    {!!task.error && <div role="alert" className="ai-error">{displayValue(task.error)}</div>}
    <p className="ai-notice"><strong>Next step:</strong> {nextStep[task.state] || 'Refresh status to see the next available action.'}</p>
    {!!task.questions?.length && <section><h3>Questions</h3><ol>{task.questions.map((question, i) => <li key={i} className="ai-text">{question}</li>)}</ol></section>}
    {task.assessment && <>
      <Assessment title={task.state === 'assessment_pending' ? 'Proposed assessment — not adopted' : 'Assessment proposal (retained)'} assessment={task.assessment} />
      {task.state === 'assessment_pending' && <div className="ai-row">
        <button disabled={disabled} onClick={() => onAction('adopt')}>Adopt assessment (no AI call)</button>
        <button disabled={disabled} onClick={() => onAction('reject')}>Reject assessment</button>
      </div>}
    </>}
    {task.plan && <section className="ai-proposal">
      <h3>{task.state === 'plan_pending' ? 'File proposal — awaiting approval' : 'File proposal (retained)'}</h3>
      <p className="ai-text">{task.plan.summary}</p>
      <strong>Proposed data policy: {task.plan.data_policy}</strong>
      <TaskDetails title="All proposed changes" value={task.plan.changes} />
      <TaskDetails title="Assumptions" value={task.plan.assumptions} />
      <h4>Proposed outputs (not downloads)</h4>
      {task.plan.outputs?.map((output, i) => <div className="ai-finding" key={i}>
        <strong>{output.name} · {output.format}</strong>
        <p className="ai-text">{output.description}</p>
        <p>Record count: {output.record_count ?? 'Not specified'} · Record segment: {output.record_segment || 'Not specified'}</p>
      </div>)}
      {task.state === 'plan_pending' && <>
        <p>No files are created by this proposal. Approval below requests separate Gemini execution consent.</p>
        {policyChanged && <p className="ai-notice">Send a follow-up to revise the plan's data policy before executing.</p>}
        <div className="ai-row">
          <button disabled={disabled || policyChanged} onClick={() => onAction('execute')}>Approve file proposal…</button>
          <button disabled={disabled} onClick={() => onAction('reject')}>Reject file proposal</button>
        </div>
      </>}
    </section>}
    {task.external && <section className="ai-proposal">
      <h3>{task.state === 'external_pending' ? 'External reference — permission required' : 'External reference (retained)'}</h3>
      <p className="ai-text"><strong>Exact URL:</strong> {task.external.url}</p>
      <p className="ai-text"><strong>Reason:</strong> {task.external.reason}</p>
      {task.state === 'external_pending' && <div className="ai-row">
        <button disabled={disabled} onClick={() => onAction('retrieve')}>Retrieve this URL…</button>
        <button disabled={disabled} onClick={() => onAction('reject')}>Reject retrieval</button>
      </div>}
    </section>}
    {(task.state === 'paused' || task.state === 'failed') && <button disabled={disabled} onClick={() => onAction('continue')}>Continue with fresh approval…</button>}
    {!!task.artifacts?.length && <section><h3>Available artifacts</h3>{task.artifacts.map(artifact => {
      const url = artifactURL(task.id, artifact.url)
      return <div className="ai-finding" key={artifact.id}>
        {url ? <a href={url} download={artifact.name}>Download {artifact.name}</a> : <strong>{artifact.name} — unsafe or unsupported download URL blocked</strong>}
        <p>{artifact.size.toLocaleString()} bytes</p><p className="ai-text">SHA-256: {artifact.sha256}</p>
        <TaskDetails title="Artifact checks (not a guarantee of compliance)" value={artifact.checks} />
      </div>
    })}</section>}
    <TaskDetails title="Source manifest — full list and hashes" value={task.sources ?? []} />
    <TaskDetails title="Source coverage / omissions" value={task.coverage_summary ?? task.coverage ?? 'No coverage reported; do not assume all sources were reviewed.'} />
    <TaskDetails title="Task event history" value={task.events ?? []} />
  </article>
}