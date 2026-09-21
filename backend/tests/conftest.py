"""
Shared pytest fixtures, loaded automatically for every test module.

Each test gets a fresh, isolated in-memory SQLite database (never the real
radar.db, and never shared state between tests), injected into the app by
overriding the get_session dependency.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.pool import StaticPool
from sqlmodel import Session, SQLModel, create_engine

from app.database import get_session
from app.main import app


@pytest.fixture(name="session")
def session_fixture():
    # "sqlite://" with no path = in-memory database, discarded when the
    # connection closes. StaticPool forces every connection from this
    # engine to reuse the same in-memory database instead of each getting
    # its own empty one.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    SQLModel.metadata.create_all(engine)
    with Session(engine) as session:
        yield session


@pytest.fixture(name="client")
def client_fixture(session: Session):
    def get_session_override():
        return session

    app.dependency_overrides[get_session] = get_session_override
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


# --- Authentication in tests ------------------------------------------
#
# Every candidaturas/cv-base route requires a token (see app/auth.py).
# Rather than adding headers=... to each of the pre-existing tests
# individually, a test user is registered once and set as the default
# Authorization header on the shared TestClient — httpx applies default
# headers to every request made with that client, so existing tests keep
# working unmodified.
#
# Tests that need to exercise auth itself (missing token, wrong
# credentials, another user's token, ...) pass their own headers on that
# specific call, overriding the default for that request only.
EMAIL_USUARIO_DE_PRUEBA = "test@ejemplo.com"
PASSWORD_USUARIO_DE_PRUEBA = "password-de-prueba"


@pytest.fixture(name="token_usuario")
def token_usuario_fixture(client: TestClient) -> str:
    respuesta = client.post(
        "/auth/registro",
        json={"email": EMAIL_USUARIO_DE_PRUEBA, "password": PASSWORD_USUARIO_DE_PRUEBA},
    )
    assert respuesta.status_code == 201, respuesta.text
    return respuesta.json()["access_token"]


@pytest.fixture(autouse=True)
def _autenticar_client_por_defecto(client: TestClient, token_usuario: str):
    client.headers.update({"Authorization": f"Bearer {token_usuario}"})


def cabecera_auth(token: str) -> dict:
    """Helper for tests that need to set the auth header explicitly (e.g.
    to use another user's token, or none at all)."""
    return {"Authorization": f"Bearer {token}"}
