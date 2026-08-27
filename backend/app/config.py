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

_AUTH_KEYS = ("AUTH_JWT_SECRET", "AUTH_BOOTSTRAP_USERNAME", "AUTH_BOOTSTRAP_PASSWORD")

_CORS_KEYS = ("CORS_ALLOWED_ORIGINS",)
# Default de dev: el puerto de `bun run dev` (frontend/CLAUDE.md). En Render/Vercel, seteando
# CORS_ALLOWED_ORIGINS (lista separada por comas) con el/los dominio(s) reales del frontend.
_DEFAULT_CORS_ORIGINS = ["http://localhost:3000"]


def load_cors_origins(env_path: Path | None = None) -> list[str]:
    """A diferencia de los otros load_*_config() de aca arriba, no es un secreto -- tiene un
    default razonable para dev en vez de RuntimeError si falta. No hace falta lidiar con cookies
    cross-site (la API nunca recibe llamadas de credenciales via cookie, ver app/auth/) pero
    igual conviene acotar el origin: si un JWT se filtra por otra via (XSS, log, etc), una
    lista abierta (allow_origins=["*"]) deja que CUALQUIER pagina en un browser lo replique
    contra esta API y lea la respuesta -- acotarlo a los dominios reales del frontend es
    defensa en profundidad barata (no afecta las llamadas legitimas: backendFetch() corre
    server-to-server, CORS ni se evalua para esas)."""
    path = env_path or PROJECT_ROOT / ".env"
    values = dict(dotenv_values(path))
    values.update({k: v for k, v in os.environ.items() if k in _CORS_KEYS})

    raw = values.get("CORS_ALLOWED_ORIGINS")
    if not raw:
        return list(_DEFAULT_CORS_ORIGINS)
    return [origin.strip() for origin in raw.split(",") if origin.strip()]

# Unico lugar del backend donde se asume el valor literal de "Estado" -- el resto del
# proyecto es deliberadamente agnostico a ese string (ver store.py).
BENCHMARK_CLOSED_ESTADOS = ["Cerrada"]
BENCHMARK_LOOKBACK_DAYS = 3
BENCHMARK_POLL_INTERVAL_SECONDS = 60.0
BENCHMARK_MASSIVE_TIMEOUT_SECONDS = 6 * 3600.0
BENCHMARK_LLM_CONCURRENCY = 4


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


@dataclass(frozen=True)
class AuthConfig:
    jwt_secret: str
    bootstrap_username: str | None
    bootstrap_password: str | None


def load_auth_config(env_path: Path | None = None) -> AuthConfig:
    path = env_path or PROJECT_ROOT / ".env"
    values = dict(dotenv_values(path))
    values.update({k: v for k, v in os.environ.items() if k in _AUTH_KEYS})

    jwt_secret = values.get("AUTH_JWT_SECRET")
    if not jwt_secret:
        raise RuntimeError(
            "Falta variable (AUTH_JWT_SECRET): definila como variable de entorno del proceso, "
            f"o copia .env.example a {path} y completa el valor (p.ej. con `openssl rand -hex "
            "32`)."
        )

    return AuthConfig(
        jwt_secret=jwt_secret,
        bootstrap_username=values.get("AUTH_BOOTSTRAP_USERNAME") or None,
        bootstrap_password=values.get("AUTH_BOOTSTRAP_PASSWORD") or None,
    )
