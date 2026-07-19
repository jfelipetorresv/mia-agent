"""Mia · onboarding.ficha_loader — carga la MEMORIA EN DISCO de un expediente para
inyectarla como una capa de contexto del turno (Pieza 4a).

Dado `(tenant_id, alias)` —donde `alias` es el UUID del asunto, misma convención que
`create_matter`/`scaffold_matter_workspace`— lee del árbol del expediente:
    · ficha.md    — ficha viva del caso (estado de Mia sobre el expediente)
    · HANDOFF.md  — traspaso entre turnos/sesiones del caso
    · bitacora/   — las entradas MÁS RECIENTES del diario de obra

y devuelve UN texto compacto bajo presupuesto de tokens, truncado por UNIDAD SEMÁNTICA
(líneas y entradas completas — nunca a mitad de línea).

FAIL-SOFT (regla dura): si la carpeta o los archivos aún no existen, o si algo falla al
leer/listar, devuelve "" sin lanzar. Inyectar la ficha es una AYUDA al turno, jamás un
candado — nunca debe tumbar el armado del prompt.

Usa los helpers de rutas de `workspace.py` (`matter_workspace_dir`) — NO reconstruye rutas
a mano. `matter_workspace_dir` aplica el mismo saneo de alias que usó `create_matter`, así
que pasar el UUID del asunto cae SIEMPRE en la MISMA carpeta que se andamió al crearlo.

Puro: solo stdlib + los helpers de `workspace` + el estimador de tokens offline. Sin DB,
sin LLM, sin red — invocable desde el armado del prompt o desde un test sin arrastrar nada.
"""
from __future__ import annotations

import logging
from pathlib import Path

from ..memory.tokens import estimate_tokens
from .workspace import matter_workspace_dir

logger = logging.getLogger("mia.onboarding.ficha_loader")

# Presupuesto de tokens por defecto para TODA la capa de ficha (estimación offline
# ~4 chars/token). Ligero a propósito: la ficha ORIENTA el turno; el material pesado
# (documentos del expediente, diagnóstico) viaja aparte en el mensaje del usuario.
DEFAULT_TOKEN_BUDGET = 1200

# Cuántas entradas recientes de la bitácora se traen como máximo (cada una = una unidad
# semántica, el contenido completo del archivo).
_MAX_BITACORA_ENTRIES = 5

# Marcador cuando una sección se recorta por presupuesto (deja claro que hay más detrás).
_TRUNCATION_MARKER = "… (recortado por espacio)"

# Encabezado de la capa completa y de cada sección (markdown ligero, coherente con el
# resto del contexto del asunto).
_LAYER_HEADER = "## Memoria del expediente en disco"


def _read_text(path: Path) -> str:
    """Contenido de un archivo (stripped), o "" si no existe o no se puede leer (fail-soft)."""
    try:
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001 — leer la memoria en disco jamás tumba el turno
        logger.warning("ficha_loader: no se pudo leer %s", path, exc_info=True)
        return ""


def _recent_bitacora_entries(bitacora_dir: Path, limit: int) -> list[str]:
    """Las `limit` entradas más recientes de la bitácora (por fecha de modificación, desc),
    cada una como una UNIDAD semántica completa. Fail-soft: [] si no hay carpeta o falla el
    listado. El orden por mtime es robusto a la convención de nombres de cada despacho (que
    puede o no llevar fecha en el nombre del archivo)."""
    try:
        if not bitacora_dir.is_dir():
            return []
        files = [p for p in bitacora_dir.iterdir()
                 if p.is_file() and p.suffix.lower() == ".md"]
    except Exception:  # noqa: BLE001
        logger.warning("ficha_loader: no se pudo listar la bitácora %s",
                       bitacora_dir, exc_info=True)
        return []

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    files.sort(key=_mtime, reverse=True)  # más reciente primero
    entries: list[str] = []
    for p in files[:max(0, limit)]:
        text = _read_text(p)
        if text:
            entries.append(text)
    return entries


def _truncate_by_line(text: str, budget_tokens: int) -> str:
    """Recorta `text` al presupuesto conservando LÍNEAS COMPLETAS desde el inicio (nunca
    corta a mitad de línea). Si algo queda fuera, cierra con un marcador de recorte. Un
    texto que ya cabe en el presupuesto se devuelve intacto."""
    if budget_tokens <= 0:
        return ""
    if estimate_tokens(text) <= budget_tokens:
        return text
    kept: list[str] = []
    used = 0
    for line in text.splitlines():
        cost = estimate_tokens(line) + 1  # +1 por el salto de línea
        if used + cost > budget_tokens:
            break
        kept.append(line)
        used += cost
    if not kept:
        return _TRUNCATION_MARKER
    return "\n".join(kept).rstrip() + "\n" + _TRUNCATION_MARKER


def load_ficha_context(
    tenant_id: str,
    alias: str,
    *,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
) -> str:
    """Texto compacto con la memoria en disco del expediente `alias` (UUID del asunto) del
    despacho `tenant_id`: ficha + HANDOFF + bitácora reciente, bajo `token_budget`
    (estimación offline), truncado por unidad semántica.

    Devuelve "" si no hay nada que cargar o si algo falla (fail-soft): la carpeta o los
    archivos pueden no existir aún (asunto recién creado, andamiaje que no corrió) — en ese
    caso el turno sigue exactamente como antes de esta capa.
    """
    if not tenant_id or not alias:
        return ""
    try:
        root = matter_workspace_dir(tenant_id, alias)
    except Exception:  # noqa: BLE001 — resolver la ruta jamás debe tumbar el turno
        logger.warning("ficha_loader: no se pudo resolver la carpeta del expediente "
                       "(tenant=%s alias=%s)", tenant_id, alias, exc_info=True)
        return ""

    ficha = _read_text(root / "ficha.md")
    handoff = _read_text(root / "HANDOFF.md")
    bitacora = _recent_bitacora_entries(root / "bitacora", _MAX_BITACORA_ENTRIES)

    # Secciones ORDENADAS por importancia: la ficha viva primero (estado del caso), el
    # traspaso después (cómo retomar), la bitácora reciente al final (diario de obra). Se
    # van llenando mientras quede presupuesto; la sección que desborde se trunca por línea
    # y las posteriores se omiten — así las más valiosas sobreviven al recorte.
    sections: list[tuple[str, str]] = []
    if ficha:
        sections.append(("### Ficha del caso", ficha))
    if handoff:
        sections.append(("### Traspaso (HANDOFF)", handoff))
    if bitacora:
        sections.append(("### Bitácora reciente", "\n\n".join(bitacora)))
    if not sections:
        return ""

    out: list[str] = [_LAYER_HEADER]
    remaining = token_budget - estimate_tokens(_LAYER_HEADER) - 1
    for title, body in sections:
        title_cost = estimate_tokens(title) + 1
        if remaining <= title_cost + 4:  # sin espacio útil para el título + algo de cuerpo
            break
        remaining -= title_cost
        body_fit = _truncate_by_line(body, remaining)
        if not body_fit:
            break
        out.append(title + "\n" + body_fit)
        remaining -= estimate_tokens(body_fit) + 2  # +2: el separador '\n\n' entre secciones
    if len(out) == 1:  # solo cupo el encabezado → nada útil que inyectar
        return ""
    return "\n\n".join(out)
