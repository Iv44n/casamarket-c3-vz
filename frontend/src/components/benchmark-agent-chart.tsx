import { BarChart } from '@mui/x-charts/BarChart'
import { ChartThemeProvider } from '#/components/mui-chart-theme'
import type {
  AgentBenchmarkDatum,
  TransferNotificationDatum
} from '#/lib/benchmark-analytics'
import {
  CHART_AXIS_LABEL_FONT_SIZE,
  CHART_MIN_HEIGHT_PX,
  CHART_ROW_HEIGHT_PX,
  CHART_VALUE_LABEL_FONT_SIZE
} from '#/lib/chart-typography'
import { formatSecondsAsDuration } from '#/lib/duration'

const MAX_AGENT_LABEL_CHARS = 22
const AGENT_AXIS_WIDTH_PX = 150
// Esta fila dibuja 5 barras agrupadas (saludo, despedida, ortografia, manejo
// adecuado y una barra apilada de complejidad) mas una leyenda de 7 items --
// necesita mas alto por fila y mas margen que el chart de una sola barra de
// al lado.
const QUALITY_CHART_ROW_HEIGHT_PX = 92
const QUALITY_CHART_EXTRA_HEIGHT_PX = 80
const TRANSFER_CHART_COLOR = 'var(--color-chart-1)'
// Saludo/despedida son 2 de los 4 criterios que antes componian el score combinado
// "calidad general" (junto con ortografia/manejo adecuado, que tienen su propio
// color) -- tonos mas claros del mismo verde para que se lean como su misma familia
// en vez de colores sueltos sin relacion.
const GREETING_CHART_COLOR =
  'color-mix(in oklab, var(--color-chart-2) 80%, white)'
const FAREWELL_CHART_COLOR =
  'color-mix(in oklab, var(--color-chart-2) 55%, white)'

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
// saludo/despedida/ortografia/manejo adecuado son barras individuales agrupadas
// por fila (sin un score combinado -- un AND de las 4 colapsa a un numero bajo
// parejo que no dice cual es el problema real, ver caso Andrea Siapo), y la
// distribucion de complejidad (baja/media/alta) es una barra apilada mas dentro
// de ese mismo grupo -- sus tres segmentos suman el 100% de los casos con
// complejidad evaluada de ese agente.
export function BenchmarkAgentChart({
  agents,
  transferNotifications
}: {
  agents: AgentBenchmarkDatum[]
  transferNotifications: TransferNotificationDatum[]
}) {
  const responseHeight = Math.max(
    agents.length * CHART_ROW_HEIGHT_PX + 40,
    CHART_MIN_HEIGHT_PX
  )
  const qualityHeight = Math.max(
    agents.length * QUALITY_CHART_ROW_HEIGHT_PX + QUALITY_CHART_EXTRA_HEIGHT_PX,
    CHART_MIN_HEIGHT_PX
  )
  const transferHeight = Math.max(
    transferNotifications.length * CHART_ROW_HEIGHT_PX + 40,
    CHART_MIN_HEIGHT_PX
  )
  const responseAriaLabel = `Tiempo promedio de primera respuesta por agente: ${agents
    .map(a =>
      a.avgFirstResponseSeconds !== null
        ? `${a.agente} ${formatSecondsAsDuration(a.avgFirstResponseSeconds)}`
        : `${a.agente} sin dato`
    )
    .join('; ')}`
  const qualityAriaLabel = `Saludo, despedida, ortografía, manejo adecuado y distribución de complejidad por agente: ${agents
    .map(
      a =>
        `${a.agente} saludo ${pct(a.greetingOkPct)}, despedida ${pct(a.farewellOkPct)}, ortografía ${pct(a.spellingOkPct)}, manejo adecuado ${pct(a.handledWellPct)}, complejidad baja ${pct(a.complexityLowPct)} media ${pct(a.complexityMediumPct)} alta ${pct(a.complexityHighPct)}`
    )
    .join('; ')}`
  const transferAriaLabel = `Porcentaje de casos donde se avisó al cliente antes de transferir, por agente que transfiere: ${transferNotifications
    .map(t => `${t.agente} ${pct(t.informedPct)}`)
    .join('; ')}`
  const responseDataset = agents.map(a => ({
    agente: a.agente,
    avgFirstResponseSeconds: a.avgFirstResponseSeconds ?? 0
  }))
  const qualityDataset = agents.map(a => ({
    agente: a.agente,
    greetingOkPct: a.greetingOkPct ?? 0,
    farewellOkPct: a.farewellOkPct ?? 0,
    spellingOkPct: a.spellingOkPct ?? 0,
    handledWellPct: a.handledWellPct ?? 0,
    complexityLowPct: a.complexityLowPct ?? 0,
    complexityMediumPct: a.complexityMediumPct ?? 0,
    complexityHighPct: a.complexityHighPct ?? 0
  }))
  const transferDataset = transferNotifications.map(t => ({
    agente: t.agente,
    informedPct: t.informedPct ?? 0
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
          Saludo, despedida, ortografía, manejo adecuado y complejidad
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
                  dataKey: 'greetingOkPct',
                  label: 'Saludo (casual o formal)',
                  color: GREETING_CHART_COLOR,
                  valueFormatter: pct
                },
                {
                  dataKey: 'farewellOkPct',
                  label: 'Despedida',
                  color: FAREWELL_CHART_COLOR,
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
      {transferNotifications.length > 0 && (
        <div>
          <p className="mb-1 text-sm font-medium text-muted-foreground">
            Aviso de transferencia (agente que transfiere)
          </p>
          <div role="img" aria-label={transferAriaLabel} className="w-full">
            <ChartThemeProvider>
              <BarChart
                dataset={transferDataset}
                layout="horizontal"
                height={transferHeight}
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
                    dataKey: 'informedPct',
                    label: 'Avisó antes de transferir',
                    color: TRANSFER_CHART_COLOR,
                    valueFormatter: pct
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
      )}
    </div>
  )
}
