import { BarPlot } from '@mui/x-charts/BarChart'
import { ChartsAxisHighlight } from '@mui/x-charts/ChartsAxisHighlight'
import { ChartsDataProvider } from '@mui/x-charts/ChartsDataProvider'
import { ChartsGrid } from '@mui/x-charts/ChartsGrid'
import { ChartsLegend } from '@mui/x-charts/ChartsLegend'
import { ChartsSurface } from '@mui/x-charts/ChartsSurface'
import { ChartsTooltip } from '@mui/x-charts/ChartsTooltip'
import { ChartsWrapper } from '@mui/x-charts/ChartsWrapper'
import { ChartsXAxis } from '@mui/x-charts/ChartsXAxis'
import { ChartsYAxis } from '@mui/x-charts/ChartsYAxis'
import { LinePlot, MarkPlot } from '@mui/x-charts/LineChart'
import { ChartThemeProvider } from '#/components/mui-chart-theme'
import type { DailyTrendPoint } from '#/lib/attentions-analytics'
import { CHART_AXIS_LABEL_FONT_SIZE } from '#/lib/chart-typography'

const CHART_HEIGHT_PX = 280
// Objetivo ~10 etiquetas visibles en el eje X sin importar cuantos dias tenga
// el rango elegido -- evita que un rango de 90 dias sature el eje.
const TARGET_X_TICKS = 10

export function DailyTrendChart({ points }: { points: DailyTrendPoint[] }) {
  const skip = Math.max(1, Math.ceil(points.length / TARGET_X_TICKS))
  let peakIndex = 0
  points.forEach((p, i) => {
    if (p.count > points[peakIndex].count) peakIndex = i
  })

  return (
    <ChartThemeProvider>
      <ChartsDataProvider
        series={[
          {
            type: 'bar',
            id: 'casos',
            data: points.map(p => p.count),
            label: 'Casos por día',
            color: 'var(--color-chart-3)',
            xAxisId: 'x'
          },
          {
            type: 'line',
            id: 'tendencia',
            data: points.map(p => Math.round(p.movingAverage * 10) / 10),
            label: 'Tendencia (promedio móvil)',
            color: 'var(--color-primary)',
            xAxisId: 'x',
            showMark: ({ index }) => index === peakIndex
          }
        ]}
        xAxis={[
          {
            id: 'x',
            scaleType: 'band',
            data: points.map(p => p.label),
            tickLabelStyle: { fontSize: CHART_AXIS_LABEL_FONT_SIZE },
            tickLabelInterval: (_value, index) =>
              index % skip === 0 || index === points.length - 1
          }
        ]}
        yAxis={[{ tickLabelStyle: { fontSize: CHART_AXIS_LABEL_FONT_SIZE } }]}
        height={CHART_HEIGHT_PX}
      >
        <ChartsWrapper>
          <ChartsLegend />
          <ChartsSurface>
            <ChartsGrid horizontal />
            <BarPlot borderRadius={4} />
            <LinePlot />
            <MarkPlot />
            <ChartsAxisHighlight x="band" />
            <ChartsXAxis axisId="x" />
            <ChartsYAxis />
          </ChartsSurface>
          <ChartsTooltip trigger="axis" />
        </ChartsWrapper>
      </ChartsDataProvider>
    </ChartThemeProvider>
  )
}
