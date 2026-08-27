from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .. import config
from . import security, store

_bearer_scheme = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class CurrentUser:
    id: int
    username: str
    is_admin: bool


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),
) -> CurrentUser:
    """Stateless: no toca Turso en el hot path, solo verifica firma+expiracion del JWT contra
    AUTH_JWT_SECRET. Un RuntimeError de config.load_auth_config() (falta la variable) se deja
    propagar como 500 -- es un error de configuracion del server, no "tu token es invalido"."""
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

    return CurrentUser(id=payload.user_id, username=payload.username, is_admin=payload.is_admin)


def require_admin(user: CurrentUser = Depends(get_current_user)) -> CurrentUser:
    """A diferencia de get_current_user, esta si toca Turso -- re-verifica is_admin contra la DB
    en vez de confiar ciegamente en el claim del JWT. Solo la gatean 2 endpoints de bajo trafico
    (POST/GET /auth/users), asi que el costo extra es aceptable a cambio de cerrar la ventana en
    la que a un admin degradado a usuario normal le seguiria funcionando is_admin=true en su
    token viejo hasta que expire (14 dias) -- el resto de la API sigue sin este costo porque no
    le importa is_admin."""
    conn = store.get_connection()
    try:
        current = store.get_user_by_username(conn, user.username)
    finally:
        conn.close()

    if current is None or not current.is_admin:
        raise HTTPException(status_code=403, detail="Se requiere una cuenta admin")
    return user
