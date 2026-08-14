import { useDrawingArea } from '@mui/x-charts/hooks'
import { PieChart } from '@mui/x-charts/PieChart'
import { useMemo, useState } from 'react'
import { ChartThemeProvider } from '#/components/mui-chart-theme'
import { estadoColor, type StatusChartSlice } from '#/lib/attentions-analytics'
import { tintChartColor } from '#/lib/utils'

const DIRECTION_LABEL: Record<'incoming' | 'outgoing', string> = {
  incoming: 'Entrantes',
  outgoing: 'Salientes'
}
const MIN_LABEL_PCT = 8
const MIN_LABEL_ANGLE_DEG = 360 * (MIN_LABEL_PCT / 100)
function PieCenterLabel({ text }: { text: string }) {
  const { left, top, width, height } = useDrawingArea()
  if (!text) {
    return null
  }
  return (
    <text
      x={left + width / 2}
      y={top + height / 2}
      textAnchor="middle"
      dominantBaseline="central"
      fontSize={22}
      fontWeight={700}
      fill="var(--color-foreground)"
    >
      {text}
    </text>
  )
}
export function StatusDonutChart({
  total,
  slices
}: {
  total: number
  slices: StatusChartSlice[]
}) {
  const [highlightedIndex, setHighlightedIndex] = useState<number | null>(null)
  const data = useMemo(
    () =>
      slices.map(slice => {
        const baseColor = estadoColor(slice.estado)
        return {
          id: slice.id,
          value: slice.count,
          label: slice.direction
            ? `${slice.estado} · ${DIRECTION_LABEL[slice.direction]}`
            : slice.estado,
          color:
            slice.direction === 'outgoing'
              ? tintChartColor(baseColor)
              : baseColor
        }
      }),
    [slices]
  )
  const centerText =
    highlightedIndex !== null && data[highlightedIndex]
      ? String(data[highlightedIndex].value)
      : ''
  const ariaLabel = `Distribucion por estado de ${total} atenciones: ${data
    .map(({ label, value }) => `${label} ${value}`)
    .join(', ')}`
  return (
    <div role="img" aria-label={ariaLabel} className="h-full w-full">
      <ChartThemeProvider>
        <PieChart
          series={[
            {
              data,
              innerRadius: '60%',
              outerRadius: '86%',
              paddingAngle: 2,
              cornerRadius: 3,
              arcLabel: item => `${Math.round((item.value / total) * 100)}%`,
              arcLabelMinAngle: MIN_LABEL_ANGLE_DEG,
              arcLabelRadius: '80%',
              valueFormatter: item =>
                `${item.value} (${Math.round((item.value / total) * 100)}%)`
            }
          ]}
          onHighlightChange={item =>
            setHighlightedIndex(item?.dataIndex ?? null)
          }
          slotProps={{
            legend: {
              direction: 'horizontal',
              position: { vertical: 'bottom', horizontal: 'center' }
            },
            pieArc: { stroke: 'none' }
          }}
          sx={{
            '& .MuiPieChart-arcLabel': {
              fill: '#0a0a0a !important',
              fontWeight: 700,
              fontSize: 13
            }
          }}
        >
          <PieCenterLabel text={centerText} />
        </PieChart>
      </ChartThemeProvider>
    </div>
  )
}
