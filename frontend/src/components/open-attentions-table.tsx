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
import { formatSecondsAsDuration } from '#/lib/duration'
import { cn } from '#/lib/utils'
import type { OpenAttentionRecord } from '#/server/schemas'

const PAGE_SIZE = 15
const DIRECTION_LABEL: Record<OpenAttentionRecord['direction'], string> = {
  incoming: 'Entrante',
  outgoing: 'Saliente'
}
const STALE_THRESHOLD_SECONDS = 60 * 60

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

function withAgentSeconds(
  record: OpenAttentionRecord,
  now: number
): number | null {
  return record.withAgentSinceMs === null
    ? null
    : Math.max(0, (now - record.withAgentSinceMs) / 1000)
}

export function OpenAttentionsTable({
  records
}: {
  records: OpenAttentionRecord[]
}) {
  const [page, setPage] = useState(0)
  // biome-ignore lint/correctness/useExhaustiveDependencies: resets pagination whenever the parent's records (e.g. its date filter) change
  useEffect(() => {
    setPage(0)
  }, [records])

  if (records.length === 0) {
    return (
      <Card size="sm" className="mt-4">
        <CardContent className="text-sm text-muted-foreground">
          No hay atenciones abiertas para el filtro actual.
        </CardContent>
      </Card>
    )
  }

  const now = Date.now()
  const staleCount = records.filter(record => {
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
        <CardTitle>Atenciones abiertas</CardTitle>
        <CardDescription>
          {records.length} atenciones sin cerrar, ordenadas por cuanto tiempo
          lleva cada una con su agente actual (desde la ultima transferencia, si
          la hubo).
        </CardDescription>
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
              <TableHead className="max-w-48">Cliente</TableHead>
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
              const isStale =
                seconds !== null && seconds > STALE_THRESHOLD_SECONDS
              return (
                <TableRow key={start + i}>
                  <TableCell className="align-top text-muted-foreground">
                    <Cell value={record.idAtencion} />
                  </TableCell>
                  <TableCell className="max-w-48 align-top">
                    <TruncatedCell
                      value={record.cliente}
                      className="max-w-48"
                    />
                  </TableCell>
                  <TableCell className="max-w-36 align-top">
                    <TruncatedCell value={record.agente} className="max-w-36" />
                  </TableCell>
                  <TableCell className="max-w-36 align-top">
                    <TruncatedCell
                      value={record.transferredBy ?? ''}
                      className="max-w-36"
                    />
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
                    {record.startEpochMs === null ? (
                      <span className="text-muted-foreground">—</span>
                    ) : (
                      formatSecondsAsDuration(
                        Math.max(0, (now - record.startEpochMs) / 1000)
                      )
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
