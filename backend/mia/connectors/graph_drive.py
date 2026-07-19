"""Mia · connectors.graph_drive — OneDrive remoto SELECTIVO (Fase 3 · fuentes remotas).

El abogado NAVEGA su OneDrive (vía Microsoft Graph, para quien NO usa el cliente de
escritorio), ELIGE subcarpetas concretas ("la información que yo quiero ver", nunca todo
el drive) y Mia las sincroniza de forma incremental hacia el conocimiento del despacho
(kind='knowledge' → knowledge_chunks) o hacia un expediente (kind='matters' → documents +
chunks, origin='drive'). SOLO LECTURA: jamás se escribe contra Graph.

Consent-first / allowlist: solo se recorre lo que el despacho registró en
`remote_drive_sources` (migración 027). Molde del motor: connectors/local_folders.py
(LocalFolderSync) — dos pasadas conceptuales (identificación barata por eTag → ingesta con
embeddings solo de lo cambiado), incremental por `remote_file_hashes`, límites por corrida.
Diferencia con la carpeta local: los archivos NUNCA tocan disco (se descargan a memoria).

Aislamiento: TODA operación de DB por-tenant pasa por `pool.tenant_connection(tenant_id)`
(RLS activo, fail-closed). El motor de embeddings, el troceo y la extracción de texto se
reutilizan de local_folders/ingest para no divergir.

Renombrar/mover un archivo remoto (mismo item_id, mismo contenido, ruta nueva) NO lo pierde:
la ruta relativa se persiste en `remote_file_hashes.rel_path`; cuando el rel guardado difiere
del actual se MUEVE el documento/fragmentos a la ruta nueva (`_move_content`) en vez de dejarlo
huérfano bajo la vieja. Cubre el renombre con y sin cambio de eTag.

DEUDAS conocidas (anotadas, ver reporte):
  · Simetría con LocalFolderSync en el borrado: 'knowledge' borra sus chunks; 'matters' poda
    los documentos origin='drive' cuyo archivo remoto ya no existe, ACOTADA por `source_id`
    (mismo espejo del fix de poda cruzada de LocalFolderSync — ver memory/bugs-and-risks.md):
    el sync de UNA carpeta de OneDrive nunca poda los documentos que trajo OTRA carpeta
    hermana del mismo expediente (los origin='upload' y origin='folder' JAMÁS se tocan).
"""
from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timezone
from typing import Optional
from urllib.parse import quote

from ..db import pool
from ..jobs import enqueue_classification
from ..ingest.extract import extract_text_detailed_async
from ..ingest.ingest import chunk_text_with_folios
from .local_folders import (
    MAX_FILE_BYTES,
    MAX_FILES_PER_SYNC,
    MAX_SCAN_FILES,
    LocalFolderSync,
    _guess_mime,
)
from .mailbox.service import MailboxService

logger = logging.getLogger("mia.connectors.graph_drive")

GRAPH_BASE = "https://graph.microsoft.com/v1.0"
SOURCE_PREFIX = "drive:"                 # knowledge_chunks.source = 'drive:<source_id>'
ALLOWED_SUFFIXES = {".pdf", ".docx", ".txt", ".md"}
MAX_FOLDERS_PER_SCAN = 5000              # tope duro de carpetas visitadas por corrida (defensivo)
MAX_SOURCES_PER_TENANT = 20             # tope de carpetas remotas registradas por despacho
CRON_THROTTLE_HOURS = 1.0               # ventana del throttle del sync PROGRAMADO (bloque 3b)

# Lock anti-duplicado por fuente, COMPARTIDO entre el sync manual (api/routes/remote_drive.py)
# y el cron programado (cron/scheduler.py::sync_remote_drive_all_tenants). Vive aquí (no en la
# ruta) precisamente para que el scheduler pueda importarlo sin depender del módulo de rutas.
# Mismo comportamiento de antes: un clic manual y el cron nunca sincronizan la MISMA carpeta
# a la vez; el que llega segundo ve la fuente ya en vuelo y se salta (sin tumbar nada).
# INVARIANTE (M1): este set NO es thread-safe. Su `add`/`discard` DEBEN ejecutarse siempre
# en el event loop (nunca dentro de un `asyncio.to_thread`). Solo la extracción/OCR —que es
# CPU-pesada— se delega a un hilo; el candado se manipula antes y después, en el loop.
SYNCS_IN_FLIGHT: set[str] = set()


# ── errores del dominio ──────────────────────────────────────────────────────────
class GraphDriveError(RuntimeError):
    """Fallo al leer OneDrive vía Graph (se traduce a 502 en llano en la ruta)."""


