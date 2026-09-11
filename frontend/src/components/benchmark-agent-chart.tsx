import { BarChart } from '@mui/x-charts/BarChart'
import {
  getValueToPositionMapper,
  useXScale,
  useYScale
} from '@mui/x-charts/hooks'
import { ChevronDownIcon } from 'lucide-react'
import { useState } from 'react'
import { ChartThemeProvider } from '#/components/mui-chart-theme'
import { Button } from '#/components/ui/button'
import { Checkbox } from '#/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger
} from '#/components/ui/dropdown-menu'
import { Label } from '#/components/ui/label'
import { Separator } from '#/components/ui/separator'
import type {
  AgentBenchmarkDatum,
  TransferNotificationDatum
} from '#/lib/benchmark-analytics'
import {
  CHART_AXIS_LABEL_FONT_SIZE,
  CHART_VALUE_LABEL_FONT_SIZE
} from '#/lib/chart-typography'
import { formatSecondsAsDuration } from '#/lib/duration'

const MAX_AGENT_LABEL_CHARS = 14
// Barras verticales: el ancho total escala con la cantidad de agentes (una
// columna por agente) en vez de la altura -- lo opuesto del chart horizontal
// de al lado. El contenedor scrollea horizontalmente si no entra.
const AGENT_COLUMN_WIDTH_PX = 64
// Ancho por CADA barra visible dentro del grupo de un agente (saludo,
// despedida, ortografia, manejo adecuado, complejidad apilada) -- el ancho
// total de la fila de calidad escala con cuantas de esas 5 estan activas via
// el selector "Mostrar", no siempre las 5.
const QUALITY_BAR_SLOT_WIDTH_PX = 34
const CHART_MIN_WIDTH_PX = 420
const CHART_HEIGHT_PX = 320
// Mas alto que el resto: suma la leyenda horizontal de 7 items debajo del eje
// X ya rotado.
const QUALITY_CHART_HEIGHT_PX = 420
const TRANSFER_CHART_COLOR = 'var(--color-chart-1)'
const PRODUCTIVITY_RAW_CHART_COLOR = 'var(--color-chart-3)'
const PRODUCTIVITY_WEIGHTED_CHART_COLOR = 'var(--color-primary)'
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
    tickLabelStyle: {
      fontSize: CHART_AXIS_LABEL_FONT_SIZE,
      angle: -35,
      textAnchor: 'end' as const
    },
    height: 'auto' as const
  }
}
// Eje de valor (vertical, antes el eje X del layout horizontal) -- oculto:
// las barras ya muestran su propio valor via barLabel/label, un eje numerico
// al lado seria redundante.
const hiddenValueAxis = {
  disableLine: true,
  disableTicks: true,
  tickLabelInterval: () => false
}

function pct(value: number | null | undefined): string {
  return `${Math.round(value ?? 0)}%`
}

// Etiqueta "x1.85" arriba del par de barras (bruto/ponderado) de cada agente --
// la razon score/bruto que responde "que tan cargada de complejidad media/alta
// esta la mezcla de este agente" (ver lib/benchmark-analytics.ts). Renderizada
// como <text> plano dentro del <svg> del chart (mismo patron que
// PieCenterLabel en status-donut-chart.tsx), no como HTML superpuesto, para
// que quede alineada en las mismas coordenadas que las barras sin importar el
// tamano del contenedor. useXScale/useYScale solo funcionan como hijos de un
// componente MUI X Charts (leen el contexto que ChartsDataProvider provee) --
// no se puede precalcular esto fuera del <BarChart>.
function ProductivityRatioLabels({
  data
}: {
  data: Array<{
    agente: string
    complexityCheckedCount: number
    complexityWeightedScore: number
  }>
}) {
  const xPosition = getValueToPositionMapper(useXScale())
  const yPosition = getValueToPositionMapper(useYScale())
  return (
    <>
      {data.map(item => {
        if (item.complexityCheckedCount === 0) return null
        const ratio = item.complexityWeightedScore / item.complexityCheckedCount
        const topValue = Math.max(
          item.complexityCheckedCount,
          item.complexityWeightedScore
        )
        return (
          <text
            key={item.agente}
            x={xPosition(item.agente)}
            y={yPosition(topValue) - 22}
            textAnchor="middle"
            fontSize={CHART_VALUE_LABEL_FONT_SIZE}
            fontWeight={700}
            fill="var(--color-foreground)"
          >
            {`×${ratio.toFixed(2)}`}
          </text>
        )
      })}
    </>
  )
}

