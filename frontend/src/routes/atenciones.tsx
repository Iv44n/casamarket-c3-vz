import { createFileRoute, Link } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import {
  ChevronDownIcon,
  FileJsonIcon,
  FileTextIcon,
  RefreshCwIcon
} from 'lucide-react'
import { useCallback, useEffect, useRef, useState } from 'react'
import { toast } from 'sonner'
import { AgentWorkloadChart } from '#/components/agent-workload-chart'
import { AttentionRecordsTable } from '#/components/attention-records-table'
import { CampaignWorkloadChart } from '#/components/campaign-workload-chart'
import { DateRangeFilter } from '#/components/date-range-filter'
import { DemandHeatmapChart } from '#/components/demand-heatmap-chart'
import { IncidentHierarchy } from '#/components/incident-hierarchy'
import { StatusDonutChart } from '#/components/status-donut-chart'
import { Badge } from '#/components/ui/badge'
import { Button } from '#/components/ui/button'
import {
  Card,
  CardAction,
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
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '#/components/ui/select'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '#/components/ui/tabs'
import {
  buildAgentRanking,
  buildCampaignRanking,
  buildDemandHeatmap,
  buildStatusChartData,
  buildTopClosers,
  describeAvailability,
  getAvailableEstados
} from '#/lib/attentions-analytics'
import { downloadBlob } from '#/lib/download-file'
import {
  buildIncidentHierarchyTree,
  INCIDENT_CATEGORY_COLOR,
  INCIDENT_CATEGORY_LABEL,
  pickDominantCategoryOrder
} from '#/lib/incident-analytics'
import { buildIncidentHierarchyPdf } from '#/lib/incident-hierarchy-pdf'
import { cn } from '#/lib/utils'
import {
  getAttentionRecordsPage,
  getAttentionsAnalytics,
  getDemandAnalytics,
  getIncidentAnalytics,
  triggerBackfill,
  triggerRefresh
} from '#/server/reports.functions'
import {
  AGENT_LIMIT_OPTIONS,
  type AgentLimit,
  ATTENTION_FILTERS,
  type AtencionesView,
  type AttentionFilter,
  type AttentionRecordsPage,
  type AttentionsSearch,
  attentionsSearchSchema,
  type EstadosFilter,
  type IncidentCategory,
  todayIsoDate
} from '#/server/schemas'

const FILTER_LABEL: Record<AttentionFilter, string> = {
  all: 'Todas',
  incoming: 'Entrantes',
  outgoing: 'Salientes'
}
function formatAgentLimit(limit: AgentLimit) {
  return limit === 'all' ? 'Todos' : `Top ${limit}`
}
function formatEstadosFilter(filter: EstadosFilter, available: string[]) {
  if (filter === 'all' || filter.length === available.length) {
    return 'Todos'
  }
  if (filter.length === 0) {
    return 'Ninguno'
  }
  if (filter.length === 1) {
    return filter[0]
  }
  return `${filter.length} estados`
}
function CategorySwatch({ category }: { category: IncidentCategory }) {
  return (
    <span
      className="size-2.5 shrink-0 rounded-sm"
      style={{ background: INCIDENT_CATEGORY_COLOR[category] }}
    />
  )
}
const UNKNOWN_AGENT_LABEL = 'Sin agente'
function incidentAgentLabel(agente: string) {
  return agente.trim() === '' ? UNKNOWN_AGENT_LABEL : agente
}
const UNKNOWN_PLAN_LABEL = 'Sin plan'
function planLabel(plan: string) {
  return plan.trim() === '' ? UNKNOWN_PLAN_LABEL : plan
}
const DEMORAS_PAGE_SIZE = 50

const EMPTY_ATTENTION_RECORDS_PAGE: AttentionRecordsPage = {
  total: 0,
  staleCount: 0,
  records: [],
  availablePlans: []
}

export const Route = createFileRoute('/atenciones')({
  ssr: 'data-only',
  validateSearch: attentionsSearchSchema,
  loader: async ({ location }) => {
    const { date, dateEnd, demandDate, demandDateEnd } =
      location.search as AttentionsSearch
    const [attentions, incidents, demand] = await Promise.all([
      getAttentionsAnalytics({ data: { date, dateEnd } }),
      getIncidentAnalytics({ data: { date, dateEnd } }),
      getDemandAnalytics({ data: { date: demandDate, dateEnd: demandDateEnd } })
    ])
    return { attentions, incidents, demand }
  },
  component: AtencionesPage
})
function AtencionesPage() {
  const initialData = Route.useLoaderData()
  const {
    direction,
    agentLimit,
    estados,
    view,
    category,
    agente,
    campana,
    plan,
    date,
    dateEnd,
    demandDate,
    demandDateEnd,
    demorasPage
  } = Route.useSearch()
  const navigate = Route.useNavigate()
  const refresh = useServerFn(triggerRefresh)
  const backfill = useServerFn(triggerBackfill)
  const fetchAttentionsAnalytics = useServerFn(getAttentionsAnalytics)
  const fetchIncidentAnalytics = useServerFn(getIncidentAnalytics)
  const fetchDemandAnalytics = useServerFn(getDemandAnalytics)
  const fetchAttentionRecordsPage = useServerFn(getAttentionRecordsPage)
  const [pending, setPending] = useState(false)
  const [analytics, setAnalytics] = useState(initialData.attentions)
  const [incidentAnalytics, setIncidentAnalytics] = useState(
    initialData.incidents
  )
  const [demandAnalytics, setDemandAnalytics] = useState(initialData.demand)
  const [summaryLoading, setSummaryLoading] = useState(false)
  const [demandLoading, setDemandLoading] = useState(false)
  const [attentionRecordsPage, setAttentionRecordsPage] = useState(
    EMPTY_ATTENTION_RECORDS_PAGE
  )
  const [demorasLoading, setDemorasLoading] = useState(true)
  const isFirstSummaryRun = useRef(true)
  const refetchSummary = useCallback(
    async (targetDate: typeof date, targetDateEnd: typeof dateEnd) => {
      setSummaryLoading(true)
      try {
        const [attentions, incidents] = await Promise.all([
          fetchAttentionsAnalytics({
            data: { date: targetDate, dateEnd: targetDateEnd }
          }),
          fetchIncidentAnalytics({
            data: { date: targetDate, dateEnd: targetDateEnd }
          })
        ])
        setAnalytics(attentions)
        setIncidentAnalytics(incidents)
      } finally {
        setSummaryLoading(false)
      }
    },
    [fetchAttentionsAnalytics, fetchIncidentAnalytics]
  )
  useEffect(() => {
    if (isFirstSummaryRun.current) {
      isFirstSummaryRun.current = false
      return
    }
    refetchSummary(date, dateEnd)
  }, [date, dateEnd, refetchSummary])

  const isFirstDemandRun = useRef(true)
  const refetchDemand = useCallback(
    async (
      targetDemandDate: typeof demandDate,
      targetDemandDateEnd: typeof demandDateEnd
    ) => {
      setDemandLoading(true)
      try {
        setDemandAnalytics(
          await fetchDemandAnalytics({
            data: { date: targetDemandDate, dateEnd: targetDemandDateEnd }
          })
        )
      } finally {
        setDemandLoading(false)
      }
    },
    [fetchDemandAnalytics]
  )
  useEffect(() => {
    if (isFirstDemandRun.current) {
      isFirstDemandRun.current = false
      return
    }
    refetchDemand(demandDate, demandDateEnd)
  }, [demandDate, demandDateEnd, refetchDemand])

  useEffect(() => {
    if (view !== 'demoras') return
    let cancelled = false
    setDemorasLoading(true)
    fetchAttentionRecordsPage({
      data: {
        direction,
        estados,
        campana,
        agente,
        date,
        dateEnd,
        page: demorasPage,
        pageSize: DEMORAS_PAGE_SIZE
      }
    })
      .then(result => {
        if (!cancelled) setAttentionRecordsPage(result)
      })
      .finally(() => {
        if (!cancelled) setDemorasLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [
    view,
    direction,
    estados,
    campana,
    agente,
    date,
    dateEnd,
    demorasPage,
    fetchAttentionRecordsPage
  ])
  const availableEstados = getAvailableEstados(analytics)
  const { total, slices } = buildStatusChartData(analytics, direction, estados)
  const agents = buildAgentRanking(analytics, direction, agentLimit, estados)
  const topClosers = buildTopClosers(analytics)
  const campaigns = buildCampaignRanking(analytics, direction, estados)
  const demandHeatmap = buildDemandHeatmap(demandAnalytics, direction, estados)
  const { blockedMessage, advisoryMessage } = describeAvailability(
    analytics,
    direction
  )
  const availableIncidentAgents = [
    ...new Set(
      incidentAnalytics.records.map(record => incidentAgentLabel(record.agente))
    )
  ].sort((a, b) => a.localeCompare(b))
  const availableIncidentCampaigns = [
    ...new Set(incidentAnalytics.records.map(record => record.campana))
  ].sort((a, b) => a.localeCompare(b))
  const incidentRecords = incidentAnalytics.records.filter(
    record =>
      (agente === 'all' || incidentAgentLabel(record.agente) === agente) &&
      (campana === 'all' || record.campana === campana)
  )
  const incidentCategoryOrder = pickDominantCategoryOrder(incidentRecords)
  const activeIncidentCategory = incidentCategoryOrder.includes(category)
    ? category
    : (incidentCategoryOrder[0] ?? category)
  const attentionRecordsAvailable =
    analytics.incoming.available || analytics.outgoing.available
  const availableRecordCampaigns = [
    ...new Set([
      ...analytics.incoming.campaignCounts.map(c => c.campana),
      ...analytics.outgoing.campaignCounts.map(c => c.campana)
    ])
  ].sort((a, b) => a.localeCompare(b))
  const availableRecordAgents = [
    ...new Set([
      ...analytics.incoming.agentCounts.map(a => a.agente),
      ...analytics.outgoing.agentCounts.map(a => a.agente)
    ])
  ].sort((a, b) => a.localeCompare(b))
  const availableRecordPlans = [
    ...new Set(attentionRecordsPage.availablePlans.map(planLabel))
  ].sort((a, b) => a.localeCompare(b))
  const filteredAttentionRecords = attentionRecordsPage.records.filter(
    record => plan === 'all' || planLabel(record.plan) === plan
  )
  const isRangeSelected = date !== 'all' && Boolean(dateEnd) && dateEnd !== date
  const isPastDaySelected =
    date !== 'all' && !isRangeSelected && date !== todayIsoDate()
  async function handleRefresh() {
    setPending(true)
    try {
      if (isPastDaySelected) {
        await backfill({ data: { date } })
        toast.success(`Backfill de ${date} completado.`)
      } else {
        await refresh()
        toast.success('Extraccion completada')
      }
      await Promise.all([
        refetchSummary(date, dateEnd),
        refetchDemand(demandDate, demandDateEnd)
      ])
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }
  function isEstadoChecked(estado: string) {
    return estados === 'all' || estados.includes(estado)
  }
  function toggleEstado(estado: string) {
    const current = estados === 'all' ? availableEstados : estados
    const next = current.includes(estado)
      ? current.filter(e => e !== estado)
      : [...current, estado]
    navigate({
      search: prev => ({ ...prev, estados: next, demorasPage: 1 }),
      replace: true
    })
  }
  function goToAgentIncidents(clickedAgent: string) {
    navigate({
      search: prev => ({
        ...prev,
        view: 'incidencias',
        agente: clickedAgent,
        demorasPage: 1
      }),
      replace: true
    })
  }
  const incidentExportChain = incidentCategoryOrder.slice(
    incidentCategoryOrder.indexOf(activeIncidentCategory)
  )
  const incidentExportFilters = [
    agente !== 'all' ? `Agente: ${agente}` : null,
    campana !== 'all' ? `Campaña: ${campana}` : null
  ].filter((part): part is string => part !== null)
  function handleDownloadIncidentsJson() {
    const payload = {
      generadoEn: new Date().toISOString(),
      categoria: activeIncidentCategory,
      cadena: incidentExportChain,
      total: incidentRecords.length,
      filtros: { agente, campana },
      arbol: buildIncidentHierarchyTree(incidentRecords, incidentExportChain)
    }
    downloadBlob(
      new Blob([JSON.stringify(payload, null, 2)], {
        type: 'application/json'
      }),
      `incidencias-${activeIncidentCategory}.json`
    )
  }
  async function handleDownloadIncidentsPdf() {
    try {
      const blob = await buildIncidentHierarchyPdf({
        title: `Escalera de incidencias -- ${INCIDENT_CATEGORY_LABEL[activeIncidentCategory]}`,
        subtitle: `${incidentRecords.length} incidencias${incidentExportFilters.length ? ` -- ${incidentExportFilters.join(', ')}` : ''}`,
        chain: incidentExportChain,
        tree: buildIncidentHierarchyTree(incidentRecords, incidentExportChain)
      })
      downloadBlob(blob, `incidencias-${activeIncidentCategory}.pdf`)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    }
  }
  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Atenciones</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Distribucion por estado, agente, tipo de caso e incidencias de las
            atenciones de WhatsApp del ultimo archivo descargado.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <DateRangeFilter
            date={date}
            dateEnd={dateEnd}
            onChange={(newDate, newDateEnd) =>
              navigate({
                search: prev => ({
                  ...prev,
                  date: newDate,
                  dateEnd: newDateEnd,
                  demorasPage: 1
                }),
                replace: true
              })
            }
          />

          {view === 'resumen' && (
            <>
              <Button
                onClick={handleRefresh}
                disabled={pending || isRangeSelected}
                variant="outline"
                title={
                  isRangeSelected
                    ? 'Elegi un solo dia (o "Todos") para refrescar desde aqui -- usa "Backfill historico" en Extraction status para un rango.'
                    : undefined
                }
              >
                <RefreshCwIcon
                  data-icon="inline-start"
                  className={cn(pending && 'animate-spin')}
                />
                {pending
                  ? 'Corriendo...'
                  : isPastDaySelected
                    ? `Backfill ${date}`
                    : 'Refresh ahora'}
              </Button>

              <DropdownMenu>
                <DropdownMenuTrigger
                  render={
                    <Button
                      variant="outline"
                      className="w-40 justify-between font-normal"
                    />
                  }
                >
                  {formatEstadosFilter(estados, availableEstados)}
                  <ChevronDownIcon className="size-4 text-muted-foreground" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  {availableEstados.map(estado => (
                    <Label
                      key={estado}
                      className="cursor-default rounded-xl px-3 py-2 font-normal hover:bg-accent"
                    >
                      <Checkbox
                        checked={isEstadoChecked(estado)}
                        onCheckedChange={() => toggleEstado(estado)}
                      />
                      {estado}
                    </Label>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>

              <Select
                value={String(agentLimit)}
                onValueChange={value =>
                  navigate({
                    search: prev => ({
                      ...prev,
                      agentLimit:
                        value === 'all' ? 'all' : (Number(value) as AgentLimit)
                    }),
                    replace: true
                  })
                }
              >
                <SelectTrigger className="w-32">
                  <SelectValue>
                    {(value: string) => formatAgentLimit(value as AgentLimit)}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {AGENT_LIMIT_OPTIONS.map(limit => (
                    <SelectItem key={limit} value={String(limit)}>
                      {formatAgentLimit(limit)}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>

              <Select
                value={direction}
                onValueChange={value =>
                  navigate({
                    search: prev => ({
                      ...prev,
                      direction: value as AttentionFilter,
                      demorasPage: 1
                    }),
                    replace: true
                  })
                }
              >
                <SelectTrigger className="w-36">
                  <SelectValue>
                    {(value: AttentionFilter) => FILTER_LABEL[value]}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {ATTENTION_FILTERS.map(filter => (
                    <SelectItem key={filter} value={filter}>
                      {FILTER_LABEL[filter]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </>
          )}
        </div>
      </div>

      <Tabs
        value={view}
        onValueChange={value =>
          navigate({
            search: prev => ({ ...prev, view: value as AtencionesView }),
            replace: true
          })
        }
        className="mt-6"
      >
        <TabsList className="w-fit">
          <TabsTrigger value="resumen">Resumen</TabsTrigger>
          <TabsTrigger value="incidencias">Incidencias</TabsTrigger>
          <TabsTrigger value="demoras">Demoras</TabsTrigger>
        </TabsList>

        <TabsContent value="resumen" className="mt-4">
          {blockedMessage ? (
            <Card>
              <CardContent className="text-sm text-muted-foreground">
                {blockedMessage} Dispara un refresh desde{' '}
                <Link to="/status" className="text-primary underline">
                  /status
                </Link>
                .
              </CardContent>
            </Card>
          ) : (
            <div>
              {advisoryMessage && (
                <p className="mb-4 text-sm text-muted-foreground">
                  {advisoryMessage} Dispara un refresh desde{' '}
                  <Link to="/status" className="text-primary underline">
                    /status
                  </Link>
                  .
                </p>
              )}

              <div
                className={cn(
                  'grid grid-cols-1 gap-4 transition-opacity lg:grid-cols-2',
                  summaryLoading && 'opacity-50'
                )}
              >
                <section
                  aria-label="Distribucion por estado"
                  className="flex flex-col"
                >
                  <Card size="sm" className="flex h-full flex-col">
                    <CardHeader className="shrink-0 gap-0.5">
                      <CardTitle className="text-base font-medium text-muted-foreground">
                        Estado de atenciones
                      </CardTitle>
                      <CardDescription className="text-sm">
                        {total} atenciones
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-1 items-center justify-center">
                      {slices.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          Sin registros.
                        </p>
                      ) : (
                        <StatusDonutChart total={total} slices={slices} />
                      )}
                    </CardContent>
                  </Card>
                </section>

                <section
                  aria-label="Atenciones por tipo de caso"
                  className="flex flex-col"
                >
                  <Card size="sm" className="flex h-full flex-col">
                    <CardHeader className="shrink-0 gap-0.5">
                      <CardTitle className="text-base font-medium text-muted-foreground">
                        Tipo de caso
                      </CardTitle>
                      <CardDescription className="text-sm">
                        Distribucion por campaña
                      </CardDescription>
                    </CardHeader>
                    <CardContent className="flex flex-1 items-center">
                      {campaigns.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          Sin registros.
                        </p>
                      ) : (
                        <CampaignWorkloadChart campaigns={campaigns} />
                      )}
                    </CardContent>
                  </Card>
                </section>

                <section
                  aria-label="Atenciones por agente"
                  className="flex flex-col lg:col-span-2"
                >
                  <Card size="sm" className="flex h-full flex-col">
                    <CardHeader className="shrink-0 gap-0.5">
                      <CardTitle className="text-base font-medium text-muted-foreground">
                        {agentLimit === 'all'
                          ? 'Todos los agentes'
                          : `Top ${agentLimit} agentes`}
                      </CardTitle>
                      <CardDescription className="text-sm">
                        Carga de trabajo diaria
                      </CardDescription>
                      {topClosers.length > 0 && (
                        <CardAction>
                          <button
                            type="button"
                            onClick={() =>
                              goToAgentIncidents(topClosers[0].agente)
                            }
                          >
                            <Badge
                              variant="secondary"
                              className="cursor-pointer"
                            >
                              Top cerrando: {topClosers[0].agente} (
                              {topClosers[0].count})
                            </Badge>
                          </button>
                        </CardAction>
                      )}
                    </CardHeader>
                    <CardContent className="flex flex-1 items-center">
                      {agents.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          Sin registros.
                        </p>
                      ) : (
                        <AgentWorkloadChart
                          agents={agents}
                          onAgentClick={goToAgentIncidents}
                        />
                      )}
                    </CardContent>
                  </Card>
                </section>

                <section
                  aria-label="Mapa de calor de demanda"
                  className="flex flex-col lg:col-span-2"
                >
                  <Card size="sm" className="flex h-full flex-col">
                    <CardHeader className="shrink-0 gap-0.5">
                      <CardTitle className="text-base font-medium text-muted-foreground">
                        Mapa de calor de demanda
                      </CardTitle>
                      <CardDescription className="text-sm">
                        Volumen de tickets por día de la semana y hora --
                        identifica picos de capacidad. Elegi cualquier rango de
                        fechas (puede abarcar varias semanas); usa su propio
                        filtro, independiente del filtro de arriba.
                      </CardDescription>
                      <CardAction>
                        <DateRangeFilter
                          date={demandDate}
                          dateEnd={demandDateEnd}
                          onChange={(newDate, newDateEnd) =>
                            navigate({
                              search: prev => ({
                                ...prev,
                                demandDate: newDate,
                                demandDateEnd:
                                  newDateEnd ??
                                  (newDate === 'all' ? demandDateEnd : newDate)
                              }),
                              replace: true,
                              resetScroll: false
                            })
                          }
                          clearLabel="Quitar filtro de fecha del mapa de calor"
                        />
                      </CardAction>
                    </CardHeader>
                    <CardContent
                      className={cn(
                        'flex flex-1 items-center transition-opacity',
                        demandLoading && 'opacity-50'
                      )}
                    >
                      {demandHeatmap.total === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          Sin registros.
                        </p>
                      ) : (
                        <DemandHeatmapChart heatmap={demandHeatmap} />
                      )}
                    </CardContent>
                  </Card>
                </section>
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="incidencias" className="mt-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-muted-foreground">
              {incidentRecords.length} incidencias registradas en atenciones y
              llamadas salientes
              {agente !== 'all' && ` para ${agente}`}
              {campana !== 'all' && ` en ${campana}`} -- haz clic en una barra
              para ver su desglose, hasta llegar al ticket.
            </p>

            <div className="flex flex-wrap items-center gap-3">
              {availableIncidentCampaigns.length > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-muted-foreground">
                    Campaña
                  </span>
                  <Select
                    value={campana}
                    onValueChange={value =>
                      navigate({
                        search: prev => ({
                          ...prev,
                          campana: value ?? 'all',
                          demorasPage: 1
                        }),
                        replace: true
                      })
                    }
                  >
                    <SelectTrigger className="min-w-56 justify-between">
                      <SelectValue>
                        {(value: string) =>
                          value === 'all' ? 'Todas las campañas' : value
                        }
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Todas las campañas</SelectItem>
                      {availableIncidentCampaigns.map(name => (
                        <SelectItem key={name} value={name}>
                          {name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}

              {availableIncidentAgents.length > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-muted-foreground">
                    Agente
                  </span>
                  <Select
                    value={agente}
                    onValueChange={value =>
                      navigate({
                        search: prev => ({
                          ...prev,
                          agente: value ?? 'all',
                          demorasPage: 1
                        }),
                        replace: true
                      })
                    }
                  >
                    <SelectTrigger className="min-w-56 justify-between">
                      <SelectValue>
                        {(value: string) =>
                          value === 'all' ? 'Todos los agentes' : value
                        }
                      </SelectValue>
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="all">Todos los agentes</SelectItem>
                      {availableIncidentAgents.map(name => (
                        <SelectItem key={name} value={name}>
                          {name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              )}
            </div>
          </div>

          <div
            className={cn('transition-opacity', summaryLoading && 'opacity-50')}
          >
            {!incidentAnalytics.available ? (
              <Card className="mt-4">
                <CardContent className="text-sm text-muted-foreground">
                  Todavia no se descargo ningun archivo con datos de
                  incidencias. Dispara un refresh desde{' '}
                  <Link to="/status" className="text-primary underline">
                    /status
                  </Link>
                  .
                </CardContent>
              </Card>
            ) : incidentRecords.length === 0 ? (
              <Card className="mt-4">
                <CardContent className="text-sm text-muted-foreground">
                  {agente === 'all' && campana === 'all'
                    ? 'No hay incidencias registradas todavia.'
                    : 'No hay incidencias registradas para este filtro.'}
                </CardContent>
              </Card>
            ) : (
              <Card size="sm" className="mt-4">
                <CardContent>
                  <Tabs
                    value={activeIncidentCategory}
                    onValueChange={value =>
                      navigate({
                        search: prev => ({
                          ...prev,
                          category: value as IncidentCategory
                        }),
                        replace: true
                      })
                    }
                  >
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                      <TabsList>
                        {incidentCategoryOrder.map(cat => (
                          <TabsTrigger
                            key={cat}
                            value={cat}
                            className="gap-1.5"
                          >
                            <CategorySwatch category={cat} />
                            {INCIDENT_CATEGORY_LABEL[cat]}
                          </TabsTrigger>
                        ))}
                      </TabsList>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleDownloadIncidentsJson}
                        >
                          <FileJsonIcon data-icon="inline-start" />
                          JSON
                        </Button>
                        <Button
                          variant="outline"
                          size="sm"
                          onClick={handleDownloadIncidentsPdf}
                        >
                          <FileTextIcon data-icon="inline-start" />
                          PDF
                        </Button>
                      </div>
                    </div>
                    {incidentCategoryOrder.map((cat, index) => (
                      <TabsContent key={cat} value={cat}>
                        <IncidentHierarchy
                          records={incidentRecords}
                          chain={incidentCategoryOrder.slice(index)}
                        />
                      </TabsContent>
                    ))}
                  </Tabs>
                </CardContent>
              </Card>
            )}
          </div>
        </TabsContent>

        <TabsContent value="demoras" className="mt-4">
          <p className="text-sm text-muted-foreground">
            Rotacion de atenciones por estado (abierta, asignada o cerrada) para
            la fecha seleccionada, ordenadas por cuanto tiempo llevan (o
            llevaron, si ya se cerraron) con su agente actual. Si eliges un dia
            pasado, refleja el estado al momento de la ultima descarga de ese
            dia, no necesariamente el estado actual.
          </p>

          <div className="mt-3 flex flex-wrap items-center gap-3">
            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-muted-foreground">
                Estado
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
                  {formatEstadosFilter(estados, availableEstados)}
                  <ChevronDownIcon className="size-4 text-muted-foreground" />
                </DropdownMenuTrigger>
                <DropdownMenuContent align="start">
                  {availableEstados.map(estado => (
                    <Label
                      key={estado}
                      className="cursor-default rounded-xl px-3 py-2 font-normal hover:bg-accent"
                    >
                      <Checkbox
                        checked={isEstadoChecked(estado)}
                        onCheckedChange={() => toggleEstado(estado)}
                      />
                      {estado}
                    </Label>
                  ))}
                </DropdownMenuContent>
              </DropdownMenu>
            </div>

            <div className="flex items-center gap-2">
              <span className="text-sm font-medium text-muted-foreground">
                Dirección
              </span>
              <Select
                value={direction}
                onValueChange={value =>
                  navigate({
                    search: prev => ({
                      ...prev,
                      direction: value as AttentionFilter,
                      demorasPage: 1
                    }),
                    replace: true
                  })
                }
              >
                <SelectTrigger className="w-36">
                  <SelectValue>
                    {(value: AttentionFilter) => FILTER_LABEL[value]}
                  </SelectValue>
                </SelectTrigger>
                <SelectContent>
                  {ATTENTION_FILTERS.map(filter => (
                    <SelectItem key={filter} value={filter}>
                      {FILTER_LABEL[filter]}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>

            {availableRecordCampaigns.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-muted-foreground">
                  Campaña
                </span>
                <Select
                  value={campana}
                  onValueChange={value =>
                    navigate({
                      search: prev => ({
                        ...prev,
                        campana: value ?? 'all',
                        demorasPage: 1
                      }),
                      replace: true
                    })
                  }
                >
                  <SelectTrigger className="min-w-40">
                    <SelectValue>
                      {(value: string) =>
                        value === 'all' ? 'Todas las campañas' : value
                      }
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todas las campañas</SelectItem>
                    {availableRecordCampaigns.map(name => (
                      <SelectItem key={name} value={name}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {availableRecordAgents.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-muted-foreground">
                  Agente
                </span>
                <Select
                  value={agente}
                  onValueChange={value =>
                    navigate({
                      search: prev => ({
                        ...prev,
                        agente: value ?? 'all',
                        demorasPage: 1
                      }),
                      replace: true
                    })
                  }
                >
                  <SelectTrigger className="min-w-56">
                    <SelectValue>
                      {(value: string) =>
                        value === 'all' ? 'Todos los agentes' : value
                      }
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos los agentes</SelectItem>
                    {availableRecordAgents.map(name => (
                      <SelectItem key={name} value={name}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}

            {availableRecordPlans.length > 0 && (
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-muted-foreground">
                  Plan
                </span>
                <Select
                  value={plan}
                  onValueChange={value =>
                    navigate({
                      search: prev => ({ ...prev, plan: value ?? 'all' }),
                      replace: true
                    })
                  }
                >
                  <SelectTrigger className="min-w-48">
                    <SelectValue>
                      {(value: string) =>
                        value === 'all' ? 'Todos los planes' : value
                      }
                    </SelectValue>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">Todos los planes</SelectItem>
                    {availableRecordPlans.map(name => (
                      <SelectItem key={name} value={name}>
                        {name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            )}
          </div>

          {!attentionRecordsAvailable ? (
            <Card className="mt-4">
              <CardContent className="text-sm text-muted-foreground">
                Todavia no se descargo ningun archivo de atenciones. Dispara un
                refresh desde{' '}
                <Link to="/status" className="text-primary underline">
                  /status
                </Link>
                .
              </CardContent>
            </Card>
          ) : (
            <AttentionRecordsTable
              records={filteredAttentionRecords}
              total={attentionRecordsPage.total}
              staleCount={attentionRecordsPage.staleCount}
              page={demorasPage}
              pageSize={DEMORAS_PAGE_SIZE}
              isLoading={demorasLoading}
              onPageChange={nextPage =>
                navigate({
                  search: prev => ({ ...prev, demorasPage: nextPage }),
                  replace: true
                })
              }
            />
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