class RemoteSourceError(RuntimeError):
    """Base de los errores de registro de una fuente remota (se mapean a HTTP en la ruta)."""


class DuplicateSourceError(RemoteSourceError):
    """La carpeta remota ya está registrada para ese tenant/kind (→ 409)."""


class SourceLimitError(RemoteSourceError):
    """Se alcanzó el tope de carpetas remotas por despacho (→ 422)."""


class MatterNotFoundError(RemoteSourceError):
    """El expediente indicado no existe o es de otro despacho (→ 404)."""


# ── cliente Graph de SOLO LECTURA (http inyectable, patrón de mailbox/providers.py) ─
class GraphDrive:
    """Lectura de OneDrive vía Microsoft Graph. `http` (get async estilo httpx) se inyecta
    para probar sin red. Ante cualquier error de API se lanza `GraphDriveError`."""

    provider = "microsoft"

    def __init__(self, creds, *, http, base: str = GRAPH_BASE) -> None:
        self._creds = creds
        self._http = http
        self._base = base

    async def _get_json(self, url: str, *, params: Optional[dict] = None) -> dict:
        headers = {"Authorization": f"Bearer {self._creds.access_token}",
                   "Accept": "application/json"}
        resp = await self._http.get(url, params=params or {}, headers=headers)
        status = getattr(resp, "status_code", 0)
        if status != 200:
            raise GraphDriveError(f"GET {url.split('?')[0]} devolvió status {status}")
        return resp.json()

    async def list_children(self, item_id: Optional[str] = None) -> list[dict]:
        """Carpetas y archivos de UN nivel (raíz si `item_id` es None). Sigue la paginación
        `@odata.nextLink` y devuelve la FORMA COMÚN neutral al proveedor:
        {id, name, is_folder, size, etag, modified}."""
        if item_id:
            url = f"{self._base}/me/drive/items/{quote(str(item_id), safe='')}/children"
        else:
            url = f"{self._base}/me/drive/root/children"
        params = {
            "$select": "id,name,folder,file,size,eTag,lastModifiedDateTime",
            "$top": "200",
        }
        out: list[dict] = []
        next_url: Optional[str] = url
        first = True
        while next_url:
            data = await self._get_json(next_url, params=params if first else None)
            first = False
            for it in data.get("value") or []:
                out.append(self._to_common(it))
            next_url = data.get("@odata.nextLink")
        return out

    async def download_file(self, item_id: str) -> bytes:
        """Bytes de UN archivo. Graph responde `/content` con un 302 hacia una URL
        pre-firmada de descarga; se sigue el redirect con un GET sin cabecera de autorización
        (la URL ya viene firmada). El tope de 20 MB se controla ANTES en el motor de sync
        usando el tamaño del árbol, así un archivo grande nunca llega a descargarse."""
        url = f"{self._base}/me/drive/items/{quote(str(item_id), safe='')}/content"
        headers = {"Authorization": f"Bearer {self._creds.access_token}"}
        resp = await self._http.get(url, headers=headers)
        status = getattr(resp, "status_code", 0)
        if status in (301, 302, 303, 307, 308):
            location = _resp_header(resp, "Location")
            if not location:
                raise GraphDriveError("descarga sin URL de redirección")
            resp = await self._http.get(location, headers={})
            status = getattr(resp, "status_code", 0)
        if status != 200:
            raise GraphDriveError(f"descarga de archivo devolvió status {status}")
        content = getattr(resp, "content", b"")
        return content if isinstance(content, (bytes, bytearray)) else bytes(content or b"")

    @staticmethod
    def _to_common(it: dict) -> dict:
        """driveItem de Graph → forma común. `folder` presente ⇒ carpeta; `eTag`/`cTag`
        detectan cambios baratos sin descargar."""
        return {
            "id": str(it.get("id") or ""),
            "name": str(it.get("name") or ""),
            "is_folder": it.get("folder") is not None,
            "size": int(it.get("size") or 0),
            "etag": str(it.get("eTag") or it.get("cTag") or ""),
            "modified": str(it.get("lastModifiedDateTime") or ""),
        }


def _resp_header(resp, name: str) -> str:
    """Lee una cabecera de la respuesta HTTP tolerando mayúsculas/minúsculas (httpx.Headers
    es case-insensitive; un doble de test usa un dict simple)."""
    headers = getattr(resp, "headers", None) or {}
    try:
        val = headers.get(name)
        if val is None:
            val = headers.get(name.lower())
        return str(val or "")
    except Exception:  # noqa: BLE001
        return ""