// Los 3 segmentos de complejidad cuentan como UNA sola barra (apilada) a
// efectos del selector "Mostrar" -- ocultar/mostrar complejidad los mueve a
// los tres juntos, no tiene sentido activar solo un segmento del apilado.
const QUALITY_METRIC_OPTIONS = [
  { key: 'greeting', label: 'Saludo (casual o formal)' },
  { key: 'farewell', label: 'Despedida' },
  { key: 'spelling', label: 'Ortografía correcta' },
  { key: 'handledWell', label: 'Manejo adecuado a la complejidad' },
  { key: 'complexity', label: 'Complejidad (baja/media/alta)' }
] as const
type QualityMetricKey = (typeof QUALITY_METRIC_OPTIONS)[number]['key']

// Criterio de orden del chart de productividad -- 'ratio' es el score
// ponderado entre casos evaluados (razon "x1.85" de ProductivityRatioLabels),
// no un cuarto numero nuevo: reordena las mismas barras por esa razon en vez
// de por el score absoluto, para responder "que agente maneja la mezcla mas
// pesada" en vez de "quien tiene el score mas alto" (que favorece volumen).
const PRODUCTIVITY_SORT_OPTIONS = [
  { key: 'weighted', label: 'Score ponderado' },
  { key: 'raw', label: 'Casos evaluados (bruto)' },
  { key: 'ratio', label: 'Razón (score ÷ bruto)' }
] as const
type ProductivitySortKey = (typeof PRODUCTIVITY_SORT_OPTIONS)[number]['key']

