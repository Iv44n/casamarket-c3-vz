import type {
  IncidentAnalytics,
  IncidentCategory,
  ReportName,
  ReportRow
} from '#/server/schemas'
import { INCIDENT_CATEGORIES } from '#/server/schemas'

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
export function deriveIncidentAnalytics(
  rowSets: (ReportRow[] | null)[]
): IncidentAnalytics {
  const available = rowSets.some(rows => rows !== null)
  const rows = rowSets.flatMap(rows => rows ?? [])
  const total = rows.filter(
    row => !isEmptyIncidentValue(row[INCIDENT_FIELD.origen])
  ).length
  const counts = {} as IncidentAnalytics['counts']
  for (const category of INCIDENT_CATEGORIES) {
    const field = INCIDENT_FIELD[category]
    const tally = new Map<string, number>()
    for (const row of rows) {
      const raw = row[field]
      if (isEmptyIncidentValue(raw)) {
        continue
      }
      const value = String(raw).trim()
      tally.set(value, (tally.get(value) ?? 0) + 1)
    }
    counts[category] = [...tally.entries()]
      .map(([value, count]) => ({ value, count }))
      .sort((a, b) => b.count - a.count || a.value.localeCompare(b.value))
  }
  return { available, total, counts }
}
