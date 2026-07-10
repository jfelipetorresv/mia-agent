"""
Mia · test_remote_drive.py — gate de la Fase 3 "OneDrive remoto SELECTIVO".

El abogado NAVEGA su OneDrive (vía Microsoft Graph), ELIGE subcarpetas concretas y Mia las
sincroniza de forma incremental hacia el conocimiento del despacho (knowledge_chunks) o hacia
un expediente (documents + chunks, origin='drive'). SOLO LECTURA. Consent-first.

Verifica OFFLINE (Graph doblado, sin red) contra la DB REAL (documents/chunks/knowledge_chunks
+ remote_file_hashes + RLS), en el estilo de test_mail_to_matter.py y test_matter_folder.py:

  Cliente Graph (HTTP doblado):
    · list_children pagina (@odata.nextLink) y mapea la forma común {id,name,is_folder,size,etag,modified}
    · download_file sigue el 302 hacia la URL pre-firmada y devuelve los bytes

  Motor de sync (RemoteDriveSync con conector doblado, DB real):
    · 'knowledge': ingiere un árbol (carpeta + subcarpeta, pdf+txt) → knowledge_chunks; ignora
      un tipo no soportado y omite un archivo >20 MB SIN descargarlo
    · 'matters': ingiere → documents origin='drive' + chunks con embedding
    · segunda sync sin cambios → todo 'unchanged' y CERO descargas
    · cambio de eTag con MISMO contenido → solo actualiza eTag (no re-ingiere)
    · cambio REAL de contenido → re-ingiere sin duplicar
    · RENOMBRE/MOVIMIENTO remoto (mismo item_id/contenido, ruta nueva) → el documento/chunks se
      MUEVEN a la ruta nueva, sin duplicar ni podar (knowledge y matters)
    · archivo borrado en remoto → poda simétrica (knowledge borra chunks; matters poda docs 'drive')

  Superficie HTTP (TestClient + JWT, servicio de OneDrive doblado):
    · browse mapea la forma común; sin conexión → 503
    · registrar fuente (knowledge y matters); duplicado → 409; matter ajeno → 404; tope → 422
    · RLS: las fuentes de un despacho son invisibles para otro
    · lock anti-duplicado + throttle de 60s

  Cron de sincronización PROGRAMADA (bloque 3b — cierra la deuda #1 de la sesión 36):
    · scheduler: sync_remote_drive_all_tenants registrado (6h)
    · sync_tenant_sources: tenant sin cuenta Microsoft conectada → silencio total (no_account)
    · sync_tenant_sources: fuente sincronizada hace poco (< throttle) → se salta
    · sync_tenant_sources: una fuente rota (token vencido simulado) NO tumba las demás
    · sync_tenant_sources: lock compartido con el sync manual (SYNCS_IN_FLIGHT) → no duplica
    · sync_remote_drive_all_tenants: itera tenants reales (enumeración por DB) y sincroniza

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_remote_drive.py
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from mia import config, embeddings                       # noqa: E402
from mia.db import pool                                   # noqa: E402
from mia.connectors import graph_drive as gd             # noqa: E402
from mia.connectors.graph_drive import (                 # noqa: E402
    RemoteDriveSync,
    delete_source,
    get_source,
    list_sources,
    register_source,
    source_last_sync,
)
from mia.cron import build_scheduler                      # noqa: E402
from mia.cron import scheduler as cron_scheduler          # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── embeddings stub (sin red): vector(EMBED_DIM) determinista ────────────────────
def _fake_embed(texts):
    return [[0.01 * (i + 1) for _ in range(config.EMBED_DIM)] for i, _ in enumerate(texts)]


embeddings.embed_texts = _fake_embed

FORBIDDEN = ("oauth", "graph", "tenant", "eTag".lower(), "token", "scope",
             "hitl", "langgraph", "pgvector", "chunk", "embedding")

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)

CAP = gd.MAX_FILE_BYTES


def make_docx(text: str) -> bytes:
    import docx
    d = docx.Document()
    d.add_paragraph(text)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ── dobles de HTTP para el cliente Graph (estilo test_mailbox.RouteHttp) ─────────
class FakeResp:
    def __init__(self, status, payload=None, content=b"", headers=None):
        self.status_code = status
        self._payload = payload
        self.content = content
        self.headers = headers or {}

    def json(self):
        return self._payload


class RouteHttp:
    def __init__(self, routes: dict):
        self._routes = routes
        self.calls: list = []

    async def get(self, url, params=None, headers=None):
        self.calls.append(url)
        # Match más específico primero. La página 2 (nextLink) contiene TAMBIÉN la subcadena
        # de la página 1 (".../children"), así que una clave con 'skiptoken' presente en la
        # URL gana para no reservir la página 1 en bucle infinito.
        matches = [k for k in self._routes if k in url]
        if not matches:
            return FakeResp(404, {})
        matches.sort(key=lambda k: (("skiptoken" in k), len(k)), reverse=True)
        return self._routes[matches[0]]


async def graph_client_checks() -> None:
    """Mapeo REAL del JSON de Graph → forma común + paginación + descarga con 302 (HTTP doblado)."""
    from mia.connectors.mailbox.base import OAuthCreds

    file_bytes = b"%PDF-1.4 contenido remoto de prueba"
    http = RouteHttp({
        # página 1 con nextLink → página 2 (una carpeta y un archivo repartidos)
        "/me/drive/root/children": FakeResp(200, {
            "value": [
                {"id": "F1", "name": "Subcarpeta", "folder": {"childCount": 1},
                 "size": 0, "eTag": "e-f1", "lastModifiedDateTime": "2026-07-02T10:00:00Z"},
            ],
            "@odata.nextLink": "https://graph.microsoft.com/v1.0/me/drive/root/children?$skiptoken=abc",
        }),
        "$skiptoken=abc": FakeResp(200, {"value": [
            {"id": "D1", "name": "demanda.pdf", "file": {"mimeType": "application/pdf"},
             "size": len(file_bytes), "eTag": "e-d1",
             "lastModifiedDateTime": "2026-07-03T11:00:00Z"},
        ]}),
        # descarga: 302 → URL pre-firmada con los bytes
        "/me/drive/items/D1/content": FakeResp(302, headers={"Location": "https://dl.example/D1"}),
        "https://dl.example/D1": FakeResp(200, content=file_bytes),
    })
    drive = gd.GraphDrive(OAuthCreds("microsoft", "AT", scopes=("Files.Read",)), http=http)

    children = await drive.list_children(None)
    by_id = {c["id"]: c for c in children}
    check("Graph.list_children: pagina (@odata.nextLink) y trae ambos niveles (2 ítems)",
          len(children) == 2 and "F1" in by_id and "D1" in by_id)
    check("Graph.list_children: mapea la forma común (carpeta vs archivo, size, etag, modified)",
          by_id["F1"]["is_folder"] is True and by_id["D1"]["is_folder"] is False
          and by_id["D1"]["size"] == len(file_bytes) and by_id["D1"]["etag"] == "e-d1"
          and by_id["D1"]["modified"].startswith("2026-07-03"))

    blob = await drive.download_file("D1")
    check("Graph.download_file: sigue el 302 a la URL pre-firmada y devuelve los bytes",
          blob == file_bytes)


# ── conector de OneDrive DOBLADO (árbol en memoria, cuenta descargas) ────────────
class FakeDrive:
    """Doble de GraphDrive: sirve list_children/download_file desde un árbol en memoria.

    `tree`: dict item_id -> lista de hijos en forma común {id,name,is_folder,size,etag}.
    `blobs`: dict item_id -> bytes. Cuenta las descargas para probar el incremental."""

    provider = "microsoft"

    def __init__(self, tree: dict, blobs: dict):
        self.tree = tree
        self.blobs = blobs
        self.downloads: list[str] = []
        self.list_calls: list[str] = []

    async def list_children(self, item_id=None):
        key = item_id if item_id is not None else "__root__"
        self.list_calls.append(key)
        return [dict(c) for c in self.tree.get(key, [])]

    async def download_file(self, item_id):
        self.downloads.append(item_id)
        if item_id not in self.blobs:
            raise gd.GraphDriveError("archivo inexistente en el doble")
        return self.blobs[item_id]


def _f(item_id, name, size, etag, is_folder=False):
    return {"id": item_id, "name": name, "is_folder": is_folder, "size": size,
            "etag": etag, "modified": "2026-07-02T10:00:00Z"}


def make_tenants() -> tuple[str, str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A test drive') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test drive') RETURNING id").fetchone()[0]
    return str(a), str(b)


def make_matter(tenant_id: str, title: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO matters(tenant_id, title) VALUES(%s::uuid, %s) RETURNING id",
            (tenant_id, title)).fetchone()[0])


def drop_tenants(a: str, b: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([a, b],))


# Conteos directos (postgres es superusuario → ignora RLS).
def sql_count_knowledge(tenant_id: str, source_id: str) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(DISTINCT source_path) FROM knowledge_chunks "
            "WHERE tenant_id=%s::uuid AND source=%s",
            (tenant_id, "drive:" + source_id)).fetchone()[0]


def sql_count_docs(matter_id: str, origin: str = "drive") -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin=%s",
            (matter_id, origin)).fetchone()[0]


def sql_chunks_with_embedding(matter_id: str) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM chunks ch JOIN documents d ON d.id=ch.document_id "
            "WHERE d.matter_id=%s::uuid AND d.origin='drive' AND ch.embedding IS NOT NULL",
            (matter_id,)).fetchone()[0]


def sql_doc_has_path(matter_id: str, path: str) -> bool:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='drive' "
            "AND source_path=%s", (matter_id, path)).fetchone()[0] > 0


def sql_knowledge_has_path(tenant_id: str, source_id: str, path: str) -> bool:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM knowledge_chunks WHERE tenant_id=%s::uuid AND source=%s "
            "AND source_path=%s", (tenant_id, "drive:" + source_id, path)).fetchone()[0] > 0


# ── checks del motor de sync (DB real, Graph doblado) ────────────────────────────
async def sync_checks(a: str, matter_a: str) -> None:
    await pool.open_pool()
    try:
        pdf_bytes = b"%PDF-1.4 poliza remota del despacho"
        txt_bytes = "Notas de conocimiento del despacho sobre seguros.".encode("utf-8")
        big_bytes = b"x"  # su 'size' declarado supera el tope: no debe descargarse

        # Árbol: raíz KA con subcarpeta SUB; archivos pdf+txt+un .zip no soportado+un gigante
        tree = {
            "KA": [_f("SUB", "Subcarpeta", 0, "e-sub", is_folder=True),
                   _f("T1", "notas.txt", len(txt_bytes), "e-t1"),
                   _f("Z1", "archivo.zip", 10, "e-z1"),               # no soportado
                   _f("G1", "gigante.pdf", CAP + 1, "e-g1")],         # >20 MB
            "SUB": [_f("P1", "poliza.pdf", len(pdf_bytes), "e-p1")],
        }
        blobs = {"T1": txt_bytes, "P1": pdf_bytes, "G1": big_bytes}
        drive = FakeDrive(tree, blobs)

        # extract_text doblado para el PDF (evita depender de PyMuPDF con bytes falsos).
        # M1: el connector ahora extrae vía extract_text_detailed_async (en hilo) → el doble
        # es async y devuelve (texto, meta) con has_body True.
        orig_extract = gd.extract_text_detailed_async

        async def fake_extract(filename, data):
            return (f"Texto extraído de {filename}: coberturas y clausulas remotas.",
                    {"has_body": True, "ocr_unavailable": False})

        gd.extract_text_detailed_async = fake_extract

        # ── KNOWLEDGE ────────────────────────────────────────────────────────────
        ksrc = await register_source(a, "KA", label="Conocimiento OneDrive", kind="knowledge")
        s1 = await RemoteDriveSync(drive).sync_source(a, ksrc)
        check("knowledge sync inicial: ingiere pdf+txt (ingested=2), omite el gigante (skipped=1)",
              s1["ingested"] == 2 and s1["skipped"] == 1 and s1["errors"] == 0)
        check("knowledge sync inicial: NO se descarga el archivo >20 MB",
              "G1" not in drive.downloads)
        check("knowledge sync inicial: el .zip no soportado se ignora (no se descarga)",
              "Z1" not in drive.downloads)
        check("knowledge: 2 archivos en knowledge_chunks (source='drive:<id>')",
              sql_count_knowledge(a, ksrc["id"]) == 2)

        # segunda sync sin cambios → todo unchanged, CERO descargas
        drive.downloads.clear()
        s2 = await RemoteDriveSync(drive).sync_source(a, ksrc)
        check("knowledge re-sync sin cambios: todo 'unchanged' (=2), ingested=0",
              s2["unchanged"] == 2 and s2["ingested"] == 0)
        check("knowledge re-sync sin cambios: CERO descargas (incremental por eTag)",
              len(drive.downloads) == 0)

        # cambio de eTag con MISMO contenido → solo actualiza eTag (no re-ingiere)
        drive.downloads.clear()
        tree["SUB"][0]["etag"] = "e-p1-v2"   # el eTag cambia; el blob P1 es el mismo
        s3 = await RemoteDriveSync(drive).sync_source(a, ksrc)
        check("knowledge: eTag distinto pero MISMO contenido → unchanged, ingested=0",
              s3["ingested"] == 0 and s3["unchanged"] == 2 and "P1" in drive.downloads)

        # cambio REAL de contenido → re-ingiere sin duplicar
        drive.downloads.clear()
        blobs["P1"] = b"%PDF-1.4 poliza remota CORREGIDA con nuevas coberturas"
        tree["SUB"][0]["etag"] = "e-p1-v3"
        s4 = await RemoteDriveSync(drive).sync_source(a, ksrc)
        check("knowledge: contenido REAL cambiado → re-ingiere (ingested=1) sin duplicar (siguen 2)",
              s4["ingested"] == 1 and sql_count_knowledge(a, ksrc["id"]) == 2)

        # RENOMBRE remoto (mismo item_id/contenido, nombre+eTag nuevos): T1 "notas.txt" →
        # "notas-2026.txt". El archivo debe SOBREVIVIR bajo la ruta nueva, sin duplicar ni podar.
        drive.downloads.clear()
        tree["KA"][1]["name"] = "notas-2026.txt"   # T1 es el índice 1 en KA
        tree["KA"][1]["etag"] = "e-t1-v2"
        sren = await RemoteDriveSync(drive).sync_source(a, ksrc)
        check("knowledge rename: mismo contenido, ruta nueva → sin re-ingesta ni duplicados (siguen 2)",
              sql_count_knowledge(a, ksrc["id"]) == 2 and sren["deleted"] == 0 and sren["ingested"] == 0)
        check("knowledge rename: los fragmentos viven bajo la ruta NUEVA (notas-2026.txt), no la vieja",
              sql_knowledge_has_path(a, ksrc["id"], "notas-2026.txt")
              and not sql_knowledge_has_path(a, ksrc["id"], "notas.txt"))

        # archivo borrado en remoto → poda sus chunks
        del tree["SUB"][0]           # se borra poliza.pdf del remoto
        s5 = await RemoteDriveSync(drive).sync_source(a, ksrc)
        check("knowledge: archivo borrado en remoto → poda (deleted=1) y queda 1 archivo",
              s5["deleted"] == 1 and sql_count_knowledge(a, ksrc["id"]) == 1)

        # ── MATTERS (documents origin='drive') ───────────────────────────────────
        tree2 = {
            "MA": [_f("MT1", "contrato.txt", len(txt_bytes), "e-mt1"),
                   _f("MP1", "anexo.pdf", len(pdf_bytes), "e-mp1")],
        }
        drive2 = FakeDrive(tree2, {"MT1": txt_bytes, "MP1": pdf_bytes})
        msrc = await register_source(a, "MA", label="Carpeta del expediente", kind="matters",
                                     matter_id=matter_a)
        sm1 = await RemoteDriveSync(drive2).sync_source(a, msrc)
        check("matters sync inicial: ingiere 2 → documents origin='drive'",
              sm1["ingested"] == 2 and sql_count_docs(matter_a) == 2)
        check("matters: los documentos tienen fragmentos con embedding",
              sql_chunks_with_embedding(matter_a) >= 2)

        # RENOMBRE remoto en el expediente (mismo item_id/contenido, nombre+eTag nuevos):
        # MT1 "contrato.txt" → "contrato-final.txt". El documento se MUEVE de ruta, no se
        # re-ingiere ni se poda (hallazgo M1).
        drive2.downloads.clear()
        tree2["MA"][0]["name"] = "contrato-final.txt"   # MT1 es el índice 0 en MA
        tree2["MA"][0]["etag"] = "e-mt1-v2"
        smren = await RemoteDriveSync(drive2).sync_source(a, msrc)
        check("matters rename: mismo contenido, ruta nueva → sin duplicar ni podar (siguen 2 docs)",
              sql_count_docs(matter_a) == 2 and smren["deleted"] == 0 and smren["ingested"] == 0)
        check("matters rename: el documento vive bajo la ruta NUEVA (contrato-final.txt), no la vieja",
              sql_doc_has_path(matter_a, "contrato-final.txt") and not sql_doc_has_path(matter_a, "contrato.txt"))

        # archivo borrado en remoto → poda documentos origin='drive'
        del tree2["MA"][1]           # se borra anexo.pdf
        sm2 = await RemoteDriveSync(drive2).sync_source(a, msrc)
        check("matters: archivo borrado en remoto → poda documento 'drive' (deleted=1, queda 1)",
              sm2["deleted"] == 1 and sql_count_docs(matter_a) == 1)

        # ── ANTI-PODA-CRUZADA (H11): DOS carpetas de OneDrive del MISMO expediente ──────
        # Espejo del fix de LocalFolderSync: cada fuente drive poda SOLO lo que ella misma
        # trajo (documents.source_id), nunca lo que trajo una carpeta hermana del mismo
        # expediente. Sin el fix, _prune_matter_docs filtraba solo por matter_id y el sync
        # de UNA carpeta borraba en silencio los documentos de la OTRA.
        baseline_docs = sql_count_docs(matter_a)   # 1 doc de la fuente MA de arriba
        txt_cruce = "Contrato de la carpeta A del expediente.".encode("utf-8")
        pdf_cruce = b"%PDF-1.4 contrato de la carpeta B del expediente"
        tree_cross = {
            "CA": [_f("CA1", "contrato_a.txt", len(txt_cruce), "e-ca1")],
            "CB": [_f("CB1", "contrato_b.pdf", len(pdf_cruce), "e-cb1")],
        }
        drive_cross = FakeDrive(tree_cross, {"CA1": txt_cruce, "CB1": pdf_cruce})
        src_ca = await register_source(a, "CA", label="Carpeta A del expediente", kind="matters",
                                       matter_id=matter_a)
        src_cb = await register_source(a, "CB", label="Carpeta B del expediente", kind="matters",
                                       matter_id=matter_a)

        sca1 = await RemoteDriveSync(drive_cross).sync_source(a, src_ca)
        scb1 = await RemoteDriveSync(drive_cross).sync_source(a, src_cb)
        check("anti-poda-cruzada: ambas carpetas ingieren su propio archivo (1 cada una)",
              sca1["ingested"] == 1 and scb1["ingested"] == 1)
        check("anti-poda-cruzada: los DOS documentos conviven en el expediente",
              sql_count_docs(matter_a) == baseline_docs + 2
              and sql_doc_has_path(matter_a, "contrato_a.txt")
              and sql_doc_has_path(matter_a, "contrato_b.pdf"))

        # Un archivo desaparece de la carpeta A (se borra en OneDrive) y se re-sincroniza
        # SOLO A → el documento de B debe seguir intacto (antes del fix, se habría borrado).
        del tree_cross["CA"][0]
        sca2 = await RemoteDriveSync(drive_cross).sync_source(a, src_ca)
        check("anti-poda-cruzada: re-sync de A poda SU PROPIO archivo borrado (deleted=1)",
              sca2["deleted"] == 1 and not sql_doc_has_path(matter_a, "contrato_a.txt"))
        check("anti-poda-cruzada: el documento de la carpeta HERMANA B sigue intacto "
              "(la poda de A no lo tocó)",
              sql_doc_has_path(matter_a, "contrato_b.pdf")
              and sql_count_docs(matter_a) == baseline_docs + 1)

        gd.extract_text_detailed_async = orig_extract
    finally:
        await pool.close_pool()


# ── dobles del servicio de OneDrive para el CRON (bloque 3b) ─────────────────────
class FakeCronService:
    """Doble de GraphDriveService para el cron: mapea tenant_id -> conector (o None si el
    despacho no tiene cuenta Microsoft conectada). `aclose` no-op (sin red real)."""

    def __init__(self, connectors: dict):
        self._connectors = connectors

    async def connector_for(self, tenant_id, provider="microsoft"):
        return self._connectors.get(tenant_id)

    async def aclose(self):
        pass


def set_last_synced(source_id: str, seconds_ago: float) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute(
            "UPDATE remote_drive_sources SET last_synced_at = now() - (%s || ' seconds')::interval "
            "WHERE id=%s::uuid", (seconds_ago, source_id))


# ── checks del cron de sincronización PROGRAMADA (bloque 3b) ────────────────────
async def cron_checks(c_tenant: str, d_tenant: str) -> None:
    """Ejercita connectors.graph_drive.sync_tenant_sources (motor del cron) y
    cron.scheduler.sync_remote_drive_all_tenants (wiring: enumeración de tenants reales +
    GraphDriveService), con Graph doblado y DB real. Sin red ni cuentas Microsoft reales."""
    await pool.open_pool()
    try:
        txt_bytes = "Notas del cron para el conocimiento del despacho.".encode("utf-8")

        # tenant C: cuenta Microsoft conectada, con 3 fuentes: una que sincroniza bien, una
        # que se sincronizó hace un instante (throttle) y una cuyo token está "vencido"
        # (simulado) para probar que una fuente rota no tumba a las demás.
        src_ok = await register_source(c_tenant, "C-OK", label="ok", kind="knowledge")
        src_recent = await register_source(c_tenant, "C-RECENT", label="reciente", kind="knowledge")
        src_bad = await register_source(c_tenant, "C-BAD", label="rota", kind="knowledge")
        set_last_synced(src_recent["id"], seconds_ago=60)   # hace 1 minuto: dentro del throttle de 1h

        tree_c = {
            "C-OK": [_f("CT1", "notas.txt", len(txt_bytes), "e-ct1")],
            "C-RECENT": [_f("CT2", "notas2.txt", len(txt_bytes), "e-ct2")],
            "C-BAD": [_f("CT3", "notas3.txt", len(txt_bytes), "e-ct3")],
        }
        drive_c = FakeDrive(tree_c, {"CT1": txt_bytes, "CT2": txt_bytes, "CT3": txt_bytes})
        orig_extract = gd.extract_text_detailed_async

        async def _cron_extract(name, data):
            return ("texto de prueba del cron", {"has_body": True, "ocr_unavailable": False})

        gd.extract_text_detailed_async = _cron_extract

        # Simula "token vencido a mitad de corrida"/"carpeta borrada" para C-BAD: envuelve
        # RemoteDriveSync para que ESA fuente lance, y deja las demás intactas.
        OrigSync = gd.RemoteDriveSync

        class RaisingSync:
            def __init__(self, connector):
                self._inner = OrigSync(connector)

            async def sync_source(self, tenant_id, source):
                if source["remote_item_id"] == "C-BAD":
                    raise RuntimeError("token vencido (simulado)")
                return await self._inner.sync_source(tenant_id, source)

        gd.RemoteDriveSync = RaisingSync
        try:
            service_c = FakeCronService({c_tenant: drive_c})
            stats_c = await gd.sync_tenant_sources(c_tenant, service_c, throttle_hours=1)
        finally:
            gd.RemoteDriveSync = OrigSync
            gd.extract_text_detailed_async = orig_extract

        check("cron: fuente sana se sincroniza (synced=1)", stats_c["synced"] == 1)
        check("cron: fuente sincronizada hace poco se salta por throttle (skipped_throttle=1)",
              stats_c["skipped_throttle"] == 1)
        check("cron: fuente rota (token vencido simulado) falla SIN tumbar a las demás "
              "(failed=1, synced sigue en 1)",
              stats_c["failed"] == 1 and stats_c["synced"] == 1)
        check("cron: tenant con cuenta conectada → no_account=False", stats_c["no_account"] is False)

        # tenant D: sin cuenta Microsoft conectada (o sin permiso de archivos) → silencio total,
        # cero fuentes tocadas, sin error ruidoso.
        await register_source(d_tenant, "D-1", label="sin cuenta", kind="knowledge")
        service_d = FakeCronService({})   # connector_for devuelve None para cualquier tenant
        stats_d = await gd.sync_tenant_sources(d_tenant, service_d, throttle_hours=1)
        check("cron: tenant SIN cuenta Microsoft conectada → silencio total (no_account=True, cero syncs)",
              stats_d["no_account"] is True and stats_d["synced"] == 0 and stats_d["failed"] == 0)

        # lock COMPARTIDO con el sync manual: si el endpoint manual ya está sincronizando esta
        # MISMA fuente (SYNCS_IN_FLIGHT), el cron la ve en vuelo y se salta (no la duplica).
        set_last_synced(src_ok["id"], seconds_ago=999999)   # fuera del throttle: forzaría re-sync
        gd.SYNCS_IN_FLIGHT.add(str(src_ok["id"]))
        try:
            service_c2 = FakeCronService({c_tenant: drive_c})
            stats_lock = await gd.sync_tenant_sources(c_tenant, service_c2, throttle_hours=1)
        finally:
            gd.SYNCS_IN_FLIGHT.discard(str(src_ok["id"]))
        check("cron: lock compartido con el sync manual (SYNCS_IN_FLIGHT) → no duplica "
              "una fuente ya en vuelo (skipped_lock>=1)",
              stats_lock["skipped_lock"] >= 1)

        # ── wiring del job completo: scheduler.build_scheduler + sync_remote_drive_all_tenants ──
        jobs = {j["name"]: j for j in build_scheduler().list_jobs()}
        check("scheduler: sync_remote_drive_all_tenants registrado cada 6h",
              "sync_remote_drive_all_tenants" in jobs
              and jobs["sync_remote_drive_all_tenants"]["interval_hours"] == 6)

        # el job real enumera tenants por DB (admin) y sincroniza con GraphDriveService real —
        # se dobla la CLASE (el cron la instancia sin argumentos) para no tocar red/tokens.
        set_last_synced(src_ok["id"], seconds_ago=999999)
        set_last_synced(src_recent["id"], seconds_ago=999999)

        class FixedService:
            async def connector_for(self, tenant_id, provider="microsoft"):
                return {c_tenant: drive_c}.get(tenant_id)

            async def aclose(self):
                pass

        orig_service_cls = gd.GraphDriveService
        gd.RemoteDriveSync = RaisingSync  # C-BAD sigue rota: confirma fail-soft también aquí
        gd.extract_text_detailed_async = _cron_extract
        gd.GraphDriveService = FixedService
        try:
            out = await cron_scheduler.sync_remote_drive_all_tenants()
        finally:
            gd.GraphDriveService = orig_service_cls
            gd.RemoteDriveSync = OrigSync
            gd.extract_text_detailed_async = orig_extract

        check("cron job: sync_remote_drive_all_tenants itera tenants reales (enumeración por "
              "DB) y trae stats del tenant con fuentes habilitadas",
              c_tenant in out and isinstance(out[c_tenant], dict)
              and out[c_tenant].get("no_account") is False)
        check("cron job: un tenant sin fuentes tocadas no aparece con error (fail-soft, no "
              "tumba a los demás)",
              not isinstance(out.get(c_tenant), dict) or "error" not in out[c_tenant])
    finally:
        await pool.close_pool()


# ── dobles del servicio de OneDrive para la superficie HTTP ──────────────────────
class FakeService:
    """Doble de GraphDriveService: devuelve un FakeDrive (o None si 'sin cuenta')."""

    def __init__(self, connector):
        self._connector = connector

    async def connector_for(self, tenant_id, provider="microsoft"):
        return self._connector

    async def aclose(self):
        pass


# ── checks de la superficie HTTP (TestClient + JWT) ──────────────────────────────
def api_checks(a: str, b: str, matter_a: str, matter_b: str) -> None:
    import jwt
    from fastapi.testclient import TestClient
    from mia.api import main as main_mod
    from mia.api.routes import remote_drive

    token_a = jwt.encode({"tenant_id": a, "email": "abogado@a.co"},
                         config.JWT_SECRET, algorithm=config.JWT_ALG)
    token_b = jwt.encode({"tenant_id": b, "email": "abogado@b.co"},
                         config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}
    visible: list[str] = []

    browse_tree = {"__root__": [_f("F1", "Casos", 0, "e1", is_folder=True),
                                _f("D1", "poliza.pdf", 1234, "e2")]}
    drive = FakeDrive(browse_tree, {})

    def use_service(connector) -> None:
        remote_drive._make_drive_service = lambda: FakeService(connector)

    with TestClient(main_mod.app) as client:
        # ── browse: mapea la forma común ──
        use_service(drive)
        r = client.get("/api/drive/browse", headers=auth_a)
        # Nota: NO se mete la respuesta de browse en `visible`: son datos estructurados
        # (nombres de campos técnicos del JSON como `etag`, permitidos por §G), no PROSA
        # para el abogado. El §G se valida sobre mensajes/errores, no sobre campos del JSON.
        items = r.json().get("items", []) if r.status_code == 200 else []
        shape_ok = all(set(x) >= {"id", "name", "is_folder", "size", "etag", "modified"} for x in items)
        check("browse: 200 con la forma común de cada ítem (carpeta + archivo)",
              r.status_code == 200 and len(items) == 2 and shape_ok)

        # sin conexión → 503
        use_service(None)
        r = client.get("/api/drive/browse", headers=auth_a)
        check("browse: sin cuenta conectada → 503 en llano", r.status_code == 503)
        visible.append(r.text)

        # ── registrar fuentes ──
        r = client.post("/api/drive/sources", headers=auth_a,
                        json={"remote_item_id": "K1", "label": "Conocimiento", "kind": "knowledge"})
        visible.append(r.text)
        src_k = r.json() if r.status_code == 200 else {}
        check("registrar: knowledge → 200 con id/kind", r.status_code == 200 and src_k.get("kind") == "knowledge")

        r = client.post("/api/drive/sources", headers=auth_a,
                        json={"remote_item_id": "M1", "label": "Expediente", "kind": "matters",
                              "matter_id": matter_a})
        check("registrar: matters con expediente propio → 200", r.status_code == 200)
        visible.append(r.text)

        # duplicado → 409
        r = client.post("/api/drive/sources", headers=auth_a,
                        json={"remote_item_id": "K1", "label": "Conocimiento", "kind": "knowledge"})
        check("registrar: la MISMA carpeta otra vez → 409", r.status_code == 409)
        visible.append(r.text)

        # matter ajeno → 404
        r = client.post("/api/drive/sources", headers=auth_a,
                        json={"remote_item_id": "X1", "kind": "matters", "matter_id": matter_b})
        check("registrar: expediente de otro despacho → 404", r.status_code == 404)
        visible.append(r.text)

        # listar: aparecen las dos recién registradas (el tenant A ya trae otras de sync_checks)
        r = client.get("/api/drive/sources", headers=auth_a)
        srcs = r.json().get("sources", [])
        remote_ids = {s.get("remote_item_id") for s in srcs}
        check("listar: el despacho ve las carpetas que registró (K1 y M1 presentes)",
              {"K1", "M1"} <= remote_ids)

        # ── RLS: B no ve las fuentes de A ──
        r = client.get("/api/drive/sources", headers=auth_b)
        check("RLS: otro despacho NO ve las carpetas de A (0)", len(r.json().get("sources", [])) == 0)

        # ── tope de fuentes → 422 ──
        with psycopg.connect(autocommit=True, **PG) as c:
            for i in range(gd.MAX_SOURCES_PER_TENANT):   # rellena hasta el tope
                c.execute("INSERT INTO remote_drive_sources (tenant_id, provider, remote_item_id, label, kind) "
                          "VALUES (%s::uuid, 'microsoft', %s, 'relleno', 'knowledge') "
                          "ON CONFLICT DO NOTHING", (a, f"FILL{i}"))
        r = client.post("/api/drive/sources", headers=auth_a,
                        json={"remote_item_id": "OVER", "kind": "knowledge"})
        check("registrar: superar el tope de carpetas → 422", r.status_code == 422)
        visible.append(r.text)

        # ── sync: throttle + lock ──
        # una fuente 'matters' de B, con conector doblado que tarda (para probar el lock)
        use_service(FakeDrive({"MB": []}, {}))
        rb = client.post("/api/drive/sources", headers=auth_b,
                         json={"remote_item_id": "MB", "kind": "matters", "matter_id": matter_b})
        sid_b = rb.json()["id"]
        r1 = client.post(f"/api/drive/sources/{sid_b}/sync", headers=auth_b)
        check("sync: primera vez → 'started'", r1.status_code == 200 and r1.json().get("status") == "started")
        visible.append(r1.text)

        # fuente inexistente → 404
        r = client.post("/api/drive/sources/00000000-0000-0000-0000-000000000000/sync", headers=auth_b)
        check("sync: carpeta inexistente → 404", r.status_code == 404)

        # throttle: forzar una revisión reciente (last_synced_at=now()) y re-sincronizar → 'up_to_date'
        with psycopg.connect(autocommit=True, **PG) as c:
            c.execute("UPDATE remote_drive_sources SET last_synced_at=now() WHERE id=%s::uuid", (sid_b,))
        r = client.post(f"/api/drive/sources/{sid_b}/sync", headers=auth_b)
        check("sync: recién sincronizada (<60s) → 'up_to_date' (throttle)",
              r.status_code == 200 and r.json().get("status") == "up_to_date")
        visible.append(r.text)

        # lock: dos disparos sin throttle (last_synced_at borrado) → el segundo 'in_progress'
        with psycopg.connect(autocommit=True, **PG) as c:
            c.execute("UPDATE remote_drive_sources SET last_synced_at=NULL WHERE id=%s::uuid", (sid_b,))
        remote_drive._SYNCS_IN_FLIGHT.add(sid_b)   # simula una corrida en vuelo
        try:
            r = client.post(f"/api/drive/sources/{sid_b}/sync", headers=auth_b)
            check("sync: ya hay una corrida en vuelo → 'in_progress' (lock anti-duplicado)",
                  r.status_code == 200 and r.json().get("status") == "in_progress")
            visible.append(r.text)
        finally:
            remote_drive._SYNCS_IN_FLIGHT.discard(sid_b)

        # ── DELETE ──
        r = client.delete(f"/api/drive/sources/{src_k['id']}", headers=auth_a)
        check("quitar: DELETE de una carpeta propia → 200 removed",
              r.status_code == 200 and r.json().get("status") == "removed")
        visible.append(r.text)
        r = client.delete(f"/api/drive/sources/{src_k['id']}", headers=auth_a)
        check("quitar: DELETE de nuevo → 404 (ya no existe)", r.status_code == 404)

    # §G — sin jerga técnica en lo que ve el abogado
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: textos sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def main() -> int:
    print("== OneDrive remoto selectivo (navegar + registrar + sincronizar) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env — necesario para la DB real")
        return 1
    if not config.JWT_SECRET:
        print("  [FAIL] JWT_SECRET vacío en .env — necesario para la superficie HTTP")
        return 1

    import init_remote_sources
    init_remote_sources.apply()   # tablas remote_drive_sources/remote_file_hashes + origin 'drive'

    asyncio.run(graph_client_checks())   # cliente Graph (offline, sin DB)

    a, b = make_tenants()
    matter_a = make_matter(a, "Asunto A (OneDrive)")
    matter_b = make_matter(b, "Asunto B (OneDrive)")
    try:
        asyncio.run(sync_checks(a, matter_a))
        api_checks(a, b, matter_a, matter_b)
    finally:
        drop_tenants(a, b)

    c, d = make_tenants()   # tenants dedicados al cron (bloque 3b): C con cuenta, D sin cuenta
    try:
        asyncio.run(cron_checks(c, d))
    finally:
        drop_tenants(c, d)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("OneDrive remoto selectivo OK — navegar + registrar + sincronizar verificados.")
        return 0
    print("OneDrive remoto selectivo FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
