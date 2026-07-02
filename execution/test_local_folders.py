"""
Mia · test_local_folders.py — gate de CP-C1 (carpetas de trabajo · decisión #30).

Ejercita el conector de carpetas locales/nubes espejo (connectors/local_folders) contra la
DB real (migración 016), con carpetas de prueba TEMPORALES bajo `.tmp/` (NUNCA las carpetas
reales del usuario). Cubre: migración + RLS de las 2 tablas, allowlist fail-closed de dos
capas (registro y sync), escaneo con exclusiones y límites, sync incremental por hash
(primera vez / idempotente / cambio / borrado), PDF/Word vía extract_text (mockeado),
aislamiento por tenant, detección de nubes espejo y registro del job en el scheduler.
Refuerzos post-revisión: exclusión de subcarpetas de sistema (AppData/ProgramData) en el
descenso del scan, ventana MAX_FILES_PER_SYNC sin pérdida de conocimiento (diferidos se
retoman, sin poda indebida) y UNIQUE (tenant_id, path, kind) en local_folder_sources.

EMBEDDINGS MOCKEADOS: vectores aleatorios de 1024 floats (mismo criterio que
test_obsidian_sync — el gate corre offline y sin gastar API). extract_text también se
mockea para PDF/Word: se prueba el flujo, no PyMuPDF/python-docx.

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_local_folders.py
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

import init_local_folders                              # noqa: E402  (runner de la migración 016)
from mia import config, embeddings                     # noqa: E402
from mia.db import pool                                # noqa: E402
from mia.connectors import local_folders as lf         # noqa: E402
from mia.connectors.local_folders import (             # noqa: E402
    LocalFolderSync,
    detect_cloud_folders,
    disable_source,
    list_sources,
    register_source,
    validate_source_path,
)
from mia.cron import build_scheduler                   # noqa: E402

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
        a = c.execute("INSERT INTO tenants(name) VALUES('A test cpc1') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test cpc1') RETURNING id").fetchone()[0]
    return str(a), str(b)


def drop_tenants(a: str, b: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([a, b],))


def _rechaza(path) -> bool:
    """True si validate_source_path RECHAZA la ruta (fail-closed)."""
    try:
        validate_source_path(str(path))
        return False
    except ValueError:
        return True


# ── checks que NO tocan DB (allowlist, escaneo, límites, nubes, scheduler) ───
def offline_checks(work: Path) -> None:
    docs = work / "docs_offline"
    docs.mkdir(parents=True, exist_ok=True)
    (docs / "nota.md").write_text("# Nota\n\ncontenido.", encoding="utf-8")

    # --- allowlist capa 1: registro ---
    check("allowlist: carpeta válida es aceptada y devuelta resuelta",
          validate_source_path(str(docs)) == docs.resolve())
    check("allowlist: ruta inexistente rechazada", _rechaza(work / "no_existe_xyz"))
    check("allowlist: raíz de unidad rechazada", _rechaza(Path(ROOT.anchor)))
    sysroot = os.environ.get("SystemRoot", r"C:\Windows")
    check("allowlist: directorio de sistema (Windows) rechazado",
          _rechaza(sysroot) if Path(sysroot).exists() else True)
    fake_win = work / "Windows" / "sub"
    fake_win.mkdir(parents=True, exist_ok=True)
    check("allowlist: cualquier ruta con segmento de sistema rechazada", _rechaza(fake_win))
    check("allowlist: un archivo (no carpeta) rechazado", _rechaza(docs / "nota.md"))

    # --- allowlist capa 2: un archivo cuya ruta REAL apunta fuera se omite ---
    sync = LocalFolderSync()
    root = docs.resolve()
    fuera = (work / "fuera.txt")
    fuera.write_text("secreto fuera de la carpeta registrada", encoding="utf-8")
    check("allowlist capa 2: ruta real fuera de la registrada NO pasa el guard",
          not sync._resolves_inside(root, fuera.resolve()))
    check("allowlist capa 2: archivo dentro de la registrada SÍ pasa el guard",
          sync._resolves_inside(root, (docs / "nota.md")))

    # --- escaneo: exclusiones de ocultos/sistema y sufijos ---
    scan_dir = work / "scan"
    for d in (".oculta", "~temp", "node_modules", "__pycache__", "visible"):
        (scan_dir / d).mkdir(parents=True, exist_ok=True)
        (scan_dir / d / "x.md").write_text("# x\n\ncuerpo", encoding="utf-8")
    (scan_dir / "raiz.txt").write_text("texto", encoding="utf-8")
    (scan_dir / "binario.exe").write_bytes(b"\x00\x01")
    (scan_dir / "~lock.md").write_text("lock", encoding="utf-8")
    files, _, _ = sync._scan_folder(scan_dir.resolve())
    rels = {f.relative_to(scan_dir.resolve()).as_posix() for f in files}
    check("scan: excluye .oculta/, ~temp/, node_modules/ y __pycache__/",
          rels == {"visible/x.md", "raiz.txt"})

    # --- FIX 1 (privacidad): subcarpetas de SISTEMA se excluyen en el descenso ---
    # Registrar C:\Users\<usuario> pasa la validación de raíz; el scan NO debe entrar
    # a AppData/ProgramData (case-insensitive) y mandar credenciales a embeddings.
    appdata = scan_dir / "AppData" / "Roaming"
    appdata.mkdir(parents=True, exist_ok=True)
    (appdata / "credenciales.txt").write_text("token=secreto-no-indexar", encoding="utf-8")
    (scan_dir / "programdata").mkdir(exist_ok=True)
    (scan_dir / "programdata" / "config.txt").write_text("cfg", encoding="utf-8")
    files_sys, _, _ = sync._scan_folder(scan_dir.resolve())
    rels_sys = {f.relative_to(scan_dir.resolve()).as_posix() for f in files_sys}
    check("privacidad: subcarpetas de sistema (AppData/programdata) dentro de una "
          "fuente NO se indexan (case-insensitive)",
          rels_sys == {"visible/x.md", "raiz.txt"})

    # --- límite defensivo: archivo demasiado grande se omite ---
    big_dir = work / "big"
    big_dir.mkdir(exist_ok=True)
    (big_dir / "grande.txt").write_text("x" * 100, encoding="utf-8")
    (big_dir / "chico.txt").write_text("y" * 5, encoding="utf-8")
    orig_max = lf.MAX_FILE_BYTES
    try:
        lf.MAX_FILE_BYTES = 10
        bfiles, bomitted, _ = sync._scan_folder(big_dir.resolve())
    finally:
        lf.MAX_FILE_BYTES = orig_max
    check("límite: archivo que supera el tamaño máximo se omite con conteo",
          len(bfiles) == 1 and bomitted == 1 and bfiles[0].name == "chico.txt")

    # --- detección de nubes espejo (solo las que existen) ---
    home_fake = work / "home"
    home_fake.mkdir(exist_ok=True)
    onedrive = work / "cloud" / "OneDrive"
    onedrive.mkdir(parents=True, exist_ok=True)
    gdrive_root = work / "gdrive"
    (gdrive_root / "My Drive").mkdir(parents=True, exist_ok=True)
    orig_env = os.environ.get("OneDrive")
    try:
        os.environ["OneDrive"] = str(onedrive)
        found = detect_cloud_folders(home=home_fake, drive_roots=[gdrive_root])
        labels = {f["label"]: f["path"] for f in found}
        check("nubes: OneDrive existente detectado con etiqueta amable",
              labels.get("Tu OneDrive") == str(onedrive))
        check("nubes: Google Drive ('My Drive' en la unidad) detectado",
              labels.get("Tu Google Drive") == str(gdrive_root / "My Drive"))

        os.environ["OneDrive"] = str(work / "no_existe_onedrive")
        found2 = detect_cloud_folders(home=home_fake, drive_roots=[])
        check("nubes: solo se devuelven rutas que EXISTEN", found2 == [])

        (home_fake / "Google Drive").mkdir(exist_ok=True)
        found3 = detect_cloud_folders(home=home_fake, drive_roots=[])
        check("nubes: carpeta espejo 'Google Drive' del home detectada",
              any(f["label"] == "Tu Google Drive" for f in found3))
    finally:
        if orig_env is None:
            os.environ.pop("OneDrive", None)
        else:
            os.environ["OneDrive"] = orig_env

    # --- scheduler: el job diario está registrado junto al de Obsidian ---
    jobs = {j["name"]: j for j in build_scheduler().list_jobs()}
    check("scheduler: sync_local_folders_all_tenants registrado (diario)",
          "sync_local_folders_all_tenants" in jobs
          and jobs["sync_local_folders_all_tenants"]["interval_hours"] == 24)


# ── checks que tocan DB (migración, RLS, registro, sync incremental) ─────────
async def db_checks(a: str, b: str, work: Path) -> None:
    await pool.open_pool()
    try:
        sync = LocalFolderSync()

        # --- migración: las 2 tablas con columnas clave ---
        async with pool.connection() as conn:
            cols_src = {r[0] for r in await (await conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='local_folder_sources'"
            )).fetchall()}
            cols_h = {r[0] for r in await (await conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='local_file_hashes'"
            )).fetchall()}
        check("migración: local_folder_sources con columnas clave",
              {"id", "tenant_id", "path", "label", "kind", "enabled"}.issubset(cols_src))
        check("migración: local_file_hashes con columnas clave",
              {"tenant_id", "source_id", "file_path", "content_hash"}.issubset(cols_h))

        # --- registrar carpeta válida → fila con tenant correcto ---
        docs = work / "docs_db"
        docs.mkdir(parents=True, exist_ok=True)
        (docs / "nota.md").write_text(
            "# Contratos\n\nCláusulas de indemnización del despacho.\n", encoding="utf-8")
        (docs / "apunte.txt").write_text(
            "Apunte sobre responsabilidad civil y seguros.", encoding="utf-8")

        src = await register_source(a, str(docs), label="Carpeta de prueba")
        async with pool.tenant_connection(a) as conn:
            row = await (await conn.execute(
                "SELECT tenant_id, path, enabled FROM local_folder_sources WHERE id=%s::uuid",
                (src["id"],),
            )).fetchone()
        check("registro: fila creada con tenant correcto y ruta resuelta",
              row is not None and str(row[0]) == a
              and row[1] == str(docs.resolve()) and row[2] is True)

        # --- registro fail-closed también en la capa async ---
        rejected = False
        try:
            await register_source(a, str(Path(ROOT.anchor)))
        except ValueError:
            rejected = True
        check("registro: raíz de unidad rechazada también al registrar", rejected)

        # --- re-registrar la misma ruta no duplica (re-habilita) ---
        src_again = await register_source(a, str(docs))
        srcs_a = await list_sources(a)
        check("registro: re-registrar la misma ruta re-usa la fila (sin duplicados)",
              src_again["id"] == src["id"] and len(srcs_a) == 1)

        # --- FIX 3: UNIQUE (tenant_id, path, kind) a nivel de DB ---
        async with pool.connection() as conn:
            uq = (await (await conn.execute(
                "SELECT count(*) FROM pg_constraint "
                "WHERE conname='uq_local_folder_sources_tenant_path_kind' "
                "AND conrelid='public.local_folder_sources'::regclass AND contype='u'"
            )).fetchone())[0]
        async with pool.tenant_connection(a) as conn:
            n_rows = (await (await conn.execute(
                "SELECT count(*) FROM local_folder_sources WHERE path=%s AND kind='knowledge'",
                (str(docs.resolve()),),
            )).fetchone())[0]
        check("migración: UNIQUE (tenant_id, path, kind) vigente y una sola fila tras "
              "doble registro", uq == 1 and n_rows == 1)

        # --- RLS: B no ve las fuentes de A ---
        check("RLS local_folder_sources: B no ve las fuentes de A",
              await list_sources(b) == [])

        db_source = lf.SOURCE_PREFIX + src["id"]

        async def count_chunks(tenant: str, where_path: str | None = None) -> int:
            async with pool.tenant_connection(tenant) as conn:
                if where_path:
                    q = ("SELECT count(*) FROM knowledge_chunks WHERE source=%s AND source_path=%s")
                    args = (db_source, where_path)
                else:
                    q = "SELECT count(*) FROM knowledge_chunks WHERE source LIKE 'local:%%'"
                    args = ()
                return (await (await conn.execute(q, args)).fetchone())[0]

        async def count_hashes(tenant: str) -> int:
            async with pool.tenant_connection(tenant) as conn:
                return (await (await conn.execute(
                    "SELECT count(*) FROM local_file_hashes WHERE source_id=%s::uuid",
                    (src["id"],),
                )).fetchone())[0]

        # --- sync primera vez: 2 archivos → chunks + hashes ---
        s1 = await sync.sync_tenant(a)
        check("sync primera vez: 1 fuente, indexed=2, skipped=0, errors=0",
              s1["sources"] == 1 and s1["indexed"] == 2
              and s1["skipped"] == 0 and s1["errors"] == 0)
        check("sync primera vez: hay chunks con source 'local:<id>' (distinto de Obsidian)",
              await count_chunks(a) > 0)
        check("sync primera vez: 2 hashes guardados", await count_hashes(a) == 2)

        # --- idempotente: sin cambios, 0 procesados ---
        s2 = await sync.sync_tenant(a)
        c_after = await count_chunks(a)
        check("sync idempotente: indexed=0, skipped=2 (hash incremental)",
              s2["indexed"] == 0 and s2["skipped"] == 2)

        # --- modificar 1 → solo ese se reprocesa ---
        (docs / "apunte.txt").write_text(
            "Apunte EDITADO sobre responsabilidad y pólizas.", encoding="utf-8")
        s3 = await sync.sync_tenant(a)
        check("sync detecta cambio: indexed=1, skipped=1",
              s3["indexed"] == 1 and s3["skipped"] == 1)
        check("upsert: re-sync no duplica chunks", await count_chunks(a) == c_after)

        # --- borrar 1 → sus chunks desaparecen ---
        (docs / "nota.md").unlink()
        s4 = await sync.sync_tenant(a)
        check("sync detecta borrado: deleted=1 y chunks del archivo eliminados",
              s4["deleted"] == 1 and await count_chunks(a, "nota.md") == 0)
        check("hashes en espejo: queda 1 hash tras el borrado", await count_hashes(a) == 1)

        # --- PDF y Word pasan por extract_text (mockeado) ---
        (docs / "escrito.pdf").write_bytes(b"%PDF-fake bytes de prueba")
        (docs / "memo.docx").write_bytes(b"PK-fake docx de prueba")
        seen: list[str] = []
        orig_extract = lf.extract_text

        def fake_extract(filename: str, data: bytes) -> str:
            seen.append(filename)
            return f"Texto extraído de {filename} para el gate."

        lf.extract_text = fake_extract
        try:
            s5 = await sync.sync_tenant(a)
        finally:
            lf.extract_text = orig_extract
        async with pool.tenant_connection(a) as conn:
            pdf_txt = await (await conn.execute(
                "SELECT content FROM knowledge_chunks WHERE source=%s AND source_path='escrito.pdf'",
                (db_source,),
            )).fetchone()
        check("PDF/Word: ambos pasan por extract_text y quedan indexados",
              s5["indexed"] == 2 and sorted(seen) == ["escrito.pdf", "memo.docx"]
              and pdf_txt is not None and "escrito.pdf" in pdf_txt[0])

        # --- allowlist capa 2 en vivo: symlink que escapa se omite (si el SO lo permite) ---
        fuera = work / "secreto_fuera.txt"
        fuera.write_text("dato fuera de la allowlist", encoding="utf-8")
        try:
            os.symlink(fuera, docs / "enlace.txt")
            s6 = await sync.sync_tenant(a)
            check("allowlist capa 2 (symlink real): el enlace que escapa se omite sin indexar",
                  s6["omitted"] >= 1 and await count_chunks(a, "enlace.txt") == 0)
            (docs / "enlace.txt").unlink()
        except (OSError, NotImplementedError):
            print("  [INFO] symlinks no disponibles sin privilegios — guard ya cubierto offline")

        # --- FIX 2: ventana por sync SIN pérdida de conocimiento ---
        # Con MAX_FILES_PER_SYNC=2 y 3 archivos NUEVOS: se indexan 2, el tercero queda
        # diferido (deferred=1, NO indexado aún) y los chunks de un archivo previamente
        # indexado que SIGUE existiendo (apunte.txt) NO se borran. La corrida siguiente
        # retoma el diferido sola.
        for i in (1, 2, 3):
            (docs / f"nuevo{i}.txt").write_text(
                f"documento nuevo número {i} para probar la ventana por sincronización.",
                encoding="utf-8")
        orig_limit = lf.MAX_FILES_PER_SYNC
        try:
            lf.MAX_FILES_PER_SYNC = 2
            s8 = await sync.sync_tenant(a)
        finally:
            lf.MAX_FILES_PER_SYNC = orig_limit
        check("ventana por sync: indexa 2 nuevos, difiere 1 con warning y deleted=0",
              s8["indexed"] == 2 and s8["deferred"] == 1 and s8["deleted"] == 0)
        check("ventana por sync: el diferido aún NO está indexado y los chunks del "
              "archivo previamente indexado que sigue existiendo NO se borran",
              await count_chunks(a, "nuevo3.txt") == 0
              and await count_chunks(a, "apunte.txt") > 0)
        s9 = await sync.sync_tenant(a)
        check("ventana por sync: la corrida siguiente indexa el diferido (nada se pierde)",
              s9["indexed"] == 1 and s9["deferred"] == 0
              and await count_chunks(a, "nuevo3.txt") > 0)

        # --- RLS: B no ve chunks ni hashes de A ---
        check("RLS knowledge_chunks: B no ve los chunks de carpetas de A",
              await count_chunks(b) == 0)
        check("RLS local_file_hashes: B no ve los hashes de A", await count_hashes(b) == 0)

        # --- deshabilitar: borra conocimiento y saca la fuente del sync ---
        ok = await disable_source(a, src["id"])
        s7 = await sync.sync_tenant(a)
        check("deshabilitar: fuente fuera del sync y su conocimiento borrado",
              ok and s7["sources"] == 0 and await count_chunks(a) == 0
              and await count_hashes(a) == 0)
        check("deshabilitar: id ajeno/inexistente devuelve False (nunca datos de otro)",
              (await disable_source(b, src["id"])) is False)
    finally:
        await pool.close_pool()


def main() -> int:
    print("== CP-C1 · Carpetas de trabajo (local_folder_sources + knowledge_chunks) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env — necesario para la migración")
        return 1

    init_local_folders.apply()   # idempotente: asegura las tablas (rol postgres)

    (ROOT / ".tmp").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="localfolders_", dir=str(ROOT / ".tmp")))

    a, b = make_tenants()
    try:
        offline_checks(work)
        asyncio.run(db_checks(a, b, work))
    finally:
        drop_tenants(a, b)
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Carpetas de trabajo OK — CP-C1 verificado.")
        return 0
    print("Carpetas de trabajo FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