# ── servicio: resuelve el conector de OneDrive del tenant (tokens + refresco) ─────
class GraphDriveService:
    """Resuelve un `GraphDrive` listo para el tenant, reutilizando la plomería de tokens de
    MailboxService (cargar + refrescar + persistir). Devuelve None si el despacho no tiene
    Microsoft conectado, o si lo conectó SIN permiso de archivos (Files.Read) — en ambos
    casos la ruta responde 503 en llano. `http`/`store_mod`/... se inyectan para pruebas."""

    def __init__(self, *, http=None, store_mod=None, oauth_mod=None,
                 client_credentials=None) -> None:
        self._svc = MailboxService(http=http, store_mod=store_mod, oauth_mod=oauth_mod,
                                   client_credentials=client_credentials)

    async def connector_for(self, tenant_id: str, provider: str = "microsoft"):
        """GraphDrive del tenant, o None (sin cuenta Microsoft / sin permiso de archivos)."""
        creds = await self._svc.fresh_creds(tenant_id, provider)
        if creds is None:
            return None
        if "Files.Read" not in (creds.scopes or ()):
            # Conectado, pero sin el permiso de archivos: se trata como "no disponible"
            # (la ruta pide reconectar con permiso de archivos).
            return None
        return GraphDrive(creds, http=self._svc.client_http())

    async def aclose(self) -> None:
        await self._svc.aclose()


# ── allowlist de fuentes remotas (RLS por tenant) ────────────────────────────────
async def register_source(tenant_id: str, remote_item_id: str, label: str | None = None,
                          kind: str = "knowledge", matter_id: str | None = None,
                          provider: str = "microsoft") -> dict:
    """Registra una carpeta de OneDrive en la allowlist del tenant.

    kind='knowledge' (default): conocimiento del despacho (matter_id NULL).
    kind='matters': vinculada a UN expediente — exige matter_id del propio despacho (se
    valida bajo RLS: un asunto ajeno es invisible → MatterNotFoundError).

    Errores: kind inválido / item vacío → ValueError; expediente ajeno → MatterNotFoundError;
    ya registrada → DuplicateSourceError; tope por despacho → SourceLimitError."""
    if kind not in ("knowledge", "matters"):
        raise ValueError("No reconozco ese tipo de carpeta.")
    if not remote_item_id or not str(remote_item_id).strip():
        raise ValueError("Necesito la carpeta de OneDrive que quieres que Mia conozca.")
    remote_item_id = str(remote_item_id).strip()
    if kind == "matters":
        if not matter_id:
            raise ValueError("Necesito el expediente al que quieres vincular la carpeta.")
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT 1 FROM matters WHERE id=%s::uuid", (matter_id,))).fetchone()
        if row is None:
            raise MatterNotFoundError("No encontré ese expediente en tu despacho.")
    else:
        matter_id = None
    label = (label or "Carpeta de OneDrive")[:200]

    async with pool.tenant_connection(tenant_id) as conn:
        total = (await (await conn.execute(
            "SELECT count(*) FROM remote_drive_sources WHERE enabled")).fetchone())[0]
        if total >= MAX_SOURCES_PER_TENANT:
            raise SourceLimitError(
                f"Llegaste al máximo de {MAX_SOURCES_PER_TENANT} carpetas de OneDrive. "
                f"Quita alguna que ya no uses antes de agregar otra.")
        row = await (await conn.execute(
            "INSERT INTO remote_drive_sources (tenant_id, provider, remote_item_id, label, kind, matter_id) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id, provider, remote_item_id, kind) DO NOTHING RETURNING id",
            (tenant_id, provider, remote_item_id, label, kind, matter_id),
        )).fetchone()
    if row is None:
        raise DuplicateSourceError("Esa carpeta de OneDrive ya está agregada.")
    return {"id": str(row[0]), "remote_item_id": remote_item_id, "label": label,
            "kind": kind, "matter_id": matter_id, "enabled": True, "provider": provider}


async def list_sources(tenant_id: str) -> list[dict]:
    """Fuentes remotas registradas del tenant, con su última sincronización (si la hubo)."""
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT s.id, s.label, s.kind, s.matter_id, s.enabled, s.remote_item_id, s.created_at, "
            "  s.last_synced_at AS last_sync "
            "FROM remote_drive_sources s WHERE s.enabled ORDER BY s.created_at",
        )).fetchall()
    return [
        {"id": str(r[0]), "label": r[1], "kind": r[2],
         "matter_id": str(r[3]) if r[3] else None, "enabled": r[4],
         "remote_item_id": r[5], "created_at": r[6].isoformat(),
         "last_sync": r[7].isoformat() if r[7] else None}
        for r in rows
    ]


