from datetime import datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from .. import config
from ..auth import security, store
from ..auth.dependencies import CurrentUser, get_current_user, require_admin

router = APIRouter(prefix="/auth", tags=["auth"])


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
    is_admin: bool
    created_at: str


class CreateUserRequest(BaseModel):
    username: str
    password: str
    is_admin: bool = False


@router.post("/login")
def login(request: LoginRequest) -> TokenResponse:
    conn = store.get_connection()
    try:
        user = store.get_user_by_username(conn, request.username)
    finally:
        conn.close()

    # Usuario desconocido y password incorrecta devuelven el mismo 401 generico a proposito --
    # distinguirlos permitiria enumerar usernames validos.
    if user is None or not security.verify_password(request.password, user.password_hash):
        raise HTTPException(status_code=401, detail="Usuario o contraseña incorrectos")

    auth_config = config.load_auth_config()
    token, expires_at = security.create_access_token(
        user.id, user.username, user.is_admin, auth_config.jwt_secret
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

    return UserPublic(
        id=user.id, username=user.username, is_admin=user.is_admin, created_at=user.created_at
    )


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
                request.is_admin,
                datetime.now(timezone.utc).isoformat(),
            )
        except store.UsernameTakenError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    finally:
        conn.close()

    return UserPublic(
        id=user.id, username=user.username, is_admin=user.is_admin, created_at=user.created_at
    )
