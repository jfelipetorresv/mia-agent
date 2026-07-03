"""Mia · agents.context_references — adjuntar pruebas por referencia (CP-E2, Ola 5).

El abogado escribe en su mensaje una MENCIÓN a evidencia que ya vive en Mia y Mia la
EXPANDE e inyecta en el turno, sellada como datos no confiables:

    "Revisa @expediente y compáralo con @carpeta:"Pruebas Zurich"."
    "Según @expediente:"Banco Popular vs Zurich" ¿qué defensa tengo?"

Dos tipos de referencia (patrón `@kind:value` de Hermes `agent/context_references.py`,
traducido al dominio jurídico):

  · @expediente            → los documentos del asunto EN CURSO (solo en un turno de asunto).
  · @expediente:"Título"   → los documentos de OTRO asunto del despacho (por título o id).
  · @carpeta:"Etiqueta"    → el contenido indexado de una carpeta de trabajo registrada.

CONFINAMIENTO (la razón de ser de CP-E2 · fail-closed, más estricto que Hermes):
  Mia NO tiene un workspace de archivos por despacho: el "workspace" del abogado son sus
  filas en la DB. Por eso una referencia NUNCA resuelve a una ruta del disco — resuelve
  SIEMPRE contra las tablas del tenant bajo `pool.tenant_connection` (RLS fail-closed):
    · @expediente lee `documents`+`chunks` del asunto (un asunto ajeno es INVISIBLE).
    · @carpeta lee `knowledge_chunks` de una fuente `local_folder_sources` HABILITADA
      (allowlist de CP-C1). Lee el contenido YA INDEXADO — jamás abre un archivo del disco.
  Consecuencia: no hay superficie de path traversal. Una referencia que "parece" una ruta
  (`@carpeta:"C:\\Windows"`, `..`) se rechaza ANTES de tocar la DB (denylist explícita) y,
  aunque pasara, no casaría con ninguna etiqueta registrada → fail-closed.

SELLADO (CP-S1): todo lo adjuntado es CONTENIDO EXTERNO — pasa por `agents.untrusted`
(datos, no órdenes; anti-escape de los marcadores de sello).

TECHO DE TOKENS: la inyección total se acota a REF_HARD_LIMIT_FRACTION de la ventana del
modelo; cada referencia recibe el presupuesto RESTANTE y su contenido se RECORTA para caber
(con marca visible `[…recortado…]` — nunca se recorta evidencia en silencio). Pasado
REF_SOFT_LIMIT_FRACTION se emite un aviso informativo.

QUERY LIMPIA: en el turno de asunto el mensaje del abogado se usa como consulta de
recuperación (RRF, embeddings). Por eso `expand_context_references` devuelve DOS textos:
`retrieval_query` (el mensaje SIN las referencias ni los adjuntos — consulta limpia) y
`message` (con los adjuntos sellados — lo que ven los especialistas). Así adjuntar un
expediente entero no contamina el embedding de búsqueda del turno.
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass, field
from typing import Optional

from . import untrusted
from ..db import pool
from ..memory.tokens import estimate_tokens

# ── sintaxis de la referencia ────────────────────────────────────────────────
# Valor entre comillas (`"..."`, `'...'`, backticks) o token suelto (\S+).
_QUOTED = r'(?:"[^"\n]+"|\'[^\'\n]+\'|`[^`\n]+`)'
# @expediente (suelto = asunto en curso) | @expediente:VALOR | @carpeta:VALOR.
# El look-behind evita capturar correos ("a@b") o rutas ("x/@y").
REFERENCE_PATTERN = re.compile(
    # `\b` tras el tipo: `@expedientes`/`@carpetas` (plural natural del oficio) NO son
    # referencias (revisión capa 2 · MENOR 3). El `\b` casa entre "expediente" y `:` o
    # el espacio, pero NO entre "expediente" y "s".
    r"(?<![\w/@.])@(?P<kind>expediente|carpeta)\b"
    rf"(?::(?P<value>{_QUOTED}|\S+))?",
    re.IGNORECASE,
)
_TRAILING_PUNCT = ",.;:!?"

# ── techo de tokens (Mia-tuned) ──────────────────────────────────────────────
# Más conservador que el 25%/50% de Hermes: en Mia los adjuntos se SUMAN al contexto
# del turno (historial del asistente, documentos del asunto), no son el contenido
# principal — inyectar la mitad de la ventana ahogaría el resto.
REF_SOFT_LIMIT_FRACTION = 0.15
REF_HARD_LIMIT_FRACTION = 0.35
# Umbral mínimo de presupuesto para que valga la pena adjuntar algo (evita bloques
# de solo el encabezado + "[…recortado…]").
_MIN_USEFUL_TOKENS = 64

# Topes defensivos.
MAX_REFERENCES = 12          # nº de referencias procesadas por mensaje (anti-abuso)
MAX_DOCS_PER_REF = 100       # documentos/archivos listados por referencia
MAX_MATCH_CANDIDATES = 25    # candidatos leídos al resolver un nombre ambiguo
# Tope DURO de filas leídas de la DB por referencia (revisión capa 2 · MAYOR 1): el
# techo de tokens acota el PROMPT, no el FETCH. Sin este LIMIT en SQL, un expediente con
# cientos de documentos cargaría decenas de MB de texto a memoria antes de recortar. Es
# un tope de RECURSOS, no una garantía de completitud: con chunks de tamaño normal, 2000
# filas (≈ cientos de miles de chars) cubren de sobra el techo de tokens; con chunks
# patológicamente diminutos podría adjuntarse de menos — fail-safe (jamás de más).
MAX_FETCH_ROWS = 2000

_TRUNCATION_MARK = "\n[…contenido recortado por límite de tamaño; no es la prueba completa…]"


@dataclass(frozen=True)
class ContextReference:
    raw: str
    kind: str            # "expediente" | "carpeta"
    target: str          # "" para @expediente en curso
    start: int
    end: int


@dataclass
class ContextReferenceResult:
    message: str                 # mensaje con los adjuntos sellados (lo ve el modelo)
    retrieval_query: str         # mensaje SIN referencias ni adjuntos (consulta RRF limpia)
    original_message: str
    references: list[ContextReference] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    injected_tokens: int = 0
    expanded: bool = False


# ── parseo ───────────────────────────────────────────────────────────────────
def parse_context_references(message: str) -> list[ContextReference]:
    refs: list[ContextReference] = []
    if not message:
        return refs
    for m in REFERENCE_PATTERN.finditer(message):
        value = m.group("value") or ""
        target = _strip_wrappers(_strip_trailing_punct(value))
        refs.append(ContextReference(
            raw=m.group(0), kind=m.group("kind").lower(), target=target,
            start=m.start(), end=m.end(),
        ))
    return refs


def _strip_trailing_punct(value: str) -> str:
    return value.rstrip(_TRAILING_PUNCT)


def _strip_wrappers(value: str) -> str:
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'`":
        return value[1:-1]
    return value.strip()


def _looks_like_path(value: str) -> bool:
    """Denylist explícita: un valor que parece una RUTA no es un nombre de expediente
    ni una etiqueta de carpeta. Se rechaza ANTES de la DB (defensa en profundidad; la
    resolución es DB-only, así que igual no abriría el disco, pero un aviso claro es
    mejor que una búsqueda ILIKE inútil sobre una ruta)."""
    if not value:
        return False
    v = value.strip()
    if ".." in v:
        return True
    if "/" in v or "\\" in v:
        return True
    # Unidad de Windows tipo "C:" al inicio.
    if re.match(r"^[A-Za-z]:", v):
        return True
    return False


# ── expansión (async · RLS) ──────────────────────────────────────────────────
async def expand_context_references(
    tenant_id: str,
    message: str,
    *,
    matter_id: Optional[str] = None,
    context_length: int,
) -> ContextReferenceResult:
    """Expande @expediente/@carpeta en `message` contra las filas del tenant (RLS).

    `matter_id` = el asunto en curso (habilita `@expediente` suelto); None en el
    asistente (conversación libre), donde `@expediente` suelto pide un nombre.
    """
    refs = parse_context_references(message)
    if not refs:
        return ContextReferenceResult(
            message=message, retrieval_query=message, original_message=message)

    hard_limit = max(_MIN_USEFUL_TOKENS, int(context_length * REF_HARD_LIMIT_FRACTION))
    soft_limit = max(1, int(context_length * REF_SOFT_LIMIT_FRACTION))

    warnings: list[str] = []
    blocks: list[str] = []
    injected = 0

    if len(refs) > MAX_REFERENCES:
        warnings.append(
            f"Se recibieron {len(refs)} referencias; solo se adjuntan las primeras "
            f"{MAX_REFERENCES} (el resto se ignora por límite de tamaño).")
        refs_to_process = refs[:MAX_REFERENCES]
    else:
        refs_to_process = refs

    for ref in refs_to_process:
        remaining = hard_limit - injected
        if remaining < _MIN_USEFUL_TOKENS:
            warnings.append(
                f"{ref.raw}: no se adjuntó — ya se alcanzó el límite de tamaño del turno.")
            continue
        try:
            warning, block, was_truncated = await _expand_one(
                ref, tenant_id, matter_id=matter_id, token_budget=remaining)
        except Exception as exc:  # noqa: BLE001 — una referencia fallida nunca tumba el turno
            warnings.append(f"{ref.raw}: no se pudo adjuntar ({exc}).")
            continue
        if warning:
            warnings.append(warning)
        if block:
            blocks.append(block)
            injected += estimate_tokens(block)
            if was_truncated:
                warnings.append(
                    f"{ref.raw}: se adjuntó recortado por tamaño — no es la prueba completa.")

    if injected > soft_limit:
        warnings.append(
            "Se adjuntó bastante material; si la respuesta pierde foco, referencia "
            "evidencia más específica.")

    stripped = _remove_reference_tokens(message, refs)
    final = stripped
    if warnings:
        final += "\n\n--- Avisos de contexto ---\n" + "\n".join(f"- {w}" for w in warnings)
    if blocks:
        final += "\n\n--- Pruebas adjuntas por referencia ---\n\n" + "\n\n".join(blocks)

    # Query de recuperación LIMPIA (revisión capa 2 · MENOR 4): si el mensaje era SOLO la
    # referencia, `stripped` queda vacío — se usa una frase neutra en vez del mensaje
    # original (que reintroduciría el token `@expediente` al embedding) y en vez de ""
    # (que rompería embed_texts). La evidencia ya viaja adjunta en `message`.
    clean_query = stripped.strip() or "consulta sobre la evidencia adjunta"

    return ContextReferenceResult(
        message=final.strip(),
        retrieval_query=clean_query,
        original_message=message,
        references=refs,
        warnings=warnings,
        injected_tokens=injected,
        expanded=bool(blocks or warnings),
    )


async def _expand_one(
    ref: ContextReference, tenant_id: str, *, matter_id: Optional[str], token_budget: int,
) -> tuple[Optional[str], Optional[str], bool]:
    """Devuelve (aviso|None, bloque_sellado|None, recortado)."""
    if ref.target and _looks_like_path(ref.target):
        return (f"{ref.raw}: usa el NOMBRE del expediente o de la carpeta, no una ruta.",
                None, False)
    if ref.kind == "expediente":
        return await _expand_expediente(ref, tenant_id, matter_id, token_budget)
    if ref.kind == "carpeta":
        return await _expand_carpeta(ref, tenant_id, token_budget)
    return (f"{ref.raw}: tipo de referencia no soportado.", None, False)


# ── @expediente ──────────────────────────────────────────────────────────────
async def _expand_expediente(
    ref: ContextReference, tenant_id: str, matter_id: Optional[str], token_budget: int,
) -> tuple[Optional[str], Optional[str], bool]:
    async with pool.tenant_connection(tenant_id) as conn:
        if not ref.target:
            # @expediente suelto → el asunto en curso (solo en un turno de asunto).
            if not matter_id:
                return ("@expediente: dime cuál — escribe @expediente:\"nombre del asunto\".",
                        None, False)
            resolved_id, title = matter_id, await _matter_title(conn, matter_id)
            if title is None:
                return ("@expediente: no encontré el asunto en curso.", None, False)
        else:
            matches = await _resolve_matter(conn, ref.target)
            if not matches:
                return (f"{ref.raw}: no encontré un expediente con ese nombre.", None, False)
            if len(matches) > 1:
                nombres = ", ".join(_short(t) for _, t in matches[:5])
                return (f"{ref.raw}: hay varios expedientes que coinciden ({nombres}). "
                        "Precisa el nombre.", None, False)
            resolved_id, title = matches[0]

        docs = await _matter_documents(conn, resolved_id)

    if not docs:
        return (f"{ref.raw}: ese expediente no tiene documentos con texto indexado.",
                None, False)

    header = f"Documentos del expediente «{_short(title)}» (evidencia — analízalos como hechos):"
    return _assemble_sealed(header, "DOC", docs, token_budget)


async def _matter_title(conn, matter_id: str) -> Optional[str]:
    if not _is_uuid(matter_id):
        return None
    row = await (await conn.execute(
        "SELECT title FROM matters WHERE id = %s::uuid", (matter_id,))).fetchone()
    return row[0] if row else None


async def _resolve_matter(conn, target: str) -> list[tuple[str, str]]:
    """Resuelve un asunto por id o por título (RLS). Exacto (case-insensitive) primero;
    si no hay, ILIKE 'contiene'. Devuelve [(id, title)] — >1 = ambiguo."""
    if _is_uuid(target):
        row = await (await conn.execute(
            "SELECT id, title FROM matters WHERE id = %s::uuid", (target,))).fetchone()
        return [(str(row[0]), row[1])] if row else []
    exact = await (await conn.execute(
        "SELECT id, title FROM matters WHERE lower(title) = lower(%s) "
        "ORDER BY created_at DESC LIMIT %s", (target, MAX_MATCH_CANDIDATES))).fetchall()
    if exact:
        return [(str(r[0]), r[1]) for r in exact]
    like = await (await conn.execute(
        "SELECT id, title FROM matters WHERE title ILIKE %s ESCAPE '\\' "
        "ORDER BY created_at DESC LIMIT %s",
        (f"%{_like_escape(target)}%", MAX_MATCH_CANDIDATES))).fetchall()
    return [(str(r[0]), r[1]) for r in like]


async def _matter_documents(conn, matter_id: str) -> list[tuple[str, str]]:
    """[(filename, texto_completo)] de un asunto, reensamblando cada documento desde sus
    chunks en orden. Solo documentos con al menos un chunk (texto indexado)."""
    rows = await (await conn.execute(
        "SELECT d.id, d.filename, c.content "
        "FROM documents d JOIN chunks c ON c.document_id = d.id "
        "WHERE d.matter_id = %s::uuid "
        "ORDER BY d.created_at, d.id, c.ord "
        "LIMIT %s",
        (matter_id, MAX_FETCH_ROWS))).fetchall()
    out: list[tuple[str, str]] = []
    cur_id: Optional[str] = None
    cur_name = ""
    parts: list[str] = []
    for did, filename, content in rows:
        did = str(did)
        if did != cur_id:
            if cur_id is not None:
                out.append((cur_name, "\n".join(parts)))
            cur_id, cur_name, parts = did, filename or "documento", []
        parts.append(content or "")
    if cur_id is not None:
        out.append((cur_name, "\n".join(parts)))
    return out[:MAX_DOCS_PER_REF]


# ── @carpeta ─────────────────────────────────────────────────────────────────
async def _expand_carpeta(
    ref: ContextReference, tenant_id: str, token_budget: int,
) -> tuple[Optional[str], Optional[str], bool]:
    if not ref.target:
        return ("@carpeta: dime cuál — escribe @carpeta:\"nombre de la carpeta\".",
                None, False)
    async with pool.tenant_connection(tenant_id) as conn:
        matches = await _resolve_folder(conn, ref.target)
        if not matches:
            return (f"{ref.raw}: no encontré una carpeta de trabajo registrada con ese nombre.",
                    None, False)
        if len(matches) > 1:
            nombres = ", ".join(_short(lbl) for _, lbl in matches[:5])
            return (f"{ref.raw}: hay varias carpetas que coinciden ({nombres}). "
                    "Precisa el nombre.", None, False)
        source_id, label = matches[0]
        files = await _folder_files(conn, source_id)

    if not files:
        return (f"{ref.raw}: esa carpeta no tiene documentos con texto indexado todavía.",
                None, False)

    header = (f"Contenido de la carpeta de trabajo «{_short(label)}» "
              f"({len(files)} documento(s) indexado(s) — material del despacho):")
    return _assemble_sealed(header, "ARCHIVO", files, token_budget, listing=True)


async def _resolve_folder(conn, target: str) -> list[tuple[str, str]]:
    """Resuelve una carpeta de trabajo HABILITADA por id o etiqueta (RLS). Exacto primero,
    luego ILIKE. Devuelve [(source_id, label)] — >1 = ambiguo."""
    if _is_uuid(target):
        row = await (await conn.execute(
            "SELECT id, label FROM local_folder_sources "
            "WHERE id = %s::uuid AND enabled AND kind = 'knowledge'", (target,))).fetchone()
        return [(str(row[0]), row[1])] if row else []
    exact = await (await conn.execute(
        "SELECT id, label FROM local_folder_sources "
        "WHERE lower(label) = lower(%s) AND enabled AND kind = 'knowledge' "
        "ORDER BY created_at LIMIT %s", (target, MAX_MATCH_CANDIDATES))).fetchall()
    if exact:
        return [(str(r[0]), r[1]) for r in exact]
    like = await (await conn.execute(
        "SELECT id, label FROM local_folder_sources "
        "WHERE label ILIKE %s ESCAPE '\\' AND enabled AND kind = 'knowledge' "
        "ORDER BY created_at LIMIT %s",
        (f"%{_like_escape(target)}%", MAX_MATCH_CANDIDATES))).fetchall()
    return [(str(r[0]), r[1]) for r in like]


async def _folder_files(conn, source_id: str) -> list[tuple[str, str]]:
    """[(ruta_relativa, texto)] de los archivos indexados de una carpeta, desde
    `knowledge_chunks` (source='local:<id>'). NUNCA abre el disco: lee lo ya indexado."""
    db_source = f"local:{source_id}"
    rows = await (await conn.execute(
        "SELECT source_path, content FROM knowledge_chunks "
        "WHERE source = %s ORDER BY source_path, chunk_index LIMIT %s",
        (db_source, MAX_FETCH_ROWS))).fetchall()
    out: list[tuple[str, str]] = []
    cur_path: Optional[str] = None
    parts: list[str] = []
    for source_path, content in rows:
        if source_path != cur_path:
            if cur_path is not None:
                out.append((cur_path, "\n".join(parts)))
            cur_path, parts = source_path, []
        parts.append(content or "")
    if cur_path is not None:
        out.append((cur_path, "\n".join(parts)))
    return out[:MAX_DOCS_PER_REF]


# ── ensamblado sellado + presupuesto ─────────────────────────────────────────
def _assemble_sealed(
    header: str, label: str, items: list[tuple[str, str]], token_budget: int,
    *, listing: bool = False,
) -> tuple[Optional[str], Optional[str], bool]:
    """Ensambla un bloque: encabezado + cada ítem SELLADO (CP-S1), recortando el
    contenido para caber en `token_budget`. Devuelve (None, bloque, recortado).

    Con `listing=True` (carpeta) se antepone la lista de archivos incluidos para que
    quede claro qué se adjuntó (transparencia). El COSTO del listado se descuenta del
    presupuesto por archivo — si no, una carpeta con muchos archivos pequeños desbordaría
    el techo de tokens (el listado no es gratis)."""
    truncated = False
    # Reserva fija: encabezado + encabezado del listado + línea de "(omitidos…)" + holgura.
    remaining = token_budget - estimate_tokens(header) - 16
    if listing:
        remaining -= estimate_tokens("Documentos incluidos:")
    pieces: list[str] = []
    included: list[str] = []
    omitted = 0

    for i, (name, content) in enumerate(items):
        fence_open, fence_close = untrusted.fence_markers(label, index=i + 1, source=name)
        overhead = estimate_tokens(fence_open) + estimate_tokens(fence_close) + 4
        # El renglón del listado ("  · <archivo>") también consume presupuesto.
        listing_cost = (estimate_tokens("  · " + str(name)[:200]) + 1) if listing else 0
        if remaining <= overhead + listing_cost + 16:
            omitted = len(items) - i
            truncated = True
            break
        body = str(content or "")
        body_budget = remaining - overhead - listing_cost
        if estimate_tokens(body) > body_budget:
            body = _truncate_to_tokens(body, body_budget)
            truncated = True
        piece = f"{fence_open}\n{untrusted.neutralize(body)}\n{fence_close}"
        remaining -= estimate_tokens(piece) + listing_cost + 2
        pieces.append(piece)
        included.append(name)

    if not pieces:
        # No cupo ni un ítem: al menos un aviso honesto (sin bloque).
        return ("(la evidencia referenciada no cupo en el límite de tamaño del turno)",
                None, True)

    parts = [header]
    if listing:
        listing_lines = "\n".join(f"  · {untrusted.sanitize_field(n, 200)}" for n in included)
        parts.append("Documentos incluidos:\n" + listing_lines)
    if omitted:
        parts.append(f"(se omitieron {omitted} documento(s) más por límite de tamaño)")
    parts.append("\n\n".join(pieces))
    return (None, "\n".join(parts), truncated)


def _truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Recorta a ~max_tokens (estimate_tokens = chars/4) con marca visible. Determinista."""
    if max_tokens <= 0:
        return _TRUNCATION_MARK.strip()
    max_chars = max_tokens * 4
    if len(text) <= max_chars:
        return text
    keep = max(0, max_chars - len(_TRUNCATION_MARK))
    return text[:keep] + _TRUNCATION_MARK


def _remove_reference_tokens(message: str, refs: list[ContextReference]) -> str:
    """Quita los tokens `@...` del mensaje (como Hermes) para que la consulta/instrucción
    quede natural. Colapsa el whitespace sobrante y limpia el espacio antes de la
    puntuación."""
    pieces: list[str] = []
    cursor = 0
    for ref in refs:
        pieces.append(message[cursor:ref.start])
        cursor = ref.end
    pieces.append(message[cursor:])
    text = "".join(pieces)
    text = re.sub(r"[ \t]{2,}", " ", text)
    text = re.sub(r"[ \t]+([,.;:!?])", r"\1", text)
    return text.strip()


# ── utilidades ───────────────────────────────────────────────────────────────
def _is_uuid(s: str) -> bool:
    try:
        uuid.UUID(str(s))
        return True
    except (ValueError, AttributeError, TypeError):
        return False


def _like_escape(s: str) -> str:
    """Escapa los comodines de LIKE (`\\ % _`) para que un nombre con '%' no haga match
    de más (ni permita inyección de patrón)."""
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def _short(s: str, n: int = 120) -> str:
    return untrusted.sanitize_field(s, n)
