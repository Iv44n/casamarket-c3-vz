import { redirect } from '@tanstack/react-router'
import { deleteCookie, getCookie } from '@tanstack/react-start/server'
import type {
  AgentesFilter,
  AttentionRecordsPageRequest,
  BackfillRunSummary,
  BackfillStatus,
  BenchmarkCaseResult,
  BenchmarkDirection,
  BenchmarkRunStatus,
  ContactsSyncStatus,
  CreateUserResult,
  CurrentUser,
  DailyCaseCount,
  ExtractionStatus,
  HistoricalBackfillStatus,
  ReportRow,
  ReportRowsPage
} from './schemas'

const BASE_URL = process.env.C3_API_URL ?? 'http://127.0.0.1:8000'
export const SESSION_COOKIE_NAME = 'c3_session'
// El backend ahora exige Authorization: Bearer <jwt> en todo salvo estos dos --
// ver backend/CLAUDE.md's "Auth" section. Login necesita poder recibir su propio
// 401 (credenciales invalidas) sin que backendFetch lo trate como sesion expirada.
const PUBLIC_BACKEND_PATHS = ['/auth/login', '/health']
function isPublicBackendPath(path: string): boolean {
  return PUBLIC_BACKEND_PATHS.some(
    publicPath => path === publicPath || path.startsWith(`${publicPath}?`)
  )
}
// allowedStatuses: statuses the CALLER wants to inspect itself instead of having
// backendFetch turn them into a thrown Error -- 404 is always allowed (the established
// "nothing downloaded yet" signal across this file); a caller like createUserOnBackend
// below adds 403/409 since those are expected, handled outcomes for that one endpoint,
// not real failures.
async function backendFetch(
  path: string,
  init?: RequestInit,
  opts?: { allowedStatuses?: number[] }
): Promise<Response> {
  const isPublic = isPublicBackendPath(path)
  const token = getCookie(SESSION_COOKIE_NAME)
  if (!isPublic && !token) {
    throw redirect({ to: '/login' })
  }
  const headers = new Headers(init?.headers)
  if (token) headers.set('Authorization', `Bearer ${token}`)
  const response = await fetch(`${BASE_URL}${path}`, { ...init, headers })
  if (response.status === 401) {
    if (isPublic) return response
    deleteCookie(SESSION_COOKIE_NAME, { path: '/' })
    throw redirect({ to: '/login' })
  }
  const allowedStatuses = new Set([404, ...(opts?.allowedStatuses ?? [])])
  if (!response.ok && !allowedStatuses.has(response.status)) {
    throw new Error(
      `C3 backend ${path} responded ${response.status}: ${await response.text()}`
    )
  }
  return response
}
export async function authenticateWithBackend(
  username: string,
  password: string
): Promise<string | null> {
  const response = await backendFetch('/auth/login', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password })
  })
  if (response.status === 401) return null
  const data: { access_token: string } = await response.json()
  return data.access_token
}
export async function fetchCurrentUser(): Promise<CurrentUser> {
  const response = await backendFetch('/auth/me')
  return response.json()
}
export async function fetchUsers(): Promise<CurrentUser[]> {
  const response = await backendFetch('/auth/users')
  return response.json()
}
export async function createUserOnBackend(
  username: string,
  password: string,
  isAdmin: boolean
): Promise<CreateUserResult> {
  const response = await backendFetch(
    '/auth/users',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, is_admin: isAdmin })
    },
    { allowedStatuses: [403, 409] }
  )
  if (response.status === 409) return { status: 'duplicate' }
  if (response.status === 403) return { status: 'forbidden' }
  return { status: 'created', user: await response.json() }
}
const _reportRowsCache = new Map<
  string,
  { promise: Promise<ReportRow[] | null>; expiresAt: number }
>()
const REPORT_ROWS_CACHE_TTL_MS = 60_000

