import { ClockIcon, UserIcon } from 'lucide-react'
import { useState } from 'react'
import {
  CHART_AXIS_LABEL_FONT_SIZE,
  CHART_BIG_NUMBER_FONT_SIZE
} from '#/lib/chart-typography'
import { formatSecondsAsDuration } from '#/lib/duration'
import {
  DIMENSION_CHAIN,
  groupIncidentsBy,
  INCIDENT_CATEGORY_COLOR,
  type IncidentGroup
} from '#/lib/incident-analytics'
import { cn, tintChartBackground } from '#/lib/utils'
import type { IncidentCategory, IncidentRecord } from '#/server/schemas'

const MAX_BAR_PX = 220
const MIN_BAR_PX = 4

function TicketList({ items }: { items: IncidentRecord[] }) {
  return (
    <div className="flex max-h-80 flex-col gap-1 overflow-y-auto rounded-xl bg-foreground/3 p-2">
      {items.map((item, i) => (
        <div key={i} className="rounded-lg px-2 py-1.5 hover:bg-foreground/4">
          <p className="text-foreground text-sm">
            {item.descripcion || (
              <span className="text-muted-foreground">Sin descripción</span>
            )}
          </p>
          <div className="mt-0.5 flex items-center gap-3 text-muted-foreground text-xs">
            <span className="inline-flex items-center gap-1">
              <ClockIcon className="size-3" />
              {item.tiempoSegundos === null
                ? '—'
                : formatSecondsAsDuration(item.tiempoSegundos)}
            </span>
            <span className="inline-flex items-center gap-1">
              <UserIcon className="size-3" />
              {item.agente || 'Sin agente'}
            </span>
          </div>
        </div>
      ))}
    </div>
  )
}

function HierarchyRow({
  entry,
  color,
  maxCount,
  chain,
  depth
}: {
  entry: IncidentGroup
  color: string
  maxCount: number
  chain: IncidentCategory[]
  depth: number
}) {
  const [expanded, setExpanded] = useState(false)
  const isLeaf = depth === chain.length - 1
  const barWidth = Math.max(MIN_BAR_PX, (entry.count / maxCount) * MAX_BAR_PX)
  const rowContent = (
    <>
      <span
        className="truncate text-foreground"
        style={{ fontSize: CHART_AXIS_LABEL_FONT_SIZE }}
        title={entry.label}
      >
        {entry.label}
      </span>
      <span
        className="h-4.25 shrink-0 rounded-[5px]"
        style={{ width: barWidth, background: color }}
      />
      <span
        className="w-6 shrink-0 text-left font-medium text-muted-foreground"
        style={{ fontSize: CHART_AXIS_LABEL_FONT_SIZE }}
      >
        {entry.count}
      </span>
    </>
  )
  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(value => !value)}
        className={cn(
          'flex w-full cursor-pointer items-center justify-end gap-2.5 rounded-md px-1 py-1.5 text-left transition-colors hover:bg-foreground/4',
          expanded && 'bg-foreground/5'
        )}
      >
        {rowContent}
      </button>
      {expanded && (
        <div className="mt-1.5 mb-2 ml-5">
          {isLeaf ? (
            <TicketList items={entry.items} />
          ) : (
            <HierarchyLevel
              records={entry.items}
              chain={chain}
              depth={depth + 1}
            />
          )}
        </div>
      )}
    </div>
  )
}
function HierarchyLevel({
  records,
  chain,
  depth
}: {
  records: IncidentRecord[]
  chain: IncidentCategory[]
  depth: number
}) {
  const key = chain[depth]
  const groups = groupIncidentsBy(records, key)
  const maxCount = groups[0]?.count ?? 1
  const color = INCIDENT_CATEGORY_COLOR[key]
  return (
    <div
      className="flex items-center gap-4 rounded-2xl px-5 py-4"
      style={{ background: tintChartBackground(color) }}
    >
      <div className="min-w-0 flex-1 space-y-1">
        {groups.map(entry => (
          <HierarchyRow
            key={entry.label}
            entry={entry}
            color={color}
            maxCount={maxCount}
            chain={chain}
            depth={depth}
          />
        ))}
      </div>
      <div
        className="w-9 shrink-0 text-center font-bold text-foreground"
        style={{ fontSize: CHART_BIG_NUMBER_FONT_SIZE }}
      >
        {records.length}
      </div>
    </div>
  )
}
export function IncidentHierarchy({
  records,
  dimension
}: {
  records: IncidentRecord[]
  dimension: IncidentCategory
}) {
  return (
    <HierarchyLevel
      records={records}
      chain={DIMENSION_CHAIN[dimension]}
      depth={0}
    />
  )
}
