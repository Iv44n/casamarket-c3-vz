import { createFileRoute, Link, useRouter } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import {
  CalendarIcon,
  ChevronDownIcon,
  RefreshCwIcon,
  XIcon
} from 'lucide-react'
import { useState } from 'react'
import type { DateRange } from 'react-day-picker'
import { es } from 'react-day-picker/locale'
import { toast } from 'sonner'
import { AgentWorkloadChart } from '#/components/agent-workload-chart'
import { AttentionRecordsTable } from '#/components/attention-records-table'
import { CampaignWorkloadChart } from '#/components/campaign-workload-chart'
import { IncidentHierarchy } from '#/components/incident-hierarchy'
import { StatusDonutChart } from '#/components/status-donut-chart'
import { Badge } from '#/components/ui/badge'
import { Button } from '#/components/ui/button'
import { Calendar } from '#/components/ui/calendar'
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
  Popover,
  PopoverContent,
  PopoverTrigger
} from '#/components/ui/popover'
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
  buildStatusChartData,
  buildTopClosers,
  describeAvailability,
  getAvailableEstados
} from '#/lib/attentions-analytics'
import {
  INCIDENT_CATEGORY_COLOR,
  INCIDENT_CATEGORY_LABEL,
  pickDominantCategoryOrder
} from '#/lib/incident-analytics'
import { cn } from '#/lib/utils'
import {
  getAttentionsAnalytics,
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
function toIsoDateLocal(date: Date): string {
  const year = date.getFullYear()
  const month = String(date.getMonth() + 1).padStart(2, '0')
  const day = String(date.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}
const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/
function parseIsoDateLocal(value: string): Date | undefined {
  const match = ISO_DATE.exec(value)
  if (!match) return undefined
  const [, year, month, day] = match
  return new Date(Number(year), Number(month) - 1, Number(day))
}
export const Route = createFileRoute('/atenciones')({
  ssr: 'data-only',
  validateSearch: attentionsSearchSchema,
  loaderDeps: ({ search }) => ({
    date: search.date,
    dateEnd: search.dateEnd
  }),
  loader: async ({ deps }) => {
    const [attentions, incidents] = await Promise.all([
      getAttentionsAnalytics({ data: deps }),
      getIncidentAnalytics({ data: deps })
    ])
    return { attentions, incidents }
  },
  component: AtencionesPage
})
function AtencionesPage() {
  const { attentions: analytics, incidents: incidentAnalytics } =
    Route.useLoaderData()
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
    dateEnd
  } = Route.useSearch()
  const navigate = Route.useNavigate()
  const router = useRouter()
  const refresh = useServerFn(triggerRefresh)
  const backfill = useServerFn(triggerBackfill)
  const [pending, setPending] = useState(false)
  const availableEstados = getAvailableEstados(analytics)
  const { total, slices } = buildStatusChartData(analytics, direction, estados)
  const agents = buildAgentRanking(analytics, direction, agentLimit, estados)
  const topClosers = buildTopClosers(analytics)
  const campaigns = buildCampaignRanking(analytics, direction, estados)
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
  const allAttentionRecords = [
    ...analytics.incoming.attentionRecords,
    ...analytics.outgoing.attentionRecords
  ]
  const availableRecordCampaigns = [
    ...new Set(allAttentionRecords.map(record => record.campana))
  ].sort((a, b) => a.localeCompare(b))
  const availableRecordAgents = [
    ...new Set(allAttentionRecords.map(record => record.agente))
  ].sort((a, b) => a.localeCompare(b))
  const availableRecordPlans = [
    ...new Set(allAttentionRecords.map(record => planLabel(record.plan)))
  ].sort((a, b) => a.localeCompare(b))
  const filteredAttentionRecords = allAttentionRecords.filter(
    record =>
      (direction === 'all' || record.direction === direction) &&
      (campana === 'all' || record.campana === campana) &&
      (agente === 'all' || record.agente === agente) &&
      (plan === 'all' || planLabel(record.plan) === plan) &&
      (estados === 'all' || estados.includes(record.estado))
  )
  const isRangeSelected = date !== 'all' && Boolean(dateEnd) && dateEnd !== date
  const isPastDaySelected =
    date !== 'all' && !isRangeSelected && date !== todayIsoDate()
  const committedRange: DateRange | undefined =
    date === 'all'
      ? undefined
      : {
          from: parseIsoDateLocal(date),
          to: dateEnd ? parseIsoDateLocal(dateEnd) : parseIsoDateLocal(date)
        }
  const [pendingRange, setPendingRange] = useState<DateRange | undefined>(
    committedRange
  )
  function commitDateRange(from: Date, to: Date) {
    const fromIso = toIsoDateLocal(from)
    const toIso = toIsoDateLocal(to)
    navigate({
      search: prev => ({
        ...prev,
        date: fromIso,
        dateEnd: toIso !== fromIso ? toIso : undefined
      }),
      replace: true
    })
  }
  function handlePendingRangeSelect(next: DateRange | undefined) {
    setPendingRange(next)
    if (!next?.from) {
      navigate({
        search: prev => ({ ...prev, date: 'all', dateEnd: undefined }),
        replace: true
      })
      return
    }
    if (!next.to) return
    commitDateRange(next.from, next.to)
  }
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
      await router.invalidate()
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
      search: prev => ({ ...prev, estados: next }),
      replace: true
    })
  }
  function goToAgentIncidents(clickedAgent: string) {
    navigate({
      search: prev => ({
        ...prev,
        view: 'incidencias',
        agente: clickedAgent
      }),
      replace: true
    })
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
          <div className="flex items-center gap-1">
            <Popover
              onOpenChange={open => {
                if (open) setPendingRange(committedRange)
              }}
            >
              <PopoverTrigger
                render={<Button variant="outline" className="font-normal" />}
              >
                <CalendarIcon data-icon="inline-start" />
                {date === 'all'
                  ? 'Elegir fecha'
                  : isRangeSelected
                    ? `${date} — ${dateEnd}`
                    : date}
              </PopoverTrigger>
              <PopoverContent className="w-auto p-0">
                <Calendar
                  mode="range"
                  numberOfMonths={2}
                  resetOnSelect
                  selected={pendingRange}
                  onSelect={handlePendingRangeSelect}
                  disabled={{ after: new Date() }}
                  locale={es}
                />
                <p className="px-3 pb-2 text-xs text-muted-foreground">
                  Elegi el primer y el segundo dia para un rango, o el mismo dia
                  dos veces para un solo dia.
                </p>
              </PopoverContent>
            </Popover>
            {date !== 'all' && (
              <Button
                variant="ghost"
                size="icon-sm"
                aria-label="Quitar filtro de fecha"
                onClick={() =>
                  navigate({
                    search: prev => ({
                      ...prev,
                      date: 'all',
                      dateEnd: undefined
                    }),
                    replace: true
                  })
                }
              >
                <XIcon />
              </Button>
            )}
          </div>

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
                      direction: value as AttentionFilter
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

              <div className="grid grid-cols-1 gap-4 lg:grid-cols-2">
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
                        search: prev => ({ ...prev, campana: value ?? 'all' }),
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
                        search: prev => ({ ...prev, agente: value ?? 'all' }),
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

          {!incidentAnalytics.available ? (
            <Card className="mt-4">
              <CardContent className="text-sm text-muted-foreground">
                Todavia no se descargo ningun archivo con datos de incidencias.
                Dispara un refresh desde{' '}
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
                  <TabsList className="mb-4">
                    {incidentCategoryOrder.map(cat => (
                      <TabsTrigger key={cat} value={cat} className="gap-1.5">
                        <CategorySwatch category={cat} />
                        {INCIDENT_CATEGORY_LABEL[cat]}
                      </TabsTrigger>
                    ))}
                  </TabsList>
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
                      direction: value as AttentionFilter
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
                      search: prev => ({ ...prev, campana: value ?? 'all' }),
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
                      search: prev => ({ ...prev, agente: value ?? 'all' }),
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
            <AttentionRecordsTable records={filteredAttentionRecords} />
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
