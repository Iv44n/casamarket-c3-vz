import type { DateFilter, ReportRow } from '#/server/schemas'

const DDMMYYYY = /^(\d{2})\/(\d{2})\/(\d{4})$/
const YYYYMMDD = /^(\d{4})-(\d{2})-(\d{2})$/
const HHMMSS = /^(\d{2}):(\d{2}):(\d{2})$/
const LIMA_UTC_OFFSET_MS = 5 * 60 * 60 * 1000

function toIsoDate(value: unknown): string | null {
  if (typeof value !== 'string') return null
  const match = DDMMYYYY.exec(value.trim())
  if (!match) return null
  const [, day, month, year] = match
  return `${year}-${month}-${day}`
}

export function filterRowsByDate<T extends ReportRow>(
  rows: T[],
  dateField: string,
  date: DateFilter
): T[] {
  if (date === 'all') return rows
  return rows.filter(row => toIsoDate(row[dateField]) === date)
}

export function parseLimaDateTime(
  fecha: unknown,
  hora: unknown
): number | null {
  if (typeof fecha !== 'string' || typeof hora !== 'string') return null
  const dateMatch = DDMMYYYY.exec(fecha.trim())
  const timeMatch = HHMMSS.exec(hora.trim())
  if (!dateMatch || !timeMatch) return null
  const [, day, month, year] = dateMatch
  const [, hours, minutes, seconds] = timeMatch
  return (
    Date.UTC(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hours),
      Number(minutes),
      Number(seconds)
    ) + LIMA_UTC_OFFSET_MS
  )
}

export function parseLimaIsoDateTime(
  fecha: unknown,
  hora: unknown
): number | null {
  if (typeof fecha !== 'string' || typeof hora !== 'string') return null
  const dateMatch = YYYYMMDD.exec(fecha.trim())
  const timeMatch = HHMMSS.exec(hora.trim())
  if (!dateMatch || !timeMatch) return null
  const [, year, month, day] = dateMatch
  const [, hours, minutes, seconds] = timeMatch
  return (
    Date.UTC(
      Number(year),
      Number(month) - 1,
      Number(day),
      Number(hours),
      Number(minutes),
      Number(seconds)
    ) + LIMA_UTC_OFFSET_MS
  )
}
