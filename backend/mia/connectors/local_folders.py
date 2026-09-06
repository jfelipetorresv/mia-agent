"""Mia · connectors.local_folders — indexador incremental de carpetas de trabajo (CP-C1, Pilar C · decisión #30).

Mia conoce las carpetas de trabajo del abogado — disco local, OneDrive y Google Drive (vía
sus carpetas espejo de escritorio en Windows) — y las indexa sola, con ALLOWLIST EXPLÍCITA:
solo se escanea lo que el despacho registró en `local_folder_sources`. Calcado del patrón
de obsidian_sync.py: hash sha256 incremental (vs. `local_file_hashes`), chunking,
embeddings en batch (voyage-law-2 vía librería LiteLLM, NO el proxy chat — decisión #17 C2
/ Riesgo #4) y persistencia en `knowledge_chunks` con source = 'local:<source_id>' para
distinguirlos de los de Obsidian (source='obsidian').

SEGURIDAD (allowlist fail-closed, DOS CAPAS — privacidad primero):
  1. Al REGISTRAR una fuente (`validate_source_path`): se rechazan rutas inexistentes,
     raíces de unidad (C:\\, D:\\) y directorios de sistema (Windows, Program Files,
     AppData, ...). Se guarda la ruta ya RESUELTA (sin symlinks ni '..').
  2. Al SINCRONIZAR: la raíz se re-resuelve y se re-valida (si dejó de ser segura o su
     ruta real ya no coincide con la registrada, la fuente se omite); cada archivo se
     resuelve (`Path.resolve()`) y si apunta FUERA de la carpeta registrada (symlink de
     escape) se omite. NUNCA se escanea nada fuera de las fuentes registradas.

Límites defensivos: archivos > 20 MB se omiten con log. La sincronización hace primero
una pasada BARATA de solo hashes sobre todo lo escaneado y luego indexa (embeddings) como
máximo MAX_FILES_PER_SYNC archivos NUEVOS/CAMBIADOS por corrida; los diferidos quedan sin
hash guardado y se indexan en la corrida siguiente (nunca se pierden). La enumeración del
disco tiene un tope duro (MAX_SCAN_FILES); si se alcanza, en esa corrida NO se poda nada
(ni chunks ni hashes de archivos no vistos) para no borrar conocimiento de archivos que
sí existen pero quedaron fuera del escaneo.

Las subcarpetas de sistema (_FORBIDDEN_PARTS: Windows, AppData, ProgramData, ...) se
excluyen TAMBIÉN durante el descenso recursivo del scan — no solo al validar la raíz —
para que registrar p. ej. C:\\Users\\<usuario> nunca indexe configuraciones o credenciales.

Aislamiento: TODA operación de DB por-tenant pasa por `pool.tenant_connection(tenant_id)`
(RLS activo, fail-closed).

Navegador (`safe_browse_roots`/`browse_folder`, Bloque A · A1): deja al abogado ELEGIR una
carpeta navegando en vez de escribir la ruta a mano. Mismas reglas fail-closed que registrar
(`_FORBIDDEN_PARTS`, `Path.resolve()`), pero SOLO devuelve nombres de subcarpetas — nunca
archivos ni su contenido — y no exige que la ruta esté ya registrada (se navega ANTES de
registrar, no al revés). Deshabilitable con `MIA_DISABLE_FOLDER_BROWSE` en despliegue
compartido (ver `api/routes/folders.py`).
"""
from __future__ import annotations

import asyncio
import hashlib
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from .. import embeddings
from ..db import pool
from ..jobs import enqueue_classification
from ..ingest.extract import extract_text_detailed
from ..ingest.document_derivation import SUPPORTED_ANYDOC_EXTENSIONS
from ..ingest.ingest import chunk_text, chunk_extracted_text
from .obsidian_sync import ObsidianSync
from .pinecone_connector import pinecone_scope_for_tenant

logger = logging.getLogger("mia.connectors.local_folders")

SOURCE_PREFIX = "local:"          # knowledge_chunks.source = 'local:<source_id>' (varchar 50)
ALLOWED_SUFFIXES = {".md", ".txt", ".pdf", ".docx"} | set(SUPPORTED_ANYDOC_EXTENSIONS)
EXCLUDED_DIR_NAMES = {"node_modules", "__pycache__"}
MAX_FILE_BYTES = 20 * 1024 * 1024   # > 20 MB → se omite con log
MAX_FILES_PER_SYNC = 2000           # máx. archivos NUEVOS/CAMBIADOS indexados por corrida
MAX_SCAN_FILES = 50000              # tope duro de enumeración por carpeta (defensivo)
EMBED_BATCH = 128                   # máx chunks por llamada de embedding (igual que Obsidian)
# Lectura al vuelo para el chat. Es deliberadamente más pequeña que una sincronización:
# se hace en la ruta interactiva, no copia nada a Mia y nunca debe recorrer una carpeta
# enorme ni cargar decenas de documentos en memoria durante un turno.
LIVE_SCAN_FILES = 500
LIVE_READ_FILES = 12
LIVE_READ_BYTES = 8 * 1024 * 1024

# Directorios de sistema: cualquier ruta que CONTENGA uno de estos segmentos se rechaza
# (fail-closed: mejor rechazar una carpeta legítima rara que escanear el sistema).
_FORBIDDEN_PARTS = {
    "windows", "program files", "program files (x86)", "programdata", "appdata",
    "$recycle.bin", "system volume information",
}


@dataclass
class LiveMatterSourceRead:
    """Resultado de lectura directa, con cobertura explícita para el turno."""

    files: list[dict] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _is_locked(exc: BaseException) -> bool:
    """True si el error es 'archivo en uso' (p. ej. abierto en Word): PermissionError o
    WinError 32. Un archivo bloqueado NO se descarta: se reintenta en el próximo ciclo."""
    return isinstance(exc, PermissionError) or (
        isinstance(exc, OSError) and getattr(exc, "winerror", None) == 32
    )


def _guess_mime(name: str) -> str | None:
    """Tipo MIME aproximado a partir de la extensión (solo para mostrarlo al abogado)."""
    n = (name or "").lower()
    if n.endswith(".pdf"):
        return "application/pdf"
    if n.endswith(".docx"):
        return "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    if n.endswith(".md"):
        return "text/markdown"
    if n.endswith(".txt"):
        return "text/plain"
    return None


