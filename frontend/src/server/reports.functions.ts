import { createServerFn } from '@tanstack/react-start'
import {
  epochMsToLimaDate,
  filterRowsByDate,
  parseLimaDateTime,
  parseLimaIsoDateTime
} from '#/lib/date-filter'
import { parseDurationToSeconds } from '#/lib/duration'
import {
  deriveIncidentAnalytics,
  INCIDENT_DATE_FIELD,
  INCIDENT_SOURCE_REPORTS
} from '#/lib/incident-analytics'
import {
  fetchAttentionRecordsPage,
  fetchBackfillStatus,
  fetchBenchmarkResults,
  fetchBenchmarkRunStatus,
  fetchContactsSyncStatus,
  fetchExtractionStatus,
  fetchHistoricalBackfillStatus,
  fetchReportDailyCounts,
  fetchReportRows,
  fetchReportRowsHistory,
  fetchReportRowsPage,
  triggerBackfillExtraction,
  triggerBenchmarkAnalysis,
  triggerContactsSync,
  triggerExtractionRefresh,
  triggerHistoricalBackfill
} from './backend.server'
import type {
  AgentesFilter,
  AttentionDirection,
  AttentionRecord,
  AttentionRecordsPage,
  AttentionsAnalytics,
  DailyTrendAnalytics,
  DemandAnalytics,
  DemandBucketCount,
  DirectionAnalytics,
  IncidentAnalytics,
  ReportRow,
  ReportRowsPage,
  ReportSummary,
  TransferHop
} from './schemas'
import {
  attentionRecordsPageRequestSchema,
  backfillRequestSchema,
  benchmarkResultsRequestSchema,
  benchmarkRunRequestSchema,
  dateAndAgentesFilterSchema,
  dateFilterSchema,
  enumerateIsoDates,
  historicalBackfillRequestSchema,
  reportNameSchema,
  reportRowsPageRequestSchema
} from './schemas'

const ATTENTION_DATE_FIELD = 'Fecha registro'

type ContactInfo = { plan: string; rubro: string }

function normalizePhoneKey(value: unknown): string | null {
  if (typeof value !== 'string' && typeof value !== 'number') return null
  const digits = String(value).replace(/\D/g, '')
  return digits.length >= 9 ? digits.slice(-9) : null
}

function cleanContactField(value: unknown): string {
  return typeof value === 'string' && value.trim() !== '-' ? value.trim() : ''
}

function buildContactsIndex(rows: ReportRow[]): Map<string, ContactInfo> {
  const index = new Map<string, ContactInfo>()
  for (const row of rows) {
    const key = normalizePhoneKey(row.Telefono)
    if (key === null) continue
    index.set(key, {
      plan: cleanContactField(row.Plan),
      rubro: cleanContactField(row.Rubro)
    })
  }
  return index
}

function buildTransferChainIndex(
  rows: ReportRow[]
): Map<string, TransferHop[]> {
  const index = new Map<string, TransferHop[]>()
  for (const row of rows) {
    const idRaw = row['Atención ID']
    if (typeof idRaw !== 'string' && typeof idRaw !== 'number') continue
    const id = String(idRaw).trim()
    const epochMs = parseLimaIsoDateTime(row.Fecha, row.Hora)
    if (epochMs === null) continue
    const agenteOrigen = row['Agente Origen']
    const destType = row['Tipo destino']
    const destino = row.Destino
    const chain = index.get(id) ?? []
    chain.push({
      agenteOrigen: typeof agenteOrigen === 'string' ? agenteOrigen : '',
      destType: typeof destType === 'string' ? destType : '',
      destino: typeof destino === 'string' ? destino : '',
      epochMs
    })
    index.set(id, chain)
  }
  for (const chain of index.values()) {
    chain.sort((a, b) => a.epochMs - b.epochMs)
  }
  return index
}

export const getReportRows = createServerFn({ method: 'GET' })
  .validator(reportNameSchema)
  .handler(async ({ data }) => fetchReportRows(data.reportName))

export const getReportRowsPage = createServerFn({ method: 'GET' })
  .validator(reportRowsPageRequestSchema)
  .handler(
    async ({ data }): Promise<ReportRowsPage | null> =>
      fetchReportRowsPage(data.reportName, data.page, data.pageSize)
  )

const SUMMARY_CACHE_TTL_MS = 5 * 60 * 1000
type SummaryCache = {
  summary: ReportSummary | null
  fetchedAt: number
}
const _summaryCache = new Map<string, SummaryCache>()

