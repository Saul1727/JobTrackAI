"""
Extracts structured data from a job offer using an AI model (Google
Gemini, with Groq as an automatic fallback).
"""
import time
from typing import Optional

from google import genai
from groq import Groq
from pydantic import BaseModel

from app.config import settings
from app.models import ModalidadTrabajo

# "flash" is Gemini's fast, low-cost tier, well suited to a bounded
# structured-extraction task like this one rather than long-form reasoning.
MODELO_GEMINI = "gemini-3.6-flash"

# Upper bound on how much of the page text is sent to the model. Offer
# details are almost always within the first few thousand characters, and
# capping this avoids unnecessary cost/latency on unusually long pages.
MAX_CARACTERES_CONTENIDO = 15_000

# Gemini's free tier occasionally returns a transient 503 ("UNAVAILABLE")
# under high demand; a short retry usually resolves it. Any other error
# (invalid key, quota exhausted) is not retried, since retrying would not
# fix it. Limited to a single retry — the free tier's daily request quota
# is low, and each retry consumes part of it.
INTENTOS_MAXIMOS_GEMINI = 2
ESPERA_ENTRE_INTENTOS_SEGUNDOS = 5

# Fallback used when Gemini's quota is exhausted or it fails persistently.
# Groq hosts open-weight models on its own infrastructure and has a
# separate free quota, so it is often available when Gemini is not.
MODELO_GROQ = "openai/gpt-oss-20b"

# A reasoning model spends part of its token budget "thinking" before
# writing the final answer; at the default effort level that could exhaust
# the completion limit before any JSON was written. "low" is enough for a
# straightforward extraction task and leaves the budget for the response
# itself.
GROQ_REASONING_EFFORT = "low"
GROQ_MAX_COMPLETION_TOKENS = 4096


class OfertaExtraida(BaseModel):
    """Fields requested from the model. All optional — the model should
    return null rather than invent a value it did not find in the text."""

    empresa: Optional[str] = None
    puesto: Optional[str] = None
    ciudad: Optional[str] = None
    salario: Optional[str] = None
    tipo_contrato: Optional[str] = None
    experiencia_requerida: Optional[str] = None
    tecnologias: Optional[str] = None
    idiomas: Optional[str] = None
    modalidad: Optional[ModalidadTrabajo] = None
    detalle_hibrido: Optional[str] = None


class ExtraccionIAError(Exception):
    """Raised for any failure in this layer (missing key, network error,
    unparseable response). Routes catch this specific exception and turn
    it into a clean API error instead of leaking an internal traceback."""


def _esquema_json_estricto(modelo_pydantic: type[BaseModel]) -> dict:
    """
    Groq's strict json_schema mode requires every object in the schema to
    set "additionalProperties": false and list all of its properties in
    "required" (a field can still be optional in practice by allowing
    null as its value). Pydantic's generated schema doesn't set these by
    default, so they're patched in here from the real schema rather than
    duplicated by hand.
    """

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


def _rescatar_con_groq(prompt: str, motivo_fallo_gemini: str) -> OfertaExtraida:
    """Called once Gemini has failed outright. Falls back to Groq if a key
    is configured; otherwise (or if Groq also fails) re-raises the
    original Gemini failure reason, with a note appended if Groq failed too."""
    if not settings.groq_api_key:
        raise ExtraccionIAError(motivo_fallo_gemini)

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
                    "name": "oferta_extraida",
                    "strict": True,
                    "schema": _esquema_json_estricto(OfertaExtraida),
                },
            },
        )

        if respuesta.choices[0].finish_reason == "length":
            raise ExtraccionIAError(
                "Groq ha cortado la respuesta antes de terminar (demasiado "
                "contenido para el límite de tokens). Inténtalo de nuevo."
            )

        return OfertaExtraida.model_validate_json(respuesta.choices[0].message.content)
    except ExtraccionIAError:
        raise
    except Exception as exc:
        raise ExtraccionIAError(
            f"{motivo_fallo_gemini} Tampoco se ha podido usar Groq como respaldo: {exc}"
        ) from exc


def extraer_datos_oferta(url: str, contenido_pagina: str) -> OfertaExtraida:
    """Extracts empresa/puesto/ciudad/salario (and related fields) from a
    job offer's page text. Raises ExtraccionIAError on any failure — never
    returns partial data silently."""
    if not settings.gemini_api_key:
        raise ExtraccionIAError(
            "No hay ninguna clave de Gemini configurada (GEMINI_API_KEY en .env)."
        )

    texto_recortado = contenido_pagina[:MAX_CARACTERES_CONTENIDO]

    prompt = f"""Eres un asistente que extrae información estructurada de una
oferta de empleo a partir de su URL y del contenido de su página web.

URL de la oferta: {url}

Contenido de la página (puede incluir texto de menús, cookies u otro ruido
ajeno a la oferta; ignóralo):
---
{texto_recortado}
---

Extrae los siguientes campos SOLO si aparecen explícitamente en el texto.
Si un dato no aparece escrito, devuélvelo como null — nunca inventes ni
asumas un valor que no esté en el texto:
- empresa: nombre de la empresa que ofrece el puesto
- puesto: título del puesto de trabajo
- ciudad: ciudad o ubicación del puesto, si se menciona
- salario: cifra o rango salarial tal y como aparece en el texto (texto libre)
- tipo_contrato: tipo de jornada o contrato, tal y como aparece en el texto (p.ej. "Tiempo completo", "Media jornada", "Freelance", "Prácticas", "Temporal", "Indefinido") — distinto de "modalidad" (esa es presencial/remoto/híbrido, esto es la jornada/tipo de contrato)
- experiencia_requerida: experiencia pedida, tal y como aparece en el texto (p.ej. "2-3 años", "Junior", "Sin experiencia")
- tecnologias: lista de tecnologías, lenguajes o herramientas requeridas, separadas por comas (p.ej. "Python, FastAPI, Docker")
- idiomas: idiomas requeridos y su nivel si se indica (p.ej. "Inglés B2, Español nativo")
- modalidad: "presencial", "remoto" o "hibrido" — SOLO si el texto lo deja claro; null si no se menciona
- detalle_hibrido: si la modalidad es híbrida y el texto especifica el reparto (p.ej. "3 días oficina, 2 remoto"), inclúyelo aquí; si no, null
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
                    "response_json_schema": OfertaExtraida.model_json_schema(),
                },
            )
            break
        except Exception as exc:  # the Google SDK can raise several exception types
            mensaje = str(exc)

            # 429 RESOURCE_EXHAUSTED means the free quota is exhausted, not
            # a transient overload — retrying will not help.
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
        return OfertaExtraida.model_validate_json(respuesta.text)
    except Exception as exc:
        raise ExtraccionIAError(
            f"Gemini devolvió una respuesta que no se pudo interpretar: {exc}"
        ) from exc
