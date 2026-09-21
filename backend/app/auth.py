"""
Authentication: password hashing and stateless (JWT) sessions.

JWT is used instead of server-side sessions because the API is consumed by
two independent clients (the Chrome extension and the web panel) that each
store the token themselves (chrome.storage / localStorage) and send it on
every request. The server does not need to keep any session state —
verifying the signature is enough to know who is calling and that the
token has not been tampered with.
"""
from datetime import datetime, timedelta, timezone
from typing import Optional

import bcrypt
import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlmodel import Session

from app.config import settings
from app.database import get_session
from app.models import Usuario

ALGORITMO_JWT = "HS256"


def hash_password(password: str) -> str:
    """
    Hashes a password with bcrypt (which generates and embeds its own
    random salt, so two hashes of the same password never match).

    Note: bcrypt only considers the first 72 bytes of the input — a
    limitation of the algorithm itself, irrelevant for any realistic
    password length.
    """
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verificar_password(password: str, password_hash: str) -> bool:
    return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))


def crear_token(usuario_id: int) -> str:
    """"sub" is stored as a string because that is what the JWT spec requires,
    even though it is an int in the database."""
    expira = datetime.now(timezone.utc) + timedelta(minutes=settings.jwt_expira_minutos)
    payload = {"sub": str(usuario_id), "exp": expira}
    return jwt.encode(payload, settings.secret_key, algorithm=ALGORITMO_JWT)


# tokenUrl only tells the interactive docs (/docs) which route to request a
# token from via the "Authorize" button; it has no effect on how tokens are
# validated below. auto_error=False lets usuario_actual() raise its own 401
# with a custom message instead of FastAPI's generic one.
_esquema_token = OAuth2PasswordBearer(tokenUrl="/auth/login", auto_error=False)


def usuario_actual(
    token: Optional[str] = Depends(_esquema_token),
    session: Session = Depends(get_session),
) -> Usuario:
    """
    Dependency that protects a route: use it as
    `usuario: Usuario = Depends(usuario_actual)` on any endpoint that
    requires an authenticated user.
    """
    error_credenciales = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No autenticado, o la sesión ha caducado.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if token is None:
        raise error_credenciales

    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITMO_JWT])
        usuario_id = int(payload["sub"])
    except (jwt.PyJWTError, KeyError, ValueError):
        # A malformed/tampered signature and an expired token both raise
        # here; both map to the same generic error so no information is
        # leaked about which case applies.
        raise error_credenciales from None

    usuario = session.get(Usuario, usuario_id)
    if usuario is None:
        # Valid token for a user that no longer exists — same generic
        # error, for the same reason.
        raise error_credenciales
    return usuario