export async function fetchReportRows(
  reportName: string
): Promise<ReportRow[] | null> {
  const now = Date.now()
  const cached = _reportRowsCache.get(reportName)
  if (cached && cached.expiresAt > now) return cached.promise

  const promise = (async () => {
    const response = await backendFetch(`/data/${reportName}`)
    return response.status === 404 ? null : await response.json()
  })()
  _reportRowsCache.set(reportName, {
    promise,
    expiresAt: now + REPORT_ROWS_CACHE_TTL_MS
  })
  // Si la peticion falla, sacamos la promesa rechazada del cache para que el proximo
  // llamado reintente en vez de devolver el mismo error cacheado por todo el TTL.
  promise.catch(() => {
    const entry = _reportRowsCache.get(reportName)
    if (entry?.promise === promise) _reportRowsCache.delete(reportName)
  })
  return promise
}

export async function fetchReportRowsPage(
  reportName: string,
  page: number,
  pageSize: number
): Promise<ReportRowsPage | null> {
  const query = new URLSearchParams()
  query.set('page', String(page))
  query.set('page_size', String(pageSize))
  const response = await backendFetch(
    `/data/${reportName}/page?${query.toString()}`
  )
  return response.status === 404 ? null : await response.json()
}

// TTL cache (not just in-flight dedup): history fetches are expensive on the backend
// (full row-level data for every day in range, no server-side caching there -- a 30-day
// attention history costs ~8s measured live), and this app now has multiple analytics
// functions (heatmap + daily trend on /tendencias-historicas, summary + incidents on
// /atenciones) that each need the same report/range history concurrently or in quick
// succession. Caching the promise itself (not just the resolved value) covers the
// concurrent case too, same as fetchReportRows above.
const _historyRowsCache = new Map<
  string,
  { promise: Promise<ReportRow[] | null>; expiresAt: number }
>()
const HISTORY_ROWS_CACHE_TTL_MS = 60_000

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
  const now = Date.now()
  const cached = _historyRowsCache.get(path)
  if (cached && cached.expiresAt > now) return cached.promise

  const promise = (async () => {
    const response = await backendFetch(path)
    return response.status === 404 ? null : await response.json()
  })()
  _historyRowsCache.set(path, {
    promise,
    expiresAt: now + HISTORY_ROWS_CACHE_TTL_MS
  })
  promise.catch(() => {
    const entry = _historyRowsCache.get(path)
    if (entry?.promise === promise) _historyRowsCache.delete(path)
  })
  return promise
}

// Aggregated variant of fetchReportRowsHistory: GROUP BY date in SQL server-side, so a
// 30-day range comes back as ~30 {date,count} rows instead of thousands of full attention
// rows -- sub-second instead of the 8s+ measured for /history on the same range. Use this
// whenever only the daily count is needed (e.g. the trend chart); reach for
// fetchReportRowsHistory only when the row-level detail itself is required.
export async function fetchReportDailyCounts(
  reportName: string,
  dateFrom: string,
  dateTo: string,
  agentes: AgentesFilter = 'all'
): Promise<DailyCaseCount[] | null> {
  const params = new URLSearchParams()
  params.set('date_from', dateFrom)
  params.set('date_to', dateTo)
  if (agentes !== 'all') {
    for (const agente of agentes) params.append('agentes', agente)
  }
  const response = await backendFetch(
    `/data/${reportName}/history/daily-counts?${params.toString()}`
  )
  return response.status === 404 ? null : await response.json()
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
export async function fetchBenchmarkRunStatus(): Promise<BenchmarkRunStatus> {
  const response = await backendFetch('/benchmarks/run/status')
  return response.json()
}
export async function triggerBenchmarkAnalysis(
  directions?: BenchmarkDirection[]
): Promise<BenchmarkRunStatus> {
  const response = await backendFetch('/benchmarks/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(directions ? { directions } : {})
  })
  return response.json()
}
export async function fetchBenchmarkResults(params: {
  direction?: BenchmarkDirection
  dateFrom?: string
  dateTo?: string
}): Promise<BenchmarkCaseResult[]> {
  const query = new URLSearchParams()
  if (params.direction) query.set('direction', params.direction)
  if (params.dateFrom) query.set('date_from', params.dateFrom)
  if (params.dateTo) query.set('date_to', params.dateTo)
  const qs = query.toString()
  const response = await backendFetch(
    `/benchmarks/results${qs ? `?${qs}` : ''}`
  )
  return response.json()
}
