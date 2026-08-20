import type {
  AttentionRecordsPageRequest,
  BackfillRunSummary,
  BackfillStatus,
  ContactsSyncStatus,
  ExtractionStatus,
  HistoricalBackfillStatus,
  ReportRow
} from './schemas'

const BASE_URL = process.env.C3_API_URL ?? 'http://127.0.0.1:8000'
async function backendFetch(
  path: string,
  init?: RequestInit
): Promise<Response> {
  const response = await fetch(`${BASE_URL}${path}`, init)
  if (!response.ok && response.status !== 404) {
    throw new Error(
      `C3 backend ${path} responded ${response.status}: ${await response.text()}`
    )
  }
  return response
}
export async function fetchReportRows(
  reportName: string
): Promise<ReportRow[] | null> {
  const response = await backendFetch(`/data/${reportName}`)
  if (response.status === 404) return null
  return response.json()
}

const inFlightHistoryFetches = new Map<string, Promise<ReportRow[] | null>>()

export async function fetchReportRowsHistory(
  reportName: string,
  dateFrom?: string,
  dateTo?: string
): Promise<ReportRow[] | null> {
  const params = new URLSearchParams()
  if (dateFrom) params.set('date_from', dateFrom)
  if (dateTo) params.set('date_to', dateTo)
  const query = params.toString()
  const path = `/data/${reportName}/history${query ? `?${query}` : ''}`
  const existing = inFlightHistoryFetches.get(path)
  if (existing) return existing
  const promise = (async () => {
    const response = await backendFetch(path)
    return response.status === 404 ? null : await response.json()
  })().finally(() => inFlightHistoryFetches.delete(path))
  inFlightHistoryFetches.set(path, promise)
  return promise
}
export async function fetchAttentionRecordsPage(params: {
  direction: AttentionRecordsPageRequest['direction']
  estados: AttentionRecordsPageRequest['estados']
  campana: string
  agentes: AttentionRecordsPageRequest['agentes']
  dateFrom?: string
  dateTo?: string
  page: number
  pageSize: number
}): Promise<{
  total: number
  staleCount: number
  rows: (ReportRow & { direction: 'incoming' | 'outgoing' })[]
  transfers: ReportRow[]
}> {
  const query = new URLSearchParams()
  query.set('direction', params.direction)
  if (params.estados !== 'all') {
    for (const estado of params.estados) query.append('estados', estado)
  }
  if (params.campana !== 'all') query.set('campana', params.campana)
  if (params.agentes !== 'all') {
    for (const agente of params.agentes) query.append('agentes', agente)
  }
  if (params.dateFrom) query.set('date_from', params.dateFrom)
  if (params.dateTo) query.set('date_to', params.dateTo)
  query.set('page', String(params.page))
  query.set('page_size', String(params.pageSize))
  const response = await backendFetch(
    `/data/attention-records?${query.toString()}`
  )
  return response.json()
}
export async function fetchExtractionStatus(): Promise<ExtractionStatus> {
  const response = await backendFetch('/extraction/status')
  return response.json()
}
export async function triggerExtractionRefresh(): Promise<ExtractionStatus> {
  const response = await backendFetch('/extraction/refresh', {
    method: 'POST'
  })
  return response.json()
}
export async function fetchBackfillStatus(): Promise<BackfillStatus> {
  const response = await backendFetch('/extraction/backfill/status')
  return response.json()
}
export async function triggerBackfillExtraction(
  date: string
): Promise<BackfillRunSummary> {
  const response = await backendFetch('/extraction/backfill', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ date })
  })
  return response.json()
}
export async function fetchContactsSyncStatus(): Promise<ContactsSyncStatus> {
  const response = await backendFetch('/extraction/contacts/sync/status')
  return response.json()
}
export async function triggerContactsSync(): Promise<ContactsSyncStatus> {
  const response = await backendFetch('/extraction/contacts/sync', {
    method: 'POST'
  })
  return response.json()
}
export async function fetchHistoricalBackfillStatus(): Promise<HistoricalBackfillStatus> {
  const response = await backendFetch('/extraction/historical/backfill/status')
  return response.json()
}
export async function triggerHistoricalBackfill(dateRange?: {
  dateInit: string
  dateEnd: string
}): Promise<HistoricalBackfillStatus> {
  const response = await backendFetch('/extraction/historical/backfill', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(
      dateRange
        ? { date_init: dateRange.dateInit, date_end: dateRange.dateEnd }
        : {}
    )
  })
  return response.json()
}
