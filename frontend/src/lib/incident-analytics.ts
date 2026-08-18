import { parseDurationToSeconds } from '#/lib/duration'
import {
  INCIDENT_CATEGORIES,
  type IncidentAnalytics,
  type IncidentCategory,
  type IncidentRecord,
  type ReportName,
  type ReportRow
} from '#/server/schemas'

export const INCIDENT_SOURCE_REPORTS = [
  'attention',
  'outboundattention',
  'calloutgoing'
] as const satisfies readonly ReportName[]

type IncidentSourceReportName = (typeof INCIDENT_SOURCE_REPORTS)[number]

export const INCIDENT_DATE_FIELD: Record<IncidentSourceReportName, string> = {
  attention: 'Fecha registro',
  outboundattention: 'Fecha registro',
  calloutgoing: 'Fecha'
}
export const INCIDENT_DETAIL_FIELD: Record<
  IncidentSourceReportName,
  {
    descripcion: string
    agente: string
    campana: string
    estado: string
    hora: string
    horaFinal: string
    fechaFinal: string
    tiempo: string[]
  }
> = {
  attention: {
    descripcion: 'Descripción de la incidencia',
    agente: 'Agente',
    campana: 'Campaña',
    estado: 'Estado',
    hora: 'Hora registro',
    horaFinal: 'Hora final',
    fechaFinal: 'Fecha final',
    tiempo: ['Tiempo de atención']
  },
  outboundattention: {
    descripcion: 'Descripción de la incidencia',
    agente: 'Agente',
    campana: 'Campaña',
    estado: 'Estado',
    hora: 'Hora registro',
    horaFinal: 'Hora final',
    fechaFinal: 'Fecha final',
    tiempo: ['Tiempo de atención']
  },
  calloutgoing: {
    descripcion: 'Descripción de la incidencia',
    agente: 'Agente',
    campana: 'Campaña',
    estado: 'Estado',
    hora: 'Hora',
    horaFinal: 'Hora final',
    fechaFinal: 'Fecha final',
    tiempo: ['Hablado llamada', 'Total llamada']
  }
}
export const INCIDENT_CATEGORY_LABEL: Record<IncidentCategory, string> = {
  origen: 'Origen',
  tipo: 'Tipo',
  ambito: 'Ámbito',
  resultado: 'Resultado'
}
export const INCIDENT_CATEGORY_COLOR: Record<IncidentCategory, string> = {
  origen: 'var(--color-chart-1)',
  tipo: 'var(--color-chart-2)',
  ambito: 'var(--color-chart-3)',
  resultado: 'var(--color-chart-4)'
}
const INCIDENT_FIELD: Record<IncidentCategory, string> = {
  origen: 'Origen de incidencia',
  tipo: 'Tipo de incidencia',
  ambito: 'Ámbito de incidencia',
  resultado: 'Resultado de la atención'
}
const CATEGORY_BY_FIELD: Record<string, IncidentCategory> = Object.fromEntries(
  (Object.entries(INCIDENT_FIELD) as [IncidentCategory, string][]).map(
    ([category, field]) => [field, category]
  )
)

function deriveRowCategoryOrder(row: ReportRow): IncidentCategory[] {
  const order: IncidentCategory[] = []
  for (const key of Object.keys(row)) {
    const category = CATEGORY_BY_FIELD[key]
    if (category && !order.includes(category)) {
      order.push(category)
    }
  }
  return order
}

export function pickDominantCategoryOrder(
  records: IncidentRecord[]
): IncidentCategory[] {
  const counts = new Map<string, { order: IncidentCategory[]; count: number }>()
  for (const record of records) {
    const key = record.categoryOrder.join(',')
    const entry = counts.get(key) ?? { order: record.categoryOrder, count: 0 }
    entry.count += 1
    counts.set(key, entry)
  }
  const [dominant] = [...counts.values()].sort((a, b) => b.count - a.count)
  return dominant?.order ?? [...INCIDENT_CATEGORIES]
}

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

function stringField(value: unknown): string {
  return typeof value === 'string' ? value.trim() : ''
}

function firstNonEmptyValue(row: ReportRow, fields: string[]): string | null {
  for (const field of fields) {
    const value = row[field]
    if (!isEmptyIncidentValue(value)) {
      return String(value)
    }
  }
  return null
}

export function deriveIncidentAnalytics(
  rowSets: (ReportRow[] | null)[]
): IncidentAnalytics {
  const available = rowSets.some(rows => rows !== null)
  const records: IncidentRecord[] = []
  rowSets.forEach((rows, index) => {
    if (rows === null) return
    const reportName = INCIDENT_SOURCE_REPORTS[index]
    const detailField = INCIDENT_DETAIL_FIELD[reportName]
    const dateField = INCIDENT_DATE_FIELD[reportName]
    for (const row of rows) {
      const origenRaw = row[INCIDENT_FIELD.origen]
      if (isEmptyIncidentValue(origenRaw)) {
        continue
      }
      records.push({
        categoryOrder: deriveRowCategoryOrder(row),
        origen: String(origenRaw).trim(),
        tipo: normalizeIncidentField(row[INCIDENT_FIELD.tipo], 'Sin tipo'),
        ambito: normalizeIncidentField(
          row[INCIDENT_FIELD.ambito],
          'Sin ambito'
        ),
        resultado: normalizeIncidentField(
          row[INCIDENT_FIELD.resultado],
          'Sin resultado'
        ),
        descripcion: normalizeIncidentField(row[detailField.descripcion], ''),
        agente: normalizeIncidentField(row[detailField.agente], ''),
        campana: normalizeIncidentField(
          row[detailField.campana],
          'Sin campaña'
        ),
        estado: normalizeIncidentField(row[detailField.estado], ''),
        fecha: stringField(row[dateField]),
        hora: stringField(row[detailField.hora]),
        horaFinal: stringField(row[detailField.horaFinal]),
        fechaFinal: stringField(row[detailField.fechaFinal]),
        tiempoSegundos: parseDurationToSeconds(
          firstNonEmptyValue(row, detailField.tiempo)
        )
      })
    }
  })
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
