import {
  type AgentLimit,
  type AttentionDirection,
  type AttentionFilter,
  type AttentionsAnalytics,
  DIRECTION_REPORT_NAME
} from '#/server/schemas'
export const ESTADO_COLOR: Record<string, string> = {
  Cerrada: 'var(--color-chart-2)',
  Asignada: 'var(--color-chart-3)',
  Abierta: 'var(--color-chart-4)'
}
export const ESTADO_FALLBACK_COLOR = 'var(--color-muted-foreground)'
export function estadoColor(estado: string): string {
  return ESTADO_COLOR[estado] ?? ESTADO_FALLBACK_COLOR
}
export type StatusChartSlice = {
  id: string
  estado: string
  direction: AttentionDirection | null
  count: number
}
export function buildStatusChartData(
  analytics: AttentionsAnalytics,
  filter: AttentionFilter
): {
  total: number
  slices: StatusChartSlice[]
} {
  if (filter !== 'all') {
    const { statusCounts } = analytics[filter]
    return {
      total: statusCounts.reduce((sum, { count }) => sum + count, 0),
      slices: statusCounts.map(({ estado, count }) => ({
        id: estado,
        estado,
        direction: null,
        count
      }))
    }
  }
  const incomingByEstado = new Map(
    analytics.incoming.statusCounts.map(({ estado, count }) => [estado, count])
  )
  const outgoingByEstado = new Map(
    analytics.outgoing.statusCounts.map(({ estado, count }) => [estado, count])
  )
  const estados = [
    ...new Set([...incomingByEstado.keys(), ...outgoingByEstado.keys()])
  ]
  const combined = estados
    .map(estado => {
      const incoming = incomingByEstado.get(estado) ?? 0
      const outgoing = outgoingByEstado.get(estado) ?? 0
      return { estado, incoming, outgoing, total: incoming + outgoing }
    })
    .sort((a, b) => b.total - a.total)
  const slices: StatusChartSlice[] = []
  for (const { estado, incoming, outgoing } of combined) {
    if (incoming > 0) {
      slices.push({
        id: `${estado}:incoming`,
        estado,
        direction: 'incoming',
        count: incoming
      })
    }
    if (outgoing > 0) {
      slices.push({
        id: `${estado}:outgoing`,
        estado,
        direction: 'outgoing',
        count: outgoing
      })
    }
  }
  return {
    total: combined.reduce((sum, { total }) => sum + total, 0),
    slices
  }
}
export type AgentBarDatum = {
  agente: string
  total: number
  estadoCounts: Record<string, number>
}
export function buildAgentRanking(
  analytics: AttentionsAnalytics,
  filter: AttentionFilter,
  limit: AgentLimit
): AgentBarDatum[] {
  const directions =
    filter === 'incoming'
      ? [analytics.incoming]
      : filter === 'outgoing'
        ? [analytics.outgoing]
        : [analytics.incoming, analytics.outgoing]
  const merged = new Map<string, Map<string, number>>()
  for (const direction of directions) {
    for (const { agente, estado, count } of direction.agentCounts) {
      const estadoCounts = merged.get(agente) ?? new Map<string, number>()
      estadoCounts.set(estado, (estadoCounts.get(estado) ?? 0) + count)
      merged.set(agente, estadoCounts)
    }
  }
  return [...merged.entries()]
    .map(([agente, estadoCounts]) => ({
      agente,
      total: [...estadoCounts.values()].reduce((sum, count) => sum + count, 0),
      estadoCounts: Object.fromEntries(estadoCounts)
    }))
    .sort((a, b) => b.total - a.total || a.agente.localeCompare(b.agente))
    .slice(0, limit === 'all' ? undefined : limit)
}
export function describeAvailability(
  analytics: AttentionsAnalytics,
  filter: AttentionFilter
): {
  blockedMessage: string | null
  advisoryMessage: string | null
} {
  const { incoming, outgoing } = analytics
  if (filter !== 'all') {
    const direction = analytics[filter]
    return {
      blockedMessage: direction.available
        ? null
        : `Todavia no se descargo ningun archivo de "${DIRECTION_REPORT_NAME[filter]}".`,
      advisoryMessage: null
    }
  }
  if (!incoming.available && !outgoing.available) {
    return {
      blockedMessage: `Todavia no se descargo ningun archivo de "${DIRECTION_REPORT_NAME.incoming}" ni de "${DIRECTION_REPORT_NAME.outgoing}".`,
      advisoryMessage: null
    }
  }
  if (!incoming.available) {
    return {
      blockedMessage: null,
      advisoryMessage: `Los datos de "${DIRECTION_REPORT_NAME.incoming}" aun no se descargaron; esta vista solo refleja atenciones salientes.`
    }
  }
  if (!outgoing.available) {
    return {
      blockedMessage: null,
      advisoryMessage: `Los datos de "${DIRECTION_REPORT_NAME.outgoing}" aun no se descargaron; esta vista solo refleja atenciones entrantes.`
    }
  }
  return { blockedMessage: null, advisoryMessage: null }
}
