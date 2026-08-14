import { createFileRoute, Link, useRouter } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import { ChevronDownIcon, RefreshCwIcon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
import { AgentWorkloadChart } from '#/components/agent-workload-chart'
import { CampaignWorkloadChart } from '#/components/campaign-workload-chart'
import { IncidentHierarchy } from '#/components/incident-hierarchy'
import { StatusDonutChart } from '#/components/status-donut-chart'
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
  describeAvailability,
  getAvailableEstados
} from '#/lib/attentions-analytics'
import {
  INCIDENT_CATEGORY_COLOR,
  INCIDENT_CATEGORY_LABEL
} from '#/lib/incident-analytics'
import { cn } from '#/lib/utils'
import {
  getAttentionsAnalytics,
  getIncidentAnalytics,
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
  INCIDENT_CATEGORIES,
  type IncidentCategory
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
export const Route = createFileRoute('/atenciones')({
  ssr: 'data-only',
  validateSearch: attentionsSearchSchema,
  loader: async () => {
    const [attentions, incidents] = await Promise.all([
      getAttentionsAnalytics(),
      getIncidentAnalytics()
    ])
    return { attentions, incidents }
  },
  component: AtencionesPage
})
function AtencionesPage() {
  const { attentions: analytics, incidents: incidentAnalytics } =
    Route.useLoaderData()
  const { direction, agentLimit, estados, view, category } = Route.useSearch()
  const navigate = Route.useNavigate()
  const router = useRouter()
  const refresh = useServerFn(triggerRefresh)
  const [pending, setPending] = useState(false)
  const availableEstados = getAvailableEstados(analytics)
  const { total, slices } = buildStatusChartData(analytics, direction, estados)
  const agents = buildAgentRanking(analytics, direction, agentLimit, estados)
  const campaigns = buildCampaignRanking(analytics, direction, estados)
  const { blockedMessage, advisoryMessage } = describeAvailability(
    analytics,
    direction
  )
  async function handleRefresh() {
    setPending(true)
    try {
      await refresh()
      await router.invalidate()
      toast.success('Extraccion completada')
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

        {view === 'resumen' && (
          <div className="flex items-center gap-2">
            <Button
              onClick={handleRefresh}
              disabled={pending}
              variant="outline"
            >
              <RefreshCwIcon
                data-icon="inline-start"
                className={cn(pending && 'animate-spin')}
              />
              {pending ? 'Corriendo...' : 'Refresh ahora'}
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
          </div>
        )}
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
                    </CardHeader>
                    <CardContent className="flex flex-1 items-center">
                      {agents.length === 0 ? (
                        <p className="text-sm text-muted-foreground">
                          Sin registros.
                        </p>
                      ) : (
                        <AgentWorkloadChart agents={agents} />
                      )}
                    </CardContent>
                  </Card>
                </section>
              </div>
            </div>
          )}
        </TabsContent>

        <TabsContent value="incidencias" className="mt-4">
          <p className="text-sm text-muted-foreground">
            {incidentAnalytics.total} incidencias registradas en atenciones y
            llamadas salientes -- haz clic en una barra para ver su desglose.
          </p>

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
          ) : incidentAnalytics.total === 0 ? (
            <Card className="mt-4">
              <CardContent className="text-sm text-muted-foreground">
                No hay incidencias registradas todavia.
              </CardContent>
            </Card>
          ) : (
            <Card size="sm" className="mt-4">
              <CardContent>
                <Tabs
                  value={category}
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
                    {INCIDENT_CATEGORIES.map(cat => (
                      <TabsTrigger key={cat} value={cat} className="gap-1.5">
                        <CategorySwatch category={cat} />
                        {INCIDENT_CATEGORY_LABEL[cat]}
                      </TabsTrigger>
                    ))}
                  </TabsList>
                  {INCIDENT_CATEGORIES.map(cat => (
                    <TabsContent key={cat} value={cat}>
                      <IncidentHierarchy
                        records={incidentAnalytics.records}
                        dimension={cat}
                      />
                    </TabsContent>
                  ))}
                </Tabs>
              </CardContent>
            </Card>
          )}
        </TabsContent>
      </Tabs>
    </div>
  )
}
