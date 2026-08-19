"""
Mia · test_pinecone_wiring.py — gate del Módulo A (Pinecone como store SECUNDARIO
opt-in, cableado real: sync de carpetas/Obsidian + retrieval).

Hasta esta meta, `get_pinecone_connector()` existía pero CERO llamadores en
producción lo usaban: la clave se guardaba y el indicador mostraba "activo" sin que
ninguna operación real lo tocara. Este gate ejercita el cableado de verdad:

  1. `pinecone_scope_for_tenant(tenant_id)`: sin config de Pinecone del despacho en
     `tenant_settings` (RLS) → connector Noop; con config → connector real (aquí con
     un `FakeIndex` inyectado, sin red).
  2. `LocalFolderSync._upsert_chunks/_delete_removed`: tras el INSERT/DELETE en
     `knowledge_chunks`, espeja en Pinecone con id determinista
     `local:<source_id>:<filepath>:<chunk_index>` (re-sync hace upsert, no duplica) y
     namespace `tenant_<tenant_id>`.
  3. `ObsidianSync._upsert_chunks/_delete_removed`: mismo patrón, id
     `obsidian:<filepath>:<chunk_index>`.
  4. `retrieval.retrieve_knowledge_rrf`: AUMENTA con `pinecone_secondary_notes` (menor
     prioridad, al final) — nunca compite en el RRF de pgvector.
  5. FAIL-SOFT en las tres direcciones: una excepción del `FakeIndex` (upsert/query)
     NUNCA rompe el sync ni el retrieve — mismo patrón que `wiki_notes` /
     `_notebooklm_context`.

Usa la DB real (RLS de verdad, migraciones 004/016) y embeddings + Pinecone MOCKEADOS
(sin red, sin paquete `pinecone` real). `test_pinecone_connector.py` (Módulo 3d, la
factory sola) queda intacto — este gate prueba el CABLEADO, no la factory.

HALT: si este gate falla, NO se avanza (CLAUDE.md §G). Salida: exit 0 = PASS · 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_pinecone_wiring.py
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
from psycopg.types.json import Json

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

import init_knowledge_stores                            # noqa: E402  (migración 004)
import init_local_folders                                # noqa: E402  (migración 016)
from mia import config, embeddings                       # noqa: E402
from mia.db import pool                                  # noqa: E402
from mia.connectors import pinecone_connector as pc_mod   # noqa: E402
from mia.connectors.local_folders import LocalFolderSync, register_source  # noqa: E402
from mia.connectors.obsidian_sync import ObsidianSync     # noqa: E402
from mia.agents import retrieval                          # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── embeddings mockeados (sin red): vector(1024) aleatorio por texto ─────────
def _fake_embed(texts):
    return [[random.random() for _ in range(config.EMBED_DIM)] for _ in texts]


embeddings.embed_texts = _fake_embed


# ── FakeIndex: mismo patrón de test_pinecone_connector.py (registra llamadas, sin red) ──
class FakeIndex:
    def __init__(self) -> None:
        self.upserts: list[dict] = []
        self.queries: list[dict] = []
        self.deletes: list[dict] = []
        self.raise_on_upsert = False
        self.raise_on_query = False
        self.raise_on_delete = False

    def upsert(self, vectors=None, namespace=None, **kw):
        if self.raise_on_upsert:
            raise RuntimeError("FakeIndex.upsert: fallo simulado (fail-soft)")
        self.upserts.append({"namespace": namespace, "vectors": vectors})
        return {"upserted_count": len(vectors)}

    def query(self, **kwargs):
        if self.raise_on_query:
            raise RuntimeError("FakeIndex.query: fallo simulado (fail-soft)")
        self.queries.append(kwargs)
        return {"matches": [{"id": "pc-match-1", "score": 0.77,
                             "metadata": {"content": "nota espejada en Pinecone",
                                          "source": "local:x", "source_path": "y.md"}}]}

    def delete(self, ids=None, namespace=None, **kw):
        if self.raise_on_delete:
            raise RuntimeError("FakeIndex.delete: fallo simulado (fail-soft)")
        self.deletes.append({"ids": ids, "namespace": namespace})
        return {}

    def describe_index_stats(self):
        return {"namespaces": {}}


FAKE = FakeIndex()


def _fake_get_pinecone_connector():
    """Réplica de la factory real, pero con FakeIndex inyectado (sin red, sin paquete
    `pinecone`). Respeta el mismo criterio: sin clave del tenant en el scope → Noop."""
    from mia.security import get_tenant_secret

    api_key = get_tenant_secret("pinecone_api_key")
    if not api_key:
        return pc_mod.NoopPineconeConnector()
    index_name = get_tenant_secret("pinecone_index_name", pc_mod.DEFAULT_INDEX_NAME)
    conn = pc_mod.PineconeConnector(api_key, index_name or pc_mod.DEFAULT_INDEX_NAME,
                                    pc_mod.DEFAULT_NAMESPACE_PREFIX)
    conn._index = FAKE
    return conn


pc_mod.get_pinecone_connector = _fake_get_pinecone_connector

# ── conexión admin (postgres) para tenants y limpieza ────────────────────────
PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)
TENANT_NAMES = ("PCWIRE_NOPINE", "PCWIRE_PINE")


def make_tenants() -> tuple[str, str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE name = ANY(%s)", (list(TENANT_NAMES),))
        nopine = c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (TENANT_NAMES[0],)
        ).fetchone()[0]
        pine = c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (TENANT_NAMES[1],)
        ).fetchone()[0]
        # T_PINE configuró Pinecone en su pantalla (tenant_settings, sin cifrar — el
        # gate no ejercita at_rest, eso lo cubre test_pinecone_connector.py/ux.py).
        c.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s, %s)",
            (pine, Json({"pinecone": {"api_key": "fake-key-test", "index_name": "mia-legal"}})),
        )
    return str(nopine), str(pine)


def drop_tenants(nopine: str, pine: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([nopine, pine],))


# ── (a) LocalFolderSync ───────────────────────────────────────────────────────
async def check_local_folders(nopine: str, pine: str, work: Path) -> None:
    sync = LocalFolderSync()

    docs_np = work / "docs_nopine"
    docs_np.mkdir(parents=True, exist_ok=True)
    (docs_np / "nota.txt").write_text("contenido sin Pinecone configurado.", encoding="utf-8")
    src_np = await register_source(nopine, str(docs_np))
    s_np = await sync.sync_tenant(nopine)
    check("local_folders (a1): sync SIN Pinecone configurado indexa en pgvector",
          s_np["indexed"] == 1 and s_np["errors"] == 0)
    check("local_folders (a2): FakeIndex NO recibió NINGUNA llamada (connector Noop)",
          FAKE.upserts == [] and FAKE.deletes == [] and FAKE.queries == [])

    docs_p = work / "docs_pine"
    docs_p.mkdir(parents=True, exist_ok=True)
    (docs_p / "nota.txt").write_text("contenido CON Pinecone configurado.", encoding="utf-8")
    src_p = await register_source(pine, str(docs_p))
    db_source = "local:" + src_p["id"]

    s_p = await sync.sync_tenant(pine)
    check("local_folders (b1): sync CON Pinecone configurado indexa en pgvector",
          s_p["indexed"] == 1 and s_p["errors"] == 0)
    check("local_folders (b2): el upsert SÍ llegó a Pinecone (espejo real)",
          len(FAKE.upserts) == 1 and FAKE.upserts[0]["vectors"][0]["id"]
          == f"{db_source}:nota.txt:0")
    check("local_folders (b3): namespace aislado por tenant",
          FAKE.upserts[0]["namespace"] == f"tenant_{pine}")
    check("local_folders (b4): metadata trae content/source/source_path",
          FAKE.upserts[0]["vectors"][0]["metadata"]["source_path"] == "nota.txt"
          and FAKE.upserts[0]["vectors"][0]["metadata"]["source"] == db_source
          and "Pinecone configurado" in FAKE.upserts[0]["vectors"][0]["metadata"]["content"])

    # --- re-sync sin cambios: idempotente, CERO llamadas nuevas a Pinecone (skip) ---
    FAKE.upserts.clear()
    s_p2 = await sync.sync_tenant(pine)
    check("local_folders (c1): re-sync sin cambios → skipped, sin upsert nuevo a Pinecone",
          s_p2["indexed"] == 0 and FAKE.upserts == [])

    # --- archivo modificado: upsert de nuevo (id determinista, mismo id = no duplica) ---
    (docs_p / "nota.txt").write_text("contenido EDITADO con Pinecone configurado.",
                                     encoding="utf-8")
    s_p3 = await sync.sync_tenant(pine)
    check("local_folders (d1): archivo editado → upsert de nuevo con el MISMO id determinista",
          s_p3["indexed"] == 1 and len(FAKE.upserts) == 1
          and FAKE.upserts[0]["vectors"][0]["id"] == f"{db_source}:nota.txt:0")

    # --- archivo borrado: el delete SÍ llega a Pinecone con el id correcto ---
    FAKE.upserts.clear()
    (docs_p / "nota.txt").unlink()
    s_p4 = await sync.sync_tenant(pine)
    check("local_folders (e1): archivo borrado → deleted=1 en pgvector",
          s_p4["deleted"] == 1)
    check("local_folders (e2): el delete SÍ llegó a Pinecone con el id + namespace correctos",
          len(FAKE.deletes) == 1 and FAKE.deletes[0]["ids"] == [f"{db_source}:nota.txt:0"]
          and FAKE.deletes[0]["namespace"] == f"tenant_{pine}")

    # --- FAIL-SOFT: Pinecone revienta en el upsert → el sync de pgvector SIGUE OK ---
    (docs_p / "otra.txt").write_text("archivo nuevo mientras Pinecone falla.", encoding="utf-8")
    FAKE.raise_on_upsert = True
    try:
        s_p5 = await sync.sync_tenant(pine)
    finally:
        FAKE.raise_on_upsert = False
    async with pool.tenant_connection(pine) as conn:
        row = await (await conn.execute(
            "SELECT count(*) FROM knowledge_chunks WHERE source=%s AND source_path='otra.txt'",
            (db_source,),
        )).fetchone()
    check("local_folders (f1): FAIL-SOFT — FakeIndex.upsert revienta y el sync NO se rompe",
          s_p5["indexed"] == 1 and s_p5["errors"] == 0)
    check("local_folders (f2): FAIL-SOFT — pgvector quedó escrito pese al fallo de Pinecone",
          row[0] == 1)


# ── (b) ObsidianSync ──────────────────────────────────────────────────────────
async def check_obsidian(nopine: str, pine: str, work: Path) -> None:
    sync = ObsidianSync()
    FAKE.upserts.clear()
    FAKE.deletes.clear()

    vault_np = work / "vault_nopine"
    vault_np.mkdir(parents=True, exist_ok=True)
    (vault_np / "nota.md").write_text("# Nota\n\nsin Pinecone configurado.", encoding="utf-8")
    await sync.sync(str(vault_np), nopine)
    check("obsidian (a1): sync SIN Pinecone configurado → FakeIndex sigue sin llamadas",
          FAKE.upserts == [] and FAKE.deletes == [])

    vault_p = work / "vault_pine"
    vault_p.mkdir(parents=True, exist_ok=True)
    (vault_p / "nota.md").write_text("# Nota\n\ncon Pinecone configurado.", encoding="utf-8")
    await sync.sync(str(vault_p), pine)
    check("obsidian (b1): el upsert SÍ llegó a Pinecone con id 'obsidian:<path>:<idx>'",
          len(FAKE.upserts) == 1
          and FAKE.upserts[0]["vectors"][0]["id"] == "obsidian:nota.md:0"
          and FAKE.upserts[0]["namespace"] == f"tenant_{pine}")

    # --- borrado: delete espejado ---
    FAKE.upserts.clear()
    FAKE.deletes.clear()
    (vault_p / "nota.md").unlink()
    await sync.sync(str(vault_p), pine)
    check("obsidian (c1): nota borrada → delete espejado en Pinecone",
          len(FAKE.deletes) == 1 and FAKE.deletes[-1]["ids"] == ["obsidian:nota.md:0"])

    # --- FAIL-SOFT: Pinecone revienta al borrar la nota reincorporada ---
    (vault_p / "otra.md").write_text("# Otra\n\ncontenido nuevo.", encoding="utf-8")
    await sync.sync(str(vault_p), pine)  # deja otra.md indexada
    FAKE.deletes.clear()
    (vault_p / "otra.md").unlink()
    FAKE.raise_on_delete = True
    try:
        stats = await sync.sync(str(vault_p), pine)
    finally:
        FAKE.raise_on_delete = False
    async with pool.tenant_connection(pine) as conn:
        row = await (await conn.execute(
            "SELECT count(*) FROM knowledge_chunks WHERE source='obsidian' AND source_path='otra.md'",
        )).fetchone()
    check("obsidian (d1): FAIL-SOFT — Pinecone.delete revienta y el sync NO se rompe",
          stats["deleted"] == 1 and stats["errors"] == 0)
    check("obsidian (d2): FAIL-SOFT — knowledge_chunks quedó consistente pese al fallo",
          row[0] == 0)


# ── (c) retrieval.pinecone_secondary_notes / retrieve_knowledge_rrf ───────────
async def check_retrieval(nopine: str, pine: str) -> None:
    qvec = [0.05] * config.EMBED_DIM

    notes_np = await retrieval.retrieve_knowledge_rrf(nopine, "consulta cualquiera", qvec)
    check("retrieval (a1): tenant SIN Pinecone → NINGUNA nota con id 'pc-match-1'",
          all(n.get("id") != "pc-match-1" for n in notes_np))

    FAKE.queries.clear()
    notes_p = await retrieval.retrieve_knowledge_rrf(pine, "consulta cualquiera", qvec, top_k=4)
    match = next((n for n in notes_p if n.get("id") == "pc-match-1"), None)
    check("retrieval (b1): tenant CON Pinecone → la nota secundaria SÍ aparece (append, "
          "menor prioridad)", match is not None)
    check("retrieval (b2): la nota trae content/source/source_path/score desde metadata",
          match is not None and match["content"] == "nota espejada en Pinecone"
          and match["source"] == "local:x" and match["source_path"] == "y.md"
          and match["score"] == 0.77)
    check("retrieval (b3): la consulta a Pinecone llevó el vector + namespace del tenant",
          bool(FAKE.queries) and FAKE.queries[-1]["namespace"] == f"tenant_{pine}")

    # --- FAIL-SOFT: Pinecone.query revienta → retrieve_knowledge_rrf sigue sin la nota ---
    FAKE.raise_on_query = True
    try:
        notes_boom = await retrieval.retrieve_knowledge_rrf(pine, "consulta cualquiera", qvec)
    finally:
        FAKE.raise_on_query = False
    check("retrieval (c1): FAIL-SOFT — Pinecone.query revienta y retrieve NO lanza excepción "
          "(sigue con lo de pgvector/wiki)",
          all(n.get("id") != "pc-match-1" for n in notes_boom))

    # --- pinecone_secondary_notes en Noop devuelve [] sin llamar query ---
    FAKE.queries.clear()
    direct = await retrieval.pinecone_secondary_notes(nopine, qvec)
    check("retrieval (d1): pinecone_secondary_notes en tenant sin config → [] sin llamar query",
          direct == [] and FAKE.queries == [])


def main() -> int:
    print("== Módulo A · Pinecone cableado (LocalFolderSync + ObsidianSync + retrieval) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env — necesario para la migración")
        return 1

    init_knowledge_stores.apply()
    init_local_folders.apply()

    (ROOT / ".tmp").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="pcwire_", dir=str(ROOT / ".tmp")))

    nopine, pine = make_tenants()
    try:
        async def run_all():
            await pool.open_pool()
            try:
                await check_local_folders(nopine, pine, work)
                await check_obsidian(nopine, pine, work)
                await check_retrieval(nopine, pine)
            finally:
                await pool.close_pool()

        asyncio.run(run_all())
    finally:
        drop_tenants(nopine, pine)
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Pinecone cableado OK — Módulo A verificado (secundario opt-in, fail-soft, "
              "aislado por namespace, nunca compite en el RRF de pgvector).")
        return 0
    print("Pinecone cableado FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
