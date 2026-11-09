import threading
import time
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .. import config
from . import security, store

_bearer_scheme = HTTPBearer(auto_error=False)

FULL_ACCESS_ROLES = frozenset({store.ROLE_ADMIN, store.ROLE_USER})
INCIDENTS_ACCESS_ROLES = frozenset({store.ROLE_ADMIN, store.ROLE_USER, store.ROLE_INCIDENTS})


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    is_admin: bool
    # "" = derivarlo de is_admin (admin/user) -- asi los tests y cualquier caller viejo que
    # construye CurrentUser(id, username, is_admin) posicionalmente siguen funcionando.
    role: str = ""

    def __post_init__(self) -> None:
        if not self.role:
            object.__setattr__(
                self, "role", store.ROLE_ADMIN if self.is_admin else store.ROLE_USER
            )


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """Stateless: no toca Turso en el hot path, solo verifica firma+expiracion del JWT contra
    AUTH_JWT_SECRET. Un RuntimeError de config.load_auth_config() (falta la variable) se deja
    propagar como 500 -- es un error de configuracion del server, no "tu token es invalido".
    El rol que trae el token es solo informativo: lo que decide el acceso a cada router es
    require_full_access/require_incidents_access, que re-leen el rol actual de la DB."""
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="Falta el header Authorization: Bearer <token>",
            headers={"WWW-Authenticate": "Bearer"},
        )

    auth_config = config.load_auth_config()
    try:
        payload = security.decode_access_token(credentials.credentials, auth_config.jwt_secret)
    except jwt.PyJWTError as exc:
        raise HTTPException(
            status_code=401,
            detail="Token invalido o expirado",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc

    return CurrentUser(
        id=payload.user_id,
        username=payload.username,
        is_admin=payload.is_admin,
        role=payload.role,
    )


# Cache en memoria del rol ACTUAL de cada cuenta (user_id -> (rol, expira_en)), para no pagar
# un round-trip a Turso (~0.4s) en cada request pero tampoco confiar 14 dias en el claim del
# JWT: si un admin pasa a alguien de "user" a "incidencias", el token viejo sigue diciendo
# "user". Con TTL de 60s el cambio aplica a lo sumo un minuto despues, y PATCH /auth/users/{id}
# ademas invalida la entrada (invalidate_cached_role) para que aplique en el request siguiente.
# Plain dict + Lock, mismo supuesto de "un solo proceso" que extraction/state.py y
# rate_limit.py (ver CLAUDE.md -- este servicio no escala horizontalmente).
_ROLE_CACHE_TTL_SECONDS = 60.0
_role_cache: dict[int, tuple[str, float]] = {}
_role_cache_lock = threading.Lock()


def invalidate_cached_role(user_id: int) -> None:
    with _role_cache_lock:
        _role_cache.pop(user_id, None)


def clear_role_cache() -> None:
    with _role_cache_lock:
        _role_cache.clear()


def _resolve_role(user: CurrentUser) -> str | None:
    """Rol actual de la cuenta, o None si ya no existe. Ademas de buscar por id compara el
    username: si la tabla users se recreara (pasa en la Turso de dev, el AUTOINCREMENT vuelve
    a 1), un token viejo con user_id=1 no debe heredar los permisos de quien sea el nuevo id 1."""
    now = time.monotonic()
    with _role_cache_lock:
        cached = _role_cache.get(user.id)
    if cached is not None and cached[1] > now:
        return cached[0]

    conn = store.get_connection()
    try:
        record = store.get_user_by_id(conn, user.id)
    finally:
        conn.close()

    if record is None or record.username != store.normalize_username(user.username):
        invalidate_cached_role(user.id)
        return None
    with _role_cache_lock:
        _role_cache[user.id] = (record.role, now + _ROLE_CACHE_TTL_SECONDS)
    return record.role


def _require_roles(user: CurrentUser, allowed: frozenset[str]) -> CurrentUser:
    role = _resolve_role(user)
    if role is None:
        raise HTTPException(
            status_code=401,
            detail="La cuenta ya no existe",
            headers={"WWW-Authenticate": "Bearer"},
        )
    if role not in allowed:
        raise HTTPException(status_code=403, detail="Tu cuenta no tiene acceso a esta seccion")
    return CurrentUser(id=user.id, username=user.username, is_admin=role == store.ROLE_ADMIN, role=role)


def require_full_access(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """Todo el panel existente (/data, /extraction, /benchmarks): admin y user, nunca
    "incidencias"."""
    return _require_roles(user, FULL_ACCESS_ROLES)


def require_incidents_access(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """La seccion de incidencias manuales (/incidents): los 3 roles."""
    return _require_roles(user, INCIDENTS_ACCESS_ROLES)


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """A diferencia de get_current_user, esta si toca Turso -- re-verifica is_admin contra la DB
    en vez de confiar ciegamente en el claim del JWT. Solo la gatean endpoints admin de bajo
    trafico (/auth/users, PUT /benchmarks/settings, el catalogo de incidencias), asi que el
    costo extra (sin cache, a diferencia de _resolve_role) es aceptable a cambio de que una
    degradacion de admin aplique en el acto."""
    conn = store.get_connection()
    try:
        current = store.get_user_by_username(conn, user.username)
    finally:
        conn.close()

    if current is None or not current.is_admin:
        raise HTTPException(status_code=403, detail="Se requiere una cuenta admin")
    return CurrentUser(
        id=current.id, username=current.username, is_admin=True, role=store.ROLE_ADMIN
    )
