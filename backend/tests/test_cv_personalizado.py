"""
Tests de la generación, edición y descarga en PDF del CV personalizado por
candidatura. Igual que en test_extraccion.py: nunca llamamos a Gemini de
verdad — se sustituye con monkeypatch por una función falsa que devuelve
un CVGenerado fijo, para que el test no dependa de la red ni del servicio.
"""
import io
from datetime import date

from reportlab.pdfgen import canvas

from app.schemas import CVGenerado, SeccionExperiencia
from app.services import generacion_cv


def _pdf_de_prueba(texto="Backend developer con experiencia en Python y FastAPI"):
    buffer = io.BytesIO()
    lienzo = canvas.Canvas(buffer)
    lienzo.drawString(100, 750, texto)
    lienzo.save()
    return buffer.getvalue()


def _crear_candidatura(client):
    datos = {
        "empresa": "ACME Corp",
        "puesto": "Backend Developer",
        "url_oferta": "https://ejemplo.com/oferta/123",
        "tecnologias": "Python, FastAPI",
        "fecha": str(date.today()),
    }
    return client.post("/candidaturas/", json=datos).json()


def _subir_cv_base(client):
    client.post("/cv-base/", files={"archivo": ("cv.pdf", _pdf_de_prueba(), "application/pdf")})


def _cv_falso() -> CVGenerado:
    return CVGenerado(
        nombre="Saúl Alcázar",
        email="saul@ejemplo.com",
        resumen="Backend developer con experiencia en Python.",
        experiencia=[
            SeccionExperiencia(
                puesto="Backend Developer",
                empresa="Empresa Anterior",
                fechas="2023 - Actualidad",
                logros=["Redujo el tiempo de respuesta en un 30%"],
            ),
        ],
        habilidades=["Python", "FastAPI"],
        idiomas=["Español nativo"],
    )


def test_generar_cv_sin_cv_base_da_400(client):
    candidatura = _crear_candidatura(client)

    respuesta = client.post(f"/candidaturas/{candidatura['id']}/generar-cv")

    assert respuesta.status_code == 400


def test_generar_cv_candidatura_inexistente_da_404(client):
    respuesta = client.post("/candidaturas/9999/generar-cv")

    assert respuesta.status_code == 404


def test_generar_cv_con_cv_base(client, monkeypatch):
    _subir_cv_base(client)
    candidatura = _crear_candidatura(client)
    monkeypatch.setattr(
        generacion_cv, "generar_cv_personalizado", lambda cv_base_texto, datos_oferta: _cv_falso()
    )

    respuesta = client.post(f"/candidaturas/{candidatura['id']}/generar-cv")

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["nombre"] == "Saúl Alcázar"
    assert cuerpo["experiencia"][0]["puesto"] == "Backend Developer"


def test_generar_cv_falla_da_503(client, monkeypatch):
    _subir_cv_base(client)
    candidatura = _crear_candidatura(client)

    def falla(cv_base_texto, datos_oferta):
        raise generacion_cv.GeneracionCVError("clave no configurada")

    monkeypatch.setattr(generacion_cv, "generar_cv_personalizado", falla)

    respuesta = client.post(f"/candidaturas/{candidatura['id']}/generar-cv")

    assert respuesta.status_code == 503


def test_obtener_cv_antes_de_generar_da_404(client):
    candidatura = _crear_candidatura(client)

    respuesta = client.get(f"/candidaturas/{candidatura['id']}/cv")

    assert respuesta.status_code == 404


def test_obtener_y_editar_cv_generado(client, monkeypatch):
    _subir_cv_base(client)
    candidatura = _crear_candidatura(client)
    monkeypatch.setattr(
        generacion_cv, "generar_cv_personalizado", lambda cv_base_texto, datos_oferta: _cv_falso()
    )
    client.post(f"/candidaturas/{candidatura['id']}/generar-cv")

    respuesta_get = client.get(f"/candidaturas/{candidatura['id']}/cv")
    assert respuesta_get.status_code == 200
    assert respuesta_get.json()["nombre"] == "Saúl Alcázar"

    cv_editado = respuesta_get.json()
    cv_editado["resumen"] = "Resumen editado a mano"
    respuesta_patch = client.patch(f"/candidaturas/{candidatura['id']}/cv", json=cv_editado)

    assert respuesta_patch.status_code == 200
    assert respuesta_patch.json()["resumen"] == "Resumen editado a mano"


def test_descargar_pdf_sin_cv_generado_da_404(client):
    candidatura = _crear_candidatura(client)

    respuesta = client.get(f"/candidaturas/{candidatura['id']}/cv/pdf")

    assert respuesta.status_code == 404


def test_descargar_pdf_del_cv_generado(client, monkeypatch):
    _subir_cv_base(client)
    candidatura = _crear_candidatura(client)
    monkeypatch.setattr(
        generacion_cv, "generar_cv_personalizado", lambda cv_base_texto, datos_oferta: _cv_falso()
    )
    client.post(f"/candidaturas/{candidatura['id']}/generar-cv")

    respuesta = client.get(f"/candidaturas/{candidatura['id']}/cv/pdf")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == "application/pdf"
    assert respuesta.content[:4] == b"%PDF"
