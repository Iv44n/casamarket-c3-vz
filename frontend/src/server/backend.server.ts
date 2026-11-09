import { redirect } from '@tanstack/react-router'
import { deleteCookie, getCookie } from '@tanstack/react-start/server'
import type {
  AgentesFilter,
  AttentionRecordsPageRequest,
  BackfillRunSummary,
  BackfillStatus,
  BenchmarkCaseResult,
  BenchmarkDirection,
  BenchmarkRunRecord,
  BenchmarkRunStatus,
  CatalogOptionMutationResult,
  ClientCaseCount,
  ClientSuggestion,
  ContactsSyncStatus,
  CreateUserResult,
  CurrentUser,
  DailyCaseCount,
  DeleteUserResult,
  ExtractionStatus,
  HistoricalBackfillStatus,
  IncidentCatalogOption,
  IncidentCategory,
  LlmSettings,
  ManualIncidentInput,
  ManualIncidentList,
  ManualIncidentMutationResult,
  ReportRow,
  ReportRowsPage,
  SessionUser,
  UpdateUserResult,
  UserRole
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

// `detail` de un error de FastAPI, legible: un string (HTTPException) o la lista de errores de
// validacion de pydantic (422 por body invalido).
async function readErrorDetail(response: Response): Promise<string> {
  try {
    const body: { detail?: unknown } = await response.json()
    if (typeof body.detail === 'string') return body.detail
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((item: { loc?: unknown[]; msg?: string }) =>
          [item.loc?.slice(1).join('.'), item.msg].filter(Boolean).join(': ')
        )
        .join('; ')
    }
  } catch {
    // cuerpo no-JSON: cae al mensaje generico de abajo
  }
  return `El backend respondio ${response.status}`
}

// Usuario de la sesion para __root.tsx's beforeLoad, que corre en CADA navegacion -- sin cache,
// cada click pagaria un /auth/me (un round-trip a Turso del lado del backend, ~0.4s). Cache por
// token (no por usuario: es lo unico que este server conoce antes de preguntar), con TTL corto
// para que un cambio de rol se refleje en la UI a lo sumo un minuto despues; el backend aplica
// ese cambio en el acto de todas formas (auth/dependencies.py), esto solo decide que se muestra.
const SESSION_USER_CACHE_TTL_MS = 60_000
const _sessionUserCache = new Map<
  string,
  { promise: Promise<SessionUser>; expiresAt: number }
>()