# ── allowlist · capa 1: validación al registrar ──────────────────────────────
def validate_source_path(raw: str) -> Path:
    """Valida una ruta ANTES de registrarla como fuente. Devuelve la ruta resuelta
    (sin symlinks ni '..'). Lanza ValueError con mensaje en lenguaje llano si no es
    segura: inexistente, no-carpeta, raíz de unidad o directorio de sistema."""
    if not raw or not str(raw).strip():
        raise ValueError("Necesito la ruta de la carpeta que quieres que conozca.")
    p = Path(str(raw).strip()).expanduser()
    if not p.exists():
        raise ValueError("Esa carpeta no existe en este equipo. Revisa la ruta e inténtalo de nuevo.")
    if not p.is_dir():
        raise ValueError("Esa ruta es un archivo, no una carpeta. Indícame la carpeta que la contiene.")
    resolved = p.resolve()
    _check_safe_root(resolved)
    return resolved


def _check_safe_root(resolved: Path) -> None:
    """Reglas de seguridad sobre una ruta YA resuelta (se re-usan en cada sync)."""
    if resolved == Path(resolved.anchor) or resolved.parent == resolved:
        raise ValueError(
            "Por seguridad no puedo revisar un disco completo. Elige una carpeta específica, "
            "por ejemplo la de tus documentos de trabajo."
        )
    if any(part.lower().rstrip("\\/") in _FORBIDDEN_PARTS for part in resolved.parts):
        raise ValueError(
            "Esa carpeta pertenece al sistema del computador y por seguridad no la reviso. "
            "Elige una carpeta de documentos de trabajo."
        )


# ── detección de nubes espejo (OneDrive / Google Drive) ─────────────────────
def detect_cloud_folders(home: Path | str | None = None,
                         drive_roots: list | None = None) -> list[dict]:
    """Detecta las carpetas espejo de escritorio de OneDrive y Google Drive en Windows.
    Devuelve SOLO las que existen, como [{label, path}] con etiquetas amables.
    `home` y `drive_roots` son inyectables para pruebas (por defecto: el home real y
    las unidades montadas A:..Z:)."""
    home_dir = Path(home) if home else Path.home()
    out: list[dict] = []

    # OneDrive: variable de entorno oficial, o ~/OneDrive como respaldo.
    env_od = os.environ.get("OneDrive", "")
    for cand in ([Path(env_od)] if env_od else []) + [home_dir / "OneDrive"]:
        if cand.is_dir():
            out.append({"label": "Tu OneDrive", "path": str(cand)})
            break

    # Google Drive: unidad montada con 'My Drive'/'Mi unidad' en su raíz (típico G:\),
    # o la carpeta espejo clásica en el home.
    if drive_roots is None:
        drive_roots = (
            [Path(f"{d}:/") for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ" if Path(f"{d}:/").exists()]
            if os.name == "nt" else []
        )
    gdrive: Path | None = None
    for root in drive_roots:
        for name in ("My Drive", "Mi unidad"):
            cand = Path(root) / name
            if cand.is_dir():
                gdrive = cand
                break
        if gdrive:
            break
    if gdrive is None:
        for name in ("Google Drive", "GoogleDrive"):
            cand = home_dir / name
            if cand.is_dir():
                gdrive = cand
                break
    if gdrive is not None:
        out.append({"label": "Tu Google Drive", "path": str(gdrive)})
    return out


# ── navegador seguro de carpetas (A1: elegir qué registrar, no al revés) ─────
def safe_browse_roots() -> list[dict]:
    """Puntos de partida para NAVEGAR el árbol de carpetas del equipo: las carpetas
    típicas del abogado (Documentos/Escritorio/Descargas, solo las que existan), las
    nubes espejo detectadas (OneDrive/Google Drive) y las unidades fijas montadas
    (D:\\, E:\\...). Cada raíz trae `registrable`: las carpetas de usuario y las nubes SÍ
    se pueden vincular tal cual; una unidad completa NO (`validate_source_path` la
    rechaza) — se navega para entrar y elegir una subcarpeta de adentro."""
    home = Path.home()
    out: list[dict] = []
    for label, sub in (("Documentos", "Documents"), ("Escritorio", "Desktop"),
                       ("Descargas", "Downloads")):
        cand = home / sub
        if cand.is_dir():
            out.append({"label": label, "path": str(cand), "registrable": True})
    for cloud in detect_cloud_folders():
        out.append({"label": cloud["label"], "path": cloud["path"], "registrable": True})
    if os.name == "nt":
        for d in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            root = Path(f"{d}:/")
            if root.exists():
                out.append({"label": f"Disco ({d}:)", "path": str(root), "registrable": False})
    return out


async def browse_folder(path: str) -> dict:
    """Un nivel de SUBCARPETAS bajo `path` (solo lectura, nunca archivos ni su contenido)
    — para que el abogado ELIJA qué registrar navegando, en vez de escribir la ruta a
    mano. Fail-closed, mismas reglas que registrar una fuente (`_check_safe_root`): un
    segmento de sistema (_FORBIDDEN_PARTS), una ruta inexistente o que no sea carpeta se
    RECHAZAN con `ValueError` en lenguaje llano. NO exige que `path` esté ya registrado.
    Enumera hasta 500 subcarpetas (orden alfabético, sin distinguir mayúsculas); si hay
    más, `truncated=True`."""
    if not path or not str(path).strip():
        raise ValueError("Necesito la ruta de la carpeta que quieres abrir.")
    resolved = Path(str(path).strip()).expanduser().resolve()
    if any(part.lower().rstrip("\\/") in _FORBIDDEN_PARTS for part in resolved.parts):
        raise ValueError(
            "Esa carpeta pertenece al sistema del computador y por seguridad no la abro.")
    if not resolved.exists():
        raise ValueError("Esa carpeta no existe en este equipo.")
    if not resolved.is_dir():
        raise ValueError("Esa ruta es un archivo, no una carpeta.")

    def _scan() -> tuple[list[dict], bool]:
        with os.scandir(resolved) as it:
            entries_sorted = sorted(it, key=lambda e: e.name.lower())
        items: list[dict] = []
        truncated = False
        for entry in entries_sorted:
            try:
                if not entry.is_dir(follow_symlinks=False):
                    continue
            except OSError:
                continue
            items.append({"name": entry.name, "path": str(Path(entry.path))})
            if len(items) >= 500:
                truncated = True
                break
        return items, truncated

    try:
        items, truncated = await asyncio.to_thread(_scan)
    except PermissionError:
        raise ValueError("No puedo abrir esa carpeta.")
    except OSError:
        raise ValueError("No puedo abrir esa carpeta.")

    is_drive_root = resolved == Path(resolved.anchor) or resolved.parent == resolved
    parent = None if is_drive_root else str(resolved.parent)
    return {"path": str(resolved), "parent": parent, "items": items, "truncated": truncated}


# ── registro / listado / baja de fuentes (RLS por tenant) ────────────────────
async def register_source(tenant_id: str, path: str, label: str | None = None,
                          kind: str = "knowledge", matter_id: str | None = None) -> dict:
    """Registra una carpeta en la allowlist del tenant (tras validarla). Si la misma
    ruta ya estaba registrada, la re-habilita y actualiza la etiqueta (idempotente).
    Lanza ValueError con mensaje en lenguaje llano si la ruta no es segura.

    kind='knowledge' (default): carpeta de conocimiento del despacho (matter_id NULL).
    kind='matters': carpeta vinculada a UN expediente — exige matter_id válido y del
    tenant (se valida bajo RLS: un asunto de otro despacho es invisible → se rechaza)."""
    if kind not in ("knowledge", "matters"):
        raise ValueError("No reconozco ese tipo de carpeta.")
    if kind == "matters":
        if not matter_id:
            raise ValueError("Necesito el expediente al que quieres vincular la carpeta.")
        # Pertenencia por RLS: si el asunto no es del despacho, no existe para esta conexión.
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT 1 FROM matters WHERE id=%s::uuid", (matter_id,))).fetchone()
        if row is None:
            raise ValueError("No encontré ese expediente en tu despacho.")
    else:
        matter_id = None   # las carpetas de conocimiento nunca llevan expediente
    resolved = validate_source_path(path)
    label = (label or resolved.name or "Carpeta de trabajo")[:200]
    async with pool.tenant_connection(tenant_id) as conn:
        if kind == "matters":
            # Una misma ruta NO puede servir a dos expedientes: el UNIQUE (tenant,path,kind)
            # haría que el UPDATE de abajo le "robara" la fuente al primero (y el segundo
            # heredaría los hashes → ingesta 0, silencioso). Activa → rechazo en llano;
            # desvinculada de OTRO expediente → se reasigna limpiando la memoria de
            # archivos vistos para que el expediente nuevo ingiera desde cero.
            prev = await (await conn.execute(
                "SELECT id, matter_id, enabled FROM local_folder_sources "
                "WHERE tenant_id=%s::uuid AND path=%s AND kind='matters'",
                (tenant_id, str(resolved)))).fetchone()
            if prev is not None and str(prev[1]) != str(matter_id):
                if prev[2]:
                    raise ValueError(
                        "Esa carpeta ya está vinculada a otro expediente. "
                        "Desvincúlala allá primero si quieres usarla en este.")
                await conn.execute(
                    "DELETE FROM local_file_hashes WHERE source_id=%s::uuid",
                    (str(prev[0]),))
        # UNIQUE (tenant_id, path, kind) en DB (migración 016): el insert es atómico y
        # sin carreras; si la fila ya existe, se re-habilita y refresca la etiqueta.
        row = await (await conn.execute(
            "INSERT INTO local_folder_sources (tenant_id, path, label, kind, matter_id) "
            "VALUES (%s::uuid, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, path, kind) DO NOTHING RETURNING id",
            (tenant_id, str(resolved), label, kind, matter_id),
        )).fetchone()
        if row is None:
            row = await (await conn.execute(
                "UPDATE local_folder_sources SET enabled=true, label=%s, matter_id=%s "
                "WHERE tenant_id=%s::uuid AND path=%s AND kind=%s RETURNING id",
                (label, matter_id, tenant_id, str(resolved), kind),
            )).fetchone()
        source_id = str(row[0])
    return {"id": source_id, "path": str(resolved), "label": label, "kind": kind,
            "enabled": True, "matter_id": matter_id}


async def list_sources(tenant_id: str, include_disabled: bool = False) -> list[dict]:
    """Fuentes registradas del tenant (por defecto solo las habilitadas)."""
    sql = ("SELECT id, path, label, kind, enabled, created_at, matter_id "
           "FROM local_folder_sources "
           + ("" if include_disabled else "WHERE enabled ")
           + "ORDER BY created_at")
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(sql)).fetchall()
    return [
        {"id": str(r[0]), "path": r[1], "label": r[2], "kind": r[3],
         "enabled": r[4], "created_at": r[5].isoformat(),
         "matter_id": str(r[6]) if r[6] else None}
        for r in rows
    ]


