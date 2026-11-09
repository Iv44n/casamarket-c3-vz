import { useServerFn } from '@tanstack/react-start'
import { SaveIcon } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { toast } from 'sonner'
import { Button } from '#/components/ui/button'
import {
  Combobox,
  ComboboxContent,
  ComboboxEmpty,
  ComboboxInput,
  ComboboxItem,
  ComboboxList
} from '#/components/ui/combobox'
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle
} from '#/components/ui/dialog'
import { Input } from '#/components/ui/input'
import { Label } from '#/components/ui/label'
import { Textarea } from '#/components/ui/textarea'
import { useSessionUser } from '#/hooks/use-session-user'
import { INCIDENT_CATEGORY_LABEL } from '#/lib/incident-analytics'
import {
  createManualIncident,
  getIncidentClientSuggestions,
  updateManualIncident
} from '#/server/incidents.functions'
import {
  type ClientSuggestion,
  type IncidentCatalogOption,
  type IncidentCategory,
  MANUAL_INCIDENT_CATEGORY_ORDER,
  type ManualIncident,
  type ManualIncidentInput,
  todayIsoDate
} from '#/server/schemas'

// Hora actual en Lima (HH:MM) -- mismo pinning que todayIsoDate(), no el reloj local de la
// maquina.
function nowLimaTime(): string {
  return new Intl.DateTimeFormat('en-GB', {
    timeZone: 'America/Lima',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23'
  }).format(new Date())
}

const REQUIRED_CATEGORIES: ReadonlySet<IncidentCategory> = new Set([
  'origen',
  'tipo',
  'ambito'
])
function emptyForm(): ManualIncidentInput {
  return {
    fecha: todayIsoDate(),
    hora: nowLimaTime(),
    cliente: '',
    telefono: '',
    agente: '',
    origen: '',
    tipo: '',
    ambito: '',
    resultado: '',
    descripcion: ''
  }
}

function formFromIncident(incident: ManualIncident): ManualIncidentInput {
  return {
    fecha: incident.fecha,
    hora: incident.hora,
    cliente: incident.cliente,
    telefono: incident.telefono,
    agente: incident.agente,
    origen: incident.origen,
    tipo: incident.tipo,
    ambito: incident.ambito,
    resultado: incident.resultado,
    descripcion: incident.descripcion
  }
}

function CatalogCombobox({
  id,
  category,
  options,
  value,
  onChange
}: {
  id: string
  category: IncidentCategory
  options: string[]
  value: string
  onChange: (value: string) => void
}) {
  const required = REQUIRED_CATEGORIES.has(category)
  return (
    <div className="flex flex-col gap-2">
      <Label htmlFor={id}>
        {INCIDENT_CATEGORY_LABEL[category]}
        {!required && (
          <span className="font-normal text-muted-foreground">(opcional)</span>
        )}
      </Label>
      <Combobox
        items={options}
        value={value || null}
        onValueChange={next => onChange(typeof next === 'string' ? next : '')}
      >
        <ComboboxInput
          id={id}
          className="w-full"
          placeholder="Buscar..."
          showClear={!required && value !== ''}
        />
        <ComboboxContent className="w-[min(42rem,calc(100vw-4rem))]">
          <ComboboxEmpty>Sin coincidencias en el catálogo.</ComboboxEmpty>
          <ComboboxList>
            {(item: string) => (
              <ComboboxItem key={item} value={item}>
                {item}
              </ComboboxItem>
            )}
          </ComboboxList>
        </ComboboxContent>
      </Combobox>
    </div>
  )
}