export const getReportSummary = createServerFn({ method: 'GET' })
  .validator(reportNameSchema)
  .handler(async ({ data }): Promise<ReportSummary | null> => {
    const now = Date.now()
    const cached = _summaryCache.get(data.reportName)
    if (cached && now - cached.fetchedAt < SUMMARY_CACHE_TTL_MS) {
      return cached.summary
    }
    const rows = await fetchReportRows(data.reportName)
    if (rows === null) {
      _summaryCache.set(data.reportName, { summary: null, fetchedAt: now })
      return null
    }
    const columns = new Map<string, number>()
    for (const row of rows) {
      for (const [key, value] of Object.entries(row)) {
        if (
          value !== null &&
          value !== undefined &&
          value !== '' &&
          value !== '-'
        ) {
          columns.set(key, (columns.get(key) ?? 0) + 1)
        }
      }
    }
    const summary: ReportSummary = {
      rowCount: rows.length,
      columns: [...columns.entries()]
        .map(([name, populated]) => ({ name, populated }))
        .sort((a, b) => b.populated - a.populated)
    }
    _summaryCache.set(data.reportName, { summary, fetchedAt: now })
    return summary
  })

function parseStartEpochMs(row: ReportRow): number | null {
  return (
    parseLimaDateTime(row['Fecha inicio'], row['Hora inicio']) ??
    parseLimaDateTime(row['Fecha registro'], row['Hora registro'])
  )
}
function estadoKeyOf(row: ReportRow): string {
  const estado = row.Estado
  return typeof estado === 'string' && estado.trim() !== ''
    ? estado
    : 'Sin estado'
}
function agenteKeyOf(row: ReportRow): string {
  const agente = row.Agente
  return typeof agente === 'string' &&
    agente.trim() !== '' &&
    agente.trim() !== '-'
    ? agente
    : 'Sin agente'
}
function agenteAllowed(row: ReportRow, agentes: AgentesFilter): boolean {
  return agentes === 'all' || agentes.includes(agenteKeyOf(row))
}
function campanaKeyOf(row: ReportRow): string {
  const campana = row.Campaña
  return typeof campana === 'string' && campana.trim() !== ''
    ? campana
    : 'Sin campaña'
}
function deriveDirectionAnalytics(
  rows: ReportRow[] | null
): DirectionAnalytics {
  if (rows === null) {
    return {
      available: false,
      total: 0,
      statusCounts: [],
      agentCounts: [],
      campaignCounts: [],
      agentCampaignCounts: [],
      agentAttentionSeconds: []
    }
  }
  const statusCounts = new Map<string, number>()
  const agentEstadoCounts = new Map<string, Map<string, number>>()
  const campaignEstadoCounts = new Map<string, Map<string, number>>()
  const agentCampaignEstadoCounts = new Map<
    string,
    Map<string, Map<string, number>>
  >()
  const agentEstadoAttentionSeconds = new Map<
    string,
    Map<string, { totalSeconds: number; sampleCount: number }>
  >()

  for (const row of rows) {
    const estadoKey = estadoKeyOf(row)
    statusCounts.set(estadoKey, (statusCounts.get(estadoKey) ?? 0) + 1)
    const agenteKey = agenteKeyOf(row)
    const agentCounts = agentEstadoCounts.get(agenteKey) ?? new Map()
    agentCounts.set(estadoKey, (agentCounts.get(estadoKey) ?? 0) + 1)
    agentEstadoCounts.set(agenteKey, agentCounts)
    const campanaKey = campanaKeyOf(row)
    const campaignCounts = campaignEstadoCounts.get(campanaKey) ?? new Map()
    campaignCounts.set(estadoKey, (campaignCounts.get(estadoKey) ?? 0) + 1)
    campaignEstadoCounts.set(campanaKey, campaignCounts)

    const campanaEstadoCounts =
      agentCampaignEstadoCounts.get(agenteKey) ??
      new Map<string, Map<string, number>>()
    const estadoCountsForCampana =
      campanaEstadoCounts.get(campanaKey) ?? new Map<string, number>()
    estadoCountsForCampana.set(
      estadoKey,
      (estadoCountsForCampana.get(estadoKey) ?? 0) + 1
    )
    campanaEstadoCounts.set(campanaKey, estadoCountsForCampana)
    agentCampaignEstadoCounts.set(agenteKey, campanaEstadoCounts)

    const attentionSeconds = parseDurationToSeconds(
      typeof row['Tiempo de atención'] === 'string'
        ? row['Tiempo de atención']
        : null
    )
    if (attentionSeconds !== null) {
      const estadoAttention =
        agentEstadoAttentionSeconds.get(agenteKey) ?? new Map()
      const current = estadoAttention.get(estadoKey) ?? {
        totalSeconds: 0,
        sampleCount: 0
      }
      current.totalSeconds += attentionSeconds
      current.sampleCount += 1
      estadoAttention.set(estadoKey, current)
      agentEstadoAttentionSeconds.set(agenteKey, estadoAttention)
    }
  }

  return {
    available: true,
    total: rows.length,
    statusCounts: [...statusCounts.entries()]
      .map(([estado, count]) => ({ estado, count }))
      .sort((a, b) => b.count - a.count),
    agentCounts: [...agentEstadoCounts.entries()]
      .flatMap(([agente, estadoCounts]) =>
        [...estadoCounts.entries()].map(([estado, count]) => ({
          agente,
          estado,
          count
        }))
      )
      .sort((a, b) => b.count - a.count),
    campaignCounts: [...campaignEstadoCounts.entries()]
      .flatMap(([campana, estadoCounts]) =>
        [...estadoCounts.entries()].map(([estado, count]) => ({
          campana,
          estado,
          count
        }))
      )
      .sort((a, b) => b.count - a.count),
    agentCampaignCounts: [...agentCampaignEstadoCounts.entries()].flatMap(
      ([agente, campanaEstadoCounts]) =>
        [...campanaEstadoCounts.entries()].flatMap(([campana, estadoCounts]) =>
          [...estadoCounts.entries()].map(([estado, count]) => ({
            agente,
            campana,
            estado,
            count
          }))
        )
    ),
    agentAttentionSeconds: [...agentEstadoAttentionSeconds.entries()].flatMap(
      ([agente, estadoAttention]) =>
        [...estadoAttention.entries()].map(
          ([estado, { totalSeconds, sampleCount }]) => ({
            agente,
            estado,
            totalSeconds,
            sampleCount
          })
        )
    )
  }
}

