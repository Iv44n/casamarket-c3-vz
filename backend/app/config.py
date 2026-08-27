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

_LLM_KEYS = (
    "LLM_PROVIDER",
    "MINIMAX_API_KEY",
    "MINIMAX_MODEL",
    "MINIMAX_BASE_URL",
)

_AUTH_KEYS = ("AUTH_JWT_SECRET", "AUTH_BOOTSTRAP_USERNAME", "AUTH_BOOTSTRAP_PASSWORD")

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
class LLMConfig:
    """Config agnostica de proveedor: `provider_name` decide que campos importan.
    Agregar un proveedor nuevo es agregar sus propios campos aca + una rama nueva en
    load_llm_config(), sin tocar los de los proveedores ya existentes. Hoy solo esta
    configurado MiniMax -- su API es compatible con la de OpenAI, asi que no necesita una
    clase de proveedor propia: reusa OpenAIProvider tal cual, solo con su propio api_key/
    model/base_url (ver benchmarks/llm/__init__.py's build_provider())."""

    provider_name: str
    minimax_api_key: str | None = None
    minimax_model: str | None = None
    minimax_base_url: str | None = None

    @property
    def model_label(self) -> str | None:
        """Nombre de modelo a guardar en benchmark_result.llm_model para auditoria --
        generico sobre el proveedor, para que pipeline.py no necesite conocer los campos
        propios de cada uno."""
        if self.provider_name == "minimax":
            return self.minimax_model
        return None


def load_llm_config(env_path: Path | None = None) -> LLMConfig:
    path = env_path or PROJECT_ROOT / ".env"
    values = dict(dotenv_values(path))
    values.update({k: v for k, v in os.environ.items() if k in _LLM_KEYS})

    provider_name = values.get("LLM_PROVIDER") or "minimax"

    if provider_name == "minimax":
        api_key = values.get("MINIMAX_API_KEY")
        model = values.get("MINIMAX_MODEL")
        base_url = values.get("MINIMAX_BASE_URL")
        faltantes = [
            name
            for name, value in (
                ("MINIMAX_API_KEY", api_key),
                ("MINIMAX_MODEL", model),
                ("MINIMAX_BASE_URL", base_url),
            )
            if not value
        ]
        if faltantes:
            raise RuntimeError(
                f"Faltan variables ({', '.join(faltantes)}) para LLM_PROVIDER=minimax: "
                f"definilas como variables de entorno del proceso, o copia .env.example a "
                f"{path} y completa los valores. MiniMax expone un endpoint compatible con "
                f"la API de OpenAI -- MINIMAX_BASE_URL debe apuntar a ese endpoint /v1 (ver "
                f"su documentacion) y MINIMAX_MODEL al nombre exacto del modelo a usar."
            )
        return LLMConfig(
            provider_name="minimax",
            minimax_api_key=api_key,
            minimax_model=model,
            minimax_base_url=base_url,
        )

    raise RuntimeError(
        f"LLM_PROVIDER desconocido: {provider_name!r}. Proveedor valido hoy: 'minimax'."
    )


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
