import {
  ChevronLeftIcon,
  ChevronRightIcon,
  TriangleAlertIcon
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Badge } from '#/components/ui/badge'
import { Button } from '#/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardFooter,
  CardHeader,
  CardTitle
} from '#/components/ui/card'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '#/components/ui/table'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger
} from '#/components/ui/tooltip'
import { estadoColor } from '#/lib/attentions-analytics'
import { formatSecondsAsDuration } from '#/lib/duration'
import { cn } from '#/lib/utils'
import type { AttentionRecord } from '#/server/schemas'

const PAGE_SIZE = 50
const DIRECTION_LABEL: Record<AttentionRecord['direction'], string> = {
  incoming: 'Entrante',
  outgoing: 'Saliente'
}
const STALE_THRESHOLD_SECONDS = 60 * 60
const TRANSFER_DEST_COLOR: Record<string, string> = {
  Agente: 'var(--color-chart-3)',
  Campaña: 'var(--color-chart-5)'
}

function Cell({ value }: { value: string }) {
  return value.trim() === '' ? (
    <span className="text-muted-foreground">—</span>
  ) : (
    value
  )
}

function TruncatedCell({
  value,
  className
}: {
  value: string
  className: string
}) {
  if (value.trim() === '') {
    return <span className="text-muted-foreground">—</span>
  }
  return (
    <Tooltip>
      <TooltipTrigger
        render={<span className={cn('block truncate', className)} />}
      >
        {value}
      </TooltipTrigger>
      <TooltipContent>{value}</TooltipContent>
    </Tooltip>
  )
}

function EstadoCell({ estado }: { estado: string }) {
  return (
    <span className="flex items-center gap-1.5">
      <span
        className="size-2 shrink-0 rounded-full"
        style={{ background: estadoColor(estado) }}
      />
      {estado}
    </span>
  )
}

function hopLabel(hop: AttentionRecord['transferChain'][number]): string {
  return hop.destType === 'Campaña'
    ? `a la campaña "${hop.destino}"`
    : `al agente "${hop.destino}"`
}

function TransferredByCell({
  record,
  className
}: {
  record: AttentionRecord
  className: string
}) {
  if (record.transferredBy === null || record.transferChain.length === 0) {
    return <span className="text-muted-foreground">—</span>
  }
  const color = record.transferDestType
    ? TRANSFER_DEST_COLOR[record.transferDestType]
    : undefined
  const chain = record.transferChain
  return (
    <Tooltip>
      <TooltipTrigger render={<span className="flex items-center gap-1.5" />}>
        {color && (
          <span
            className="size-2 shrink-0 rounded-full"
            style={{ background: color }}
          />
        )}
        <span className={cn('truncate', className)}>
          {record.transferredBy}
        </span>
        {chain.length > 1 && (
          <span className="shrink-0 text-[10px] text-muted-foreground">
            ×{chain.length}
          </span>
        )}
      </TooltipTrigger>
      <TooltipContent className="max-w-sm p-3 text-sm">
        <div className="flex flex-col gap-2.5">
          {chain.map((hop, i) => {
            const hopColor = TRANSFER_DEST_COLOR[hop.destType]
            return (
              <div key={i} className="flex items-start gap-2">
                <span className="shrink-0 text-muted-foreground tabular-nums">
                  {i + 1}.
                </span>
                {hopColor && (
                  <span
                    className="mt-1.5 size-1.5 shrink-0 rounded-full"
                    style={{ background: hopColor }}
                  />
                )}
                <span className="leading-snug">
                  {hop.agenteOrigen} transfirió {hopLabel(hop)}
                </span>
              </div>
            )
          })}
        </div>
      </TooltipContent>
    </Tooltip>
  )
}

function endEpochMs(record: AttentionRecord, now: number): number {
  return record.closeEpochMs ?? now
}

function elapsedSeconds(record: AttentionRecord, now: number): number | null {
  return record.startEpochMs === null
    ? null
    : Math.max(0, (endEpochMs(record, now) - record.startEpochMs) / 1000)
}

function withAgentSeconds(record: AttentionRecord, now: number): number | null {
  return record.withAgentSinceMs === null
    ? null
    : Math.max(0, (endEpochMs(record, now) - record.withAgentSinceMs) / 1000)
}

