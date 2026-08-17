import { createServerFn } from '@tanstack/react-start'
import { filterRowsByDate } from '#/lib/date-filter'
import {
  deriveIncidentAnalytics,
  INCIDENT_DATE_FIELD,
  INCIDENT_SOURCE_REPORTS
} from '#/lib/incident-analytics'
import {
  deleteDownloadedFile,
  fetchBackfillStatus,
  fetchDownloadedFiles,
  fetchExtractionStatus,
  fetchMassiveExtractionStatus,
  fetchReportRows,
  fetchReportRowsHistory,
  triggerBackfillExtraction,
  triggerExtractionRefresh,
  triggerMassiveExtractionRefresh
} from './backend.server'
import type {
  AttentionsAnalytics,
  DirectionAnalytics,
  IncidentAnalytics,
  ReportRow,
  ReportSummary
} from './schemas'
import {
  backfillRequestSchema,
  dateFilterSchema,
  deleteFileSchema,
  reportNameSchema
} from './schemas'

const ATTENTION_DATE_FIELD = 'Fecha registro'

export const getReportRows = createServerFn({ method: 'GET' })
  .validator(reportNameSchema)
  .handler(async ({ data }) => fetchReportRows(data.reportName))

export const getReportSummary = createServerFn({ method: 'GET' })
  .validator(reportNameSchema)
  .handler(async ({ data }): Promise<ReportSummary | null> => {
    const rows = await fetchReportRows(data.reportName)
    if (rows === null) return null
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
    return {
      rowCount: rows.length,
      columns: [...columns.entries()]
        .map(([name, populated]) => ({ name, populated }))
        .sort((a, b) => b.populated - a.populated)
    }
  })

function deriveDirectionAnalytics(
  rows: ReportRow[] | null
): DirectionAnalytics {
  if (rows === null) {
    return {
      available: false,
      total: 0,
      statusCounts: [],
      agentCounts: [],
      campaignCounts: []
    }
  }
  const statusCounts = new Map<string, number>()
  const agentEstadoCounts = new Map<string, Map<string, number>>()
  const campaignEstadoCounts = new Map<string, Map<string, number>>()

  for (const row of rows) {
    const estado = row.Estado
    const estadoKey =
      typeof estado === 'string' && estado.trim() !== '' ? estado : 'Sin estado'
    statusCounts.set(estadoKey, (statusCounts.get(estadoKey) ?? 0) + 1)
    const agente = row.Agente
    const agenteKey =
      typeof agente === 'string' && agente.trim() !== '' ? agente : 'Sin agente'
    const agentCounts = agentEstadoCounts.get(agenteKey) ?? new Map()
    agentCounts.set(estadoKey, (agentCounts.get(estadoKey) ?? 0) + 1)
    agentEstadoCounts.set(agenteKey, agentCounts)
    const campana = row.Campaña
    const campanaKey =
      typeof campana === 'string' && campana.trim() !== ''
        ? campana
        : 'Sin campaña'
    const campaignCounts = campaignEstadoCounts.get(campanaKey) ?? new Map()
    campaignCounts.set(estadoKey, (campaignCounts.get(estadoKey) ?? 0) + 1)
    campaignEstadoCounts.set(campanaKey, campaignCounts)
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
      .sort((a, b) => b.count - a.count)
  }
}

export const getAttentionsAnalytics = createServerFn({ method: 'GET' })
  .validator(dateFilterSchema)
  .handler(async ({ data }): Promise<AttentionsAnalytics> => {
    const [attentionRows, outboundRows] = await Promise.all([
      fetchReportRowsHistory('attention'),
      fetchReportRowsHistory('outboundattention')
    ])
    return {
      incoming: deriveDirectionAnalytics(
        attentionRows === null
          ? null
          : filterRowsByDate(attentionRows, ATTENTION_DATE_FIELD, data.date)
      ),
      outgoing: deriveDirectionAnalytics(
        outboundRows === null
          ? null
          : filterRowsByDate(outboundRows, ATTENTION_DATE_FIELD, data.date)
      )
    }
  })

export const getIncidentAnalytics = createServerFn({ method: 'GET' })
  .validator(dateFilterSchema)
  .handler(async ({ data }): Promise<IncidentAnalytics> => {
    const rowSets = await Promise.all(
      INCIDENT_SOURCE_REPORTS.map(async reportName => {
        const rows = await fetchReportRowsHistory(reportName)
        if (rows === null) return null
        return filterRowsByDate(
          rows,
          INCIDENT_DATE_FIELD[reportName],
          data.date
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

export const getMassiveExtractionStatus = createServerFn({
  method: 'GET'
}).handler(async () => {
  return fetchMassiveExtractionStatus()
})

export const triggerMassiveRefresh = createServerFn({ method: 'POST' }).handler(
  async () => {
    return triggerMassiveExtractionRefresh()
  }
)

export const getDownloadedFiles = createServerFn({ method: 'GET' }).handler(
  async () => {
    return fetchDownloadedFiles()
  }
)

export const deleteFile = createServerFn({ method: 'POST' })
  .validator(deleteFileSchema)
  .handler(async ({ data }) => {
    await deleteDownloadedFile(data.filename)
  })

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
