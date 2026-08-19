"""Mia · missions.decompose — descompone un objetivo en hitos (CP-E5, Ola 5).

Un LLM AUXILIAR barato (task='mission_decompose' → respeta la política del despacho; en
'soberano' corre 100% local) propone los hitos de un objetivo del expediente. Alrededor del
LLM hay guardas DETERMINISTAS que son las que hacen esto seguro para un despacho jurídico:

  - REGLA DURA: Mia nunca calcula términos ni plazos. El prompt prohíbe fechas; además, todo
    hito cuyo texto mencione un término/plazo/radicación se marca `is_procedural=True` (aunque
    el modelo no lo marque) → la UI lo muestra con [VERIFICAR] y el plazo lo fija el abogado.
  - ANTI-INVENCIÓN: si el modelo falla, devuelve basura o no está disponible, se cae a una
    plantilla GENÉRICA y neutra (planeación, sin afirmaciones jurídicas) — el tablero SIEMPRE
    funciona, nunca inventa pasos jurídicos específicos que no salgan del modelo.
  - CONSENT-FIRST: esto solo PROPONE. El servicio los guarda como hitos 'queued' editables; el
    abogado aprueba, edita, reordena y marca avance. Nada se ejecuta solo.

La salida es una lista de dicts `{title, detail, actor, is_procedural}` ya saneada y acotada.
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from ..agent import llm

logger = logging.getLogger("mia.missions.decompose")

MAX_MILESTONES = 8
MAX_TITLE = 160
MAX_DETAIL = 2000
VALID_ACTORS = ("mia", "abogado")

# Un hito que MENCIONA un término/plazo procesal se marca procesal aunque el modelo no lo
# haga — guarda fail-closed sobre la regla dura "Mia nunca calcula plazos".
_PROCEDURAL_RE = re.compile(
    r"(plazo|t[ée]rmino|caduc|prescrib|prescrip|radica|traslado|ejecutoria|"
    r"vencimiento|d[ií]as?\s+h[áa]biles|notific|contestar\s+dentro|interponer\s+dentro)",
    re.IGNORECASE,
)

_SYSTEM = (
    "Eres el planificador del despacho. Descompones un objetivo grande de un expediente en "
    "HITOS concretos y ordenados que el abogado verá en un tablero y avanzará a mano. "
    "Devuelve ÚNICAMENTE un arreglo JSON (sin texto alrededor, sin ```), de 3 a 8 objetos, "
    "cada uno con estas claves exactas:\n"
    '  "title": frase imperativa breve del hito (máx 12 palabras, sin artículos innecesarios),\n'
    '  "detail": 1-2 frases de qué implica el hito para el abogado,\n'
    '  "actor": "mia" si el agente puede preparar ese hito (investigar, redactar un borrador), '
    '"abogado" si requiere una decisión o acción del abogado,\n'
    '  "is_procedural": true SOLO si el hito toca un término o plazo procesal.\n'
    "REGLAS DURAS:\n"
    "- NUNCA incluyas fechas, plazos en días, ni cálculos de términos: eso lo fija el abogado. "
    "Si un hito depende de un término, descríbelo en palabras y marca is_procedural=true.\n"
    "- No inventes hechos del expediente que no estén en el objetivo. Mantente en pasos de "
    "trabajo, no en afirmaciones jurídicas de fondo.\n"
    "- Español llano en registro jurídico (no fijes país ni jurisdicción), lenguaje del "
    "oficio, sin jerga técnica de software."
)


def _fallback_template(objective: str) -> list[dict]:
    """Plantilla GENÉRICA y neutra cuando el LLM no está disponible o falló. Pasos de
    planeación (no afirmaciones jurídicas): el tablero siempre arranca aunque no haya modelo."""
    return [
        {"title": "Revisar el objetivo y el expediente",
         "detail": "Leer el objetivo y los documentos disponibles para acotar el alcance.",
         "actor": "abogado", "is_procedural": False},
        {"title": "Definir los puntos clave a trabajar",
         "detail": "Listar los asuntos concretos que este objetivo debe resolver.",
         "actor": "abogado", "is_procedural": False},
        {"title": "Preparar un primer borrador de trabajo",
         "detail": "Elaborar un borrador inicial que se pueda revisar y ajustar.",
         "actor": "mia", "is_procedural": False},
        {"title": "Revisar, ajustar y aprobar",
         "detail": "Revisar el resultado, incorporar correcciones y dar la aprobación.",
         "actor": "abogado", "is_procedural": False},
    ]


def _extract_json_array(text: str) -> Any:
    """Extrae el primer arreglo JSON del texto del modelo (tolera ``` y prosa alrededor)."""
    if not text:
        return None
    # Quita cercas de código si vinieron.
    cleaned = re.sub(r"```(?:json)?", "", text).strip()
    start = cleaned.find("[")
    end = cleaned.rfind("]")
    if start == -1 or end == -1 or end <= start:
        return None
    try:
        return json.loads(cleaned[start:end + 1])
    except (ValueError, TypeError):
        return None


def _sanitize(items: Any) -> list[dict]:
    """Normaliza y ACOTA la lista del modelo; aplica la guarda procesal fail-closed."""
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        title = str(it.get("title") or "").strip()[:MAX_TITLE]
        if not title:
            continue
        detail = str(it.get("detail") or "").strip()[:MAX_DETAIL]
        actor = str(it.get("actor") or "abogado").strip().lower()
        if actor not in VALID_ACTORS:
            actor = "abogado"
        # Guarda fail-closed: procesal si el modelo lo dijo O si el texto menciona un término.
        procedural = bool(it.get("is_procedural")) or bool(
            _PROCEDURAL_RE.search(title) or _PROCEDURAL_RE.search(detail))
        out.append({"title": title, "detail": detail, "actor": actor,
                    "is_procedural": procedural})
        if len(out) >= MAX_MILESTONES:
            break
    return out


def _build_user_prompt(objective: str, matter_title: str, matter_description: str) -> str:
    parts = [f"Objetivo del expediente:\n{objective.strip()}"]
    if matter_title.strip():
        parts.append(f"Título del expediente: {matter_title.strip()}")
    if matter_description.strip():
        parts.append(f"Descripción del expediente:\n{matter_description.strip()[:1500]}")
    parts.append("Devuelve el arreglo JSON de hitos.")
    return "\n\n".join(parts)


async def propose_milestones(
    objective: str, *, matter_title: str = "", matter_description: str = "",
) -> list[dict]:
    """Propone los hitos de `objective` (lista saneada de dicts). FAIL-SOFT: ante cualquier
    error o salida vacía, cae a la plantilla genérica — nunca lanza."""
    objective = (objective or "").strip()
    if not objective:
        return _sanitize(_fallback_template(""))
    messages = [
        {"role": "system", "content": _SYSTEM},
        {"role": "user", "content": _build_user_prompt(objective, matter_title, matter_description)},
    ]
    items: list[dict] = []
    try:
        resp = await asyncio.to_thread(llm.call_llm, messages, task="mission_decompose")
        content = resp.choices[0].message.content or ""
        items = _sanitize(_extract_json_array(content))
    except Exception:  # noqa: BLE001 — fail-soft: el tablero no depende del modelo
        logger.warning("propose_milestones: el modelo falló; se usa la plantilla genérica",
                       exc_info=True)
        items = []
    if not items:
        items = _sanitize(_fallback_template(objective))
    return items
