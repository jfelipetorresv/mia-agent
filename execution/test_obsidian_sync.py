"""
Mia · test_obsidian_sync.py — gate del Módulo 3c (Obsidian indexer · decisión #17).

Ejercita `ObsidianSync` contra la DB real (migración 004), con un vault de prueba TEMPORAL
bajo `.tmp/` (NUNCA el vault real). Cubre: migración + RLS de las 2 tablas, escaneo con
exclusiones, hashing, chunking por encabezados + tamaño máximo, sync incremental
(primera vez / idempotente / cambio / borrado / sin duplicar), aislamiento por tenant,
vault vacío y registro del job en el scheduler.

EMBEDDINGS MOCKEADOS: el gate reemplaza `embeddings.embed_texts` por vectores aleatorios de
1024 floats. El módulo prueba chunking/hashing/sync/RLS, no la calidad de voyage-law-2; así
el gate corre offline y sin gastar API (mismo criterio que test_hitl_flow). Si se quisiera
probar embeddings reales haría falta VOYAGE_API_KEY.

HALT: si este gate falla, NO se avanza al Módulo 3d (CLAUDE.md §G).
Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_obsidian_sync.py
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

import init_knowledge_stores                       # noqa: E402  (runner de la migración 004)
from mia import config, embeddings                 # noqa: E402
from mia.db import pool                             # noqa: E402
from mia.memory.tokens import estimate_tokens       # noqa: E402
from mia.connectors import ObsidianSync             # noqa: E402
from mia.connectors.obsidian_sync import MAX_CHUNK_TOKENS  # noqa: E402
from mia.cron import build_scheduler                # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── embeddings mockeados (sin red): vector(1024) aleatorio por texto ─────────
def _fake_embed(texts):
    return [[random.random() for _ in range(config.EMBED_DIM)] for _ in texts]


embeddings.embed_texts = _fake_embed

# ── conexión admin (postgres) para tenants y limpieza ────────────────────────
PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def make_tenants() -> tuple[str, str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A test 3c') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test 3c') RETURNING id").fetchone()[0]
    return str(a), str(b)


def drop_tenants(a: str, b: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([a, b],))


def build_vault(base: Path) -> None:
    """3 .md válidos + .obsidian/ (excluida) + _template.md (excluido)."""
    base.mkdir(parents=True, exist_ok=True)
    (base / "nota1.md").write_text(
        "# Nota Uno\n\nContenido de la nota uno sobre contratos estatales.\n\n"
        "## Cláusulas\n\nDetalle de las cláusulas de indemnización.\n", encoding="utf-8")
    (base / "nota2.md").write_text(
        "# Nota Dos\n\nResponsabilidad civil y seguros de cumplimiento.\n", encoding="utf-8")
    (base / "nota3.md").write_text(
        "# Nota Tres\n\nProcedimiento administrativo sancionatorio.\n", encoding="utf-8")
    (base / "_template.md").write_text("# Plantilla\n\nignorar", encoding="utf-8")
    dot = base / ".obsidian"
    dot.mkdir(exist_ok=True)
    (dot / "workspace.md").write_text("config interna", encoding="utf-8")


# ── checks que NO tocan DB (escaneo, hash, chunking) ─────────────────────────
def offline_checks(vault: Path) -> None:
    sync = ObsidianSync()

    files = sync._scan_vault(vault)
    rels = [sync._rel(vault, f) for f in files]
    check("scan: encuentra los 3 .md válidos", len(files) == 3)
    check("scan: excluye la carpeta .obsidian/", all(not r.startswith(".obsidian") for r in rels))
    check("scan: excluye _template.md (guion bajo)", "_template.md" not in [f.name for f in files])

    n1 = vault / "nota1.md"
    check("hash: determinista (mismo archivo -> mismo hash)",
          sync._hash_file(n1) == sync._hash_file(n1))
    check("hash: cambia con contenido distinto",
          sync._hash_file(n1) != sync._hash_file(vault / "nota2.md"))

    # Chunking: un H2 inicia un chunk nuevo.
    doc = "# Uno\n\ncuerpo de uno.\n\n## Dos\n\ncuerpo de dos.\n"
    ch = sync._chunk_document(doc, "x.md")
    check("chunk: un H2 marca el inicio de un chunk nuevo",
          len(ch) >= 2 and any(c["heading_path"] == "Uno > Dos" for c in ch))

    # Chunking: un bloque > 512 tokens (>2048 chars) se divide y cada parte respeta el máximo.
    big_body = "\n\n".join(f"Parrafo {i} con texto de relleno suficiente. " * 4 for i in range(20))
    big = f"# Grande\n\n{big_body}\n"
    chb = sync._chunk_document(big, "big.md")
    check("chunk: un bloque > 512 tokens se divide en partes <= 512",
          len(chb) >= 2 and all(estimate_tokens(c["text"]) <= MAX_CHUNK_TOKENS for c in chb))

    # Scheduler: el job de Obsidian está registrado.
    jobs = build_scheduler().list_jobs()
    check("scheduler: el job sync_obsidian aparece en list_jobs()",
          any("sync_obsidian" in j["name"] for j in jobs))


# ── checks que tocan DB (migración, RLS, sync incremental) ───────────────────
async def db_checks(a: str, b: str, vault: Path, empty_vault: Path) -> None:
    await pool.open_pool()
    try:
        sync = ObsidianSync()

        # --- migración: las 2 tablas y columnas clave existen ---
        async with pool.connection() as conn:
            cols = await (await conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='knowledge_chunks'"
            )).fetchall()
        colset = {r[0] for r in cols}
        need = {"tenant_id", "source", "source_path", "chunk_index", "content", "embedding"}
        check("migración: knowledge_chunks existe con las columnas clave", need.issubset(colset))

        async with pool.connection() as conn:
            h = await (await conn.execute(
                "SELECT to_regclass('public.obsidian_file_hashes')"
            )).fetchone()
        check("migración: obsidian_file_hashes existe", h[0] is not None)

        # --- RLS knowledge_chunks: A inserta, B no lo ve ---
        async with pool.tenant_connection(a) as conn:
            await conn.execute(
                "INSERT INTO knowledge_chunks(tenant_id, source, source_path, chunk_index, content) "
                "VALUES (%s::uuid, 'obsidian', '__rls__.md', 0, 'secreto de A')", (a,))
        async with pool.tenant_connection(b) as conn:
            nb = (await (await conn.execute(
                "SELECT count(*) FROM knowledge_chunks WHERE source_path='__rls__.md'"
            )).fetchone())[0]
        async with pool.tenant_connection(a) as conn:
            na = (await (await conn.execute(
                "SELECT count(*) FROM knowledge_chunks WHERE source_path='__rls__.md'"
            )).fetchone())[0]
            await conn.execute("DELETE FROM knowledge_chunks WHERE source_path='__rls__.md'")
        check("RLS knowledge_chunks: mia_app aislado por tenant (A ve, B no)", na == 1 and nb == 0)

        # --- RLS obsidian_file_hashes ---
        async with pool.tenant_connection(a) as conn:
            await conn.execute(
                "INSERT INTO obsidian_file_hashes(tenant_id, vault_path, file_hash) "
                "VALUES (%s::uuid, '__rls__.md', 'deadbeef')", (a,))
        async with pool.tenant_connection(b) as conn:
            hb = (await (await conn.execute(
                "SELECT count(*) FROM obsidian_file_hashes WHERE vault_path='__rls__.md'"
            )).fetchone())[0]
        async with pool.tenant_connection(a) as conn:
            ha = (await (await conn.execute(
                "SELECT count(*) FROM obsidian_file_hashes WHERE vault_path='__rls__.md'"
            )).fetchone())[0]
            await conn.execute("DELETE FROM obsidian_file_hashes WHERE vault_path='__rls__.md'")
        check("RLS obsidian_file_hashes: mia_app aislado por tenant", ha == 1 and hb == 0)

        async def count_chunks(tenant: str) -> int:
            async with pool.tenant_connection(tenant) as conn:
                return (await (await conn.execute(
                    "SELECT count(*) FROM knowledge_chunks WHERE source='obsidian'"
                )).fetchone())[0]

        # --- sync primera vez: 3 archivos indexados, hashes guardados ---
        s1 = await sync.sync(str(vault), a)
        c1 = await count_chunks(a)
        async with pool.tenant_connection(a) as conn:
            nh = (await (await conn.execute(
                "SELECT count(*) FROM obsidian_file_hashes"
            )).fetchone())[0]
        check("sync primera vez: indexed=3, skipped=0",
              s1["indexed"] == 3 and s1["skipped"] == 0 and s1["errors"] == 0)
        check("sync primera vez: hay chunks en knowledge_chunks", c1 > 0)
        check("sync primera vez: 3 hashes guardados", nh == 3)

        # --- los chunks tienen source='obsidian' y el tenant correcto ---
        async with pool.tenant_connection(a) as conn:
            bad = (await (await conn.execute(
                "SELECT count(*) FROM knowledge_chunks "
                "WHERE source <> 'obsidian' OR tenant_id <> %s::uuid", (a,)
            )).fetchone())[0]
        check("chunks: source='obsidian' y tenant_id correcto", bad == 0)

        # --- sync idempotente: sin cambios, todo skipped ---
        s2 = await sync.sync(str(vault), a)
        check("sync idempotente: indexed=0, skipped=3",
              s2["indexed"] == 0 and s2["skipped"] == 3)

        # --- upsert no duplica: el conteo de chunks no creció ---
        c2 = await count_chunks(a)
        check("upsert: re-sync no duplica chunks", c2 == c1)

        # --- detecta cambio: modificar un .md re-indexa solo ese ---
        (vault / "nota1.md").write_text(
            "# Nota Uno\n\nContenido EDITADO sobre contratos.\n\n## Cláusulas\n\nNuevo detalle.\n",
            encoding="utf-8")
        s3 = await sync.sync(str(vault), a)
        check("sync detecta cambio: indexed=1, skipped=2",
              s3["indexed"] == 1 and s3["skipped"] == 2)

        # --- detecta borrado: quitar un .md borra sus chunks ---
        (vault / "nota2.md").unlink()
        s4 = await sync.sync(str(vault), a)
        async with pool.tenant_connection(a) as conn:
            left = (await (await conn.execute(
                "SELECT count(*) FROM knowledge_chunks WHERE source_path='nota2.md'"
            )).fetchone())[0]
        check("sync detecta borrado: deleted=1 y chunks eliminados",
              s4["deleted"] == 1 and left == 0)

        # --- aislamiento: B no ve ningún chunk de Obsidian de A ---
        cb = await count_chunks(b)
        check("aislamiento por tenant: B no ve los knowledge_chunks de A", cb == 0)

        # --- vault vacío: stats en cero, sin error (sobre B, que no tiene datos) ---
        s5 = await sync.sync(str(empty_vault), b)
        check("vault vacío: stats en cero sin error",
              s5 == {"indexed": 0, "skipped": 0, "deleted": 0, "errors": 0})
    finally:
        await pool.close_pool()


def main() -> int:
    print("== Módulo 3c · Obsidian indexer (knowledge_chunks) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env — necesario para la migración")
        return 1

    init_knowledge_stores.apply()   # idempotente: asegura las tablas (rol postgres)

    work = Path(tempfile.mkdtemp(prefix="obsidian_", dir=str(ROOT / ".tmp")))
    vault = work / "vault"
    empty_vault = work / "empty"
    empty_vault.mkdir(parents=True, exist_ok=True)
    build_vault(vault)

    a, b = make_tenants()
    try:
        offline_checks(vault)
        asyncio.run(db_checks(a, b, vault, empty_vault))
    finally:
        drop_tenants(a, b)
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Obsidian indexer OK — Módulo 3c verificado.")
        return 0
    print("Obsidian indexer FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
