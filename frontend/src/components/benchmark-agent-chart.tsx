import { BarChart } from '@mui/x-charts/BarChart'
import { ChartThemeProvider } from '#/components/mui-chart-theme'
import type { AgentBenchmarkDatum } from '#/lib/benchmark-analytics'
import {
  CHART_AXIS_LABEL_FONT_SIZE,
  CHART_MIN_HEIGHT_PX,
  CHART_ROW_HEIGHT_PX,
  CHART_VALUE_LABEL_FONT_SIZE
} from '#/lib/chart-typography'
import { formatSecondsAsDuration } from '#/lib/duration'

const MAX_AGENT_LABEL_CHARS = 22
const AGENT_AXIS_WIDTH_PX = 150

function truncateAgentLabel(name: string) {
  return name.length > MAX_AGENT_LABEL_CHARS
    ? `${name.slice(0, MAX_AGENT_LABEL_CHARS - 1)}…`
    : name
}

function agentAxis() {
  return {
    scaleType: 'band' as const,
    dataKey: 'agente',
    valueFormatter: (value: unknown) => truncateAgentLabel(String(value)),
    tickLabelStyle: { fontSize: CHART_AXIS_LABEL_FONT_SIZE },
    width: AGENT_AXIS_WIDTH_PX
  }
}

// Dos graficos separados, no uno solo con dos series -- tiempo de respuesta (segundos) y
// % de calidad no son comparables en un mismo eje X compartido; mezclarlos en un solo
// BarChart haria que las barras no signifiquen lo mismo entre si.
export function BenchmarkAgentChart({
  agents
}: {
  agents: AgentBenchmarkDatum[]
}) {
  const height = Math.max(
    agents.length * CHART_ROW_HEIGHT_PX + 40,
    CHART_MIN_HEIGHT_PX
  )
  const responseAriaLabel = `Tiempo promedio de primera respuesta por agente: ${agents
    .map(a =>
      a.avgFirstResponseSeconds !== null
        ? `${a.agente} ${formatSecondsAsDuration(a.avgFirstResponseSeconds)}`
        : `${a.agente} sin dato`
    )
    .join('; ')}`
  const qualityAriaLabel = `Porcentaje de casos con presentación y despedida por agente: ${agents
    .map(a =>
      a.qualityOkPct !== null
        ? `${a.agente} ${Math.round(a.qualityOkPct)}%`
        : `${a.agente} sin analisis`
    )
    .join('; ')}`
  const responseDataset = agents.map(a => ({
    agente: a.agente,
    avgFirstResponseSeconds: a.avgFirstResponseSeconds ?? 0
  }))
  const qualityDataset = agents.map(a => ({
    agente: a.agente,
    qualityOkPct: a.qualityOkPct ?? 0
  }))
  return (
    <div className="grid gap-6 md:grid-cols-2">
      <div>
        <p className="mb-1 text-sm font-medium text-muted-foreground">
          Tiempo promedio de primera respuesta
        </p>
        <div role="img" aria-label={responseAriaLabel} className="w-full">
          <ChartThemeProvider>
            <BarChart
              dataset={responseDataset}
              layout="horizontal"
              height={height}
              yAxis={[agentAxis()]}
              xAxis={[
                {
                  disableLine: true,
                  disableTicks: true,
                  tickLabelInterval: () => false
                }
              ]}
              series={[
                {
                  dataKey: 'avgFirstResponseSeconds',
                  label: 'Primera respuesta',
                  color: 'var(--color-chart-2)',
                  valueFormatter: value => formatSecondsAsDuration(value ?? 0)
                }
              ]}
              borderRadius={4}
              hideLegend
              sx={{
                '& .MuiBarChart-label': {
                  fill: '#0a0a0a !important',
                  fontWeight: 700,
                  fontSize: CHART_VALUE_LABEL_FONT_SIZE
                }
              }}
            />
          </ChartThemeProvider>
        </div>
      </div>
      <div>
        <p className="mb-1 text-sm font-medium text-muted-foreground">
          % con presentación y despedida
        </p>
        <div role="img" aria-label={qualityAriaLabel} className="w-full">
          <ChartThemeProvider>
            <BarChart
              dataset={qualityDataset}
              layout="horizontal"
              height={height}
              yAxis={[agentAxis()]}
              xAxis={[
                {
                  disableLine: true,
                  disableTicks: true,
                  tickLabelInterval: () => false,
                  min: 0,
                  max: 100
                }
              ]}
              series={[
                {
                  dataKey: 'qualityOkPct',
                  label: 'Calidad',
                  color: 'var(--color-chart-4)',
                  valueFormatter: value => `${Math.round(value ?? 0)}%`
                }
              ]}
              borderRadius={4}
              hideLegend
              sx={{
                '& .MuiBarChart-label': {
                  fill: '#0a0a0a !important',
                  fontWeight: 700,
                  fontSize: CHART_VALUE_LABEL_FONT_SIZE
                }
              }}
            />
          </ChartThemeProvider>
        </div>
      </div>
    </div>
  )
}
