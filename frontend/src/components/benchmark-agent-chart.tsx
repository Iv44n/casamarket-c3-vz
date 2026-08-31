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
// Esta fila dibuja 4 barras agrupadas (calidad, ortografia, manejo adecuado y
// una barra apilada de complejidad) mas una leyenda de 6 items -- necesita mas
// alto por fila y mas margen que el chart de una sola barra de al lado.
const QUALITY_CHART_ROW_HEIGHT_PX = 72
const QUALITY_CHART_EXTRA_HEIGHT_PX = 72

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

function pct(value: number | null | undefined): string {
  return `${Math.round(value ?? 0)}%`
}

// El tiempo de respuesta (segundos) queda en su propio grafico -- mezclarlo con
// las metricas de calidad (%) en un mismo eje X compartido haria que las barras
// no signifiquen lo mismo entre si. Las metricas de calidad SI comparten unidad
// (todas son %), asi que van juntas en un chart "grouped bar" al estilo Material:
// calidad/ortografia/manejo adecuado son barras individuales agrupadas por fila,
// y la distribucion de complejidad (baja/media/alta) es una barra apilada mas
// dentro de ese mismo grupo -- sus tres segmentos suman el 100% de los casos con
// complejidad evaluada de ese agente.
export function BenchmarkAgentChart({
  agents
}: {
  agents: AgentBenchmarkDatum[]
}) {
  const responseHeight = Math.max(
    agents.length * CHART_ROW_HEIGHT_PX + 40,
    CHART_MIN_HEIGHT_PX
  )
  const qualityHeight = Math.max(
    agents.length * QUALITY_CHART_ROW_HEIGHT_PX + QUALITY_CHART_EXTRA_HEIGHT_PX,
    CHART_MIN_HEIGHT_PX
  )
  const responseAriaLabel = `Tiempo promedio de primera respuesta por agente: ${agents
    .map(a =>
      a.avgFirstResponseSeconds !== null
        ? `${a.agente} ${formatSecondsAsDuration(a.avgFirstResponseSeconds)}`
        : `${a.agente} sin dato`
    )
    .join('; ')}`
  const qualityAriaLabel = `Calidad, ortografía, manejo adecuado y distribución de complejidad por agente: ${agents
    .map(
      a =>
        `${a.agente} calidad ${pct(a.qualityOkPct)}, ortografía ${pct(a.spellingOkPct)}, manejo adecuado ${pct(a.handledWellPct)}, complejidad baja ${pct(a.complexityLowPct)} media ${pct(a.complexityMediumPct)} alta ${pct(a.complexityHighPct)}`
    )
    .join('; ')}`
  const responseDataset = agents.map(a => ({
    agente: a.agente,
    avgFirstResponseSeconds: a.avgFirstResponseSeconds ?? 0
  }))
  const qualityDataset = agents.map(a => ({
    agente: a.agente,
    qualityOkPct: a.qualityOkPct ?? 0,
    spellingOkPct: a.spellingOkPct ?? 0,
    handledWellPct: a.handledWellPct ?? 0,
    complexityLowPct: a.complexityLowPct ?? 0,
    complexityMediumPct: a.complexityMediumPct ?? 0,
    complexityHighPct: a.complexityHighPct ?? 0
  }))
  return (
    <div className="flex flex-col gap-8">
      <div>
        <p className="mb-1 text-sm font-medium text-muted-foreground">
          Tiempo promedio de primera respuesta
        </p>
        <div role="img" aria-label={responseAriaLabel} className="w-full">
          <ChartThemeProvider>
            <BarChart
              dataset={responseDataset}
              layout="horizontal"
              height={responseHeight}
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
          Calidad, ortografía, manejo adecuado y complejidad
        </p>
        <div role="img" aria-label={qualityAriaLabel} className="w-full">
          <ChartThemeProvider>
            <BarChart
              dataset={qualityDataset}
              layout="horizontal"
              height={qualityHeight}
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
                  label: 'Calidad (presentación + despedida)',
                  color: 'var(--color-chart-2)',
                  valueFormatter: pct
                },
                {
                  dataKey: 'spellingOkPct',
                  label: 'Ortografía correcta',
                  color: 'var(--color-chart-3)',
                  valueFormatter: pct
                },
                {
                  dataKey: 'handledWellPct',
                  label: 'Manejo adecuado a la complejidad',
                  color: 'var(--color-chart-5)',
                  valueFormatter: pct
                },
                {
                  dataKey: 'complexityLowPct',
                  stack: 'complexity',
                  label: 'Complejidad baja',
                  color: 'var(--color-muted-foreground)',
                  valueFormatter: pct
                },
                {
                  dataKey: 'complexityMediumPct',
                  stack: 'complexity',
                  label: 'Complejidad media',
                  color: 'var(--color-chart-4)',
                  valueFormatter: pct
                },
                {
                  dataKey: 'complexityHighPct',
                  stack: 'complexity',
                  label: 'Complejidad alta',
                  color: 'var(--color-destructive)',
                  valueFormatter: pct
                }
              ]}
              borderRadius={3}
              slotProps={{
                legend: {
                  direction: 'horizontal',
                  position: { vertical: 'bottom', horizontal: 'center' }
                }
              }}
            />
          </ChartThemeProvider>
        </div>
      </div>
    </div>
  )
}
