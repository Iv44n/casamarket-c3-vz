import { useServerFn } from '@tanstack/react-start'
import { SaveIcon } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
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
import { INCIDENT_CATEGORY_LABEL } from '#/lib/incident-analytics'
import {
  createManualIncident,
  getIncidentAgentSuggestions,
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
const LAST_AGENT_STORAGE_KEY = 'c3-panel:last-manual-incident-agent'

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
        <ComboboxContent>
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
  const fetchAgents = useServerFn(getIncidentAgentSuggestions)
  const searchClients = useServerFn(getIncidentClientSuggestions)
  const [form, setForm] = useState<ManualIncidentInput>(() =>
    incident ? formFromIncident(incident) : emptyForm()
  )
  const [agents, setAgents] = useState<string[]>([])
  const [clients, setClients] = useState<ClientSuggestion[]>([])
  const [pending, setPending] = useState(false)

  useEffect(() => {
    let active = true
    fetchAgents()
      .then(values => {
        if (active) setAgents(values)
      })
      .catch(err => {
        if (active)
          toast.error(err instanceof Error ? err.message : String(err))
      })
    if (!incident) {
      const savedAgent = window.localStorage.getItem(LAST_AGENT_STORAGE_KEY)
      if (savedAgent) {
        setForm(prev => ({ ...prev, agente: savedAgent }))
      }
    }
    return () => {
      active = false
    }
  }, [fetchAgents, incident])

  useEffect(() => {
    const query = form.cliente.trim()
    if (query.length < 2 && !/\d/.test(query)) {
      setClients([])
      return
    }
    let active = true
    const timer = window.setTimeout(() => {
      searchClients({ data: query })
        .then(values => {
          if (active) setClients(values)
        })
        .catch(err => {
          if (active)
            toast.error(err instanceof Error ? err.message : String(err))
        })
    }, 250)
    return () => {
      active = false
      window.clearTimeout(timer)
    }
  }, [form.cliente, searchClients])

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
  }

  function handleAgentChange(value: string) {
    setField('agente', value)
    if (value.trim()) window.localStorage.setItem(LAST_AGENT_STORAGE_KEY, value)
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
              <Input
                id="incident-cliente"
                placeholder="Nombre o empresa"
                autoComplete="off"
                maxLength={200}
                list="incident-client-suggestions"
                value={form.cliente}
                onChange={e => handleClientChange(e.target.value)}
              />
              <datalist id="incident-client-suggestions">
                {clients.map(client => (
                  <option
                    key={`${client.name}-${client.phone}`}
                    value={client.name}
                  >
                    {client.detail}
                  </option>
                ))}
              </datalist>
            </div>
            <div className="flex flex-col gap-2">
              <Label htmlFor="incident-telefono">Teléfono</Label>
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
              <Label htmlFor="incident-agente">Agente</Label>
              <Input
                id="incident-agente"
                placeholder="Quién atendió"
                autoComplete="off"
                maxLength={120}
                list="incident-agent-suggestions"
                value={form.agente}
                onChange={e => handleAgentChange(e.target.value)}
              />
              <datalist id="incident-agent-suggestions">
                {agents.map(agent => (
                  <option key={agent} value={agent} />
                ))}
              </datalist>
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