async def get_matter_sources(tenant_id: str, matter_id: str) -> list[dict]:
    """Todas las carpetas ACTIVAS vinculadas a un expediente (kind='matters'), de la más
    antigua a la más nueva (Bloque A · evolución de producto: un expediente ahora admite
    VARIAS carpetas — cada una se sincroniza y poda de forma independiente por su propio
    `source_id`, ver `_ingest_matter_file`/`_prune_matter_docs`)."""
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT id, path, label, kind, enabled, created_at FROM local_folder_sources "
            "WHERE matter_id=%s::uuid AND kind='matters' AND enabled "
            "ORDER BY created_at ASC",
            (matter_id,),
        )).fetchall()
    return [
        {"id": str(r[0]), "path": r[1], "label": r[2], "kind": r[3],
         "enabled": r[4], "created_at": r[5].isoformat(), "matter_id": str(matter_id)}
        for r in rows
    ]


async def get_matter_source(tenant_id: str, matter_id: str) -> dict | None:
    """DEPRECADO — usar `get_matter_sources()` (un expediente ahora admite varias
    carpetas). Se conserva para llamadores viejos que solo conocen "la" carpeta del
    expediente: devuelve la vinculada más recientemente, o None si no hay ninguna."""
    sources = await get_matter_sources(tenant_id, matter_id)
    if not sources:
        return None
    latest = sources[-1]   # get_matter_sources ya viene ordenado ASC por created_at
    return {"id": latest["id"], "path": latest["path"], "label": latest["label"],
            "kind": latest["kind"], "enabled": latest["enabled"], "matter_id": str(matter_id)}


def _live_query_terms(query: str) -> set[str]:
    """Términos simples para priorizar nombres de archivo sin usar API ni modelo."""
    import re

    return {w.casefold() for w in re.findall(r"[\wáéíóúñü]+", query or "") if len(w) >= 4}


def _validated_live_root(raw: str) -> Path:
    """Revalida que una raíz siga resolviendo al lugar autorizado al registrarla."""
    stored = Path(raw)
    root = stored.resolve()
    _check_safe_root(root)
    if str(root) != str(stored):
        raise ValueError("La ubicación real de la carpeta cambió desde que fue vinculada.")
    return root


