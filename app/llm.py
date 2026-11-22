import asyncio
import logging
from datetime import datetime
from typing import Literal, Optional

from google import genai
from google.genai import types
from pydantic import BaseModel, Field

from app import config

log = logging.getLogger(__name__)

SYSTEM_PROMPT = """Eres un asistente para agentes de atención al cliente y ventas.
Recibes la transcripción de UN chat entre un agente y un cliente. Devuelve un análisis breve y fiel.

Reglas:
- No inventes datos: si algo no aparece en el chat, déjalo en null.
- "resumen": 1 a 3 frases con lo hablado: qué quería el cliente y en qué quedó.
- "estado":
  - vendida: el cliente confirmó la compra o el pago.
  - cita_agendada: hay una cita, visita o llamada con fecha acordada.
  - pendiente_seguimiento: falta una respuesta, decisión o acción (del cliente o del agente).
  - resuelta: consulta atendida y sin nada pendiente, sin venta.
  - perdida: el cliente rechazó o dejó de interesarse explícitamente.
- "pregunta_sin_responder": true solo si el último mensaje relevante es del cliente y espera respuesta.
- "fecha_seguimiento": fecha y hora local en formato ISO 8601 (YYYY-MM-DDTHH:MM) si se acordó o se puede deducir
  un momento para retomar o una cita; usa la fecha actual dada para resolver "mañana" o "el lunes". Si no, null.
- "accion_siguiente": la próxima acción concreta del agente, o null si no hay.
- "monto": importe de la venta si se menciona, sin símbolo de moneda, o null.
- Responde en español."""


class ChatAnalysis(BaseModel):
    cliente: str = Field(description="Nombre del cliente o 'Cliente' si no se conoce")
    resumen: str
    estado: Literal["vendida", "cita_agendada", "pendiente_seguimiento", "resuelta", "perdida"]
    pregunta_sin_responder: bool
    monto: Optional[float] = None
    fecha_seguimiento: Optional[str] = None
    accion_siguiente: Optional[str] = None


_client: genai.Client | None = None


def _get_client() -> genai.Client:
    global _client
    if _client is None:
        _client = genai.Client(api_key=config.GEMINI_API_KEY)
    return _client


async def analyze(transcript: str, now_local: datetime, retries: int = 3) -> ChatAnalysis:
    prompt = (
        f"Fecha y hora actual: {now_local.strftime('%Y-%m-%d %H:%M')} ({config.TZ_NAME}).\n\n"
        f"Transcripción:\n{transcript}"
    )
    last_exc: Exception | None = None
    for attempt in range(retries):
        try:
            resp = await _get_client().aio.models.generate_content(
                model=config.GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(
                    system_instruction=SYSTEM_PROMPT,
                    response_mime_type="application/json",
                    response_schema=ChatAnalysis,
                    temperature=0.1,
                ),
            )
            return ChatAnalysis.model_validate_json(resp.text)
        except Exception as exc:  # límites de tasa, red, JSON inválido
            last_exc = exc
            log.warning("Gemini falló (intento %d/%d): %s", attempt + 1, retries, exc)
            await asyncio.sleep(2 ** (attempt + 1))
    raise RuntimeError(f"No se pudo analizar el chat: {last_exc}")