function toHistoryDateRange(
  date: string,
  dateEnd: string | undefined
): { dateFrom: string; dateTo: string } {
  return { dateFrom: date, dateTo: dateEnd ?? date }
}

export const getAttentionsAnalytics = createServerFn({ method: 'GET' })
  .validator(dateFilterSchema)
  .handler(async ({ data }): Promise<AttentionsAnalytics> => {
    const { dateFrom, dateTo } = toHistoryDateRange(data.date, data.dateEnd)
    const [attentionRows, outboundRows] = await Promise.all([
      fetchReportRowsHistory('attention', dateFrom, dateTo),
      fetchReportRowsHistory('outboundattention', dateFrom, dateTo)
    ])
    return {
      incoming: deriveDirectionAnalytics(
        attentionRows === null
          ? null
          : filterRowsByDate(
              attentionRows,
              ATTENTION_DATE_FIELD,
              data.date,
              data.dateEnd
            )
      ),
      outgoing: deriveDirectionAnalytics(
        outboundRows === null
          ? null
          : filterRowsByDate(
              outboundRows,
              ATTENTION_DATE_FIELD,
              data.date,
              data.dateEnd
            )
      )
    }
  })

function toAttentionRecord(
  row: ReportRow,
  direction: AttentionDirection,
  transfersById: Map<string, TransferHop[]>,
  contactsByPhone: Map<string, ContactInfo>
): AttentionRecord {
  const idAtencionRaw = row['ID atención']
  const idAtencion =
    typeof idAtencionRaw === 'number' || typeof idAtencionRaw === 'string'
      ? String(idAtencionRaw)
      : ''
  const cliente = row['Nombre de cliente']
  const agenteKey = agenteKeyOf(row)
  const startEpochMs = parseStartEpochMs(row)
  const closeEpochMs = parseLimaDateTime(row['Fecha final'], row['Hora final'])
  const chain = idAtencion ? (transfersById.get(idAtencion) ?? []) : []
  const lastHop = chain.length > 0 ? chain[chain.length - 1] : undefined
  const contactKey = normalizePhoneKey(row['Número cliente'])
  const contact = contactKey ? contactsByPhone.get(contactKey) : undefined
  return {
    idAtencion,
    cliente: typeof cliente === 'string' ? cliente : '',
    plan: contact?.plan ?? '',
    rubro: contact?.rubro ?? '',
    agente: agenteKey,
    campana: campanaKeyOf(row),
    direction,
    estado: estadoKeyOf(row),
    startEpochMs,
    closeEpochMs,
    transferredBy: lastHop?.agenteOrigen ?? null,
    transferDestType: lastHop?.destType ?? null,
    transferDestino: lastHop?.destino ?? null,
    transferChain: chain,
    withAgentSinceMs:
      agenteKey === 'Sin agente' ? null : (lastHop?.epochMs ?? startEpochMs)
  }
}

