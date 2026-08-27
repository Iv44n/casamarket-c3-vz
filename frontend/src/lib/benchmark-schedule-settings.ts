export type BenchmarkScheduleSettings = {
  enabled: boolean
  timeOfDay: string // "HH:mm", hora America/Lima
  lastTriggeredDateIso: string | null // yyyy-mm-dd (Lima) -- evita disparar 2 veces el mismo dia
}
export const DEFAULT_BENCHMARK_SCHEDULE_SETTINGS: BenchmarkScheduleSettings = {
  // Apagado por defecto a proposito -- esto dispara una corrida de horas con costo real de
  // LLM, no algo que deba arrancar solo sin que alguien lo prenda explicitamente.
  enabled: false,
  timeOfDay: '18:00',
  lastTriggeredDateIso: null
}
const STORAGE_KEY = 'c3-panel:benchmark-schedule-settings'
const TIME_OF_DAY_REGEX = /^([01]\d|2[0-3]):([0-5]\d)$/

function isValidSettings(value: unknown): value is BenchmarkScheduleSettings {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.enabled === 'boolean' &&
    typeof candidate.timeOfDay === 'string' &&
    TIME_OF_DAY_REGEX.test(candidate.timeOfDay) &&
    (candidate.lastTriggeredDateIso === null ||
      typeof candidate.lastTriggeredDateIso === 'string')
  )
}
export function loadBenchmarkScheduleSettings(): BenchmarkScheduleSettings {
  if (typeof window === 'undefined') return DEFAULT_BENCHMARK_SCHEDULE_SETTINGS
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_BENCHMARK_SCHEDULE_SETTINGS
    const parsed = JSON.parse(raw)
    return isValidSettings(parsed)
      ? parsed
      : DEFAULT_BENCHMARK_SCHEDULE_SETTINGS
  } catch {
    return DEFAULT_BENCHMARK_SCHEDULE_SETTINGS
  }
}
export function saveBenchmarkScheduleSettings(
  settings: BenchmarkScheduleSettings
): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
}

// Peru no observa horario de verano (UTC-5 todo el año), asi que un minuto de reloj de pared
// en Lima siempre equivale a un minuto real transcurrido -- no hay ambiguedad de DST que
// resolver aca, a diferencia de zonas horarias que si lo tienen.
export function limaDateIso(date: Date): string {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Lima',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  }).formatToParts(date)
  const part = (type: 'year' | 'month' | 'day') =>
    parts.find(p => p.type === type)?.value ?? ''
  return `${part('year')}-${part('month')}-${part('day')}`
}

function limaTimeParts(date: Date): { hour: number; minute: number } {
  const parts = new Intl.DateTimeFormat('en-US', {
    timeZone: 'America/Lima',
    hour: '2-digit',
    minute: '2-digit',
    hour12: false
  }).formatToParts(date)
  const part = (type: 'hour' | 'minute') =>
    Number(parts.find(p => p.type === type)?.value ?? '0')
  return { hour: part('hour') % 24, minute: part('minute') }
}

/**
 * Ms hasta la proxima ocurrencia de `timeOfDay` ("HH:mm", hora Lima) desde `now`. Si esa hora
 * ya paso hoy, devuelve el tiempo hasta la MISMA hora mañana (nunca negativo) -- este valor
 * grande (tipicamente >12h) es la señal que BenchmarkScheduleProvider usa para decidir si "la
 * hora de hoy ya paso" y evaluar el catch-up, no una decision que esta funcion tome por su
 * cuenta.
 */
export function msUntilNextRun(now: Date, timeOfDay: string): number {
  const match = TIME_OF_DAY_REGEX.exec(timeOfDay)
  const [targetHour, targetMinute] = match
    ? [Number(match[1]), Number(match[2])]
    : [18, 0]
  const { hour, minute } = limaTimeParts(now)
  const nowMinutes = hour * 60 + minute
  const targetMinutes = targetHour * 60 + targetMinute
  const diffMinutes =
    targetMinutes > nowMinutes
      ? targetMinutes - nowMinutes
      : 24 * 60 - nowMinutes + targetMinutes
  return diffMinutes * 60_000
}
