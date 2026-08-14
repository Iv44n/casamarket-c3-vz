import type { BarItem } from '@mui/x-charts/BarChart'
import { BarChart } from '@mui/x-charts/BarChart'
import { ChartThemeProvider } from '#/components/mui-chart-theme'
import { type CampaignBarDatum, estadoColor } from '#/lib/attentions-analytics'
import {
  CHART_AXIS_LABEL_FONT_SIZE,
  CHART_LEGEND_FONT_SIZE,
  CHART_MIN_HEIGHT_PX,
  CHART_ROW_HEIGHT_PX,
  CHART_VALUE_LABEL_FONT_SIZE
} from '#/lib/chart-typography'

const MAX_CAMPAIGN_LABEL_CHARS = 26
const CAMPAIGN_AXIS_WIDTH_PX = 170
const STACK_ID = 'atenciones-por-tipo'
function truncateCampaignLabel(name: string) {
  return name.length > MAX_CAMPAIGN_LABEL_CHARS
    ? `${name.slice(0, MAX_CAMPAIGN_LABEL_CHARS - 1)}…`
    : name
}
export function CampaignWorkloadChart({
  campaigns
}: {
  campaigns: CampaignBarDatum[]
}) {
  const ariaLabel = `Atenciones por tipo de caso: ${campaigns
    .map(({ campana, total, estadoCounts }) => {
      const breakdown = Object.entries(estadoCounts)
        .map(([estado, count]) => `${estado} ${count}`)
        .join(', ')
      return `${campana} ${total} (${breakdown})`
    })
    .join('; ')}`
  const estadoTotals = new Map<string, number>()
  for (const { estadoCounts } of campaigns) {
    for (const [estado, count] of Object.entries(estadoCounts)) {
      estadoTotals.set(estado, (estadoTotals.get(estado) ?? 0) + count)
    }
  }
  const estados = [...estadoTotals.keys()].sort(
    (a, b) => (estadoTotals.get(b) ?? 0) - (estadoTotals.get(a) ?? 0)
  )
  const dataset = campaigns.map(({ campana, estadoCounts }) => {
    const row: Record<string, number | string> = { campana }
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
    campaigns.length * CHART_ROW_HEIGHT_PX + 40,
    CHART_MIN_HEIGHT_PX
  )
  return (
    <div role="img" aria-label={ariaLabel} className="w-full">
      <ChartThemeProvider>
        <BarChart
          dataset={dataset}
          layout="horizontal"
          height={height}
          yAxis={[
            {
              scaleType: 'band',
              dataKey: 'campana',
              valueFormatter: value => truncateCampaignLabel(String(value)),
              tickLabelStyle: { fontSize: CHART_AXIS_LABEL_FONT_SIZE },
              width: CAMPAIGN_AXIS_WIDTH_PX
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
              fontSize: CHART_VALUE_LABEL_FONT_SIZE
            },
            '& .MuiChartsLegend-label': {
              fontSize: CHART_LEGEND_FONT_SIZE
            }
          }}
        />
      </ChartThemeProvider>
    </div>
  )
}
