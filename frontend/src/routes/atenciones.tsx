import { createFileRoute, Link } from '@tanstack/react-router'
import { AgentWorkloadChart } from '#/components/agent-workload-chart'
import { StatusDonutChart } from '#/components/status-donut-chart'
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle
} from '#/components/ui/card'
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue
} from '#/components/ui/select'
import {
  buildAgentRanking,
  buildStatusChartData,
  describeAvailability
} from '#/lib/attentions-analytics'
import { cn } from '#/lib/utils'
import { getAttentionsAnalytics } from '#/server/reports.functions'
import {
  ATTENTION_FILTERS,
  type AttentionFilter,
  attentionsSearchSchema
} from '#/server/schemas'

const FILTER_LABEL: Record<AttentionFilter, string> = {
  all: 'Todas',
  incoming: 'Entrantes',
  outgoing: 'Salientes'
}
export const Route = createFileRoute('/atenciones')({
  ssr: 'data-only',
  validateSearch: attentionsSearchSchema,
  loader: () => getAttentionsAnalytics(),
  component: AtencionesPage
})
function AtencionesPage() {
  const analytics = Route.useLoaderData()
  const { direction } = Route.useSearch()
  const navigate = Route.useNavigate()
  const { total, slices } = buildStatusChartData(analytics, direction)
  const agents = buildAgentRanking(analytics, direction)
  const { blockedMessage, advisoryMessage } = describeAvailability(
    analytics,
    direction
  )
  return (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex shrink-0 flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Atenciones</h1>
          <p className="mt-2 text-sm text-muted-foreground">
            Distribucion por estado y carga por agente de las atenciones de
            WhatsApp del ultimo archivo descargado.
          </p>
        </div>

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

      {blockedMessage ? (
        <Card className="mt-8">
          <CardContent className="text-sm text-muted-foreground">
            {blockedMessage} Dispara un refresh desde{' '}
            <Link to="/status" className="text-primary underline">
              /status
            </Link>
            .
          </CardContent>
        </Card>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          {advisoryMessage && (
            <p className="mt-4 shrink-0 text-sm text-muted-foreground">
              {advisoryMessage} Dispara un refresh desde{' '}
              <Link to="/status" className="text-primary underline">
                /status
              </Link>
              .
            </p>
          )}

          <div
            className={cn(
              'grid min-h-0 flex-1 grid-cols-1 gap-4 lg:grid-cols-2',
              advisoryMessage ? 'mt-4' : 'mt-8'
            )}
          >
            <section
              aria-labelledby="distribucion-por-estado"
              className="flex min-h-0 flex-col"
            >
              <h2
                id="distribucion-por-estado"
                className="shrink-0 text-lg font-semibold"
              >
                Distribucion por estado
              </h2>

              <Card className="mt-4 flex min-h-0 flex-1 flex-col">
                <CardHeader className="shrink-0">
                  <CardTitle>Estado de atenciones</CardTitle>
                  <CardDescription>{total} atenciones</CardDescription>
                </CardHeader>
                <CardContent className="min-h-0 flex-1">
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
              aria-labelledby="atenciones-por-agente"
              className="flex min-h-0 flex-col"
            >
              <h2
                id="atenciones-por-agente"
                className="shrink-0 text-lg font-semibold"
              >
                Atenciones por agente
              </h2>

              <Card className="mt-4 flex min-h-0 flex-1 flex-col">
                <CardHeader className="shrink-0">
                  <CardTitle>Top 10 agentes</CardTitle>
                  <CardDescription>Carga de trabajo diaria</CardDescription>
                </CardHeader>
                <CardContent className="min-h-0 flex-1">
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
    </div>
  )
}
