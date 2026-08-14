import type {
  IncidentAnalytics,
  IncidentCategory,
  IncidentRecord,
  ReportName,
  ReportRow
} from '#/server/schemas'

// The only reports whose C3 export ("Incluir formulario") carries the
// incident-classification columns -- see backend/recon/hallazgos.md and the
// live `/data/attention` payload, which has these mixed in with the regular
// atenciones columns. callincoming/contacts don't have them.
export const INCIDENT_SOURCE_REPORTS: ReportName[] = [
  'attention',
  'outboundattention',
  'calloutgoing'
]
export const INCIDENT_CATEGORY_LABEL: Record<IncidentCategory, string> = {
  origen: 'Origen',
  tipo: 'Tipo',
  ambito: 'Ámbito'
}
export const INCIDENT_CATEGORY_COLOR: Record<IncidentCategory, string> = {
  origen: 'var(--color-chart-1)',
  tipo: 'var(--color-chart-2)',
  ambito: 'var(--color-chart-3)'
}
export const DIMENSION_CHAIN: Record<IncidentCategory, IncidentCategory[]> = {
  ambito: ['ambito', 'origen', 'tipo'],
  origen: ['origen', 'tipo'],
  tipo: ['tipo']
}
const INCIDENT_FIELD: Record<IncidentCategory, string> = {
  origen: 'Origen de incidencia',
  tipo: 'Tipo de incidencia',
  ambito: 'Ámbito de incidencia'
}
// C3's incident form leaves these fields as the literal string "N.A" (not
// blank) when an attention/call has no incident attached to it.
const EMPTY_INCIDENT_VALUES = new Set(['', 'n.a', '-'])
function isEmptyIncidentValue(value: unknown): boolean {
  return (
    typeof value !== 'string' ||
    EMPTY_INCIDENT_VALUES.has(value.trim().toLowerCase())
  )
}
function normalizeIncidentField(value: unknown, fallback: string): string {
  return isEmptyIncidentValue(value) ? fallback : String(value).trim()
}
export function deriveIncidentAnalytics(
  rowSets: (ReportRow[] | null)[]
): IncidentAnalytics {
  const available = rowSets.some(rows => rows !== null)
  const rows = rowSets.flatMap(rows => rows ?? [])
  const records: IncidentRecord[] = []
  for (const row of rows) {
    const origenRaw = row[INCIDENT_FIELD.origen]
    if (isEmptyIncidentValue(origenRaw)) {
      continue
    }
    records.push({
      origen: String(origenRaw).trim(),
      tipo: normalizeIncidentField(row[INCIDENT_FIELD.tipo], 'Sin tipo'),
      ambito: normalizeIncidentField(row[INCIDENT_FIELD.ambito], 'Sin ambito')
    })
  }
  return { available, total: records.length, records }
}
export type IncidentGroup = {
  label: string
  count: number
  items: IncidentRecord[]
}
export function groupIncidentsBy(
  records: IncidentRecord[],
  key: IncidentCategory
): IncidentGroup[] {
  const groups = new Map<string, IncidentRecord[]>()
  for (const record of records) {
    const label = record[key]
    const items = groups.get(label) ?? []
    items.push(record)
    groups.set(label, items)
  }
  return [...groups.entries()]
    .map(([label, items]) => ({ label, count: items.length, items }))
    .sort((a, b) => b.count - a.count || a.label.localeCompare(b.label))
}
