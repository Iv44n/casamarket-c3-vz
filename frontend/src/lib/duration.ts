const EMPTY_DURATION_VALUES = new Set(['', 'n.a', '-'])

/**
 * Convierte una duracion en formato "HH:MM:SS" o "MM:SS" a segundos.
 *
 * C3 emite los campos de tiempo (Tiempo de atencion, Hablado llamada, Total
 * llamada) en formato "HH:MM:SS" cuando la duracion supera la hora, y "MM:SS"
 * cuando no -- un mismo reporte mezcla ambos segun la fila. Por eso una entrada
 * de 2 partes se interpreta como MM:SS (1:30 -> 90s), no como HH:MM (1:30 ->
 * 5400s): es el formato que el XLSX de C3 usa para duraciones cortas, y calza
 * con las duraciones de atencion reales (rara vez superan 1h).
 *
 * Valores vacios / "n.a" / "-" (case-insensitive) devuelven null.
 */
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
