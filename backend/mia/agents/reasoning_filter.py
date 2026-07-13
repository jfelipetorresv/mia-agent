"""Mia · agents.reasoning_filter — filtro determinista del "razonamiento en voz alta".

Los modelos de razonamiento LOCALES (Ollama / modo soberano `mia-local`) emiten su
cadena de pensamiento ANTES de la respuesta, envuelta en etiquetas como
`<think>…</think>` (o `<thinking>`, `<reasoning>`). Ese preámbulo NO es parte del
borrador: no debe llegar al abogado, ni al escáner de citas (agents/verification.py),
ni a la traza. Este módulo lo elimina en el único cuello de botella por el que pasa la
salida cruda de cada especialista (`MatterGraphBuilder._llm`, agents/graph.py), UNA
sola vez, ANTES de la verificación de citas.

Perfil análogo al guardián de citas (verification.flag_phantom_doc_citations): función
PURA, determinista, sin red / DB / LLM, con gate offline propio
(execution/test_reasoning_filter.py). Filosofía de diseño:

  - NO-OP seguro: si el texto NO trae ninguna etiqueta de razonamiento reconocible,
    se devuelve EXACTAMENTE igual (byte a byte). Esto es vital: en el modo normal con
    Claude —que nunca emite estas etiquetas— el filtro no altera absolutamente nada.
  - ANCLADO AL INICIO (arreglo del hallazgo bloqueante, 2026-07-13): el pensamiento del
    modelo SIEMPRE va al PRINCIPIO de la salida (el modelo "piensa antes de responder").
    Por eso SOLO se elimina un bloque de razonamiento cuando está anclado al INICIO del
    texto (tras blancos iniciales). Una etiqueta `<think>`/`</think>` que aparezca a
    MITAD del contenido es texto CITADO legítimo (p. ej. un peritaje sobre IA, código
    aportado como prueba, o el análisis de un fallo automatizado) y se conserva INTACTA.
    Este anclaje es la garantía DURA contra el borrado de texto legítimo, incluso si el
    gate por modelo (abajo) no aplicara.
  - NUNCA borra contenido que no esté dentro de un bloque de razonamiento LÍDER
    reconocible. Ante la duda, conserva (prioridad: no perder texto legítimo del
    borrador — un `</think>` citado a media respuesta pesa más que limpiar un artefacto).

Defensa en profundidad (gate por modelo): `is_reasoning_model` permite que el llamador
(graph.py `_llm`) ejecute el filtro SOLO cuando el modelo activo es local/razonamiento.
En el modo por defecto (Claude/nube, que nunca emite estas etiquetas) el filtro ni
siquiera corre — NO-OP incondicional.
"""
from __future__ import annotations

import os
import re

# Etiqueta de razonamiento (case-insensitive). Captura las tres formas en un solo patrón:
#   group(1) == "/"  → etiqueta de CIERRE   (</think>)
#   group(3) == "/"  → etiqueta AUTO-CERRADA (<think/>)
#   ninguna de las dos → etiqueta de APERTURA (<think ...>)
# Se admiten atributos (`<think foo="bar">`) vía `[^>]*?` y espacios sueltos internos.
# `thinking` va ANTES de `think` para que la alternación prefiera la variante más larga.
_TAG_RE = re.compile(
    r"<\s*(/?)\s*(?:thinking|think|reasoning)\b[^>]*?(/?)\s*>",
    re.IGNORECASE,
)

# Blancos que deja el borrado del bloque LÍDER: líneas totalmente en blanco al inicio del
# cuerpo restante. Se eliminan SOLO esas líneas-gap; la sangría de la PRIMERA línea con
# contenido real se conserva (no se toca el espaciado legítimo del resto del borrador).
_LEADING_BLANK_LINES_RE = re.compile(r"\A(?:[ \t]*\n)+")

# Marcadores (subcadena, case-insensitive) que identifican un alias/modelo LOCAL de
# razonamiento. Configurable por env (MIA_REASONING_MODEL_MARKERS, coma-separado).
_DEFAULT_LOCAL_MARKERS: tuple[str, ...] = (
    "mia-local", "ollama", "qwen", "deepseek", "reasoning", "-r1",
)


def _local_markers() -> tuple[str, ...]:
    raw = os.getenv("MIA_REASONING_MODEL_MARKERS", "")
    parts = tuple(p.strip().lower() for p in raw.split(",") if p.strip())
    return parts or _DEFAULT_LOCAL_MARKERS


