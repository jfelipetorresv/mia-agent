"""
Mia · test_carpeta_proyecto.py — gate de la CARPETA VINCULADA A UN PROYECTO.

POR QUÉ EXISTE ESTE GATE
------------------------
Los otros dos gates de carpetas (test_matter_folder.py y test_matter_folders_multi.py)
ejercitan SOLO expedientes de tipo 'asunto'. El escenario que falló de verdad en producción,
con el dueño delante, fue el de una carpeta vinculada a un PROYECTO — y no había ni un
solo check que lo cubriera. Este archivo cierra ese hueco.

Un PROYECTO no es una tabla aparte: es una fila de `matters` con kind='proyecto'
(migración 028). Reusa el MISMO mecanismo multi-carpeta que el asunto — la superficie
plural /api/matters/{id}/folders y el conector local_folders con kind='matters' — porque
`assert_owns_matter` y `register_source` no discriminan por kind. Ese "reuso silencioso"
es justamente lo que hacía fácil creer que estaba cubierto sin estarlo: ningún check
recorría el camino con un matter kind='proyecto' de punta a punta.

Cubre, contra la DB real (migraciones 016 + 025 + 028 + 034):

  Conector (llamadas directas, embeddings/extract mockeados — offline):
    · vincular una carpeta a un PROYECTO (kind='matters' + matter_id del proyecto)
    · un proyecto admite VARIAS carpetas a la vez (el mecanismo multi-carpeta)
    · indexar: conteo por fuente (source_id) y total del proyecto
    · re-indexar sin cambios = 0 trabajo
    · poda AISLADA entre las carpetas del PROPIO proyecto (borrar en una no toca la otra)
    · DESVINCULAR conserva los documentos ya traídos (el fallo real que llegó al dueño)
    · desvincular una carpeta no toca los documentos de la carpeta hermana
    · re-vincular la misma carpeta al mismo proyecto no re-ingiere lo que no cambió

  Superficie HTTP (TestClient + JWT) — el camino que recorre el abogado:
    · POST /api/matters con kind='proyecto' crea el proyecto
    · POST /api/matters/{proyecto}/folders vincula (varias, sin 409)
    · GET  /api/matters/{proyecto}/folders lista con su conteo por fuente
    · POST /api/matters/{proyecto}/folders/{id}/sync aplica el throttle de 60s
    · GET  /api/matters/{proyecto}/sources — el panel de Fuentes que el abogado ve de
      verdad (FuentesPanel.tsx lo usa igual en asuntos y en proyectos) muestra la carpeta
      del proyecto con su conteo y su estado en llano
    · DELETE /api/matters/{proyecto}/folders/{id} desvincula y CONSERVA los documentos
    · un proyecto de OTRO despacho no es alcanzable (RLS)

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_carpeta_proyecto.py
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
    disable_source,
    get_matter_sources,
    register_source,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red): embeddings vector(EMBED_DIM) aleatorio ──────────────────
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
        a = c.execute("INSERT INTO tenants(name) VALUES('A test carpeta proyecto') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test carpeta proyecto') RETURNING id").fetchone()[0]
    return str(a), str(b)


def make_project(tenant_id: str, title: str) -> str:
    """Un PROYECTO es una fila de matters con kind='proyecto' (migración 028)."""
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO matters(tenant_id, title, kind) VALUES(%s::uuid, %s, 'proyecto') "
            "RETURNING id", (tenant_id, title)).fetchone()[0])


def matter_kind_raw(matter_id: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute("SELECT kind FROM matters WHERE id=%s::uuid", (matter_id,)).fetchone()[0]


def count_folder_docs_raw(matter_id: str, source_id: str | None = None) -> int:
    """Conteo directo (superusuario, sin RLS) de los documentos de carpeta del proyecto.
    Se usa para comprobar CONSERVACIÓN tras desvincular: la fuente ya no aparece por la
    superficie normal, así que hay que contar por fuera de ella."""
    q = "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='folder'"
    args: list = [matter_id]
    if source_id is not None:
        q += " AND source_id=%s::uuid"
        args.append(source_id)
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(q, tuple(args)).fetchone()[0]


def drop_tenants(a: str, b: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([a, b],))


# ── checks del conector sobre un PROYECTO ────────────────────────────────────
async def connector_checks(a: str, proyecto: str, work: Path) -> None:
    await pool.open_pool()
    try:
        sync = LocalFolderSync()
        orig_extract = lf.extract_text_detailed

        def fake_extract(filename: str, data: bytes):
            return (f"Texto extraído de {filename}: contenido de prueba del proyecto.",
                    {"has_body": True, "ocr_unavailable": False})

        lf.extract_text_detailed = fake_extract
        try:
            check("el espacio de trabajo es un PROYECTO (kind='proyecto'), no un asunto",
                  matter_kind_raw(proyecto) == "proyecto")

            # --- vincular DOS carpetas al MISMO proyecto (mecanismo multi-carpeta) ---
            carpeta_1 = work / "carpeta_contratos"
            carpeta_1.mkdir(parents=True, exist_ok=True)
            (carpeta_1 / "acuerdo.md").write_text(
                "# Acuerdo\n\nPrimer documento del proyecto.", encoding="utf-8")
            (carpeta_1 / "anexo.md").write_text(
                "# Anexo\n\nSegundo documento del proyecto.", encoding="utf-8")

            carpeta_2 = work / "carpeta_actas"
            carpeta_2.mkdir(parents=True, exist_ok=True)
            (carpeta_2 / "acta.md").write_text(
                "# Acta\n\nDocumento de la segunda carpeta del proyecto.", encoding="utf-8")

            src1 = await register_source(a, str(carpeta_1), kind="matters", matter_id=proyecto)
            check("vincular una carpeta a un PROYECTO: aceptada (mismo mecanismo del asunto)",
                  bool(src1.get("id")))

            src2 = await register_source(a, str(carpeta_2), kind="matters", matter_id=proyecto)
            check("un PROYECTO admite VARIAS carpetas a la vez (ids distintos)",
                  src2["id"] != src1["id"])

            activas = await get_matter_sources(a, proyecto)
            check("get_matter_sources: el proyecto reporta sus 2 carpetas activas",
                  len(activas) == 2 and {s["id"] for s in activas} == {src1["id"], src2["id"]})

            # --- indexar ---
            r1 = await sync.sync_source(a, src1)
            r2 = await sync.sync_source(a, src2)
            check("indexar carpeta 1 del proyecto: indexed=2 (acuerdo + anexo), errors=0",
                  r1["indexed"] == 2 and r1["errors"] == 0)
            check("indexar carpeta 2 del proyecto: indexed=1 (acta), errors=0",
                  r2["indexed"] == 1 and r2["errors"] == 0)

            # --- contar (por fuente y total del proyecto) ---
            check("conteo POR CARPETA del proyecto: la 1a aporta 2, la 2a aporta 1",
                  count_folder_docs_raw(proyecto, src1["id"]) == 2
                  and count_folder_docs_raw(proyecto, src2["id"]) == 1)
            check("conteo TOTAL del proyecto = 3 documentos de carpeta",
                  count_folder_docs_raw(proyecto) == 3)

            # --- re-indexar sin cambios: throttle real del conector (nada que hacer) ---
            r1b = await sync.sync_source(a, src1)
            check("re-indexar sin cambios: indexed=0, skipped=2, deleted=0 (no repite trabajo)",
                  r1b["indexed"] == 0 and r1b["skipped"] == 2 and r1b["deleted"] == 0)

            # --- poda AISLADA entre las carpetas del PROPIO proyecto ---
            (carpeta_1 / "anexo.md").unlink()
            r1c = await sync.sync_source(a, src1)
            check("borrar un archivo de la carpeta 1 y re-indexar: deleted=1 (solo ese)",
                  r1c["deleted"] == 1)
            check("poda AISLADA dentro del proyecto: la carpeta 2 queda INTACTA (sigue en 1)",
                  count_folder_docs_raw(proyecto, src2["id"]) == 1)
            check("la carpeta 1 conserva su documento vivo (queda en 1)",
                  count_folder_docs_raw(proyecto, src1["id"]) == 1)

            # --- DESVINCULAR: el fallo real que llegó al dueño ---
            total_antes = count_folder_docs_raw(proyecto)
            ok_off = await disable_source(a, src1["id"])
            check("desvincular una carpeta del proyecto: disable_source devuelve True", ok_off)
            check("DESVINCULAR CONSERVA lo indexado: el total del proyecto no baja "
                  f"(antes={total_antes}, después={count_folder_docs_raw(proyecto)})",
                  count_folder_docs_raw(proyecto) == total_antes)
            check("desvincular la carpeta 1 no toca los documentos de la carpeta 2",
                  count_folder_docs_raw(proyecto, src2["id"]) == 1)

            restantes = await get_matter_sources(a, proyecto)
            check("tras desvincular: el proyecto reporta SOLO la carpeta que queda",
                  len(restantes) == 1 and restantes[0]["id"] == src2["id"])

            # --- re-vincular la MISMA carpeta al MISMO proyecto: no re-ingiere ---
            src1_again = await register_source(a, str(carpeta_1), kind="matters",
                                               matter_id=proyecto)
            r1d = await sync.sync_source(a, src1_again)
            check("re-vincular la misma carpeta al mismo proyecto: no re-ingiere lo que no "
                  "cambió (indexed=0, skipped=1)",
                  r1d["indexed"] == 0 and r1d["skipped"] == 1)
        finally:
            lf.extract_text_detailed = orig_extract
    finally:
        await pool.close_pool()


# ── checks de la superficie HTTP sobre un PROYECTO ───────────────────────────
def api_checks(tid_a: str, tid_b: str, work: Path) -> None:
    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    token_a = jwt.encode({"tenant_id": tid_a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    token_b = jwt.encode({"tenant_id": tid_b}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}
    visible: list[str] = []

    with TestClient(app) as client:
        # --- crear el PROYECTO por la superficie real ---
        rp = client.post("/api/matters", headers=auth_a,
                         json={"name": "Proyecto de prueba", "description": "", "kind": "proyecto"})
        check("POST /api/matters kind='proyecto' -> 201 crea el proyecto",
              rp.status_code == 201 and rp.json().get("kind") == "proyecto")
        visible.append(rp.text)
        proyecto = rp.json()["id"]

        carpeta_1 = work / "http_contratos"
        carpeta_1.mkdir(parents=True, exist_ok=True)
        (carpeta_1 / "minuta.md").write_text("# Minuta\n\nDocumento del proyecto.",
                                             encoding="utf-8")
        carpeta_2 = work / "http_actas"
        carpeta_2.mkdir(parents=True, exist_ok=True)
        (carpeta_2 / "memoria.txt").write_text("Memoria de la segunda carpeta.",
                                               encoding="utf-8")

        # --- vincular dos carpetas AL PROYECTO ---
        r1 = client.post(f"/api/matters/{proyecto}/folders", headers=auth_a,
                         json={"path": str(carpeta_1), "label": "Contratos"})
        check("POST /folders sobre un PROYECTO -> 200 vincula la 1a carpeta",
              r1.status_code == 200 and r1.json().get("status") == "linked")
        visible.append(r1.text)
        source1_id = r1.json()["id"]

        r2 = client.post(f"/api/matters/{proyecto}/folders", headers=auth_a,
                         json={"path": str(carpeta_2), "label": "Actas"})
        check("POST /folders sobre un PROYECTO -> 200 vincula la 2a carpeta (sin 409)",
              r2.status_code == 200 and r2.json().get("status") == "linked")
        visible.append(r2.text)
        source2_id = r2.json()["id"]

        # --- esperar a que la ingesta converja ---
        # La ingesta NO es síncrona: POST /folders solo ENCOLA un trabajo durable y el
        # trabajador (jobs/durable.DurableWorker) lo reclama con POLL_SECONDS = 1.0s. Este
        # bucle DEBE ceder tiempo real de reloj al trabajador entre sondeos; un bucle que
        # gire sin dormir agota sus vueltas en décimas de segundo y falla SIEMPRE aunque el
        # código de producción esté bien (fue exactamente la causa raíz de los dos checks
        # rojos de test_matter_folders_multi.py). Por eso el corte es por RELOJ.
        # Presupuesto MEDIDO. Las cifras viejas (9.8 / 11.2 / 8.2 / 11.3 s, gate hermano)
        # se tomaron TODAS sobre la base de desarrollo, caliente y ya poblada — y por eso
        # sobreestimaban el margen. Medido el 2026-07-20 sobre una base RECIÉN creada
        # (schema.sql + migraciones, cero filas), que es como la estrena un despacho nuevo:
        #   · base de desarrollo caliente ....... convergió en 5.6 s
        #   · base fría, primer arranque ........ NO convergió dentro de 60 s (rojo)
        #   · base fría, segunda pasada ......... convergió en 42.0 s
        # El coste de la primera pasada en frío no es la indexación: es el atasco de
        # trabajos de clasificación que el tramo del conector deja encolados y que el
        # trabajador (concurrency=2) drena antes de llegar a los sync. 60 s no daba ~5x
        # sobre eso, daba menos de 1.5x. 180 s ≈ 4x sobre los 42 s en frío.
        # OJO — esto es PACIENCIA, no un umbral: el check exige igual files>=1 en ambas
        # carpetas. Si la ingesta está rota el contador se queda en 0 y el check se pone
        # ROJO igual, solo que más tarde. Alargar el reloj no deja pasar nada roto.
        deadline = time.monotonic() + 180.0
        t0 = time.monotonic()
        files1 = files2 = 0
        elapsed = 0.0
        while True:
            rl = client.get(f"/api/matters/{proyecto}/folders", headers=auth_a)
            byid = {f["id"]: f for f in rl.json().get("folders", [])}
            files1 = byid.get(source1_id, {}).get("files_indexed", 0)
            files2 = byid.get(source2_id, {}).get("files_indexed", 0)
            elapsed = time.monotonic() - t0
            if files1 >= 1 and files2 >= 1:
                break
            if time.monotonic() >= deadline:
                break
            time.sleep(0.1)
        check(f"GET /folders del PROYECTO -> las 2 carpetas con su conteo por fuente "
              f"(convergió en {elapsed:.1f}s)",
              rl.status_code == 200 and files1 >= 1 and files2 >= 1)
        visible.append(rl.text)

        # --- re-indexar: throttle de 60s por fuente ---
        rs = client.post(f"/api/matters/{proyecto}/folders/{source1_id}/sync", headers=auth_a)
        check("POST /folders/{id}/sync del PROYECTO -> throttle 'up_to_date' (<60s)",
              rs.status_code == 200 and rs.json().get("status") == "up_to_date")
        visible.append(rs.text)

        # --- el panel de Fuentes que el abogado ve de verdad ---
        rsrc = client.get(f"/api/matters/{proyecto}/sources", headers=auth_a)
        carpetas = [s for s in rsrc.json().get("sources", []) if s["tipo"] == "carpeta"]
        check("GET /sources del PROYECTO -> el panel lista las 2 carpetas vinculadas",
              rsrc.status_code == 200 and len(carpetas) == 2
              and {c["id"] for c in carpetas} == {source1_id, source2_id})
        check("GET /sources del PROYECTO -> cada carpeta trae su conteo y su estado en llano",
              all(c["documentos"] >= 1 and isinstance(c["estado"], str) and c["estado"]
                  for c in carpetas))
        visible.append(rsrc.text)

        # --- un proyecto de OTRO despacho no es alcanzable (RLS) ---
        r_ajeno = client.get(f"/api/matters/{proyecto}/folders", headers=auth_b)
        check("GET /folders del proyecto con tenant AJENO -> 401/404 (RLS fail-closed)",
              r_ajeno.status_code in (401, 404))
        visible.append(r_ajeno.text)

        # --- DESVINCULAR por HTTP: el escenario que falló con el dueño delante ---
        total_antes = count_folder_docs_raw(proyecto)
        conteo_hermana_antes = next(
            f["files_indexed"] for f in rl.json()["folders"] if f["id"] == source2_id)
        rd = client.delete(f"/api/matters/{proyecto}/folders/{source1_id}", headers=auth_a)
        check("DELETE /folders/{id} del PROYECTO -> 200 desvincula esa carpeta",
              rd.status_code == 200 and rd.json().get("status") == "unlinked")
        visible.append(rd.text)

        check("DESVINCULAR del PROYECTO CONSERVA lo indexado: el total no baja "
              f"(antes={total_antes}, después={count_folder_docs_raw(proyecto)})",
              count_folder_docs_raw(proyecto) == total_antes)

        rl2 = client.get(f"/api/matters/{proyecto}/folders", headers=auth_a)
        quedan = rl2.json().get("folders", [])
        check("tras desvincular: el proyecto lista SOLO la carpeta que queda",
              len(quedan) == 1 and quedan[0]["id"] == source2_id)
        check("la carpeta que queda conserva su conteo (no la tocó la desvinculación)",
              quedan[0]["files_indexed"] == conteo_hermana_antes)
        visible.append(rl2.text)

        rsrc2 = client.get(f"/api/matters/{proyecto}/sources", headers=auth_a)
        carpetas2 = [s for s in rsrc2.json().get("sources", []) if s["tipo"] == "carpeta"]
        check("tras desvincular: el panel de Fuentes ya no muestra la carpeta desvinculada",
              len(carpetas2) == 1 and carpetas2[0]["id"] == source2_id)
        visible.append(rsrc2.text)

    # §G — sin jerga técnica en lo que ve el abogado
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def main() -> int:
    print("== Carpeta vinculada a un PROYECTO (kind='proyecto' · multi-carpeta) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env — necesario para la migración")
        return 1
    if not config.JWT_SECRET:
        print("  [FAIL] JWT_SECRET vacío en .env — necesario para la superficie HTTP")
        return 1

    init_local_folders.apply()          # idempotente: tablas de la allowlist (016)
    init_matter_folders.apply()         # idempotente: columnas del expediente vinculado (025)
    init_projects_multifolder.apply()   # idempotente: kind/source_id/body (028)
    # 034 NO es opcional: POST /api/matters/{id}/folders no indexa en caliente, ENCOLA un
    # trabajo durable (matter_folders.py -> enqueue_job -> INSERT INTO durable_jobs). Sin
    # esta migración la mitad HTTP del gate revienta con UndefinedTable en una base que no
    # la tenga ya aplicada — que es el caso de cualquier base de desarrollo recién creada
    # con init_db.py, porque init_db.py aplica schema.sql y NADA más. Verificado el
    # 2026-07-20 contra una base virgen: sin esta línea el gate muere con exit 120.
    init_durable_jobs.apply()           # idempotente: cola local de trabajos (034)

    (ROOT / ".tmp").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="carpetaproyecto_", dir=str(ROOT / ".tmp")))

    a, b = make_tenants()
    proyecto = make_project(a, "Proyecto A (carpeta vinculada)")
    try:
        asyncio.run(connector_checks(a, proyecto, work / "connector"))
        api_checks(a, b, work / "http")
    finally:
        drop_tenants(a, b)
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Carpeta de proyecto OK — vincular/indexar/contar/desvincular verificado.")
        return 0
    print("Carpeta de proyecto FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
