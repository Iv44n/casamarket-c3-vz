import { z } from 'zod'
export const REPORT_NAMES = [
  'attention',
  'outboundattention',
  'callincoming',
  'calloutgoing',
  'contacts',
  'transfer'
] as const
export type ReportName = (typeof REPORT_NAMES)[number]
export const reportNameSchema = z.object({
  reportName: z.enum(REPORT_NAMES)
})
export const reportSearchSchema = z.object({
  page: z.number().int().min(1).default(1),
  pageSize: z.number().int().min(1).max(200).default(50)
})
export type ReportSearch = z.infer<typeof reportSearchSchema>
type JsonPrimitive = string | number | boolean | null
export type ReportRow = Record<string, JsonPrimitive>
export type ReportSummary = {
  rowCount: number
  columns: {
    name: string
    populated: number
  }[]
}
export const ATTENTION_FILTERS = ['all', 'incoming', 'outgoing'] as const
export type AttentionFilter = (typeof ATTENTION_FILTERS)[number]
export type AttentionDirection = Exclude<AttentionFilter, 'all'>
export const AGENT_LIMIT_OPTIONS = [5, 10, 15, 20, 25, 'all'] as const
export type AgentLimit = (typeof AGENT_LIMIT_OPTIONS)[number]

const ISO_DATE_REGEX = /^\d{4}-\d{2}-\d{2}$/
const dateFilterValue = z.union([
  z.literal('all'),
  z.string().regex(ISO_DATE_REGEX)
])
export type DateFilter = z.infer<typeof dateFilterValue>
export const dateFilterSchema = z.object({
  date: dateFilterValue.default('all')
})
export function todayIsoDate(): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Lima',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(new Date())
  const part = (type: 'year' | 'month' | 'day') =>
    parts.find(p => p.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}
export const backfillRequestSchema = z.object({
  date: z.string().regex(ISO_DATE_REGEX)
})

export const INCIDENT_CATEGORIES = [
  'tipo',
  'origen',
  'ambito',
  'resultado'
] as const
export type IncidentCategory = (typeof INCIDENT_CATEGORIES)[number]
export const ATENCIONES_VIEWS = ['resumen', 'incidencias', 'demoras'] as const
export type AtencionesView = (typeof ATENCIONES_VIEWS)[number]
export const attentionsSearchSchema = z.object({
  direction: z.enum(ATTENTION_FILTERS).default('all'),
  agentLimit: z
    .union([
      z.literal(5),
      z.literal(10),
      z.literal(15),
      z.literal(20),
      z.literal(25),
      z.literal('all')
    ])
    .default(10),
  estados: z.union([z.literal('all'), z.array(z.string())]).default('all'),
  view: z.enum(ATENCIONES_VIEWS).default('resumen'),
  category: z.enum(INCIDENT_CATEGORIES).default('ambito'),
  agente: z.string().default('all'),
  campana: z.string().default('all'),
  plan: z.string().default('all'),
  date: dateFilterValue.default(todayIsoDate)
})
export type AttentionsSearch = z.infer<typeof attentionsSearchSchema>
export type EstadosFilter = AttentionsSearch['estados']
export const DIRECTION_REPORT_NAME: Record<AttentionDirection, ReportName> = {
  incoming: 'attention',
  outgoing: 'outboundattention'
}
export type DirectionAnalytics = {
  available: boolean
  total: number
  statusCounts: {
    estado: string
    count: number
  }[]
  agentCounts: {
    agente: string
    estado: string
    count: number
  }[]
  campaignCounts: {
    campana: string
    estado: string
    count: number
  }[]
  agentCampaignCounts: {
    agente: string
    campana: string
    estado: string
    count: number
  }[]
  agentAttentionSeconds: {
    agente: string
    estado: string
    totalSeconds: number
    sampleCount: number
  }[]
  attentionRecords: AttentionRecord[]
}
export type TransferHop = {
  agenteOrigen: string
  destType: string
  destino: string
  epochMs: number
}
export type AttentionRecord = {
  idAtencion: string
  cliente: string
  plan: string
  rubro: string
  agente: string
  campana: string
  direction: AttentionDirection
  estado: string
  startEpochMs: number | null
  closeEpochMs: number | null
  transferredBy: string | null
  transferDestType: string | null
  transferDestino: string | null
  transferChain: TransferHop[]
  withAgentSinceMs: number | null
}
export type AttentionsAnalytics = {
  incoming: DirectionAnalytics
  outgoing: DirectionAnalytics
}
export type IncidentRecord = {
  categoryOrder: IncidentCategory[]
  origen: string
  tipo: string
  ambito: string
  resultado: string
  descripcion: string
  agente: string
  campana: string
  estado: string
  fecha: string
  hora: string
  horaFinal: string
  tiempoSegundos: number | null
}
export type IncidentAnalytics = {
  available: boolean
  total: number
  records: IncidentRecord[]
}
export type JobSummary = {
  name: string
  ok: boolean
  error: string | null
  size_bytes: number | null
  elapsed_seconds: number | null
}
export type RunSummary = {
  started_at: string
  finished_at: string
  ok: boolean
  jobs: JobSummary[]
}
export type BackfillRunSummary = {
  started_at: string
  finished_at: string
  ok: boolean
  target_date: string
  jobs: JobSummary[]
}
export type NoRunsYet = {
  status: 'no_runs_yet'
}
export type ExtractionStatus = RunSummary | NoRunsYet
export type BackfillStatus = BackfillRunSummary | NoRunsYet
export type ContactsSyncStatus = RunSummary | NoRunsYet
export type HistoricalRunSummary = {
  started_at: string
  finished_at: string
  ok: boolean
  window_days: number
  jobs: JobSummary[]
}
export type HistoricalBackfillPhase = 'idle' | 'running' | 'done' | 'error'
export type HistoricalBackfillStatus = {
  phase: HistoricalBackfillPhase
  started_at: string | null
  finished_at: string | null
  result: HistoricalRunSummary | null
  error: string | null
}