const CONTACTS_CACHE_TTL_MS = 5 * 60 * 1000
type ContactsCache = {
  rows: ReportRow[] | null
  fetchedAt: number
}
let _contactsCache: ContactsCache | null = null

async function getCachedContactsRows(): Promise<ReportRow[] | null> {
  const now = Date.now()
  if (
    _contactsCache &&
    now - _contactsCache.fetchedAt < CONTACTS_CACHE_TTL_MS
  ) {
    return _contactsCache.rows
  }
  const rows = await fetchReportRows('contacts')
  _contactsCache = { rows, fetchedAt: now }
  return rows
}

export const getAttentionRecordsPage = createServerFn({ method: 'GET' })
  .validator(attentionRecordsPageRequestSchema)
  .handler(async ({ data }): Promise<AttentionRecordsPage> => {
    if (
      (data.estados !== 'all' && data.estados.length === 0) ||
      (data.agentes !== 'all' && data.agentes.length === 0)
    ) {
      return { total: 0, staleCount: 0, records: [], availablePlans: [] }
    }

    const { dateFrom, dateTo } = toHistoryDateRange(data.date, data.dateEnd)
    const [page, contactsRows] = await Promise.all([
      fetchAttentionRecordsPage({
        direction: data.direction,
        estados: data.estados,
        campana: data.campana,
        agentes: data.agentes,
        dateFrom,
        dateTo,
        page: data.page,
        pageSize: data.pageSize
      }),
      getCachedContactsRows()
    ])
    const transfersById = buildTransferChainIndex(page.transfers)
    const contactsByPhone = buildContactsIndex(contactsRows ?? [])
    const availablePlans = [
      ...new Set((contactsRows ?? []).map(row => cleanContactField(row.Plan)))
    ]
    return {
      total: page.total,
      staleCount: page.staleCount,
      records: page.rows.map(row =>
        toAttentionRecord(row, row.direction, transfersById, contactsByPhone)
      ),
      availablePlans
    }
  })

function aggregateDemandBuckets(rows: ReportRow[] | null): DemandBucketCount[] {
  if (rows === null) return []
  const counts = new Map<number, number>()
  for (const row of rows) {
    const startEpochMs = parseStartEpochMs(row)
    if (startEpochMs === null) continue
    const limaDate = epochMsToLimaDate(startEpochMs)
    const slot = limaDate.getUTCDay() * 24 + limaDate.getUTCHours()
    counts.set(slot, (counts.get(slot) ?? 0) + 1)
  }
  return [...counts].map(([slot, count]) => ({
    dayOfWeek: Math.floor(slot / 24),
    hour: slot % 24,
    count
  }))
}

// El endpoint de historial no agrega por agente, asi que el filtro se aplica aca en
// memoria despues de traer las filas -- availableAgentes se deriva de las filas SIN
// filtrar (solo por fecha) para que la lista de opciones no se achique al deseleccionar
// agentes.
export const getDemandAnalytics = createServerFn({ method: 'GET' })
  .validator(dateAndAgentesFilterSchema)
  .handler(async ({ data }): Promise<DemandAnalytics> => {
    const { dateFrom, dateTo } = toHistoryDateRange(data.date, data.dateEnd)
    const [attentionRows, outboundRows] = await Promise.all([
      fetchReportRowsHistory('attention', dateFrom, dateTo),
      fetchReportRowsHistory('outboundattention', dateFrom, dateTo)
    ])
    const dateFilteredAttentionRows =
      attentionRows === null
        ? null
        : filterRowsByDate(
            attentionRows,
            ATTENTION_DATE_FIELD,
            data.date,
            data.dateEnd
          )
    const dateFilteredOutboundRows =
      outboundRows === null
        ? null
        : filterRowsByDate(
            outboundRows,
            ATTENTION_DATE_FIELD,
            data.date,
            data.dateEnd
          )
    const availableAgentes = [
      ...new Set(
        [
          ...(dateFilteredAttentionRows ?? []),
          ...(dateFilteredOutboundRows ?? [])
        ].map(agenteKeyOf)
      )
    ].sort((a, b) => a.localeCompare(b))
    return {
      available: attentionRows !== null || outboundRows !== null,
      availableAgentes,
      buckets: [
        ...aggregateDemandBuckets(
          dateFilteredAttentionRows === null
            ? null
            : dateFilteredAttentionRows.filter(row =>
                agenteAllowed(row, data.agentes)
              )
        ),
        ...aggregateDemandBuckets(
          dateFilteredOutboundRows === null
            ? null
            : dateFilteredOutboundRows.filter(row =>
                agenteAllowed(row, data.agentes)
              )
        )
      ]
    }
  })

