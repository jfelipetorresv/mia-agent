"""
Mia · test_matter_folder.py — gate del EXPEDIENTE VINCULADO (Pilar C · carpeta del asunto).

Ejercita, contra la DB real (migraciones 016 + 025), la carpeta que se vincula a UN
expediente: sus documentos (PDF/Word/txt/md) se traen solos a documents + chunks del asunto
(origin='folder'), con detección incremental por sha256 sobre local_file_hashes. Cubre:

  Conector (llamadas directas, embeddings/extract mockeados — offline):
    · registro rechaza un asunto AJENO (RLS/ownership) y exige matter_id
    · sync inicial: ingiere md + pdf de una carpeta temporal (origin='folder', sha256, ruta)
    · re-sync sin cambios = 0 trabajo (skipped, indexed=0)
    · archivo editado → re-ingesta (el documento viejo de esa ruta se REEMPLAZA, no se duplica)
    · archivo borrado → poda SOLO origin='folder' (un origin='upload' del mismo asunto sobrevive)
    · archivo bloqueado (PermissionError/WinError 32, Word abierto) → queda pendiente, no rompe,
      su documento previo se conserva; el próximo ciclo lo retoma
    · desvincular (disable_source kind='matters') CONSERVA los documentos ya ingeridos

  Superficie HTTP (TestClient + JWT):
    · una carpeta por expediente (segundo POST → 409)
    · estado del expediente (linked, files_indexed) refleja la ingesta
    · re-sync con throttle (<60s → "ya está al día")
    · subida manual duplicada (mismo sha256) → status 'duplicado' sin crear otra fila
    · desvincular por HTTP conserva los documentos

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_matter_folder.py
"""
from __future__ import annotations
import asyncio
import os
import random
import shutil
import sys
import tempfile
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import init_local_folders                              # noqa: E402  (migración 016)
import init_matter_folders                             # noqa: E402  (migración 025)
from mia import config, embeddings                     # noqa: E402
from mia.db import pool                                # noqa: E402
from mia.connectors import local_folders as lf         # noqa: E402
from mia.connectors.local_folders import (             # noqa: E402
    LocalFolderSync,
    disable_source,
    get_matter_source,
    register_source,
    source_last_sync,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red): embeddings vector(1024) aleatorio; extract_text para PDF/Word ──
def _fake_embed(texts):
    return [[random.random() for _ in range(config.EMBED_DIM)] for _ in texts]


embeddings.embed_texts = _fake_embed

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "chunk", "embedding", "sync engine")

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def make_tenants() -> tuple[str, str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A test expediente') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test expediente') RETURNING id").fetchone()[0]
    return str(a), str(b)


def make_matter(tenant_id: str, title: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO matters(tenant_id, title) VALUES(%s::uuid, %s) RETURNING id",
            (tenant_id, title)).fetchone()[0])


def drop_tenants(a: str, b: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([a, b],))


