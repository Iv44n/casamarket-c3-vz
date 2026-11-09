import { useServerFn } from '@tanstack/react-start'
import { DownloadIcon, PlusIcon } from 'lucide-react'
import { useState } from 'react'
import { toast } from 'sonner'
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
import { Input } from '#/components/ui/input'
import { Switch } from '#/components/ui/switch'
import {
  INCIDENT_CATEGORY_COLOR,
  INCIDENT_CATEGORY_LABEL
} from '#/lib/incident-analytics'
import {
  addCatalogOption,
  importCatalogFromC3,
  setCatalogOptionActive
} from '#/server/incidents.functions'
import {
  type IncidentCatalogOption,
  type IncidentCategory,
  MANUAL_INCIDENT_CATEGORY_ORDER
} from '#/server/schemas'

function CategoryOptions({
  category,
  options,
  onChanged
}: {
  category: IncidentCategory
  options: IncidentCatalogOption[]
  onChanged: () => Promise<void>
}) {
  const doAdd = useServerFn(addCatalogOption)
  const doSetActive = useServerFn(setCatalogOptionActive)
  const [newValue, setNewValue] = useState('')
  const [pending, setPending] = useState(false)
  const [filter, setFilter] = useState('')
  const activeCount = options.filter(option => option.active).length
  const normalizedFilter = filter.trim().toLowerCase()
  const visible = normalizedFilter
    ? options.filter(option =>
        option.value.toLowerCase().includes(normalizedFilter)
      )
    : options

  async function handleAdd(event: React.FormEvent) {
    event.preventDefault()
    const value = newValue.trim()
    if (!value) return
    setPending(true)
    try {
      const result = await doAdd({ data: { category, value } })
      if (result.status === 'error') {
        toast.error(result.message)
        return
      }
      toast.success(`"${result.option.value}" agregado.`)
      setNewValue('')
      await onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setPending(false)
    }
  }

  async function handleToggle(option: IncidentCatalogOption, active: boolean) {
    try {
      const result = await doSetActive({ data: { id: option.id, active } })
      if (result.status === 'error') {
        toast.error(result.message)
        return
      }
      await onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    }
  }

  return (
    <div className="flex flex-col gap-3 rounded-2xl border p-4">
      <div className="flex items-center justify-between gap-2">
        <h3 className="flex items-center gap-2 font-medium">
          <span
            className="size-2.5 rounded-sm"
            style={{ background: INCIDENT_CATEGORY_COLOR[category] }}
          />
          {INCIDENT_CATEGORY_LABEL[category]}
        </h3>
        <span className="text-muted-foreground text-xs">
          {activeCount} activas de {options.length}
        </span>
      </div>
      <form className="flex gap-2" onSubmit={handleAdd}>
        <Input
          aria-label={`Nueva opción de ${INCIDENT_CATEGORY_LABEL[category]}`}
          placeholder="Nueva opción"
          maxLength={200}
          value={newValue}
          onChange={e => setNewValue(e.target.value)}
        />
        <Button
          type="submit"
          size="icon"
          variant="outline"
          disabled={pending || !newValue.trim()}
          aria-label="Agregar opción"
        >
          <PlusIcon />
        </Button>
      </form>
      {options.length > 8 && (
        <Input
          aria-label={`Filtrar ${INCIDENT_CATEGORY_LABEL[category]}`}
          placeholder="Filtrar..."
          value={filter}
          onChange={e => setFilter(e.target.value)}
        />
      )}
      <ul className="flex max-h-72 flex-col gap-0.5 overflow-y-auto">
        {visible.length === 0 && (
          <li className="px-2 py-1.5 text-muted-foreground text-sm">
            {options.length === 0
              ? 'Sin opciones todavía.'
              : 'Sin coincidencias.'}
          </li>
        )}
        {visible.map(option => (
          <li
            key={option.id}
            className="flex items-center justify-between gap-2 rounded-lg px-2 py-1.5 hover:bg-foreground/4"
          >
            <span
              className={
                option.active
                  ? 'text-sm'
                  : 'text-muted-foreground text-sm line-through'
              }
            >
              {option.value}
            </span>
            <span className="flex shrink-0 items-center gap-2">
              {option.source === 'manual' && (
                <Badge variant="secondary">Manual</Badge>
              )}
              <Switch
                checked={option.active}
                onCheckedChange={checked => handleToggle(option, checked)}
                aria-label={
                  option.active
                    ? `Desactivar ${option.value}`
                    : `Activar ${option.value}`
                }
              />
            </span>
          </li>
        ))}
      </ul>
    </div>
  )
}

// Catalogo de valores para clasificar incidencias manuales -- solo admins (el backend tambien
// lo exige: require_admin en POST/PATCH /incidents/catalog*). Desactivar una opcion la saca del
// formulario sin tocar las incidencias que ya la usan; no hay renombrar a proposito (obligaria a
// decidir si se reescribe el historial).
export function IncidentCatalogCard({
  catalog,
  onChanged
}: {
  catalog: IncidentCatalogOption[]
  onChanged: () => Promise<void>
}) {
  const doImport = useServerFn(importCatalogFromC3)
  const [importing, setImporting] = useState(false)

  async function handleImport() {
    setImporting(true)
    try {
      const { added } = await doImport()
      toast.success(
        added === 0
          ? 'El catálogo ya tenía todos los valores de C3.'
          : `${added} valores nuevos importados desde C3.`
      )
      await onChanged()
    } catch (err) {
      toast.error(err instanceof Error ? err.message : String(err))
    } finally {
      setImporting(false)
    }
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Catálogo de incidencias</CardTitle>
        <CardDescription>
          Las opciones activas son las que aparecen en el formulario. "Importar
          desde C3" agrega los valores que ya usan las atenciones de C3 y nunca
          reactiva una opción desactivada.
        </CardDescription>
        <CardAction>
          <Button variant="outline" onClick={handleImport} disabled={importing}>
            <DownloadIcon data-icon="inline-start" />
            {importing ? 'Importando...' : 'Importar desde C3'}
          </Button>
        </CardAction>
      </CardHeader>
      <CardContent className="grid gap-4 md:grid-cols-2">
        {MANUAL_INCIDENT_CATEGORY_ORDER.map(category => (
          <CategoryOptions
            key={category}
            category={category}
            options={catalog.filter(option => option.category === category)}
            onChanged={onChanged}
          />
        ))}
      </CardContent>
    </Card>
  )
}
