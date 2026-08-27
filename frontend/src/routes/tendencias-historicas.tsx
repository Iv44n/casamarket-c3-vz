import { createFileRoute } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import { ChevronDownIcon, RefreshCwIcon, TriangleAlertIcon } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { DailyTrendChart } from '#/components/daily-trend-chart'
import { DateRangeFilter } from '#/components/date-range-filter'
import { DemandHeatmapChart } from '#/components/demand-heatmap-chart'
import { Button } from '#/components/ui/button'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '#/components/ui/card'
import { Checkbox } from '#/components/ui/checkbox'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger
} from '#/components/ui/dropdown-menu'
import { Label } from '#/components/ui/label'
import { Separator } from '#/components/ui/separator'
import { Skeleton } from '#/components/ui/skeleton'
import { buildDailyTrend, buildDemandHeatmap } from '#/lib/attentions-analytics'
import { cn } from '#/lib/utils'
import {
  getDailyCaseTrend,
  getDemandAnalytics
} from '#/server/reports.functions'
import {
  type AgentesFilter,
  type TendenciasHistoricasSearch,
  tendenciasHistoricasSearchSchema
} from '#/server/schemas'

function agentesLabel(filter: AgentesFilter, available: string[]): string {
  if (filter === 'all' || filter.length === available.length) return 'Todos'
  if (filter.length === 0) return 'Ninguno'
  if (filter.length === 1) return filter[0]
  return `${filter.length} agentes`
}

function MultiSelectQuickActions({
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
          Marcar todos
        </button>
        <button
          type="button"
          className="text-xs font-medium text-primary hover:underline"
          onClick={onSelectNone}
        >
          Ninguno
        </button>
      </div>
      <Separator className="mb-1" />
    </>
  )
}

export const Route = createFileRoute('/tendencias-historicas')({
  ssr: 'data-only',
  validateSearch: tendenciasHistoricasSearchSchema,
  loader: async ({ location }) => {
    const { date, dateEnd, agentes } =
      location.search as TendenciasHistoricasSearch
    const [demand, dailyTrend] = await Promise.all([
      getDemandAnalytics({ data: { date, dateEnd, agentes } }),
      getDailyCaseTrend({ data: { date, dateEnd, agentes } })
    ])
    return { demand, dailyTrend }
  },
  component: TendenciasHistoricasPage
})

function DailyTrendSkeleton() {
  const heights = [38, 62, 44, 80, 55, 70, 48, 63, 35, 58, 90, 50, 66, 40]
  return (
    <div className="flex h-[280px] items-end gap-2 px-1">
      {heights.map((h, i) => (
        // biome-ignore lint/suspicious/noArrayIndexKey: fixed-length static placeholder list
        <Skeleton key={i} className="flex-1" style={{ height: `${h}%` }} />
      ))}
    </div>
  )
}

function DailyTrendError({
  message,
  onRetry
}: {
  message: string
  onRetry: () => void
}) {
  return (
    <div className="flex h-[280px] flex-col items-center justify-center gap-2 text-center">
      <TriangleAlertIcon className="size-8 text-destructive" />
      <p className="text-sm font-medium">No se pudo cargar la tendencia.</p>
      <p className="rounded-md bg-muted px-2.5 py-1 font-mono text-xs text-muted-foreground">
        {message}
      </p>
      <Button variant="outline" size="sm" onClick={onRetry} className="mt-1">
        <RefreshCwIcon data-icon="inline-start" />
        Reintentar
      </Button>
    </div>
  )
}

