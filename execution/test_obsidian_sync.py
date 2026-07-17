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
import init_obsidian_structure                     # noqa: E402  (runner de la migración 039)
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


def build_struct_vault(base: Path) -> None:
    """Vault REAL de estructura (039): documentos de Obsidian de todos los tipos que un
    despacho ya tiene — con frontmatter completo, sin frontmatter, con YAML roto, un índice
    lleno de enlaces y una nota con encabezados anidados."""
    base.mkdir(parents=True, exist_ok=True)

    # 1) Frontmatter completo + campos desconocidos + encabezados anidados (heading_path).
    (base / "criterio.md").write_text(
        "---\n"
        "title: Criterio de indemnización\n"
        "type: criterio\n"
        "status: verified\n"
        "fuente: Manual interno del despacho\n"
        "revisado: 2024-05-01\n"
        "tags: [contratos, clausulas]\n"
        "campo_que_nadie_conoce: valor raro\n"
        'relacionado_con: "[[Mapa de contratación]]"\n'
        "---\n"
        "# Criterio\n\nCuerpo del criterio verificado.\n\n"
        "## Detalle\n\nDetalle del criterio.\n\n"
        "### Excepción\n\nLa excepción al criterio.\n", encoding="utf-8")

    # 2) Índice/MOC: el documento más denso en señal del vault.
    (base / "Mapa de contratación.md").write_text(
        "---\n"
        "tipo: moc\n"
        "estado: verificado\n"
        "---\n"
        "# Mapa de contratación\n\n"
        "## Cláusulas\n\n"
        "- [[criterio]]\n"
        "- [[criterio|el criterio de siempre]]\n"
        "- [[carpeta/Nota Anidada#Sección]]\n"
        "- ![[diagrama.png]]\n"
        "- [[Nota Que No Existe]]\n"
        "- fundamenta:: [[criterio]]\n\n"
        "## Ejemplo de código\n\n"
        "```\n[[NoEsUnEnlace]]\n```\n", encoding="utf-8")

    # 3) Borrador declarado.
    (base / "borrador.md").write_text(
        "---\nestado: borrador\ntipo: nota\n---\n"
        "# Idea a medias\n\nEsto todavía no es criterio del despacho.\n", encoding="utf-8")

    # 4) YAML mal formado: no puede tumbar la sincronización del vault.
    (base / "roto.md").write_text(
        "---\n"
        "tipo: nota\n"
        "estado: [borrador\n"
        'sin cerrar: "comilla\n'
        "---\n"
        "# Nota rota\n\nEl cuerpo de esta nota se sigue indexando.\n", encoding="utf-8")

    # 5) Sin frontmatter: el vault que la mayoría de despachos ya tiene.
    (base / "plano.md").write_text(
        "# Nota plana\n\nTexto sin metadatos, como el 90% de los vaults.\n\n"
        "Enlaza a [[criterio]] sin decir por qué.\n", encoding="utf-8")

    # 6) Estado que no sabemos mapear: NO se adivina.
    (base / "raro.md").write_text(
        "---\nestado: en veremos\ntipo: apunte\n---\n"
        "# Apunte\n\nEstado no reconocido.\n", encoding="utf-8")


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


# ── 039 · estructura del vault (frontmatter + wikilinks), sin DB ─────────────
def _legacy_chunks(sync, content: str) -> list[tuple]:
    """Reimplementación del pipeline ANTERIOR a 039 (trocear el documento crudo, sin tocar el
    frontmatter). Es la vara de medir de la cero regresión: para un documento sin frontmatter,
    el indexador de hoy tiene que producir EXACTAMENTE esto."""
    out: list[tuple] = []
    pos = 0
    for heading_path, body in sync._split_by_headings(content):
        body = body.strip()
        if not body:
            continue
        for piece in sync._split_to_size(body):
            out.append((piece, heading_path or None, pos))
            pos += 1
    return out