// Usa /history/daily-counts (agregado con GROUP BY en SQL del lado del backend, filtro por
// agente incluido -- ver commit 016eba8 del backend) en vez de fetchReportRowsHistory --
// para un rango de 30 dias eso es ~30 filas en vez de miles de filas completas, sub-segundo
// en vez de los 8s+ medidos con el endpoint de detalle.
export const getDailyCaseTrend = createServerFn({ method: 'GET' })
  .validator(dateAndAgentesFilterSchema)
  .handler(async ({ data }): Promise<DailyTrendAnalytics> => {
    const { dateFrom, dateTo } = toHistoryDateRange(data.date, data.dateEnd)
    const [attentionCounts, outboundCounts] = await Promise.all([
      fetchReportDailyCounts('attention', dateFrom, dateTo, data.agentes),
      fetchReportDailyCounts(
        'outboundattention',
        dateFrom,
        dateTo,
        data.agentes
      )
    ])
    const counts = new Map<string, number>()
    for (const dailyCounts of [attentionCounts, outboundCounts]) {
      if (dailyCounts === null) continue
      for (const { date, count } of dailyCounts) {
        counts.set(date, (counts.get(date) ?? 0) + count)
      }
    }
    return {
      available: attentionCounts !== null || outboundCounts !== null,
      days: enumerateIsoDates(data.date, data.dateEnd ?? data.date).map(
        date => ({ date, count: counts.get(date) ?? 0 })
      )
    }
  })

export const getIncidentAnalytics = createServerFn({ method: 'GET' })
  .validator(dateFilterSchema)
  .handler(async ({ data }): Promise<IncidentAnalytics> => {
    const { dateFrom, dateTo } = toHistoryDateRange(data.date, data.dateEnd)
    const rowSets = await Promise.all(
      INCIDENT_SOURCE_REPORTS.map(async reportName => {
        const rows = await fetchReportRowsHistory(reportName, dateFrom, dateTo)
        if (rows === null) return null
        return filterRowsByDate(
          rows,
          INCIDENT_DATE_FIELD[reportName],
          data.date,
          data.dateEnd
        )
      })
    )
    return deriveIncidentAnalytics(rowSets)
  })

export const getExtractionStatus = createServerFn({ method: 'GET' }).handler(
  async () => {
    return fetchExtractionStatus()
  }
)

export const triggerRefresh = createServerFn({ method: 'POST' }).handler(
  async () => {
    return triggerExtractionRefresh()
  }
)

export const getBackfillStatus = createServerFn({ method: 'GET' }).handler(
  async () => {
    return fetchBackfillStatus()
  }
)

export const triggerBackfill = createServerFn({ method: 'POST' })
  .validator(backfillRequestSchema)
  .handler(async ({ data }) => {
    return triggerBackfillExtraction(data.date)
  })

export const getContactsSyncStatus = createServerFn({ method: 'GET' }).handler(
  async () => {
    return fetchContactsSyncStatus()
  }
)

export const triggerContactsSyncRun = createServerFn({
  method: 'POST'
}).handler(async () => {
  return triggerContactsSync()
})

export const getHistoricalBackfillStatus = createServerFn({
  method: 'GET'
}).handler(async () => {
  return fetchHistoricalBackfillStatus()
})

export const triggerHistoricalBackfillRun = createServerFn({
  method: 'POST'
})
  .validator(historicalBackfillRequestSchema)
  .handler(async ({ data }) => {
    return triggerHistoricalBackfill(
      data.dateInit && data.dateEnd
        ? { dateInit: data.dateInit, dateEnd: data.dateEnd }
        : undefined
    )
  })

export const getBenchmarkRunStatus = createServerFn({ method: 'GET' }).handler(
  async () => {
    return fetchBenchmarkRunStatus()
  }
)

export const triggerBenchmarkRun = createServerFn({ method: 'POST' })
  .validator(benchmarkRunRequestSchema)
  .handler(async ({ data }) => {
    return triggerBenchmarkAnalysis(data.directions)
  })

export const getBenchmarkResults = createServerFn({ method: 'GET' })
  .validator(benchmarkResultsRequestSchema)
  .handler(async ({ data }) => {
    return fetchBenchmarkResults(data)
  })
