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
export const reportRowsPageRequestSchema = reportNameSchema.extend({
  page: z.number().int().min(1).default(1),
  pageSize: z.number().int().min(1).max(200).default(50)
})
type JsonPrimitive = string | number | boolean | null
export type ReportRow = Record<string, JsonPrimitive>
export type ReportRowsPage = {
  total: number
  rows: ReportRow[]
}
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
const dateFilterValue = z.string().regex(ISO_DATE_REGEX)
export type DateFilter = z.infer<typeof dateFilterValue>
const dateEndValue = z.string().regex(ISO_DATE_REGEX).optional()
export const dateFilterSchema = z.object({
  date: dateFilterValue.default(todayIsoDate),
  dateEnd: dateEndValue
})
export const dateAndAgentesFilterSchema = dateFilterSchema.extend({
  agentes: z.union([z.literal('all'), z.array(z.string())]).default('all')
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
// Demand heatmap's date filter defaults to the current week (Monday-Sunday); the
// user picks any custom range from there via a calendar -- including a range
// spanning several weeks at once.
function pad2(value: number): string {
  return String(value).padStart(2, '0')
}
function formatIsoDateUtc(date: Date): string {
  return `${date.getUTCFullYear()}-${pad2(date.getUTCMonth() + 1)}-${pad2(date.getUTCDate())}`
}
export function addDaysIso(isoDate: string, days: number): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  return formatIsoDateUtc(
    new Date(Date.UTC(year, month - 1, day) + days * 24 * 60 * 60 * 1000)
  )
}
export function mondayOfWeek(isoDate: string): string {
  const [year, month, day] = isoDate.split('-').map(Number)
  const jsDayOfWeek = new Date(Date.UTC(year, month - 1, day)).getUTCDay()
  const isoDayOfWeek = jsDayOfWeek === 0 ? 7 : jsDayOfWeek // 1=Mon..7=Sun
  return addDaysIso(isoDate, -(isoDayOfWeek - 1))
}
export function firstDayOfMonthIso(isoDate: string): string {
  const [year, month] = isoDate.split('-')
  return `${year}-${month}-01`
}
export function enumerateIsoDates(from: string, to: string): string[] {
  const days: string[] = []
  let cursor = from
  while (cursor <= to) {
    days.push(cursor)
    cursor = addDaysIso(cursor, 1)
  }
  return days
}
function defaultDemandWeekStart(): string {
  return mondayOfWeek(todayIsoDate())
}
function defaultDemandWeekEnd(): string {
  return addDaysIso(defaultDemandWeekStart(), 6)
}
export const backfillRequestSchema = z.object({
  date: z.string().regex(ISO_DATE_REGEX)
})
export const historicalBackfillRequestSchema = z.object({
  dateInit: z.string().regex(ISO_DATE_REGEX).optional(),
  dateEnd: z.string().regex(ISO_DATE_REGEX).optional()
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
  agentes: z.union([z.literal('all'), z.array(z.string())]).default('all'),
  view: z.enum(ATENCIONES_VIEWS).default('resumen'),
  category: z.enum(INCIDENT_CATEGORIES).default('ambito'),
  campana: z.string().default('all'),
  plan: z.string().default('all'),
  date: dateFilterValue.default(todayIsoDate),
  dateEnd: dateEndValue,
  demorasPage: z.number().int().min(1).default(1)
})
export type AttentionsSearch = z.infer<typeof attentionsSearchSchema>
export const tendenciasHistoricasSearchSchema =
  dateAndAgentesFilterSchema.extend({
    date: dateFilterValue.default(defaultDemandWeekStart),
    dateEnd: dateEndValue.default(defaultDemandWeekEnd)
  })
export type TendenciasHistoricasSearch = z.infer<
  typeof tendenciasHistoricasSearchSchema
>
export type EstadosFilter = AttentionsSearch['estados']
export type AgentesFilter = AttentionsSearch['agentes']
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
export const attentionRecordsPageRequestSchema = z.object({
  direction: z.enum(ATTENTION_FILTERS).default('all'),
  estados: z.union([z.literal('all'), z.array(z.string())]).default('all'),
  campana: z.string().default('all'),
  agentes: z.union([z.literal('all'), z.array(z.string())]).default('all'),
  date: dateFilterValue.default(todayIsoDate),
  dateEnd: dateEndValue,
  page: z.number().int().min(1).default(1),
  pageSize: z.number().int().min(1).max(200).default(50)
})
export type AttentionRecordsPageRequest = z.infer<
  typeof attentionRecordsPageRequestSchema
>
export type AttentionRecordsPage = {
  total: number
  staleCount: number
  records: AttentionRecord[]
  availablePlans: string[]
}
export type DemandBucketCount = {
  dayOfWeek: number
  hour: number
  count: number
}
export type DemandAnalytics = {
  available: boolean
  availableAgentes: string[]
  buckets: DemandBucketCount[]
}
export type DailyCaseCount = {
  date: string // yyyy-mm-dd (Lima)
  count: number
}
export type DailyTrendAnalytics = {
  available: boolean
  days: DailyCaseCount[]
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
  fechaFinal: string
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
  date_init: string
  date_end: string
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