# ── checks del conector (DB real, mocks offline) ─────────────────────────────
async def connector_checks(a: str, b: str, matter_a: str, matter_b: str, work: Path) -> None:
    await pool.open_pool()
    try:
        sync = LocalFolderSync()

        async def count_docs(matter_id: str, origin: str | None = None,
                             source_path: str | None = None) -> int:
            q = "SELECT count(*) FROM documents WHERE matter_id=%s::uuid"
            args: list = [matter_id]
            if origin is not None:
                q += " AND origin=%s"; args.append(origin)
            if source_path is not None:
                q += " AND source_path=%s"; args.append(source_path)
            async with pool.tenant_connection(matter_id_tenant[matter_id]) as conn:
                return (await (await conn.execute(q, tuple(args))).fetchone())[0]

        async def doc_sha(matter_id: str, source_path: str) -> str | None:
            async with pool.tenant_connection(matter_id_tenant[matter_id]) as conn:
                row = await (await conn.execute(
                    "SELECT sha256 FROM documents WHERE matter_id=%s::uuid AND origin='folder' "
                    "AND source_path=%s", (matter_id, source_path))).fetchone()
            return row[0] if row else None

        async def count_chunks(matter_id: str, source_path: str) -> int:
            async with pool.tenant_connection(matter_id_tenant[matter_id]) as conn:
                return (await (await conn.execute(
                    "SELECT count(*) FROM chunks c JOIN documents d ON d.id=c.document_id "
                    "WHERE d.matter_id=%s::uuid AND d.source_path=%s", (matter_id, source_path)
                )).fetchone())[0]

        # --- carpeta temporal con md + pdf ---
        folder = work / "expediente_a"
        folder.mkdir(parents=True, exist_ok=True)
        (folder / "demanda.md").write_text(
            "# Demanda\n\nHechos y pretensiones del expediente para probar la ingesta.",
            encoding="utf-8")
        (folder / "poliza.pdf").write_bytes(b"%PDF-fake bytes de la poliza")

        # extract_text mockeado (solo PDF/Word pasan por ahí; md/txt se leen directo)
        orig_extract = lf.extract_text

        def fake_extract(filename: str, data: bytes) -> str:
            return f"Texto extraído de {filename}: clausulas y coberturas del expediente."

        lf.extract_text = fake_extract

        # --- 1) registro rechaza asunto AJENO (RLS/ownership) y exige matter_id ---
        rechazo_ajeno = False
        try:
            await register_source(b, str(folder), kind="matters", matter_id=matter_a)
        except ValueError:
            rechazo_ajeno = True
        check("registro: vincular un expediente AJENO se rechaza (RLS/ownership)", rechazo_ajeno)

        falta_matter = False
        try:
            await register_source(a, str(folder), kind="matters")
        except ValueError:
            falta_matter = True
        check("registro: kind='matters' sin expediente se rechaza", falta_matter)

        # --- registrar la carpeta del expediente de A ---
        src = await register_source(a, str(folder), kind="matters", matter_id=matter_a)
        check("registro: fuente creada con kind='matters' y matter_id del asunto",
              src["kind"] == "matters" and src["matter_id"] == matter_a)

        active = await get_matter_source(a, matter_a)
        check("get_matter_source: devuelve la carpeta activa del expediente",
              active is not None and active["id"] == src["id"])

        # --- 2) sync inicial: ingiere md + pdf ---
        s1 = await sync.sync_source(a, src)
        check("sync inicial: indexed=2 (md + pdf), errors=0, pending=0",
              s1["indexed"] == 2 and s1["errors"] == 0 and s1["pending"] == 0)
        check("sync inicial: 2 documentos origin='folder' con su ruta relativa",
              await count_docs(matter_a, origin="folder") == 2
              and await count_docs(matter_a, "folder", "demanda.md") == 1
              and await count_docs(matter_a, "folder", "poliza.pdf") == 1)
        check("sync inicial: el documento guarda su huella sha256",
              (await doc_sha(matter_a, "demanda.md")) is not None)
        check("sync inicial: el documento tiene chunks asociados",
              await count_chunks(matter_a, "demanda.md") >= 1)

        # --- 3) re-sync sin cambios = 0 trabajo ---
        s2 = await sync.sync_source(a, src)
        check("re-sync sin cambios: indexed=0, skipped=2, deleted=0",
              s2["indexed"] == 0 and s2["skipped"] == 2 and s2["deleted"] == 0)

        # --- 4) archivo editado → re-ingesta que REEMPLAZA el documento viejo ---
        sha_antes = await doc_sha(matter_a, "demanda.md")
        (folder / "demanda.md").write_text(
            "# Demanda (corregida)\n\nHechos AMPLIADOS y nuevas pretensiones del expediente.",
            encoding="utf-8")
        s3 = await sync.sync_source(a, src)
        sha_despues = await doc_sha(matter_a, "demanda.md")
        check("archivo editado: indexed=1, skipped=1",
              s3["indexed"] == 1 and s3["skipped"] == 1)
        check("archivo editado: el documento se REEMPLAZA (sigue 1 por ruta, huella cambió)",
              await count_docs(matter_a, "folder", "demanda.md") == 1
              and sha_despues is not None and sha_despues != sha_antes)

        # --- 5) archivo borrado → poda SOLO origin='folder'; un 'upload' sobrevive ---
        # Sembrar un documento subido a mano (origin='upload') en el MISMO expediente.
        async with pool.tenant_connection(a) as conn:
            await conn.execute(
                "INSERT INTO documents (tenant_id, matter_id, filename, mime, sha256, origin) "
                "VALUES (%s::uuid, %s::uuid, 'manual.pdf', 'application/pdf', 'sha-manual', 'upload')",
                (a, matter_a))
        (folder / "poliza.pdf").unlink()
        s4 = await sync.sync_source(a, src)
        check("archivo borrado: deleted=1 y el documento de la carpeta se poda",
              s4["deleted"] == 1 and await count_docs(matter_a, "folder", "poliza.pdf") == 0)
        check("poda: el documento subido a mano (origin='upload') NO se toca",
              await count_docs(matter_a, origin="upload") == 1)

        lf.extract_text = orig_extract

        # --- 6) archivo bloqueado (Word abierto) → pendiente, no rompe, conserva lo previo ---
        (folder / "bloqueado.txt").write_text("Documento en uso por Word.", encoding="utf-8")
        orig_hash = lf.LocalFolderSync._hash_file

        def locked_hash(path):
            if Path(path).name == "bloqueado.txt":
                raise PermissionError(32, "El archivo está siendo usado por otro proceso")
            return orig_hash(path)

        lf.LocalFolderSync._hash_file = staticmethod(locked_hash)
        try:
            s5 = await sync.sync_source(a, src)
        finally:
            lf.LocalFolderSync._hash_file = staticmethod(orig_hash)
        check("archivo bloqueado: queda pendiente (pending>=1), sin errores y sin indexar",
              s5["pending"] >= 1 and s5["errors"] == 0
              and await count_docs(matter_a, "folder", "bloqueado.txt") == 0)
        check("archivo bloqueado: el documento editado que sigue existiendo se conserva",
              await count_docs(matter_a, "folder", "demanda.md") == 1)

        # próximo ciclo (ya no bloqueado): lo retoma sin perder nada
        s6 = await sync.sync_source(a, src)
        check("próximo ciclo: el archivo antes bloqueado se ingiere (pending=0, indexed=1)",
              s6["pending"] == 0 and s6["indexed"] == 1
              and await count_docs(matter_a, "folder", "bloqueado.txt") == 1)

        # --- 7) desvincular CONSERVA los documentos ya ingeridos ---
        docs_antes = await count_docs(matter_a, origin="folder")
        ok = await disable_source(a, src["id"])
        check("desvincular: disable_source(kind='matters') devuelve True",
              ok is True and await get_matter_source(a, matter_a) is None)
        check("desvincular: los documentos ya traídos SE CONSERVAN",
              await count_docs(matter_a, origin="folder") == docs_antes and docs_antes >= 2)

        # last_sync existe tras las corridas (para el throttle del endpoint)
        check("source_last_sync: hay marca de última sincronización",
              (await source_last_sync(a, src["id"])) is not None)

        # --- 8) misma ruta a OTRO expediente (hallazgos de capa 2, 2026-07-08) ---
        # Desvinculada de A → reasignarla a A2 limpia la memoria de archivos vistos y
        # la ingesta arranca DESDE CERO (sin esto, A2 quedaba "vinculado" con 0 docs).
        matter_a2 = make_matter(a, "Asunto A2 (misma carpeta)")
        matter_id_tenant[matter_a2] = a
        src2 = await register_source(a, str(folder), kind="matters", matter_id=matter_a2)
        s8 = await sync.sync_source(a, src2)
        check("reasignar carpeta DESVINCULADA a otro expediente: ingiere desde cero",
              s8["indexed"] >= 2 and await count_docs(matter_a2, origin="folder") >= 2)
        # Activa en A2 → vincular la misma ruta a otro expediente se RECHAZA (nada de
        # "robar" la fuente en silencio).
        robo = False
        try:
            await register_source(a, str(folder), kind="matters", matter_id=matter_a)
        except ValueError:
            robo = True
        check("carpeta ACTIVA en otro expediente: vincularla de nuevo se rechaza", robo)
        check("la fuente del expediente activo queda intacta tras el intento",
              (await get_matter_source(a, matter_a2)) is not None)
    finally:
        await pool.close_pool()


