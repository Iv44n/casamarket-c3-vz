from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

_ALGORITHM = "HS256"
_TOKEN_LIFETIME = timedelta(days=14)


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    username: str
    is_admin: bool


def create_access_token(
    user_id: int, username: str, is_admin: bool, secret: str
) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + _TOKEN_LIFETIME
    # "user_id", no el claim reservado "sub" -- PyJWT valida que "sub" sea un string (RFC 7519),
    # y user_id es un int aca (el PK entero de auth/store.py's tabla users).
    token = jwt.encode(
        {
            "user_id": user_id,
            "username": username,
            "is_admin": is_admin,
            "exp": expires_at,
        },
        secret,
        algorithm=_ALGORITHM,
    )
    return token, expires_at


def decode_access_token(token: str, secret: str) -> TokenPayload:
    """Deja propagar jwt.PyJWTError (token expirado, firma invalida, malformado, etc) -- la
    capa HTTP (auth/dependencies.py) es la que lo convierte en un 401, siguiendo el mismo
    espiritu "print/HTTP-free" que c3/ y extraction/ ya aplican para sus propias excepciones."""
    payload = jwt.decode(token, secret, algorithms=[_ALGORITHM])
    return TokenPayload(
        user_id=payload["user_id"], username=payload["username"], is_admin=payload["is_admin"]
    )
