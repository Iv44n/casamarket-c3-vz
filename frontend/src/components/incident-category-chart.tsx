import { BarChart } from '@mui/x-charts/BarChart'
import { ChartThemeProvider } from '#/components/mui-chart-theme'
import type { IncidentCategoryCount } from '#/server/schemas'

const MAX_LABEL_CHARS = 24
const CATEGORY_AXIS_WIDTH_PX = 180
const ROW_HEIGHT_PX = 34
const MIN_CHART_HEIGHT_PX = 220
function truncateLabel(value: string) {
  return value.length > MAX_LABEL_CHARS
    ? `${value.slice(0, MAX_LABEL_CHARS - 1)}…`
    : value
}
export function IncidentCategoryChart({
  data,
  color,
  height
}: {
  data: IncidentCategoryCount[]
  color: string
  // Omit to auto-size from row count -- used by the per-category selector
  // view so a long, uncapped list (real Ambito data has 29 distinct values)
  // still gets a row each instead of being squeezed into a fixed height.
  height?: number
}) {
  const chartHeight =
    height ?? Math.max(data.length * ROW_HEIGHT_PX + 50, MIN_CHART_HEIGHT_PX)
  const ariaLabel = `Distribucion: ${data
    .map(({ value, count }) => `${value} ${count}`)
    .join(', ')}`
  return (
    <div role="img" aria-label={ariaLabel}>
      <ChartThemeProvider>
        <BarChart
          dataset={data}
          layout="horizontal"
          height={chartHeight}
          yAxis={[
            {
              scaleType: 'band',
              dataKey: 'value',
              valueFormatter: value => truncateLabel(String(value)),
              tickLabelStyle: { fontSize: 12 },
              width: CATEGORY_AXIS_WIDTH_PX
            }
          ]}
          xAxis={[
            {
              disableLine: true,
              disableTicks: true,
              tickLabelInterval: () => false
            }
          ]}
          series={[
            {
              dataKey: 'count',
              color,
              barLabel: 'value',
              valueFormatter: value => `${value ?? 0}`
            }
          ]}
          borderRadius={4}
          margin={{ top: 8, bottom: 8 }}
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
