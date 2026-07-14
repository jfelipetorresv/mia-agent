"""
Mia · test_matter_sources.py — gate de FUENTES UNIFICADAS del expediente (Bloque A · limpieza).

Ejercita GET /api/matters/{id}/sources contra la DB real (migraciones 016+025+027+028):
la vista única que junta carpetas del equipo, carpetas de OneDrive y correos vinculados
al expediente, en llano y con el conteo de documentos POR fuente. Cubre:

  · Asunto con 2 carpetas locales sincronizadas → 2 items 'carpeta' con su conteo POR
    fuente (no mezclado) + el item 'correo' SIEMPRE presente (0, estado llano)
  · Proyecto (kind='proyecto') con 1 carpeta → misma vista, funciona igual
  · OneDrive: una sola fuente 'matters' → se le atribuye el total; DOS fuentes → la
    primera se lleva el total y la segunda muestra 0 con estado honesto (deuda anotada
    de documents.source_id sin poblar para origin='drive')
  · Fail-soft: si el conector remoto revienta, la vista responde 200 sin las fuentes
    de OneDrive (nunca un 500 por eso)
  · Matter ajeno (otro tenant) → 401; uuid malformado → 401/404, ambos en llano
  · §G: nada de jerga técnica en los textos que ve el abogado

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_matter_sources.py
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
import init_remote_sources                             # noqa: E402  (migración 027)
import init_projects_multifolder                       # noqa: E402  (migración 028)
import init_durable_jobs                               # noqa: E402  (migración 034)
from mia import config, embeddings                     # noqa: E402
from mia.db import pool                                # noqa: E402
from mia.connectors import local_folders as lf         # noqa: E402
from mia.connectors.local_folders import LocalFolderSync, register_source  # noqa: E402
from mia.connectors import graph_drive as gd           # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red): embeddings vector(1024) aleatorio; extract_text para PDF/Word ──
def _fake_embed(texts):
    return [[random.random() for _ in range(config.EMBED_DIM)] for _ in texts]


embeddings.embed_texts = _fake_embed

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "chunk", "embedding",
             "sync engine", "uuid", "endpoint")

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def make_tenants() -> tuple[str, str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A test sources') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test sources') RETURNING id").fetchone()[0]
    return str(a), str(b)


def make_matter(tenant_id: str, title: str, kind: str = "asunto") -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO matters(tenant_id, title, kind) VALUES(%s::uuid, %s, %s) RETURNING id",
            (tenant_id, title, kind)).fetchone()[0])


def drop_tenants(a: str, b: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([a, b],))


def insert_doc(matter_id: str, tenant_id: str, filename: str, origin: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute(
            "INSERT INTO documents (tenant_id, matter_id, filename, mime, sha256, origin) "
            "VALUES (%s::uuid, %s::uuid, %s, 'text/plain', %s, %s)",
            (tenant_id, matter_id, filename, f"sha-{filename}-{origin}", origin))


# ── siembra: carpeta local con N archivos .md, sincronizada de verdad ────────────
async def seed_local_folder(tenant_id: str, matter_id: str, root: Path, n_files: int) -> dict:
    root.mkdir(parents=True, exist_ok=True)
    for i in range(n_files):
        (root / f"doc{i}.md").write_text(f"# Documento {i}\n\nContenido del expediente.",
                                         encoding="utf-8")
    src = await register_source(tenant_id, str(root), kind="matters", matter_id=matter_id)
    stats = await LocalFolderSync().sync_source(tenant_id, src)
    return {"source": src, "stats": stats}


async def seed_setup(a: str, matter_asunto: str, matter_proyecto: str, work: Path) -> None:
    await pool.open_pool()
    try:
        # Asunto: DOS carpetas locales con conteos DISTINTOS (2 y 1 documentos).
        s1 = await seed_local_folder(a, matter_asunto, work / "carpeta_1", 2)
        s2 = await seed_local_folder(a, matter_asunto, work / "carpeta_2", 1)
        check("siembra: carpeta_1 ingirió 2 documentos", s1["stats"]["indexed"] == 2)
        check("siembra: carpeta_2 ingirió 1 documento", s2["stats"]["indexed"] == 1)
        seed_setup.source1_id = s1["source"]["id"]
        seed_setup.source2_id = s2["source"]["id"]

        # Proyecto: UNA carpeta local con 1 documento.
        sp = await seed_local_folder(a, matter_proyecto, work / "carpeta_proyecto", 1)
        check("siembra: carpeta del proyecto ingirió 1 documento", sp["stats"]["indexed"] == 1)
        seed_setup.source_proj_id = sp["source"]["id"]
    finally:
        await pool.close_pool()


# ── checks de la superficie HTTP (TestClient + JWT) ──────────────────────────────
def api_checks(a: str, b: str, matter_asunto: str, matter_proyecto: str) -> None:
    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    token_a = jwt.encode({"tenant_id": a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    token_b = jwt.encode({"tenant_id": b}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}
    visible: list[str] = []

    with TestClient(app) as client:
        # ── 1) Asunto con 2 carpetas + correo (0 docs) ───────────────────────────
        r = client.get(f"/api/matters/{matter_asunto}/sources", headers=auth_a)
        check("GET /sources (asunto) -> 200", r.status_code == 200)
        visible.append(r.text)
        data = r.json().get("sources", [])
        carpetas = [s for s in data if s["tipo"] == "carpeta"]
        correos = [s for s in data if s["tipo"] == "correo"]
        check("asunto: trae 2 items 'carpeta'", len(carpetas) == 2)
        check("asunto: trae 1 item 'correo' (siempre presente)", len(correos) == 1)

        by_id = {c["id"]: c for c in carpetas}
        check("asunto: carpeta_1 muestra su conteo POR fuente (2, no mezclado)",
              by_id.get(seed_setup.source1_id, {}).get("documentos") == 2)
        check("asunto: carpeta_2 muestra su conteo POR fuente (1, no mezclado)",
              by_id.get(seed_setup.source2_id, {}).get("documentos") == 1)
        check("asunto: carpeta_1 trae estado en llano ('2 documentos leídos')",
              by_id.get(seed_setup.source1_id, {}).get("estado") == "2 documentos leídos")
        check("asunto: el item de correo trae documentos=0 y estado llano",
              correos[0]["documentos"] == 0
              and correos[0]["estado"] == "Sin correos vinculados todavía")
        check("asunto: el item de correo trae id=None", correos[0]["id"] is None)

        # Vincular un correo (origin='mail') al asunto: el conteo debe reflejarlo.
        insert_doc(matter_asunto, a, "correo1.txt", "mail")
        insert_doc(matter_asunto, a, "correo2.txt", "mail")
        r = client.get(f"/api/matters/{matter_asunto}/sources", headers=auth_a)
        correo_item = next(s for s in r.json()["sources"] if s["tipo"] == "correo")
        check("asunto: tras vincular 2 correos, el item de correo trae documentos=2",
              correo_item["documentos"] == 2)
        check("asunto: estado del correo pasa a 'X documentos leídos'",
              correo_item["estado"] == "2 documentos leídos")
        visible.append(r.text)

        # ── 2) Proyecto con 1 carpeta → funciona igual ───────────────────────────
        r = client.get(f"/api/matters/{matter_proyecto}/sources", headers=auth_a)
        check("GET /sources (proyecto) -> 200", r.status_code == 200)
        visible.append(r.text)
        data = r.json().get("sources", [])
        carpetas_p = [s for s in data if s["tipo"] == "carpeta"]
        correos_p = [s for s in data if s["tipo"] == "correo"]
        check("proyecto: trae 1 item 'carpeta' con su conteo",
              len(carpetas_p) == 1 and carpetas_p[0]["documentos"] == 1)
        check("proyecto: trae también el item 'correo' (0, sin correos)",
              len(correos_p) == 1 and correos_p[0]["documentos"] == 0)

        # ── 3) Matter ajeno → 401 ────────────────────────────────────────────────
        r = client.get(f"/api/matters/{matter_asunto}/sources", headers=auth_b)
        check("GET /sources de un expediente AJENO -> 401", r.status_code == 401)
        visible.append(r.text)

        # uuid malformado → 401/404, en llano (nunca 500)
        r = client.get("/api/matters/no-soy-un-uuid/sources", headers=auth_a)
        check("GET /sources con id malformado -> 401 o 404 (nunca 500)",
              r.status_code in (401, 404))
        visible.append(r.text)

        # sin sesión (sin JWT) → 401
        r = client.get(f"/api/matters/{matter_asunto}/sources")
        check("GET /sources sin sesión -> 401", r.status_code == 401)
        visible.append(r.text)

    # §G — sin jerga técnica en lo que ve el abogado
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


# ── OneDrive: una fuente = total; dos fuentes = reparto honesto + fail-soft ──────
# NOTA: cada registro de fuente remota corre en su PROPIO asyncio.run (abre y cierra el
# pool antes de tocar TestClient) — mezclar pool.open_pool()/close_pool() con un bloque
# `with TestClient(app)` YA abierto (que gestiona el mismo pool global en OTRO loop vía
# el lifespan de la app) revienta con "future belongs to a different loop".
async def _register_drive_source(tenant_id: str, matter_id: str, item_id: str, label: str) -> None:
    await pool.open_pool()
    try:
        await gd.register_source(tenant_id, item_id, label=label, kind="matters",
                                 matter_id=matter_id)
    finally:
        await pool.close_pool()


def _auth_header(tenant_id: str) -> dict:
    import jwt
    token = jwt.encode({"tenant_id": tenant_id}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    return {"Authorization": f"Bearer {token}"}


def onedrive_checks_single(a: str, matter_asunto: str) -> None:
    """UNA fuente de OneDrive con 2 documentos → se le atribuye el total."""
    from fastapi.testclient import TestClient
    from mia.api.main import app

    auth_a = _auth_header(a)
    with TestClient(app) as client:
        r = client.get(f"/api/matters/{matter_asunto}/sources", headers=auth_a)
        onedrive = [s for s in r.json()["sources"] if s["tipo"] == "onedrive"]
        check("OneDrive con UNA fuente: aparece 1 item con el total (2 documentos)",
              len(onedrive) == 1 and onedrive[0]["documentos"] == 2)


def onedrive_checks_double_and_failsoft(a: str, matter_asunto: str) -> None:
    """DOS fuentes de OneDrive: los documentos huérfanos (source_id NULL, de antes del
    backfill H11) NO se atribuyen a ninguna — atribuirlos a la carpeta equivocada fue
    justo la raíz de la poda cruzada. Ambas muestran 0 con estado honesto; el reparto
    real POR fuente lo cubre test_remote_drive (sync con source_id poblado). Además:
    fail-soft si el conector remoto revienta."""
    from fastapi.testclient import TestClient
    from mia.api.main import app

    auth_a = _auth_header(a)
    with TestClient(app) as client:
        r = client.get(f"/api/matters/{matter_asunto}/sources", headers=auth_a)
        onedrive2 = sorted((s for s in r.json()["sources"] if s["tipo"] == "onedrive"),
                           key=lambda s: s["documentos"], reverse=True)
        check("OneDrive con DOS fuentes: aparecen ambas", len(onedrive2) == 2)
        check("OneDrive con DOS fuentes: los huérfanos no se atribuyen a ninguna (0 y 0)",
              onedrive2[0]["documentos"] == 0 and onedrive2[1]["documentos"] == 0)
        check("OneDrive: la fuente en 0 trae un estado honesto (no jerga, no vacío ciego)",
              onedrive2[1]["estado"] in ("Todavía no la he revisado", "Aún sin documentos"))

        # Fail-soft: el conector remoto revienta -> la vista sigue en 200 SIN OneDrive.
        from mia.api.routes import matter_sources as ms_mod
        orig = ms_mod.list_drive_sources

        async def _boom(_tid):
            raise RuntimeError("Graph caído (simulado)")

        ms_mod.list_drive_sources = _boom
        try:
            r = client.get(f"/api/matters/{matter_asunto}/sources", headers=auth_a)
            check("fail-soft: si OneDrive revienta, la vista sigue en 200",
                  r.status_code == 200)
            onedrive3 = [s for s in r.json()["sources"] if s["tipo"] == "onedrive"]
            check("fail-soft: sin fuentes de OneDrive en la respuesta (nunca 500)",
                  onedrive3 == [])
        finally:
            ms_mod.list_drive_sources = orig


def main() -> int:
    print("== Fuentes unificadas del expediente (carpetas + OneDrive + correo) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env — necesario para la migración")
        return 1
    if not config.JWT_SECRET:
        print("  [FAIL] JWT_SECRET vacío en .env — necesario para la superficie HTTP")
        return 1

    init_local_folders.apply()          # idempotente: allowlist local (016)
    init_matter_folders.apply()         # idempotente: expediente vinculado (025)
    init_remote_sources.apply()         # idempotente: fuentes remotas OneDrive (027)
    init_projects_multifolder.apply()   # idempotente: matters.kind + documents.source_id (028)
    init_durable_jobs.apply()           # idempotente: estado durable de carpetas (034)

    (ROOT / ".tmp").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="mattersources_", dir=str(ROOT / ".tmp")))

    a, b = make_tenants()
    matter_asunto = make_matter(a, "Asunto con dos carpetas", kind="asunto")
    matter_proyecto = make_matter(a, "Proyecto con una carpeta", kind="proyecto")
    try:
        asyncio.run(seed_setup(a, matter_asunto, matter_proyecto, work))
        api_checks(a, b, matter_asunto, matter_proyecto)

        asyncio.run(_register_drive_source(a, matter_asunto, "item-1", "Casos OneDrive"))
        insert_doc(matter_asunto, a, "remoto1.pdf", "drive")
        insert_doc(matter_asunto, a, "remoto2.pdf", "drive")
        onedrive_checks_single(a, matter_asunto)

        asyncio.run(_register_drive_source(a, matter_asunto, "item-2", "Contratos OneDrive"))
        onedrive_checks_double_and_failsoft(a, matter_asunto)
    finally:
        drop_tenants(a, b)
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Fuentes unificadas OK — vista del expediente verificada.")
        return 0
    print("Fuentes unificadas FAIL — revisar antes de avanzar.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
