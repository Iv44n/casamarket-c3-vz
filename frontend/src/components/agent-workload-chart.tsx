import type { BarItem } from '@mui/x-charts/BarChart'
import { BarChart } from '@mui/x-charts/BarChart'
import {
  ChartsTooltipContainer,
  useAxesTooltip
} from '@mui/x-charts/ChartsTooltip'
import { createContext, useContext } from 'react'
import { ChartThemeProvider } from '#/components/mui-chart-theme'
import { type AgentBarDatum, estadoColor } from '#/lib/attentions-analytics'
import {
  CHART_AXIS_LABEL_FONT_SIZE,
  CHART_LEGEND_FONT_SIZE,
  CHART_MIN_HEIGHT_PX,
  CHART_ROW_HEIGHT_PX,
  CHART_VALUE_LABEL_FONT_SIZE
} from '#/lib/chart-typography'
import { formatSecondsAsDuration } from '#/lib/duration'

const MAX_AGENT_LABEL_CHARS = 22
const AGENT_AXIS_WIDTH_PX = 170
const STACK_ID = 'atenciones'
function truncateAgentLabel(name: string) {
  return name.length > MAX_AGENT_LABEL_CHARS
    ? `${name.slice(0, MAX_AGENT_LABEL_CHARS - 1)}…`
    : name
}

const AgentTooltipDataContext = createContext<AgentBarDatum[]>([])

function AgentTooltipContent() {
  const agents = useContext(AgentTooltipDataContext)
  const tooltipData = useAxesTooltip()
  if (!tooltipData || tooltipData.length === 0) return null
  const agent = agents[tooltipData[0].dataIndex]
  if (!agent) return null
  const campaigns =
    agent.campaignCounts.length > 0
      ? agent.campaignCounts
          .map(({ campana, count }) => `${campana} (${count})`)
          .join(', ')
      : 'sin campaña registrada'
  const attentionTime =
    agent.avgAttentionSeconds === null
      ? 'sin datos'
      : formatSecondsAsDuration(agent.avgAttentionSeconds)
  return (
    <div className="min-w-56 rounded-lg border border-border bg-popover p-3 text-popover-foreground text-xs shadow-md">
      <p className="mb-1.5 font-medium text-sm">{agent.agente}</p>
      <div className="space-y-1">
        {Object.entries(agent.estadoCounts).map(([estado, count]) => (
          <div key={estado} className="flex items-center gap-1.5">
            <span
              className="size-2 shrink-0 rounded-full"
              style={{ background: estadoColor(estado) }}
            />
            <span>{estado}</span>
            <span className="ml-auto font-medium">{count}</span>
          </div>
        ))}
      </div>
      <div className="mt-2 space-y-0.5 border-border border-t pt-2 text-muted-foreground">
        <p>Campañas: {campaigns}</p>
        <p>Tiempo de atención promedio: {attentionTime}</p>
      </div>
    </div>
  )
}
function AgentTooltip() {
  return (
    <ChartsTooltipContainer trigger="axis">
      <AgentTooltipContent />
    </ChartsTooltipContainer>
  )
}

export function AgentWorkloadChart({
  agents,
  onAgentClick
}: {
  agents: AgentBarDatum[]
  onAgentClick?: (agente: string) => void
}) {
  const ariaLabel = `Atenciones por agente: ${agents
    .map(({ agente, total, estadoCounts }) => {
      const breakdown = Object.entries(estadoCounts)
        .map(([estado, count]) => `${estado} ${count}`)
        .join(', ')
      return `${agente} ${total} (${breakdown})`
    })
    .join('; ')}`
  const estadoTotals = new Map<string, number>()
  for (const { estadoCounts } of agents) {
    for (const [estado, count] of Object.entries(estadoCounts)) {
      estadoTotals.set(estado, (estadoTotals.get(estado) ?? 0) + count)
    }
  }
  const estados = [...estadoTotals.keys()].sort(
    (a, b) => (estadoTotals.get(b) ?? 0) - (estadoTotals.get(a) ?? 0)
  )
  const dataset = agents.map(({ agente, estadoCounts }) => {
    const row: Record<string, number | string> = { agente }
    for (const estado of estados) {
      row[estado] = estadoCounts[estado] ?? 0
    }
    return row
  })
  const series = estados.map(estado => ({
    dataKey: estado,
    label: estado,
    color: estadoColor(estado),
    stack: STACK_ID,
    valueFormatter: (value: number | null) => `${value ?? 0} ${estado}`,
    barLabel: (item: BarItem) => (item.value ? String(item.value) : null)
  }))
  const height = Math.max(
    agents.length * CHART_ROW_HEIGHT_PX + 40,
    CHART_MIN_HEIGHT_PX
  )
  return (
    <div role="img" aria-label={ariaLabel} className="w-full">
      <AgentTooltipDataContext.Provider value={agents}>
        <ChartThemeProvider>
          <BarChart
            dataset={dataset}
            layout="horizontal"
            height={height}
            slots={{ tooltip: AgentTooltip }}
            onItemClick={(_event, item) => {
              const agent = agents[item.dataIndex]
              if (agent) onAgentClick?.(agent.agente)
            }}
            yAxis={[
              {
                scaleType: 'band',
                dataKey: 'agente',
                valueFormatter: value => truncateAgentLabel(String(value)),
                tickLabelStyle: { fontSize: CHART_AXIS_LABEL_FONT_SIZE },
                width: AGENT_AXIS_WIDTH_PX
              }
            ]}
            xAxis={[
              {
                disableLine: true,
                disableTicks: true,
                tickLabelInterval: () => false
              }
            ]}
            series={series}
            borderRadius={4}
            sx={{
              '& .MuiBarChart-series': {
                cursor: onAgentClick ? 'pointer' : undefined
              },
              '& .MuiBarChart-label': {
                fill: '#0a0a0a !important',
                fontWeight: 700,
                fontSize: CHART_VALUE_LABEL_FONT_SIZE
              },
              '& .MuiChartsLegend-label': {
                fontSize: CHART_LEGEND_FONT_SIZE
              }
            }}
          />
        </ChartThemeProvider>
      </AgentTooltipDataContext.Provider>
    </div>
  )
}
