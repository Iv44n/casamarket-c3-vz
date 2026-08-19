import {
  Tooltip,
  TooltipContent,
  TooltipTrigger
} from '#/components/ui/tooltip'
import {
  DEMAND_HOURS,
  DEMAND_LEVEL_LABEL,
  DEMAND_LEVELS,
  type DemandHeatmap,
  type DemandHeatmapCell,
  type DemandLevel
} from '#/lib/attentions-analytics'
import { CHART_AXIS_LABEL_FONT_SIZE } from '#/lib/chart-typography'
import { sequentialChartMix } from '#/lib/utils'

const LEVEL_MIX_PERCENT: Record<DemandLevel, number> = {
  none: 6,
  bajo: 22,
  medio: 45,
  alto: 70,
  pico: 100
}
const CELL_SIZE_PX = 26

function levelBackground(level: DemandLevel): string {
  return sequentialChartMix('var(--color-primary)', LEVEL_MIX_PERCENT[level])
}

function cellTooltipText(dayLabel: string, cell: DemandHeatmapCell): string {
  const hourRange = `${cell.hour}h–${cell.hour + 1}h`
  if (cell.level === 'none') {
    return `${dayLabel} ${hourRange}: sin tickets`
  }
  return `${dayLabel} ${hourRange}: ${cell.count} tickets (${DEMAND_LEVEL_LABEL[cell.level]})`
}

export function DemandHeatmapChart({ heatmap }: { heatmap: DemandHeatmap }) {
  return (
    <div className="w-full">
      <div className="mb-3 flex flex-wrap items-center gap-4">
        {DEMAND_LEVELS.map(level => (
          <span
            key={level}
            className="flex items-center gap-1.5 text-muted-foreground text-xs"
          >
            <span
              className="size-2.5 shrink-0 rounded-sm"
              style={{ background: levelBackground(level) }}
            />
            {DEMAND_LEVEL_LABEL[level]}
          </span>
        ))}
      </div>

      <div className="w-full overflow-x-auto">
        <table
          aria-label="Volumen de tickets por dia de la semana y hora"
          className="border-separate"
          style={{ borderSpacing: 2 }}
        >
          <thead>
            <tr>
              <th />
              {DEMAND_HOURS.map(hour => (
                <th
                  key={hour}
                  scope="col"
                  className="pb-1 font-normal text-muted-foreground"
                  style={{
                    fontSize: CHART_AXIS_LABEL_FONT_SIZE,
                    width: CELL_SIZE_PX
                  }}
                >
                  {hour}h
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {heatmap.rows.map(row => (
              <tr key={row.dayOfWeek}>
                <th
                  scope="row"
                  className="pr-2 text-right font-normal text-muted-foreground"
                  style={{ fontSize: CHART_AXIS_LABEL_FONT_SIZE }}
                >
                  {row.label}
                </th>
                {row.cells.map(cell => (
                  <td key={cell.hour} className="p-0">
                    <Tooltip>
                      <TooltipTrigger
                        render={
                          <button
                            type="button"
                            aria-label={cellTooltipText(row.label, cell)}
                            className="block rounded-[3px] border border-border/50"
                            style={{
                              width: CELL_SIZE_PX,
                              height: CELL_SIZE_PX,
                              background: levelBackground(cell.level)
                            }}
                          />
                        }
                      />
                      <TooltipContent>
                        {cellTooltipText(row.label, cell)}
                      </TooltipContent>
                    </Tooltip>
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  )
}
