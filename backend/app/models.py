"""
Database models: Usuario and Candidatura.

Each SQLModel class here defines both the database table schema (via
table=True) and a Pydantic-validated model. These are deliberately not
exposed directly by the API — see schemas.py for the separate models used
at the API boundary, so that internal columns never leak into responses
by accident.
"""
from datetime import date, datetime
from enum import Enum
from typing import Optional

from sqlmodel import Field, SQLModel


class Usuario(SQLModel, table=True):
    """One row per registered account. "email" is unique at the database
    level (not just checked in Python) to rule out a race condition
    between two concurrent registration requests."""

    id: Optional[int] = Field(default=None, primary_key=True)
    email: str = Field(unique=True, index=True, max_length=255)
    password_hash: str
    creado_en: datetime = Field(default_factory=datetime.utcnow)


class EstadoCandidatura(str, Enum):
    """Closed set of values, enforced at both the database and API layer."""

    GUARDADA = "guardada"
    APLICADO = "aplicado"
    ENTREVISTA = "entrevista"
    OFERTA = "oferta"
    RECHAZADO = "rechazado"


class ModalidadTrabajo(str, Enum):
    PRESENCIAL = "presencial"
    REMOTO = "remoto"
    HIBRIDO = "hibrido"


class Candidatura(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    # Owning user. Indexed because every listing query filters on it (see
    # crud.listar_candidaturas).
    usuario_id: int = Field(foreign_key="usuario.id", index=True)

    empresa: str = Field(index=True, max_length=200)
    puesto: str = Field(max_length=200)
    url_oferta: str = Field(max_length=2048)
    ciudad: Optional[str] = Field(default=None, max_length=120)

    # Free text: salary ranges, "negotiable", etc. don't fit a numeric
    # column, and None (not a sentinel string) means "not specified".
    salario: Optional[str] = Field(default=None, max_length=120)

    experiencia_requerida: Optional[str] = Field(default=None, max_length=200)
    tecnologias: Optional[str] = Field(default=None, max_length=500)  # comma-separated
    idiomas: Optional[str] = Field(default=None, max_length=300)

    modalidad: Optional[ModalidadTrabajo] = Field(default=None)
    # Only meaningful when modalidad is "hibrido" (e.g. "3 days office, 2
    # remote"). Left unvalidated at the database level — a cross-field
    # constraint here would add more complexity than it is worth.
    detalle_hibrido: Optional[str] = Field(default=None, max_length=200)

    tipo_contrato: Optional[str] = Field(default=None, max_length=120)

    # Never populated by the AI extraction step — user-entered tracking
    # fields only.
    notas: Optional[str] = Field(default=None, max_length=2000)
    fecha_seguimiento: Optional[date] = Field(default=None)

    estado: EstadoCandidatura = Field(default=EstadoCandidatura.GUARDADA)
    fecha: date

    # The generated CV is stored as a JSON blob (structure defined in
    # schemas.CVGenerado) rather than its own table: only the latest
    # version per application is kept, so a new generation simply
    # overwrites the previous one.
    cv_personalizado_json: Optional[str] = Field(default=None)
    cv_generado_en: Optional[datetime] = Field(default=None)

    creado_en: datetime = Field(default_factory=datetime.utcnow)
    actualizado_en: datetime = Field(default_factory=datetime.utcnow)


class CVBase(SQLModel, table=True):
    """
    The template CV a user uploads once (and can re-upload to replace).
    Only the text extracted from the file is stored — never the original
    file — since it is only ever used as AI context, never served back as
    a download.

    At most one row exists per user; uploading a new file replaces the
    previous one (enforced in crud.guardar_cv_base).
    """

    id: Optional[int] = Field(default=None, primary_key=True)
    usuario_id: int = Field(foreign_key="usuario.id", unique=True, index=True)
    nombre_archivo: str = Field(max_length=255)
    contenido_texto: str
    subido_en: datetime = Field(default_factory=datetime.utcnow)
