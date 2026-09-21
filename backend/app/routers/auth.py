"""
Authentication routes: register, log in, and "who am I". These are the
only routes that don't require an existing session — every other route
depends on auth.usuario_actual.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlmodel import Session, select

from app import auth
from app.database import get_session
from app.models import Usuario
from app.schemas import Token, UsuarioCreate, UsuarioLogin, UsuarioRead

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/registro", response_model=Token, status_code=status.HTTP_201_CREATED)
def registrar(datos: UsuarioCreate, session: Session = Depends(get_session)):
    ya_existe = session.exec(select(Usuario).where(Usuario.email == datos.email)).first()
    if ya_existe is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Ya existe una cuenta con ese email.",
        )

    usuario = Usuario(email=datos.email, password_hash=auth.hash_password(datos.password))
    session.add(usuario)
    session.commit()
    session.refresh(usuario)

    return Token(access_token=auth.crear_token(usuario.id))


@router.post("/login", response_model=Token)
def iniciar_sesion(datos: UsuarioLogin, session: Session = Depends(get_session)):
    usuario = session.exec(select(Usuario).where(Usuario.email == datos.email)).first()

    # Same generic error for "unknown email" and "wrong password", so the
    # login endpoint can't be used to enumerate registered accounts.
    credenciales_invalidas = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Email o contraseña incorrectos.",
    )
    if usuario is None or not auth.verificar_password(datos.password, usuario.password_hash):
        raise credenciales_invalidas

    return Token(access_token=auth.crear_token(usuario.id))


@router.get("/yo", response_model=UsuarioRead)
def quien_soy(usuario: Usuario = Depends(auth.usuario_actual)):
    """Used by clients to validate a stored token and to display the
    active account without decoding the JWT themselves."""
    return usuario