async def read_matter_sources_live(tenant_id: str, matter_id: str,
                                   query: str) -> LiveMatterSourceRead:
    """Lee al vuelo carpetas locales ya vinculadas al expediente, sin indexarlas.

    La autorización se descubre en ``local_folder_sources`` bajo RLS mediante
    ``get_matter_sources``. Luego se repiten las dos defensas del sincronizador: raíz
    registrada todavía segura y cada archivo resuelto dentro de ella. No se entrega una
    herramienta, una terminal ni el perfil personal del ejecutor CLI; Mia abre únicamente
    archivos de lectura permitidos dentro de esa allowlist y devuelve texto para sellarlo
    como evidencia no confiable en el turno.

    La lectura es acotada por archivos, bytes y enumeración. Los nombres parecidos a la
    consulta van primero; el orden estable cubre el resto cuando la consulta es general.
    Cualquier fuente desmontada, archivo bloqueado o documento ilegible se omite sin tumbar
    el chat. No escribe contenido ni hashes en la base.
    """
    result = LiveMatterSourceRead()
    try:
        sources = await get_matter_sources(tenant_id, matter_id)
    except Exception:  # noqa: BLE001 — el turno recibe el límite en llano
        logger.warning("lectura al vuelo: no pude resolver las fuentes autorizadas",
                       exc_info=True)
        result.warnings.append(
            "No pude comprobar las carpetas vinculadas al caso en este turno."
        )
        return result
    if not sources:
        return result
    terms = _live_query_terms(query)
    sync = LocalFolderSync()
    candidates: list[tuple[int, str, dict, Path, Path]] = []
    for source in sources:
        try:
            root = _validated_live_root(source["path"])
            # La ruta se guardó resuelta al autorizarla. Si ahora resuelve a otro sitio
            # (junction/symlink cambiado), se cierra en vez de seguir el redireccionamiento.
            files, omitted, truncated = await asyncio.to_thread(
                sync._scan_folder, root, LIVE_SCAN_FILES)
        except Exception:  # noqa: BLE001 — una fuente inaccesible nunca tumba el chat
            logger.warning("lectura al vuelo omitida para fuente %s", source.get("id"),
                           exc_info=True)
            result.warnings.append(
                f"No pude abrir la carpeta vinculada «{source.get('label') or 'sin nombre'}» "
                "en este turno."
            )
            continue
        if truncated:
            result.warnings.append(
                f"La carpeta «{source.get('label') or root.name}» tiene más de "
                f"{LIVE_SCAN_FILES} archivos compatibles; la lectura de este turno es parcial."
            )
        if omitted:
            result.warnings.append(
                f"En «{source.get('label') or root.name}» omití {omitted} archivo(s) "
                "por tamaño, seguridad o porque no se podían leer."
            )
        if not files:
            result.warnings.append(
                f"La carpeta «{source.get('label') or root.name}» no contiene archivos "
                "compatibles que pueda leer en este turno."
            )
        for path in files:
            rel = sync._rel(root, path)
            score = sum(1 for term in terms if term in rel.casefold())
            candidates.append((-score, rel.casefold(), source, root, path))

    candidates.sort(key=lambda item: (item[0], item[1]))
    used_bytes = 0
    skipped_for_bytes = 0
    read_errors = 0
    for _score, _order, source, root, path in candidates:
        if len(result.files) >= LIVE_READ_FILES:
            break
        try:
            size = path.stat().st_size
            if size <= 0 or used_bytes + size > LIVE_READ_BYTES:
                skipped_for_bytes += 1
                continue
            # Revalidación justo antes de abrir: protege contra un cambio entre escaneo
            # y lectura (TOCTOU) y conserva el confinamiento a la raíz autorizada.
            if not sync._resolves_inside(root, path):
                continue
            text, meta = await asyncio.to_thread(sync._read_text, path)
            if not text.strip() or not meta.get("has_body", True):
                continue
        except Exception:  # noqa: BLE001
            logger.warning("lectura al vuelo: no pude abrir %s", path, exc_info=True)
            read_errors += 1
            continue
        used_bytes += size
        result.files.append({
            "source_id": source["id"],
            "source_label": source.get("label") or root.name,
            "source_path": sync._rel(root, path),
            "content": text,
        })
    if len(candidates) > len(result.files):
        unseen = max(0, len(candidates) - len(result.files) - read_errors - skipped_for_bytes)
        omitted_total = unseen + read_errors + skipped_for_bytes
        if omitted_total:
            result.warnings.append(
                f"La lectura directa incluyó {len(result.files)} archivo(s) y dejó "
                f"{omitted_total} fuera por los límites del turno o por errores de lectura."
            )
    return result


async def source_last_sync(tenant_id: str, source_id: str):
    """Momento de la última sincronización de una fuente (max updated_at de sus hashes),
    o None si nunca corrió. Sirve para el estado del expediente y el throttle de re-sync."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT max(updated_at) FROM local_file_hashes WHERE source_id=%s::uuid",
            (source_id,),
        )).fetchone()
    return row[0] if row else None


async def disable_source(tenant_id: str, source_id: str) -> bool:
    """Deshabilita una fuente. Devuelve False si no existe (o es ajena).

    kind='knowledge' (conocimiento del despacho): BORRA sus chunks y hashes (privacidad
    primero — quitar una carpeta saca su contenido del conocimiento de Mia de inmediato;
    re-habilitarla la re-indexa).

    kind='matters' (expediente vinculado): solo DESVINCULA — los documentos que ya trajo
    al expediente SE CONSERVAN (el abogado los sigue viendo). Los hashes también se
    conservan, así re-vincular la misma carpeta no re-ingiere lo que no cambió."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT kind FROM local_folder_sources WHERE id=%s::uuid", (source_id,))).fetchone()
        if row is None:
            return False
        kind = row[0]
        res = await conn.execute(
            "UPDATE local_folder_sources SET enabled=false WHERE id=%s::uuid",
            (source_id,),
        )
        if res.rowcount == 0:
            return False
        if kind == "matters":
            # Expediente vinculado: se conservan documents y hashes; solo se desvincula.
            return True
        await conn.execute(
            "DELETE FROM knowledge_chunks WHERE tenant_id=%s::uuid AND source=%s",
            (tenant_id, SOURCE_PREFIX + str(source_id)),
        )
        await conn.execute(
            "DELETE FROM local_file_hashes WHERE tenant_id=%s::uuid AND source_id=%s::uuid",
            (tenant_id, source_id),
        )
    return True


