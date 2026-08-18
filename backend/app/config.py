import os
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from dotenv import dotenv_values

_CREDENTIAL_KEYS = ("C3_USERNAME", "C3_PASSWORD", "C3_BASE_URL")

BASE_URL = "https://casamarket.c3.pe"
LOGIN_PATH = "/user/login"
SIGNIN_PATH = "/user/signin"

REPORT_PATHS = {
    "attention": "/user/report_message/attention",
    "outboundattention": "/user/report_message/outboundattention",
}

TZ = ZoneInfo("America/Lima")

PROJECT_ROOT = Path(__file__).resolve().parent.parent

RECON_DIR = PROJECT_ROOT / "recon"
DOWNLOADS_DIR = PROJECT_ROOT / "downloads"

HISTORICAL_BACKFILL_WINDOW_DAYS = 90
HISTORICAL_CLIENT_TIMEOUT_SECONDS = 300.0

_TURSO_KEYS = ("TURSO_DATABASE_URL", "TURSO_AUTH_TOKEN")


def hoy() -> date:
    return datetime.now(TZ).date()


@dataclass(frozen=True)
class Credentials:
    base_url: str
    username: str
    password: str


def load_credentials(env_path: Path | None = None) -> Credentials:
    path = env_path or PROJECT_ROOT / ".env"
    values = dict(dotenv_values(path))
    values.update({k: v for k, v in os.environ.items() if k in _CREDENTIAL_KEYS})

    username = values.get("C3_USERNAME")
    password = values.get("C3_PASSWORD")

    faltantes = [
        name
        for name, value in (("C3_USERNAME", username), ("C3_PASSWORD", password))
        if not value
    ]
    if faltantes:
        raise RuntimeError(
            f"Faltan variables ({', '.join(faltantes)}): defini C3_USERNAME/C3_PASSWORD como "
            f"variables de entorno del proceso, o copia .env.example a {path} y completa los "
            f"valores."
        )

    base_url = values.get("C3_BASE_URL") or BASE_URL
    return Credentials(base_url=base_url, username=username, password=password)


@dataclass(frozen=True)
class TursoConfig:
    database_url: str
    auth_token: str


def load_turso_config(env_path: Path | None = None) -> TursoConfig:
    path = env_path or PROJECT_ROOT / ".env"
    values = dict(dotenv_values(path))
    values.update({k: v for k, v in os.environ.items() if k in _TURSO_KEYS})

    database_url = values.get("TURSO_DATABASE_URL")
    auth_token = values.get("TURSO_AUTH_TOKEN")

    faltantes = [
        name
        for name, value in (
            ("TURSO_DATABASE_URL", database_url),
            ("TURSO_AUTH_TOKEN", auth_token),
        )
        if not value
    ]
    if faltantes:
        raise RuntimeError(
            f"Faltan variables ({', '.join(faltantes)}): defini TURSO_DATABASE_URL/"
            f"TURSO_AUTH_TOKEN como variables de entorno del proceso, o copia .env.example "
            f"a {path} y completa los valores."
        )

    return TursoConfig(database_url=database_url, auth_token=auth_token)
