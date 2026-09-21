"""
Extracts text from a PDF, used to read an uploaded base CV before storing
it (only the extracted text is kept, never the original file — see
models.CVBase).
"""
import io

from pypdf import PdfReader


class ExtraccionPDFError(Exception):
    """El PDF no se pudo abrir, o no tiene texto extraíble."""


def extraer_texto_pdf(contenido_pdf: bytes) -> str:
    """
    Recibe los bytes crudos de un PDF y devuelve su texto. Lanza
    ExtraccionPDFError si el archivo está corrupto, no es un PDF de
    verdad, o no tiene ni una palabra de texto seleccionable (un CV
    escaneado como foto/imagen, por ejemplo — pypdf no hace OCR).
    """
    try:
        lector = PdfReader(io.BytesIO(contenido_pdf))
        texto = "\n".join(pagina.extract_text() or "" for pagina in lector.pages)
    except Exception as exc:  # pypdf can raise several exception types
        raise ExtraccionPDFError(f"No se pudo leer el PDF: {exc}") from exc

    texto = texto.strip()
    if not texto:
        raise ExtraccionPDFError(
            "El PDF no contiene texto seleccionable — ¿es una imagen escaneada?"
        )
    return texto