export async function fetchSessionUser(): Promise<SessionUser> {
  const token = getCookie(SESSION_COOKIE_NAME)
  if (!token) throw redirect({ to: '/login' })
  const now = Date.now()
  const cached = _sessionUserCache.get(token)
  if (cached && cached.expiresAt > now) return cached.promise

  for (const [key, entry] of _sessionUserCache) {
    if (entry.expiresAt <= now) _sessionUserCache.delete(key)
  }
  const promise = (async () => {
    const user = await fetchCurrentUser()
    return { id: user.id, username: user.username, role: user.role }
  })()
  _sessionUserCache.set(token, {
    promise,
    expiresAt: now + SESSION_USER_CACHE_TTL_MS
  })
  promise.catch(() => {
    const entry = _sessionUserCache.get(token)
    if (entry?.promise === promise) _sessionUserCache.delete(token)
  })
  return promise
}
export function forgetSessionUser(token: string | undefined): void {
  if (token) _sessionUserCache.delete(token)
}
export async function fetchUsers(): Promise<CurrentUser[]> {
  const response = await backendFetch('/auth/users')
  return response.json()
}
export async function createUserOnBackend(
  username: string,
  password: string,
  role: UserRole
): Promise<CreateUserResult> {
  const response = await backendFetch(
    '/auth/users',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ username, password, role })
    },
    { allowedStatuses: [403, 409] }
  )
  if (response.status === 409) return { status: 'duplicate' }
  if (response.status === 403) return { status: 'forbidden' }
  return { status: 'created', user: await response.json() }
}
export async function updateUserOnBackend(
  userId: number,
  changes: { username?: string; password?: string; role?: UserRole }
): Promise<UpdateUserResult> {
  const response = await backendFetch(
    `/auth/users/${userId}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(changes)
    },
    { allowedStatuses: [400, 403, 409, 422] }
  )
  if (response.status === 404) {
    return { status: 'error', message: 'El usuario ya no existe.' }
  }
  if (!response.ok) {
    return { status: 'error', message: await readErrorDetail(response) }
  }
  // La sesion cacheada de esa cuenta (keyed por SU token, que aca no conocemos) quedaria con el
  // rol/username viejo hasta el TTL -- vaciar todo es barato (un /auth/me por usuario activo).
  _sessionUserCache.clear()
  return { status: 'updated', user: await response.json() }
}
export async function deleteUserOnBackend(
  userId: number
): Promise<DeleteUserResult> {
  const response = await backendFetch(
    `/auth/users/${userId}`,
    { method: 'DELETE' },
    { allowedStatuses: [400, 403, 409] }
  )
  if (response.status === 404) {
    return { status: 'error', message: 'El usuario ya no existe.' }
  }
  if (!response.ok) {
    return { status: 'error', message: await readErrorDetail(response) }
  }
  _sessionUserCache.clear()
  return { status: 'deleted' }
}

// --- Incidencias manuales ---------------------------------------------------------------------

export async function fetchManualIncidents(
  dateFrom: string,
  dateTo: string
): Promise<ManualIncidentList> {
  const query = new URLSearchParams({ date_from: dateFrom, date_to: dateTo })
  const response = await backendFetch(`/incidents?${query.toString()}`)
  return response.json()
}
async function saveManualIncident(
  path: string,
  method: 'POST' | 'PUT',
  input: ManualIncidentInput
): Promise<ManualIncidentMutationResult> {
  const response = await backendFetch(
    path,
    {
      method,
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input)
    },
    { allowedStatuses: [422] }
  )
  if (response.status === 404) return { status: 'not_found' }
  if (response.status === 422) {
    return { status: 'invalid', message: await readErrorDetail(response) }
  }
  return { status: 'saved', incident: await response.json() }
}
export function createManualIncidentOnBackend(
  input: ManualIncidentInput
): Promise<ManualIncidentMutationResult> {
  return saveManualIncident('/incidents', 'POST', input)
}
export function updateManualIncidentOnBackend(
  id: number,
  input: ManualIncidentInput
): Promise<ManualIncidentMutationResult> {
  return saveManualIncident(`/incidents/${id}`, 'PUT', input)
}
// true si se borro, false si ya no existia (otro usuario la borro antes) -- ambos dejan la
// lista en el mismo estado, el caller solo decide el texto del toast.
export async function deleteManualIncidentOnBackend(
  id: number
): Promise<boolean> {
  const response = await backendFetch(`/incidents/${id}`, { method: 'DELETE' })
  return response.status !== 404
}
export async function fetchIncidentCatalog(): Promise<IncidentCatalogOption[]> {
  const response = await backendFetch('/incidents/catalog')
  return response.json()
}
export async function fetchIncidentAgentSuggestions(): Promise<string[]> {
  const response = await backendFetch('/incidents/lookups/agents')
  return response.json()
}
export async function fetchIncidentClientSuggestions(
  query: string
): Promise<ClientSuggestion[]> {
  const params = new URLSearchParams({ q: query })
  const response = await backendFetch(`/incidents/lookups/clients?${params}`)
  return response.json()
}
export async function addCatalogOptionOnBackend(
  category: IncidentCategory,
  value: string
): Promise<CatalogOptionMutationResult> {
  const response = await backendFetch(
    '/incidents/catalog',
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category, value })
    },
    { allowedStatuses: [403, 409, 422] }
  )
  if (!response.ok) {
    return { status: 'error', message: await readErrorDetail(response) }
  }
  return { status: 'saved', option: await response.json() }
}
export async function setCatalogOptionActiveOnBackend(
  id: number,
  active: boolean
): Promise<CatalogOptionMutationResult> {
  const response = await backendFetch(
    `/incidents/catalog/${id}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ active })
    },
    { allowedStatuses: [403] }
  )
  if (!response.ok) {
    return { status: 'error', message: await readErrorDetail(response) }
  }
  return { status: 'saved', option: await response.json() }
}
export async function importCatalogFromC3OnBackend(): Promise<{
  added: number
}> {
  const response = await backendFetch('/incidents/catalog/import-c3', {
    method: 'POST'
  })
  return response.json()
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
  cliente?: string
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
  if (params.cliente) query.set('cliente', params.cliente)
  query.set('page', String(params.page))
  query.set('page_size', String(params.pageSize))
  const response = await backendFetch(
    `/data/attention-records?${query.toString()}`
  )
  return response.json()
}

