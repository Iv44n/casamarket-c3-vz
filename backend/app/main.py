import logging
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .auth import store as auth_store
from .routers import auth, data, runs

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

DESCRIPTION = """
Extraccion y consulta de los reportes diarios de Casa Market's Contact Center Cloud (C3): atenciones
de WhatsApp entrantes/salientes, llamadas entrantes/salientes, y el padron de contactos.

`POST /extraction/refresh` dispara una corrida bajo demanda (login + las 5 descargas) -- el cliente
la llama periodicamente con su propio intervalo, este servidor no programa nada por su cuenta.
`GET /data/{report_name}` sirve el contenido ya parseado del ultimo archivo descargado.
"""

TAGS_METADATA = [
    {
        "name": "auth",
        "description": "Login (usuario + password) y alta de cuentas (admin-only).",
    },
    {
        "name": "extraction",
        "description": "Disparar una corrida de descargas y consultar la ultima.",
    },
    {
        "name": "data",
        "description": "Los reportes ya descargados, parseados a JSON.",
    },
]


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Sembrar la primera cuenta (admin) tiene que pasar una sola vez, deterministicamente, antes
    # de aceptar requests -- no en el primer get_connection() lazy cualquiera, porque ese primer
    # toque bien podria ser el primer intento de login real (carrera entre "existe la cuenta
    # todavia" y "alguien intentando usarla"). RuntimeError (falta AUTH_JWT_SECRET) se loguea y
    # no tumba el arranque -- mismo espiritu fail-lazy que load_credentials()/load_turso_config()
    # ya tienen (nunca se validan eager al importar).
    try:
        auth_config = config.load_auth_config()
        conn = auth_store.get_connection()
        try:
            seeded = auth_store.seed_bootstrap_admin(
                conn, auth_config, datetime.now(timezone.utc).isoformat()
            )
        finally:
            conn.close()
        if seeded is not None:
            logger.info("Bootstrap: cuenta admin '%s' creada", seeded.username)
    except RuntimeError as exc:
        logger.warning("Auth bootstrap salteado: %s", exc)
    yield


app = FastAPI(
    title="C3 Panel API",
    description=DESCRIPTION,
    version="0.1.0",
    openapi_tags=TAGS_METADATA,
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router)
app.include_router(runs.router)
app.include_router(data.router)


@app.get("/health", tags=["health"])
def health() -> dict:
    """Publico a proposito, sin Depends(get_current_user) -- el HEALTHCHECK de Dockerfile (y
    cualquier probe de Render) necesita poder confirmar que el proceso esta vivo sin credenciales.
    GET /extraction/status ya no sirve para esto desde que quedo protegido por auth; este endpoint
    reemplaza su rol de "always 200, side-effect-free" en el Dockerfile."""
    return {"status": "ok"}
