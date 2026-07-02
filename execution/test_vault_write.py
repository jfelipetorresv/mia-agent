"""
Mia · test_vault_write.py — gate de CP-C2 (vault bidireccional · decisión #32).

Verifica que Mia escribe su memoria visible (conceptos y reportes) en el vault de
Obsidian SOLO bajo `{vault}/Mia/`, con frontmatter sin tenant, y que:
  (a) export_concept escribe bajo Mia/ con frontmatter válido (title/fecha/fuente: Mia);
  (b) los intentos de escape (nombre con `..`, vault fuera de la allowlist) se RECHAZAN;
      incluye {vault}/Mia como JUNCTION/symlink hacia fuera de la allowlist (mklink /J
      real; si el entorno no lo permite, se simula con monkeypatch de os.path.realpath)
      y los stems reservados de Windows (CON, COM1-9, ...) renombrados con sufijo;
  (c) roundtrip: una nota escrita por Mia la reindexa obsidian_sync → knowledge_chunks;
  (d) una nota preexistente del abogado NUNCA cambia (hash sha256 antes/después);
  (e) bootstrap crea Mia/conceptos, Mia/reportes y README en lenguaje llano;
  (f) si el vault falla, la wiki interna sigue funcionando (export con log, sin excepción);
  (g) is_installed()/install() no lanzan aunque winget no exista (mockeado).

Vault TEMPORAL bajo `.tmp/` agregado a la allowlist vía OBSIDIAN_VAULT_ALLOWLIST (env),
EMBEDDINGS MOCKEADOS (vectores aleatorios, mismo criterio que test_obsidian_sync) y LLM
falso (mismo criterio que test_wiki_manager). Limpia sus tenants y archivos al salir.

    .venv\\Scripts\\python.exe execution\\test_vault_write.py
"""
from __future__ import annotations

import asyncio
import hashlib
import os
import random
import shutil
import sys
import tempfile
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

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

import init_knowledge_stores                                  # noqa: E402
from mia import config, embeddings                            # noqa: E402
from mia.agent import llm                                     # noqa: E402
from mia.connectors import ObsidianSync, obsidian_install     # noqa: E402
from mia.connectors import vault_writer as vw                 # noqa: E402
from mia.connectors.vault_writer import VaultWriter           # noqa: E402
from mia.db import pool                                       # noqa: E402
from mia.memory.trace_capture import TraceCapture             # noqa: E402
from mia.memory.wiki_manager import WikiManager               # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks: embeddings sin red + LLM falso (sin API) ──────────────────────────
def _fake_embed(texts):
    return [[random.random() for _ in range(config.EMBED_DIM)] for _ in texts]


embeddings.embed_texts = _fake_embed


def fake_llm(messages, *, task=None, **kwargs):
    content = messages[-1]["content"]
    if "JSON array" in content:
        out = '["Concepto Vault"]'
    else:
        out = (
            "## Definicion (segun la practica de este despacho)\n"
            "Definicion desde evidencia aprobada.\n\n"
            "## Patrones identificados\n- Patron reutilizable.\n\n"
            "## Casos que lo soportan (referencias anonimas)\n- matter anonimo.\n\n"
            "## Conexiones con otros conceptos\n- [[Concepto Beta]]\n\n"
            "## Lo que NO funciona (aprendido de rechazos)\n- Pendiente.\n"
        )
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=out))])


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ── conexión admin (postgres) para el tenant de prueba ───────────────────────
PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def make_tenant() -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute("INSERT INTO tenants(name) VALUES('Vault CP-C2') RETURNING id").fetchone()[0])


