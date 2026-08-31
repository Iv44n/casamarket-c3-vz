import { createFileRoute, useRouter } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import {
  CheckIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  PlayIcon,
  SettingsIcon,
  XIcon
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { BenchmarkAgentChart } from '#/components/benchmark-agent-chart'
import { useBenchmarkSchedule } from '#/components/benchmark-schedule-provider'
import { DateRangeFilter } from '#/components/date-range-filter'
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
import { Checkbox } from '#/components/ui/checkbox'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger
} from '#/components/ui/dialog'
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuTrigger
} from '#/components/ui/dropdown-menu'
import { Field, FieldLabel } from '#/components/ui/field'
import { Input } from '#/components/ui/input'
import { Label } from '#/components/ui/label'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '#/components/ui/select'
import { Separator } from '#/components/ui/separator'
import { Switch } from '#/components/ui/switch'
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow
} from '#/components/ui/table'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '#/components/ui/tabs'
import {
  Tooltip,
  TooltipContent,
  TooltipTrigger
} from '#/components/ui/tooltip'
import {
  benchmarkTotals,
  bestQualityAgent,
  buildAgentBenchmarkRanking
} from '#/lib/benchmark-analytics'
import { CHART_BIG_NUMBER_FONT_SIZE } from '#/lib/chart-typography'
import { formatSecondsAsDuration } from '#/lib/duration'
import { cn, withoutScrollReset } from '#/lib/utils'
import {
  getBenchmarkResults,
  getBenchmarkRunStatus,
  getBenchmarkRuns,
  getLlmSettings,
  triggerBenchmarkRun,
  updateLlmSettings
} from '#/server/reports.functions'
import type {
  BenchmarkComplexity,
  BenchmarkGreetingLevel,
  BenchmarkRunRecord,
  BenchmarkRunStatus,
  LlmSettings
} from '#/server/schemas'
import {
  AGENT_LIMIT_OPTIONS,
  type AgentLimit,
  BENCHMARK_DIRECTION_LABEL,
  type BenchmarkDirection,
  type BenchmarkDirectionFilter,
  type BenchmarksSearch,
  type BenchmarksView,
  benchmarksSearchSchema,
  todayIsoDate
} from '#/server/schemas'

export const Route = createFileRoute('/benchmarks')({
  ssr: 'data-only',
  validateSearch: benchmarksSearchSchema,
  // Sin loaderDeps a proposito: si el loader reaccionara al search, TanStack Router
  // muestra su spinner de pagina completa en cada cambio de filtro (incluidos
  // agentLimit/agentes, que ni siquiera pegan al servidor -- se resuelven client-side
  // mas abajo). El resultado de la tabla se refetchea a mano en el componente, igual
  // que ya hacen /atenciones y /tendencias-historicas.
  loader: async ({ location }) => {
    const search = location.search as BenchmarksSearch
    const direction = search.direction === 'all' ? undefined : search.direction
    const dateFrom = search.date
    const dateTo = search.dateEnd ?? search.date
    const [runStatus, results, llmSettings, runs] = await Promise.all([
      getBenchmarkRunStatus(),
      getBenchmarkResults({ data: { direction, dateFrom, dateTo } }),
      // null para no-admins (403) -- la card de configuracion simplemente no se
      // muestra, en vez de tirar abajo el resto de la pagina para ellos.
      getLlmSettings().catch(() => null),
      getBenchmarkRuns()
    ])
    return { runStatus, results, llmSettings, runs }
  },
  component: BenchmarksPage
})

const UNKNOWN_AGENT_LABEL = 'Sin agente'
function benchmarkAgentLabel(agente: string | null): string {
  return agente && agente.trim() !== '' ? agente : UNKNOWN_AGENT_LABEL
}