// Clientes con casos (entrantes + salientes) en el rango, ya agregados en SQL del lado del
// backend -- mismo motivo que fetchReportDailyCounts: la alternativa (traer cada fila de
// /history y contar aca) cuesta segundos y megabytes para un rango de un mes. El conteo usa el
// mismo WHERE y la misma clave de cliente que fetchAttentionRecordsPage(cliente=...), asi que
// cada `count` coincide con el `total` del detalle de ese cliente. `plan` lo agrega el caller.
export async function fetchAttentionClientCounts(params: {
  agentes: AgentesFilter
  dateFrom: string
  dateTo: string
}): Promise<Omit<ClientCaseCount, 'plan'>[]> {
  const query = new URLSearchParams()
  query.set('date_from', params.dateFrom)
  query.set('date_to', params.dateTo)
  if (params.agentes !== 'all') {
    for (const agente of params.agentes) query.append('agentes', agente)
  }
  const response = await backendFetch(
    `/data/attention-records/clients?${query.toString()}`
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
export async function triggerBenchmarkAnalysis(params: {
  directions?: BenchmarkDirection[]
  dateFrom?: string
  dateTo?: string
  forceReanalyze?: boolean
}): Promise<BenchmarkRunStatus> {
  const response = await backendFetch('/benchmarks/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      ...(params.directions ? { directions: params.directions } : {}),
      ...(params.dateFrom ? { date_from: params.dateFrom } : {}),
      ...(params.dateTo ? { date_to: params.dateTo } : {}),
      ...(params.forceReanalyze
        ? { force_reanalyze: params.forceReanalyze }
        : {})
    })
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
export async function fetchBenchmarkResultsPage(params: {
  direction?: BenchmarkDirection
  dateFrom?: string
  dateTo?: string
  agentes?: string[]
  page: number
  pageSize: number
}): Promise<{ total: number; rows: BenchmarkCaseResult[] }> {
  const query = new URLSearchParams()
  if (params.direction) query.set('direction', params.direction)
  if (params.dateFrom) query.set('date_from', params.dateFrom)
  if (params.dateTo) query.set('date_to', params.dateTo)
  if (params.agentes) {
    for (const agente of params.agentes) query.append('agentes', agente)
  }
  query.set('page', String(params.page))
  query.set('page_size', String(params.pageSize))
  const response = await backendFetch(
    `/benchmarks/results/page?${query.toString()}`
  )
  return response.json()
}
export async function fetchLlmSettings(): Promise<LlmSettings> {
  const response = await backendFetch('/benchmarks/settings')
  return response.json()
}
export async function fetchBenchmarkRuns(
  limit: number
): Promise<BenchmarkRunRecord[]> {
  const response = await backendFetch(`/benchmarks/runs?limit=${limit}`)
  return response.json()
}
export async function updateLlmSettingsOnBackend(data: {
  provider_name?: string
  api_key?: string
  model: string
  base_url?: string
}): Promise<LlmSettings> {
  const response = await backendFetch('/benchmarks/settings', {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data)
  })
  return response.json()
}
