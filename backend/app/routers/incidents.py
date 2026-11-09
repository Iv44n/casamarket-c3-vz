from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field, field_validator

from ..auth.dependencies import CurrentUser, require_admin, require_incidents_access
from ..extraction import store as extraction_store
from ..incidents import lookups, store

# Accesible para los 3 roles (admin, user, incidencias) -- es la UNICA parte de la API que el
# rol "incidencias" puede usar (ver auth/dependencies.py). El catalogo se edita solo con admin.
router = APIRouter(
    prefix="/incidents", tags=["incidents"], dependencies=[Depends(require_incidents_access)]
)

ISO_DATE_PATTERN = r"^\d{4}-\d{2}-\d{2}$"
Category = Literal["origen", "tipo", "ambito", "resultado"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class IncidentRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    fecha: str = Field(pattern=ISO_DATE_PATTERN)
    hora: str = Field(default="", pattern=r"^(([01]\d|2[0-3]):[0-5]\d)?$")
    cliente: str = Field(default="", max_length=200)
    telefono: str = Field(default="", max_length=40)
    agente: str = Field(default="", max_length=120)
    origen: str = Field(min_length=1, max_length=200)
    tipo: str = Field(min_length=1, max_length=200)
    ambito: str = Field(min_length=1, max_length=200)
    resultado: str = Field(default="", max_length=200)
    descripcion: str = Field(min_length=1, max_length=5000)

    @field_validator("fecha")
    @classmethod
    def _real_calendar_date(cls, value: str) -> str:
        # El pattern acepta 2026-13-45; esto exige una fecha que exista.
        date.fromisoformat(value)
        return value

    def to_input(self) -> store.IncidentInput:
        return store.IncidentInput(**self.model_dump())


class ManualIncidentPublic(BaseModel):
    id: int
    fecha: str
    hora: str
    cliente: str
    telefono: str
    agente: str
    origen: str
    tipo: str
    ambito: str
    resultado: str
    descripcion: str
    created_by: str
    created_at: str
    updated_by: str | None
    updated_at: str | None


class IncidentListResponse(BaseModel):
    rows: list[ManualIncidentPublic]
    # True si habia mas de store.LIST_LIMIT incidencias en el rango (solo se devuelven las
    # mas recientes) -- la UI lo avisa en vez de mostrar un total incompleto como si fuera real.
    truncated: bool


class CatalogOptionPublic(BaseModel):
    id: int
    category: Category
    value: str
    active: bool
    source: Literal["c3", "manual"]
    created_at: str


class CatalogOptionCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    category: Category
    value: str = Field(min_length=1, max_length=200)


class CatalogOptionUpdate(BaseModel):
    active: bool


class CatalogImportResult(BaseModel):
    added: int


class ClientSuggestionPublic(BaseModel):
    name: str
    phone: str
    detail: str
    document: str


class ClientSuggestionsPage(BaseModel):
    rows: list[ClientSuggestionPublic]
    page: int
    page_size: int
    has_more: bool


def _incident_public(incident: store.ManualIncident) -> ManualIncidentPublic:
    return ManualIncidentPublic(**incident.__dict__)


def _option_public(option: store.CatalogOption) -> CatalogOptionPublic:
    return CatalogOptionPublic(**option.__dict__)


@router.get("")
def list_incidents(
    date_from: str = Query(pattern=ISO_DATE_PATTERN),
    date_to: str = Query(pattern=ISO_DATE_PATTERN),
) -> IncidentListResponse:
    if date_from > date_to:
        raise HTTPException(status_code=422, detail="date_from no puede ser posterior a date_to")
    conn = store.get_connection()
    try:
        rows, truncated = store.list_incidents(conn, date_from, date_to)
    finally:
        conn.close()
    return IncidentListResponse(rows=[_incident_public(r) for r in rows], truncated=truncated)


@router.post("", status_code=201)
def create_incident(
    request: IncidentRequest, user: CurrentUser = Depends(require_incidents_access)
) -> ManualIncidentPublic:
    conn = store.get_connection()
    try:
        try:
            incident = store.create_incident(conn, request.to_input(), user.username, _now())
        except store.InvalidCatalogValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        conn.close()
    lookups.invalidate_manual()
    return _incident_public(incident)


@router.put("/{incident_id}")
def update_incident(
    incident_id: int,
    request: IncidentRequest,
    user: CurrentUser = Depends(require_incidents_access),
) -> ManualIncidentPublic:
    conn = store.get_connection()
    try:
        try:
            incident = store.update_incident(
                conn, incident_id, request.to_input(), user.username, _now()
            )
        except store.InvalidCatalogValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        conn.close()
    if incident is None:
        raise HTTPException(status_code=404, detail="La incidencia no existe")
    lookups.invalidate_manual()
    return _incident_public(incident)


@router.delete("/{incident_id}", status_code=204)
def delete_incident(
    incident_id: int, user: CurrentUser = Depends(require_incidents_access)
) -> None:
    conn = store.get_connection()
    try:
        deleted = store.delete_incident(conn, incident_id, user.username, _now())
    finally:
        conn.close()
    if not deleted:
        raise HTTPException(status_code=404, detail="La incidencia no existe")
    lookups.invalidate_manual()


@router.get("/lookups/agents")
def list_agent_suggestions() -> list[str]:
    """Agentes conocidos (historial de C3 + los escritos a mano), para sugerir en el formulario.
    Son nombres de empleados, no datos de clientes: se devuelve la lista completa (~40)."""
    return lookups.list_agents()


@router.get("/lookups/clients")
def search_client_suggestions(
    q: str = Query(default="", max_length=100),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=100),
) -> ClientSuggestionsPage:
    """Clientes paginados disponibles para el selector inicial o filtrados por texto."""
    if q.strip() and not lookups.is_searchable(q):
        lookups.warm_in_background()
        rows, has_more = [], False
    else:
        rows, has_more = lookups.client_page(q, page, page_size)
    return ClientSuggestionsPage(
        rows=[ClientSuggestionPublic(**vars(c)) for c in rows],
        page=page,
        page_size=page_size,
        has_more=has_more,
    )


