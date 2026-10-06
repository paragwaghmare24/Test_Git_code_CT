import { useState } from 'react'
import AIAssistBar, { AITabAction } from './AIAssistBar'

const actions: AITabAction[] = [
  { label: 'Assess EDI', icon: '✓', description: 'Propose an evidence-based assessment', promptHint: 'Assess the supplied EDI and explain findings with evidence and limitations.' },
  { label: 'Propose files', icon: '+', description: 'Plan outputs before requesting execution approval', promptHint: 'Propose files to meet these requirements. Ask about missing values; do not assume synthetic data.' },
  { label: 'Interpret guide', icon: '⊞', description: 'Use configured guide sources', promptHint: 'Interpret relevant configured companion guide source texts and cite evidence.' },
  { label: 'Analyze response', icon: '↩', description: 'Explain acknowledgment or claim response', promptHint: 'Analyze the supplied acknowledgment and explain the response and recommended next steps.' },
]

export default function AIPanel() {
  const [context, setContext] = useState('')
  return <div style={{ padding: 24 }}>
    <h1 style={{ color: '#1f4e79', fontSize: 20 }}>AI Assistance & Chat</h1>
    <p>Gemini-led tasks with explicit consent, source evidence, reviewed assessments and separately approved file proposals.</p>
    <label>Full source context / requirements
      <textarea aria-label="AI source context" value={context} onChange={e => setContext(e.target.value)}
        style={{ display: 'block', width: '100%', minHeight: 120, boxSizing: 'border-box', marginTop: 8, padding: 12 }}
        placeholder="Paste requirements, EDI, or full result data. Attach files in the AI bar below." />
    </label>
    <AIAssistBar tabName="AI Assistance" context={context} actions={actions} initialExpanded />
  </div>
}
