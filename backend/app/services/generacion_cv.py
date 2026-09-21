"""
Generates a job-offer-tailored CV using an AI model (Google Gemini, with
Groq as an automatic fallback) — same provider strategy as
extraccion_ia.py, applied to generation instead of extraction.
"""
import time

from google import genai
from groq import Groq
from pydantic import BaseModel

from app.config import settings
from app.schemas import CVGenerado

MODELO_GEMINI = "gemini-3.6-flash"

# Same retry strategy as extraccion_ia.py: a transient 503 from Gemini's
# free tier is worth one retry; anything else is not, and the daily quota
# is too tight to spend on repeated retries.
INTENTOS_MAXIMOS_GEMINI = 2
ESPERA_ENTRE_INTENTOS_SEGUNDOS = 5

# Same fallback as extraccion_ia.py — see that file for the rationale
# behind the model choice and the strict JSON schema mode used below.
MODELO_GROQ = "openai/gpt-oss-20b"

# A full CV (several roles, each with multiple bullet points) is
# considerably longer than the handful of fields extracted in
# extraccion_ia.py, so the completion budget is set higher here to make
# sure a multi-role CV fits without being truncated mid-generation.
GROQ_REASONING_EFFORT = "low"
GROQ_MAX_COMPLETION_TOKENS = 8192


class GeneracionCVError(Exception):
    """Raised for any failure in this layer (missing key, network error,
    unparseable response); the calling route turns it into a clean API error."""


def _esquema_json_estricto(modelo_pydantic: type[BaseModel]) -> dict:
    """See the identical helper in extraccion_ia.py: adapts a Pydantic
    schema to Groq's strict json_schema requirements, including nested
    objects (here, SeccionExperiencia and SeccionEducacion)."""

    def limpiar(nodo):
        if isinstance(nodo, dict):
            nodo.pop("default", None)
            if nodo.get("type") == "object" and "properties" in nodo:
                nodo["additionalProperties"] = False
                nodo["required"] = list(nodo["properties"].keys())
            for valor in nodo.values():
                limpiar(valor)
        elif isinstance(nodo, list):
            for elemento in nodo:
                limpiar(elemento)

    esquema = modelo_pydantic.model_json_schema()
    limpiar(esquema)
    return esquema


def _rescatar_con_groq(prompt: str, motivo_fallo_gemini: str) -> CVGenerado:
    """Same fallback pattern as extraccion_ia.py."""
    if not settings.groq_api_key:
        raise GeneracionCVError(motivo_fallo_gemini)

    try:
        cliente_groq = Groq(api_key=settings.groq_api_key)
        respuesta = cliente_groq.chat.completions.create(
            model=MODELO_GROQ,
            messages=[{"role": "user", "content": prompt}],
            reasoning_effort=GROQ_REASONING_EFFORT,
            max_completion_tokens=GROQ_MAX_COMPLETION_TOKENS,
            response_format={
                "type": "json_schema",
                "json_schema": {
                    "name": "cv_generado",
                    "strict": True,
                    "schema": _esquema_json_estricto(CVGenerado),
                },
            },
        )

        # A response cut short by the token limit is reported via
        # finish_reason "length" rather than an unparseable-JSON error —
        # detected explicitly here for a clearer message.
        if respuesta.choices[0].finish_reason == "length":
            raise GeneracionCVError(
                "Groq ha cortado la respuesta antes de terminar el CV (demasiado "
                "contenido para el límite de tokens). Prueba a acortar el CV base "
                "o inténtalo de nuevo."
            )

        return CVGenerado.model_validate_json(respuesta.choices[0].message.content)
    except GeneracionCVError:
        raise
    except Exception as exc:
        raise GeneracionCVError(
            f"{motivo_fallo_gemini} Tampoco se ha podido usar Groq como respaldo: {exc}"
        ) from exc


