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


def update_user(
    conn: DBConnection,
    user_id: int,
    *,
    username: str | None = None,
    password_hash: str | None = None,
    role: str | None = None,
) -> UserRecord | None:
    """Edita los campos que vengan (None = no tocar). None si el usuario no existe.
    UsernameTakenError si el username nuevo ya es de otra cuenta; LastAdminError si el cambio
    dejaria el sistema sin ningun admin (nadie podria volver a gestionar cuentas). Mismo
    check-then-write que create_user -- ventana TOCTOU chica, aceptable para una operacion
    admin-only de bajo volumen.

    Ojo: renombrar invalida en la practica los tokens ya emitidos de esa cuenta (el claim
    username deja de coincidir, ver dependencies._resolve_role) -- la persona tiene que volver a
    iniciar sesion. Cambiar la contraseña NO invalida tokens (son stateless, ver CLAUDE.md)."""
    current = get_user_by_id(conn, user_id)
    if current is None:
        return None

    assignments: list[str] = []
    params: list[object] = []
    if username is not None:
        normalized = normalize_username(username)
        if not normalized:
            raise ValueError("El usuario no puede estar vacio")
        if normalized != current.username:
            other = get_user_by_username(conn, normalized)
            if other is not None and other.id != user_id:
                raise UsernameTakenError(f"El usuario {username!r} ya existe")
            assignments.append("username = ?")
            params.append(normalized)
    if password_hash is not None:
        assignments.append("password_hash = ?")
        params.append(password_hash)
    if role is not None:
        _validate_role(role)
        if role != current.role:
            if current.role == ROLE_ADMIN and count_admins(conn) <= 1:
                raise LastAdminError("No se puede quitar el rol admin a la unica cuenta admin")
            assignments.extend(["role = ?", "is_admin = ?"])
            params.extend([role, int(role == ROLE_ADMIN)])

    if assignments:
        conn.execute(
            f"UPDATE users SET {', '.join(assignments)} WHERE id = ?", (*params, user_id)
        )
        conn.commit()
    return get_user_by_id(conn, user_id)


def delete_user(conn: DBConnection, user_id: int) -> bool:
    """Borrado fisico de la cuenta (no hay nada que la referencie por FK: las incidencias
    manuales guardan created_by como texto, asi que su autoria se conserva). False si no existe;
    LastAdminError si es la unica cuenta admin."""
    current = get_user_by_id(conn, user_id)
    if current is None:
        return False
    if current.role == ROLE_ADMIN and count_admins(conn) <= 1:
        raise LastAdminError("No se puede eliminar la unica cuenta admin")
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    return True


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
