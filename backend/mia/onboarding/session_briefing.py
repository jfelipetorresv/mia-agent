"""Mia · onboarding.session_briefing — lógica del /daily y del /cierre del expediente
(Piezas 4c, 4d, 4e). Núcleo compartido por el router (`api/routes/sessions.py`) y por el
disparo automático de cierre; el router solo valida propiedad del asunto y delega aquí.

Dos operaciones sobre la MEMORIA EN DISCO del expediente (helpers de `workspace.py`):

  · build_daily_briefing  (/daily) — LEE bitácora + bandeja (inbox) + el bloque
    "Pendiente de tu decisión" del HANDOFF y devuelve un resumen PRIORIZADO: lo que
    requiere decisión del abogado va ARRIBA y marcado; cada ítem lleva una referencia
    estable `#N`. Determinista (sin LLM), async, fail-soft.

  · distill_and_write_cierre  (/cierre) — DESTILA con la cadena BARATA de LLM
    (`call_llm(task="session_search")`, jerarquía tipo Haiku) SOLO lo que el ABOGADO
    decidió/instruyó en la sesión (nunca lo que Mia infiere), y ESCRIBE el resultado en
    disco: los hechos durables como una entrada nueva de la bitácora, y las decisiones
    abiertas como un bloque "Pendiente de tu decisión" separado FÍSICAMENTE (otra región
    del HANDOFF, tras una regla horizontal). Async, fail-soft, CERO cron.

  · maybe_auto_cierre  — el mismo destilado, GATEADO por el llenado de contexto (~65%).
    Ready e invocable; su disparo automático lo decide quien SÍ tiene la conversación y su
    tamaño (hoy, el frontend — ver la nota de integración en `api/routes/stream.py`).

Regla dura (memoria de Mia): el destilado resume lo que el ABOGADO suministró/decidió, que
se asume fidedigno; NUNCA inventa hechos, citas ni decisiones. Si no hay nada durable en la
sesión, no escribe nada (no fabrica un cierre).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime
from pathlib import Path

from ..agent import llm
from .workspace import matter_workspace_dir

logger = logging.getLogger("mia.onboarding.session_briefing")

# Encabezado del bloque de decisiones abiertas. FUENTE ÚNICA: lo ESCRIBE el /cierre y lo LEE
# el /daily — deben coincidir byte a byte para que el diario surta las decisiones pendientes.
PENDING_DECISION_HEADER = "## Pendiente de tu decisión"

# Umbral de llenado de contexto que dispara el cierre automático (~65%). Decisión de Pipe:
# cerrar antes de perder contexto. Se compara contra la ventana del modelo (config).
CONTEXT_FILL_THRESHOLD = 0.65

# Roles que cuentan como intervención DEL ABOGADO en la sesión (lo demás —Mia, sistema,
# resúmenes— NO se destila: el cierre es lo que el abogado decidió/instruyó, no lo que Mia
# infirió). Se aceptan sinónimos por compatibilidad con distintas capas del frontend/grafo.
_LAWYER_ROLES = frozenset({"user", "abogado", "lawyer", "human"})

# Delimitadores del destilado (formato de máquina, parseo determinista). El modelo emite
# dos bloques; si no respeta el formato, se degrada guardando el texto crudo como registro.
_DISTILL_DURABLE = "=== HECHOS DURABLES ==="
_DISTILL_PENDING = "=== PENDIENTE DE TU DECISIÓN ==="
_DISTILL_END = "=== FIN ==="

_DISTILL_SYSTEM = (
    "Eres un archivista del despacho que cierra una sesión de trabajo sobre un asunto. "
    "Tu tarea es DESTILAR, en español jurídico llano, SOLO lo que el ABOGADO decidió o "
    "instruyó en los mensajes que siguen — nunca lo que un asistente infirió, propuso o "
    "redactó. NO inventes hechos, decisiones, normas ni citas: si algo no está dicho por "
    "el abogado, no lo pongas. Si la sesión no contiene ninguna decisión ni instrucción "
    "durable, deja ambas listas vacías. Produce EXACTAMENTE este formato, sin saludo ni "
    "preámbulo:\n"
    f"{_DISTILL_DURABLE}\n"
    "- <un hecho o decisión durable del abogado, uno por línea; de 0 a 3 en total>\n"
    f"{_DISTILL_PENDING}\n"
    "- <una decisión que el abogado dejó ABIERTA y debe tomar, una por línea; 0 o más>\n"
    f"{_DISTILL_END}"
)


# ── util: conteo de tokens de una conversación (para el gate de auto-cierre) ─────────
def _messages_tokens(messages: list[dict]) -> int:
    """Tokens estimados (offline) de una lista de mensajes; +4 por mensaje de overhead,
    mismo criterio que el ContextCompressor."""
    from ..memory.tokens import estimate_tokens

    total = 0
    for m in messages or []:
        c = m.get("content") if isinstance(m, dict) else None
        total += estimate_tokens(c if isinstance(c, str) else str(c or "")) + 4
    return total


def _lawyer_transcript(messages: list[dict]) -> str:
    """Transcripción SOLO de las intervenciones del abogado, en orden. "" si no hay ninguna."""
    lines: list[str] = []
    for m in messages or []:
        if not isinstance(m, dict):
            continue
        role = str(m.get("role") or "").strip().lower()
        if role not in _LAWYER_ROLES:
            continue
        text = m.get("content")
        text = text if isinstance(text, str) else str(text or "")
        text = text.strip()
        if text:
            lines.append(text)
    return "\n\n".join(lines)


# ── /daily · resumen priorizado (determinista, fail-soft) ────────────────────────────
def _bullets_under_heading(markdown: str, heading: str) -> list[str]:
    """Todas las viñetas ('- '/'* ') que cuelgan de CUALQUIER sección cuyo encabezado empiece
    por `heading`, hasta el siguiente encabezado. Deja pasar varios bloques (p. ej. varios
    cierres) acumulando sus viñetas. Determinista y tolerante a texto libre entre medio."""
    out: list[str] = []
    in_section = False
    for raw in (markdown or "").splitlines():
        line = raw.rstrip()
        stripped = line.lstrip()
        if stripped.startswith("#"):
            in_section = stripped.startswith(heading)
            continue
        if in_section:
            body = stripped
            if body[:2] in ("- ", "* "):
                item = body[2:].strip()
                if item:
                    out.append(item)
    return out


def _read_text(path: Path) -> str:
    try:
        if not path.is_file():
            return ""
        return path.read_text(encoding="utf-8", errors="replace").strip()
    except Exception:  # noqa: BLE001 — leer disco jamás tumba el briefing
        logger.warning("session_briefing: no se pudo leer %s", path, exc_info=True)
        return ""


def _inbox_items(inbox_dir: Path) -> list[str]:
    """Un ítem por archivo sin clasificar en la bandeja (inbox): nombre + una línea de
    vistazo. Fail-soft: [] si no hay carpeta o falla el listado."""
    try:
        if not inbox_dir.is_dir():
            return []
        files = sorted(p for p in inbox_dir.iterdir() if p.is_file())
    except Exception:  # noqa: BLE001
        logger.warning("session_briefing: no se pudo listar la bandeja %s",
                       inbox_dir, exc_info=True)
        return []
    items: list[str] = []
    for p in files:
        preview = ""
        if p.suffix.lower() in (".md", ".txt"):
            for ln in _read_text(p).splitlines():
                if ln.strip():
                    preview = ln.strip()
                    break
        items.append(f"{p.name}" + (f" — {preview}" if preview else ""))
    return items


def _bitacora_previews(bitacora_dir: Path, limit: int) -> list[str]:
    """Vistazo (primera línea con texto) de las `limit` entradas más recientes de la
    bitácora, más reciente primero. Fail-soft: []."""
    try:
        if not bitacora_dir.is_dir():
            return []
        files = [p for p in bitacora_dir.iterdir()
                 if p.is_file() and p.suffix.lower() == ".md"]
    except Exception:  # noqa: BLE001
        logger.warning("session_briefing: no se pudo listar la bitácora %s",
                       bitacora_dir, exc_info=True)
        return []

    def _mtime(p: Path) -> float:
        try:
            return p.stat().st_mtime
        except OSError:
            return 0.0

    files.sort(key=_mtime, reverse=True)
    out: list[str] = []
    for p in files[:max(0, limit)]:
        preview = ""
        for ln in _read_text(p).splitlines():
            s = ln.lstrip("#").strip()
            if s:
                preview = s
                break
        out.append(preview or p.name)
    return out


async def build_daily_briefing(tenant_id: str, matter_id: str) -> dict:
    """Resumen priorizado del asunto para el arranque del día (/daily).

    LEE (fail-soft, cada fuente por separado) el bloque "Pendiente de tu decisión" del
    HANDOFF, la bandeja (inbox) y la bitácora reciente, y devuelve una lista ÚNICA ordenada:
    los ítems que REQUIEREN decisión del abogado van primero (`requiere_decision: true`),
    luego lo informativo. Cada ítem lleva una referencia estable `#N` en el orden devuelto.
    """
    def _gather() -> dict:
        root = matter_workspace_dir(tenant_id, matter_id)
        pendientes = _bullets_under_heading(_read_text(root / "HANDOFF.md"),
                                            PENDING_DECISION_HEADER)
        bandeja = _inbox_items(root / "inbox")
        bitacora = _bitacora_previews(root / "bitacora", 5)

        items: list[dict] = []
        n = 0
        for texto in pendientes:                       # decisiones abiertas → lo más urgente
            n += 1
            items.append({"ref": f"#{n}", "requiere_decision": True,
                          "origen": "pendiente", "texto": texto})
        for texto in bandeja:                          # bandeja sin clasificar → atención
            n += 1
            items.append({"ref": f"#{n}", "requiere_decision": True,
                          "origen": "bandeja", "texto": texto})
        for texto in bitacora:                         # diario reciente → informativo
            n += 1
            items.append({"ref": f"#{n}", "requiere_decision": False,
                          "origen": "bitacora", "texto": texto})

        requieren = sum(1 for it in items if it["requiere_decision"])
        if not items:
            resumen = "Sin novedades en el expediente: nada pendiente de tu decisión hoy."
        elif requieren:
            resumen = (f"{requieren} punto(s) requieren tu decisión, marcados arriba; "
                       f"{len(items) - requieren} nota(s) informativa(s) más abajo.")
        else:
            resumen = "Nada requiere tu decisión hoy; solo hay notas informativas."
        return {"matter_id": matter_id, "items": items,
                "requieren_decision": requieren, "resumen": resumen}

    try:
        return await asyncio.to_thread(_gather)
    except Exception:  # noqa: BLE001 — /daily nunca responde 500 por leer disco
        logger.warning("build_daily_briefing: fallo leyendo el expediente (tenant=%s matter=%s)",
                       tenant_id, matter_id, exc_info=True)
        return {"matter_id": matter_id, "items": [], "requieren_decision": 0,
                "resumen": "No se pudo leer el expediente en disco en este momento."}


# ── /cierre · destilado con LLM barato + escritura en disco (fail-soft) ───────────────
def _parse_distillation(text: str) -> tuple[list[str], list[str]] | None:
    """(hechos_durables, pendientes) del destilado, o None si el formato no se reconoce.

    Determinista y tolerante: toma el bloque DURABLE entre su encabezado y el de PENDIENTE,
    y el bloque PENDIENTE hasta FIN (o el final del texto). De cada bloque extrae las viñetas
    ('- '/'* '). Sin el encabezado DURABLE → None (deja que el caller guarde el crudo)."""
    if not text:
        return None
    i_dur = text.find(_DISTILL_DURABLE)
    if i_dur == -1:
        return None
    i_pen = text.find(_DISTILL_PENDING, i_dur)
    i_end = text.find(_DISTILL_END, max(i_dur, i_pen))

    def _bullets(chunk: str) -> list[str]:
        out: list[str] = []
        for ln in chunk.splitlines():
            s = ln.strip()
            if s[:2] in ("- ", "* "):
                item = s[2:].strip().lstrip("*_ ").rstrip("*_ ").strip()
                if item:
                    out.append(item)
        return out

    dur_end = i_pen if i_pen != -1 else (i_end if i_end != -1 else len(text))
    durables = _bullets(text[i_dur + len(_DISTILL_DURABLE):dur_end])
    pendientes: list[str] = []
    if i_pen != -1:
        pen_end = i_end if i_end != -1 else len(text)
        pendientes = _bullets(text[i_pen + len(_DISTILL_PENDING):pen_end])
    return durables, pendientes


def _write_bitacora_entry(root: Path, body: str, now: datetime) -> str:
    """Escribe una entrada NUEVA en la bitácora (append-only: nombre único por timestamp).
    Devuelve la ruta relativa creada. No pisa nada."""
    d = root / "bitacora"
    d.mkdir(parents=True, exist_ok=True)
    name = f"cierre-{now:%Y%m%d-%H%M%S}.md"
    path = d / name
    content = f"# Cierre de sesión — {now:%Y-%m-%d %H:%M}\n\n{body.strip()}\n"
    path.write_text(content, encoding="utf-8")
    return f"bitacora/{name}"


def _append_pending_block(root: Path, pendientes: list[str], now: datetime) -> None:
    """Añade el bloque 'Pendiente de tu decisión' al HANDOFF.md, SEPARADO FÍSICAMENTE del
    resto por una regla horizontal y su propio encabezado. Append-only (nunca pisa lo que ya
    hay). Si el HANDOFF no existe aún, lo crea con un encabezado mínimo."""
    path = root / "HANDOFF.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    block = ("\n\n---\n\n"
             f"{PENDING_DECISION_HEADER} — {now:%Y-%m-%d %H:%M}\n\n"
             + "\n".join(f"- {p}" for p in pendientes) + "\n")
    if not path.exists():
        path.write_text("# HANDOFF\n\nTraspaso entre sesiones de este asunto.\n",
                        encoding="utf-8")
    with path.open("a", encoding="utf-8") as fh:
        fh.write(block)


async def distill_and_write_cierre(
    tenant_id: str,
    matter_id: str,
    messages: list[dict],
    *,
    now: datetime | None = None,
) -> dict:
    """Destila lo que el ABOGADO decidió/instruyó en la sesión y lo ESCRIBE en disco.

    Usa la cadena BARATA (`call_llm(task="session_search")` → Haiku/local según política).
    Escribe los hechos durables como entrada nueva de la bitácora y las decisiones abiertas
    como bloque "Pendiente de tu decisión" separado físicamente en el HANDOFF.

    Fail-soft: si no hay intervenciones del abogado, o el LLM/disco falla, devuelve un dict
    con `written: False` y una razón — nunca lanza. Nunca fabrica un cierre si no hay nada.
    """
    now = now or datetime.now()
    transcript = _lawyer_transcript(messages)
    if not transcript:
        return {"written": False, "reason": "sin_intervencion_abogado",
                "durables": [], "pendientes": []}

    # Destilado con la cadena barata. call_llm es SÍNCRONO → to_thread para no bloquear.
    try:
        resp = await asyncio.to_thread(
            llm.call_llm,
            [{"role": "system", "content": _DISTILL_SYSTEM},
             {"role": "user", "content": transcript}],
            task="session_search",
        )
        raw = (resp.choices[0].message.content or "").strip()
    except Exception:  # noqa: BLE001 — un fallo del LLM no tumba el cierre; se reporta
        logger.warning("distill_and_write_cierre: el destilado LLM falló (tenant=%s matter=%s)",
                       tenant_id, matter_id, exc_info=True)
        return {"written": False, "reason": "fallo_llm", "durables": [], "pendientes": []}

    parsed = _parse_distillation(raw)
    if parsed is None:
        # El modelo no respetó el formato: guardamos el crudo como registro (mejor que
        # perderlo), sin bloque de pendientes.
        durables_text, pendientes = raw, []
        durables: list[str] = [raw] if raw else []
    else:
        durables, pendientes = parsed
        durables_text = "\n".join(f"- {d}" for d in durables)

    if not durables and not pendientes:
        return {"written": False, "reason": "nada_durable", "durables": [], "pendientes": []}

    def _persist() -> str | None:
        root = matter_workspace_dir(tenant_id, matter_id)
        entry_rel = None
        if durables_text.strip():
            entry_rel = _write_bitacora_entry(root, durables_text, now)
        if pendientes:
            _append_pending_block(root, pendientes, now)
        return entry_rel

    try:
        entry_rel = await asyncio.to_thread(_persist)
    except Exception:  # noqa: BLE001 — escribir en disco jamás tumba el turno
        logger.warning("distill_and_write_cierre: no se pudo escribir el cierre en disco "
                       "(tenant=%s matter=%s)", tenant_id, matter_id, exc_info=True)
        return {"written": False, "reason": "fallo_escritura",
                "durables": durables, "pendientes": pendientes}

    return {"written": True, "reason": "ok", "durables": durables,
            "pendientes": pendientes, "bitacora_entry": entry_rel}


async def maybe_auto_cierre(
    tenant_id: str,
    matter_id: str,
    messages: list[dict],
    *,
    context_window: int | None = None,
    fill_threshold: float = CONTEXT_FILL_THRESHOLD,
    now: datetime | None = None,
) -> dict:
    """Cierre AUTOMÁTICO: dispara `distill_and_write_cierre` SOLO si la conversación llena la
    ventana de contexto por encima de `fill_threshold` (~65%), para no perder contexto.

    Ready e invocable por quien tenga la conversación y su tamaño (hoy el frontend, que
    conoce el hilo visible — ver la nota de integración en `api/routes/stream.py`). CERO
    cron: se dispara por llamada, no por reloj. Fail-soft en todas sus ramas.

    Devuelve `{triggered: bool, fill: float, ...}`; si disparó, incluye el resultado del
    destilado (`written`, `durables`, `pendientes`).
    """
    from .. import config

    window = int(context_window or getattr(config, "MIA_CONTEXT_WINDOW", 200000) or 200000)
    used = _messages_tokens(messages)
    fill = (used / window) if window > 0 else 0.0
    if fill < fill_threshold:
        return {"triggered": False, "fill": round(fill, 4)}
    result = await distill_and_write_cierre(tenant_id, matter_id, messages, now=now)
    return {"triggered": True, "fill": round(fill, 4), **result}