export function AttentionRecordsTable({
  records
}: {
  records: AttentionRecord[]
}) {
  const [page, setPage] = useState(0)
  // biome-ignore lint/correctness/useExhaustiveDependencies: resets pagination whenever the parent's records (e.g. its date/estado filter) change
  useEffect(() => {
    setPage(0)
  }, [records])

  if (records.length === 0) {
    return (
      <Card size="sm" className="mt-4">
        <CardContent className="text-sm text-muted-foreground">
          No hay atenciones para el filtro actual.
        </CardContent>
      </Card>
    )
  }

  const now = Date.now()
  const staleCount = records.filter(record => {
    if (record.closeEpochMs !== null) return false
    const seconds = withAgentSeconds(record, now)
    return seconds !== null && seconds > STALE_THRESHOLD_SECONDS
  }).length
  const sorted = [...records].sort((a, b) => {
    const secondsA = withAgentSeconds(a, now) ?? -1
    const secondsB = withAgentSeconds(b, now) ?? -1
    return secondsB - secondsA
  })
  const totalPages = Math.max(1, Math.ceil(sorted.length / PAGE_SIZE))
  const start = page * PAGE_SIZE
  const pageRecords = sorted.slice(start, start + PAGE_SIZE)

  return (
    <Card size="sm" className="mt-4">
      <CardHeader>
        <CardTitle>Atenciones</CardTitle>
        <CardDescription>
          {records.length} atenciones para el filtro actual, ordenadas por
          cuanto tiempo llevan (o llevaron, si ya se cerraron) con su agente
          actual (desde la ultima transferencia, si la hubo).
        </CardDescription>
        <div className="flex items-center gap-3 text-muted-foreground text-xs">
          <span className="flex items-center gap-1.5">
            <span
              className="size-2 rounded-full"
              style={{ background: TRANSFER_DEST_COLOR.Agente }}
            />
            Transferido a un agente
          </span>
          <span className="flex items-center gap-1.5">
            <span
              className="size-2 rounded-full"
              style={{ background: TRANSFER_DEST_COLOR.Campaña }}
            />
            Transferido a una campaña
          </span>
        </div>
        {staleCount > 0 && (
          <p className="mt-1 flex items-center gap-1.5 text-destructive text-sm">
            <TriangleAlertIcon className="size-4" />
            {staleCount} {staleCount === 1 ? 'lleva' : 'llevan'} mas de{' '}
            {formatSecondsAsDuration(STALE_THRESHOLD_SECONDS)} sin atencion de
            su agente actual.
          </p>
        )}
      </CardHeader>
      <CardContent className="overflow-x-auto p-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>ID</TableHead>
              <TableHead>Estado</TableHead>
              <TableHead className="max-w-48">Cliente</TableHead>
              <TableHead className="max-w-32">Plan</TableHead>
              <TableHead className="max-w-36">Agente</TableHead>
              <TableHead className="max-w-36">Transferido por</TableHead>
              <TableHead className="max-w-32">Campaña</TableHead>
              <TableHead>Dirección</TableHead>
              <TableHead>Tiempo abierta</TableHead>
              <TableHead>Tiempo con agente actual</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {pageRecords.map((record, i) => {
              const seconds = withAgentSeconds(record, now)
              const totalSeconds = elapsedSeconds(record, now)
              const isStale =
                record.closeEpochMs === null &&
                seconds !== null &&
                seconds > STALE_THRESHOLD_SECONDS
              return (
                <TableRow key={start + i}>
                  <TableCell className="align-top text-muted-foreground">
                    <Cell value={record.idAtencion} />
                  </TableCell>
                  <TableCell className="align-top">
                    <EstadoCell estado={record.estado} />
                  </TableCell>
                  <TableCell className="max-w-48 align-top">
                    <TruncatedCell
                      value={record.cliente}
                      className="max-w-48"
                    />
                  </TableCell>
                  <TableCell className="max-w-32 align-top">
                    <TruncatedCell value={record.plan} className="max-w-32" />
                  </TableCell>
                  <TableCell className="max-w-36 align-top">
                    <TruncatedCell value={record.agente} className="max-w-36" />
                  </TableCell>
                  <TableCell className="max-w-36 align-top">
                    <TransferredByCell record={record} className="max-w-32" />
                  </TableCell>
                  <TableCell className="max-w-32 align-top">
                    <TruncatedCell
                      value={record.campana}
                      className="max-w-32"
                    />
                  </TableCell>
                  <TableCell className="align-top">
                    <Badge variant="outline">
                      {DIRECTION_LABEL[record.direction]}
                    </Badge>
                  </TableCell>
                  <TableCell className="align-top font-medium">
                    {totalSeconds === null ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      formatSecondsAsDuration(totalSeconds)
                    )}
                  </TableCell>
                  <TableCell className="align-top font-medium">
                    {seconds === null ? (
                      <span className="text-muted-foreground">—</span>
                    ) : isStale ? (
                      <span className="inline-flex items-center gap-1 text-destructive">
                        <TriangleAlertIcon className="size-3.5" />
                        {formatSecondsAsDuration(seconds)}
                      </span>
                    ) : (
                      formatSecondsAsDuration(seconds)
                    )}
                  </TableCell>
                </TableRow>
              )
            })}
          </TableBody>
        </Table>
      </CardContent>
      <CardFooter className="justify-center gap-2">
        <Button
          variant="outline"
          size="icon-sm"
          onClick={() => setPage(p => Math.max(0, p - 1))}
          disabled={page <= 0}
          aria-label="Pagina anterior"
        >
          <ChevronLeftIcon />
        </Button>
        <span className="text-sm text-muted-foreground">
          Página {page + 1} de {totalPages}
        </span>
        <Button
          variant="outline"
          size="icon-sm"
          onClick={() => setPage(p => Math.min(totalPages - 1, p + 1))}
          disabled={page >= totalPages - 1}
          aria-label="Pagina siguiente"
        >
          <ChevronRightIcon />
        </Button>
      </CardFooter>
    </Card>
  )
}
