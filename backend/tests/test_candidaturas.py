"""
Tests de regresión del CRUD de candidaturas (Fase 0).

"Regresión" significa exactamente lo que buscas: si mañana tocas
crud.py o un router y rompes algo sin querer, uno de estos tests debería
fallar y avisarte ANTES de que lo descubras a mano probando en /docs.
"""
from datetime import date


def candidatura_de_ejemplo(**overrides):
    """Body válido reutilizable para crear una candidatura en los tests."""
    datos = {
        "empresa": "ACME Corp",
        "puesto": "Backend Developer",
        "url_oferta": "https://ejemplo.com/oferta/123",
        "ciudad": "Valencia",
        "salario": "30000-35000",
        "estado": "aplicado",
        "fecha": str(date.today()),
    }
    datos.update(overrides)
    return datos


def test_crear_candidatura(client):
    respuesta = client.post("/candidaturas/", json=candidatura_de_ejemplo())

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["empresa"] == "ACME Corp"
    assert cuerpo["estado"] == "aplicado"
    assert cuerpo["id"] is not None


def test_crear_candidatura_con_los_campos_nuevos(client):
    respuesta = client.post(
        "/candidaturas/",
        json=candidatura_de_ejemplo(
            tipo_contrato="Tiempo completo",
            experiencia_requerida="2-3 años",
            tecnologias="Python, FastAPI, Docker",
            idiomas="Inglés B2",
            modalidad="hibrido",
            detalle_hibrido="3 días oficina, 2 remoto",
            notas="Contacté con el reclutador por LinkedIn",
            fecha_seguimiento=str(date.today()),
        ),
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["tipo_contrato"] == "Tiempo completo"
    assert cuerpo["experiencia_requerida"] == "2-3 años"
    assert cuerpo["tecnologias"] == "Python, FastAPI, Docker"
    assert cuerpo["idiomas"] == "Inglés B2"
    assert cuerpo["modalidad"] == "hibrido"
    assert cuerpo["detalle_hibrido"] == "3 días oficina, 2 remoto"
    assert cuerpo["notas"] == "Contacté con el reclutador por LinkedIn"
    assert cuerpo["fecha_seguimiento"] == str(date.today())


def test_crear_candidatura_sin_los_campos_nuevos_quedan_en_null(client):
    respuesta = client.post("/candidaturas/", json=candidatura_de_ejemplo())

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["tipo_contrato"] is None
    assert cuerpo["experiencia_requerida"] is None
    assert cuerpo["tecnologias"] is None
    assert cuerpo["idiomas"] is None
    assert cuerpo["modalidad"] is None
    assert cuerpo["detalle_hibrido"] is None
    assert cuerpo["notas"] is None
    assert cuerpo["fecha_seguimiento"] is None


def test_actualizar_notas_y_fecha_seguimiento(client):
    # Estos dos campos son el caso de uso típico de un PATCH manual desde
    # el panel: nunca los rellena la extensión ni la IA.
    creada = client.post("/candidaturas/", json=candidatura_de_ejemplo()).json()

    respuesta = client.patch(
        f"/candidaturas/{creada['id']}",
        json={"notas": "Prueba técnica el jueves", "fecha_seguimiento": str(date.today())},
    )

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["notas"] == "Prueba técnica el jueves"
    assert cuerpo["fecha_seguimiento"] == str(date.today())


def test_crear_candidatura_modalidad_invalida_da_422(client):
    # "remote" en vez de "remoto": no es uno de los tres valores exactos
    # que acepta el Enum, así que debe rechazarse en la validación, no
    # guardarse tal cual en la base de datos.
    respuesta = client.post("/candidaturas/", json=candidatura_de_ejemplo(modalidad="remote"))

    assert respuesta.status_code == 422


def test_actualizar_modalidad(client):
    creada = client.post("/candidaturas/", json=candidatura_de_ejemplo()).json()

    respuesta = client.patch(f"/candidaturas/{creada['id']}", json={"modalidad": "remoto"})

    assert respuesta.status_code == 200
    assert respuesta.json()["modalidad"] == "remoto"


def test_crear_candidatura_url_invalida_da_422(client):
    respuesta = client.post("/candidaturas/", json=candidatura_de_ejemplo(url_oferta="no-es-una-url"))

    assert respuesta.status_code == 422


def test_crear_candidatura_sin_estado_usa_guardada_por_defecto(client):
    # Guardar una oferta no es lo mismo que haber aplicado a ella: si no
    # se manda "estado" explícitamente, debe caer en "guardada", nunca en
    # "aplicado".
    datos = candidatura_de_ejemplo()
    del datos["estado"]

    respuesta = client.post("/candidaturas/", json=datos)

    assert respuesta.status_code == 201
    assert respuesta.json()["estado"] == "guardada"


def test_crear_candidatura_sin_ciudad_ni_salario(client):
    # ciudad y salario son opcionales: la petición debe aceptarse igual.
    datos = candidatura_de_ejemplo()
    del datos["ciudad"]
    del datos["salario"]

    respuesta = client.post("/candidaturas/", json=datos)

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["ciudad"] is None
    assert cuerpo["salario"] is None


def test_listar_candidaturas(client):
    client.post("/candidaturas/", json=candidatura_de_ejemplo(empresa="Empresa A"))
    client.post("/candidaturas/", json=candidatura_de_ejemplo(empresa="Empresa B"))

    respuesta = client.get("/candidaturas/")

    assert respuesta.status_code == 200
    empresas = [c["empresa"] for c in respuesta.json()]
    assert empresas == ["Empresa A", "Empresa B"]


def test_obtener_candidatura_existente(client):
    creada = client.post("/candidaturas/", json=candidatura_de_ejemplo()).json()

    respuesta = client.get(f"/candidaturas/{creada['id']}")

    assert respuesta.status_code == 200
    assert respuesta.json()["id"] == creada["id"]


def test_obtener_candidatura_inexistente_da_404(client):
    respuesta = client.get("/candidaturas/9999")

    assert respuesta.status_code == 404


def test_actualizar_solo_el_estado_no_toca_el_resto(client):
    creada = client.post("/candidaturas/", json=candidatura_de_ejemplo()).json()

    respuesta = client.patch(f"/candidaturas/{creada['id']}", json={"estado": "entrevista"})

    assert respuesta.status_code == 200
    cuerpo = respuesta.json()
    assert cuerpo["estado"] == "entrevista"
    # Lo que no se mandó en el PATCH debe seguir igual que al crear.
    assert cuerpo["empresa"] == creada["empresa"]
    assert cuerpo["puesto"] == creada["puesto"]


def test_actualizar_candidatura_inexistente_da_404(client):
    respuesta = client.patch("/candidaturas/9999", json={"estado": "entrevista"})

    assert respuesta.status_code == 404


def test_borrar_candidatura(client):
    creada = client.post("/candidaturas/", json=candidatura_de_ejemplo()).json()

    respuesta_borrado = client.delete(f"/candidaturas/{creada['id']}")
    respuesta_get_tras_borrar = client.get(f"/candidaturas/{creada['id']}")

    assert respuesta_borrado.status_code == 204
    assert respuesta_get_tras_borrar.status_code == 404


def test_borrar_candidatura_inexistente_da_404(client):
    respuesta = client.delete("/candidaturas/9999")

    assert respuesta.status_code == 404


def test_exportar_excel(client):
    client.post("/candidaturas/", json=candidatura_de_ejemplo())

    respuesta = client.get("/candidaturas/exportar")

    assert respuesta.status_code == 200
    assert respuesta.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    )
    # Un .xlsx es en realidad un .zip; comprobamos la "firma" de sus
    # primeros bytes en vez de abrirlo entero — suficiente para saber que
    # se generó un archivo real, no un cuerpo vacío o corrupto.
    assert respuesta.content[:2] == b"PK"


def test_exportar_no_choca_con_obtener_por_id(client):
    # Regresión directa del problema de orden de rutas: si "/{candidatura_id}"
    # capturase "exportar" como si fuera un id, esto devolvería 422 en vez
    # de la exportación.
    respuesta = client.get("/candidaturas/exportar")

    assert respuesta.status_code == 200
