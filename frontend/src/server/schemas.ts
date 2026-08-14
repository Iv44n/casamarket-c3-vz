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
  estados: z.union([z.literal('all'), z.array(z.string())]).default('all')
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
}
export type AttentionsAnalytics = {
  incoming: DirectionAnalytics
  outgoing: DirectionAnalytics
}
export const INCIDENT_CATEGORIES = ['origen', 'tipo', 'ambito'] as const
export type IncidentCategory = (typeof INCIDENT_CATEGORIES)[number]
export type IncidentCategoryCount = { value: string; count: number }
export type IncidentAnalytics = {
  available: boolean
  total: number
  counts: Record<IncidentCategory, IncidentCategoryCount[]>
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
export type NoRunsYet = {
  status: 'no_runs_yet'
}
export type ExtractionStatus = RunSummary | NoRunsYet
export type MassiveExtractionStatus = MassiveRunSummary | NoRunsYet
