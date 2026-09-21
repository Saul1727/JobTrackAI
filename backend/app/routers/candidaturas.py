"""
HTTP routes for the Candidatura resource. Each handler is intentionally
thin: it validates the request (via the schemas), delegates to crud.py,
and returns the appropriate response — no business logic lives here.
"""
import io
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from openpyxl import Workbook
from sqlmodel import Session

from app import auth, crud
from app.database import get_session
from app.models import Usuario
from app.schemas import (
    CandidaturaCreate,
    CandidaturaExtraerRequest,
    CandidaturaRead,
    CandidaturaUpdate,
    CVGenerado,
)
from app.services import extraccion_ia, generacion_cv
from app.services.pdf_cv import generar_pdf_cv

router = APIRouter(prefix="/candidaturas", tags=["candidaturas"])


@router.post("/", response_model=CandidaturaRead, status_code=status.HTTP_201_CREATED)
def crear(
    datos: CandidaturaCreate,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    return crud.crear_candidatura(session, datos, usuario.id)


@router.post("/extraer", response_model=CandidaturaRead, status_code=status.HTTP_201_CREATED)
def extraer_y_crear(
    datos: CandidaturaExtraerRequest,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    """
    Called by the Chrome extension: receives the offer URL and page text,
    asks the AI service to extract the structured fields, and creates the
    record with whatever was found. Fields the AI could not find are left
    blank (empresa/puesto fall back to a placeholder since the model
    requires them) — always editable afterwards, creation is never blocked
    on incomplete extraction.
    """
    try:
        extraido = extraccion_ia.extraer_datos_oferta(str(datos.url), datos.contenido_pagina)
    except extraccion_ia.ExtraccionIAError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo extraer los datos automáticamente: {exc}",
        ) from exc

    candidatura_nueva = CandidaturaCreate(
        empresa=extraido.empresa or "Por revisar",
        puesto=extraido.puesto or "Por revisar",
        url_oferta=datos.url,
        ciudad=extraido.ciudad,
        salario=extraido.salario,
        tipo_contrato=extraido.tipo_contrato,
        experiencia_requerida=extraido.experiencia_requerida,
        tecnologias=extraido.tecnologias,
        idiomas=extraido.idiomas,
        modalidad=extraido.modalidad,
        detalle_hibrido=extraido.detalle_hibrido,
        fecha=date.today(),
    )
    return crud.crear_candidatura(session, candidatura_nueva, usuario.id)


@router.get("/", response_model=list[CandidaturaRead])
def listar(
    skip: int = 0,
    limit: int = 100,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    return crud.listar_candidaturas(session, usuario.id, skip=skip, limit=limit)


@router.get("/exportar")
def exportar_excel(
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    """
    Streams all of the current user's records as an in-memory .xlsx file.

    Declared before "/{candidatura_id}" so that FastAPI's path matching
    (routes are tried in declaration order) doesn't interpret "exportar"
    as a candidatura id.
    """
    candidaturas = crud.listar_candidaturas(session, usuario.id, skip=0, limit=10_000)

    libro = Workbook()
    hoja = libro.active
    hoja.title = "Candidaturas"
    hoja.append(
        [
            "Empresa", "Puesto", "Ciudad", "Salario", "Tipo de contrato", "Experiencia",
            "Tecnologías", "Idiomas", "Modalidad", "Detalle híbrido", "Notas",
            "Seguimiento", "Estado", "Fecha", "URL", "Creado", "Actualizado",
        ]
    )
    for c in candidaturas:
        hoja.append(
            [
                c.empresa,
                c.puesto,
                c.ciudad or "",
                c.salario or "",
                c.tipo_contrato or "",
                c.experiencia_requerida or "",
                c.tecnologias or "",
                c.idiomas or "",
                c.modalidad.value if c.modalidad else "",
                c.detalle_hibrido or "",
                c.notas or "",
                str(c.fecha_seguimiento) if c.fecha_seguimiento else "",
                c.estado.value,
                str(c.fecha),
                c.url_oferta,
                str(c.creado_en),
                str(c.actualizado_en),
            ]
        )

    buffer = io.BytesIO()
    libro.save(buffer)
    buffer.seek(0)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=candidaturas.xlsx"},
    )


@router.get("/{candidatura_id}", response_model=CandidaturaRead)
def obtener(
    candidatura_id: int,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    candidatura = crud.obtener_candidatura(session, candidatura_id, usuario.id)
    if candidatura is None:
        # Same 404 whether the id doesn't exist or belongs to another
        # user — the response never reveals which case applies.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidatura no encontrada")
    return candidatura


@router.patch("/{candidatura_id}", response_model=CandidaturaRead)
def actualizar(
    candidatura_id: int,
    cambios: CandidaturaUpdate,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    candidatura = crud.obtener_candidatura(session, candidatura_id, usuario.id)
    if candidatura is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidatura no encontrada")
    return crud.actualizar_candidatura(session, candidatura, cambios)


@router.delete("/{candidatura_id}", status_code=status.HTTP_204_NO_CONTENT)
def borrar(
    candidatura_id: int,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    candidatura = crud.obtener_candidatura(session, candidatura_id, usuario.id)
    if candidatura is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidatura no encontrada")
    crud.borrar_candidatura(session, candidatura)


@router.post("/{candidatura_id}/generar-cv", response_model=CVGenerado)
def generar_cv(
    candidatura_id: int,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    """Generates (or regenerates, overwriting the previous version) a CV
    tailored to this application, from the user's base CV and the fields
    already extracted from the job offer."""
    candidatura = crud.obtener_candidatura(session, candidatura_id, usuario.id)
    if candidatura is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidatura no encontrada")

    cv_base = crud.obtener_cv_base(session, usuario.id)
    if cv_base is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Todavía no se ha subido ningún CV base.",
        )

    datos_oferta = {
        "empresa": candidatura.empresa,
        "puesto": candidatura.puesto,
        "experiencia_requerida": candidatura.experiencia_requerida,
        "tecnologias": candidatura.tecnologias,
        "idiomas": candidatura.idiomas,
    }

    try:
        cv_generado = generacion_cv.generar_cv_personalizado(cv_base.contenido_texto, datos_oferta)
    except generacion_cv.GeneracionCVError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"No se pudo generar el CV: {exc}",
        ) from exc

    crud.guardar_cv_generado(session, candidatura, cv_generado)
    return cv_generado


@router.get("/{candidatura_id}/cv", response_model=CVGenerado)
def obtener_cv_generado(
    candidatura_id: int,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    """Latest generated CV for this application."""
    candidatura = crud.obtener_candidatura(session, candidatura_id, usuario.id)
    if candidatura is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidatura no encontrada")
    if not candidatura.cv_personalizado_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todavía no se ha generado un CV para esta candidatura.",
        )
    return CVGenerado.model_validate_json(candidatura.cv_personalizado_json)


@router.patch("/{candidatura_id}/cv", response_model=CVGenerado)
def editar_cv_generado(
    candidatura_id: int,
    cv: CVGenerado,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    """Saves manual edits made to a generated CV (overwrites the previous version)."""
    candidatura = crud.obtener_candidatura(session, candidatura_id, usuario.id)
    if candidatura is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidatura no encontrada")
    crud.guardar_cv_generado(session, candidatura, cv)
    return cv


@router.get("/{candidatura_id}/cv/pdf")
def descargar_cv_pdf(
    candidatura_id: int,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    candidatura = crud.obtener_candidatura(session, candidatura_id, usuario.id)
    if candidatura is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Candidatura no encontrada")
    if not candidatura.cv_personalizado_json:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todavía no se ha generado un CV para esta candidatura.",
        )

    cv = CVGenerado.model_validate_json(candidatura.cv_personalizado_json)
    pdf_bytes = generar_pdf_cv(cv)

    nombre_archivo = f"CV_{candidatura.empresa}_{candidatura.puesto}.pdf".replace(" ", "_")
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{nombre_archivo}"'},
    )