const BENCHMARK_DIRECTION_DOT: Record<BenchmarkDirection, string> = {
  attention: 'var(--color-primary)',
  outboundattention: 'var(--color-chart-3)'
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

function BenchmarksPage() {
  const {
    runStatus,
    results: initialResults,
    llmSettings,
    runs
  } = Route.useLoaderData()
  const search = Route.useSearch()
  const navigate = withoutScrollReset(Route.useNavigate())
  const fetchResults = useServerFn(getBenchmarkResults)

  const [results, setResults] = useState(initialResults)
  const [resultsLoading, setResultsLoading] = useState(false)
  const isFirstResultsRun = useRef(true)
  const resultsRequestIdRef = useRef(0)

  // El loader solo corre en el mount inicial y cuando algo llama a router.invalidate()
  // (p.ej. al terminar una corrida) -- este efecto sincroniza ese refresco "de fondo"
  // con el estado local de abajo, sin pasar por un refetch manual.
  useEffect(() => {
    setResults(initialResults)
  }, [initialResults])

  const refetchResults = useCallback(
    async (
      direction: BenchmarksSearch['direction'],
      date: string,
      dateEnd: string | undefined
    ) => {
      const requestId = ++resultsRequestIdRef.current
      setResultsLoading(true)
      try {
        const next = await fetchResults({
          data: {
            direction: direction === 'all' ? undefined : direction,
            dateFrom: date,
            dateTo: dateEnd ?? date
          }
        })
        if (requestId !== resultsRequestIdRef.current) return
        setResults(next)
      } catch (err) {
        if (requestId === resultsRequestIdRef.current) {
          toast.error(err instanceof Error ? err.message : String(err))
        }
      } finally {
        if (requestId === resultsRequestIdRef.current) setResultsLoading(false)
      }
    },
    [fetchResults]
  )
  useEffect(() => {
    if (isFirstResultsRun.current) {
      isFirstResultsRun.current = false
      return
    }
    refetchResults(search.direction, search.date, search.dateEnd)
  }, [search.direction, search.date, search.dateEnd, refetchResults])

  const totals = benchmarkTotals(results)
  const agentRanking = buildAgentBenchmarkRanking(results, search.agentLimit)
  const topQualityAgent = bestQualityAgent(
    buildAgentBenchmarkRanking(results, 'all')
  )

  const availableAgentes = useMemo(
    () =>
      [...new Set(results.map(row => benchmarkAgentLabel(row.agente)))].sort(
        (a, b) => a.localeCompare(b)
      ),
    [results]
  )
  const filteredResults = useMemo(
    () =>
      search.agentes === 'all'
        ? results
        : results.filter(row =>
            (search.agentes as string[]).includes(
              benchmarkAgentLabel(row.agente)
            )
          ),
    [results, search.agentes]
  )
  const [resultsPage, setResultsPage] = useState(1)
  const [resultsPageSize, setResultsPageSize] = useState<50 | 100>(50)
  const resultsTotalPages = Math.max(
    1,
    Math.ceil(filteredResults.length / resultsPageSize)
  )
  const resultsPageSafe = Math.min(resultsPage, resultsTotalPages)
  const pagedResults = useMemo(
    () =>
      filteredResults.slice(
        (resultsPageSafe - 1) * resultsPageSize,
        resultsPageSafe * resultsPageSize
      ),
    [filteredResults, resultsPageSafe, resultsPageSize]
  )
  function handleResultsPageSizeChange(value: string | null) {
    if (value === null) return
    setResultsPageSize(Number(value) as 50 | 100)
    setResultsPage(1)
  }
  function isAgenteChecked(agenteName: string) {
    return search.agentes === 'all' || search.agentes.includes(agenteName)
  }
  function toggleAgente(agenteName: string) {
    const current = search.agentes === 'all' ? availableAgentes : search.agentes
    const next = current.includes(agenteName)
      ? current.filter(a => a !== agenteName)
      : [...current, agenteName]
    setResultsPage(1)
    navigate({ search: prev => ({ ...prev, agentes: next }) })
  }
  function selectAllAgentes() {
    setResultsPage(1)
    navigate({ search: prev => ({ ...prev, agentes: 'all' }) })
  }
  function selectNoAgentes() {
    setResultsPage(1)
    navigate({ search: prev => ({ ...prev, agentes: [] }) })
  }
  const agentesFilterLabel =
    search.agentes === 'all' ||
    search.agentes.length === availableAgentes.length
      ? 'Todos'
      : search.agentes.length === 0
        ? 'Ninguno'
        : search.agentes.length === 1
          ? search.agentes[0]
          : `${search.agentes.length} agentes`

  return (
    <div>
      <div className="flex items-center gap-3">
        <h1 className="text-2xl font-bold tracking-tight">
          Benchmarks de agentes
        </h1>
        <Badge variant="secondary">
          {totals.analyzed}/{totals.total} casos con veredicto de calidad
        </Badge>
      </div>
      <p className="mt-1 text-sm text-muted-foreground">
        A partir de casos ya cerrados: tiempo de primera respuesta y calidad de
        atención (presentación + despedida), juzgada por un LLM sobre el reporte
        masivo de C3.
      </p>

      <Tabs
        value={search.view}
        onValueChange={value =>
          navigate({
            search: prev => ({ ...prev, view: value as BenchmarksView }),
            replace: true
          })
        }
        className="mt-6"
      >
        <TabsList className="w-fit">
          <TabsTrigger value="resultados">Resultados</TabsTrigger>
          <TabsTrigger value="administracion">Administración</TabsTrigger>
        </TabsList>

        <TabsContent value="resultados" className="mt-4">
          <div
            className={cn(
              'grid grid-cols-2 gap-4 transition-opacity lg:grid-cols-4',
              resultsLoading && 'opacity-50'
            )}
          >
            <Card size="sm">
              <CardHeader className="gap-1">
                <CardTitle className="text-base font-medium text-muted-foreground">
                  Casos totales
                </CardTitle>
                <CardDescription className="flex items-baseline gap-1.5 text-sm">
                  <span
                    className="font-bold text-foreground tabular-nums"
                    style={{ fontSize: CHART_BIG_NUMBER_FONT_SIZE }}
                  >
                    {totals.total}
                  </span>
                  en el rango elegido
                </CardDescription>
              </CardHeader>
            </Card>
            <Card size="sm">
              <CardHeader className="gap-1">
                <CardTitle className="text-base font-medium text-muted-foreground">
                  Con veredicto
                </CardTitle>
                <CardDescription className="flex items-baseline gap-1.5 text-sm">
                  <span
                    className="font-bold text-foreground tabular-nums"
                    style={{ fontSize: CHART_BIG_NUMBER_FONT_SIZE }}
                  >
                    {totals.analyzed}
                  </span>
                  {totals.total > 0
                    ? `${Math.round((totals.analyzed / totals.total) * 100)}% del total`
                    : 'del total'}
                </CardDescription>
              </CardHeader>
            </Card>
            <Card size="sm">
              <CardHeader className="gap-1">
                <CardTitle className="text-base font-medium text-muted-foreground">
                  1ra respuesta promedio
                </CardTitle>
                <CardDescription className="flex items-baseline gap-1.5 text-sm">
                  <span
                    className="font-bold text-foreground tabular-nums"
                    style={{ fontSize: CHART_BIG_NUMBER_FONT_SIZE }}
                  >
                    {totals.avgFirstResponseSeconds !== null
                      ? formatSecondsAsDuration(totals.avgFirstResponseSeconds)
                      : '—'}
                  </span>
                  promedio general
                </CardDescription>
              </CardHeader>
            </Card>
            <Card size="sm">
              <CardHeader className="gap-1">
                <CardTitle className="text-base font-medium text-muted-foreground">
                  Calidad promedio
                </CardTitle>
                <CardDescription className="flex items-baseline gap-1.5 text-sm">
                  <span
                    className="font-bold text-foreground tabular-nums"
                    style={{ fontSize: CHART_BIG_NUMBER_FONT_SIZE }}
                  >
                    {totals.qualityOkPct !== null
                      ? `${Math.round(totals.qualityOkPct)}%`
                      : '—'}
                  </span>
                  presentación + despedida
                </CardDescription>
              </CardHeader>
            </Card>
          </div>

          <Card className="mt-4">
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>Promedio por agente</CardTitle>
                <CardDescription>
                  Tiempo de primera respuesta y % de casos con presentación y
                  despedida.
                </CardDescription>
              </div>
              <div className="flex flex-col items-end gap-2">
                {topQualityAgent && (
                  <Badge variant="secondary" className="max-w-64">
                    <span className="min-w-0 truncate">
                      Mejor calidad: {topQualityAgent.agente} (
                      {Math.round(topQualityAgent.qualityOkPct ?? 0)}%)
                    </span>
                  </Badge>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-muted-foreground">
                    Top agentes
                  </span>
                  <Select
                    value={String(search.agentLimit)}
                    onValueChange={value =>
                      navigate({
                        search: prev => ({
                          ...prev,
                          agentLimit: (value === 'all'
                            ? 'all'
                            : Number(value)) as AgentLimit
                        })
                      })
                    }
                  >
                    <SelectTrigger className="w-36">
                      <SelectValue>
                        {() =>
                          search.agentLimit === 'all'
                            ? 'Todos'
                            : `Top ${search.agentLimit}`
                        }
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      {AGENT_LIMIT_OPTIONS.map(option => (
                        <SelectItem key={option} value={String(option)}>
                          {option === 'all' ? 'Todos' : `Top ${option}`}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>
            </CardHeader>
            <CardContent
              className={cn(
                'transition-opacity',
                resultsLoading && 'opacity-50'
              )}
            >
              {agentRanking.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  Todavía no hay resultados para el rango elegido.
                </p>
              ) : (
                <BenchmarkAgentChart agents={agentRanking} />
              )}
            </CardContent>
          </Card>

          <Card className="mt-4">
            <CardHeader className="flex-row items-center justify-between">
              <div>
                <CardTitle>Detalle por caso</CardTitle>
                <CardDescription>
                  {filteredResults.length} caso
                  {filteredResults.length === 1 ? '' : 's'} en el rango elegido.
                </CardDescription>
              </div>
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-muted-foreground">
                  Dirección
                </span>
                <Select
                  value={search.direction}
                  onValueChange={value => {
                    setResultsPage(1)
                    navigate({
                      search: prev => ({
                        ...prev,
                        direction: value as BenchmarkDirectionFilter
                      })
                    })
                  }}
                >
                  <SelectTrigger className="w-32">
                    <SelectValue>
                      {() =>
                        search.direction === 'all'
                          ? 'Todas'
                          : BENCHMARK_DIRECTION_LABEL[search.direction]
                      }
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas</SelectItem>
                    <SelectItem value="attention">Entrantes</SelectItem>
                    <SelectItem value="outboundattention">Salientes</SelectItem>
                  </SelectContent>
                </Select>
                {availableAgentes.length > 0 && (
                  <>
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
                          {agentesFilterLabel}
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
                  </>
                )}
                <span className="text-sm font-medium text-muted-foreground">
                  Fecha
                </span>
                <DateRangeFilter
                  date={search.date}
                  dateEnd={search.dateEnd}
                  onChange={(date, dateEnd) => {
                    setResultsPage(1)
                    navigate({ search: prev => ({ ...prev, date, dateEnd }) })
                  }}
                />
              </div>
            </CardHeader>
            <CardContent
              className={cn(
                'transition-opacity',
                resultsLoading && 'opacity-50'
              )}
            >
              <BenchmarkResultsTable results={pagedResults} />
            </CardContent>
            {filteredResults.length > 0 && (
              <CardFooter className="flex-wrap items-center justify-between gap-2">
                <div className="flex items-center gap-2">
                  <span className="text-sm text-muted-foreground">Mostrar</span>
                  <Select
                    value={String(resultsPageSize)}
                    onValueChange={handleResultsPageSizeChange}
                  >
                    <SelectTrigger className="w-20">
                      <SelectValue>{() => String(resultsPageSize)}</SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="50">50</SelectItem>
                      <SelectItem value="100">100</SelectItem>
                    </SelectContent>
                  </Select>
                  <span className="text-sm text-muted-foreground">
                    por página
                  </span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() => setResultsPage(p => Math.max(1, p - 1))}
                    disabled={resultsPageSafe <= 1}
                    aria-label="Pagina anterior"
                  >
                    <ChevronLeftIcon />
                  </Button>
                  <span className="text-sm text-muted-foreground">
                    Página {resultsPageSafe} de {resultsTotalPages}
                  </span>
                  <Button
                    variant="outline"
                    size="icon-sm"
                    onClick={() =>
                      setResultsPage(p => Math.min(resultsTotalPages, p + 1))
                    }
                    disabled={resultsPageSafe >= resultsTotalPages}
                    aria-label="Pagina siguiente"
                  >
                    <ChevronRightIcon />
                  </Button>
                </div>
              </CardFooter>
            )}
          </Card>
        </TabsContent>

        <TabsContent value="administracion" className="mt-4">
          <div className="grid gap-4 md:grid-cols-2">
            <BenchmarkRunCard initialStatus={runStatus} />
            <BenchmarkScheduleCard />
          </div>

          {llmSettings && <LlmSettingsCard initialSettings={llmSettings} />}

          <BenchmarkRunHistoryCard runs={runs} />
        </TabsContent>
      </Tabs>
    </div>
  )
}

function VerdictCell({ value }: { value: boolean | null }) {
  if (value === null) return <span className="text-muted-foreground">—</span>
  return value ? (
    <CheckIcon className="size-4 text-chart-2" />
  ) : (
    <XIcon className="size-4 text-destructive" />
  )
}

function NotesCell({ value }: { value: string | null }) {
  if (value === null || value.trim() === '') {
    return <span className="text-muted-foreground">—</span>
  }
  return (
    <Tooltip>
      <TooltipTrigger
        render={
          <span className="block max-w-48 truncate text-muted-foreground" />
        }
      >
        {value}
      </TooltipTrigger>
      <TooltipContent>{value}</TooltipContent>
    </Tooltip>
  )
}

const COMPLEXITY_LABEL: Record<BenchmarkComplexity, string> = {
  baja: 'Baja',
  media: 'Media',
  alta: 'Alta'
}
const COMPLEXITY_BADGE_CLASS: Record<BenchmarkComplexity, string> = {
  baja: 'bg-secondary text-secondary-foreground',
  media: 'bg-chart-4/15 text-chart-4',
  alta: 'bg-destructive/10 text-destructive'
}
function ComplexityCell({ value }: { value: BenchmarkComplexity | null }) {
  if (value === null) return <span className="text-muted-foreground">—</span>
  return (
    <Badge variant="secondary" className={COMPLEXITY_BADGE_CLASS[value]}>
      {COMPLEXITY_LABEL[value]}
    </Badge>
  )
}

const GREETING_LABEL: Record<BenchmarkGreetingLevel, string> = {
  ninguno: 'Ninguno',
  casual: 'Casual',
  formal: 'Formal'
}
// Casual y formal cuentan igual para quality_ok (solo "ninguno" resta) -- por eso
// comparten el mismo estilo "positivo", nunca uno mejor que el otro.
const GREETING_BADGE_CLASS: Record<BenchmarkGreetingLevel, string> = {
  ninguno: 'bg-destructive/10 text-destructive',
  casual: 'bg-chart-2/15 text-chart-2',
  formal: 'bg-chart-2/15 text-chart-2'
}
function GreetingCell({ value }: { value: BenchmarkGreetingLevel | null }) {
  if (value === null) return <span className="text-muted-foreground">—</span>
  return (
    <Badge variant="secondary" className={GREETING_BADGE_CLASS[value]}>
      {GREETING_LABEL[value]}
    </Badge>
  )
}

function TransferCell({
  hadTransfer,
  informedTransfer
}: {
  hadTransfer: boolean
  informedTransfer: boolean | null
}) {
  if (!hadTransfer) {
    return <span className="text-muted-foreground">Sin transferencia</span>
  }
  if (informedTransfer === null) {
    return <Badge variant="secondary">Transferida</Badge>
  }
  return informedTransfer ? (
    <Badge variant="secondary" className="bg-chart-2/15 text-chart-2">
      Informada
    </Badge>
  ) : (
    <Badge variant="secondary" className="bg-destructive/10 text-destructive">
      No informada
    </Badge>
  )
}

function BenchmarkResultsTable({
  results
}: {
  results: Awaited<ReturnType<typeof getBenchmarkResults>>
}) {
  if (results.length === 0) {
    return (
      <p className="text-sm text-muted-foreground">
        Todavía no hay casos analizados para el rango elegido.
      </p>
    )
  }
  return (
    <div className="overflow-x-auto">
      <Table>
        <TableHeader>
          <TableRow>
            <TableHead>ID atención</TableHead>
            <TableHead>Dirección</TableHead>
            <TableHead>Fecha cierre</TableHead>
            <TableHead>Cliente</TableHead>
            <TableHead>Agente</TableHead>
            <TableHead>Campaña</TableHead>
            <TableHead>1ra respuesta</TableHead>
            <TableHead>Saludo</TableHead>
            <TableHead>Despedida</TableHead>
            <TableHead>Ortografía</TableHead>
            <TableHead>Complejidad</TableHead>
            <TableHead>Manejo adecuado</TableHead>
            <TableHead>Transferencia</TableHead>
            <TableHead>Notas</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {results.map(row => (
            <TableRow key={`${row.direction}:${row.id_atencion}`}>
              <TableCell>{row.id_atencion}</TableCell>
              <TableCell>
                <span
                  className="mr-2 inline-block size-1.5 rounded-full align-middle"
                  style={{ background: BENCHMARK_DIRECTION_DOT[row.direction] }}
                />
                {BENCHMARK_DIRECTION_LABEL[row.direction]}
              </TableCell>
              <TableCell>
                {row.fecha_final
                  ? `${row.fecha_final}${row.hora_final ? ` ${row.hora_final}` : ''}`
                  : '—'}
              </TableCell>
              <TableCell>{row.cliente ?? 'Sin cliente'}</TableCell>
              <TableCell>{row.agente ?? 'Sin agente'}</TableCell>
              <TableCell>{row.campana ?? 'Sin campaña'}</TableCell>
              <TableCell>
                {row.first_response_seconds !== null ? (
                  formatSecondsAsDuration(row.first_response_seconds)
                ) : (
                  <span className="text-muted-foreground">—</span>
                )}
              </TableCell>
              <TableCell>
                <GreetingCell value={row.greeting_level} />
              </TableCell>
              <TableCell>
                <VerdictCell value={row.has_farewell} />
              </TableCell>
              <TableCell>
                <VerdictCell value={row.spelling_ok} />
              </TableCell>
              <TableCell>
                <ComplexityCell value={row.complexity} />
              </TableCell>
              <TableCell>
                <VerdictCell value={row.handled_well_for_complexity} />
              </TableCell>
              <TableCell>
                <TransferCell
                  hadTransfer={row.had_transfer}
                  informedTransfer={row.informed_transfer}
                />
              </TableCell>
              <TableCell>
                <NotesCell value={row.llm_notes} />
              </TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}

const BENCHMARK_RUN_POLL_MS = 3000

function runStatusBadge(phase: BenchmarkRunStatus['phase']): {
  label: string
  className: string
} {
  switch (phase) {
    case 'running':
      return { label: 'En curso', className: 'bg-primary/10 text-primary' }
    case 'done':
      return { label: 'Completado', className: 'bg-chart-2/15 text-chart-2' }
    case 'error':
      return {
        label: 'Error',
        className: 'bg-destructive/10 text-destructive'
      }
    default:
      return { label: 'Sin corridas', className: '' }
  }
}

function BenchmarkRunCard({
  initialStatus
}: {
  initialStatus: BenchmarkRunStatus
}) {
  const router = useRouter()
  const startRun = useServerFn(triggerBenchmarkRun)
  const getStatus = useServerFn(getBenchmarkRunStatus)
  const [status, setStatus] = useState(initialStatus)
  const [confirming, setConfirming] = useState(false)
  const [forceReanalyze, setForceReanalyze] = useState(false)
  const timeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  // Alcance de ESTA corrida, propio de la tarjeta -- deliberadamente independiente
  // del filtro de fecha/direccion de la pestana Resultados. Antes reusaba
  // search.date/search.direction (pedido explicito de backend para mantener la
  // corrida "scopeada a lo que se esta viendo"), pero con el split en pestanas esa
  // dependencia quedaba invisible: el usuario en Administracion no podia ver que
  // filtro de Resultados iba a terminar afectando su corrida. Controles propios
  // abajo resuelven la confusion sin tocar el contrato del backend (que ya acepta
  // dateFrom/dateTo/directions opcionales).
  const [runDate, setRunDate] = useState(todayIsoDate())
  const [runDateEnd, setRunDateEnd] = useState<string | undefined>(undefined)
  const [runDirection, setRunDirection] =
    useState<BenchmarkDirectionFilter>('all')
  const dateFrom = runDate
  const dateTo = runDateEnd ?? runDate
  const directions =
    runDirection === 'all'
      ? undefined
      : ([runDirection] as BenchmarkDirection[])
  const includesToday = dateFrom <= todayIsoDate() && todayIsoDate() <= dateTo

  useEffect(() => {
    if (status.phase !== 'running') return
    timeoutRef.current = setTimeout(async () => {
      const next = await getStatus()
      setStatus(next)
      if (next.phase !== 'running') {
        await router.invalidate()
      }
    }, BENCHMARK_RUN_POLL_MS)
    return () => {
      if (timeoutRef.current) clearTimeout(timeoutRef.current)
    }
  }, [status, getStatus, router])

  async function handleConfirm() {
    setConfirming(false)
    try {
      const next = await startRun({
        data: { directions, dateFrom, dateTo, forceReanalyze }
      })
      setStatus(next)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    }
  }

  const isRunning = status.phase === 'running'
  const badge = runStatusBadge(status.phase)
  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <div className="flex items-center gap-2">
            <CardTitle>Corrida de benchmarks</CardTitle>
            <Badge
              variant="secondary"
              className={cn('gap-1.5', badge.className)}
            >
              {isRunning && (
                <span className="size-1.5 animate-pulse rounded-full bg-current" />
              )}
              {badge.label}
            </Badge>
          </div>
          <CardDescription>
            Dispara el reporte masivo de C3 (entrantes y salientes) y el
            análisis de calidad para los casos ya cerrados que todavía no tengan
            veredicto, en el rango y dirección elegidos abajo.
          </CardDescription>
        </div>
        <Button
          onClick={() => {
            setForceReanalyze(false)
            setConfirming(true)
          }}
          disabled={isRunning || confirming}
          variant="secondary"
        >
          <PlayIcon
            data-icon="inline-start"
            className={cn(isRunning && 'animate-pulse')}
          />
          {isRunning ? 'Corriendo...' : 'Ejecutar ahora'}
        </Button>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap items-center gap-2 rounded-xl bg-muted/50 px-3 py-2">
          <span className="text-xs font-medium text-muted-foreground">
            Rango de esta corrida
          </span>
          <DateRangeFilter
            date={runDate}
            dateEnd={runDateEnd}
            onChange={(date, dateEndValue) => {
              setRunDate(date)
              setRunDateEnd(dateEndValue)
            }}
          />
          <span className="text-xs font-medium text-muted-foreground">
            Dirección
          </span>
          <Select
            value={runDirection}
            onValueChange={value =>
              setRunDirection(value as BenchmarkDirectionFilter)
            }
          >
            <SelectTrigger className="h-8 w-32 text-xs">
              <SelectValue>
                {() =>
                  runDirection === 'all'
                    ? 'Todas'
                    : BENCHMARK_DIRECTION_LABEL[runDirection]
                }
              </SelectValue>
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="all">Todas</SelectItem>
              <SelectItem value="attention">Entrantes</SelectItem>
              <SelectItem value="outboundattention">Salientes</SelectItem>
            </SelectContent>
          </Select>
          <span className="ml-auto text-xs text-muted-foreground">
            Independiente del filtro de Resultados
          </span>
        </div>
        <p className="text-sm text-muted-foreground">
          {status.phase === 'idle' && 'Sin corridas todavía.'}
          {status.phase === 'running' && `En curso desde ${status.started_at}.`}
          {status.phase === 'done' &&
            `Última corrida: ${status.finished_at} (ok: ${status.result?.ok}).`}
          {status.phase === 'error' && `Último error: ${status.error}`}
        </p>
        {confirming && (
          <div className="flex flex-col gap-3 rounded-xl bg-accent px-3.5 py-2.5">
            <p className="text-xs text-accent-foreground">
              Esto le pide a C3 el reporte masivo de atenciones entrantes y
              salientes (puede tardar horas) y después llama a un LLM por cada
              caso cerrado sin veredicto todavía, entre{' '}
              <strong>{dateFrom}</strong>
              {dateTo !== dateFrom && (
                <>
                  {' '}
                  y <strong>{dateTo}</strong>
                </>
              )}
              . ¿Continuar?
            </p>
            {!includesToday && (
              <p className="text-xs text-destructive">
                El rango elegido no incluye hoy -- el reporte masivo de C3
                siempre trae el zip de hoy, así que los casos nuevos de este
                rango van a quedar sin PDF para analizar.
              </p>
            )}
            <div className="flex items-center gap-2">
              <Checkbox
                id="benchmark-force-reanalyze"
                checked={forceReanalyze}
                onCheckedChange={checked => setForceReanalyze(checked === true)}
                className="border-accent-foreground"
              />
              <Label
                htmlFor="benchmark-force-reanalyze"
                className="text-xs font-normal text-accent-foreground"
              >
                Reanalizar casos ya evaluados
              </Label>
            </div>
            <div className="flex shrink-0 justify-end gap-2">
              <Button
                size="sm"
                variant="ghost"
                onClick={() => setConfirming(false)}
              >
                Cancelar
              </Button>
              <Button size="sm" onClick={handleConfirm}>
                Sí, ejecutar
              </Button>
            </div>
          </div>
        )}
        {isRunning && (
          <div className="h-1.5 overflow-hidden rounded-full bg-muted">
            <div className="h-full w-2/5 animate-[progress-indeterminate_1.1s_ease-in-out_infinite] rounded-full bg-primary" />
          </div>
        )}
      </CardContent>
      {status.result && (
        <CardFooter className="flex-col items-stretch gap-1 border-t pt-3">
          {status.result.directions.map(direction => (
            <p
              key={direction.direction}
              className="text-xs text-muted-foreground"
            >
              {BENCHMARK_DIRECTION_LABEL[direction.direction]}:{' '}
              {direction.action === 'failed'
                ? `fallo (${direction.error})`
                : `${direction.cases_analyzed} analizados de ${direction.cases_pending} pendientes (${direction.cases_closed} cerrados en total)`}
            </p>
          ))}
        </CardFooter>
      )}
    </Card>
  )
}

function BenchmarkScheduleCard() {
  const { settings, setSettings, lastRunAt, lastError } = useBenchmarkSchedule()
  const [draftEnabled, setDraftEnabled] = useState(settings.enabled)
  const [draftTime, setDraftTime] = useState(settings.timeOfDay)

  function handleSave() {
    if (!/^([01]\d|2[0-3]):([0-5]\d)$/.test(draftTime)) {
      toast.error('La hora debe tener el formato HH:mm.')
      return
    }
    setSettings({ ...settings, enabled: draftEnabled, timeOfDay: draftTime })
    toast.success('Horario de benchmarks diarios actualizado.')
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Corrida automática diaria</CardTitle>
          <CardDescription>
            Programable desde el cliente, igual que el auto-refresh: mientras
            esta pestaña esté abierta, dispara la corrida una vez por día a la
            hora elegida (horario Lima). Apagado por defecto -- es una corrida
            de horas con costo real de LLM.
          </CardDescription>
        </div>
        <Badge
          variant="secondary"
          className={settings.enabled ? 'bg-primary/10 text-primary' : ''}
        >
          {settings.enabled
            ? `Activado · ${settings.timeOfDay}`
            : 'Desactivado'}
        </Badge>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="flex items-center gap-2">
          <Switch
            id="benchmark-schedule-enabled"
            checked={draftEnabled}
            onCheckedChange={setDraftEnabled}
          />
          <Label htmlFor="benchmark-schedule-enabled">Activado</Label>
        </div>
        <div className="flex flex-wrap items-end gap-2">
          <Field className="w-32">
            <FieldLabel htmlFor="benchmark-schedule-time">
              Hora (Lima)
            </FieldLabel>
            <Input
              id="benchmark-schedule-time"
              type="time"
              value={draftTime}
              onChange={e => setDraftTime(e.target.value)}
            />
          </Field>
          <Button onClick={handleSave}>Guardar</Button>
        </div>
        <p className="text-xs text-muted-foreground">
          {settings.enabled
            ? `Activo: todos los días a las ${settings.timeOfDay}.`
            : 'Desactivado.'}{' '}
          {settings.lastTriggeredDateIso &&
            `Último disparo automático: ${settings.lastTriggeredDateIso}.`}{' '}
          {lastRunAt && `(${lastRunAt.toLocaleTimeString()})`}
        </p>
        {lastError && (
          <p className="text-xs text-destructive">
            Último error del disparo automático: {lastError}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function LlmSettingsCard({
  initialSettings
}: {
  initialSettings: LlmSettings
}) {
  const doUpdateSettings = useServerFn(updateLlmSettings)
  const [settings, setSettings] = useState(initialSettings)
  const [dialogOpen, setDialogOpen] = useState(false)
  const [providerName, setProviderName] = useState(settings.provider_name)
  const [model, setModel] = useState(settings.minimax_model ?? '')
  const [baseUrl, setBaseUrl] = useState(settings.minimax_base_url ?? '')
  const [apiKey, setApiKey] = useState('')
  const [pending, setPending] = useState(false)

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    setPending(true)
    try {
      const updated = await doUpdateSettings({
        data: {
          provider_name: providerName,
          ...(apiKey ? { minimax_api_key: apiKey } : {}),
          minimax_model: model,
          minimax_base_url: baseUrl
        }
      })
      setSettings(updated)
      setDialogOpen(false)
      toast.success('Configuración del LLM actualizada.')
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <Card className="mt-4">
      <CardHeader className="flex-row items-center justify-between">
        <div>
          <CardTitle>Configuración del LLM</CardTitle>
          <CardDescription>
            Proveedor usado para juzgar la calidad de las atenciones. Sin una
            API key configurada, "Ejecutar ahora" va a fallar.
          </CardDescription>
        </div>
        <Dialog
          open={dialogOpen}
          onOpenChange={open => {
            setDialogOpen(open)
            if (open) {
              setProviderName(settings.provider_name)
              setModel(settings.minimax_model ?? '')
              setBaseUrl(settings.minimax_base_url ?? '')
              setApiKey('')
            }
          }}
        >
          <DialogTrigger render={<Button variant="secondary" />}>
            <SettingsIcon data-icon="inline-start" />
            {settings.has_api_key ? 'Editar' : 'Configurar'}
          </DialogTrigger>
          <DialogContent>
            <DialogHeader>
              <DialogTitle>Configuración del LLM</DialogTitle>
              <DialogDescription>
                La API key nunca se muestra -- dejala en blanco para conservar
                la que ya está guardada.
              </DialogDescription>
            </DialogHeader>
            <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
              <div className="flex flex-col gap-2">
                <Label htmlFor="llm-provider">Proveedor</Label>
                <Input
                  id="llm-provider"
                  value={providerName}
                  onChange={e => setProviderName(e.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="llm-model">Modelo</Label>
                <Input
                  id="llm-model"
                  value={model}
                  onChange={e => setModel(e.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="llm-base-url">Base URL</Label>
                <Input
                  id="llm-base-url"
                  type="url"
                  value={baseUrl}
                  onChange={e => setBaseUrl(e.target.value)}
                  required
                />
              </div>
              <div className="flex flex-col gap-2">
                <Label htmlFor="llm-api-key">API key</Label>
                <Input
                  id="llm-api-key"
                  type="password"
                  autoComplete="off"
                  value={apiKey}
                  onChange={e => setApiKey(e.target.value)}
                  placeholder={
                    settings.has_api_key
                      ? 'Dejar en blanco para no cambiarla'
                      : 'Requerida'
                  }
                  required={!settings.has_api_key}
                />
              </div>
              <DialogFooter>
                <DialogClose
                  render={<Button type="button" variant="outline" />}
                >
                  Cancelar
                </DialogClose>
                <Button type="submit" disabled={pending}>
                  {pending ? 'Guardando...' : 'Guardar'}
                </Button>
              </DialogFooter>
            </form>
          </DialogContent>
        </Dialog>
      </CardHeader>
      <CardContent className="space-y-1.5 text-sm">
        <p className="text-muted-foreground">
          Proveedor:{' '}
          <span className="text-foreground">{settings.provider_name}</span>
        </p>
        <p className="text-muted-foreground">
          Modelo:{' '}
          <span className="text-foreground">
            {settings.minimax_model ?? 'sin configurar'}
          </span>
        </p>
        <p className="text-muted-foreground">
          Base URL:{' '}
          <span className="text-foreground">
            {settings.minimax_base_url ?? 'sin configurar'}
          </span>
        </p>
        <p className="flex items-center gap-2 text-muted-foreground">
          API key:
          <Badge
            variant="secondary"
            className={
              settings.has_api_key
                ? 'bg-chart-2/15 text-chart-2'
                : 'bg-destructive/10 text-destructive'
            }
          >
            {settings.has_api_key ? 'Configurada' : 'Sin configurar'}
          </Badge>
        </p>
        {settings.updated_at && (
          <p className="text-xs text-muted-foreground">
            Última actualización:{' '}
            {new Date(settings.updated_at).toLocaleString()}
          </p>
        )}
      </CardContent>
    </Card>
  )
}

function runOkBadge(ok: boolean | null): { label: string; className: string } {
  if (ok === null) {
    return { label: 'En curso', className: 'bg-primary/10 text-primary' }
  }
  return ok
    ? { label: 'Completado', className: 'bg-chart-2/15 text-chart-2' }
    : { label: 'Error', className: 'bg-destructive/10 text-destructive' }
}

function BenchmarkRunHistoryCard({ runs }: { runs: BenchmarkRunRecord[] }) {
  return (
    <Card className="mt-4">
      <CardHeader>
        <CardTitle>Historial de corridas</CardTitle>
        <CardDescription>
          {runs.length} corrida{runs.length === 1 ? '' : 's'} más reciente
          {runs.length === 1 ? '' : 's'}.
        </CardDescription>
      </CardHeader>
      <CardContent>
        {runs.length === 0 ? (
          <p className="text-sm text-muted-foreground">
            Todavía no hay corridas registradas.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Inicio</TableHead>
                  <TableHead>Fin</TableHead>
                  <TableHead>Estado</TableHead>
                  <TableHead>Rango</TableHead>
                  <TableHead>Direcciones</TableHead>
                  <TableHead>Reanalizar</TableHead>
                  <TableHead>Resultado</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {runs.map(run => {
                  const badge = runOkBadge(run.ok)
                  const resultSummary = run.directions
                    .map(
                      direction =>
                        `${BENCHMARK_DIRECTION_LABEL[direction.direction]}: ${
                          direction.action === 'failed'
                            ? `falló (${direction.error})`
                            : `${direction.cases_analyzed}/${direction.cases_pending}`
                        }`
                    )
                    .join(' · ')
                  return (
                    <TableRow key={run.id}>
                      <TableCell>
                        {new Date(run.started_at).toLocaleString()}
                      </TableCell>
                      <TableCell>
                        {run.finished_at
                          ? new Date(run.finished_at).toLocaleString()
                          : '—'}
                      </TableCell>
                      <TableCell>
                        <Badge variant="secondary" className={badge.className}>
                          {badge.label}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        {run.date_from
                          ? `${run.date_from}${
                              run.date_to && run.date_to !== run.date_from
                                ? ` a ${run.date_to}`
                                : ''
                            }`
                          : 'Todo'}
                      </TableCell>
                      <TableCell>
                        {run.requested_directions.length > 0
                          ? run.requested_directions
                              .map(
                                direction =>
                                  BENCHMARK_DIRECTION_LABEL[
                                    direction as BenchmarkDirection
                                  ] ?? direction
                              )
                              .join(', ')
                          : 'Todas'}
                      </TableCell>
                      <TableCell>{run.force_reanalyze ? 'Sí' : 'No'}</TableCell>
                      <TableCell className="max-w-64">
                        {run.error ? (
                          <Tooltip>
                            <TooltipTrigger
                              render={
                                <span className="block truncate text-destructive" />
                              }
                            >
                              {run.error}
                            </TooltipTrigger>
                            <TooltipContent>{run.error}</TooltipContent>
                          </Tooltip>
                        ) : (
                          <span className="block truncate text-muted-foreground">
                            {resultSummary || '—'}
                          </span>
                        )}
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        )}
      </CardContent>
    </Card>
  )
}