// Alta y edicion de una incidencia manual. Origen/tipo/ambito/resultado salen del catalogo
// (solo opciones activas); al editar, el valor que la incidencia ya tenia se ofrece aunque un
// admin lo haya desactivado despues -- el backend acepta ese caso (incidents/store.py's
// _validate_catalog_values), asi se puede corregir la descripcion sin reclasificar.
// El form se siembra una sola vez al montar: el caller le cambia la `key` en cada apertura (alta
// o edicion de otra fila) para arrancar limpio.
export function ManualIncidentFormDialog({
  open,
  onOpenChange,
  catalog,
  incident,
  onSaved
}: {
  open: boolean
  onOpenChange: (open: boolean) => void
  catalog: IncidentCatalogOption[]
  // undefined = alta; una incidencia = edicion.
  incident?: ManualIncident
  onSaved: (incident: ManualIncident) => void
}) {
  const doCreate = useServerFn(createManualIncident)
  const doUpdate = useServerFn(updateManualIncident)
  const searchClients = useServerFn(getIncidentClientSuggestions)
  const sessionUser = useSessionUser()
  const [form, setForm] = useState<ManualIncidentInput>(() =>
    incident ? formFromIncident(incident) : emptyForm()
  )
  const [clientQuery, setClientQuery] = useState(incident?.cliente ?? '')
  const [clients, setClients] = useState<ClientSuggestion[]>([])
  const [clientsLoading, setClientsLoading] = useState(false)
  const [clientsError, setClientsError] = useState<string | null>(null)
  const [clientSelectorOpen, setClientSelectorOpen] = useState(false)
  const clientRequestId = useRef(0)
  const [pending, setPending] = useState(false)

  useEffect(() => {
    if (!incident && sessionUser?.username) {
      setForm(prev => ({ ...prev, agente: sessionUser.username }))
    }
  }, [incident, sessionUser?.username])

  const loadClients = useCallback(
    async (query: string) => {
      const requestId = ++clientRequestId.current
      setClientsLoading(true)
      setClientsError(null)
      try {
        const values = await searchClients({ data: query })
        if (requestId === clientRequestId.current) setClients(values)
      } catch (err) {
        if (requestId === clientRequestId.current) {
          setClientsError(err instanceof Error ? err.message : String(err))
        }
      } finally {
        if (requestId === clientRequestId.current) setClientsLoading(false)
      }
    },
    [searchClients]
  )

  useEffect(() => {
    const query = clientQuery.trim()
    if (!query || !clientSelectorOpen) return
    const timer = window.setTimeout(() => {
      if (clientSelectorOpen) void loadClients(query)
    }, 250)
    return () => {
      window.clearTimeout(timer)
    }
  }, [clientQuery, clientSelectorOpen, loadClients])

  const optionsByCategory = useMemo(() => {
    const result = {} as Record<IncidentCategory, string[]>
    for (const category of MANUAL_INCIDENT_CATEGORY_ORDER) {
      const values = catalog
        .filter(option => option.category === category && option.active)
        .map(option => option.value)
      const current = incident?.[category]
      if (current && !values.includes(current)) values.push(current)
      result[category] = values.sort((a, b) => a.localeCompare(b))
    }
    return result
  }, [catalog, incident])

  function setField<K extends keyof ManualIncidentInput>(
    key: K,
    value: ManualIncidentInput[K]
  ) {
    setForm(prev => ({ ...prev, [key]: value }))
  }

  function handleClientChange(value: string) {
    const selected = clients.find(
      client =>
        client.name.trim().toLocaleLowerCase() ===
        value.trim().toLocaleLowerCase()
    )
    setForm(prev => ({
      ...prev,
      cliente: value,
      ...(selected ? { telefono: selected.phone } : {})
    }))
    setClientQuery(value)
  }

  function handleClientSelectorOpenChange(open: boolean) {
    setClientSelectorOpen(open)
    if (open && clients.length === 0 && !clientsLoading) void loadClients('')
  }

  function handleClientQueryChange(value: string) {
    setClientQuery(value)
    if (!value.trim() && clientSelectorOpen) void loadClients('')
  }

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault()
    const missing = MANUAL_INCIDENT_CATEGORY_ORDER.filter(
      category => REQUIRED_CATEGORIES.has(category) && !form[category]
    )
    if (missing.length > 0) {
      toast.error(
        `Completá ${missing.map(c => INCIDENT_CATEGORY_LABEL[c].toLowerCase()).join(', ')}.`
      )
      return
    }
    if (!form.descripcion.trim()) {
      toast.error('La descripción es obligatoria.')
      return
    }
    setPending(true)
    try {
      const result = incident
        ? await doUpdate({ data: { ...form, id: incident.id } })
        : await doCreate({ data: form })
      if (result.status === 'invalid') {
        toast.error(result.message)
        return
      }
      if (result.status === 'not_found') {
        toast.error('La incidencia ya no existe (alguien la borró).')
        onOpenChange(false)
        return
      }
      toast.success(
        incident ? 'Incidencia actualizada.' : 'Incidencia registrada.'
      )
      onSaved(result.incident)
      onOpenChange(false)
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[calc(100dvh-2rem)] overflow-y-auto sm:max-w-2xl">
        <DialogHeader>
          <DialogTitle>
            {incident ? 'Editar incidencia' : 'Nueva incidencia'}
          </DialogTitle>
          <DialogDescription>
            Incidencias que no pasan por C3. La clasificación usa el catálogo de
            incidencias.
          </DialogDescription>
        </DialogHeader>
        <form className="flex flex-col gap-4" onSubmit={handleSubmit}>
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="flex flex-col gap-2">
              <Label htmlFor="incident-fecha">Fecha</Label>
              <Input
                id="incident-fecha"
                type="date"
                value={form.fecha}
                onChange={e => setField('fecha', e.target.value)}
                required
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="incident-hora">
                Hora
                <span className="font-normal text-muted-foreground">
                  (opcional)
                </span>
              </Label>
              <Input
                id="incident-hora"
                type="time"
                value={form.hora}
                onChange={e => setField('hora', e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="incident-cliente">Cliente</Label>
              <Combobox
                items={clients.map(client => client.name)}
                value={form.cliente || null}
                inputValue={clientQuery}
                onInputValueChange={handleClientQueryChange}
                onOpenChange={handleClientSelectorOpenChange}
                onValueChange={next =>
                  handleClientChange(typeof next === 'string' ? next : '')
                }
              >
                <ComboboxInput
                  id="incident-cliente"
                  className="w-full"
                  placeholder="Buscar cliente..."
                  showClear={form.cliente !== ''}
                  maxLength={200}
                />
                <ComboboxContent className="w-[min(60rem,calc(100vw-2rem))]">
                  {clientsLoading && (
                    <div className="px-3 py-2 text-sm text-muted-foreground">
                      Cargando clientes...
                    </div>
                  )}
                  {clientsError && (
                    <button
                      type="button"
                      className="w-full px-3 py-2 text-left text-sm text-destructive"
                      onClick={() => void loadClients(clientQuery.trim())}
                    >
                      No se pudieron cargar los clientes. Reintentar
                    </button>
                  )}
                  {!clientsLoading && !clientsError && (
                    <ComboboxEmpty>
                      No hay clientes que coincidan con la búsqueda.
                    </ComboboxEmpty>
                  )}
                  <ComboboxList>
                    {(item: string) => {
                      const client = clients.find(
                        option => option.name === item
                      )
                      return (
                        <ComboboxItem key={item} value={item}>
                          {item}
                          {client?.document && (
                            <span className="text-muted-foreground">
                              DNI: {client.document}
                            </span>
                          )}
                          {client?.phone && (
                            <span className="text-muted-foreground">
                              Tel: {client.phone}
                            </span>
                          )}
                          {client?.detail && (
                            <span className="text-muted-foreground">
                              {client.detail}
                            </span>
                          )}
                        </ComboboxItem>
                      )
                    }}
                  </ComboboxList>
                </ComboboxContent>
              </Combobox>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="incident-telefono">
                Teléfono
                <span className="font-normal text-muted-foreground">
                  (opcional)
                </span>
              </Label>
              <Input
                id="incident-telefono"
                inputMode="tel"
                autoComplete="off"
                maxLength={40}
                value={form.telefono}
                onChange={e => setField('telefono', e.target.value)}
              />
            </div>
            <div className="flex flex-col gap-2 sm:col-span-2">
              <Label htmlFor="incident-agente">Usuario</Label>
              <Input id="incident-agente" readOnly value={form.agente} />
            </div>
            {MANUAL_INCIDENT_CATEGORY_ORDER.map(category => (
              <CatalogCombobox
                key={category}
                id={`incident-${category}`}
                category={category}
                options={optionsByCategory[category]}
                value={form[category]}
                onChange={value => setField(category, value)}
              />
            ))}
            <div className="flex flex-col gap-2 sm:col-span-2">
              <Label htmlFor="incident-descripcion">Descripción</Label>
              <Textarea
                id="incident-descripcion"
                rows={4}
                maxLength={5000}
                value={form.descripcion}
                onChange={e => setField('descripcion', e.target.value)}
                required
              />
            </div>
          </div>
          <DialogFooter>
            <DialogClose render={<Button type="button" variant="outline" />}>
              Cancelar
            </DialogClose>
            <Button type="submit" disabled={pending}>
              <SaveIcon data-icon="inline-start" />
              {pending ? 'Guardando...' : 'Guardar'}
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  )
}
