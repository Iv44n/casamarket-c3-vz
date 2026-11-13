import type { ManualIncident } from '#/server/schemas'

// Exportacion de incidencias manuales. Cada incidencia lleva TODOS sus campos (los de negocio y
// los de auditoria); nada se resume ni se omite.

export const INCIDENT_EXPORT_COLUMNS = [
  'id',
  'fecha',
  'hora',
  'cliente',
  'telefono',
  'agente',
  'origen',
  'tipo',
  'ambito',
  'resultado',
  'descripcion',
  'created_by',
  'created_at',
  'updated_by',
  'updated_at'
] as const satisfies readonly (keyof ManualIncident)[]

function csvCell(value: string | number | null): string {
  const text = value === null ? '' : String(value)
  return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text
}

// UTF-8 con BOM (Excel lo necesita para leer bien las tildes) y CRLF (RFC 4180). Los saltos de
// linea de la descripcion quedan dentro de comillas, asi que no rompen la fila.
export function incidentsToCsv(incidents: ManualIncident[]): string {
  const lines = [
    INCIDENT_EXPORT_COLUMNS.join(','),
    ...incidents.map(incident =>
      INCIDENT_EXPORT_COLUMNS.map(column => csvCell(incident[column])).join(',')
    )
  ]
  return `﻿${lines.join('\r\n')}\r\n`
}

export type IncidentExportRange = { dateFrom: string; dateTo: string }

// JSON estructurado: metadatos de la exportacion + una entrada por incidencia con la
// clasificacion y la auditoria agrupadas.
export function incidentsToJson(
  incidents: ManualIncident[],
  range: IncidentExportRange,
  exportedAt: string
): string {
  return JSON.stringify(
    {
      exportado_en: exportedAt,
      rango: { desde: range.dateFrom, hasta: range.dateTo },
      total: incidents.length,
      incidencias: incidents.map(incident => ({
        id: incident.id,
        fecha: incident.fecha,
        hora: incident.hora,
        cliente: incident.cliente,
        telefono: incident.telefono,
        agente: incident.agente,
        clasificacion: {
          origen: incident.origen,
          tipo: incident.tipo,
          ambito: incident.ambito,
          resultado: incident.resultado
        },
        descripcion: incident.descripcion,
        registro: {
          creada_por: incident.created_by,
          creada_en: incident.created_at,
          editada_por: incident.updated_by,
          editada_en: incident.updated_at
        }
      }))
    },
    null,
    2
  )
}

export function incidentExportFilename(
  range: IncidentExportRange,
  extension: 'json' | 'csv'
): string {
  const days =
    range.dateFrom === range.dateTo
      ? range.dateFrom
      : `${range.dateFrom}_a_${range.dateTo}`
  return `incidencias-manuales_${days}.${extension}`
}
