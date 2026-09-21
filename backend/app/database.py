"""
Database connection setup, using SQLModel (SQLAlchemy + Pydantic): the
same model classes define both the table schema and request/response
validation, and queries are parameterized automatically (no manual SQL
string concatenation).
"""
from sqlmodel import Session, SQLModel, create_engine

from app.config import settings


def _url_normalizada(url: str) -> str:
    """
    Managed Postgres providers (e.g. Neon) hand out connection strings
    starting with "postgresql://", which SQLAlchemy interprets as
    psycopg2 — not installed here, since this project uses psycopg 3 (see
    requirements.txt). Normalizing the scheme here lets the connection
    string be used verbatim, exactly as provided.
    """
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    if url.startswith("postgres://"):
        # The short "postgres://" scheme (e.g. Heroku-style) isn't
        # recognized by SQLAlchemy at all.
        return url.replace("postgres://", "postgresql+psycopg://", 1)
    return url


DATABASE_URL = _url_normalizada(settings.database_url)

# El "engine" es el objeto que sabe cómo hablar con la base de datos.
# connect_args es específico de SQLite: por defecto SQLite solo permite que
# un único hilo use la misma conexión; FastAPI puede atender peticiones en
# hilos distintos, así que lo desactivamos explícitamente aquí.
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, echo=settings.debug, connect_args=connect_args)


def create_db_and_tables() -> None:
    """Crea las tablas en la base de datos si todavía no existen."""
    SQLModel.metadata.create_all(engine)


def get_session():
    """
    FastAPI dependency (used via Depends() in routes). Each HTTP request
    gets its own database session, and the "yield" pattern guarantees the
    session is closed when the request finishes, even if an error occurs
    partway through.
    """
    with Session(engine) as session:
        yield session
