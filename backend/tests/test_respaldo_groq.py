"""
Tests del respaldo automático con Groq cuando Gemini falla del todo (cuota
agotada, o un error que los reintentos no arreglan) — comprobamos que:

1. Si hay una clave de Groq configurada, se usa como plan B y devuelve un
   resultado válido en vez de fallar.
2. Si NO hay clave de Groq configurada, el comportamiento es exactamente
   el de antes: falla con el mensaje claro de Gemini, sin intentar nada
   más (y sin llamar a Groq, claro).

Igual que en test_reintentos_gemini.py, montamos un doble de genai.Client
que falla siempre, y aquí además un doble de Groq que responde bien —
así comprobamos el mecanismo de verdad, sin llamar a ninguna IA real.
"""
from types import SimpleNamespace

from app.config import settings
from app.services import extraccion_ia, generacion_cv


class _ClienteGeminiSinCuota:
    """Simula genai.Client cuando la cuota gratuita ya está agotada."""

    def __init__(self):
        self.models = self

    def generate_content(self, **kwargs):
        raise RuntimeError(
            "429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': "
            "'You exceeded your current quota'}}"
        )


class _ClienteGroqFalso:
    """
    Simula Groq(api_key=...).chat.completions.create(...) — la forma es
    distinta de la de Gemini (client.chat.completions.create, no
    client.models.generate_content), así que el doble tiene que imitar
    esa misma forma anidada.
    """

    def __init__(self, texto_respuesta: str, finish_reason: str = "stop"):
        # finish_reason="stop" es lo que devuelve la API real de Groq
        # cuando termina de escribir la respuesta con normalidad (por
        # oposición a "length", cuando se corta por el límite de tokens —
        # ver test_groq_corta_por_limite_de_tokens_da_error_claro más abajo).
        self.chat = SimpleNamespace(
            completions=SimpleNamespace(
                create=lambda **kwargs: SimpleNamespace(
                    choices=[
                        SimpleNamespace(
                            message=SimpleNamespace(content=texto_respuesta),
                            finish_reason=finish_reason,
                        )
                    ]
                )
            )
        )


def test_extraccion_usa_groq_cuando_gemini_agota_cuota_y_hay_clave(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    monkeypatch.setattr(settings, "groq_api_key", "clave-groq-de-prueba")
    monkeypatch.setattr(extraccion_ia.genai, "Client", lambda api_key: _ClienteGeminiSinCuota())

    texto_json = '{"empresa": "Groq Inc", "puesto": "Backend Developer"}'
    monkeypatch.setattr(extraccion_ia, "Groq", lambda api_key: _ClienteGroqFalso(texto_json))

    resultado = extraccion_ia.extraer_datos_oferta("https://ejemplo.com/oferta", "texto de la página")

    assert resultado.empresa == "Groq Inc"


def test_extraccion_sin_clave_groq_falla_igual_que_antes(monkeypatch):
    # settings.groq_api_key vacío por defecto — no hace falta monkeypatchearlo.
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    monkeypatch.setattr(settings, "groq_api_key", "")
    monkeypatch.setattr(extraccion_ia.genai, "Client", lambda api_key: _ClienteGeminiSinCuota())

    try:
        extraccion_ia.extraer_datos_oferta("https://ejemplo.com/oferta", "texto")
        assert False, "debería haber lanzado ExtraccionIAError"
    except extraccion_ia.ExtraccionIAError as exc:
        assert "cuota gratuita" in str(exc)
        assert "Groq" not in str(exc)  # ni se ha intentado, así que no se menciona


def test_generacion_cv_usa_groq_cuando_gemini_agota_cuota_y_hay_clave(monkeypatch):
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    monkeypatch.setattr(settings, "groq_api_key", "clave-groq-de-prueba")
    monkeypatch.setattr(generacion_cv.genai, "Client", lambda api_key: _ClienteGeminiSinCuota())

    texto_json = '{"nombre": "Saúl Alcázar", "experiencia": [], "educacion": []}'
    monkeypatch.setattr(generacion_cv, "Groq", lambda api_key: _ClienteGroqFalso(texto_json))

    resultado = generacion_cv.generar_cv_personalizado("CV base de prueba", {"puesto": "Backend Developer"})

    assert resultado.nombre == "Saúl Alcázar"


def test_groq_corta_por_limite_de_tokens_da_error_claro(monkeypatch):
    # Regresión del error real "max completion tokens reached before
    # generating a valid document": si Groq corta la respuesta a medio
    # escribir (finish_reason="length"), el mensaje debe decirlo
    # claramente, no fallar más abajo con un error de parseo de JSON
    # críptico (el contenido truncado ni siquiera es JSON válido).
    monkeypatch.setattr(settings, "gemini_api_key", "clave-de-prueba")
    monkeypatch.setattr(settings, "groq_api_key", "clave-groq-de-prueba")
    monkeypatch.setattr(generacion_cv.genai, "Client", lambda api_key: _ClienteGeminiSinCuota())

    texto_cortado_a_medias = '{"nombre": "Saúl Alcázar", "experiencia": [{"puesto": "Dev'
    monkeypatch.setattr(
        generacion_cv,
        "Groq",
        lambda api_key: _ClienteGroqFalso(texto_cortado_a_medias, finish_reason="length"),
    )

    try:
        generacion_cv.generar_cv_personalizado("CV base de prueba", {"puesto": "Backend Developer"})
        assert False, "debería haber lanzado GeneracionCVError"
    except generacion_cv.GeneracionCVError as exc:
        assert "cortado" in str(exc)
        assert "límite de tokens" in str(exc)