# mapa matter_id → tenant_id para los helpers de conteo (RLS)
matter_id_tenant: dict[str, str] = {}


# ── checks de la superficie HTTP (TestClient + JWT) ──────────────────────────
def api_checks(tid: str, matter_id: str, folder: Path) -> None:
    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    token = jwt.encode({"tenant_id": tid}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth = {"Authorization": f"Bearer {token}"}
    visible: list[str] = []

    with TestClient(app) as client:
        # vincular la carpeta
        r = client.post(f"/api/matters/{matter_id}/folder", headers=auth, json={"path": str(folder)})
        check("POST /folder -> 200 vinculada", r.status_code == 200 and r.json().get("status") == "linked")
        visible.append(r.text)

        # una carpeta por expediente: segundo POST -> 409
        r = client.post(f"/api/matters/{matter_id}/folder", headers=auth, json={"path": str(folder)})
        check("POST /folder de nuevo -> 409 (una carpeta por expediente)", r.status_code == 409)
        visible.append(r.text)

        # el estado refleja la ingesta (la sync corre en segundo plano; se drena con GETs)
        files_indexed = 0
        for _ in range(100):
            r = client.get(f"/api/matters/{matter_id}/folder", headers=auth)
            files_indexed = r.json().get("files_indexed", 0)
            if files_indexed >= 2:
                break
        check("GET /folder -> linked con files_indexed de la carpeta (md+txt)",
              r.status_code == 200 and r.json().get("linked") is True and files_indexed >= 2)
        visible.append(r.text)

        # re-sync con throttle: acabó de sincronizarse -> "ya está al día"
        r = client.post(f"/api/matters/{matter_id}/folder/sync", headers=auth)
        check("POST /folder/sync -> throttle 'up_to_date' (sync reciente <60s)",
              r.status_code == 200 and r.json().get("status") == "up_to_date")
        visible.append(r.text)

        # subida manual duplicada -> status 'duplicado' sin crear otra fila
        contenido = b"Documento manual del expediente para probar el dedupe por huella."
        r1 = client.post(f"/api/matters/{matter_id}/documents", headers=auth,
                         files={"file": ("manual.txt", contenido, "text/plain")})
        r2 = client.post(f"/api/matters/{matter_id}/documents", headers=auth,
                         files={"file": ("manual.txt", contenido, "text/plain")})
        check("POST documento manual -> 201 la primera vez", r1.status_code == 201)
        check("POST el MISMO documento -> status 'duplicado' (sin re-embeber)",
              r2.status_code == 200 and r2.json().get("status") == "duplicado")
        visible.append(r2.text)
        with psycopg.connect(autocommit=True, **PG) as c:
            n_manual = c.execute(
                "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND filename='manual.txt'",
                (matter_id,)).fetchone()[0]
        check("dedupe: solo hay UNA fila para el documento manual repetido", n_manual == 1)

        # desvincular por HTTP conserva los documentos
        with psycopg.connect(autocommit=True, **PG) as c:
            docs_folder = c.execute(
                "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='folder'",
                (matter_id,)).fetchone()[0]
        r = client.delete(f"/api/matters/{matter_id}/folder", headers=auth)
        check("DELETE /folder -> 200 desvinculada", r.status_code == 200 and r.json().get("status") == "unlinked")
        visible.append(r.text)
        with psycopg.connect(autocommit=True, **PG) as c:
            docs_despues = c.execute(
                "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='folder'",
                (matter_id,)).fetchone()[0]
        check("DELETE /folder: los documentos ya traídos SE CONSERVAN",
              docs_despues == docs_folder and docs_folder >= 2)

    # §G — sin jerga técnica en lo que ve el abogado
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def main() -> int:
    print("== Expediente vinculado (carpeta del asunto → documents + chunks) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env — necesario para la migración")
        return 1
    if not config.JWT_SECRET:
        print("  [FAIL] JWT_SECRET vacío en .env — necesario para la superficie HTTP")
        return 1

    init_local_folders.apply()    # idempotente: tablas de la allowlist (016)
    init_matter_folders.apply()   # idempotente: columnas del expediente vinculado (025)

    (ROOT / ".tmp").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="matterfolder_", dir=str(ROOT / ".tmp")))

    a, b = make_tenants()
    matter_a = make_matter(a, "Asunto A (expediente)")
    matter_b = make_matter(b, "Asunto B (expediente)")
    matter_id_tenant[matter_a] = a
    matter_id_tenant[matter_b] = b
    try:
        asyncio.run(connector_checks(a, b, matter_a, matter_b, work))

        # carpeta fresca para la superficie HTTP (md + txt; sin PDF para no depender de libs)
        api_folder = work / "expediente_http"
        api_folder.mkdir(parents=True, exist_ok=True)
        (api_folder / "contestacion.md").write_text(
            "# Contestación\n\nExcepciones y defensa del expediente.", encoding="utf-8")
        (api_folder / "notas.txt").write_text(
            "Notas del abogado sobre el expediente y su estrategia.", encoding="utf-8")
        matter_http = make_matter(a, "Asunto A (HTTP)")
        matter_id_tenant[matter_http] = a
        api_checks(a, matter_http, api_folder)
    finally:
        drop_tenants(a, b)
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Expediente vinculado OK — carpeta del asunto verificada.")
        return 0
    print("Expediente vinculado FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
