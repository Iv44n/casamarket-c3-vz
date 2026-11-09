import { createFileRoute, useRouter } from '@tanstack/react-router'
import { useServerFn } from '@tanstack/react-start'
import {
  ChevronLeftIcon,
  ChevronRightIcon,
  PencilIcon,
  PlusIcon,
  Trash2Icon,
  TriangleAlertIcon
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { toast } from 'sonner'
import { DateRangeFilter } from '#/components/date-range-filter'
import { IncidentCatalogCard } from '#/components/incident-catalog-card'
import { IncidentHierarchy } from '#/components/incident-hierarchy'
import { ManualIncidentFormDialog } from '#/components/manual-incident-form-dialog'
import { Badge } from '#/components/ui/badge'
import { Button } from '#/components/ui/button'
import { Card, CardContent } from '#/components/ui/card'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '#/components/ui/dialog'
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
import { useSessionUser } from '#/hooks/use-session-user'
import {
  INCIDENT_CATEGORY_COLOR,
  INCIDENT_CATEGORY_LABEL
} from '#/lib/incident-analytics'
import { withoutScrollReset } from '#/lib/utils'
import {
  deleteManualIncident,
  getIncidentCatalog,
  getManualIncidents
} from '#/server/incidents.functions'
import {
  type IncidentCategory,
  type IncidentRecord,
  MANUAL_INCIDENT_CATEGORY_ORDER,
  type ManualIncident,
  type ManualIncidentView,
  manualIncidentsSearchSchema
} from '#/server/schemas'

const PAGE_SIZE = 50

export const Route = createFileRoute('/incidencias-manuales')({
  ssr: 'data-only',
  validateSearch: manualIncidentsSearchSchema,
  // Solo el rango de fechas re-dispara el loader -- cambiar de pestaña, de categoria o de
  // pagina es puramente client-side sobre las filas ya cargadas.
  loaderDeps: ({ search: { date, dateEnd } }) => ({ date, dateEnd }),
  loader: async ({ deps: { date, dateEnd } }) => {
    const [incidents, catalog] = await Promise.all([
      getManualIncidents({ data: { dateFrom: date, dateTo: dateEnd ?? date } }),
      getIncidentCatalog()
    ])
    return { incidents, catalog }
  },
  component: IncidenciasManualesPage
})

// Mismo shape que las incidencias de C3, para reusar la escalera de /atenciones tal cual.
// Campos que una incidencia manual no tiene (campaña, estado, cierre, duracion) quedan vacios.
function toIncidentRecord(incident: ManualIncident): IncidentRecord {
  return {
    categoryOrder: [...MANUAL_INCIDENT_CATEGORY_ORDER],
    origen: incident.origen,
    tipo: incident.tipo,
    ambito: incident.ambito,
    resultado: incident.resultado || 'Sin resultado',
    descripcion: incident.descripcion,
    agente: incident.agente,
    telefonoCliente: incident.telefono,
    campana: '',
    estado: '',
    fecha: incident.fecha,
    hora: incident.hora,
    horaFinal: '',
    fechaFinal: '',
    tiempoSegundos: null
  }
}

function formatFecha(fecha: string): string {
  const [year, month, day] = fecha.split('-')
  return `${day}/${month}/${year}`
}

function CategorySwatch({ category }: { category: IncidentCategory }) {
  return (
    <span
      className="size-2.5 shrink-0 rounded-sm"
      style={{ background: INCIDENT_CATEGORY_COLOR[category] }}
    />
  )
}

function IncidenciasManualesPage() {
  const { incidents, catalog } = Route.useLoaderData()
  const { date, dateEnd, view, category, page } = Route.useSearch()
  const navigate = withoutScrollReset(Route.useNavigate())
  const router = useRouter()
  const sessionUser = useSessionUser()
  const isAdmin = sessionUser?.role === 'admin'
  const doDelete = useServerFn(deleteManualIncident)
  const fetchCatalog = useServerFn(getIncidentCatalog)

  const [formOpen, setFormOpen] = useState(false)
  const [formKey, setFormKey] = useState(0)
  const [editing, setEditing] = useState<ManualIncident | undefined>()
  const [deleting, setDeleting] = useState<ManualIncident | undefined>()
  const [deletePending, setDeletePending] = useState(false)
  // El catalogo se edita desde la pestaña de admin sin recargar las incidencias: se guarda una
  // copia local que arranca con la del loader.
  const [catalogOverride, setCatalogOverride] = useState<typeof catalog>()
  const currentCatalog = catalogOverride ?? catalog

  const rows = incidents.rows
  const records = useMemo(() => rows.map(toIncidentRecord), [rows])
  const pageCount = Math.max(1, Math.ceil(rows.length / PAGE_SIZE))
  const currentPage = Math.min(page, pageCount)
  const pageRows = rows.slice(
    (currentPage - 1) * PAGE_SIZE,
    currentPage * PAGE_SIZE
  )
  const catalogIsUsable = (['origen', 'tipo', 'ambito'] as const).every(
    required =>
      currentCatalog.some(
        option => option.category === required && option.active
      )
  )
  const activeView: ManualIncidentView =
    view === 'catalogo' && !isAdmin ? 'registro' : view
  const categoryIndex = MANUAL_INCIDENT_CATEGORY_ORDER.indexOf(
    category as (typeof MANUAL_INCIDENT_CATEGORY_ORDER)[number]
  )
  const activeCategory =
    categoryIndex === -1 ? MANUAL_INCIDENT_CATEGORY_ORDER[0] : category

  function openCreate() {
    setEditing(undefined)
    setFormKey(key => key + 1)
    setFormOpen(true)
  }
  function openEdit(incident: ManualIncident) {
    setEditing(incident)
    setFormKey(key => key + 1)
    setFormOpen(true)
  }
  async function refetchCatalog() {
    try {
      setCatalogOverride(await fetchCatalog())
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    }
  }
  async function handleConfirmDelete() {
    if (!deleting) return
    setDeletePending(true)
    try {
      const deleted = await doDelete({ data: { id: deleting.id } })
      toast.success(
        deleted ? 'Incidencia borrada.' : 'La incidencia ya estaba borrada.'
      )
      setDeleting(undefined)
      await router.invalidate()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setDeletePending(false)
    }
  }

  return (
    <div>
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold">Incidencias manuales</h1>
          <p className="mt-2 max-w-lg text-sm text-muted-foreground">
            Incidencias registradas a mano, que no pasan por C3. Se clasifican
            con el mismo catálogo de origen, tipo, ámbito y resultado.
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <DateRangeFilter
            date={date}
            dateEnd={dateEnd}
            onChange={(newDate, newDateEnd) =>
              navigate({
                search: prev => ({
                  ...prev,
                  date: newDate,
                  dateEnd: newDateEnd,
                  page: 1
                }),
                replace: true
              })
            }
          />
          <Button onClick={openCreate} disabled={!catalogIsUsable}>
            <PlusIcon data-icon="inline-start" />
            Nueva incidencia
          </Button>
        </div>
      </div>

      {!catalogIsUsable && (
        <Card className="mt-6">
          <CardContent className="flex items-start gap-3 text-sm">
            <TriangleAlertIcon className="mt-0.5 size-4 shrink-0 text-destructive" />
            <p>
              El catálogo de incidencias no tiene opciones activas de origen,
              tipo y ámbito, así que todavía no se puede registrar nada.{' '}
              {isAdmin
                ? 'Importalo desde C3 en la pestaña "Catálogo".'
                : 'Pedile a un administrador que lo importe desde C3.'}
            </p>
          </CardContent>
        </Card>
      )}

      <Tabs
        className="mt-6"
        value={activeView}
        onValueChange={value =>
          navigate({
            search: prev => ({ ...prev, view: value as ManualIncidentView }),
            replace: true
          })
        }
      >
        <TabsList>
          <TabsTrigger value="registro">Registro</TabsTrigger>
          <TabsTrigger value="resumen">Resumen</TabsTrigger>
          {isAdmin && <TabsTrigger value="catalogo">Catálogo</TabsTrigger>}
        </TabsList>

        <TabsContent value="registro" className="mt-4">
          <p className="text-sm text-muted-foreground">
            {rows.length === 1
              ? '1 incidencia en el rango.'
              : `${rows.length} incidencias en el rango.`}
            {incidents.truncated &&
              ' Hay más incidencias de las que se pueden mostrar: acotá el rango de fechas.'}
          </p>
          {rows.length === 0 ? (
            <Card className="mt-4">
              <CardContent className="text-sm text-muted-foreground">
                No hay incidencias registradas para estas fechas.
              </CardContent>
            </Card>
          ) : (
            <Card className="mt-4">
              <CardContent>
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>Fecha</TableHead>
                      <TableHead>Cliente</TableHead>
                      <TableHead>Clasificación</TableHead>
                      <TableHead>Descripción</TableHead>
                      <TableHead>Registrado por</TableHead>
                      <TableHead className="text-right">
                        <span className="sr-only">Acciones</span>
                      </TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {pageRows.map(incident => (
                      <TableRow key={incident.id}>
                        <TableCell className="align-top whitespace-nowrap tabular-nums">
                          <div>{formatFecha(incident.fecha)}</div>
                          {incident.hora && (
                            <div className="text-muted-foreground text-xs">
                              {incident.hora}
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="align-top">
                          <div
                            className="max-w-40 truncate"
                            title={incident.cliente}
                          >
                            {incident.cliente || (
                              <span className="text-muted-foreground">—</span>
                            )}
                          </div>
                          {incident.telefono && (
                            <div className="text-muted-foreground text-xs tabular-nums">
                              {incident.telefono}
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="align-top">
                          <div className="flex max-w-64 flex-col gap-0.5 text-xs">
                            {MANUAL_INCIDENT_CATEGORY_ORDER.map(cat =>
                              incident[cat] ? (
                                <span
                                  key={cat}
                                  className="flex items-center gap-1.5"
                                  title={`${INCIDENT_CATEGORY_LABEL[cat]}: ${incident[cat]}`}
                                >
                                  <CategorySwatch category={cat} />
                                  <span className="truncate">
                                    {incident[cat]}
                                  </span>
                                </span>
                              ) : null
                            )}
                          </div>
                        </TableCell>
                        <TableCell className="align-top">
                          <p className="line-clamp-3 max-w-md text-sm whitespace-normal">
                            {incident.descripcion}
                          </p>
                          {incident.agente && (
                            <p className="mt-0.5 text-muted-foreground text-xs">
                              Agente: {incident.agente}
                            </p>
                          )}
                        </TableCell>
                        <TableCell className="align-top text-sm">
                          <div>{incident.created_by}</div>
                          {incident.updated_by && (
                            <div className="text-muted-foreground text-xs">
                              Editada por {incident.updated_by}
                            </div>
                          )}
                        </TableCell>
                        <TableCell className="align-top">
                          <div className="flex justify-end gap-1">
                            <Tooltip>
                              <TooltipTrigger
                                render={
                                  <Button
                                    variant="ghost"
                                    size="icon-sm"
                                    aria-label="Editar incidencia"
                                    onClick={() => openEdit(incident)}
                                  />
                                }
                              >
                                <PencilIcon />
                              </TooltipTrigger>
                              <TooltipContent>Editar</TooltipContent>
                            </Tooltip>
                            <Tooltip>
                              <TooltipTrigger
                                render={
                                  <Button
                                    variant="ghost"
                                    size="icon-sm"
                                    aria-label="Borrar incidencia"
                                    onClick={() => setDeleting(incident)}
                                  />
                                }
                              >
                                <Trash2Icon />
                              </TooltipTrigger>
                              <TooltipContent>Borrar</TooltipContent>
                            </Tooltip>
                          </div>
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
                {pageCount > 1 && (
                  <div className="mt-4 flex items-center justify-end gap-2 text-sm">
                    <span className="text-muted-foreground">
                      Página {currentPage} de {pageCount}
                    </span>
                    <Button
                      variant="outline"
                      size="icon-sm"
                      aria-label="Página anterior"
                      disabled={currentPage <= 1}
                      onClick={() =>
                        navigate({
                          search: prev => ({ ...prev, page: currentPage - 1 }),
                          replace: true
                        })
                      }
                    >
                      <ChevronLeftIcon />
                    </Button>
                    <Button
                      variant="outline"
                      size="icon-sm"
                      aria-label="Página siguiente"
                      disabled={currentPage >= pageCount}
                      onClick={() =>
                        navigate({
                          search: prev => ({ ...prev, page: currentPage + 1 }),
                          replace: true
                        })
                      }
                    >
                      <ChevronRightIcon />
                    </Button>
                  </div>
                )}
              </CardContent>
            </Card>
          )}
        </TabsContent>

        <TabsContent value="resumen" className="mt-4">
          {records.length === 0 ? (
            <Card>
              <CardContent className="text-sm text-muted-foreground">
                No hay incidencias registradas para estas fechas.
              </CardContent>
            </Card>
          ) : (
            <>
              <p className="text-sm text-muted-foreground">
                {records.length === 1
                  ? '1 incidencia'
                  : `${records.length} incidencias`}{' '}
                -- haz clic en una barra para ver su desglose, hasta llegar al
                ticket.
              </p>
              <Card size="sm" className="mt-4">
                <CardContent>
                  <Tabs
                    value={activeCategory}
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
                      {MANUAL_INCIDENT_CATEGORY_ORDER.map(cat => (
                        <TabsTrigger key={cat} value={cat} className="gap-1.5">
                          <CategorySwatch category={cat} />
                          {INCIDENT_CATEGORY_LABEL[cat]}
                        </TabsTrigger>
                      ))}
                    </TabsList>
                    {MANUAL_INCIDENT_CATEGORY_ORDER.map((cat, index) => (
                      <TabsContent key={cat} value={cat}>
                        <IncidentHierarchy
                          records={records}
                          chain={MANUAL_INCIDENT_CATEGORY_ORDER.slice(index)}
                        />
                      </TabsContent>
                    ))}
                  </Tabs>
                </CardContent>
              </Card>
            </>
          )}
        </TabsContent>

        {isAdmin && (
          <TabsContent value="catalogo" className="mt-4">
            <IncidentCatalogCard
              catalog={currentCatalog}
              onChanged={refetchCatalog}
            />
          </TabsContent>
        )}
      </Tabs>

      <ManualIncidentFormDialog
        key={formKey}
        open={formOpen}
        onOpenChange={setFormOpen}
        catalog={currentCatalog}
        incident={editing}
        onSaved={() => router.invalidate()}
      />

      <Dialog
        open={deleting !== undefined}
        onOpenChange={open => {
          if (!open) setDeleting(undefined)
        }}
      >
        <DialogContent>
          <DialogHeader>
            <DialogTitle>¿Borrar esta incidencia?</DialogTitle>
            <DialogDescription>
              Deja de aparecer en el registro y en el resumen para todos los
              usuarios.
            </DialogDescription>
          </DialogHeader>
          {deleting && (
            <div className="rounded-xl bg-foreground/3 p-3 text-sm">
              <div className="flex flex-wrap items-center gap-2 text-muted-foreground text-xs">
                <span className="tabular-nums">
                  {formatFecha(deleting.fecha)} {deleting.hora}
                </span>
                {deleting.cliente && (
                  <Badge variant="secondary">{deleting.cliente}</Badge>
                )}
              </div>
              <p className="mt-1 line-clamp-3">{deleting.descripcion}</p>
            </div>
          )}
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" />}>
              Cancelar
            </DialogClose>
            <Button
              variant="destructive"
              onClick={handleConfirmDelete}
              disabled={deletePending}
            >
              <Trash2Icon data-icon="inline-start" />
              {deletePending ? 'Borrando...' : 'Borrar'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  )
}
