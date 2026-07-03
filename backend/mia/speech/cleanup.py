"""Mia · speech.cleanup — pulido opcional del dictado con el modelo LOCAL.

Réplica del post-proceso de Lexter (`spanish_polish` con Ollama local): toma la
transcripción cruda y corrige puntuación y mayúsculas SIN cambiar el contenido.
Reglas que se heredan de Lexter:

  - SOLO el modelo local (`mia-local`, el Ollama del despacho vía el gateway).
    NUNCA un modelo de nube: el dictado es material de trabajo sin filtrar y la
    Ola 3 es 100% local. Por eso se pasa `model="mia-local"` explícito a
    call_llm (cadena de UN alias, sin fallback a la nube).
  - Guardrail anti-traducción: si la salida parece una traducción al inglés o
    difiere demasiado del original, se descarta y gana el texto crudo.
  - Fail-soft: si el modelo local no está corriendo o falla, el dictado sale
    crudo (cleaned_text=None). El pulido es un lujo, no un requisito.
"""
from __future__ import annotations

import logging
import re

logger = logging.getLogger(__name__)

_PROMPT = (
    "Eres un corrector de dictados jurídicos en español. Recibes la transcripción "
    "cruda de un dictado por voz. Devuelve el MISMO texto con puntuación, tildes y "
    "mayúsculas corregidas. Reglas estrictas: no traduzcas a ningún otro idioma; no "
    "agregues, quites ni resumas contenido; no expliques nada; conserva los términos "
    "jurídicos tal como se dictaron; responde ÚNICAMENTE con el texto corregido."
)

# Palabras funcionales del español vs. inglés: si el original trae varias en
# español y la salida las pierde — o gana palabras funcionales inglesas que el
# original no tenía — lo más probable es que el modelo tradujo (guardrail de
# Lexter). OJO: "no" y "un" existen en ambos idiomas → NO cuentan como señal.
_ES_STOPWORDS = re.compile(
    r"\b(el|la|los|las|de|del|que|y|en|una|por|para|con|se|al|su|es|como)\b",
    re.IGNORECASE,
)
_EN_STOPWORDS = re.compile(
    r"\b(the|of|and|is|are|was|were|there|that|this|to|from|with|not)\b",
    re.IGNORECASE,
)


def _distinct(pattern: re.Pattern, text: str) -> int:
    return len({m.lower() for m in pattern.findall(text)})


def _looks_wrong(original: str, cleaned: str) -> bool:
    """True si la 'limpieza' cambió el texto de forma sospechosa (traducción,
    resumen o relleno). Preferimos el crudo ante cualquier duda."""
    if not cleaned:
        return True
    ratio = len(cleaned) / max(len(original), 1)
    if not (0.5 <= ratio <= 1.6):
        return True
    # Traducción ES→EN (hallazgo capa 2: una sola coincidencia era burlable con
    # palabras compartidas): la salida debe CONSERVAR el español del original y
    # no puede GANAR palabras funcionales inglesas que el original no tenía.
    es_in, es_out = _distinct(_ES_STOPWORDS, original), _distinct(_ES_STOPWORDS, cleaned)
    if es_in >= 2 and es_out < 2:
        return True
    if _distinct(_EN_STOPWORDS, cleaned) > _distinct(_EN_STOPWORDS, original):
        return True
    return False


def polish_transcript(text: str) -> str | None:
    """Pulido con el modelo LOCAL. Devuelve el texto pulido o None si no se pudo
    (o el guardrail lo rechazó). Síncrono — llamar vía asyncio.to_thread."""
    text = (text or "").strip()
    if not text:
        return None
    try:
        from ..agent.llm import call_llm  # import diferido (los gates no cargan LLM)

        resp = call_llm(
            [
                {"role": "system", "content": _PROMPT},
                {"role": "user", "content": text},
            ],
            task="speech_cleanup",
            model="mia-local",   # candado: SOLO el Ollama local, sin fallback a nube
            temperature=0.0,
            max_tokens=2048 + len(text) // 2,
        )
        cleaned = (resp.choices[0].message.content or "").strip()
    except Exception:  # noqa: BLE001 — sin Ollama corriendo, el dictado sale crudo
        logger.info("speech: pulido local no disponible; se entrega el texto crudo")
        return None
    if _looks_wrong(text, cleaned):
        logger.warning("speech: el pulido local se descartó por el guardrail")
        return None
    return cleaned
