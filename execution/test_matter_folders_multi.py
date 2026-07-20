"""
Mia · test_matter_folders_multi.py — gate del EXPEDIENTE con VARIAS carpetas vinculadas
(Bloque A · evolución de producto, corrección del bug de PODA CRUZADA).

Ejercita, contra la DB real (migraciones 016 + 025 + 028), que un mismo expediente admita
VARIAS carpetas vinculadas y que cada una se sincronice/pode de forma AISLADA por su propio
`source_id` — antes del fix, el sync de UNA carpeta podaba documentos traídos por OTRA
carpeta del mismo expediente (el filtro era solo por matter_id+origin='folder'). Cubre:

  Conector (llamadas directas, embeddings/extract mockeados — offline):
    · EL CASO DEL BUG: 2 carpetas vinculadas al mismo expediente, sync de ambas, borrar un
      archivo de A y re-sync SOLO A → los documentos de B quedan INTACTOS y solo se poda
      el archivo borrado de A
    · files_indexed por fuente (COUNT documents por matter_id+origin='folder'+source_id)
    · la misma ruta a DOS expedientes distintos sigue rechazándose (no cambia con Bloque A)
    · CARRERA DE SINCRONIZACIÓN (H1): 2 sync_source() simultáneos de LA MISMA fuente
      (asyncio.gather) no dejan documentos duplicados — exclusión mutua real por fuente
      (candado a nivel de módulo en local_folders._lock_for)
    · BACKFILL DE LA 028 (H3): expediente con historial AMBIGUO (fuente A desvinculada +
      fuente B vinculada) conserva sus documentos viejos con source_id NULL tras el
      backfill (no se colapsan bajo un solo source_id) y una sync de B no los borra;
      expediente con UNA sola fuente en su historial SÍ recibe el source_id sobre sus
      documentos NULL (caso feliz, procedencia inequívoca)

  Superficie HTTP plural (TestClient + JWT):
    · POST /matters/{id}/folders vincula varias carpetas al mismo expediente (sin 409)
    · GET /matters/{id}/folders lista todas con su estado individual
    · POST /matters/{id}/folders/{source_id}/sync sincroniza SOLO esa fuente (throttle 60s)
    · DELETE /matters/{id}/folders/{source_id} desvincula solo esa (documentos se conservan)
    · tope defensivo de carpetas por expediente → 422 en llano
    · una fuente de OTRO tenant/expediente → 404 en llano (sync y delete)

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_matter_folders_multi.py
"""
from __future__ import annotations
import asyncio
import os
import random
import shutil
import sys
import tempfile
import time
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
import init_projects_multifolder                       # noqa: E402  (migración 028)
import init_durable_jobs                               # noqa: E402  (migración 034)
from mia import config, embeddings                     # noqa: E402
from mia.db import pool                                # noqa: E402
from mia.connectors import local_folders as lf         # noqa: E402
from mia.connectors.local_folders import (             # noqa: E402
    LocalFolderSync,
    get_matter_sources,
    register_source,
)
from mia.api.routes import matter_folders as mf_routes  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red): embeddings vector(EMBED_DIM) aleatorio; extract_text para PDF/Word ──
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
        a = c.execute("INSERT INTO tenants(name) VALUES('A test multi-carpeta') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test multi-carpeta') RETURNING id").fetchone()[0]
    return str(a), str(b)


def make_matter(tenant_id: str, title: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO matters(tenant_id, title) VALUES(%s::uuid, %s) RETURNING id",
            (tenant_id, title)).fetchone()[0])


def drop_tenants(a: str, b: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([a, b],))


# ── helpers RAW (bypasean el conector) para simular el estado PRE-migración 028: una
# fila en local_folder_sources y un documento origin='folder' con source_id NULL, como
# quedaban los expedientes antes de que existiera la columna source_id ──────────────
def make_source_raw(tenant_id: str, matter_id: str, path: str, enabled: bool) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO local_folder_sources(tenant_id, path, label, kind, matter_id, enabled) "
            "VALUES (%s::uuid, %s, %s, 'matters', %s::uuid, %s) RETURNING id",
            (tenant_id, path, path, matter_id, enabled)).fetchone()[0])


def make_orphan_document(tenant_id: str, matter_id: str, source_path: str, filename: str) -> str:
    """Documento origin='folder' con source_id NULL — el estado en que quedaba un
    expediente antes de la migración 028 (sin fuente trazada por columna)."""
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO documents(tenant_id, matter_id, filename, mime, sha256, "
            "source_path, origin, source_id) VALUES "
            "(%s::uuid, %s::uuid, %s, 'application/pdf', %s, %s, 'folder', NULL) RETURNING id",
            (tenant_id, matter_id, filename, "hash-" + filename, source_path)).fetchone()[0])


