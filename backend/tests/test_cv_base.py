"""
Tests del CV base (POST/GET /cv-base/) — el que subes una vez en PDF o
Word y que la IA usa como punto de partida real para cada CV personalizado.

Para no depender de un PDF/DOCX real guardado en el repo, generamos
archivos mínimos válidos aquí mismo con reportlab y python-docx (las
mismas librerías que ya usa la propia aplicación).
"""
import io

from docx import Document
from reportlab.pdfgen import canvas


def _pdf_de_prueba(texto="Ingeniero de software con experiencia en Python"):
    buffer = io.BytesIO()
    lienzo = canvas.Canvas(buffer)
    lienzo.drawString(100, 750, texto)
    lienzo.save()
    return buffer.getvalue()


def _docx_de_prueba(texto="Ingeniero de software con experiencia en Python"):
    documento = Document()
    documento.add_paragraph(texto)
    buffer = io.BytesIO()
    documento.save(buffer)
    return buffer.getvalue()


def test_subir_cv_base_pdf(client):
    respuesta = client.post(
        "/cv-base/",
        files={"archivo": ("mi_cv.pdf", _pdf_de_prueba(), "application/pdf")},
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["nombre_archivo"] == "mi_cv.pdf"


def test_subir_cv_base_docx(client):
    respuesta = client.post(
        "/cv-base/",
        files={
            "archivo": (
                "mi_cv.docx",
                _docx_de_prueba(),
                "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        },
    )

    assert respuesta.status_code == 201
    assert respuesta.json()["nombre_archivo"] == "mi_cv.docx"


def test_subir_cv_base_formato_no_soportado_da_422(client):
    # .txt no es ni PDF ni Word — debe rechazarse por la extensión, sin
    # llegar siquiera a intentar leer el contenido.
    respuesta = client.post(
        "/cv-base/",
        files={"archivo": ("mi_cv.txt", b"solo texto plano", "text/plain")},
    )

    assert respuesta.status_code == 422


def test_obtener_cv_base_sin_subir_da_404(client):
    respuesta = client.get("/cv-base/")

    assert respuesta.status_code == 404


def test_subir_cv_base_reemplaza_el_anterior(client):
    # Solo existe un CV base a la vez: subir uno nuevo debe sustituir al
    # anterior, no acumularlos.
    client.post("/cv-base/", files={"archivo": ("primero.pdf", _pdf_de_prueba(), "application/pdf")})
    client.post("/cv-base/", files={"archivo": ("segundo.pdf", _pdf_de_prueba(), "application/pdf")})

    respuesta = client.get("/cv-base/")

    assert respuesta.status_code == 200
    assert respuesta.json()["nombre_archivo"] == "segundo.pdf"
