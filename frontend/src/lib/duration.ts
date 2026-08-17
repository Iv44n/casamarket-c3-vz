const EMPTY_DURATION_VALUES = new Set(['', 'n.a', '-'])

export function parseDurationToSeconds(
  value: string | null | undefined
): number | null {
  if (typeof value !== 'string') return null
  const trimmed = value.trim()
  if (EMPTY_DURATION_VALUES.has(trimmed.toLowerCase())) return null
  const parts = trimmed.split(':').map(Number)
  if (parts.length < 2 || parts.length > 3 || parts.some(Number.isNaN)) {
    return null
  }
  const [hours, minutes, seconds] =
    parts.length === 3 ? parts : [0, parts[0], parts[1]]
  return hours * 3600 + minutes * 60 + seconds
}

export function formatSecondsAsDuration(seconds: number): string {
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const secs = Math.floor(seconds % 60)
  const parts: string[] = []
  if (hours > 0) parts.push(`${hours}h`)
  if (hours > 0 || minutes > 0) parts.push(`${minutes}m`)
  parts.push(`${secs}s`)
  return parts.join(' ')
}