def doc_source_id(doc_id: str) -> str | None:
    with psycopg.connect(autocommit=True, **PG) as c:
        row = c.execute("SELECT source_id FROM documents WHERE id=%s::uuid", (doc_id,)).fetchone()
        return str(row[0]) if row and row[0] else None


def doc_still_exists(doc_id: str) -> bool:
    with psycopg.connect(autocommit=True, **PG) as c:
        row = c.execute("SELECT 1 FROM documents WHERE id=%s::uuid", (doc_id,)).fetchone()
        return row is not None


# mapa matter_id → tenant_id para los helpers de conteo (RLS)
matter_id_tenant: dict[str, str] = {}


# ── checks del conector: EL CASO DEL BUG (2 carpetas, poda aislada por source_id) ────
async def connector_checks(a: str, b: str, matter_a: str, work: Path) -> None:
    await pool.open_pool()
    try:
        sync = LocalFolderSync()

        async def count_docs(matter_id: str, source_path: str | None = None,
                             source_id: str | None = None) -> int:
            q = "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='folder'"
            args: list = [matter_id]
            if source_path is not None:
                q += " AND source_path=%s"; args.append(source_path)
            if source_id is not None:
                q += " AND source_id=%s::uuid"; args.append(source_id)
            async with pool.tenant_connection(matter_id_tenant[matter_id]) as conn:
                return (await (await conn.execute(q, tuple(args))).fetchone())[0]

        orig_extract = lf.extract_text_detailed

        def fake_extract(filename: str, data: bytes):
            return (f"Texto extraído de {filename}: contenido de prueba del expediente.",
                    {"has_body": True, "ocr_unavailable": False})

        lf.extract_text_detailed = fake_extract

        # --- 2 carpetas DISTINTAS vinculadas al MISMO expediente (Bloque A) ---
        folder_x = work / "carpeta_x"
        folder_x.mkdir(parents=True, exist_ok=True)
        (folder_x / "uno.md").write_text("# Uno\n\nDocumento uno de la carpeta X.", encoding="utf-8")
        (folder_x / "dos.md").write_text("# Dos\n\nDocumento dos de la carpeta X.", encoding="utf-8")

        folder_y = work / "carpeta_y"
        folder_y.mkdir(parents=True, exist_ok=True)
        (folder_y / "tres.md").write_text("# Tres\n\nDocumento tres de la carpeta Y.", encoding="utf-8")

        src_x = await register_source(a, str(folder_x), kind="matters", matter_id=matter_a)
        src_y = await register_source(a, str(folder_y), kind="matters", matter_id=matter_a)
        check("register_source: 2 carpetas DISTINTAS al mismo expediente, ambas OK",
              src_x["id"] != src_y["id"])

        sources = await get_matter_sources(a, matter_a)
        check("get_matter_sources: devuelve las 2 carpetas activas del expediente",
              len(sources) == 2 and {s["id"] for s in sources} == {src_x["id"], src_y["id"]})

        # --- sync inicial de ambas ---
        sx1 = await sync.sync_source(a, src_x)
        sy1 = await sync.sync_source(a, src_y)
        check("sync inicial X: indexed=2 (uno.md + dos.md), errors=0",
              sx1["indexed"] == 2 and sx1["errors"] == 0)
        check("sync inicial Y: indexed=1 (tres.md), errors=0",
              sy1["indexed"] == 1 and sy1["errors"] == 0)
        check("files_indexed por fuente: X aporta 2, Y aporta 1 (COUNT por source_id)",
              await count_docs(matter_a, source_id=src_x["id"]) == 2
              and await count_docs(matter_a, source_id=src_y["id"]) == 1)
        check("total origin='folder' del expediente = 3 (X+Y)",
              await count_docs(matter_a) == 3)

        # --- EL CASO DEL BUG: borrar un archivo de X y re-sync SOLO X ---
        (folder_x / "dos.md").unlink()
        sx2 = await sync.sync_source(a, src_x)
        check("re-sync SOLO X tras borrar 'dos.md': deleted=1 (solo el borrado de X)",
              sx2["deleted"] == 1)
        check("poda AISLADA: 'dos.md' de X desaparece, 'uno.md' de X sobrevive",
              await count_docs(matter_a, "dos.md") == 0
              and await count_docs(matter_a, "uno.md") == 1)
        check("BUG CORREGIDO: los documentos de Y (carpeta HERMANA) quedan INTACTOS "
              "tras el sync de X — antes de la corrección esto los podaba",
              await count_docs(matter_a, "tres.md") == 1
              and await count_docs(matter_a, source_id=src_y["id"]) == 1)

        # re-sync de Y (sin cambios) confirma que Y sigue sano y con su propio conteo
        sy2 = await sync.sync_source(a, src_y)
        check("re-sync Y sin cambios: indexed=0, skipped=1, deleted=0 (no lo tocó el sync de X)",
              sy2["indexed"] == 0 and sy2["skipped"] == 1 and sy2["deleted"] == 0)

        # --- H1: CARRERA DE SINCRONIZACIÓN — 2 sync_source() simultáneos de LA MISMA
        # fuente (asyncio.gather, como cron sync_tenant y POST /api/folders/sync
        # disparándose a la vez sobre la misma carpeta) no deben duplicar el documento.
        # El candado real vive en el motor (local_folders._lock_for, por source_id), así
        # que sirve sin importar por qué vía entró cada sync. ---
        folder_race = work / "carpeta_carrera"
        folder_race.mkdir(parents=True, exist_ok=True)
        (folder_race / "concurrente.md").write_text(
            "# Concurrente\n\nDocumento usado para probar la carrera de sincronización.",
            encoding="utf-8")
        src_race = await register_source(a, str(folder_race), kind="matters", matter_id=matter_a)
        results_race = await asyncio.gather(
            sync.sync_source(a, src_race), sync.sync_source(a, src_race))
        check("carrera: los 2 sync_source() concurrentes de LA MISMA fuente terminan sin errores",
              all(r["errors"] == 0 for r in results_race))
        check("H1 CORREGIDO: 2 syncs simultáneos de la MISMA fuente no duplican el documento "
              "(candado por source_id serializa cron/HTTP/expediente sin importar la vía)",
              await count_docs(matter_a, "concurrente.md", src_race["id"]) == 1)

        # --- H3: BACKFILL DE LA 028 — un expediente con historial AMBIGUO (vinculó A,
        # la desvinculó, vinculó B) NO debe colapsar sus documentos viejos bajo el
        # source_id de B; un expediente con UNA sola fuente en su historial sí debe
        # recibir el source_id sobre sus documentos viejos (procedencia inequívoca). ---
        matter_multi = make_matter(a, "Asunto backfill (multi-fuente ambigua)")
        matter_id_tenant[matter_multi] = a
        matter_single = make_matter(a, "Asunto backfill (fuente única)")
        matter_id_tenant[matter_single] = a

        folder_b = work / "carpeta_backfill_b"
        folder_b.mkdir(parents=True, exist_ok=True)
        (folder_b / "demanda.pdf").write_text("contenido de prueba del backfill", encoding="utf-8")

        # Simula el estado PRE-028 de un expediente con historial ambiguo: fuente A
        # desvinculada (su documento quedó origin='folder' con source_id NULL, tal como
        # lo conserva disable_source) + fuente B activa.
        make_source_raw(a, matter_multi, str(work / "carpeta_backfill_a_ya_no_existe"), enabled=False)
        src_b_id = make_source_raw(a, matter_multi, str(folder_b), enabled=True)
        doc_viejo_id = make_orphan_document(a, matter_multi, "escrito_viejo.pdf", "escrito_viejo.pdf")

        # Expediente con UNA sola fuente en TODO su historial: procedencia inequívoca.
        src_c_id = make_source_raw(a, matter_single, str(work / "carpeta_backfill_c_ya_no_existe"),
                                   enabled=True)
        doc_unico_id = make_orphan_document(a, matter_single, "doc_unico.pdf", "doc_unico.pdf")

        # Re-aplica el backfill de la 028 (idempotente, mismo SQL que corrió en producción).
        init_projects_multifolder.apply()
        init_durable_jobs.apply()

        check("backfill H3: expediente con historial AMBIGUO (A desvinculada + B activa) "
              "conserva su documento viejo con source_id NULL — no se colapsa bajo B",
              doc_source_id(doc_viejo_id) is None)
        check("backfill H3 caso feliz: expediente con UNA sola fuente en su historial SÍ "
              "recibe el source_id sobre su documento viejo (procedencia inequívoca)",
              doc_source_id(doc_unico_id) == src_c_id)

        # Sync real de B (la fuente ACTIVA del expediente ambiguo): la poda de B está
        # acotada por source_id=B, así que NO debe tocar el documento NULL de A.
        src_b = {"id": src_b_id, "path": str(folder_b), "kind": "matters", "matter_id": matter_multi}
        sb = await sync.sync_source(a, src_b)
        check("sync de B (fuente activa del expediente ambiguo) corre sin errores",
              sb["errors"] == 0)
        check("H3 CORREGIDO: la poda del sync de B NO borra el documento NULL de A — "
              "sigue existiendo en el expediente (pérdida de datos silenciosa evitada)",
              doc_still_exists(doc_viejo_id))

        lf.extract_text_detailed = orig_extract

        # --- la MISMA ruta a OTRO expediente sigue rechazándose (no cambia con Bloque A) ---
        matter_a2 = make_matter(a, "Asunto A2 (multi-carpeta, rechazo)")
        matter_id_tenant[matter_a2] = a
        robo = False
        try:
            await register_source(a, str(folder_x), kind="matters", matter_id=matter_a2)
        except ValueError:
            robo = True
        check("la misma ruta a OTRO expediente (mientras está activa en A) sigue "
              "rechazándose", robo)
    finally:
        await pool.close_pool()


