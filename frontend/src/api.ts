import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export const parseEDI = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/parse', fd)
}

export const validateEDI = (file: File, partnerName = '') => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('partner_name', partnerName)
  return api.post('/validate', fd)
}

export const generateEDIFromFile = (file: File, transactionType: string) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('transaction_type', transactionType)
  return api.post('/generate/upload', fd)
}

export const generateEDI = (transactionType: string, data: Record<string, unknown>) =>
  api.post('/generate', { transaction_type: transactionType, data })

export const compareEDI = (fileA: File, fileB: File) => {
  const fd = new FormData()
  fd.append('file_a', fileA)
  fd.append('file_b', fileB)
  return api.post('/compare', fd)
}

export const exportComparisonExcel = (fileA: File, fileB: File) => {
  const fd = new FormData()
  fd.append('file_a', fileA)
  fd.append('file_b', fileB)
  return api.post('/compare/export', fd, { responseType: 'blob' })
}

export const proposeCorrections = (file: File, partnerName = '') => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('partner_name', partnerName)
  return api.post('/correct/propose', fd)
}

export const analyze999 = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/analyze/999', fd)
}

export const analyze277ca = (file: File) => {
  const fd = new FormData()
  fd.append('file', file)
  return api.post('/analyze/277ca', fd)
}

export const exportExcel = (file: File, partnerName = '', runValidation = true) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('partner_name', partnerName)
  fd.append('run_validation', runValidation.toString())
  return api.post('/export', fd)
}

export const batchProcess = (files: File[], partnerName = '') => {
  const fd = new FormData()
  files.forEach(f => fd.append('files', f))
  fd.append('partner_name', partnerName)
  return api.post('/batch', fd)
}

export const getAuditLog = (date?: string) =>
  api.get('/audit', { params: date ? { date } : {} })

export const listCompanionGuides = () => api.get('/companion-guides')

export const getGuideRules = (txType: string) =>
  api.get(`/companion-guides/${txType}`)

export const searchGuideRules = (txType: string, q: string) =>
  api.get(`/companion-guides/${txType}/search`, { params: { q } })

export const uploadTPMapping = (file: File, partnerName: string, txType: string) => {
  const fd = new FormData()
  fd.append('file', file)
  fd.append('partner_name', partnerName)
  fd.append('transaction_type', txType)
  return api.post('/tp-mappings/upload', fd)
}

export const listTPMappings = () => api.get('/tp-mappings')

export const requestAI = (action: string, context = '') =>
  api.post('/ai/request', { action, context })

export const approveAI = (requestId: string) =>
  api.post(`/ai/approve/${requestId}`)

export type AIDataPolicy = 'undecided' | 'supplied' | 'duplicate' | 'synthetic'
export type AITaskAction = 'adopt' | 'reject' | 'execute' | 'retrieve' | 'continue' | 'reply'
export type AITaskState = 'answered' | 'clarification' | 'assessment_pending' | 'plan_pending'
  | 'external_pending' | 'paused' | 'failed' | 'completed' | 'adopted' | 'rejected'

export interface AIAssessment {
  message: string
  verdict: 'PASS' | 'FAIL' | 'REVIEW'
  findings: { classification: string; description: string; evidence: unknown[] }[]
  limitations: string[]
}

export interface AITask {
  id: string
  revision: number
  state: AITaskState
  panel: string
  message: string
  questions?: string[]
  assessment?: AIAssessment | null
  adopted_assessment?: AIAssessment | null
  plan?: {
    summary: string
    changes: string[]
    assumptions: string[]
    data_policy: AIDataPolicy
    outputs: { name: string; format: string; description: string; record_count?: number | null; record_segment?: string }[]
  } | null
  external?: { url: string; reason: string } | null
  artifacts?: { id: string; name: string; size: number; sha256: string; checks: unknown; url: string }[]
  error?: unknown
  events?: { action: string; result: string; at: string }[]
  data_policy: AIDataPolicy
  ai_model?: string
  sources?: { id: string; name: string; sha256: string; length: number; kind: string }[]
  coverage?: unknown
  coverage_summary?: { document_id: string; name: string; kind: string; characters_read: number; total_characters: number; complete: boolean }[]
}

export const createAITask = (input: {
  request_id: string; panel: string; instruction: string; context: string
  data_policy: AIDataPolicy; files?: readonly File[]
}) => {
  const fd = new FormData()
  fd.append('request_id', input.request_id)
  fd.append('panel', input.panel)
  fd.append('instruction', input.instruction)
  fd.append('context', input.context)
  fd.append('data_policy', input.data_policy)
  input.files?.forEach(file => fd.append('files', file))
  return api.post<AITask>('/ai/tasks', fd)
}

export const getAITask = (id: string) => api.get<AITask>(`/ai/tasks/${encodeURIComponent(id)}`)

export const actAITask = (id: string, input: {
  revision: number; action: AITaskAction; request_id?: string; message?: string; data_policy?: AIDataPolicy
}) => api.post<AITask>(`/ai/tasks/${encodeURIComponent(id)}/actions`, input)

export const downloadExport = (filename: string) =>
  api.get(`/export/${filename}`, { responseType: 'blob' })

export default api
