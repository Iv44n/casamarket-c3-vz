import { z } from 'zod'
export const REPORT_NAMES = [
  'attention',
  'outboundattention',
  'callincoming',
  'calloutgoing',
  'contacts'
] as const
export type ReportName = (typeof REPORT_NAMES)[number]
export const reportNameSchema = z.object({
  reportName: z.enum(REPORT_NAMES)
})
export const deleteFileSchema = z.object({
  filename: z.string().min(1)
})
export const reportSearchSchema = z.object({
  page: z.number().int().min(1).default(1),
  pageSize: z.number().int().min(1).max(200).default(25)
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
// "Today" in America/Lima specifically -- not the executing machine's local
// time, which (unlike the browser) could be anything once this runs
// server-side during SSR. Mirrors the backend's config.hoy() (see
// backend/app/config.py), which uses the same zone for the same reason: the
// server responds in GMT, so a naive local-clock "today" can drift by a day
// near midnight.
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
// Unlike dateFilterSchema above, backfill always targets one concrete day --
// there's no 'all' concept for "re-fetch every day from C3".
export const backfillRequestSchema = z.object({
  date: z.string().regex(ISO_DATE_REGEX)
})
// Ambito first: it's the richest dimension to drill into (ambito -> origen ->
// tipo), see DIMENSION_CHAIN in lib/incident-analytics.ts.
export const INCIDENT_CATEGORIES = ['ambito', 'origen', 'tipo'] as const
export type IncidentCategory = (typeof INCIDENT_CATEGORIES)[number]
export const ATENCIONES_VIEWS = ['resumen', 'incidencias'] as const
export type AtencionesView = (typeof ATENCIONES_VIEWS)[number]
export const attentionsSearchSchema = z.object({
  direction: z.enum(ATTENTION_FILTERS).default('all'),
  // Kept in sync by hand with AGENT_LIMIT_OPTIONS -- z.union needs a literal
  // per option, it can't be built from that array's mixed number/string type.
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
  // Which "estado" values to include in the charts. 'all' means no filter --
  // the set of valid estados comes from the backend data itself, so it can't
  // be validated against a fixed enum here. Once the user unchecks anything,
  // this becomes an explicit list (which may be empty, meaning "show none").
  estados: z.union([z.literal('all'), z.array(z.string())]).default('all'),
  // Which of the page's two tabs is showing.
  view: z.enum(ATENCIONES_VIEWS).default('resumen'),
  // Active dimension tab within the "incidencias" view.
  category: z.enum(INCIDENT_CATEGORIES).default('ambito'),
  // Defaults to today (not 'all') -- a fresh visit should show today's
  // atenciones, not every historical day merged together; 'all' is still
  // reachable via the clear ("Quitar filtro de fecha") button.
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
  // "Campaña" in the raw C3 export -- the case's business type (Soporte,
  // Implementacion, Activaciones, etc), not a marketing campaign.
  campaignCounts: {
    campana: string
    estado: string
    count: number
  }[]
}
export type AttentionsAnalytics = {
  incoming: DirectionAnalytics
  outgoing: DirectionAnalytics
}
export type IncidentRecord = {
  origen: string
  tipo: string
  ambito: string
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
export type MassiveRunSummary = {
  started_at: string
  finished_at: string
  ok: boolean
  massive: string | null
  massive_error: string | null
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
export type MassiveExtractionStatus = MassiveRunSummary | NoRunsYet
export type BackfillStatus = BackfillRunSummary | NoRunsYet
export type DownloadedFile = {
  report_name: ReportName
  date: string
  filename: string
  size_bytes: number
}