@router.get("/catalog")
def list_catalog() -> list[CatalogOptionPublic]:
    """Todas las opciones, activas e inactivas -- el formulario filtra las activas; la pestaña
    de catalogo (admin) muestra todas."""
    conn = store.get_connection()
    try:
        options = store.list_catalog(conn)
    finally:
        conn.close()
    return [_option_public(o) for o in options]


@router.post("/catalog", status_code=201)
def add_catalog_option(
    request: CatalogOptionCreate, _admin: CurrentUser = Depends(require_admin)
) -> CatalogOptionPublic:
    conn = store.get_connection()
    try:
        try:
            option = store.add_catalog_option(conn, request.category, request.value, _now())
        except store.CatalogOptionExistsError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        conn.close()
    return _option_public(option)


@router.patch("/catalog/{option_id}")
def update_catalog_option(
    option_id: int, request: CatalogOptionUpdate, _admin: CurrentUser = Depends(require_admin)
) -> CatalogOptionPublic:
    conn = store.get_connection()
    try:
        option = store.set_catalog_option_active(conn, option_id, request.active)
    finally:
        conn.close()
    if option is None:
        raise HTTPException(status_code=404, detail="La opcion no existe")
    return _option_public(option)


@router.post("/catalog/import-c3")
def import_catalog_from_c3(_admin: CurrentUser = Depends(require_admin)) -> CatalogImportResult:
    """Siembra el catalogo con los valores que C3 ya usa. Idempotente; no reactiva opciones que
    un admin desactivo (ver store.import_catalog_values)."""
    extraction_conn = extraction_store.get_connection()
    try:
        values = extraction_store.distinct_incident_values(extraction_conn)
    finally:
        extraction_conn.close()

    conn = store.get_connection()
    try:
        added = store.import_catalog_values(conn, values, _now())
    finally:
        conn.close()
    return CatalogImportResult(added=added)
