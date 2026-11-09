import { createServerFn } from '@tanstack/react-start'
import {
  addCatalogOptionOnBackend,
  createManualIncidentOnBackend,
  deleteManualIncidentOnBackend,
  fetchIncidentAgentSuggestions,
  fetchIncidentCatalog,
  fetchIncidentClientSuggestions,
  fetchManualIncidents,
  importCatalogFromC3OnBackend,
  setCatalogOptionActiveOnBackend,
  updateManualIncidentOnBackend
} from './backend.server'
import {
  catalogOptionCreateSchema,
  catalogOptionUpdateSchema,
  manualIncidentIdSchema,
  manualIncidentInputSchema,
  manualIncidentsRangeSchema,
  manualIncidentUpdateSchema
} from './schemas'

// Wrappers de la seccion /incidencias-manuales (backend: /incidents). El backend exige el rol
// en cada endpoint (auth/dependencies.py's require_incidents_access / require_admin) -- estas
// funciones son RPC accesibles desde el navegador, asi que NO son la barrera de seguridad.

export const getManualIncidents = createServerFn({ method: 'GET' })
  .validator(manualIncidentsRangeSchema)
  .handler(async ({ data }) => fetchManualIncidents(data.dateFrom, data.dateTo))

export const createManualIncident = createServerFn({ method: 'POST' })
  .validator(manualIncidentInputSchema)
  .handler(async ({ data }) => createManualIncidentOnBackend(data))

export const updateManualIncident = createServerFn({ method: 'POST' })
  .validator(manualIncidentUpdateSchema)
  .handler(async ({ data: { id, ...input } }) =>
    updateManualIncidentOnBackend(id, input)
  )

export const deleteManualIncident = createServerFn({ method: 'POST' })
  .validator(manualIncidentIdSchema)
  .handler(async ({ data }) => deleteManualIncidentOnBackend(data.id))

export const getIncidentCatalog = createServerFn({ method: 'GET' }).handler(
  async () => fetchIncidentCatalog()
)
export const getIncidentAgentSuggestions = createServerFn({
  method: 'GET'
}).handler(async () => fetchIncidentAgentSuggestions())
export const getIncidentClientSuggestions = createServerFn({
  method: 'GET'
})
  .validator((data: { query: string; page: number; pageSize: number }) => data)
  .handler(async ({ data }) =>
    fetchIncidentClientSuggestions(data.query, data.page, data.pageSize)
  )

export const addCatalogOption = createServerFn({ method: 'POST' })
  .validator(catalogOptionCreateSchema)
  .handler(async ({ data }) =>
    addCatalogOptionOnBackend(data.category, data.value)
  )

export const setCatalogOptionActive = createServerFn({ method: 'POST' })
  .validator(catalogOptionUpdateSchema)
  .handler(async ({ data }) =>
    setCatalogOptionActiveOnBackend(data.id, data.active)
  )

export const importCatalogFromC3 = createServerFn({ method: 'POST' }).handler(
  async () => importCatalogFromC3OnBackend()
)
