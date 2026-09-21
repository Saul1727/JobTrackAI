"""
API schemas (DTOs), kept separate from the database models in models.py:
request bodies should not be able to set server-controlled fields like
"id" or timestamps, updates are typically partial, and internal columns
should never leak into a response just because they exist on the table.
"""
from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, EmailStr, HttpUrl, field_validator

from app.models import EstadoCandidatura, ModalidadTrabajo


class UsuarioCreate(BaseModel):
    email: EmailStr
    password: str

    @field_validator("password")
    @classmethod
    def password_minima(cls, valor: str) -> str:
        if len(valor) < 8:
            raise ValueError("La contraseña debe tener al menos 8 caracteres.")
        return valor


class UsuarioLogin(BaseModel):
    email: EmailStr
    password: str


class UsuarioRead(BaseModel):
    """Never includes password_hash."""

    id: int
    email: str
    creado_en: datetime

    model_config = ConfigDict(from_attributes=True)


class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class CandidaturaCreate(BaseModel):
    empresa: str
    puesto: str
    url_oferta: HttpUrl
    ciudad: Optional[str] = None
    salario: Optional[str] = None
    experiencia_requerida: Optional[str] = None
    tecnologias: Optional[str] = None
    idiomas: Optional[str] = None
    modalidad: Optional[ModalidadTrabajo] = None
    detalle_hibrido: Optional[str] = None
    tipo_contrato: Optional[str] = None
    notas: Optional[str] = None
    fecha_seguimiento: Optional[date] = None
    # Saving an offer is not the same as having applied to it.
    estado: EstadoCandidatura = EstadoCandidatura.GUARDADA
    fecha: date


class CandidaturaUpdate(BaseModel):
    """All fields optional: the client sends only what it wants to change."""

    empresa: Optional[str] = None
    puesto: Optional[str] = None
    url_oferta: Optional[HttpUrl] = None
    ciudad: Optional[str] = None
    salario: Optional[str] = None
    experiencia_requerida: Optional[str] = None
    tecnologias: Optional[str] = None
    idiomas: Optional[str] = None
    modalidad: Optional[ModalidadTrabajo] = None
    detalle_hibrido: Optional[str] = None
    tipo_contrato: Optional[str] = None
    notas: Optional[str] = None
    fecha_seguimiento: Optional[date] = None
    estado: Optional[EstadoCandidatura] = None
    fecha: Optional[date] = None


class CandidaturaExtraerRequest(BaseModel):
    """Sent by the Chrome extension: the offer's URL and the page text
    already loaded in the browser tab, so the backend never has to fetch
    the page itself (many job boards block non-browser requests)."""

    url: HttpUrl
    contenido_pagina: str


class CandidaturaRead(BaseModel):
    id: int
    empresa: str
    puesto: str
    url_oferta: str
    ciudad: Optional[str]
    salario: Optional[str]
    experiencia_requerida: Optional[str]
    tecnologias: Optional[str]
    idiomas: Optional[str]
    modalidad: Optional[ModalidadTrabajo]
    detalle_hibrido: Optional[str]
    tipo_contrato: Optional[str]
    notas: Optional[str]
    fecha_seguimiento: Optional[date]
    estado: EstadoCandidatura
    fecha: date
    # cv_personalizado_json is intentionally excluded here — listing
    # endpoints don't need the full generated CV, only whether one exists.
    cv_generado_en: Optional[datetime]
    creado_en: datetime
    actualizado_en: datetime

    model_config = ConfigDict(from_attributes=True)


class CVBaseRead(BaseModel):
    nombre_archivo: str
    subido_en: datetime

    model_config = ConfigDict(from_attributes=True)


class SeccionExperiencia(BaseModel):
    puesto: str
    empresa: str
    fechas: str
    ubicacion: Optional[str] = None
    logros: list[str] = []


class SeccionEducacion(BaseModel):
    titulo: str
    institucion: str
    fechas: str
    detalle: Optional[str] = None


class CVGenerado(BaseModel):
    """
    A personalized CV in "Harvard" format: standard sections, plain text,
    no tables or images, so any ATS (applicant tracking system) can parse
    it reliably. Used both as the schema requested from the AI model and
    as the shape edited in the web panel.
    """

    nombre: str
    email: Optional[str] = None
    telefono: Optional[str] = None
    ubicacion: Optional[str] = None
    linkedin: Optional[str] = None
    resumen: str = ""
    experiencia: list[SeccionExperiencia] = []
    educacion: list[SeccionEducacion] = []
    habilidades: list[str] = []
    idiomas: list[str] = []