function QualityMetricsQuickActions({
  onSelectAll,
  onSelectNone
}: {
  onSelectAll: () => void
  onSelectNone: () => void
}) {
  return (
    <>
      <div className="flex items-center justify-between gap-2 px-3 py-1.5">
        <button
          type="button"
          className="text-xs font-medium text-primary hover:underline"
          onClick={onSelectAll}
        >
          Marcar todas
        </button>
        <button
          type="button"
          className="text-xs font-medium text-primary hover:underline"
          onClick={onSelectNone}
        >
          Ninguna
        </button>
      </div>
      <Separator className="mb-1" />
    </>
  )
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
  const [visibleMetrics, setVisibleMetrics] = useState<QualityMetricKey[]>(
    QUALITY_METRIC_OPTIONS.map(option => option.key)
  )
  const [productivitySortKey, setProductivitySortKey] =
    useState<ProductivitySortKey>('weighted')
  function isMetricVisible(key: QualityMetricKey) {
    return visibleMetrics.includes(key)
  }
  function toggleMetric(key: QualityMetricKey) {
    setVisibleMetrics(current =>
      current.includes(key) ? current.filter(k => k !== key) : [...current, key]
    )
  }
  function selectAllMetrics() {
    setVisibleMetrics(QUALITY_METRIC_OPTIONS.map(option => option.key))
  }
  function selectNoMetrics() {
    setVisibleMetrics([])
  }
  const metricsFilterLabel =
    visibleMetrics.length === QUALITY_METRIC_OPTIONS.length
      ? 'Todas'
      : visibleMetrics.length === 0
        ? 'Ninguna'
        : visibleMetrics.length === 1
          ? QUALITY_METRIC_OPTIONS.find(
              option => option.key === visibleMetrics[0]
            )?.label
          : `${visibleMetrics.length} de ${QUALITY_METRIC_OPTIONS.length}`

  // Cada grafico ordena de menor a mayor por SU propio numero mostrado --
  // no hay un orden unico compartido porque cada uno grafica una metrica
  // distinta. El de calidad no tiene un solo valor por barra cuando se
  // muestran varias metricas a la vez (son 4 barras + 1 apilada por agente),
  // asi que en ese caso ordena por la calidad propia combinada del agente
  // (ownConductOkPct, el mismo score del badge "Mejor calidad") -- PERO si el
  // selector "Mostrar" deja una sola metrica visible, el orden pasa a ser el
  // de esa metrica puntual: mostrar solo "Despedida", por ejemplo, y que las
  // barras NO queden ordenadas por despedida se veria roto.
  const singleVisibleMetric =
    visibleMetrics.length === 1 ? visibleMetrics[0] : null
  function qualitySortValue(agent: AgentBenchmarkDatum): number {
    switch (singleVisibleMetric) {
      case 'greeting':
        return agent.greetingOkPct ?? 0
      case 'farewell':
        return agent.farewellOkPct ?? 0
      case 'spelling':
        return agent.spellingOkPct ?? 0
      case 'handledWell':
        return agent.handledWellPct ?? 0
      case 'complexity':
        // La complejidad no tiene un solo "bueno/malo" (es una distribucion
        // baja/media/alta) -- ordena por cuanta complejidad alta maneja cada
        // agente, el segmento que mas cambia el perfil de dificultad.
        return agent.complexityHighPct ?? 0
      default:
        return agent.ownConductOkPct ?? 0
    }
  }
  const responseSorted = [...agents].sort(
    (a, b) =>
      (a.avgFirstResponseSeconds ?? 0) - (b.avgFirstResponseSeconds ?? 0)
  )
  const qualitySorted = [...agents].sort(
    (a, b) => qualitySortValue(a) - qualitySortValue(b)
  )
  // 'ratio' (score / bruto) es 0 para un agente sin ningun caso con
  // complejidad juzgada -- mismo tratamiento que 'weighted'/'raw' en ese caso
  // (se van al fondo del orden ascendente, no rompen la division por 0).
  function productivitySortValue(agent: AgentBenchmarkDatum): number {
    switch (productivitySortKey) {
      case 'raw':
        return agent.complexityCheckedCount
      case 'ratio':
        return agent.complexityCheckedCount > 0
          ? agent.complexityWeightedScore / agent.complexityCheckedCount
          : 0
      default:
        return agent.complexityWeightedScore
    }
  }
  const productivitySorted = [...agents].sort(
    (a, b) => productivitySortValue(a) - productivitySortValue(b)
  )
  const transferSorted = [...transferNotifications].sort(
    (a, b) => (a.informedPct ?? 0) - (b.informedPct ?? 0)
  )
  const responseWidth = Math.max(
    responseSorted.length * AGENT_COLUMN_WIDTH_PX,
    CHART_MIN_WIDTH_PX
  )
  const qualityWidth = Math.max(
    qualitySorted.length *
      Math.max(visibleMetrics.length, 1) *
      QUALITY_BAR_SLOT_WIDTH_PX,
    CHART_MIN_WIDTH_PX
  )
  const transferWidth = Math.max(
    transferSorted.length * AGENT_COLUMN_WIDTH_PX,
    CHART_MIN_WIDTH_PX
  )
  const productivityWidth = Math.max(
    productivitySorted.length * 2 * QUALITY_BAR_SLOT_WIDTH_PX,
    CHART_MIN_WIDTH_PX
  )
  const responseAriaLabel = `Tiempo promedio de primera respuesta por agente, de menor a mayor: ${responseSorted
    .map(a =>
      a.avgFirstResponseSeconds !== null
        ? `${a.agente} ${formatSecondsAsDuration(a.avgFirstResponseSeconds)}`
        : `${a.agente} sin dato`
    )
    .join('; ')}`
  const qualityAriaLabel = `Saludo, despedida, ortografía, manejo adecuado y distribución de complejidad por agente, de menor a mayor calidad general (mostrando: ${QUALITY_METRIC_OPTIONS.filter(
    option => isMetricVisible(option.key)
  )
    .map(option => option.label)
    .join(', ')}): ${qualitySorted
    .map(a => {
      const parts: string[] = []
      if (isMetricVisible('greeting'))
        parts.push(`saludo ${pct(a.greetingOkPct)}`)
      if (isMetricVisible('farewell'))
        parts.push(`despedida ${pct(a.farewellOkPct)}`)
      if (isMetricVisible('spelling'))
        parts.push(`ortografía ${pct(a.spellingOkPct)}`)
      if (isMetricVisible('handledWell'))
        parts.push(`manejo adecuado ${pct(a.handledWellPct)}`)
      if (isMetricVisible('complexity'))
        parts.push(
          `complejidad baja ${pct(a.complexityLowPct)} media ${pct(a.complexityMediumPct)} alta ${pct(a.complexityHighPct)}`
        )
      return `${a.agente} ${parts.join(', ')}`
    })
    .join('; ')}`
  const transferAriaLabel = `Porcentaje de casos donde se avisó al cliente antes de transferir, por agente que transfiere, de menor a mayor: ${transferSorted
    .map(t => `${t.agente} ${pct(t.informedPct)}`)
    .join('; ')}`
  const productivitySortLabel =
    PRODUCTIVITY_SORT_OPTIONS.find(option => option.key === productivitySortKey)
      ?.label ?? ''
  const productivityAriaLabel = `Casos evaluados y score de productividad ponderado por complejidad (baja=1, media=2, alta=3) por agente, de menor a mayor ${productivitySortLabel.toLowerCase()}: ${productivitySorted
    .map(a => {
      const ratio =
        a.complexityCheckedCount > 0
          ? (a.complexityWeightedScore / a.complexityCheckedCount).toFixed(2)
          : null
      return `${a.agente} ${a.complexityCheckedCount} casos, score ${a.complexityWeightedScore}${ratio !== null ? `, razón x${ratio}` : ''}`
    })
    .join('; ')}`
  const responseDataset = responseSorted.map(a => ({
    agente: a.agente,
    avgFirstResponseSeconds: a.avgFirstResponseSeconds ?? 0
  }))
  const qualityDataset = qualitySorted.map(a => ({
    agente: a.agente,
    greetingOkPct: a.greetingOkPct ?? 0,
    farewellOkPct: a.farewellOkPct ?? 0,
    spellingOkPct: a.spellingOkPct ?? 0,
    handledWellPct: a.handledWellPct ?? 0,
    complexityLowPct: a.complexityLowPct ?? 0,
    complexityMediumPct: a.complexityMediumPct ?? 0,
    complexityHighPct: a.complexityHighPct ?? 0
  }))
  const transferDataset = transferSorted.map(t => ({
    agente: t.agente,
    informedPct: t.informedPct ?? 0
  }))
  const productivityDataset = productivitySorted.map(a => ({
    agente: a.agente,
    complexityCheckedCount: a.complexityCheckedCount,
    complexityWeightedScore: a.complexityWeightedScore
  }))
  // Headroom explicito arriba de la barra mas alta -- sin esto el eje Y auto-
  // escala pegado al valor maximo y la etiqueta de razon (ProductivityRatioLabels)
  // queda encima del propio numero de la barra (o se corta contra el borde del
  // chart).
  const productivityMaxValue = Math.max(
    0,
    ...productivityDataset.flatMap(d => [
      d.complexityCheckedCount,
      d.complexityWeightedScore
    ])
  )
  const productivityYAxisMax =
    productivityMaxValue > 0
      ? Math.ceil(productivityMaxValue * 1.35)
      : undefined
  const qualitySeriesDefs: Array<{
    metric: QualityMetricKey
    dataKey: string
    stack?: string
    label: string
    color: string
    valueFormatter: (value: number | null) => string
    barLabel: (item: { value: number | null }) => string
  }> = [
    {
      metric: 'greeting',
      dataKey: 'greetingOkPct',
      label: 'Saludo (casual o formal)',
      color: GREETING_CHART_COLOR,
      valueFormatter: pct,
      barLabel: item => pct(item.value)
    },
    {
      metric: 'farewell',
      dataKey: 'farewellOkPct',
      label: 'Despedida',
      color: FAREWELL_CHART_COLOR,
      valueFormatter: pct,
      barLabel: item => pct(item.value)
    },
    {
      metric: 'spelling',
      dataKey: 'spellingOkPct',
      label: 'Ortografía correcta',
      color: 'var(--color-chart-3)',
      valueFormatter: pct,
      barLabel: item => pct(item.value)
    },
    {
      metric: 'handledWell',
      dataKey: 'handledWellPct',
      label: 'Manejo adecuado a la complejidad',
      color: 'var(--color-chart-5)',
      valueFormatter: pct,
      barLabel: item => pct(item.value)
    },
    {
      metric: 'complexity',
      dataKey: 'complexityLowPct',
      stack: 'complexity',
      label: 'Complejidad baja',
      color: 'var(--color-muted-foreground)',
      valueFormatter: pct,
      barLabel: item => pct(item.value)
    },
    {
      metric: 'complexity',
      dataKey: 'complexityMediumPct',
      stack: 'complexity',
      label: 'Complejidad media',
      color: 'var(--color-chart-4)',
      valueFormatter: pct,
      barLabel: item => pct(item.value)
    },
    {
      metric: 'complexity',
      dataKey: 'complexityHighPct',
      stack: 'complexity',
      label: 'Complejidad alta',
      color: 'var(--color-destructive)',
      valueFormatter: pct,
      barLabel: item => pct(item.value)
    }
  ]
  const qualitySeries = qualitySeriesDefs.filter(series =>
    isMetricVisible(series.metric)
  )
  return (
    <div className="flex flex-col gap-8">
      <div>
        <p className="mb-1 text-sm font-medium text-muted-foreground">
          Tiempo promedio de primera respuesta
        </p>
        <div
          role="img"
          aria-label={responseAriaLabel}
          className="w-full overflow-x-auto"
        >
          <ChartThemeProvider>
            <BarChart
              dataset={responseDataset}
              width={responseWidth}
              height={CHART_HEIGHT_PX}
              xAxis={[agentAxis()]}
              yAxis={[hiddenValueAxis]}
              series={[
                {
                  dataKey: 'avgFirstResponseSeconds',
                  label: 'Primera respuesta',
                  color: 'var(--color-chart-2)',
                  valueFormatter: value => formatSecondsAsDuration(value ?? 0),
                  barLabel: item => formatSecondsAsDuration(item.value ?? 0)
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
        <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium text-muted-foreground">
            Saludo, despedida, ortografía, manejo adecuado y complejidad
          </p>
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              Mostrar
            </span>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-40 justify-between font-normal"
                  />
                }
              >
                <span className="min-w-0 truncate">{metricsFilterLabel}</span>
                <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-64">
                <QualityMetricsQuickActions
                  onSelectAll={selectAllMetrics}
                  onSelectNone={selectNoMetrics}
                />
                {QUALITY_METRIC_OPTIONS.map(option => (
                  <Label
                    key={option.key}
                    className="cursor-default items-start rounded-xl px-3 py-2 font-normal hover:bg-accent"
                  >
                    <Checkbox
                      checked={isMetricVisible(option.key)}
                      onCheckedChange={() => toggleMetric(option.key)}
                      className="mt-0.5"
                    />
                    {option.label}
                  </Label>
                ))}
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        {qualitySeries.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Elegí al menos una barra en "Mostrar" para ver el gráfico.
          </p>
        ) : (
          <div
            role="img"
            aria-label={qualityAriaLabel}
            className="w-full overflow-x-auto"
          >
            <ChartThemeProvider>
              <BarChart
                dataset={qualityDataset}
                width={qualityWidth}
                height={QUALITY_CHART_HEIGHT_PX}
                xAxis={[agentAxis()]}
                yAxis={[{ ...hiddenValueAxis, min: 0, max: 100 }]}
                series={qualitySeries}
                borderRadius={3}
                slotProps={{
                  legend: {
                    direction: 'horizontal',
                    position: { vertical: 'bottom', horizontal: 'center' }
                  }
                }}
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
        )}
      </div>
      <div>
        <div className="mb-1 flex flex-wrap items-center justify-between gap-2">
          <p className="text-sm font-medium text-muted-foreground">
            Productividad: casos evaluados vs. score ponderado por complejidad
            (baja=1, media=2, alta=3)
          </p>
          <div className="flex items-center gap-2">
            <span className="text-xs font-medium text-muted-foreground">
              Ordenar por
            </span>
            <DropdownMenu>
              <DropdownMenuTrigger
                render={
                  <Button
                    variant="outline"
                    size="sm"
                    className="w-48 justify-between font-normal"
                  />
                }
              >
                <span className="min-w-0 truncate">
                  {productivitySortLabel}
                </span>
                <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground" />
              </DropdownMenuTrigger>
              <DropdownMenuContent align="end" className="min-w-56">
                <DropdownMenuRadioGroup
                  value={productivitySortKey}
                  onValueChange={value =>
                    setProductivitySortKey(value as ProductivitySortKey)
                  }
                >
                  {PRODUCTIVITY_SORT_OPTIONS.map(option => (
                    <DropdownMenuRadioItem key={option.key} value={option.key}>
                      {option.label}
                    </DropdownMenuRadioItem>
                  ))}
                </DropdownMenuRadioGroup>
              </DropdownMenuContent>
            </DropdownMenu>
          </div>
        </div>
        <div
          role="img"
          aria-label={productivityAriaLabel}
          className="w-full overflow-x-auto"
        >
          <ChartThemeProvider>
            <BarChart
              dataset={productivityDataset}
              width={productivityWidth}
              height={CHART_HEIGHT_PX}
              xAxis={[agentAxis()]}
              yAxis={[{ ...hiddenValueAxis, max: productivityYAxisMax }]}
              series={[
                {
                  dataKey: 'complexityCheckedCount',
                  label: 'Casos evaluados (bruto)',
                  color: PRODUCTIVITY_RAW_CHART_COLOR,
                  valueFormatter: value => String(value ?? 0),
                  barLabel: item => String(item.value ?? 0)
                },
                {
                  dataKey: 'complexityWeightedScore',
                  label: 'Score ponderado por complejidad',
                  color: PRODUCTIVITY_WEIGHTED_CHART_COLOR,
                  valueFormatter: value => String(value ?? 0),
                  barLabel: item => String(item.value ?? 0)
                }
              ]}
              borderRadius={4}
              slotProps={{
                legend: {
                  direction: 'horizontal',
                  position: { vertical: 'bottom', horizontal: 'center' }
                }
              }}
              sx={{
                '& .MuiBarChart-label': {
                  fill: '#0a0a0a !important',
                  fontWeight: 700,
                  fontSize: CHART_VALUE_LABEL_FONT_SIZE
                }
              }}
            >
              <ProductivityRatioLabels data={productivityDataset} />
            </BarChart>
          </ChartThemeProvider>
        </div>
      </div>
      {transferNotifications.length > 0 && (
        <div>
          <p className="mb-1 text-sm font-medium text-muted-foreground">
            Aviso de transferencia (agente que transfiere)
          </p>
          <div
            role="img"
            aria-label={transferAriaLabel}
            className="w-full overflow-x-auto"
          >
            <ChartThemeProvider>
              <BarChart
                dataset={transferDataset}
                width={transferWidth}
                height={CHART_HEIGHT_PX}
                xAxis={[agentAxis()]}
                yAxis={[{ ...hiddenValueAxis, min: 0, max: 100 }]}
                series={[
                  {
                    dataKey: 'informedPct',
                    label: 'Avisó antes de transferir',
                    color: TRANSFER_CHART_COLOR,
                    valueFormatter: pct,
                    barLabel: item => pct(item.value)
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
