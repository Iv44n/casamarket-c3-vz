import { createServerFn } from '@tanstack/react-start'
import {
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
  AttentionDirection,
  AttentionsAnalytics,
  DirectionAnalytics,
  IncidentAnalytics,
  ReportRow,
  ReportSummary,
  TransferHop
} from './schemas'
import {
  backfillRequestSchema,
  dateFilterSchema,
  deleteFileSchema,
  reportNameSchema
} from './schemas'

const ATTENTION_DATE_FIELD = 'Fecha registro'

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
  rows: ReportRow[] | null,
  direction: AttentionDirection,
  transfersById: Map<string, TransferHop[]>
): DirectionAnalytics {
  if (rows === null) {
    return {
      available: false,
      total: 0,
      statusCounts: [],
      agentCounts: [],
      campaignCounts: [],
      agentCampaignCounts: [],
      agentAttentionSeconds: [],
      openAttentions: []
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
  const openAttentions: DirectionAnalytics['openAttentions'] = []

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

    if (estadoKey === 'Abierta') {
      const idAtencionRaw = row['ID atención']
      const idAtencion =
        typeof idAtencionRaw === 'number' || typeof idAtencionRaw === 'string'
          ? String(idAtencionRaw)
          : ''
      const cliente = row['Nombre de cliente']
      const campana = row.Campaña
      const startEpochMs = parseLimaDateTime(
        row['Fecha inicio'],
        row['Hora inicio']
      )
      const chain = idAtencion ? (transfersById.get(idAtencion) ?? []) : []
      const lastHop = chain.length > 0 ? chain[chain.length - 1] : undefined
      openAttentions.push({
        idAtencion,
        cliente: typeof cliente === 'string' ? cliente : '',
        agente: agenteKey,
        campana:
          typeof campana === 'string' && campana.trim() !== ''
            ? campana
            : 'Sin campaña',
        direction,
        startEpochMs,
        transferredBy: lastHop?.agenteOrigen ?? null,
        transferDestType: lastHop?.destType ?? null,
        transferDestino: lastHop?.destino ?? null,
        transferChain: chain,
        withAgentSinceMs: lastHop?.epochMs ?? startEpochMs
      })
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
    ),
    openAttentions
  }
}

export const getAttentionsAnalytics = createServerFn({ method: 'GET' })
  .validator(dateFilterSchema)
  .handler(async ({ data }): Promise<AttentionsAnalytics> => {
    const [attentionRows, outboundRows, transferRows] = await Promise.all([
      fetchReportRowsHistory('attention'),
      fetchReportRowsHistory('outboundattention'),
      fetchReportRowsHistory('transfer')
    ])
    const transfersById = buildTransferChainIndex(transferRows ?? [])
    return {
      incoming: deriveDirectionAnalytics(
        attentionRows === null
          ? null
          : filterRowsByDate(attentionRows, ATTENTION_DATE_FIELD, data.date),
        'incoming',
        transfersById
      ),
      outgoing: deriveDirectionAnalytics(
        outboundRows === null
          ? null
          : filterRowsByDate(outboundRows, ATTENTION_DATE_FIELD, data.date),
        'outgoing',
        transfersById
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
