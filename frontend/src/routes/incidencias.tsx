import { createFileRoute, Link } from '@tanstack/react-router'
import { z } from 'zod'
import { IncidentCategoryChart } from '#/components/incident-category-chart'
import { Card, CardContent, CardHeader, CardTitle } from '#/components/ui/card'
import { Tabs, TabsContent, TabsList, TabsTrigger } from '#/components/ui/tabs'
import {
  INCIDENT_CATEGORY_COLOR,
  INCIDENT_CATEGORY_LABEL
} from '#/lib/incident-analytics'
import { getIncidentAnalytics } from '#/server/reports.functions'
import { INCIDENT_CATEGORIES, type IncidentCategory } from '#/server/schemas'

const incidenciasSearchSchema = z.object({
  category: z.enum(INCIDENT_CATEGORIES).default('origen')
})
export const Route = createFileRoute('/incidencias')({
  ssr: 'data-only',
  validateSearch: incidenciasSearchSchema,
  loader: () => getIncidentAnalytics(),
  component: IncidenciasPage
})
function CategorySwatch({ category }: { category: IncidentCategory }) {
  return (
    <span
      className="size-2.5 shrink-0 rounded-sm"
      style={{ background: INCIDENT_CATEGORY_COLOR[category] }}
    />
  )
}
function IncidenciasPage() {
  const analytics = Route.useLoaderData()
  const { category } = Route.useSearch()
  const navigate = Route.useNavigate()
  return (
    <div>
      <h1 className="text-2xl font-bold tracking-tight">
        Clasificacion de incidencias
      </h1>
      <p className="mt-2 text-sm text-muted-foreground">
        {analytics.total} incidencias registradas en atenciones y llamadas
        salientes.
      </p>

      {!analytics.available ? (
        <Card className="mt-8">
          <CardContent className="text-sm text-muted-foreground">
            Todavia no se descargo ningun archivo con datos de incidencias.
            Dispara un refresh desde{' '}
            <Link to="/status" className="text-primary underline">
              /status
            </Link>
            .
          </CardContent>
        </Card>
      ) : (
        <Card className="mt-6">
          <CardHeader>
            <CardTitle className="flex items-center gap-1.5">
              <CategorySwatch category={category} />
              {INCIDENT_CATEGORY_LABEL[category]} de incidencia
            </CardTitle>
          </CardHeader>
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
                  {analytics.counts[cat].length === 0 ? (
                    <p className="text-sm text-muted-foreground">
                      Sin registros.
                    </p>
                  ) : (
                    <IncidentCategoryChart
                      data={analytics.counts[cat]}
                      color={INCIDENT_CATEGORY_COLOR[cat]}
                    />
                  )}
                </TabsContent>
              ))}
            </Tabs>
          </CardContent>
        </Card>
      )}
    </div>
  )
}