def structure_checks(vault: Path) -> None:
    sync = ObsidianSync()
    read = lambda name: (vault / name).read_text(encoding="utf-8")  # noqa: E731

    # ── CERO REGRESIÓN: un vault sin frontmatter produce hoy los mismos chunks que antes ──
    for name in ("plano.md",):
        raw = read(name)
        got = [(c["text"], c["heading_path"], c["position"]) for c in sync._chunk_document(raw, name)]
        check(f"cero regresión: {name} (sin frontmatter) produce los MISMOS chunks que antes de 039",
              got == _legacy_chunks(sync, raw))
    doc_plano = "# Uno\n\ncuerpo de uno.\n\n## Dos\n\ncuerpo de dos.\n"
    ch = sync._chunk_document(doc_plano, "x.md")
    check("cero regresión: sin frontmatter → frontmatter {} y metadatos vacíos",
          all(c["frontmatter"] == {} and c["doc_status"] is None and c["doc_type"] is None
              for c in ch))
    big_body = "\n\n".join(f"Parrafo {i} con texto de relleno suficiente. " * 4 for i in range(20))
    check("cero regresión: el troceado por tamaño no cambió",
          [(c["text"], c["heading_path"], c["position"])
           for c in sync._chunk_document(f"# G\n\n{big_body}\n", "b.md")]
          == _legacy_chunks(sync, f"# G\n\n{big_body}\n"))

    # ── frontmatter completo ──
    crit = sync._chunk_document(read("criterio.md"), "criterio.md")
    fm = crit[0]["frontmatter"]
    check("frontmatter: el YAML deja de entrar como texto dentro del chunk",
          all("campo_que_nadie_conoce" not in c["text"] and not c["text"].startswith("---")
              for c in crit))
    check("frontmatter: se parsea a metadatos consultables",
          fm.get("title") == "Criterio de indemnización" and fm.get("type") == "criterio")
    check("frontmatter: campos desconocidos se conservan sin romper",
          fm.get("campo_que_nadie_conoce") == "valor raro")
    check("frontmatter: las fechas de YAML se guardan en ISO (JSON-safe)",
          fm.get("revisado") == "2024-05-01")
    check("frontmatter: las listas se conservan", fm.get("tags") == ["contratos", "clausulas"])
    check("frontmatter: se replica en TODOS los chunks del documento (filtrable por fila)",
          all(c["frontmatter"] == fm for c in crit))

    # ── heading_path INTACTO con frontmatter presente ──
    paths = [c["heading_path"] for c in crit]
    check("heading_path: la miga de pan sigue intacta con encabezados anidados",
          "Criterio" in paths and "Criterio > Detalle" in paths
          and "Criterio > Detalle > Excepción" in paths)

    # ── estado ──
    check("estado: 'verified' → 'verificado' (variante en inglés)",
          crit[0]["doc_status"] == "verificado")
    check("estado: 'borrador' → 'borrador'",
          sync._chunk_document(read("borrador.md"), "b.md")[0]["doc_status"] == "borrador")
    check("estado: variante de nombre 'estado' + valor 'verificado'",
          sync._chunk_document(read("Mapa de contratación.md"), "m.md")[0]["doc_status"] == "verificado")
    raro = sync._chunk_document(read("raro.md"), "raro.md")
    check("estado: un valor desconocido NO se adivina → None", raro[0]["doc_status"] is None)
    check("estado: el valor crudo desconocido sigue en frontmatter",
          raro[0]["frontmatter"].get("estado") == "en veremos")
    check("tipo: variante 'tipo' se normaliza a minúsculas", raro[0]["doc_type"] == "apunte")
    check("estado: variantes de nombre y forma (Estado / STATUS / Doc-Status)",
          sync._chunk_document("---\nEstado: Verificado\n---\n# A\n\nx\n", "a.md")[0]["doc_status"] == "verificado"
          and sync._chunk_document("---\nSTATUS: Draft\n---\n# A\n\nx\n", "a.md")[0]["doc_status"] == "borrador"
          and sync._chunk_document("---\nDoc-Status: evergreen\n---\n# A\n\nx\n", "a.md")[0]["doc_status"] == "verificado")

    # ── YAML mal formado: fail-soft por documento ──
    roto = sync._chunk_document(read("roto.md"), "roto.md")
    check("YAML roto: no lanza y el cuerpo se sigue indexando",
          len(roto) >= 1 and any("cuerpo de esta nota" in c["text"] for c in roto))
    check("YAML roto: degrada a texto plano (frontmatter {}, sin estado)",
          roto[0]["frontmatter"] == {} and roto[0]["doc_status"] is None)
    check("YAML roto: el documento queda EXACTAMENTE como antes de 039",
          [(c["text"], c["heading_path"], c["position"]) for c in roto]
          == _legacy_chunks(sync, read("roto.md")))

    # ── frontmatter que no es un mapa / delimitadores que no lo son ──
    lista = "---\n- uno\n- dos\n---\n# T\n\ncuerpo.\n"
    check("frontmatter que es una lista (YAML válido, no metadatos) → texto plano",
          sync._chunk_document(lista, "l.md")[0]["frontmatter"] == {})
    sin_cierre = "---\ntipo: nota\n# T\n\ncuerpo.\n"
    check("bloque '---' sin cerrar → NO es frontmatter, texto intacto",
          sync._chunk_document(sin_cierre, "s.md")[0]["frontmatter"] == {})
    regla = "# T\n\ncuerpo.\n\n---\n\notro párrafo.\n"
    check("una regla horizontal '---' a mitad del documento NO se confunde con frontmatter",
          sync._chunk_document(regla, "r.md")[0]["frontmatter"] == {}
          and [(c["text"], c["heading_path"], c["position"])
               for c in sync._chunk_document(regla, "r.md")] == _legacy_chunks(sync, regla))
    check("frontmatter vacío ('---\\n---') no rompe",
          sync._chunk_document("---\n---\n# T\n\ncuerpo.\n", "v.md")[0]["frontmatter"] == {})

    # ── wikilinks ──
    moc = sync._chunk_document(read("Mapa de contratación.md"), "moc.md")
    clausulas = next(c for c in moc if c["heading_path"] == "Mapa de contratación > Cláusulas")
    keys = [l["to_key"] for l in clausulas["links"]]
    check("wikilinks: el índice deja de ser un chunk de enlaces rotos", len(keys) >= 4)
    check("wikilinks: enlace simple [[criterio]]", "criterio" in keys)
    check("wikilinks: [[nota|alias]] → destino 'criterio' (el alias se descarta)",
          all("|" not in k for k in keys))
    check("wikilinks: [[nota#sección]] → la nota, sin la sección",
          any(l["to"] == "carpeta/Nota Anidada" and l["to_key"] == "nota anidada"
              for l in clausulas["links"]))
    check("wikilinks: un destino inexistente se conserva (el enlace roto es información)",
          "nota que no existe" in keys)
    check("wikilinks: ![[diagrama.png]] (adjunto) se ignora",
          not any("diagrama" in k for k in keys))
    check("wikilinks: motivo declarado con campo inline (fundamenta:: [[criterio]])",
          any(l["to_key"] == "criterio" and l["rel"] == "fundamenta" for l in clausulas["links"]))
    check("wikilinks: un enlace suelto NO inventa motivo (rel=None)",
          any(l["to_key"] == "criterio" and l["rel"] is None for l in clausulas["links"]))
    codigo = next((c for c in moc if "NoEsUnEnlace" in c["text"]), None)
    check("wikilinks: los [[enlaces]] dentro de un bloque de código se ignoran",
          codigo is not None and not any("noesunenlace" in l["to_key"] for l in codigo["links"]))
    check("wikilinks: los enlaces se guardan en el chunk donde APARECEN, no en todos",
          all(not c["links"] for c in moc if c["heading_path"] == "Mapa de contratación"))
    check("wikilinks: motivo declarado desde el frontmatter (relacionado_con) → primer chunk",
          any(l["to_key"] == "mapa de contratación" and l["rel"] == "relacionado_con"
              for l in crit[0]["links"]))
    check("wikilinks: un vault sin enlaces produce links=[] (cero regresión)",
          sync._chunk_document(doc_plano, "x.md")[0]["links"] == [])
    dup = "# T\n\n[[a]] y otra vez [[a]] y [[a|alias]].\n"
    check("wikilinks: sin repetidos (mismo destino, mismo motivo)",
          len(sync._chunk_document(dup, "d.md")[0]["links"]) == 1)


