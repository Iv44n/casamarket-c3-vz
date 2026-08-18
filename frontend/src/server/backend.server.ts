import type {
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

export async function fetchReportRowsHistory(
  reportName: string
): Promise<ReportRow[] | null> {
  const response = await backendFetch(`/data/${reportName}/history`)
  if (response.status === 404) return null
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
export async function triggerHistoricalBackfill(): Promise<HistoricalBackfillStatus> {
  const response = await backendFetch('/extraction/historical/backfill', {
    method: 'POST'
  })
  return response.json()
}
