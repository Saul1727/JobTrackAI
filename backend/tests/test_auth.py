"""
Tests de autenticación (registro/login) y de aislamiento entre usuarios.

Esto último es el motivo de ser de todo el sistema de login: como ahora
varios amigos comparten el mismo backend, hay que comprobar de verdad que
ninguno puede ver ni tocar los datos de otro — no basta con que cada uno
"vea solo lo suyo" en el caso normal, hay que comprobar también que
intentarlo a propósito (adivinando un id) falla.
"""
import io
from datetime import date

from reportlab.pdfgen import canvas

from tests.conftest import EMAIL_USUARIO_DE_PRUEBA, PASSWORD_USUARIO_DE_PRUEBA, cabecera_auth


def _pdf_de_prueba(texto="Ingeniero de software con experiencia en Python"):
    # Mismo helper que test_cv_base.py: un PDF mínimo pero real, generado
    # con reportlab — un PDF "a mano" con bytes inventados haría fallar la
    # extracción de texto (422) antes de llegar a lo que este test
    # realmente quiere comprobar (el aislamiento entre usuarios).
    buffer = io.BytesIO()
    lienzo = canvas.Canvas(buffer)
    lienzo.drawString(100, 750, texto)
    lienzo.save()
    return buffer.getvalue()


def candidatura_de_ejemplo(**overrides):
    datos = {
        "empresa": "ACME Corp",
        "puesto": "Backend Developer",
        "url_oferta": "https://ejemplo.com/oferta/123",
        "fecha": str(date.today()),
    }
    datos.update(overrides)
    return datos


# --- Registro --------------------------------------------------------------


def test_registro_crea_usuario_y_devuelve_token(client):
    # El fixture autouse ya ha registrado EMAIL_USUARIO_DE_PRUEBA — usamos
    # aquí un email distinto para no chocar con el 409 de "ya existe".
    respuesta = client.post(
        "/auth/registro", json={"email": "nuevo@ejemplo.com", "password": "password123"}
    )

    assert respuesta.status_code == 201
    cuerpo = respuesta.json()
    assert cuerpo["access_token"]
    assert cuerpo["token_type"] == "bearer"


def test_registro_con_email_duplicado_da_409(client):
    # EMAIL_USUARIO_DE_PRUEBA ya está registrado por el fixture autouse.
    respuesta = client.post(
        "/auth/registro",
        json={"email": EMAIL_USUARIO_DE_PRUEBA, "password": "otra-password"},
    )

    assert respuesta.status_code == 409


def test_registro_con_password_corta_da_422(client):
    respuesta = client.post(
        "/auth/registro", json={"email": "corta@ejemplo.com", "password": "1234567"}
    )

    assert respuesta.status_code == 422


def test_registro_con_email_invalido_da_422(client):
    respuesta = client.post(
        "/auth/registro", json={"email": "no-es-un-email", "password": "password123"}
    )

    assert respuesta.status_code == 422


# --- Login -------------------------------------------------------------


def test_login_con_credenciales_correctas_da_token(client):
    respuesta = client.post(
        "/auth/login",
        json={"email": EMAIL_USUARIO_DE_PRUEBA, "password": PASSWORD_USUARIO_DE_PRUEBA},
    )

    assert respuesta.status_code == 200
    assert respuesta.json()["access_token"]


def test_login_con_password_incorrecta_da_401(client):
    respuesta = client.post(
        "/auth/login",
        json={"email": EMAIL_USUARIO_DE_PRUEBA, "password": "password-equivocada"},
    )

    assert respuesta.status_code == 401


def test_login_con_email_inexistente_da_401(client):
    respuesta = client.post(
        "/auth/login",
        json={"email": "no-existe@ejemplo.com", "password": "lo-que-sea"},
    )

    assert respuesta.status_code == 401


# --- /auth/yo y protección de rutas ----------------------------------------


def test_yo_con_token_devuelve_el_email(client):
    respuesta = client.get("/auth/yo")  # el fixture autouse ya pone el token

    assert respuesta.status_code == 200
    assert respuesta.json()["email"] == EMAIL_USUARIO_DE_PRUEBA


def test_yo_sin_token_da_401(client):
    respuesta = client.get("/auth/yo", headers={"Authorization": ""})

    assert respuesta.status_code == 401


def test_ruta_protegida_sin_token_da_401(client):
    respuesta = client.get("/candidaturas/", headers={"Authorization": ""})

    assert respuesta.status_code == 401


def test_ruta_protegida_con_token_invalido_da_401(client):
    respuesta = client.get("/candidaturas/", headers=cabecera_auth("esto-no-es-un-jwt-valido"))

    assert respuesta.status_code == 401


# --- Aislamiento entre usuarios ---------------------------------------------


def _token_de_otro_usuario(client) -> str:
    respuesta = client.post(
        "/auth/registro", json={"email": "otro@ejemplo.com", "password": "password-otro"}
    )
    assert respuesta.status_code == 201
    return respuesta.json()["access_token"]


def test_un_usuario_no_ve_las_candidaturas_de_otro(client):
    client.post("/candidaturas/", json=candidatura_de_ejemplo(empresa="Mía"))

    token_otro = _token_de_otro_usuario(client)
    respuesta = client.get("/candidaturas/", headers=cabecera_auth(token_otro))

    assert respuesta.status_code == 200
    assert respuesta.json() == []  # el otro usuario no ve la candidatura del primero


def test_un_usuario_no_puede_obtener_la_candidatura_de_otro(client):
    creada = client.post("/candidaturas/", json=candidatura_de_ejemplo()).json()

    token_otro = _token_de_otro_usuario(client)
    respuesta = client.get(f"/candidaturas/{creada['id']}", headers=cabecera_auth(token_otro))

    # 404, no 403: no queremos confirmarle a un usuario que ese id existe
    # (aunque sea de otra persona) — mismo mensaje que un id inventado.
    assert respuesta.status_code == 404


def test_un_usuario_no_puede_editar_la_candidatura_de_otro(client):
    creada = client.post("/candidaturas/", json=candidatura_de_ejemplo()).json()

    token_otro = _token_de_otro_usuario(client)
    respuesta = client.patch(
        f"/candidaturas/{creada['id']}",
        json={"estado": "entrevista"},
        headers=cabecera_auth(token_otro),
    )

    assert respuesta.status_code == 404


def test_un_usuario_no_puede_borrar_la_candidatura_de_otro(client):
    creada = client.post("/candidaturas/", json=candidatura_de_ejemplo()).json()

    token_otro = _token_de_otro_usuario(client)
    respuesta_borrado = client.delete(f"/candidaturas/{creada['id']}", headers=cabecera_auth(token_otro))
    # Sigue existiendo para su dueño real.
    respuesta_get = client.get(f"/candidaturas/{creada['id']}")

    assert respuesta_borrado.status_code == 404
    assert respuesta_get.status_code == 200


def test_cada_usuario_tiene_su_propio_cv_base(client):
    client.post(
        "/cv-base/",
        files={"archivo": ("mi_cv.pdf", _pdf_de_prueba(), "application/pdf")},
    )

    token_otro = _token_de_otro_usuario(client)
    respuesta = client.get("/cv-base/", headers=cabecera_auth(token_otro))

    # El otro usuario todavía no ha subido ningún CV base — el mío no se lo filtra.
    assert respuesta.status_code == 404