def is_reasoning_model(model_id: object) -> bool:
    """True si `model_id` (alias o nombre de modelo) es un modelo LOCAL de razonamiento
    (los únicos que emiten `<think>…</think>`). Vacío/None/nube → False.

    Gate por modelo (defensa en profundidad): el llamador ejecuta `strip_reasoning` SOLO
    cuando esto es True. Para Claude/nube devuelve False → el filtro no corre (NO-OP
    incondicional). Como los aliases locales llevan un marcador reconocible tanto en el
    alias (`mia-local`) como en el modelo subyacente (`ollama/qwen2.5:7b-instruct`),
    basta una coincidencia de subcadena; Claude (`claude-sonnet`, `anthropic/…`) nunca
    la trae."""
    if not model_id:
        return False
    mid = str(model_id).lower()
    return any(mk in mid for mk in _local_markers())


def _consume_leading_reasoning(text: str) -> tuple[int, bool]:
    """Recorre el PREFIJO del texto consumiendo razonamiento LÍDER y devuelve
    `(inicio_del_cuerpo, se_borró_algo)`.

    Reglas (todas ancladas al INICIO; tras blancos iniciales opcionales):
      - Bloque pareado `<think ...>…</think>` (anidamiento respetado) → se descarta y se
        sigue buscando otro bloque líder contiguo (separado solo por blancos).
      - Apertura huérfana `<think ...>` sin cierre → razonamiento truncado que ocupa el
        resto: se descarta HASTA EL FINAL (cuerpo vacío).
      - Auto-cerrada líder `<think/>` → marcador vacío: se descarta y se sigue.
      - Cierre huérfano líder `</think>` (stray al inicio) → se descarta y se sigue.
      - Al toparse con CONTENIDO real (o una etiqueta a media respuesta) → se DETIENE:
        todo lo que sigue es el cuerpo legítimo y se conserva intacto.
    """
    n = len(text)
    pos = 0
    removed = False
    while True:
        # Salta blancos iniciales para localizar la etiqueta líder.
        j = pos
        while j < n and text[j].isspace():
            j += 1
        m = _TAG_RE.match(text, j)
        if not m:
            break  # el prefijo ya es contenido real (o una etiqueta a media respuesta)
        is_close = bool(m.group(1))
        is_self = bool(m.group(2))
        if is_self or is_close:
            # Auto-cerrada o cierre huérfano líder: se descarta solo la etiqueta.
            pos = m.end()
            removed = True
            continue
        # Apertura líder: busca su cierre respetando anidamiento.
        depth = 1
        k = m.end()
        while depth > 0:
            m2 = _TAG_RE.search(text, k)
            if not m2:
                return n, True  # apertura huérfana → se descarta hasta el final
            if m2.group(2):        # auto-cerrada: no afecta la profundidad
                k = m2.end()
                continue
            if m2.group(1):        # cierre
                depth -= 1
            else:                  # apertura anidada
                depth += 1
            k = m2.end()
        pos = k
        removed = True
    return pos, removed


def strip_reasoning(text: str) -> str:
    """Elimina el razonamiento en voz alta del modelo SOLO cuando está anclado al INICIO
    de la salida, y devuelve el cuerpo legítimo. Reconoce `<think>`, `<thinking>` y
    `<reasoning>` (case-insensitive, multilínea, con atributos, anidado).

    ANCLAJE AL INICIO (garantía dura contra el hallazgo bloqueante): una etiqueta de
    razonamiento que aparezca a MITAD del contenido es texto CITADO legítimo y se
    conserva INTACTA. Solo se descarta el bloque/preámbulo que ocupa el PRINCIPIO.

    NO-OP byte a byte cuando no hay ninguna etiqueta reconocible O cuando la etiqueta no
    está anclada al inicio (contenido citado): se devuelve `text` sin tocar. El modo
    normal con Claude nunca emite estas etiquetas.
    """
    if not text:
        return text
    # NO-OP byte a byte: sin etiquetas de razonamiento no se ejecuta NADA.
    if not _TAG_RE.search(text):
        return text
    body_start, removed = _consume_leading_reasoning(text)
    if not removed:
        # Había etiquetas, pero NINGUNA anclada al inicio (todas a media respuesta =
        # contenido citado) → NO-OP byte a byte.
        return text
    # Limpieza SOLO alrededor del corte líder: elimina las líneas-gap que deja el borrado
    # sin tocar la sangría de la primera línea real ni el espaciado del resto del cuerpo.
    return _LEADING_BLANK_LINES_RE.sub("", text[body_start:])
