import threading
from dataclasses import dataclass
from typing import Protocol

import turso_serverless

from .. import config
from . import security

# Roles de cuenta. "admin" y "user" ven todo el panel (admin ademas gestiona cuentas, la config
# del LLM y el catalogo de incidencias); "incidencias" SOLO puede usar /incidents/* (la seccion
# de incidencias manuales) -- el resto de la API le responde 403 (ver dependencies.py).
ROLE_ADMIN = "admin"
ROLE_USER = "user"
ROLE_INCIDENTS = "incidencias"
ROLES = (ROLE_ADMIN, ROLE_USER, ROLE_INCIDENTS)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    username        TEXT NOT NULL UNIQUE,
    password_hash   TEXT NOT NULL,
    is_admin        INTEGER NOT NULL DEFAULT 0,
    created_at      TEXT NOT NULL,
    role            TEXT NOT NULL DEFAULT 'user'
);
"""

_USER_COLUMNS = "id, username, password_hash, role, created_at"


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
    role: str
    created_at: str

    @property
    def is_admin(self) -> bool:
        return self.role == ROLE_ADMIN


class UsernameTakenError(Exception):
    pass


class LastAdminError(Exception):
    pass


def _row_to_user(row) -> UserRecord:
    return UserRecord(
        id=row[0], username=row[1], password_hash=row[2], role=row[3], created_at=row[4]
    )


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
    _migrate_role_column(conn)


def _migrate_role_column(conn: DBConnection) -> None:
    """`role` no existia cuando `users` se creo por primera vez -- CREATE TABLE IF NOT EXISTS no
    agrega columnas a una tabla ya existente en la Turso en vivo, mismo motivo/patron que
    extraction/store.py's _migrate_* (PRAGMA table_info + ALTER TABLE ADD COLUMN, aditivo, nunca
    se dropea nada). El backfill sale de is_admin, que se sigue escribiendo en sincronia
    (is_admin = role == 'admin') para que un rollback a codigo viejo siga funcionando."""
    cursor = conn.execute("PRAGMA table_info(users)")
    existing = {row[1] for row in cursor.fetchall()}
    if "role" in existing:
        return
    conn.execute("ALTER TABLE users ADD COLUMN role TEXT NOT NULL DEFAULT 'user'")
    conn.execute("UPDATE users SET role = 'admin' WHERE is_admin = 1")
    conn.commit()


def normalize_username(username: str) -> str:
    return username.strip().lower()


def get_user_by_username(conn: DBConnection, username: str) -> UserRecord | None:
    cursor = conn.execute(
        f"SELECT {_USER_COLUMNS} FROM users WHERE username = ?",
        (normalize_username(username),),
    )
    row = cursor.fetchone()
    return None if row is None else _row_to_user(row)


def get_user_by_id(conn: DBConnection, user_id: int) -> UserRecord | None:
    cursor = conn.execute(f"SELECT {_USER_COLUMNS} FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    return None if row is None else _row_to_user(row)


def _validate_role(role: str) -> None:
    if role not in ROLES:
        raise ValueError(f"Rol invalido: {role!r}. Validos: {list(ROLES)}")


def create_user(
    conn: DBConnection, username: str, password_hash: str, role: str, created_at: str
) -> UserRecord:
    """Check-then-insert en vez de depender de capturar una excepcion IntegrityError especifica
    de turso_serverless (no confirmada en este codigo) -- hay una ventana TOCTOU chica bajo
    concurrencia, aceptable para una operacion admin-only de bajo volumen."""
    _validate_role(role)
    normalized = normalize_username(username)
    if get_user_by_username(conn, normalized) is not None:
        raise UsernameTakenError(f"El usuario {username!r} ya existe")

    conn.execute(
        "INSERT INTO users (username, password_hash, is_admin, role, created_at) "
        "VALUES (?, ?, ?, ?, ?)",
        (normalized, password_hash, int(role == ROLE_ADMIN), role, created_at),
    )
    conn.commit()
    user = get_user_by_username(conn, normalized)
    assert user is not None
    return user


def count_users(conn: DBConnection) -> int:
    cursor = conn.execute("SELECT COUNT(*) FROM users")
    return cursor.fetchone()[0]


def count_admins(conn: DBConnection) -> int:
    cursor = conn.execute("SELECT COUNT(*) FROM users WHERE role = ?", (ROLE_ADMIN,))
    return cursor.fetchone()[0]


def update_user_role(conn: DBConnection, user_id: int, role: str) -> UserRecord | None:
    """None si el usuario no existe. LastAdminError si el cambio dejaria el sistema sin ningun
    admin (nadie podria volver a crear cuentas ni cambiar roles). Mismo check-then-write que
    create_user -- ventana TOCTOU chica, aceptable para una operacion admin-only de bajo volumen."""
    _validate_role(role)
    current = get_user_by_id(conn, user_id)
    if current is None:
        return None
    if current.role == role:
        return current
    if current.role == ROLE_ADMIN and count_admins(conn) <= 1:
        raise LastAdminError("No se puede quitar el rol admin a la unica cuenta admin")

    conn.execute(
        "UPDATE users SET role = ?, is_admin = ? WHERE id = ?",
        (role, int(role == ROLE_ADMIN), user_id),
    )
    conn.commit()
    return get_user_by_id(conn, user_id)


def list_users(conn: DBConnection) -> list[UserRecord]:
    """Sin paginacion a proposito -- una tabla de cuentas admin-creadas para un equipo interno
    se espera chica (a diferencia de attention/callincoming/etc, que sí necesitan pagina server-
    side, ver /data/attention-records)."""
    cursor = conn.execute(f"SELECT {_USER_COLUMNS} FROM users ORDER BY id")
    return [_row_to_user(row) for row in cursor.fetchall()]


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
        conn, auth_config.bootstrap_username, password_hash, role=ROLE_ADMIN, created_at=created_at
    )
