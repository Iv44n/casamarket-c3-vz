import { createServerFn } from '@tanstack/react-start'
import {
  deriveIncidentAnalytics,
  INCIDENT_SOURCE_REPORTS
} from '#/lib/incident-analytics'
import {
  fetchExtractionStatus,
  fetchMassiveExtractionStatus,
  fetchReportRows,
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
import { reportNameSchema } from './schemas'

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

export const getAttentionsAnalytics = createServerFn({ method: 'GET' }).handler(
  async (): Promise<AttentionsAnalytics> => {
    const [attentionRows, outboundRows] = await Promise.all([
      fetchReportRows('attention'),
      fetchReportRows('outboundattention')
    ])
    return {
      incoming: deriveDirectionAnalytics(attentionRows),
      outgoing: deriveDirectionAnalytics(outboundRows)
    }
  }
)

export const getIncidentAnalytics = createServerFn({ method: 'GET' }).handler(
  async (): Promise<IncidentAnalytics> => {
    const rowSets = await Promise.all(
      INCIDENT_SOURCE_REPORTS.map(reportName => fetchReportRows(reportName))
    )
    return deriveIncidentAnalytics(rowSets)
  }
)

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