def drop_tenant(tid: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id=%s::uuid", (tid,))


# ── checks sin DB: escritura, escapes, bootstrap, instalación ────────────────
def offline_checks(work: Path, vault: Path, lawyer_note: Path, lawyer_hash: str) -> None:
    writer = VaultWriter(vault)

    # (e) bootstrap crea la estructura mínima + README legible.
    created = writer.bootstrap_vault()
    readme = vault / "Mia" / "README.md"
    check("bootstrap crea Mia/conceptos y Mia/reportes",
          (vault / "Mia" / "conceptos").is_dir() and (vault / "Mia" / "reportes").is_dir())
    check("bootstrap crea README en lenguaje llano",
          readme.is_file() and "Mia" in readme.read_text(encoding="utf-8")
          and "tenant" not in readme.read_text(encoding="utf-8").lower())
    check("bootstrap reporta lo creado", len(created) == 3)
    check("bootstrap es idempotente (segunda pasada no crea nada)", writer.bootstrap_vault() == [])

    # (a) export_concept: SOLO bajo Mia/, frontmatter válido, backlinks conservados.
    body = "# Concepto Alfa\nTexto con backlink a [[Concepto Beta]].\n"
    target = writer.export_concept("tenant-x", "Concepto Alfa", body,
                                   metadata={"confidence": 0.42, "tenant_id": "SECRETO"})
    text = target.read_text(encoding="utf-8")
    check("export_concept escribe bajo Mia/conceptos/",
          target == (vault / "Mia" / "conceptos" / "concepto-alfa.md").resolve())
    check("export_concept escribe frontmatter title/fecha/fuente",
          text.startswith("---\n") and 'title: "Concepto Alfa"' in text
          and f"fecha: {date.today().isoformat()}" in text and "fuente: Mia" in text)
    check("export_concept conserva los backlinks [[...]]", "[[Concepto Beta]]" in text)
    check("privacidad: el frontmatter no incluye el tenant",
          "tenant" not in text.lower() and "SECRETO" not in text)
    check("frontmatter admite métricas inofensivas (confidence)", "confidence: 0.42" in text)

    # (b) export_report con fecha + slug.
    report = writer.export_report("tenant-x", "Resumen semanal", "Esta semana hubo 2 asuntos.")
    check("export_report escribe Mia/reportes/{fecha}-{slug}.md",
          report == (vault / "Mia" / "reportes" / f"{date.today().isoformat()}-resumen-semanal.md").resolve()
          and report.is_file())

    # (b) intentos de escape → rechazados con ValueError, sin escribir nada fuera.
    def rejected(fn) -> bool:
        try:
            fn()
            return False
        except ValueError:
            return True

    check("escape: nombre con '..' rechazado",
          rejected(lambda: writer.export_concept("t", "../fuera", "x")))
    check("escape: nombre con separador de ruta rechazado",
          rejected(lambda: writer.export_concept("t", "a/b", "x"))
          and rejected(lambda: writer.export_concept("t", "a\\b", "x")))
    check("escape: nombre vacío o solo raros rechazado",
          rejected(lambda: writer.export_concept("t", "  ", "x"))
          and rejected(lambda: writer.export_report("t", "%%%", "x")))
    outside = Path(tempfile.mkdtemp(prefix="vault_out_"))
    try:
        check("escape: vault fuera de la allowlist rechazado",
              rejected(lambda: VaultWriter(outside)))
    finally:
        shutil.rmtree(outside, ignore_errors=True)
    check("escape: nada quedó escrito fuera de Mia/",
          not (vault / "fuera.md").exists() and not (work / "fuera.md").exists())

    # FIX E (revisión CP-C2): stems reservados de Windows → renombrados con sufijo
    # (un "con.md"/"aux.md" en Windows apunta a un DISPOSITIVO, no a un archivo).
    reserved = writer.export_concept("t", "CON", "cuerpo de prueba")
    check("reservados Windows: 'CON' se exporta como con-nota.md",
          reserved.name == "con-nota.md" and reserved.is_file())
    check("reservados Windows: com3/LPT1/Nul sufijados (case-insensitive), resto intacto",
          vw._slugify("com3") == "com3-nota" and vw._slugify("LPT1") == "lpt1-nota"
          and vw._slugify("Nul") == "nul-nota" and vw._slugify("consola") == "consola")

    # (d) la nota del abogado no cambió con ninguna operación de escritura.
    check("nota del abogado intacta tras bootstrap+exports", _sha(lawyer_note) == lawyer_hash)

    # (g) instalación guiada: nunca lanza aunque winget no exista.
    real_run = obsidian_install.subprocess.run
    real_local = os.environ.get("LOCALAPPDATA")

    def no_winget(*args, **kwargs):
        raise FileNotFoundError("winget no existe")

    try:
        obsidian_install.subprocess.run = no_winget
        os.environ["LOCALAPPDATA"] = str(work / "appdata_vacio")
        check("is_installed() no lanza sin winget (devuelve False)",
              obsidian_install.is_installed() is False)
        ok, msg = obsidian_install.install()
        check("install() sin winget devuelve (False, mensaje llano)",
              ok is False and isinstance(msg, str) and "obsidian" in msg.lower())

        def fake_ok(cmd, **kwargs):
            assert isinstance(cmd, list) and cmd[0] == "winget"  # lista de args, sin shell
            listing = "Obsidian.Obsidian" if cmd[1] == "list" else ""
            return SimpleNamespace(returncode=0, stdout=listing, stderr="")

        obsidian_install.subprocess.run = fake_ok
        check("is_installed() detecta vía winget list (mock)", obsidian_install.is_installed() is True)
        ok2, msg2 = obsidian_install.install()
        check("install() con Obsidian presente responde ok y en llano",
              ok2 is True and "instalado" in msg2.lower())
    finally:
        obsidian_install.subprocess.run = real_run
        if real_local is None:
            os.environ.pop("LOCALAPPDATA", None)
        else:
            os.environ["LOCALAPPDATA"] = real_local

    # Integraciones presentes (revisión de fuente, como en test_wiki_manager).
    wiki_src = (ROOT / "backend" / "mia" / "memory" / "wiki_manager.py").read_text(encoding="utf-8")
    dreams_src = (ROOT / "backend" / "mia" / "memory" / "dreams.py").read_text(encoding="utf-8")
    main_src = (ROOT / "backend" / "mia" / "api" / "main.py").read_text(encoding="utf-8")
    check("wiki_manager espeja conceptos al vault (try/except con log)",
          "_mirror_concept_to_vault" in wiki_src and "logger.warning" in wiki_src)
    check("dreams espeja el reporte semanal al vault (try/except con log)",
          "_mirror_report_to_vault" in dreams_src and "export_report" in dreams_src)
    check("la API monta /api/obsidian/*", "obsidian_router" in main_src)


# ── FIX D (revisión CP-C2): {vault}/Mia como junction/symlink → RECHAZADO ────
def junction_checks(work: Path) -> None:
    """Reproduce el hallazgo del revisor: `mklink /J {vault}/Mia {fuera_allowlist}`.
    Si el entorno no permite crear el junction, se SIMULA con monkeypatch de
    os.path.realpath (mismo camino de código; anotado en el nombre del check)."""
    import subprocess

    def rejected(fn) -> bool:
        try:
            fn()
            return False
        except ValueError:
            return True

    vault_j = work / "vault_junction"
    vault_j.mkdir(parents=True, exist_ok=True)
    outside = Path(tempfile.mkdtemp(prefix="vault_escape_"))  # FUERA de la allowlist
    link = vault_j / "Mia"
    created = False
    if os.name == "nt":
        try:
            r = subprocess.run(["cmd", "/c", "mklink", "/J", str(link), str(outside)],
                               capture_output=True, text=True, timeout=30)
            created = r.returncode == 0 and link.exists()
        except Exception:
            created = False
    try:
        if created:
            writer = VaultWriter(vault_j)
            check("junction REAL (mklink /J): export_concept rechazado (ValueError)",
                  rejected(lambda: writer.export_concept("t", "escape-junction", "x")))
            check("junction REAL: export_report y bootstrap también rechazados",
                  rejected(lambda: writer.export_report("t", "escape", "x"))
                  and rejected(writer.bootstrap_vault))
            check("junction REAL: nada quedó escrito fuera de la allowlist",
                  not any(outside.iterdir()))
        else:
            # ANOTADO: no se pudo crear el junction en este entorno — se simula el
            # reparse point parcheando os.path.realpath para que {vault}/Mia
            # "apunte" fuera de la allowlist (mismo camino de código del rechazo).
            real_realpath = os.path.realpath

            def fake_realpath(p, *a, **k):
                if Path(p) == link:
                    return str(outside)
                return real_realpath(p, *a, **k)

            vw.os.path.realpath = fake_realpath
            try:
                writer = VaultWriter(vault_j)
                check("junction SIMULADO (monkeypatch realpath): export rechazado",
                      rejected(lambda: writer.export_concept("t", "escape-junction", "x")))
                check("junction SIMULADO: export_report y bootstrap también rechazados",
                      rejected(lambda: writer.export_report("t", "escape", "x"))
                      and rejected(writer.bootstrap_vault))
                check("junction SIMULADO: nada quedó escrito fuera",
                      not any(outside.iterdir()))
            finally:
                vw.os.path.realpath = real_realpath
    finally:
        if created:
            try:
                os.rmdir(link)   # borra el junction, no el destino
            except OSError:
                pass
        shutil.rmtree(outside, ignore_errors=True)


# ── (f) vault caído: la wiki interna sigue funcionando ───────────────────────
async def broken_vault_check(tmp: Path) -> None:
    async def kaboom(tenant_id):
        raise RuntimeError("vault caído / disco desconectado")

    original = vw.tenant_vault_writer
    original_llm = llm.call_llm
    vw.tenant_vault_writer = kaboom
    llm.call_llm = fake_llm
    try:
        mgr = WikiManager(home=tmp, trace_capture=TraceCapture(tmp / "traces"))
        content = await mgr.compile_concept("tenant-caido", "Concepto Resiliente", ["evidencia"])
        internal = mgr.concept_path("tenant-caido", "Concepto Resiliente")
        check("vault caído: compile_concept NO lanza y la wiki interna queda escrita",
              internal.exists() and "confidence:" in content)
    except Exception:
        check("vault caído: compile_concept NO lanza y la wiki interna queda escrita", False)
    finally:
        vw.tenant_vault_writer = original
        llm.call_llm = original_llm


# ── (c) roundtrip con DB: Mia escribe → obsidian_sync reindexa ───────────────
async def db_checks(tenant: str, vault: Path, lawyer_note: Path, lawyer_hash: str, tmp: Path) -> None:
    await pool.open_pool()
    original_llm = llm.call_llm
    llm.call_llm = fake_llm
    try:
        # registro del vault del tenant (mismo mecanismo que el sync de lectura).
        await vw.register_tenant_vault(tenant, str(vault))
        stored = await vw.get_tenant_vault_path(tenant)
        check("register/get del vault del tenant (tenant_settings)", stored == str(vault))

        # la wiki interna compila y ESPEJA al vault (cadena completa vía DB).
        mgr = WikiManager(home=tmp, trace_capture=TraceCapture(tmp / "traces"))
        await mgr.compile_concept(tenant, "Concepto Vault", ["Evidencia aprobada"])
        mirrored = vault / "Mia" / "conceptos" / "concepto-vault.md"
        check("compile_concept espeja el concepto en el vault del tenant",
              mirrored.is_file() and "fuente: Mia" in mirrored.read_text(encoding="utf-8"))
        check("la wiki interna sigue siendo la fuente de verdad (archivo interno existe)",
              mgr.concept_path(tenant, "Concepto Vault").exists())

        # roundtrip: obsidian_sync reindexa la nota de Mia → knowledge_chunks.
        stats = await ObsidianSync().sync(str(vault), tenant)
        async with pool.tenant_connection(tenant) as conn:
            n = (await (await conn.execute(
                "SELECT count(*) FROM knowledge_chunks WHERE source='obsidian' "
                "AND source_path LIKE 'Mia/conceptos/%'"
            )).fetchone())[0]
        check("roundtrip: la nota de Mia aparece en knowledge_chunks",
              stats["errors"] == 0 and n > 0)

        # (d) el sync solo LEE: la nota del abogado sigue byte a byte igual.
        check("nota del abogado intacta tras el sync", _sha(lawyer_note) == lawyer_hash)
    finally:
        llm.call_llm = original_llm
        await pool.close_pool()


def main() -> int:
    print("== CP-C2 · Vault bidireccional (VaultWriter + roundtrip) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env — necesario para el roundtrip")
        return 1

    init_knowledge_stores.apply()   # idempotente: asegura knowledge_chunks/hashes

    (ROOT / ".tmp").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="vault_write_", dir=str(ROOT / ".tmp")))
    vault = work / "vault"
    vault.mkdir(parents=True, exist_ok=True)

    # nota preexistente del abogado (fuera de Mia/): jamás debe cambiar.
    lawyer_note = vault / "nota_del_abogado.md"
    lawyer_note.write_text("# Mi nota\n\nApuntes personales del abogado.\n", encoding="utf-8")
    lawyer_hash = _sha(lawyer_note)

    original_allow = os.environ.get("OBSIDIAN_VAULT_ALLOWLIST")
    os.environ["OBSIDIAN_VAULT_ALLOWLIST"] = str(work)
    tenant = make_tenant()
    try:
        offline_checks(work, vault, lawyer_note, lawyer_hash)
        junction_checks(work)
        asyncio.run(broken_vault_check(work / "wiki_home_caido"))
        asyncio.run(db_checks(tenant, vault, lawyer_note, lawyer_hash, work / "wiki_home"))
    finally:
        drop_tenant(tenant)
        if original_allow is None:
            os.environ.pop("OBSIDIAN_VAULT_ALLOWLIST", None)
        else:
            os.environ["OBSIDIAN_VAULT_ALLOWLIST"] = original_allow
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Vault bidireccional OK — CP-C2 verificado.")
        return 0
    print("Vault bidireccional FAIL — no avanzar con la siguiente tarea.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
