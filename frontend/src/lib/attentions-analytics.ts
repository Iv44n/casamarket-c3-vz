import {
  type AgentLimit,
  type AttentionDirection,
  type AttentionFilter,
  type AttentionsAnalytics,
  type DemandAnalytics,
  DIRECTION_REPORT_NAME,
  type EstadosFilter
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
export function getAvailableEstados(analytics: AttentionsAnalytics): string[] {
  const estados = new Set<string>()
  for (const { estado } of analytics.incoming.statusCounts) {
    estados.add(estado)
  }
  for (const { estado } of analytics.outgoing.statusCounts) {
    estados.add(estado)
  }
  return [...estados].sort((a, b) => a.localeCompare(b))
}
function estadoAllowed(estado: string, estadosFilter: EstadosFilter): boolean {
  return estadosFilter === 'all' || estadosFilter.includes(estado)
}
export type StatusChartSlice = {
  id: string
  estado: string
  direction: AttentionDirection | null
  count: number
}
export function buildStatusChartData(
  analytics: AttentionsAnalytics,
  filter: AttentionFilter,
  estadosFilter: EstadosFilter
): {
  total: number
  slices: StatusChartSlice[]
} {
  if (filter !== 'all') {
    const statusCounts = analytics[filter].statusCounts.filter(({ estado }) =>
      estadoAllowed(estado, estadosFilter)
    )
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
    analytics.incoming.statusCounts
      .filter(({ estado }) => estadoAllowed(estado, estadosFilter))
      .map(({ estado, count }) => [estado, count])
  )
  const outgoingByEstado = new Map(
    analytics.outgoing.statusCounts
      .filter(({ estado }) => estadoAllowed(estado, estadosFilter))
      .map(({ estado, count }) => [estado, count])
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
  campaignCounts: { campana: string; count: number }[]
  avgAttentionSeconds: number | null
}
export function buildAgentRanking(
  analytics: AttentionsAnalytics,
  filter: AttentionFilter,
  limit: AgentLimit,
  estadosFilter: EstadosFilter
): AgentBarDatum[] {
  const directions =
    filter === 'incoming'
      ? [analytics.incoming]
      : filter === 'outgoing'
        ? [analytics.outgoing]
        : [analytics.incoming, analytics.outgoing]
  const merged = new Map<string, Map<string, number>>()
  const campaignMerged = new Map<string, Map<string, number>>()
  const attentionMerged = new Map<
    string,
    { totalSeconds: number; sampleCount: number }
  >()
  for (const direction of directions) {
    for (const { agente, estado, count } of direction.agentCounts) {
      if (!estadoAllowed(estado, estadosFilter)) {
        continue
      }
      const estadoCounts = merged.get(agente) ?? new Map<string, number>()
      estadoCounts.set(estado, (estadoCounts.get(estado) ?? 0) + count)
      merged.set(agente, estadoCounts)
    }
    for (const {
      agente,
      campana,
      estado,
      count
    } of direction.agentCampaignCounts) {
      if (!estadoAllowed(estado, estadosFilter)) {
        continue
      }
      const campanaCounts =
        campaignMerged.get(agente) ?? new Map<string, number>()
      campanaCounts.set(campana, (campanaCounts.get(campana) ?? 0) + count)
      campaignMerged.set(agente, campanaCounts)
    }
    for (const {
      agente,
      estado,
      totalSeconds,
      sampleCount
    } of direction.agentAttentionSeconds) {
      if (!estadoAllowed(estado, estadosFilter)) {
        continue
      }
      const current = attentionMerged.get(agente) ?? {
        totalSeconds: 0,
        sampleCount: 0
      }
      current.totalSeconds += totalSeconds
      current.sampleCount += sampleCount
      attentionMerged.set(agente, current)
    }
  }
  return [...merged.entries()]
    .map(([agente, estadoCounts]) => {
      const attention = attentionMerged.get(agente)
      return {
        agente,
        total: [...estadoCounts.values()].reduce(
          (sum, count) => sum + count,
          0
        ),
        estadoCounts: Object.fromEntries(estadoCounts),
        campaignCounts: [
          ...(campaignMerged.get(agente) ?? new Map<string, number>()).entries()
        ]
          .map(([campana, count]) => ({ campana, count }))
          .sort((a, b) => b.count - a.count),
        avgAttentionSeconds:
          attention && attention.sampleCount > 0
            ? attention.totalSeconds / attention.sampleCount
            : null
      }
    })
    .sort((a, b) => b.total - a.total || a.agente.localeCompare(b.agente))
    .slice(0, limit === 'all' ? undefined : limit)
}
export type TopCloserDatum = {
  agente: string
  count: number
}
const TOP_CLOSERS_LIMIT = 5
export function buildTopClosers(
  analytics: AttentionsAnalytics
): TopCloserDatum[] {
  const merged = new Map<string, number>()
  for (const direction of [analytics.incoming, analytics.outgoing]) {
    for (const { agente, estado, count } of direction.agentCounts) {
      if (estado !== 'Cerrada') continue
      merged.set(agente, (merged.get(agente) ?? 0) + count)
    }
  }
  return [...merged.entries()]
    .map(([agente, count]) => ({ agente, count }))
    .sort((a, b) => b.count - a.count || a.agente.localeCompare(b.agente))
    .slice(0, TOP_CLOSERS_LIMIT)
}
export type CampaignBarDatum = {
  campana: string
  total: number
  estadoCounts: Record<string, number>
}
export function buildCampaignRanking(
  analytics: AttentionsAnalytics,
  filter: AttentionFilter,
  estadosFilter: EstadosFilter
): CampaignBarDatum[] {
  const directions =
    filter === 'incoming'
      ? [analytics.incoming]
      : filter === 'outgoing'
        ? [analytics.outgoing]
        : [analytics.incoming, analytics.outgoing]
  const merged = new Map<string, Map<string, number>>()
  for (const direction of directions) {
    for (const { campana, estado, count } of direction.campaignCounts) {
      if (!estadoAllowed(estado, estadosFilter)) {
        continue
      }
      const estadoCounts = merged.get(campana) ?? new Map<string, number>()
      estadoCounts.set(estado, (estadoCounts.get(estado) ?? 0) + count)
      merged.set(campana, estadoCounts)
    }
  }
  return [...merged.entries()]
    .map(([campana, estadoCounts]) => ({
      campana,
      total: [...estadoCounts.values()].reduce((sum, count) => sum + count, 0),
      estadoCounts: Object.fromEntries(estadoCounts)
    }))
    .sort((a, b) => b.total - a.total || a.campana.localeCompare(b.campana))
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
export const DEMAND_DAY_LABELS: { dayOfWeek: number; label: string }[] = [
  { dayOfWeek: 1, label: 'Lun' },
  { dayOfWeek: 2, label: 'Mar' },
  { dayOfWeek: 3, label: 'Mié' },
  { dayOfWeek: 4, label: 'Jue' },
  { dayOfWeek: 5, label: 'Vie' },
  { dayOfWeek: 6, label: 'Sáb' },
  { dayOfWeek: 0, label: 'Dom' }
]
export const DEMAND_HOURS = Array.from({ length: 24 }, (_, hour) => hour)
export const DEMAND_LEVELS = ['bajo', 'medio', 'alto', 'pico'] as const
export type DemandLevel = 'none' | (typeof DEMAND_LEVELS)[number]
export const DEMAND_LEVEL_LABEL: Record<
  (typeof DEMAND_LEVELS)[number],
  string
> = {
  bajo: 'Bajo',
  medio: 'Medio',
  alto: 'Alto',
  pico: 'Pico'
}
export type DemandHeatmapCell = {
  dayOfWeek: number
  hour: number
  count: number
  level: DemandLevel
}
export type DemandHeatmapRow = {
  dayOfWeek: number
  label: string
  cells: DemandHeatmapCell[]
}
export type DemandHeatmap = {
  rows: DemandHeatmapRow[]
  total: number
}
export function buildDemandHeatmap(
  demand: DemandAnalytics,
  filter: AttentionFilter,
  estadosFilter: EstadosFilter
): DemandHeatmap {
  const counts = new Map<string, number>()
  let total = 0
  for (const bucket of demand.buckets) {
    if (filter !== 'all' && bucket.direction !== filter) continue
    if (!estadoAllowed(bucket.estado, estadosFilter)) continue
    const key = `${bucket.dayOfWeek}:${bucket.hour}`
    counts.set(key, (counts.get(key) ?? 0) + bucket.count)
    total += bucket.count
  }
  // Quantile-by-unique-value binning: robust to skewed/tied distributions,
  // unlike raw value thresholds which degenerate when many cells share a count.
  const uniqueSorted = [...new Set(counts.values())].sort((a, b) => a - b)
  const levelByCount = new Map<number, DemandLevel>()
  uniqueSorted.forEach((value, i) => {
    const bucket = Math.min(3, Math.floor((i * 4) / uniqueSorted.length))
    levelByCount.set(value, DEMAND_LEVELS[bucket])
  })
  function levelFor(count: number): DemandLevel {
    return count <= 0 ? 'none' : (levelByCount.get(count) ?? 'bajo')
  }
  const rows = DEMAND_DAY_LABELS.map(({ dayOfWeek, label }) => ({
    dayOfWeek,
    label,
    cells: DEMAND_HOURS.map(hour => {
      const count = counts.get(`${dayOfWeek}:${hour}`) ?? 0
      return { dayOfWeek, hour, count, level: levelFor(count) }
    })
  }))
  return { rows, total }
}
