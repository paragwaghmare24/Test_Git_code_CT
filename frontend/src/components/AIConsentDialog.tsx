import React, { useEffect, useRef, useState } from 'react'
import { requestAI, approveAI } from '../api'

interface Props {
  onClose: () => void
  action: string
  context?: string
  purpose?: string
  onApproved: (requestId: string) => void
}

const s: Record<string, React.CSSProperties> = {
  overlay: {
    position: 'fixed', inset: 0, background: 'rgba(0,0,0,0.5)',
    display: 'flex', alignItems: 'center', justifyContent: 'center', zIndex: 1000,
  },
  dialog: {
    background: '#fff', borderRadius: 12, padding: 32, maxWidth: 480, width: '90%',
    boxShadow: '0 8px 32px rgba(0,0,0,0.2)', maxHeight: '90vh', overflowY: 'auto',
  },
  title: { fontSize: 18, fontWeight: 700, color: '#1F4E79', marginBottom: 8 },
  warning: { background: '#fff8e1', border: '1px solid #ffe082', borderRadius: 8, padding: '12px 16px', marginBottom: 16, fontSize: 14 },
  action: { background: '#e3f0fa', borderRadius: 8, padding: '10px 14px', marginBottom: 16, fontSize: 14, fontFamily: 'monospace' },
  btnRow: { display: 'flex', gap: 12, justifyContent: 'flex-end', marginTop: 16 },
  btnApprove: { padding: '10px 24px', background: '#2e7d32', color: '#fff', border: 'none', borderRadius: 6, cursor: 'pointer', fontWeight: 700 },
  btnCancel: { padding: '10px 24px', background: '#f5f5f5', color: '#333', border: '1px solid #ddd', borderRadius: 6, cursor: 'pointer', fontWeight: 600 },
  status: { fontSize: 13, color: '#888', marginTop: 8 },
}

export default function AIConsentDialog({ onClose, action, context = '', purpose = 'create', onApproved }: Props) {
  const [step, setStep] = useState<'confirm' | 'requesting' | 'pending' | 'approved' | 'error'>('confirm')
  const [requestId, setRequestId] = useState('')
  const [error, setError] = useState('')
  const active = useRef(true)
  const submitting = useRef(false)
  const cancelRef = useRef<HTMLButtonElement>(null)
  useEffect(() => {
    active.current = true
    const previousFocus = document.activeElement as HTMLElement | null
    cancelRef.current?.focus()
    return () => { active.current = false; previousFocus?.focus() }
  }, [])

  const close = () => { active.current = false; onClose() }

  const handleApprove = async () => {
    if (submitting.current || !active.current) return
    submitting.current = true
    setStep('requesting')
    try {
      const reqRes = await requestAI(action, context)
      if (!active.current) return
      const rid = reqRes.data.request_id
      setRequestId(rid)
      setStep('pending')

      // Auto-approve after user clicks (this is the explicit approval)
      await approveAI(rid)
      if (!active.current) return
      setStep('approved')
      onApproved(rid)
    } catch (e: any) {
      if (active.current) {
        const detail = e.response?.data?.detail ?? e.message
        setError(typeof detail === 'string' ? detail : JSON.stringify(detail))
        setStep('error')
      }
    } finally {
      submitting.current = false
    }
  }

  return (
    <div style={s.overlay}>
      <div style={s.dialog} role="dialog" aria-modal="true" aria-labelledby="ai-consent-title"
        onKeyDown={e => {
          if (e.key === 'Escape') close()
          if (e.key === 'Tab') {
            const controls = Array.from(e.currentTarget.querySelectorAll<HTMLElement>('button:not([disabled]), summary, [tabindex="0"]'))
            const first = controls[0], last = controls[controls.length - 1]
            if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last?.focus() }
            else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first?.focus() }
          }
        }}>
        <div id="ai-consent-title" style={s.title}>⚠ Gemini Approval — This Action Only</div>
        <div style={s.warning}>
          <strong>AI is disabled by default.</strong><br />
          This action sends approved source content and context to the <strong>Gemini external API</strong>,
          including any sensitive healthcare or personal data they contain. Configured companion guide
          source texts may also be used. Task snapshots, sources and history are retained locally by the server.<br /><br />
          {purpose === 'execute'
            ? 'This approval authorizes file creation only within the exact displayed proposal and revision. Original files and deterministic results remain unchanged.'
            : purpose === 'retrieve'
              ? 'This approval authorizes retrieval of the exact URL shown below, once, for the stated reason, and use of the retrieved content by Gemini. It does not authorize other URLs.'
              : purpose === 'continue'
                ? 'This approval resumes the existing task scope, including any previously approved execution. New scope or external retrieval requires separate approval.'
                : 'This approval authorizes review or conversation only. It does NOT authorize file creation, assessment adoption, or external retrieval.'}
          <br />Review all approved inputs below. An approval is consumed once and cannot be reused.
        </div>

        <div>
          <strong style={{ fontSize: 13, color: '#444' }}>Requested Action:</strong>
          <div style={s.action}>{action}</div>
          {context && (
            <>
              <details open>
                <summary style={{ fontSize: 13, color: '#444' }}>Full approval snapshot (sources, context, proposal / exact URL and revision)</summary>
                <pre tabIndex={0} style={{ ...s.action, marginTop: 4, maxHeight: 280, overflow: 'auto', whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>{context}</pre>
              </details>
            </>
          )}
        </div>

        {step === 'error' && (
          <div role="alert" style={{ color: '#c62828', fontSize: 13, marginTop: 8 }}>Error: {error}. Close and request fresh consent to try again.</div>
        )}
        {step === 'approved' && (
          <div style={{ color: '#2e7d32', fontSize: 13, marginTop: 8 }}>
            ✓ Approved. AI will assist with this action only. Request ID: {requestId}
          </div>
        )}

        <div style={s.btnRow}>
          <button ref={cancelRef} onClick={close} style={s.btnCancel}>Cancel</button>
          {step === 'confirm' && (
            <button onClick={handleApprove} style={s.btnApprove}>
              Approve AI for This Action
            </button>
          )}
          {step === 'approved' && (
            <button onClick={close} style={s.btnApprove}>Close</button>
          )}
        </div>

        <p style={s.status}>
          {(step === 'requesting' || step === 'pending') ? 'Recording one-time approval…' : 'Gemini external API · Fresh approval for every invocation · No deterministic fallback.'}
        </p>
      </div>
    </div>
  )
}
