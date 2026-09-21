"""
Tests del endpoint de extracción por IA (POST /candidaturas/extraer).

Importante: estos tests NUNCA llaman a la Gemini real. Eso costaría
tiempo, dinero (aunque sea poco) y haría los tests poco fiables (podrían
fallar por un corte de red, no por un bug tuyo). En su lugar,
"sustituimos" la función que llama a Gemini por una falsa que devuelve
justo lo que queremos probar — es el mismo patrón de
app.dependency_overrides que viste en conftest.py, pero aplicado a mano
con monkeypatch en vez de con Depends().
"""
from app.services import extraccion_ia


def test_extraer_crea_candidatura_con_datos_encontrados(client, monkeypatch):
    resultado_falso = extraccion_ia.OfertaExtraida(
        empresa="ACME Corp",
        puesto="Backend Developer",
        ciudad="Valencia",
        salario="30000-35000",
    )
    monkeypatch.setattr(extraccion_ia, "extraer_datos_oferta", lambda url, texto: resultado_falso)

    respuesta = client.post(
        "/candidaturas/extraer",
        json={"url": "https://ejemplo.com/oferta/123", "contenido_pagina": "texto de la oferta..."},
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["empresa"] == "ACME Corp"
    assert cuerpo["puesto"] == "Backend Developer"
    assert cuerpo["ciudad"] == "Valencia"
    # "guardada", no "aplicado": encontrar y guardar una oferta no es lo
    # mismo que haber aplicado a ella. La IA nunca decide el estado.
    assert cuerpo["estado"] == "guardada"


def test_extraer_traspasa_los_campos_nuevos(client, monkeypatch):
    resultado_falso = extraccion_ia.OfertaExtraida(
        empresa="ACME Corp",
        puesto="Backend Developer",
        tipo_contrato="Tiempo completo",
        experiencia_requerida="Junior",
        tecnologias="Python, FastAPI",
        idiomas="Inglés B2",
        modalidad=extraccion_ia.ModalidadTrabajo.HIBRIDO,
        detalle_hibrido="3 días oficina, 2 remoto",
    )
    monkeypatch.setattr(extraccion_ia, "extraer_datos_oferta", lambda url, texto: resultado_falso)

    respuesta = client.post(
        "/candidaturas/extraer",
        json={"url": "https://ejemplo.com/oferta/999", "contenido_pagina": "texto de la oferta..."},
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["tipo_contrato"] == "Tiempo completo"
    assert cuerpo["experiencia_requerida"] == "Junior"
    assert cuerpo["tecnologias"] == "Python, FastAPI"
    assert cuerpo["idiomas"] == "Inglés B2"
    assert cuerpo["modalidad"] == "hibrido"
    assert cuerpo["detalle_hibrido"] == "3 días oficina, 2 remoto"
    # notas y fecha_seguimiento son SOLO tuyas — nunca deben venir
    # rellenas por la IA, ni aunque el texto de la oferta las sugiriese.
    assert cuerpo["notas"] is None
    assert cuerpo["fecha_seguimiento"] is None


def test_extraer_con_datos_incompletos_usa_por_revisar(client, monkeypatch):
    # La IA no siempre encuentra todo — empresa/puesto son obligatorios en
    # el modelo, así que deben caer al placeholder en vez de romper la
    # creación de la candidatura.
    resultado_falso = extraccion_ia.OfertaExtraida(empresa=None, puesto=None, ciudad=None, salario=None)
    monkeypatch.setattr(extraccion_ia, "extraer_datos_oferta", lambda url, texto: resultado_falso)

    respuesta = client.post(
        "/candidaturas/extraer",
        json={"url": "https://ejemplo.com/oferta/456", "contenido_pagina": "poco texto"},
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["empresa"] == "Por revisar"
    assert cuerpo["puesto"] == "Por revisar"
    assert cuerpo["ciudad"] is None


def test_extraer_da_503_si_la_ia_falla(client, monkeypatch):
    def falla(url, texto):
        raise extraccion_ia.ExtraccionIAError("clave no configurada")

    monkeypatch.setattr(extraccion_ia, "extraer_datos_oferta", falla)

    respuesta = client.post(
        "/candidaturas/extraer",
        json={"url": "https://ejemplo.com/oferta/789", "contenido_pagina": "texto"},
    )

    assert respuesta.status_code == 503


def test_extraer_url_invalida_da_422(client):
    respuesta = client.post(
        "/candidaturas/extraer",
        json={"url": "no-es-una-url", "contenido_pagina": "texto"},
    )

    assert respuesta.status_code == 422