async def get_source(tenant_id: str, source_id: str) -> dict | None:
    """Una fuente remota registrada del tenant, o None si no existe (o es ajena)."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT id, label, kind, matter_id, enabled, remote_item_id "
            "FROM remote_drive_sources WHERE id=%s::uuid AND enabled", (source_id,))).fetchone()
    if row is None:
        return None
    return {"id": str(row[0]), "label": row[1], "kind": row[2],
            "matter_id": str(row[3]) if row[3] else None, "enabled": row[4],
            "remote_item_id": row[5]}


async def source_last_sync(tenant_id: str, source_id: str):
    """Momento de la última sincronización COMPLETADA (last_synced_at de la fuente), o None.
    Se marca al final de cada corrida aunque la carpeta esté vacía, así el throttle también
    aplica a carpetas sin archivos (m2)."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT last_synced_at FROM remote_drive_sources WHERE id=%s::uuid AND enabled",
            (source_id,))).fetchone()
    return row[0] if row else None


async def delete_source(tenant_id: str, source_id: str) -> bool:
    """Quita una fuente remota. False si no existe (o es ajena).

    Simétrico con folders.py: 'knowledge' BORRA su conocimiento indexado (privacidad
    primero — quitar la carpeta la saca del conocimiento de Mia de inmediato); 'matters'
    CONSERVA los documentos ya traídos al expediente (el abogado los sigue viendo). En
    ambos casos se elimina la fila registrada y sus hashes (cascade por FK)."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT kind FROM remote_drive_sources WHERE id=%s::uuid", (source_id,))).fetchone()
        if row is None:
            return False
        kind = row[0]
        if kind == "knowledge":
            await conn.execute(
                "DELETE FROM knowledge_chunks WHERE tenant_id=%s::uuid AND source=%s",
                (tenant_id, SOURCE_PREFIX + str(source_id)))
        res = await conn.execute(
            "DELETE FROM remote_drive_sources WHERE id=%s::uuid", (source_id,))
    return res.rowcount > 0


# ── motor de sincronización (calcado de LocalFolderSync.sync_source) ──────────────
class RemoteDriveSync:
    """Sincroniza UNA carpeta remota registrada. Recibe el conector `GraphDrive` ya resuelto
    (o un doble en las pruebas). Reutiliza el troceo/embeddings/upsert de LocalFolderSync
    para 'knowledge' y un molde propio (origin='drive') para 'matters'."""

    def __init__(self, connector: "GraphDrive") -> None:
        self._drive = connector
        self._local = LocalFolderSync()   # reutiliza chunking/embeddings/upsert/poda

    async def sync_source(self, tenant_id: str, source: dict) -> dict:
        """Recorre el árbol de la carpeta remota (BFS), detecta cambios por eTag (barato,
        sin descargar) y por sha256 (contenido), ingiere solo lo nuevo/cambiado y poda lo
        borrado. Devuelve {ingested, unchanged, skipped, deleted, errors, deferred}."""
        stats = {"ingested": 0, "unchanged": 0, "skipped": 0, "deleted": 0,
                 "errors": 0, "deferred": 0}
        kind = source.get("kind") or "knowledge"
        matter_id = source.get("matter_id")
        source_id = str(source["id"])
        root_id = source["remote_item_id"]
        db_source = SOURCE_PREFIX + source_id

        try:
            files, oversize, truncated = await self._scan_tree(root_id)
        except Exception:  # noqa: BLE001 — no se pudo leer la carpeta raíz remota
            logger.warning("fuente remota %s: no pude leer la carpeta en OneDrive", source_id)
            stats["errors"] += 1
            return stats
        stats["skipped"] += oversize

        current_rels = {f["rel"] for f in files}
        stored = await self._get_stored_hashes(tenant_id, source_id)

        new_hashes: dict[str, tuple[str, str, str]] = {}
        to_process: list[dict] = []
        for f in files:
            st = stored.get(f["item_id"])
            if st is not None and st[0] and st[0] == f["etag"]:
                # eTag idéntico → sin cambios de contenido: no se descarga (pasada barata).
                # Pero la RUTA pudo cambiar (renombre/movimiento sin cambio de eTag): si el rel
                # guardado difiere del actual, se MUEVE el contenido a la ruta nueva (no se re-
                # descarga) para que la poda por ruta no lo borre bajo la ruta vieja.
                stats["unchanged"] += 1
                if st[2] and st[2] != f["rel"]:
                    try:
                        await self._move_content(tenant_id, kind, matter_id, source_id,
                                                 db_source, st[2], f["rel"], f["name"])
                    except Exception:  # noqa: BLE001 — un movimiento que falle no tumba la corrida
                        logger.warning("fuente remota %s: no pude mover %s → %s",
                                       source_id, st[2], f["rel"])
                new_hashes[f["item_id"]] = (st[0], st[1], f["rel"])
            else:
                to_process.append(f)

        # Ventana por corrida: lo diferido queda SIN hash guardado → la corrida siguiente lo
        # retoma (nada se pierde en silencio, igual criterio que LocalFolderSync).
        if len(to_process) > MAX_FILES_PER_SYNC:
            deferred = to_process[MAX_FILES_PER_SYNC:]
            to_process = to_process[:MAX_FILES_PER_SYNC]
            stats["deferred"] = len(deferred)
            logger.warning("fuente remota %s: %d archivos superan el límite de %d por corrida; "
                           "%d quedan pendientes", source_id, len(to_process) + len(deferred),
                           MAX_FILES_PER_SYNC, len(deferred))

        for f in to_process:
            try:
                blob = await self._drive.download_file(f["item_id"])
                sha = hashlib.sha256(blob).hexdigest()
                st = stored.get(f["item_id"])
                if st is not None and st[1] and st[1] == sha:
                    # Cambió el eTag pero el contenido es idéntico. Si además cambió la RUTA
                    # (renombre/movimiento), se MUEVE el contenido a la ruta nueva en vez de
                    # dejarlo bajo la vieja (que la poda borraría); si no, solo se refresca el eTag.
                    stats["unchanged"] += 1
                    if st[2] and st[2] != f["rel"]:
                        await self._move_content(tenant_id, kind, matter_id, source_id,
                                                 db_source, st[2], f["rel"], f["name"])
                    new_hashes[f["item_id"]] = (f["etag"], sha, f["rel"])
                    continue
                text, meta = await self._text_from_bytes(f["name"], blob)
                # M3: un escaneo sin cuerpo legible (o sin motor de OCR) se cuenta como
                # OMITIDO con motivo — NO se ingesta un placeholder como si fuera válido. Sin
                # hash guardado → se reintenta si más adelante se instala la lectura óptica.
                if not meta.get("has_body", True):
                    stats["skipped"] += 1
                    reason = ("escaneado y este servidor no tiene lectura óptica"
                              if meta.get("ocr_unavailable") else "sin texto legible")
                    logger.info("fuente remota %s: omito %s (%s)", source_id, f.get("rel"), reason)
                    continue
                if kind == "matters":
                    await self._ingest_matter_file(tenant_id, matter_id, source_id, f["rel"],
                                                   f["name"], text, sha,
                                                   offset_map=meta.get("folio_map") or [])
                else:
                    chunks = self._local._chunk_file(text, f["rel"])
                    vectors = await self._local._embed_chunks([c["text"] for c in chunks])
                    await self._local._upsert_chunks(tenant_id, db_source, f["rel"], chunks, vectors)
                new_hashes[f["item_id"]] = (f["etag"], sha, f["rel"])
                stats["ingested"] += 1
            except Exception:  # noqa: BLE001 — un archivo malo no tumba la corrida
                stats["errors"] += 1
                logger.exception("fuente remota %s: no pude ingerir %s", source_id, f.get("rel"))
                # sin hash guardado → se reintenta en la próxima sincronización

        if truncated:
            # Escaneo incompleto: no se poda NADA (los no vistos podrían existir).
            await self._save_hashes(tenant_id, source_id, new_hashes, prune=False)
        else:
            if kind == "matters":
                stats["deleted"] = await self._prune_matter_docs(tenant_id, matter_id, source_id,
                                                                   current_rels)
            else:
                stats["deleted"] = await self._local._delete_removed(tenant_id, db_source, current_rels)
            await self._save_hashes(tenant_id, source_id, new_hashes, prune=True)
        # Marca la carpeta como revisada AHORA (haya o no archivos): de aquí salen el "última
        # revisión" y el throttle, así una carpeta vacía también queda marcada (m2).
        await self._touch_source(tenant_id, source_id)
        return stats

    # ── escaneo del árbol remoto (BFS, tope duro defensivo) ──────────────────────
    async def _scan_tree(self, root_id: str) -> tuple[list[dict], int, bool]:
        """Archivos indexables bajo la carpeta remota (BFS). Excluye extensiones no
        soportadas y archivos > 20 MB (contados como omitidos, sin descargarse). Corta en
        MAX_SCAN_FILES / MAX_FOLDERS_PER_SCAN (defensivo). Devuelve (archivos, omitidos,
        truncado). Un fallo listando la RAÍZ propaga; listar una SUBCARPETA que falla se
        omite (fail-soft, no tumba la corrida)."""
        files: list[dict] = []
        oversize = 0
        truncated = False
        # La raíz puede fallar (propaga → sync_source cuenta error y sale).
        root_children = await self._drive.list_children(root_id)
        queue: list[tuple[dict, str]] = [(c, "") for c in root_children]
        folders_seen = 0
        while queue:
            node, prefix = queue.pop(0)
            name = node.get("name") or ""
            if name.startswith(".") or name.startswith("~"):
                continue
            if node.get("is_folder"):
                if folders_seen >= MAX_FOLDERS_PER_SCAN:
                    truncated = True
                    logger.warning("fuente remota: se alcanzó el tope de carpetas (%d); "
                                   "escaneo INCOMPLETO", MAX_FOLDERS_PER_SCAN)
                    break
                folders_seen += 1
                child_prefix = f"{prefix}{name}/"
                try:
                    kids = await self._drive.list_children(node["id"])
                except Exception:  # noqa: BLE001 — subcarpeta ilegible: se omite ese subárbol
                    logger.warning("fuente remota: no pude leer una subcarpeta; se omite")
                    continue
                for k in kids:
                    queue.append((k, child_prefix))
                continue
            # archivo
            suffix = ("." + name.rsplit(".", 1)[-1].lower()) if "." in name else ""
            if suffix not in ALLOWED_SUFFIXES:
                continue
            if int(node.get("size") or 0) > MAX_FILE_BYTES:
                oversize += 1
                continue
            files.append({"item_id": str(node["id"]), "rel": f"{prefix}{name}",
                          "name": name, "size": int(node.get("size") or 0),
                          "etag": str(node.get("etag") or "")})
            if len(files) >= MAX_SCAN_FILES:
                truncated = True
                logger.warning("fuente remota: se alcanzó el tope de archivos (%d); "
                               "escaneo INCOMPLETO", MAX_SCAN_FILES)
                break
        return files, oversize, truncated

    @staticmethod
    async def _text_from_bytes(name: str, blob: bytes) -> tuple[str, dict]:
        """Texto plano + metadata de OCR. PDF/Word vía extract_text (en hilo — M1: el OCR es
        CPU-pesado y no debe congelar el cron ni los demás jobs); .md/.txt decodificados."""
        if name.lower().endswith((".pdf", ".docx")):
            return await extract_text_detailed_async(name, blob)
        # .md/.txt: texto plano sin páginas → mapa de folios vacío (folio NULL). No inventar.
        return (blob.decode("utf-8", errors="replace"),
                {"has_body": True, "ocr_unavailable": False, "folio_map": []})

    # ── persistencia del EXPEDIENTE VINCULADO (documents origin='drive' + chunks) ──
    async def _ingest_matter_file(self, tenant_id: str, matter_id, source_id: str, rel: str,
                                  name: str, text: str, sha256: str,
                                  offset_map: list[tuple[int, int, int]] | None = None) -> None:
        """Ingesta un archivo remoto al expediente: extrae texto, trocea, embebe e inserta un
        documento (origin='drive', source_path=ruta relativa, sha256, source_id=ESTA fuente)
        y sus chunks. Reemplaza SIEMPRE el documento previo de esa ruta (sus chunks caen por
        cascade) — así un archivo CAMBIADO no deja el documento viejo detrás. El DELETE previo
        está ACOTADO a `source_id`: solo pisa la versión anterior de ESTA MISMA carpeta remota
        y los huérfanos sin fuente trazada (`source_id IS NULL`, de antes del backfill de la
        migración 028) — NUNCA los de OTRA carpeta de OneDrive vinculada al mismo expediente
        (bug de poda cruzada, ver memory/bugs-and-risks.md). Los documentos subidos a mano
        (origin='upload') y los de carpetas locales (origin='folder') NUNCA se tocan aquí."""
        # Troceo con folio: cada chunk hereda el folio (página) de su offset de inicio, medido
        # sobre el MISMO `text` que produjo extract (`offset_map`). Sin páginas → folio NULL.
        pairs = chunk_text_with_folios(text, offset_map or [])
        # Los embeddings se calculan ANTES de abrir la conexión por-tenant (igual que la ruta
        # de conocimiento): una llamada de red al servicio de embeddings no debe mantener
        # abierta una conexión con RLS del pool (m6).
        vectors = await self._local._embed_chunks([c for c, _ in pairs]) if pairs else []
        async with pool.tenant_connection(tenant_id) as conn:
            # Borrar la versión previa de ESTA ruta traída por ESTA fuente (idempotente) —
            # o el huérfano pre-028 del mismo path, nunca la de una carpeta remota hermana.
            await conn.execute(
                "DELETE FROM documents WHERE matter_id=%s::uuid AND origin='drive' "
                "AND source_path=%s AND (source_id=%s::uuid OR source_id IS NULL)",
                (matter_id, rel, source_id))
            if not pairs:
                return
            doc_id = (await (await conn.execute(
                "INSERT INTO documents (tenant_id, matter_id, filename, mime, sha256, "
                "source_path, origin, source_id) VALUES "
                "(%s::uuid, %s::uuid, %s, %s, %s, %s, 'drive', %s::uuid) RETURNING id",
                (tenant_id, matter_id, name, _guess_mime(name), sha256, rel, source_id),
            )).fetchone())[0]
            for i, ((content, folio), vec) in enumerate(zip(pairs, vectors)):
                await conn.execute(
                    "INSERT INTO chunks (tenant_id, document_id, ord, content, embedding, procedencia, folio_ancla) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s)",
                    (tenant_id, doc_id, i, content, vec, "documento", folio))
        # Documento + chunks ya COMMITEADOS (cerró el `async with`): recién aquí el job ve la fila.
        # Triaje de metadata como trabajo recuperable — fail-soft, jamás rompe el sync de OneDrive.
        await enqueue_classification(tenant_id, doc_id)

    async def _prune_matter_docs(self, tenant_id: str, matter_id, source_id: str,
                                 current_rels) -> int:
        """Borra los documentos origin='drive' DE ESTA FUENTE cuyos archivos ya no están en la
        carpeta remota. Acotado por `source_id`: el sync de UNA carpeta de OneDrive jamás poda
        los documentos que trajo OTRA carpeta hermana del mismo expediente (bug de poda cruzada
        corregido — antes el filtro era solo por matter_id, mismo patrón que LocalFolderSync).
        Los documentos con `source_id IS NULL` (huérfanos de antes del backfill de la migración
        028, sin fuente trazada) NUNCA se podan por sync — conservador: mejor conservarlos que
        borrar algo que no se puede atribuir con certeza a esta carpeta. Los origin='upload'/
        'folder' JAMÁS se tocan. Devuelve el número de ARCHIVOS podados."""
        current = set(current_rels)
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT DISTINCT source_path FROM documents "
                "WHERE matter_id=%s::uuid AND origin='drive' AND source_id=%s::uuid",
                (matter_id, source_id))).fetchall()
            removed = sorted({r[0] for r in rows if r[0] is not None} - current)
            if removed:
                await conn.execute(
                    "DELETE FROM documents WHERE matter_id=%s::uuid AND origin='drive' "
                    "AND source_id=%s::uuid AND source_path = ANY(%s)",
                    (matter_id, source_id, removed))
        return len(removed)

    async def _move_content(self, tenant_id: str, kind: str, matter_id, source_id: str,
                            db_source: str, old_rel: str, new_rel: str, name: str) -> None:
        """Renombre/movimiento remoto (mismo item_id y mismo contenido, ruta distinta): en vez
        de re-descargar y re-embeber, se MUEVE el contenido ya ingerido de `old_rel` a `new_rel`.
        Sin esto, la poda por ruta borraría el archivo al no hallar la ruta vieja entre las
        actuales, y el conocimiento/expediente lo perdería en silencio (hallazgo M1). Para
        kind='matters' el UPDATE está ACOTADO por `source_id` (o huérfano sin fuente trazada,
        source_id IS NULL) — mismo criterio anti-poda-cruzada de `_ingest_matter_file`/
        `_prune_matter_docs`: mover nunca debe tocar el documento de OTRA carpeta hermana."""
        async with pool.tenant_connection(tenant_id) as conn:
            if kind == "matters":
                await conn.execute(
                    "UPDATE documents SET source_path=%s, filename=%s "
                    "WHERE matter_id=%s::uuid AND origin='drive' AND source_path=%s "
                    "AND (source_id=%s::uuid OR source_id IS NULL)",
                    (new_rel, name, matter_id, old_rel, source_id))
            else:
                await conn.execute(
                    "UPDATE knowledge_chunks SET source_path=%s "
                    "WHERE tenant_id=%s::uuid AND source=%s AND source_path=%s",
                    (new_rel, tenant_id, db_source, old_rel))

    async def _touch_source(self, tenant_id: str, source_id: str) -> None:
        """Marca la fuente como sincronizada AHORA (last_synced_at=now()). De aquí salen la
        última revisión que ve el abogado y el throttle de re-sync, también para carpetas
        vacías (que no dejan filas en remote_file_hashes) — hallazgo m2."""
        async with pool.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "UPDATE remote_drive_sources SET last_synced_at=now() WHERE id=%s::uuid",
                (source_id,))

    # ── hashes remotos (RLS por tenant) ──────────────────────────────────────────
    async def _get_stored_hashes(self, tenant_id: str, source_id: str) -> dict[str, tuple[str, str, str]]:
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT item_id, etag, sha256, rel_path FROM remote_file_hashes "
                "WHERE tenant_id=%s::uuid AND source_id=%s::uuid",
                (tenant_id, source_id))).fetchall()
        return {r[0]: (r[1] or "", r[2] or "", r[3] or "") for r in rows}

    async def _save_hashes(self, tenant_id: str, source_id: str,
                           hashes: dict[str, tuple[str, str, str]], prune: bool = True) -> None:
        """Upsert de los hashes vigentes (por item_id, incluida la ruta relativa para detectar
        renombres) + (si prune) borra los de archivos que ya no están. Con escaneo truncado se
        llama con prune=False (los no vistos podrían existir; borrar su hash forzaría re-
        indexarlos o perder su rastro)."""
        async with pool.tenant_connection(tenant_id) as conn:
            for item_id, (etag, sha, rel) in hashes.items():
                await conn.execute(
                    "INSERT INTO remote_file_hashes (tenant_id, source_id, item_id, etag, sha256, rel_path) "
                    "VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id, source_id, item_id) DO UPDATE SET "
                    "  etag=EXCLUDED.etag, sha256=EXCLUDED.sha256, rel_path=EXCLUDED.rel_path, "
                    "  synced_at=now()",
                    (tenant_id, source_id, item_id, etag, sha, rel))
            if prune:
                await conn.execute(
                    "DELETE FROM remote_file_hashes WHERE tenant_id=%s::uuid "
                    "AND source_id=%s::uuid AND NOT (item_id = ANY(%s))",
                    (tenant_id, source_id, list(hashes.keys()) or [""]))


# ── cron: sincronización PROGRAMADA de todas las fuentes de un tenant (bloque 3b) ────
async def sync_tenant_sources(tenant_id: str, service: "GraphDriveService",
                              *, throttle_hours: float = CRON_THROTTLE_HOURS) -> dict:
    """Sincroniza TODAS las fuentes remotas HABILITADAS de un tenant — usado por el job
    programado del scheduler (`cron/scheduler.py::sync_remote_drive_all_tenants`).

    Fail-soft en dos niveles, igual criterio que LocalFolderSync/ObsidianSync:
      · Tenant sin cuenta Microsoft conectada (o sin permiso Files.Read) → silencio total:
        devuelve {"no_account": True} SIN tocar ninguna fuente. Es el estado normal de un
        despacho que no conectó OneDrive, no un error.
      · Una fuente que falle (token vencido a mitad de corrida, carpeta borrada en OneDrive,
        error inesperado) se cuenta en 'failed' y NO detiene las demás fuentes del tenant.

    Throttle programado: una fuente sincronizada hace menos de `throttle_hours` se salta
    (columna `last_synced_at`, la MISMA que usa el throttle de 60s del botón manual).

    Lock COMPARTIDO con el sync manual (`SYNCS_IN_FLIGHT`, arriba en este módulo): si el
    abogado ya disparó un sync manual de esa carpeta (o el cron mismo la está sincronizando
    en otra corrida), esta fuente se salta en vez de duplicar la sincronización.

    Devuelve {"no_account": False, "synced", "skipped_throttle", "skipped_lock", "failed"}."""
    conn = await service.connector_for(tenant_id)
    if conn is None:
        logger.debug("cron OneDrive: tenant %s sin cuenta Microsoft con permiso de archivos "
                     "— silencio", tenant_id)
        return {"no_account": True, "synced": 0, "skipped_throttle": 0,
                "skipped_lock": 0, "failed": 0}

    stats = {"no_account": False, "synced": 0, "skipped_throttle": 0,
             "skipped_lock": 0, "failed": 0}
    for source in await list_sources(tenant_id):
        sid = str(source["id"])
        # MEN4: `list_sources` YA trae `last_sync` (mismo `last_synced_at`) → sin round-trip
        # redundante por fuente a la DB.
        last_iso = source.get("last_sync")
        if last_iso is not None:
            last = datetime.fromisoformat(last_iso)
            elapsed_hours = (datetime.now(timezone.utc) - last).total_seconds() / 3600
            if elapsed_hours < throttle_hours:
                stats["skipped_throttle"] += 1
                continue
        if sid in SYNCS_IN_FLIGHT:
            stats["skipped_lock"] += 1
            continue
        SYNCS_IN_FLIGHT.add(sid)
        try:
            await RemoteDriveSync(conn).sync_source(tenant_id, source)
            stats["synced"] += 1
        except Exception:  # noqa: BLE001 — una fuente rota no debe tumbar el ciclo ni las demás
            stats["failed"] += 1
            logger.exception("cron OneDrive: sync falló (tenant=%s fuente=%s)", tenant_id, sid)
        finally:
            SYNCS_IN_FLIGHT.discard(sid)
    return stats
