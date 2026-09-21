"""
Tests del reintento automático cuando Gemini responde con un 503 de "alta
demanda" — comprueban directamente las funciones de servicio (no pasan por
la API HTTP), simulando genai.Client con un doble que falla las primeras
veces y luego responde bien.

monkeypatch de time.sleep: sin esto, este test tardaría de verdad los 5-10
segundos de espera entre reintentos — lo sustituimos por una función que no
espera nada, para que el test siga siendo instantáneo.
"""
from types import SimpleNamespace

from app.config import settings
from app.services import extraccion_ia, generacion_cv


class _ClienteFalso:
    """
    Simula genai.Client(...): las primeras `fallos_antes_de_responder`
    llamadas a generate_content lanzan un error de "alta demanda" (503),
    y la siguiente ya responde bien — así comprobamos que el reintento
    automático de verdad recupera la petición en vez de rendirse al
    primer fallo.
    """

    def __init__(self, fallos_antes_de_responder: int, texto_respuesta: str):
        self._fallos_restantes = fallos_antes_de_responder
        self._texto_respuesta = texto_respuesta
        self.models = self  # así "cliente.models.generate_content(...)" llega aquí

    def generate_content(self, **kwargs):
        if self._fallos_restantes > 0:
            self._fallos_restantes -= 1
            raise RuntimeError("503 UNAVAILABLE: modelo con alta demanda ahora mismo")
        return SimpleNamespace(text=self._texto_respuesta)


def test_extraer_datos_oferta_reintenta_tras_un_503(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    monkeypatch.setattr(extraccion_ia.time, "sleep", lambda segundos: None)

    texto_json = '{"empresa": "ACME Corp", "puesto": "Backend Developer"}'
    cliente_falso = _ClienteFalso(fallos_antes_de_responder=1, texto_respuesta=texto_json)
    monkeypatch.setattr(extraccion_ia.genai, "Client", lambda api_key: cliente_falso)

    resultado = extraccion_ia.extraer_datos_oferta("https://ejemplo.com/oferta", "texto de la página")

    assert resultado.empresa == "ACME Corp"


def test_extraer_datos_oferta_no_reintenta_si_el_error_no_es_de_saturacion(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")

    # No hace falta simular el paso del tiempo aquí: si el código reintentase
    # (no debería) sí llamaría a time.sleep, y no lo hemos parcheado — un
    # posible bug que sí reintentara se notaría porque el test tardaría de
    # verdad, en vez de fallar limpiamente.
    contador_de_llamadas = {"veces": 0}

    class _ClienteQueFallaSiempre:
        models = None

        def __init__(self):
            self.models = self

        def generate_content(self, **kwargs):
            contador_de_llamadas["veces"] += 1
            raise RuntimeError("401 clave de API inválida")

    monkeypatch.setattr(extraccion_ia.genai, "Client", lambda api_key: _ClienteQueFallaSiempre())

    try:
        extraccion_ia.extraer_datos_oferta("https://ejemplo.com/oferta", "texto")
        assert False, "debería haber lanzado ExtraccionIAError"
    except extraccion_ia.ExtraccionIAError:
        pass  # falla al primer intento, sin reintentar — es justo lo que probamos

    assert contador_de_llamadas["veces"] == 1


def test_extraer_datos_oferta_cuota_agotada_no_reintenta_y_da_mensaje_claro(monkeypatch):
    # Un 429 RESOURCE_EXHAUSTED es distinto de un 503: no es que el modelo
    # esté saturado un momento, es que se acabó la cuota gratuita — insistir
    # no lo arregla, así que debe fallar al primer intento (no reintentar) y
    # con un mensaje que un humano pueda leer, no el JSON crudo de Google.
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    contador_de_llamadas = {"veces": 0}

    class _ClienteSinCuota:
        def __init__(self):
            self.models = self

        def generate_content(self, **kwargs):
            contador_de_llamadas["veces"] += 1
            raise RuntimeError(
                "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
                "'You exceeded your current quota'}}"
            )

    monkeypatch.setattr(extraccion_ia.genai, "Client", lambda api_key: _ClienteSinCuota())

    try:
        extraccion_ia.extraer_datos_oferta("https://ejemplo.com/oferta", "texto")
        assert False, "debería haber lanzado ExtraccionIAError"
    except extraccion_ia.ExtraccionIAError as exc:
        assert "cuota gratuita" in str(exc)

    assert contador_de_llamadas["veces"] == 1


def test_generar_cv_personalizado_reintenta_tras_un_503(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    monkeypatch.setattr(generacion_cv.time, "sleep", lambda segundos: None)

    # Con INTENTOS_MAXIMOS_GEMINI = 2, solo hay margen para 1 fallo antes de
    # que se agoten los intentos — de ahí fallos_antes_de_responder=1.
    texto_json = '{"nombre": "Saúl Alcázar"}'
    cliente_falso = _ClienteFalso(fallos_antes_de_responder=1, texto_respuesta=texto_json)
    monkeypatch.setattr(generacion_cv.genai, "Client", lambda api_key: cliente_falso)

    resultado = generacion_cv.generar_cv_personalizado("CV base de prueba", {"puesto": "Backend Developer"})

    assert resultado.nombre == "Saúl Alcázar"
