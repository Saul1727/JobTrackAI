"""
Data access layer (repository pattern), kept separate from the HTTP
routers so the query logic can be tested without an HTTP server and swapped
independently of how routes are structured.
"""
from datetime import datetime
from typing import Optional

from sqlmodel import Session, select

from app.models import Candidatura, CVBase
from app.schemas import CandidaturaCreate, CandidaturaUpdate, CVGenerado


def crear_candidatura(session: Session, datos: CandidaturaCreate, usuario_id: int) -> Candidatura:
    # Built field by field instead of unpacking the schema dict: this
    # avoids the type mismatches model_dump(mode="json") would introduce
    # (e.g. HttpUrl becoming a Url object rather than the plain string the
    # column expects).
    #
    # usuario_id always comes from the already-validated token (see
    # usuario_actual), never from the request body — otherwise a caller
    # could create records under another account's id.
    candidatura = Candidatura(
        usuario_id=usuario_id,
        empresa=datos.empresa,
        puesto=datos.puesto,
        url_oferta=str(datos.url_oferta),
        ciudad=datos.ciudad,
        salario=datos.salario,
        experiencia_requerida=datos.experiencia_requerida,
        tecnologias=datos.tecnologias,
        idiomas=datos.idiomas,
        modalidad=datos.modalidad,
        detalle_hibrido=datos.detalle_hibrido,
        tipo_contrato=datos.tipo_contrato,
        notas=datos.notas,
        fecha_seguimiento=datos.fecha_seguimiento,
        estado=datos.estado,
        fecha=datos.fecha,
    )
    session.add(candidatura)
    session.commit()
    session.refresh(candidatura)
    return candidatura


def listar_candidaturas(
    session: Session, usuario_id: int, skip: int = 0, limit: int = 100
) -> list[Candidatura]:
    return list(
        session.exec(
            select(Candidatura)
            .where(Candidatura.usuario_id == usuario_id)
            .offset(skip)
            .limit(limit)
        ).all()
    )


def obtener_candidatura(session: Session, candidatura_id: int, usuario_id: int) -> Optional[Candidatura]:
    # The ownership filter is part of the query itself, not a check applied
    # after fetching by id: a request for another user's record therefore
    # gets exactly the same "not found" result as a nonexistent id.
    return session.exec(
        select(Candidatura).where(
            Candidatura.id == candidatura_id, Candidatura.usuario_id == usuario_id
        )
    ).first()


def actualizar_candidatura(
    session: Session, candidatura: Candidatura, cambios: CandidaturaUpdate
) -> Candidatura:
    # exclude_unset=True: only fields explicitly sent by the client are
    # applied — omitted fields are left untouched rather than cleared.
    datos = cambios.model_dump(exclude_unset=True)
    for campo, valor in datos.items():
        if campo == "url_oferta" and valor is not None:
            valor = str(valor)
        setattr(candidatura, campo, valor)

    candidatura.actualizado_en = datetime.utcnow()

    session.add(candidatura)
    session.commit()
    session.refresh(candidatura)
    return candidatura


def borrar_candidatura(session: Session, candidatura: Candidatura) -> None:
    session.delete(candidatura)
    session.commit()


def obtener_cv_base(session: Session, usuario_id: int) -> Optional[CVBase]:
    return session.exec(select(CVBase).where(CVBase.usuario_id == usuario_id)).first()


def guardar_cv_base(session: Session, usuario_id: int, nombre_archivo: str, contenido_texto: str) -> CVBase:
    # Uploading replaces any existing base CV for this user.
    existente = obtener_cv_base(session, usuario_id)
    if existente is not None:
        session.delete(existente)
        session.commit()

    cv_base = CVBase(usuario_id=usuario_id, nombre_archivo=nombre_archivo, contenido_texto=contenido_texto)
    session.add(cv_base)
    session.commit()
    session.refresh(cv_base)
    return cv_base


def guardar_cv_generado(session: Session, candidatura: Candidatura, cv: CVGenerado) -> Candidatura:
    candidatura.cv_personalizado_json = cv.model_dump_json()
    candidatura.cv_generado_en = datetime.utcnow()
    session.add(candidatura)
    session.commit()
    session.refresh(candidatura)
    return candidatura
