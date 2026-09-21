"""
Routes for the "base" CV: the file a user uploads once (and can re-upload
to update) that the AI uses as the starting point for each tailored CV.
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, status
from sqlmodel import Session

from app import auth, crud
from app.database import get_session
from app.models import Usuario
from app.schemas import CVBaseRead
from app.services.extraer_texto_docx import ExtraccionDOCXError, extraer_texto_docx
from app.services.extraer_texto_pdf import ExtraccionPDFError, extraer_texto_pdf

router = APIRouter(prefix="/cv-base", tags=["cv-base"])


def _tipo_por_extension(nombre_archivo: str) -> str | None:
    # Determined from the filename extension rather than the browser's
    # reported content_type, which is unreliable for .docx (some
    # browsers/OSes send a generic application/octet-stream instead).
    nombre = (nombre_archivo or "").lower()
    if nombre.endswith(".pdf"):
        return "pdf"
    if nombre.endswith(".docx"):
        return "docx"
    return None


@router.post("/", response_model=CVBaseRead, status_code=status.HTTP_201_CREATED)
async def subir_cv_base(
    archivo: UploadFile,
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    tipo = _tipo_por_extension(archivo.filename or "")
    if tipo is None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Solo se aceptan archivos PDF (.pdf) o Word (.docx).",
        )

    contenido = await archivo.read()
    try:
        if tipo == "pdf":
            texto = extraer_texto_pdf(contenido)
        else:
            texto = extraer_texto_docx(contenido)
    except (ExtraccionPDFError, ExtraccionDOCXError) as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    return crud.guardar_cv_base(session, usuario.id, archivo.filename or f"cv.{tipo}", texto)


@router.get("/", response_model=CVBaseRead)
def obtener_cv_base(
    session: Session = Depends(get_session),
    usuario: Usuario = Depends(auth.usuario_actual),
):
    cv_base = crud.obtener_cv_base(session, usuario.id)
    if cv_base is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Todavía no se ha subido ningún CV base.",
        )
    return cv_base
