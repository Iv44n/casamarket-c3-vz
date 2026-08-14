export type IntervalUnit = 'seconds' | 'minutes' | 'hours'
export type AutoRefreshSettings = {
  enabled: boolean
  value: number
  unit: IntervalUnit
}
export const DEFAULT_AUTO_REFRESH_SETTINGS: AutoRefreshSettings = {
  enabled: true,
  value: 5,
  unit: 'minutes'
}
const STORAGE_KEY = 'c3-panel:auto-refresh-settings'
const MS_PER_UNIT: Record<IntervalUnit, number> = {
  seconds: 1000,
  minutes: 60000,
  hours: 3600000
}
export function intervalMs(value: number, unit: IntervalUnit): number {
  return value * MS_PER_UNIT[unit]
}
function isValidSettings(value: unknown): value is AutoRefreshSettings {
  if (typeof value !== 'object' || value === null) return false
  const candidate = value as Record<string, unknown>
  return (
    typeof candidate.enabled === 'boolean' &&
    typeof candidate.value === 'number' &&
    Number.isFinite(candidate.value) &&
    candidate.value > 0 &&
    (candidate.unit === 'seconds' ||
      candidate.unit === 'minutes' ||
      candidate.unit === 'hours')
  )
}
export function loadAutoRefreshSettings(): AutoRefreshSettings {
  if (typeof window === 'undefined') return DEFAULT_AUTO_REFRESH_SETTINGS
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY)
    if (!raw) return DEFAULT_AUTO_REFRESH_SETTINGS
    const parsed = JSON.parse(raw)
    return isValidSettings(parsed) ? parsed : DEFAULT_AUTO_REFRESH_SETTINGS
  } catch {
    return DEFAULT_AUTO_REFRESH_SETTINGS
  }
}
export function saveAutoRefreshSettings(settings: AutoRefreshSettings): void {
  if (typeof window === 'undefined') return
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings))
}
