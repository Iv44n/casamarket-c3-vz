import { useState } from 'react'
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
      <span className="truncate text-sm text-foreground" title={entry.label}>
        {entry.label}
      </span>
      <span
        className="h-[17px] shrink-0 rounded-[5px]"
        style={{ width: barWidth, background: color }}
      />
      <span className="w-6 shrink-0 text-left text-xs font-medium text-muted-foreground">
        {entry.count}
      </span>
    </>
  )
  if (isLeaf) {
    return (
      <div className="flex items-center justify-end gap-2.5 px-1 py-1.5">
        {rowContent}
      </div>
    )
  }
  return (
    <div>
      <button
        type="button"
        onClick={() => setExpanded(value => !value)}
        className={cn(
          'flex w-full cursor-pointer items-center justify-end gap-2.5 rounded-md px-1 py-1.5 text-left transition-colors hover:bg-foreground/[0.04]',
          expanded && 'bg-foreground/[0.05]'
        )}
      >
        {rowContent}
      </button>
      {expanded && (
        <div className="mt-1.5 mb-2 ml-5">
          <HierarchyLevel
            records={entry.items}
            chain={chain}
            depth={depth + 1}
          />
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
      <div className="w-9 shrink-0 text-center text-2xl font-bold text-foreground">
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
