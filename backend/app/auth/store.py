import threading
from dataclasses import dataclass
from typing import Protocol

import turso_serverless

from .. import config
from . import security

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    is_admin        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL
);
"""


class DBConnection(Protocol):
    """Mismo contrato minimo que extraction/store.py's DBConnection -- cualquier conexion
    DB-API 2.0 compatible con sqlite3 (stdlib sqlite3.Connection en tests, turso_serverless.
    Connection en produccion)."""

    def execute(self, sql: str, parameters: tuple = ()): ...
    def executescript(self, sql: str): ...
    def commit(self) -> None: ...


@dataclass(frozen=True)
class UserRecord:
    id: int
    username: str
    password_hash: str
    is_admin: bool
    created_at: str


class UsernameTakenError(Exception):
    pass


_schema_initialized = False
_schema_lock = threading.Lock()


def get_connection() -> turso_serverless.Connection:
    global _schema_initialized
    turso_config = config.load_turso_config()
    conn = turso_serverless.connect(
        turso_config.database_url, auth_token=turso_config.auth_token
    )
    if not _schema_initialized:
        with _schema_lock:
            if not _schema_initialized:
                _init_schema(conn)
                _schema_initialized = True
    return conn


def _init_schema(conn: DBConnection) -> None:
    conn.executescript(_SCHEMA)


def _normalize_username(username: str) -> str:
    return username.strip().lower()


def get_user_by_username(conn: DBConnection, username: str) -> UserRecord | None:
    cursor = conn.execute(
        "SELECT id, username, password_hash, is_admin, created_at FROM users WHERE username = ?",
        (_normalize_username(username),),
    )
    row = cursor.fetchone()
    if row is None:
        return None
    return UserRecord(
        id=row[0], username=row[1], password_hash=row[2], is_admin=bool(row[3]), created_at=row[4]
    )


def create_user(
    conn: DBConnection, username: str, password_hash: str, is_admin: bool, created_at: str
) -> UserRecord:
    """Check-then-insert en vez de depender de capturar una excepcion IntegrityError especifica
    de turso_serverless (no confirmada en este codigo) -- hay una ventana TOCTOU chica bajo
    concurrencia, aceptable para una operacion admin-only de bajo volumen."""
    normalized = _normalize_username(username)
    if get_user_by_username(conn, normalized) is not None:
        raise UsernameTakenError(f"El usuario {username!r} ya existe")

    conn.execute(
        "INSERT INTO users (username, password_hash, is_admin, created_at) VALUES (?, ?, ?, ?)",
        (normalized, password_hash, int(is_admin), created_at),
    )
    conn.commit()
    user = get_user_by_username(conn, normalized)
    assert user is not None
    return user


def count_users(conn: DBConnection) -> int:
    cursor = conn.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()[0]


def list_users(conn: DBConnection) -> list[UserRecord]:
    """Sin paginacion a proposito -- una tabla de cuentas admin-creadas para un equipo interno
    se espera chica (a diferencia de attention/callincoming/etc, que sí necesitan pagina server-
    side, ver /data/attention-records)."""
    cursor = conn.execute(
        "SELECT id, username, password_hash, is_admin, created_at FROM users ORDER BY id"
    )
    return [
        UserRecord(id=row[0], username=row[1], password_hash=row[2], is_admin=bool(row[3]), created_at=row[4])
        for row in cursor.fetchall()
    ]


def seed_bootstrap_admin(
    conn: DBConnection, auth_config: config.AuthConfig, created_at: str
) -> UserRecord | None:
    """Siembra la primera cuenta (admin) solo si la tabla esta vacia y AUTH_BOOTSTRAP_USERNAME/
    AUTH_BOOTSTRAP_PASSWORD estan seteadas -- no-op en cualquier otro caso (tabla ya tiene al
    menos un usuario, o faltan las variables de bootstrap). Pensado para correr una sola vez
    desde el lifespan hook de main.py, no en el primer get_connection() lazy cualquiera --  ver
    CLAUDE.md para el detalle de la carrera que evita."""
    if count_users(conn) > 0:
        return None
    if not auth_config.bootstrap_username or not auth_config.bootstrap_password:
        return None

    password_hash = security.hash_password(auth_config.bootstrap_password)
    return create_user(
        conn, auth_config.bootstrap_username, password_hash, is_admin=True, created_at=created_at
    )