# ── checks que tocan DB (migración, RLS, sync incremental) ───────────────────
async def db_checks(a: str, b: str, vault: Path, empty_vault: Path, struct_vault: Path) -> None:
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

        # --- 039: estructura persistida (se usa B, que quedó vacío tras el check anterior) ---
        await struct_db_checks(a, b, struct_vault)
    finally:
        await pool.close_pool()


# ── 039 · estructura persistida en knowledge_chunks ──────────────────────────
async def struct_db_checks(a: str, b: str, struct_vault: Path) -> None:
    sync = ObsidianSync()

    # --- migración 039: columnas nuevas + restricción del vocabulario de estado ---
    async with pool.connection() as conn:
        cols = {r[0] for r in await (await conn.execute(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name='knowledge_chunks'"
        )).fetchall()}
    check("migración 039: knowledge_chunks tiene doc_status, doc_type, frontmatter y links",
          {"doc_status", "doc_type", "frontmatter", "links"}.issubset(cols))
    async with pool.connection() as conn:
        ck = (await (await conn.execute(
            "SELECT count(*) FROM pg_constraint WHERE conname='ck_knowledge_chunks_doc_status'"
        )).fetchone())[0]
    check("migración 039: el vocabulario de estado está restringido en la base", ck == 1)

    # --- sync del vault estructurado: 6 notas, la rota NO tumba la sincronización ---
    s = await sync.sync(str(struct_vault), b)
    check("vault estructurado: se indexan las 6 notas y la del YAML roto NO rompe el sync",
          s["indexed"] == 6 and s["errors"] == 0)

    async def rows(tenant: str, where: str, params: tuple = ()) -> list:
        async with pool.tenant_connection(tenant) as conn:
            return await (await conn.execute(
                f"SELECT source_path, doc_status, doc_type, frontmatter, links, content "
                f"FROM knowledge_chunks WHERE source='obsidian' AND {where}", params
            )).fetchall()

    # --- el estado queda disponible para filtrar ---
    verificados = {r[0] for r in await rows(b, "doc_status = 'verificado'")}
    borradores = {r[0] for r in await rows(b, "doc_status = 'borrador'")}
    check("estado en DB: la recuperación puede pedir SOLO lo verificado",
          verificados == {"criterio.md", "Mapa de contratación.md"})
    check("estado en DB: el borrador del despacho es distinguible del criterio verificado",
          borradores == {"borrador.md"} and not (verificados & borradores))
    sin_estado = {r[0] for r in await rows(b, "doc_status IS NULL")}
    check("estado en DB: lo que el vault no declara queda NULL (ni borrador ni verificado)",
          sin_estado == {"roto.md", "plano.md", "raro.md"})

    # --- el frontmatter dejó de ser basura textual dentro del chunk ---
    crit = await rows(b, "source_path = 'criterio.md'")
    check("frontmatter en DB: se guarda parseado y consultable",
          crit and crit[0][3].get("fuente") == "Manual interno del despacho")
    check("frontmatter en DB: el YAML ya no contamina el texto del chunk",
          all("campo_que_nadie_conoce" not in r[5] for r in crit))
    async with pool.tenant_connection(b) as conn:
        n_fm = (await (await conn.execute(
            "SELECT count(DISTINCT source_path) FROM knowledge_chunks "
            "WHERE source='obsidian' AND frontmatter @> '{\"tipo\": \"moc\"}'"
        )).fetchone())[0]
    check("frontmatter en DB: un campo NO normalizado sigue siendo consultable con @>", n_fm == 1)

    # --- backlinks sin tabla de grafo: quién enlaza a 'criterio' y por qué ---
    async with pool.tenant_connection(b) as conn:
        back = await (await conn.execute(
            "SELECT DISTINCT source_path FROM knowledge_chunks "
            "WHERE source='obsidian' AND links @> '[{\"to_key\": \"criterio\"}]' "
            "ORDER BY source_path"
        )).fetchall()
    check("enlaces en DB: los backlinks se consultan con links @> (sin tabla de grafo)",
          {r[0] for r in back} == {"Mapa de contratación.md", "plano.md"})
    async with pool.tenant_connection(b) as conn:
        motivo = await (await conn.execute(
            "SELECT DISTINCT source_path FROM knowledge_chunks WHERE source='obsidian' "
            "AND links @> '[{\"to_key\": \"criterio\", \"rel\": \"fundamenta\"}]'"
        )).fetchall()
    check("enlaces en DB: el MOTIVO del vínculo es consultable (rel='fundamenta')",
          {r[0] for r in motivo} == {"Mapa de contratación.md"})
    plano = await rows(b, "source_path = 'plano.md'")
    check("enlaces en DB: un vault sin frontmatter conserva sus enlaces y '{}' de metadatos",
          plano and plano[0][3] == {} and plano[0][4] and plano[0][4][0]["rel"] is None)

    # --- re-sync: un cambio de estado se refleja (el UPDATE también escribe estructura) ---
    (struct_vault / "borrador.md").write_text(
        "---\nestado: verificado\ntipo: nota\n---\n"
        "# Idea a medias\n\nEsto todavía no es criterio del despacho.\n", encoding="utf-8")
    s2 = await sync.sync(str(struct_vault), b)
    now = await rows(b, "source_path = 'borrador.md'")
    check("re-sync: borrador → verificado se refleja en la fila (no queda estado viejo)",
          s2["indexed"] == 1 and all(r[1] == "verificado" for r in now))

    # --- aislamiento: A (que tiene su propio vault) no ve NADA de la estructura de B ---
    async with pool.tenant_connection(a) as conn:
        leak = (await (await conn.execute(
            "SELECT count(*) FROM knowledge_chunks WHERE source='obsidian' "
            "AND (doc_status IS NOT NULL OR links <> '[]'::jsonb "
            "     OR frontmatter <> '{}'::jsonb)"
        )).fetchone())[0]
    check("RLS 039: A no ve el frontmatter, el estado ni los enlaces del vault de B", leak == 0)


def main() -> int:
    print("== Módulo 3c · Obsidian indexer (knowledge_chunks) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env — necesario para la migración")
        return 1

    init_knowledge_stores.apply()      # idempotente: asegura las tablas (rol postgres)
    init_obsidian_structure.apply()    # idempotente: migración 039 (estructura del vault)

    work = Path(tempfile.mkdtemp(prefix="obsidian_", dir=str(ROOT / ".tmp")))
    vault = work / "vault"
    empty_vault = work / "empty"
    empty_vault.mkdir(parents=True, exist_ok=True)
    build_vault(vault)
    struct_vault = work / "struct"
    build_struct_vault(struct_vault)

    a, b = make_tenants()
    try:
        offline_checks(vault)
        structure_checks(struct_vault)
        asyncio.run(db_checks(a, b, vault, empty_vault, struct_vault))
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