# ── exclusión mutua real por fuente (H1 · corrige carrera de sincronización) ──
# Dos sync de la MISMA fuente pueden dispararse por vías distintas al mismo tiempo
# (el cron sync_tenant, POST /api/folders/sync y los endpoints de expediente que
# lanzan sync en segundo plano) — sin candado, ambos hacen el borra-y-reinserta de
# _ingest_matter_file en paralelo y pueden dejar el mismo archivo duplicado en el
# expediente. Este dict vive a nivel de módulo (una sola vez por proceso, NO por
# instancia de LocalFolderSync) para que CUALQUIER llamador comparta el mismo
# candado de una fuente, sin importar por dónde entró. Crece como máximo un Lock
# por fuente registrada (docenas, no miles, en un despacho real) — no se limpia
# nunca, pero el costo es insignificante frente al riesgo de duplicar documentos;
# no hay anidamiento (sync_tenant sincroniza sus fuentes una tras otra, y cada una
# toma y suelta su propio candado antes de pasar a la siguiente), así que no hay
# riesgo de deadlock entre fuentes distintas.
_SOURCE_SYNC_LOCKS: dict[str, asyncio.Lock] = {}


def _lock_for(source_id: str) -> asyncio.Lock:
    """Devuelve el candado de esta fuente (lo crea la primera vez que se pide)."""
    lock = _SOURCE_SYNC_LOCKS.get(source_id)
    if lock is None:
        lock = asyncio.Lock()
        _SOURCE_SYNC_LOCKS[source_id] = lock
    return lock


