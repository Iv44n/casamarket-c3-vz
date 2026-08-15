import type { DateFilter, ReportRow } from '#/server/schemas'

const DDMMYYYY = /^(\d{2})\/(\d{2})\/(\d{4})$/

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
