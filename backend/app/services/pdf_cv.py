"""
Renderiza un CVGenerado (ver schemas.py) como un PDF descargable, en un
formato "Harvard" simple y compatible con ATS.

Usamos reportlab construyendo el documento pieza a pieza (párrafo a
párrafo) en vez de, por ejemplo, generar HTML y convertirlo a PDF. Dos
motivos:
  1. Dependencias mínimas: reportlab es una única librería de Python
     pura, sin depender de un motor de renderizado HTML aparte.
  2. Control total del resultado: un CV "ATS-friendly" tiene que ser
     estrictamente una sola columna de texto normal, sin tablas ni cajas
     flotantes — construyéndolo pieza a pieza es imposible que se cuele
     algo que un sistema ATS no sepa leer.
"""
import io
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import HRFlowable, Paragraph, SimpleDocTemplate, Spacer

from app.schemas import CVGenerado

GRIS = colors.HexColor("#555555")
LINEA = colors.HexColor("#aaaaaa")

ESTILO_NOMBRE = ParagraphStyle(
    "Nombre", fontName="Helvetica-Bold", fontSize=18, leading=22, alignment=TA_LEFT,
)
ESTILO_CONTACTO = ParagraphStyle(
    "Contacto", fontName="Helvetica", fontSize=9.5, leading=13, textColor=GRIS,
)
ESTILO_SECCION = ParagraphStyle(
    "Seccion", fontName="Helvetica-Bold", fontSize=11.5, leading=14, spaceBefore=12, spaceAfter=2,
)
ESTILO_CUERPO = ParagraphStyle(
    "Cuerpo", fontName="Helvetica", fontSize=10, leading=13.5, spaceAfter=3,
)
ESTILO_SUBTITULO = ParagraphStyle(
    "Subtitulo", fontName="Helvetica-Bold", fontSize=10, leading=13, spaceBefore=6,
)


def _esc(texto: str) -> str:
    # reportlab interpreta el texto de un Paragraph como un mini-XML
    # propio (p.ej. <b>negrita</b>) — sin escapar, un "&" o "<" sueltos en
    # un nombre de empresa ("AT&T", por ejemplo) rompería el renderizado.
    return escape(texto or "")


def generar_pdf_cv(cv: CVGenerado) -> bytes:
    buffer = io.BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=2 * cm,
        rightMargin=2 * cm,
        topMargin=1.5 * cm,
        bottomMargin=1.5 * cm,
        title=f"CV - {cv.nombre}",
    )

    elementos = [Paragraph(_esc(cv.nombre), ESTILO_NOMBRE)]

    contacto = " · ".join(_esc(dato) for dato in [cv.email, cv.telefono, cv.ubicacion, cv.linkedin] if dato)
    if contacto:
        elementos.append(Spacer(1, 2))
        elementos.append(Paragraph(contacto, ESTILO_CONTACTO))

    def seccion(titulo: str):
        elementos.append(Paragraph(titulo, ESTILO_SECCION))
        elementos.append(HRFlowable(width="100%", thickness=0.6, color=LINEA, spaceAfter=4))

    if cv.resumen:
        seccion("RESUMEN")
        elementos.append(Paragraph(_esc(cv.resumen), ESTILO_CUERPO))

    if cv.experiencia:
        seccion("EXPERIENCIA")
        for exp in cv.experiencia:
            elementos.append(Paragraph(f"{_esc(exp.puesto)} — {_esc(exp.empresa)}", ESTILO_SUBTITULO))
            pie = _esc(exp.fechas) + (f" · {_esc(exp.ubicacion)}" if exp.ubicacion else "")
            elementos.append(Paragraph(pie, ESTILO_CONTACTO))
            for logro in exp.logros:
                elementos.append(Paragraph(f"• {_esc(logro)}", ESTILO_CUERPO))

    if cv.educacion:
        seccion("EDUCACIÓN")
        for edu in cv.educacion:
            elementos.append(Paragraph(f"{_esc(edu.titulo)} — {_esc(edu.institucion)}", ESTILO_SUBTITULO))
            pie = _esc(edu.fechas) + (f" · {_esc(edu.detalle)}" if edu.detalle else "")
            elementos.append(Paragraph(pie, ESTILO_CONTACTO))

    if cv.habilidades:
        seccion("HABILIDADES")
        elementos.append(Paragraph(_esc(", ".join(cv.habilidades)), ESTILO_CUERPO))

    if cv.idiomas:
        seccion("IDIOMAS")
        elementos.append(Paragraph(_esc(", ".join(cv.idiomas)), ESTILO_CUERPO))

    documento.build(elementos)
    return buffer.getvalue()
