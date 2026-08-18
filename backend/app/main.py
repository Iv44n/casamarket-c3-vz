import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import data, runs

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
)

DESCRIPTION = """
Extraccion y consulta de los reportes diarios de Casa Market's Contact Center Cloud (C3): atenciones
de WhatsApp entrantes/salientes, llamadas entrantes/salientes, y el padron de contactos.

`POST /extraction/refresh` dispara una corrida bajo demanda (login + las 5 descargas) -- el cliente
la llama periodicamente con su propio intervalo, este servidor no programa nada por su cuenta.
`GET /data/{report_name}` sirve el contenido ya parseado del ultimo archivo descargado.
"""

TAGS_METADATA = [
    {
        "name": "extraction",
        "description": "Disparar una corrida de descargas y consultar la ultima.",
    },
    {
        "name": "data",
        "description": "Los reportes ya descargados, parseados a JSON.",
    },
]


app = FastAPI(
    title="C3 Panel API",
    description=DESCRIPTION,
    version="0.1.0",
    openapi_tags=TAGS_METADATA,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(runs.router)
app.include_router(data.router)
