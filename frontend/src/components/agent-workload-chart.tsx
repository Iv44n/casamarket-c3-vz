import type { BarItem } from '@mui/x-charts/BarChart'
import { BarChart } from '@mui/x-charts/BarChart'
import { ChartThemeProvider } from '#/components/mui-chart-theme'
import { type AgentBarDatum, estadoColor } from '#/lib/attentions-analytics'

const MAX_AGENT_LABEL_CHARS = 22
const AGENT_AXIS_WIDTH_PX = 170
const STACK_ID = 'atenciones'
function truncateAgentLabel(name: string) {
  return name.length > MAX_AGENT_LABEL_CHARS
    ? `${name.slice(0, MAX_AGENT_LABEL_CHARS - 1)}…`
    : name
}
export function AgentWorkloadChart({ agents }: { agents: AgentBarDatum[] }) {
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
  return (
    <div role="img" aria-label={ariaLabel} className="h-full w-full">
      <ChartThemeProvider>
        <BarChart
          dataset={dataset}
          layout="horizontal"
          yAxis={[
            {
              scaleType: 'band',
              dataKey: 'agente',
              valueFormatter: value => truncateAgentLabel(String(value)),
              tickLabelStyle: { fontSize: 12 },
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
            '& .MuiBarChart-label': {
              fill: '#0a0a0a !important',
              fontWeight: 700,
              fontSize: 12
            }
          }}
        />
      </ChartThemeProvider>
    </div>
  )
}