def generar_cv_personalizado(cv_base_texto: str, datos_oferta: dict) -> CVGenerado:
    """datos_oferta carries the fields already extracted for the
    application (empresa, puesto, experiencia_requerida, tecnologias,
    idiomas) — the full offer page text is not re-sent, these structured
    fields are enough to tailor the CV."""
    if not settings.gemini_api_key:
        raise GeneracionCVError(
            "No hay ninguna clave de Gemini configurada (GEMINI_API_KEY en .env)."
        )

    prompt = f"""Eres un experto en redacción de currículums. Vas a adaptar el
CV REAL de un candidato a una oferta de trabajo concreta.

CV actual del candidato (texto extraído de su PDF):
---
{cv_base_texto}
---

Oferta de trabajo a la que se presenta:
- Empresa: {datos_oferta.get("empresa") or "no especificada"}
- Puesto: {datos_oferta.get("puesto") or "no especificado"}
- Experiencia requerida: {datos_oferta.get("experiencia_requerida") or "no especificada"}
- Tecnologías/skills pedidas: {datos_oferta.get("tecnologias") or "no especificadas"}
- Idiomas requeridos: {datos_oferta.get("idiomas") or "no especificados"}

Genera un CV en formato "Harvard" (secciones claras y de texto plano —
resumen, experiencia, educación, habilidades, idiomas — SIN tablas,
columnas ni gráficos, para que lo pueda leer sin perder nada un sistema
ATS de filtrado automático) adaptado específicamente a esta oferta.

Reglas que debes seguir sin excepción:
- NUNCA inventes experiencia, puestos, empresas, fechas ni titulaciones
  que no estén en el CV real de arriba. Tu trabajo es reordenar, resumir
  y redactar mejor lo que YA existe, priorizando lo más relevante para
  esta oferta concreta — no añadir contenido nuevo.
- Puedes usar, cuando encajen de verdad con la experiencia real del
  candidato, las palabras clave de las tecnologías pedidas en la oferta
  (ayuda a pasar los filtros ATS) — pero nunca listes una tecnología que
  el candidato no tenga ya en su CV real.
- "resumen": 2-4 líneas, adaptado a este puesto concreto.
- Cada elemento de "logros" en una experiencia debe ser una frase breve
  orientada a resultados (qué conseguiste), no solo una tarea genérica.
- Voz: "resumen" y "logros" van en PRIMERA persona del singular, con el
  pronombre "yo" omitido (la convención estándar en un CV, porque lo
  escribe el propio candidato sobre sí mismo) — por ejemplo "Desarrollé y
  desplegué una API REST...", NUNCA "Desarrolló y desplegó una API
  REST..." (tercera persona: suena a que lo ha redactado otra persona
  describiéndolo desde fuera, no él mismo).
- Si un dato de contacto (email, teléfono, ubicación, LinkedIn) no
  aparece en el CV real, déjalo como null — no lo inventes.
"""

    cliente = genai.Client(api_key=settings.gemini_api_key)

    respuesta = None
    for intento in range(1, INTENTOS_MAXIMOS_GEMINI + 1):
        try:
            respuesta = cliente.models.generate_content(
                model=MODELO_GEMINI,
                contents=prompt,
                config={
                    "response_mime_type": "application/json",
                    "response_json_schema": CVGenerado.model_json_schema(),
                },
            )
            break
        except Exception as exc:  # the Google SDK can raise several exception types
            mensaje = str(exc)

            es_cuota_agotada = "429" in mensaje or "RESOURCE_EXHAUSTED" in mensaje or "quota" in mensaje.lower()
            if es_cuota_agotada:
                return _rescatar_con_groq(
                    prompt,
                    "Se ha agotado la cuota gratuita de Gemini por ahora. Espera "
                    "un rato (o a que se reinicie mañana, si es el límite diario) "
                    "y vuelve a intentarlo — puedes ver el detalle exacto en "
                    "https://aistudio.google.com/",
                )

            es_saturacion_temporal = "503" in mensaje or "UNAVAILABLE" in mensaje
            si_es_el_ultimo_intento = intento == INTENTOS_MAXIMOS_GEMINI
            if not es_saturacion_temporal or si_es_el_ultimo_intento:
                return _rescatar_con_groq(prompt, f"Fallo al llamar a Gemini: {exc}")
            time.sleep(ESPERA_ENTRE_INTENTOS_SEGUNDOS * intento)

    try:
        return CVGenerado.model_validate_json(respuesta.text)
    except Exception as exc:
        raise GeneracionCVError(
            f"Gemini devolvió una respuesta que no se pudo interpretar: {exc}"
        ) from exc