function TendenciasHistoricasPage() {
  const initialData = Route.useLoaderData()
  const { date, dateEnd, agentes } = Route.useSearch()
  const navigate = Route.useNavigate()
  const fetchDailyTrend = useServerFn(getDailyCaseTrend)
  const fetchDemandAnalytics = useServerFn(getDemandAnalytics)

  const [dailyTrendAnalytics, setDailyTrendAnalytics] = useState(
    initialData.dailyTrend
  )
  const [trendLoading, setTrendLoading] = useState(false)
  const [trendError, setTrendError] = useState<string | null>(null)
  const isFirstTrendRun = useRef(true)
  const trendRequestIdRef = useRef(0)

  const [demandAnalytics, setDemandAnalytics] = useState(initialData.demand)
  const [demandLoading, setDemandLoading] = useState(false)
  const isFirstDemandRun = useRef(true)
  const demandRequestIdRef = useRef(0)

  // Sin loaderDeps a proposito: si el loader reaccionara al search, TanStack Router
  // muestra su spinner de pagina completa en cada cambio de rango, tapando el estado
  // de carga propio de esta card (y el de la card de abajo). Cada card resuelve su
  // propio refetch/loading/error, igual que ya hace /atenciones.
  const refetchTrend = useCallback(
    async (
      targetDate: typeof date,
      targetDateEnd: typeof dateEnd,
      targetAgentes: typeof agentes
    ) => {
      const requestId = ++trendRequestIdRef.current
      setTrendLoading(true)
      setTrendError(null)
      try {
        const result = await fetchDailyTrend({
          data: {
            date: targetDate,
            dateEnd: targetDateEnd,
            agentes: targetAgentes
          }
        })
        if (requestId !== trendRequestIdRef.current) return
        setDailyTrendAnalytics(result)
      } catch (err) {
        if (requestId !== trendRequestIdRef.current) return
        setTrendError(err instanceof Error ? err.message : String(err))
      } finally {
        if (requestId === trendRequestIdRef.current) setTrendLoading(false)
      }
    },
    [fetchDailyTrend]
  )
  useEffect(() => {
    if (isFirstTrendRun.current) {
      isFirstTrendRun.current = false
      return
    }
    refetchTrend(date, dateEnd, agentes)
  }, [date, dateEnd, agentes, refetchTrend])

  const refetchDemand = useCallback(
    async (
      targetDate: typeof date,
      targetDateEnd: typeof dateEnd,
      targetAgentes: typeof agentes
    ) => {
      const requestId = ++demandRequestIdRef.current
      setDemandLoading(true)
      try {
        const result = await fetchDemandAnalytics({
          data: {
            date: targetDate,
            dateEnd: targetDateEnd,
            agentes: targetAgentes
          }
        })
        if (requestId !== demandRequestIdRef.current) return
        setDemandAnalytics(result)
      } catch (err) {
        if (requestId === demandRequestIdRef.current) {
          toast.error(err instanceof Error ? err.message : String(err))
        }
      } finally {
        if (requestId === demandRequestIdRef.current) setDemandLoading(false)
      }
    },
    [fetchDemandAnalytics]
  )
  useEffect(() => {
    if (isFirstDemandRun.current) {
      isFirstDemandRun.current = false
      return
    }
    refetchDemand(date, dateEnd, agentes)
  }, [date, dateEnd, agentes, refetchDemand])

  const dailyTrend = useMemo(
    () => buildDailyTrend(dailyTrendAnalytics),
    [dailyTrendAnalytics]
  )
  const demandHeatmap = useMemo(
    () => buildDemandHeatmap(demandAnalytics),
    [demandAnalytics]
  )
  const availableAgentes = demandAnalytics.availableAgentes

  function isAgenteChecked(agenteName: string) {
    return agentes === 'all' || agentes.includes(agenteName)
  }
  function toggleAgente(agenteName: string) {
    const current = agentes === 'all' ? availableAgentes : agentes
    const next = current.includes(agenteName)
      ? current.filter(a => a !== agenteName)
      : [...current, agenteName]
    navigate({ search: prev => ({ ...prev, agentes: next }) })
  }
  function selectAllAgentes() {
    navigate({ search: prev => ({ ...prev, agentes: 'all' }) })
  }
  function selectNoAgentes() {
    navigate({ search: prev => ({ ...prev, agentes: [] }) })
  }

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Tendencias históricas</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Volumen de tickets por día de la semana y hora, a partir de las
            atenciones de WhatsApp -- identifica picos de capacidad.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {availableAgentes.length > 0 && (
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-muted-foreground">
                Agentes
              </span>
              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      variant="outline"
                      className="w-40 justify-between font-normal"
                    />
                  }
                >
                  <span className="min-w-0 truncate">
                    {agentesLabel(agentes, availableAgentes)}
                  </span>
                  <ChevronDownIcon className="size-4 shrink-0 text-muted-foreground" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end" className="min-w-64">
                  <MultiSelectQuickActions
                    onSelectAll={selectAllAgentes}
                    onSelectNone={selectNoAgentes}
                  />
                  {availableAgentes.map(agenteName => (
                    <Label
                      key={agenteName}
                      className="cursor-default items-start rounded-xl px-3 py-2 font-normal hover:bg-accent"
                    >
                      <Checkbox
                        checked={isAgenteChecked(agenteName)}
                        onCheckedChange={() => toggleAgente(agenteName)}
                        className="mt-0.5"
                      />
                      {agenteName}
                    </Label>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          )}
          <DateRangeFilter
            date={date}
            dateEnd={dateEnd}
            onChange={(newDate, newDateEnd) =>
              navigate({
                search: prev => ({
                  ...prev,
                  date: newDate,
                  dateEnd: newDateEnd ?? newDate
                })
              })
            }
          />
        </div>
      </div>

      <Card className="mt-6">
        <CardHeader>
          <CardTitle>Casos diarios</CardTitle>
          <CardDescription>
            Cantidad de casos registrados por día, con la tendencia de fondo.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {!trendLoading && !trendError && dailyTrend.points.length > 0 && (
            <div className="mb-5 flex flex-wrap items-center gap-4 text-sm">
              <div>
                <span className="text-xs text-muted-foreground">Total</span>
                <p className="font-semibold tabular-nums">{dailyTrend.total}</p>
              </div>
              <div className="h-6 w-px bg-border" />
              <div>
                <span className="text-xs text-muted-foreground">
                  Promedio/día
                </span>
                <p className="font-semibold tabular-nums">
                  {Math.round(dailyTrend.average)}
                </p>
              </div>
              {dailyTrend.peak && (
                <>
                  <div className="h-6 w-px bg-border" />
                  <div>
                    <span className="text-xs text-muted-foreground">Pico</span>
                    <p className="font-semibold tabular-nums">
                      {dailyTrend.peak.label} · {dailyTrend.peak.count}
                    </p>
                  </div>
                </>
              )}
            </div>
          )}

          {trendLoading ? (
            <DailyTrendSkeleton />
          ) : trendError ? (
            <DailyTrendError
              message={trendError}
              onRetry={() => refetchTrend(date, dateEnd, agentes)}
            />
          ) : dailyTrend.points.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              Sin registros en el rango elegido.
            </p>
          ) : (
            <DailyTrendChart points={dailyTrend.points} />
          )}
        </CardContent>
      </Card>

      <Card className="mt-4">
        <CardHeader>
          <CardTitle>Mapa de calor de demanda</CardTitle>
          <CardDescription>
            Elegí cualquier rango de fechas -- puede abarcar varias semanas.
          </CardDescription>
        </CardHeader>
        <CardContent
          className={cn(
            'flex items-center justify-center transition-opacity',
            demandLoading && 'opacity-50'
          )}
        >
          {demandHeatmap.total === 0 ? (
            <p className="text-sm text-muted-foreground">Sin registros.</p>
          ) : (
            <DemandHeatmapChart heatmap={demandHeatmap} />
          )}
        </CardContent>
      </Card>
    </div>
  )
}