# ── checks de la superficie HTTP plural (TestClient + JWT) ───────────────────
def api_checks(tid_a: str, tid_b: str, matter_target: str, matter_same_tenant: str,
               work: Path) -> None:
    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    token_a = jwt.encode({"tenant_id": tid_a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    token_b = jwt.encode({"tenant_id": tid_b}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}
    visible: list[str] = []

    with TestClient(app) as client:
        folder1 = work / "http_carpeta_1"
        folder1.mkdir(parents=True, exist_ok=True)
        (folder1 / "nota.md").write_text("# Nota\n\nContenido de la carpeta 1.", encoding="utf-8")

        folder2 = work / "http_carpeta_2"
        folder2.mkdir(parents=True, exist_ok=True)
        (folder2 / "apunte.txt").write_text("Apunte de la carpeta 2.", encoding="utf-8")

        # --- vincular 2 carpetas al MISMO expediente por la superficie plural ---
        r1 = client.post(f"/api/matters/{matter_target}/folders", headers=auth_a,
                         json={"path": str(folder1), "label": "Carpeta uno"})
        check("POST /folders (plural) -> 200 vincula la 1a carpeta",
              r1.status_code == 200 and r1.json().get("status") == "linked")
        visible.append(r1.text)
        source1_id = r1.json()["id"]

        r2 = client.post(f"/api/matters/{matter_target}/folders", headers=auth_a,
                         json={"path": str(folder2), "label": "Carpeta dos"})
        check("POST /folders (plural) -> 200 vincula la 2a carpeta (SIN 409)",
              r2.status_code == 200 and r2.json().get("status") == "linked")
        visible.append(r2.text)
        source2_id = r2.json()["id"]
        check("las 2 carpetas tienen ids distintos", source1_id != source2_id)

        # --- GET /folders lista ambas y su ingesta converge ---
        # La ingesta NO es síncrona: POST /folders solo ENCOLA un trabajo durable y el
        # trabajador (jobs/durable.DurableWorker) lo reclama con POLL_SECONDS = 1.0s. Este
        # bucle DEBE ceder tiempo real al trabajador entre sondeos; si gira sin dormir,
        # agota sus intentos en ~0.2s (medido: 100 GET seguidos tardan 243 ms) y falla
        # SIEMPRE, sin que el código de producción tenga nada malo. Por eso el corte es
        # por RELOJ, no por número de vueltas.
        # Presupuesto MEDIDO (4 corridas seguidas en esta máquina, 2 carpetas de 1 archivo
        # cada una): convergió en 9.8 s, 11.2 s, 8.2 s y 11.3 s. El tope de 60 s deja ~5x
        # sobre el peor caso observado. El reloj SOLO se agota cuando algo está realmente
        # roto, así que un tope holgado no vuelve lento el gate en verde.
        deadline = time.monotonic() + 60.0
        t0 = time.monotonic()
        files1 = files2 = 0
        elapsed = 0.0
        while True:
            rl = client.get(f"/api/matters/{matter_target}/folders", headers=auth_a)
            byid = {f["id"]: f for f in rl.json().get("folders", [])}
            files1 = byid.get(source1_id, {}).get("files_indexed", 0)
            files2 = byid.get(source2_id, {}).get("files_indexed", 0)
            elapsed = time.monotonic() - t0
            if files1 >= 1 and files2 >= 1:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        check(f"GET /folders -> lista las 2 carpetas con su conteo por fuente "
              f"(convergió en {elapsed:.1f}s)",
              rl.status_code == 200 and files1 >= 1 and files2 >= 1)
        visible.append(rl.text)

        # --- sync throttle por fuente (una recién sincronizada -> up_to_date) ---
        rs = client.post(f"/api/matters/{matter_target}/folders/{source1_id}/sync", headers=auth_a)
        check("POST /folders/{id}/sync -> throttle 'up_to_date' (sync reciente <60s)",
              rs.status_code == 200 and rs.json().get("status") == "up_to_date")
        visible.append(rs.text)

        # --- tope defensivo de carpetas por expediente -> 422 ---
        orig_max = mf_routes.MAX_FOLDERS_PER_MATTER
        mf_routes.MAX_FOLDERS_PER_MATTER = 2
        try:
            folder3 = work / "http_carpeta_3"
            folder3.mkdir(parents=True, exist_ok=True)
            r3 = client.post(f"/api/matters/{matter_target}/folders", headers=auth_a,
                             json={"path": str(folder3)})
            check("POST /folders -> 422 al superar el tope de carpetas por expediente",
                  r3.status_code == 422)
            visible.append(r3.text)
        finally:
            mf_routes.MAX_FOLDERS_PER_MATTER = orig_max

        # --- fuente de OTRO tenant -> 401/404 en llano (el expediente ni existe para ese tenant) ---
        r_foreign_sync = client.post(f"/api/matters/{matter_target}/folders/{source1_id}/sync",
                                     headers=auth_b)
        check("POST /folders/{id}/sync con tenant AJENO -> 401/404 (asunto no visible por RLS)",
              r_foreign_sync.status_code in (401, 404))
        visible.append(r_foreign_sync.text)

        # --- fuente de OTRO expediente del MISMO tenant -> 404 en llano ---
        r_wrong_matter = client.post(f"/api/matters/{matter_same_tenant}/folders/{source1_id}/sync",
                                     headers=auth_a)
        check("POST /folders/{id}/sync con fuente de OTRO expediente (mismo despacho) "
              "-> 404 en llano", r_wrong_matter.status_code == 404)
        visible.append(r_wrong_matter.text)

        r_wrong_del = client.delete(f"/api/matters/{matter_same_tenant}/folders/{source1_id}",
                                    headers=auth_a)
        check("DELETE /folders/{id} con fuente de OTRO expediente (mismo despacho) "
              "-> 404 en llano", r_wrong_del.status_code == 404)
        visible.append(r_wrong_del.text)

        # --- desvincular UNA carpeta conserva la otra y sus documentos ---
        docs_before = client.get(f"/api/matters/{matter_target}/folders", headers=auth_a).json()["folders"]
        rd = client.delete(f"/api/matters/{matter_target}/folders/{source2_id}", headers=auth_a)
        check("DELETE /folders/{id} -> 200 desvincula SOLO esa carpeta",
              rd.status_code == 200 and rd.json().get("status") == "unlinked")
        visible.append(rd.text)

        rl2 = client.get(f"/api/matters/{matter_target}/folders", headers=auth_a)
        remaining = rl2.json().get("folders", [])
        check("tras desvincular la 2a: queda SOLO 1 carpeta activa y es la primera",
              len(remaining) == 1 and remaining[0]["id"] == source1_id)
        check("la carpeta que quedó conserva su conteo de documentos (no se tocó)",
              remaining[0]["files_indexed"] == next(
                  f["files_indexed"] for f in docs_before if f["id"] == source1_id))

    # §G — sin jerga técnica en lo que ve el abogado
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def main() -> int:
    print("== Expediente con VARIAS carpetas vinculadas (Bloque A · poda aislada por fuente) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env — necesario para la migración")
        return 1
    if not config.JWT_SECRET:
        print("  [FAIL] JWT_SECRET vacío en .env — necesario para la superficie HTTP")
        return 1

    init_local_folders.apply()          # idempotente: tablas de la allowlist (016)
    init_matter_folders.apply()         # idempotente: columnas del expediente vinculado (025)
    init_projects_multifolder.apply()   # idempotente: source_id/body/kind (028)

    (ROOT / ".tmp").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="matterfoldersmulti_", dir=str(ROOT / ".tmp")))

    a, b = make_tenants()
    matter_a = make_matter(a, "Asunto A (multi-carpeta)")
    matter_id_tenant[matter_a] = a
    try:
        asyncio.run(connector_checks(a, b, matter_a, work / "connector"))

        matter_http = make_matter(a, "Asunto A (HTTP, multi-carpeta)")
        matter_id_tenant[matter_http] = a
        # matter_a (mismo tenant, expediente DISTINTO al target) prueba el 404 "fuente de
        # otro expediente"; el tenant b (auth_b) prueba el 401/404 de RLS.
        api_checks(a, b, matter_http, matter_a, work / "http")
    finally:
        drop_tenants(a, b)
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Expediente multi-carpeta OK — poda aislada por fuente verificada.")
        return 0
    print("Expediente multi-carpeta FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