# ── sincronizador ─────────────────────────────────────────────────────────────
class LocalFolderSync:
    """Sincroniza las carpetas registradas de un tenant con `knowledge_chunks`
    (incremental por hash sha256, mismo patrón que ObsidianSync)."""

    def __init__(self) -> None:
        self._md = ObsidianSync()   # re-usa el troceo por encabezados para .md

    # ── entry points ─────────────────────────────────────────────────────────
    async def sync_tenant(self, tenant_id: str) -> dict:
        """Sincroniza TODAS las fuentes habilitadas del tenant (conocimiento Y expedientes
        vinculados). Devuelve stats agregadas
        {sources, indexed, skipped, deleted, errors, omitted, deferred, pending}."""
        totals = {"sources": 0, "indexed": 0, "skipped": 0, "deleted": 0,
                  "errors": 0, "omitted": 0, "deferred": 0, "pending": 0}
        for source in await list_sources(tenant_id):
            totals["sources"] += 1
            stats = await self.sync_source(tenant_id, source)
            for k in ("indexed", "skipped", "deleted", "errors", "omitted", "deferred", "pending"):
                totals[k] += stats.get(k, 0)
        return totals

    async def sync_source(self, tenant_id: str, source: dict) -> dict:
        """Sincroniza UNA fuente registrada (allowlist · capa 2: re-valida la raíz y que
        su ruta real siga siendo la registrada antes de tocar el disco).

        Estrategia anti-pérdida de conocimiento:
          1. Pasada barata de SOLO hashes sobre todo lo escaneado (decide qué cambió).
          2. Se indexan (embeddings) como máximo MAX_FILES_PER_SYNC archivos nuevos o
             cambiados; los diferidos ('deferred') quedan SIN hash guardado, así la
             corrida siguiente los retoma — jamás se pierden en silencio.
          3. La poda (chunks de archivos borrados + hashes huérfanos) SOLO corre si el
             escaneo vio la carpeta completa; si la enumeración se truncó en
             MAX_SCAN_FILES, no se borra nada en esa corrida (los archivos no vistos
             podrían seguir existiendo)."""
        stats = {"indexed": 0, "skipped": 0, "deleted": 0, "errors": 0,
                 "omitted": 0, "deferred": 0, "pending": 0}
        kind = source.get("kind") or "knowledge"
        matter_id = source.get("matter_id")
        source_id = str(source["id"])
        async with _lock_for(source_id):
            registered = Path(source["path"])

            try:
                root = registered.resolve(strict=True)
            except OSError:
                logger.warning("fuente %s: la carpeta %s ya no existe — se omite",
                               source_id, registered)
                stats["errors"] += 1
                return stats
            # La ruta REAL debe seguir siendo (o estar dentro de) la registrada: si alguien
            # reemplazó la carpeta por un symlink hacia otro lugar, NO se escanea.
            if not (root == registered or root.is_relative_to(registered)):
                logger.warning("fuente %s: la ruta real (%s) ya no coincide con la registrada "
                               "(%s) — se omite por seguridad", source_id, root, registered)
                stats["errors"] += 1
                return stats
            try:
                _check_safe_root(root)
            except ValueError:
                logger.warning("fuente %s: la carpeta %s dejó de ser segura — se omite",
                               source_id, root)
                stats["errors"] += 1
                return stats
            if not root.is_dir():
                stats["errors"] += 1
                return stats

            files, omitted, truncated = self._scan_folder(root)
            stats["omitted"] = omitted
            current = {self._rel(root, f) for f in files}
            stored = await self._get_stored_hashes(tenant_id, source_id)
            db_source = SOURCE_PREFIX + source_id

            # Pasada 1 (barata): solo hashes — decide qué necesita reproceso realmente.
            new_hashes: dict[str, str] = {}
            to_process: list[tuple[Path, str]] = []
            for f in files:
                rel = self._rel(root, f)
                try:
                    h = self._hash_file(f)
                except Exception as exc:  # noqa: BLE001 — clasificamos bloqueo vs. error real
                    if _is_locked(exc):
                        # Archivo en uso (p. ej. abierto en Word, WinError 32): NO se descarta.
                        # Se conserva su hash previo — así no se re-indexa ni se poda su documento —
                        # y se cuenta como pendiente para reintentarlo en el próximo ciclo.
                        stats["pending"] += 1
                        if rel in stored:
                            new_hashes[rel] = stored[rel]
                        continue
                    stats["errors"] += 1
                    logger.exception("fuente %s: no pude leer %s", source_id, rel)
                    continue
                new_hashes[rel] = h
                if stored.get(rel) == h:
                    stats["skipped"] += 1
                else:
                    to_process.append((f, rel))

            # Ventana por corrida SOLO sobre nuevos/cambiados: lo diferido queda sin hash
            # guardado → la corrida siguiente lo retoma (nada se pierde en silencio).
            if len(to_process) > MAX_FILES_PER_SYNC:
                deferred = to_process[MAX_FILES_PER_SYNC:]
                to_process = to_process[:MAX_FILES_PER_SYNC]
                stats["deferred"] = len(deferred)
                for _, rel in deferred:
                    new_hashes.pop(rel, None)
                logger.warning(
                    "fuente %s: %d archivos nuevos/cambiados superan el límite de %d por "
                    "sincronización; %d quedan pendientes y se indexarán en la corrida siguiente",
                    source_id, len(to_process) + len(deferred), MAX_FILES_PER_SYNC, len(deferred),
                )

            # Pasada 2 (cara): extracción + embeddings + upsert, solo de lo que cambió.
            # Según el tipo de fuente el destino cambia: 'knowledge' → knowledge_chunks (RAG del
            # despacho); 'matters' → documents + chunks del expediente (origin='folder').
            for f, rel in to_process:
                try:
                    # M1: leer del disco + extraer (OCR incluido) es IO/CPU-pesado — va a un hilo
                    # para no congelar el event loop mientras se indexa una carpeta escaneada.
                    text, meta = await asyncio.to_thread(self._read_text, f)
                    # M3: un escaneo sin cuerpo legible (o sin motor de OCR) NO se ingesta como
                    # documento válido — vale para AMBOS destinos (expediente y conocimiento).
                    # Sin hash guardado → se reintenta si más adelante se instala la lectura óptica.
                    if not meta.get("has_body", True):
                        stats["omitted"] += 1
                        reason = ("escaneado y este servidor no tiene lectura óptica"
                                  if meta.get("ocr_unavailable") else "sin texto legible")
                        logger.info("fuente %s: omito %s (%s)", source_id, rel, reason)
                        new_hashes.pop(rel, None)
                        continue
                    if kind == "matters":
                        await self._ingest_matter_file(tenant_id, matter_id, source_id, rel,
                                                       text, new_hashes[rel], f,
                                                       offset_map=meta.get("folio_map") or [],
                                                       extraction_meta=meta)
                    else:
                        chunks = self._chunk_file(text, rel, meta)
                        vectors = await self._embed_chunks([c["text"] for c in chunks])
                        await self._upsert_chunks(tenant_id, db_source, rel, chunks, vectors)
                    stats["indexed"] += 1
                except Exception as exc:  # noqa: BLE001 — clasificamos bloqueo vs. error real
                    if _is_locked(exc):
                        # Se bloqueó entre la pasada 1 y la 2: se reintenta el próximo ciclo
                        # conservando el hash previo (no se poda su documento).
                        stats["pending"] += 1
                        if rel in stored:
                            new_hashes[rel] = stored[rel]
                        else:
                            new_hashes.pop(rel, None)
                        continue
                    stats["errors"] += 1
                    logger.exception("fuente %s: no pude indexar %s", source_id, rel)
                    # sin hash guardado → se reintenta en la próxima sincronización
                    new_hashes.pop(rel, None)

            if truncated:
                # El escaneo NO vio la carpeta completa: los archivos no vistos podrían
                # existir. No se borra NADA (ni chunks ni hashes) en esta corrida.
                logger.warning(
                    "fuente %s: el escaneo se truncó en %d archivos — en esta corrida se "
                    "omite la poda de archivos eliminados para no borrar conocimiento de "
                    "archivos que sí existen", source_id, MAX_SCAN_FILES,
                )
                await self._save_hashes(tenant_id, source_id, new_hashes, prune=False)
            else:
                if kind == "matters":
                    stats["deleted"] = await self._prune_matter_docs(tenant_id, matter_id,
                                                                       source_id, current)
                else:
                    stats["deleted"] = await self._delete_removed(tenant_id, db_source, current)
                await self._save_hashes(tenant_id, source_id, new_hashes)
            return stats

    # ── escaneo (allowlist · capa 2 por archivo) ─────────────────────────────
    def _scan_folder(self, root: Path,
                     max_files: int = MAX_SCAN_FILES) -> tuple[list[Path], int, bool]:
        """Archivos indexables bajo la raíz YA resuelta. Excluye carpetas/archivos ocultos
        ('.'/'~', node_modules, __pycache__) y directorios de SISTEMA (_FORBIDDEN_PARTS,
        case-insensitive) también en el descenso recursivo, archivos cuya ruta REAL apunte
        fuera de la carpeta registrada (symlinks de escape) y archivos > 20 MB. Corta la
        enumeración en MAX_SCAN_FILES con warning (tope duro defensivo). Devuelve
        (archivos, omitidos, truncado)."""
        files: list[Path] = []
        omitted = 0
        truncated = False
        for p in sorted(root.rglob("*")):
            if p.suffix.lower() not in ALLOWED_SUFFIXES:
                continue
            rel = p.relative_to(root)
            if any(self._excluded_part(part) for part in rel.parts):
                continue
            if not p.is_file():
                continue
            if not self._resolves_inside(root, p):
                logger.warning("se omite %s: su ruta real apunta fuera de la carpeta registrada", p)
                omitted += 1
                continue
            try:
                size = p.stat().st_size
            except OSError:
                omitted += 1
                continue
            if size > MAX_FILE_BYTES:
                logger.warning("se omite %s: pesa más de %d MB", p, MAX_FILE_BYTES // (1024 * 1024))
                omitted += 1
                continue
            files.append(p)
            if len(files) >= max_files:
                truncated = True
                logger.warning("carpeta %s: se alcanzó el tope duro de enumeración "
                               "(%d archivos); el escaneo queda INCOMPLETO y en esta "
                               "corrida no se podará nada", root, max_files)
                break
        return files, omitted, truncated

    @staticmethod
    def _excluded_part(part: str) -> bool:
        """True si el segmento se excluye del descenso: ocultos ('.'/'~'), carpetas de
        build (node_modules, __pycache__) y directorios de SISTEMA (_FORBIDDEN_PARTS,
        case-insensitive) — así una raíz legítima (p. ej. C:\\Users\\<usuario>) nunca
        arrastra AppData/ProgramData al índice (privacidad primero)."""
        return (
            part.startswith(".")
            or part.startswith("~")
            or part in EXCLUDED_DIR_NAMES
            or part.lower().rstrip("\\/") in _FORBIDDEN_PARTS
        )

    @staticmethod
    def _resolves_inside(root: Path, p: Path) -> bool:
        """True si la ruta REAL del archivo sigue dentro de la raíz registrada (los
        symlinks que escapan de la carpeta se omiten — nunca se lee fuera de la allowlist)."""
        try:
            rp = p.resolve()
        except OSError:
            return False
        return rp == root or rp.is_relative_to(root)

    @staticmethod
    def _rel(root: Path, f: Path) -> str:
        """Ruta relativa a la carpeta registrada, con separadores '/' (estable entre SO)."""
        return f.relative_to(root).as_posix()

    # ── hashing / lectura / chunking ─────────────────────────────────────────
    @staticmethod
    def _hash_file(path: Path) -> str:
        """sha256 del contenido del archivo (hex)."""
        return hashlib.sha256(Path(path).read_bytes()).hexdigest()

    @staticmethod
    def _read_text(p: Path) -> tuple[str, dict]:
        """Texto plano + metadata de OCR. PDF/Word vía extract_text_detailed (SÍNCRONA y
        CPU-pesada — el llamador la corre en un hilo, M1); .md/.txt lectura directa."""
        if p.suffix.lower() in ({".pdf"} | SUPPORTED_ANYDOC_EXTENSIONS):
            return extract_text_detailed(p.name, p.read_bytes())
        # .md/.txt: texto plano sin páginas → mapa de folios vacío (folio NULL). No inventar.
        return (p.read_text(encoding="utf-8", errors="replace"),
                {"has_body": True, "ocr_unavailable": False, "folio_map": []})

    def _chunk_file(self, text: str, rel: str, extraction_meta: dict | None = None) -> list[dict]:
        """.md → troceo por encabezados de ObsidianSync; el resto → chunk_text (ingest)."""
        if rel.lower().endswith(".md"):
            return self._md._chunk_document(text, rel)
        if (extraction_meta or {}).get("derivation", {}).get("parser") == "anydoc":
            structured = chunk_extracted_text(text, extraction_meta)
            return [
                {"text": piece, "heading_path": None, "position": i, "source_file": rel}
                for i, (piece, _folio) in enumerate(structured)
            ]
        return [
            {"text": piece, "heading_path": None, "position": i, "source_file": rel}
            for i, piece in enumerate(chunk_text(text))
        ]

    # ── embeddings (librería LiteLLM, batches de 128 — decisión #17 C2) ──────
    async def _embed_chunks(self, texts: list[str]) -> list[list[float] | None]:
        if not texts:
            return []
        vectors: list[list[float] | None] = []
        for i in range(0, len(texts), EMBED_BATCH):
            vectors.extend(embeddings.embed_texts_optional(texts[i:i + EMBED_BATCH]))
        return vectors

    # ── persistencia en knowledge_chunks (RLS por tenant) ────────────────────
    async def _upsert_chunks(self, tenant_id: str, db_source: str, filepath: str,
                             chunks: list[dict], vectors: list[list[float] | None]) -> None:
        """Upsert de los chunks de un archivo (ON CONFLICT) y poda de los sobrantes si
        el archivo encogió — mismo patrón que ObsidianSync."""
        async with pool.tenant_connection(tenant_id) as conn:
            for chunk, vec in zip(chunks, vectors):
                await conn.execute(
                    "INSERT INTO knowledge_chunks "
                    "  (tenant_id, source, source_path, chunk_index, heading_path, content, embedding) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id, source, source_path, chunk_index) DO UPDATE SET "
                    "  heading_path = EXCLUDED.heading_path, content = EXCLUDED.content, "
                    "  embedding = EXCLUDED.embedding, updated_at = now()",
                    (tenant_id, db_source, filepath, chunk["position"],
                     chunk["heading_path"], chunk["text"], vec),
                )
            pruned = await (await conn.execute(
                "DELETE FROM knowledge_chunks WHERE tenant_id = %s::uuid AND source = %s "
                "AND source_path = %s AND chunk_index >= %s RETURNING chunk_index",
                (tenant_id, db_source, filepath, len(chunks)),
            )).fetchall()
        await self._pinecone_mirror_upsert(tenant_id, db_source, filepath, chunks, vectors,
                                           pruned_indices=[r[0] for r in pruned])

    async def _delete_removed(self, tenant_id: str, db_source: str, current) -> int:
        """Borra los chunks cuyos archivos ya no existen en la carpeta. Devuelve el
        número de ARCHIVOS eliminados."""
        current = set(current)
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT DISTINCT source_path FROM knowledge_chunks "
                "WHERE tenant_id = %s::uuid AND source = %s",
                (tenant_id, db_source),
            )).fetchall()
            removed = sorted({r[0] for r in rows} - current)
            deleted_rows: list[tuple] = []
            if removed:
                deleted_rows = await (await conn.execute(
                    "DELETE FROM knowledge_chunks WHERE tenant_id = %s::uuid AND source = %s "
                    "AND source_path = ANY(%s) RETURNING source_path, chunk_index",
                    (tenant_id, db_source, removed),
                )).fetchall()
        if deleted_rows:
            ids = [f"{db_source}:{path}:{idx}" for path, idx in deleted_rows]
            await self._pinecone_mirror_delete(tenant_id, ids)
        return len(removed)

    # ── espejo en Pinecone (store SECUNDARIO opt-in, Módulo A) ───────────────
    async def _pinecone_mirror_upsert(self, tenant_id: str, db_source: str, filepath: str,
                                      chunks: list[dict], vectors: list[list[float] | None],
                                      *, pruned_indices: list[int]) -> None:
        """Espeja el upsert (y la poda por encogimiento) de ESTE archivo en Pinecone.
        Id determinista `{db_source}:{filepath}:{chunk_index}`: un re-sync hace upsert
        en sitio, nunca duplica. FAIL-SOFT total (mismo patrón que `wiki_notes` /
        `_notebooklm_context`): pgvector YA quedó escrito arriba; si Pinecone no está
        configurado (Noop) o la llamada falla, el sync del abogado sigue igual."""
        try:
            async with pinecone_scope_for_tenant(tenant_id) as pc:
                if not pc.is_configured:
                    return
                if chunks:
                    vectors_pc = []
                    for chunk, vec in zip(chunks, vectors):
                        if vec is None:
                            continue
                        metadata = {
                            "content": (chunk["text"] or "")[:2000],
                            "source": db_source,
                            "source_path": filepath,
                        }
                        if chunk.get("heading_path"):
                            metadata["heading_path"] = chunk["heading_path"]
                        vectors_pc.append({
                            "id": f"{db_source}:{filepath}:{chunk['position']}",
                            "values": vec,
                            "metadata": metadata,
                        })
                    await pc.upsert(tenant_id, vectors_pc)
                if pruned_indices:
                    ids = [f"{db_source}:{filepath}:{idx}" for idx in pruned_indices]
                    await pc.delete(tenant_id, ids)
        except Exception:  # noqa: BLE001 — Pinecone es opcional, jamás tumba el sync
            logger.warning("pinecone: upsert omitido para %s (tenant=%s)",
                           filepath, tenant_id, exc_info=True)

    async def _pinecone_mirror_delete(self, tenant_id: str, ids: list[str]) -> None:
        """Espeja en Pinecone el borrado de chunks cuyos archivos desaparecieron de la
        carpeta. FAIL-SOFT total — ver `_pinecone_mirror_upsert`."""
        try:
            async with pinecone_scope_for_tenant(tenant_id) as pc:
                if not pc.is_configured:
                    return
                await pc.delete(tenant_id, ids)
        except Exception:  # noqa: BLE001 — Pinecone es opcional, jamás tumba el sync
            logger.warning("pinecone: delete omitido para %d ids (tenant=%s)",
                           len(ids), tenant_id, exc_info=True)

    # ── persistencia del EXPEDIENTE VINCULADO (documents + chunks · RLS por tenant) ──
    async def _ingest_matter_file(self, tenant_id: str, matter_id, source_id: str, rel: str,
                                  text: str, sha256: str, path: Path,
                                  offset_map: list[tuple[int, int, int]] | None = None,
                                  extraction_meta: dict | None = None) -> None:
        """Ingesta un archivo de la carpeta vinculada al expediente: extrae texto, trocea,
        embebe e inserta un documento (origin='folder', source_path=ruta relativa, sha256,
        source_id=ESTA fuente) y sus chunks. Reemplaza SIEMPRE el documento previo de esa
        ruta (sus chunks caen por cascade) — así un archivo CAMBIADO no deja el documento
        viejo detrás. El DELETE previo está ACOTADO a `source_id`: solo pisa la versión
        anterior de ESTA MISMA carpeta y los huérfanos sin fuente trazada (documentos
        `origin='folder'` de antes de la migración 028, `source_id IS NULL`) — NUNCA los
        de OTRA carpeta vinculada al mismo expediente (bug de poda cruzada, ver
        memory/bugs-and-risks.md). Los documentos subidos a mano (origin='upload') NUNCA
        se tocan aquí."""
        # Troceo con folio: cada chunk hereda el folio (página) de su offset de inicio, medido
        # sobre el MISMO `text` que produjo extract (`offset_map`). Sin páginas → folio NULL.
        pairs = chunk_extracted_text(text, extraction_meta or {"folio_map": offset_map or []})
        async with pool.tenant_connection(tenant_id) as conn:
            # Borrar la versión previa de ESTA ruta traída por ESTA fuente (idempotente) —
            # o el huérfano pre-028 del mismo path, nunca la de una carpeta hermana.
            await conn.execute(
                "DELETE FROM documents WHERE matter_id=%s::uuid AND origin='folder' "
                "AND source_path=%s AND (source_id=%s::uuid OR source_id IS NULL)",
                (matter_id, rel, source_id))
            if not pairs:
                # Archivo sin texto útil: no se crea documento (quedó podado el anterior).
                return
            vectors = await self._embed_chunks([c for c, _ in pairs])
            doc_id = (await (await conn.execute(
                "INSERT INTO documents (tenant_id, matter_id, filename, mime, sha256, "
                "source_path, origin, source_id) VALUES "
                "(%s::uuid, %s::uuid, %s, %s, %s, %s, 'folder', %s::uuid) RETURNING id",
                (tenant_id, matter_id, path.name, _guess_mime(path.name), sha256, rel,
                 source_id),
            )).fetchone())[0]
            for i, ((content, folio), vec) in enumerate(zip(pairs, vectors)):
                await conn.execute(
                    "INSERT INTO chunks (tenant_id, document_id, ord, content, embedding, procedencia, folio_ancla) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)",
                    (tenant_id, doc_id, i, content, vec, "documento", folio))
        # Documento + chunks ya COMMITEADOS (cerró el `async with`): recién aquí el job ve la fila.
        # Triaje de metadata como trabajo recuperable — fail-soft, jamás rompe el sync de la carpeta.
        await enqueue_classification(tenant_id, doc_id)

    async def _prune_matter_docs(self, tenant_id: str, matter_id, source_id: str,
                                 current) -> int:
        """Borra los documentos origin='folder' DE ESTA FUENTE cuyos archivos ya no están
        en la carpeta. Acotado por `source_id`: el sync de UNA carpeta jamás poda los
        documentos que trajo OTRA carpeta hermana del mismo expediente (bug de poda
        cruzada corregido — antes el filtro era solo por matter_id). Los documentos con
        `source_id IS NULL` (huérfanos de antes de la migración 028, sin fuente trazada)
        NUNCA se podan por sync — conservador: mejor conservarlos que borrar algo que no
        se puede atribuir con certeza a esta carpeta. Los origin='upload' (subidos a mano)
        JAMÁS se tocan. Sus chunks caen por cascade. Devuelve el número de ARCHIVOS
        eliminados."""
        current = set(current)
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT DISTINCT source_path FROM documents "
                "WHERE matter_id=%s::uuid AND origin='folder' AND source_id=%s::uuid",
                (matter_id, source_id),
            )).fetchall()
            removed = sorted({r[0] for r in rows if r[0] is not None} - current)
            if removed:
                await conn.execute(
                    "DELETE FROM documents WHERE matter_id=%s::uuid AND origin='folder' "
                    "AND source_id=%s::uuid AND source_path = ANY(%s)",
                    (matter_id, source_id, removed),
                )
        return len(removed)

    # ── hashes (RLS por tenant) ───────────────────────────────────────────────
    async def _get_stored_hashes(self, tenant_id: str, source_id: str) -> dict[str, str]:
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT file_path, content_hash FROM local_file_hashes "
                "WHERE tenant_id = %s::uuid AND source_id = %s::uuid",
                (tenant_id, source_id),
            )).fetchall()
        return {r[0]: r[1] for r in rows}

    async def _save_hashes(self, tenant_id: str, source_id: str,
                           hashes: dict[str, str], prune: bool = True) -> None:
        """Upsert de los hashes vigentes + (si prune) borra los de archivos que ya no
        están, manteniendo la tabla en espejo con la carpeta. Con escaneo TRUNCADO se
        llama con prune=False: los archivos no vistos podrían existir y borrar su hash
        forzaría re-indexarlos (o peor, ya se habrían borrado sus chunks)."""
        async with pool.tenant_connection(tenant_id) as conn:
            for file_path, content_hash in hashes.items():
                await conn.execute(
                    "INSERT INTO local_file_hashes (tenant_id, source_id, file_path, content_hash) "
                    "VALUES (%s::uuid, %s::uuid, %s, %s) "
                    "ON CONFLICT (tenant_id, source_id, file_path) DO UPDATE SET "
                    "  content_hash = EXCLUDED.content_hash, updated_at = now()",
                    (tenant_id, source_id, file_path, content_hash),
                )
            if prune:
                await conn.execute(
                    "DELETE FROM local_file_hashes WHERE tenant_id = %s::uuid "
                    "AND source_id = %s::uuid AND NOT (file_path = ANY(%s))",
                    (tenant_id, source_id, list(hashes.keys()) or [""]),
                )
