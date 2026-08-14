import type {
  ExtractionStatus,
  MassiveExtractionStatus,
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
export async function fetchMassiveExtractionStatus(): Promise<MassiveExtractionStatus> {
  const response = await backendFetch('/extraction/massive/status')
  return response.json()
}
export async function triggerMassiveExtractionRefresh(): Promise<MassiveExtractionStatus> {
  const response = await backendFetch('/extraction/massive/refresh', {
    method: 'POST'
  })
  return response.json()
}
