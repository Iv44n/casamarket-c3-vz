from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

import bcrypt
import jwt

_ALGORITHM = "HS256"
_TOKEN_LIFETIME = timedelta(days=14)
# Un solo emisor/audiencia (esta misma API) -- no cambia el modelo de amenaza (el secreto sigue
# siendo lo unico que efectivamente protege el token), pero validarlos explicitamente rechaza
# de una un JWT valido-pero-de-otro-contexto si este secreto llegara a reusarse en otro lado.
_ISSUER = "c3-panel-backend"
_AUDIENCE = "c3-panel-frontend"


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


@dataclass(frozen=True)
class TokenPayload:
    user_id: int
    username: str
    role: str

    @property
    def is_admin(self) -> bool:
        return self.role == "admin"


def create_access_token(
    user_id: int, username: str, role: str, secret: str
) -> tuple[str, datetime]:
    expires_at = datetime.now(timezone.utc) + _TOKEN_LIFETIME
    # "user_id", no el claim reservado "sub" -- PyJWT valida que "sub" sea un string (RFC 7519),
    # y user_id es un int aca (el PK entero de auth/store.py's tabla users).
    token = jwt.encode(
        {
            "user_id": user_id,
            "username": username,
            "role": role,
            # is_admin se sigue emitiendo (derivado de role) solo por compatibilidad con
            # cualquier lector viejo del token -- la fuente de verdad es "role".
            "is_admin": role == "admin",
            "exp": expires_at,
            "iss": _ISSUER,
            "aud": _AUDIENCE,
        },
        secret,
        algorithm=_ALGORITHM,
    )
    return token, expires_at


def decode_access_token(token: str, secret: str) -> TokenPayload:
    """Deja propagar jwt.PyJWTError (token expirado, firma invalida, malformado, iss/aud que no
    matchean, etc) -- la capa HTTP (auth/dependencies.py) es la que lo convierte en un 401,
    siguiendo el mismo espiritu "print/HTTP-free" que c3/ y extraction/ ya aplican para sus
    propias excepciones."""
    payload = jwt.decode(
        token, secret, algorithms=[_ALGORITHM], issuer=_ISSUER, audience=_AUDIENCE
    )
    # Tokens emitidos antes de que existiera el claim "role" (hasta 14 dias de vida) solo
    # traen is_admin -- se deriva de ahi. Igual el rol que de verdad decide el acceso se
    # re-lee de la DB (dependencies.py's _resolve_role), esto es solo el valor inicial.
    role = payload.get("role") or ("admin" if payload.get("is_admin") else "user")
    return TokenPayload(user_id=payload["user_id"], username=payload["username"], role=role)
