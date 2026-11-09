from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from .. import config
from ..auth import rate_limit, security, store
from ..auth.dependencies import (
    CurrentUser,
    get_current_user,
    invalidate_cached_role,
    require_admin,
)

router = APIRouter(prefix="/auth", tags=["auth"])

Role = Literal["admin", "user", "incidencias"]


class LoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_at: str


class UserPublic(BaseModel):
    id: int
    username: str
    role: Role
    # Derivado de role (role == "admin"), se mantiene por compatibilidad con el frontend viejo.
    is_admin: bool
    created_at: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    role: Role = "user"


class UpdateUserRequest(BaseModel):
    # Todos opcionales: solo se cambia lo que venga. password en claro, se hashea aca.
    username: str | None = Field(default=None, min_length=1, max_length=120)
    password: str | None = Field(default=None, min_length=1)
    role: Role | None = None


def _to_public(user: store.UserRecord) -> UserPublic:
    return UserPublic(
        id=user.id,
        username=user.username,
        role=user.role,
        is_admin=user.is_admin,
        created_at=user.created_at,
    )


@router.post("/login")
def login(request: LoginRequest) -> TokenResponse:
    rate_limit_key = store.normalize_username(request.username)
    try:
        rate_limit.check(rate_limit_key)
    except rate_limit.TooManyAttemptsError as exc:
        raise HTTPException(status_code=429, detail=str(exc)) from exc

    conn = store.get_connection()
    try:
        user = store.get_user_by_username(conn, request.username)
    finally:
        conn.close()

    # Usuario desconocido y password incorrecta devuelven el mismo 401 generico a proposito --
    # distinguirlos permitiria enumerar usernames validos.
    if user is None or not security.verify_password(request.password, user.password_hash):
        rate_limit.record_failure(rate_limit_key)
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    rate_limit.clear(rate_limit_key)
    auth_config = config.load_auth_config()
    token, expires_at = security.create_access_token(
        user.id, user.username, user.role, auth_config.jwt_secret
    )
    return TokenResponse(access_token=token, expires_at=expires_at.isoformat())


@router.get("/me")
def me(current_user: CurrentUser = Depends(get_current_user)) -> UserPublic:
    conn = store.get_connection()
    try:
        user = store.get_user_by_username(conn, current_user.username)
    finally:
        conn.close()

    if user is None:
        # El JWT sigue siendo valido pero la cuenta ya no existe (borrada manualmente en Turso).
        raise HTTPException(status_code=401, detail="La cuenta ya no existe")

    return _to_public(user)


@router.get("/users")
def list_users(_admin: CurrentUser = Depends(require_admin)) -> list[UserPublic]:
    conn = store.get_connection()
    try:
        users = store.list_users(conn)
    finally:
        conn.close()

    return [_to_public(u) for u in users]


@router.post("/users", status_code=201)
def create_user(
    request: CreateUserRequest, _admin: CurrentUser = Depends(require_admin)
) -> UserPublic:
    conn = store.get_connection()
    try:
        password_hash = security.hash_password(request.password)
        try:
            user = store.create_user(
                conn,
                request.username,
                password_hash,
                request.role,
                datetime.now(timezone.utc).isoformat(),
            )
        except store.UsernameTakenError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        conn.close()

    return _to_public(user)


@router.patch("/users/{user_id}")
def update_user(
    user_id: int, request: UpdateUserRequest, admin: CurrentUser = Depends(require_admin)
) -> UserPublic:
    if request.username is None and request.password is None and request.role is None:
        raise HTTPException(status_code=400, detail="No hay cambios para guardar")

    conn = store.get_connection()
    try:
        if user_id == admin.id:
            # En la propia cuenta solo la contraseña: quitarse el rol admin dejaria a esta
            # persona afuera, y renombrarse invalidaria su propio token a mitad de sesion.
            own = store.get_user_by_id(conn, user_id)
            renaming = (
                request.username is not None
                and own is not None
                and store.normalize_username(request.username) != own.username
            )
            changing_role = request.role is not None and own is not None and request.role != own.role
            if renaming or changing_role:
                raise HTTPException(
                    status_code=400,
                    detail="En la propia cuenta solo se puede cambiar la contraseña",
                )
        password_hash = (
            security.hash_password(request.password) if request.password is not None else None
        )
        try:
            user = store.update_user(
                conn,
                user_id,
                username=request.username,
                password_hash=password_hash,
                role=request.role,
            )
        except (store.UsernameTakenError, store.LastAdminError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        conn.close()

    if user is None:
        raise HTTPException(status_code=404, detail="El usuario no existe")
    # Que un cambio de rol (o un rename, que invalida el token viejo) aplique en el proximo
    # request de esa cuenta, no recien cuando venza el TTL de la cache de roles.
    invalidate_cached_role(user_id)
    return _to_public(user)


@router.delete("/users/{user_id}", status_code=204)
def delete_user(user_id: int, admin: CurrentUser = Depends(require_admin)) -> None:
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="No se puede eliminar la propia cuenta")

    conn = store.get_connection()
    try:
        try:
            deleted = store.delete_user(conn, user_id)
        except store.LastAdminError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        conn.close()

    if not deleted:
        raise HTTPException(status_code=404, detail="El usuario no existe")
    # Su token sigue firmado y vigente, pero el proximo request ya no encuentra la cuenta y
    # responde 401 (dependencies._resolve_role) -- sin esperar el TTL de la cache.
    invalidate_cached_role(user_id)
