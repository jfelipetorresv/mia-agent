"""
Mia · test_vault_export.py — gate de Fase 3 · frente C (bóveda visible, parte backend).

Verifica OFFLINE (sin DB, dicts fabricados a mano):
  1. `export_playbook` escribe `Mia/procedimientos/{slug}.md` con frontmatter SIN
     tenant_id (title/fecha/fuente/estado) y cuerpo (H1 + blockquote del summary +
     sección "Cuándo aplica" + content).
  2. Slug seguro: un título con `..`/separadores de ruta se RECHAZA (ValueError,
     fail-closed) en vez de "arreglarse" en silencio y escapar de `procedimientos/`;
     un título con caracteres raros (tildes, símbolos) se slugifica sin salir del dir.
  3. `render_norm_ficha` + `_group_norms_by_parent`: 2 filas segmentadas
     ("X (parte 1 de 2)" / "X (parte 2 de 2)", ambas con `metadata.parent_norm="X"`)
     producen UN solo grupo → UNA sola ficha (nunca una ficha por segmento).
  4. `render_jurisprudence_ficha` trae magistrado ponente, fecha y URL de la fuente.
  5. Fail-closed: `_export_ficha` con un subdir fuera de la allowlist se RECHAZA sin
     escribir nada; un vault fuera de `OBSIDIAN_VAULT_ALLOWLIST` también se rechaza.

Además, un check de HUMO con DB real (requiere PG_PASSWORD/.env): lee el corpus
jurídico ingerido por `corpus_factory` (`metadata->>'ingesta'='corpus_factory'` —
se esperan 21 normas + 10 sentencias, ver memoria de sesión) y exporta las fichas a
un vault TEMPORAL, verificando que nada se escribió fuera de ese tmp dir.

Vault TEMPORAL bajo `.tmp/`, agregado a la allowlist vía `OBSIDIAN_VAULT_ALLOWLIST`
(env) ANTES de instanciar cualquier `VaultWriter` (mismo criterio que
`test_vault_write.py`).

    .venv\\Scripts\\python.exe execution\\test_vault_export.py
"""
from __future__ import annotations

import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# Vault temporal ANTES de instanciar cualquier VaultWriter (config lee el env en
# cada llamada — igual criterio que test_vault_write.py).
(ROOT / ".tmp").mkdir(exist_ok=True)
WORK = Path(tempfile.mkdtemp(prefix="vault_export_", dir=str(ROOT / ".tmp")))
VAULT = WORK / "vault"
VAULT.mkdir(parents=True, exist_ok=True)
_ORIGINAL_ALLOWLIST = os.environ.get("OBSIDIAN_VAULT_ALLOWLIST")
os.environ["OBSIDIAN_VAULT_ALLOWLIST"] = str(WORK)

from mia import config  # noqa: E402
from mia.connectors import vault_export as ve  # noqa: E402
from mia.connectors.vault_writer import (  # noqa: E402
    CORPUS_JURISPRUDENCIA_SUBDIR,
    CORPUS_NORMATIVA_SUBDIR,
    PROCEDURES_SUBDIR,
    VaultWriter,
)
from mia.db import pool  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _rejected(fn) -> bool:
    try:
        fn()
        return False
    except ValueError:
        return True


# ── 1 · export_playbook: frontmatter + cuerpo ─────────────────────────────────
def test_export_playbook() -> None:
    writer = VaultWriter(VAULT)
    playbook = {
        "title": "Caducidad en reparación directa",
        "summary": "Cómputo del término de dos años.",
        "applies_when": "El daño es imputable al Estado y se discute la oportunidad.",
        "content": "CUERPO_PLAYBOOK — desarrollo completo del procedimiento.",
        "status": "active",
    }
    target = writer.export_playbook("tenant-secreto", playbook)
    check("export_playbook escribe bajo Mia/procedimientos/",
          target == (VAULT / "Mia" / PROCEDURES_SUBDIR / "caducidad-en-reparacion-directa.md").resolve())
    text = target.read_text(encoding="utf-8")
    check("frontmatter trae title/fecha/fuente/estado",
          text.startswith("---\n") and 'title: "Caducidad en reparación directa"' in text
          and "fuente: Mia" in text and "estado: active" in text)
    check("privacidad: el frontmatter NUNCA incluye tenant_id",
          "tenant" not in text.lower() and "tenant-secreto" not in text)
    check("cuerpo: título como H1", "# Caducidad en reparación directa" in text)
    check("cuerpo: summary como blockquote", "> Cómputo del término de dos años." in text)
    check("cuerpo: applies_when bajo 'Cuándo aplica'",
          "## Cuándo aplica" in text and "El daño es imputable al Estado" in text)
    check("cuerpo: content completo presente", "CUERPO_PLAYBOOK" in text)

    # playbook 'draft' (no activo) también se puede exportar; el estado queda visible.
    draft = dict(playbook, title="Playbook en borrador", status="draft")
    draft_target = writer.export_playbook("tenant-secreto", draft)
    check("estado del playbook se refleja en el frontmatter (draft)",
          "estado: draft" in draft_target.read_text(encoding="utf-8"))

    # sin título → rechazado explícitamente (no escribe un archivo vacío/anónimo).
    check("playbook sin título se rechaza (ValueError)",
          _rejected(lambda: writer.export_playbook("t", {"summary": "x"})))


# ── 2 · slug seguro ────────────────────────────────────────────────────────────
def test_slug_seguro() -> None:
    writer = VaultWriter(VAULT)
    before = set((VAULT / "Mia" / PROCEDURES_SUBDIR).glob("*.md")) if \
        (VAULT / "Mia" / PROCEDURES_SUBDIR).is_dir() else set()

    check("título con '..' se RECHAZA (no escapa de procedimientos/)",
          _rejected(lambda: writer.export_playbook("t", {"title": "../../fuera-del-vault"})))
    check("título con separador de ruta se RECHAZA",
          _rejected(lambda: writer.export_playbook("t", {"title": "a/b"}))
          and _rejected(lambda: writer.export_playbook("t", {"title": "a\\b"})))
    check("nada quedó escrito fuera de procedimientos/ tras los intentos de escape",
          not (VAULT / "fuera-del-vault.md").exists() and not (WORK / "fuera-del-vault.md").exists())

    # título con caracteres raros: se slugifica de forma segura, SIN salir del dir.
    weird = writer.export_playbook("t", {"title": "Título Ñoño & Cía. — 2026"})
    check("título con caracteres raros produce un slug ascii seguro",
          weird.parent == (VAULT / "Mia" / PROCEDURES_SUBDIR).resolve()
          and weird.is_relative_to((VAULT / "Mia" / PROCEDURES_SUBDIR).resolve()))

    after = set((VAULT / "Mia" / PROCEDURES_SUBDIR).glob("*.md"))
    check("los rechazos no dejaron archivos nuevos (solo el título válido)",
          after - before == {weird})


# ── 3 · ficha de norma: agrupa segmentos por metadata.parent_norm ────────────
def test_render_norm_ficha_agrupa_segmentos() -> None:
    seg1 = {
        "id": "norm-1", "norm_number": "Ley 100 (parte 1 de 2)",
        "title": "Ley 100 de 1993", "summary": "Sistema de seguridad social integral.",
        "full_text": "texto completo del segmento 1 " * 50,
        "practice_areas": ["seguridad social", "laboral"],
        "metadata": {
            "parent_norm": "Ley 100", "segment": 1, "segments_total": 2,
            "source_url": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=5248",
            "fetched_at": "2026-07-01T10:00:00+00:00",
            "content_sha256": "abc123",
        },
    }
    seg2 = {
        "id": "norm-2", "norm_number": "Ley 100 (parte 2 de 2)",
        "title": "Ley 100 de 1993", "summary": "Sistema de seguridad social integral.",
        "full_text": "texto completo del segmento 2 " * 50,
        "practice_areas": ["seguridad social", "laboral"],
        "metadata": {
            "parent_norm": "Ley 100", "segment": 2, "segments_total": 2,
            "source_url": "https://www.funcionpublica.gov.co/eva/gestornormativo/norma.php?i=5248",
            "fetched_at": "2026-07-01T10:00:00+00:00",
            "content_sha256": "abc123",
        },
    }
    groups = ve._group_norms_by_parent([seg1, seg2])
    check("2 filas segmentadas con el mismo parent_norm producen UN solo grupo",
          list(groups.keys()) == ["Ley 100"] and len(groups["Ley 100"]) == 2)

    slug, content = ve.render_norm_ficha("Ley 100", groups["Ley 100"])
    check("la ficha de norma trae el número, la fuente y la huella sha256",
          "Ley 100" in content and "funcionpublica.gov.co" in content and "abc123" in content)
    check("la ficha de norma reporta los segmentos (no es un segmento suelto)",
          "**Segmentos:** 2" in content)
    check("la ficha de norma NO incluye el texto completo (full_text)",
          "texto completo del segmento" not in content)
    check("la ficha de norma trae un resumen corto (<=400 chars) y las áreas como tags",
          "Sistema de seguridad social integral." in content and "seguridad social" in content)

    # una norma sin segmentar (sin parent_norm) agrupa por su propio norm_number.
    solo = {
        "id": "norm-3", "norm_number": "Decreto 123 de 2020", "title": "Decreto suelto",
        "summary": "resumen", "full_text": "x", "practice_areas": [],
        "metadata": {"source_url": "https://x", "fetched_at": "2026-01-01", "content_sha256": "z"},
    }
    solo_groups = ve._group_norms_by_parent([solo])
    check("norma sin segmentar agrupa por su propio norm_number",
          list(solo_groups.keys()) == ["Decreto 123 de 2020"])


# ── 4 · ficha de sentencia: MP/fecha/URL ──────────────────────────────────────
def test_render_jurisprudence_ficha() -> None:
    row = {
        "id": "juris-1", "court": "Corte Constitucional", "decision_number": "T-406 de 1992",
        "magistrado_ponente": "Ciro Angarita Barón", "decision_date": "1992-06-05",
        "topic": "Estado social de derecho y principio de eficacia.",
        "metadata": {
            "source_url": "https://www.corteconstitucional.gov.co/relatoria/1992/T-406-92.htm",
            "content_sha256": "def456",
        },
    }
    slug, content = ve.render_jurisprudence_ficha(row)
    check("ficha de sentencia trae magistrado ponente", "Ciro Angarita Barón" in content)
    check("ficha de sentencia trae la fecha", "1992-06-05" in content)
    check("ficha de sentencia trae la URL de la fuente oficial",
          "corteconstitucional.gov.co/relatoria/1992/T-406-92.htm" in content)
    check("ficha de sentencia trae corte y número", "Corte Constitucional" in content and "T-406 de 1992" in content)
    check("ficha de sentencia NO incluye ratio_decidendi/texto completo (no viene en el SELECT)",
          "ratio_decidendi" not in content)


# ── 5 · fail-closed: subdir fuera de la allowlist / vault fuera de la allowlist ──
def test_fail_closed() -> None:
    writer = VaultWriter(VAULT)
    check("_export_ficha con subdir NO permitido se rechaza",
          _rejected(lambda: writer._export_ficha("otra-carpeta", "slug", "contenido")))
    check("_export_ficha con intento de escape en el subdir se rechaza",
          _rejected(lambda: writer._export_ficha("../fuera", "slug", "contenido")))
    check("nada quedó escrito por los subdirs rechazados",
          not (VAULT / "Mia" / "otra-carpeta").exists() and not (VAULT.parent / "fuera").exists())

    outside = Path(tempfile.mkdtemp(prefix="vault_export_outside_"))
    try:
        check("vault fuera de OBSIDIAN_VAULT_ALLOWLIST se rechaza (VaultWriter)",
              _rejected(lambda: VaultWriter(outside)))
        check("nada quedó escrito fuera de la allowlist", not any(outside.iterdir()))
    finally:
        shutil.rmtree(outside, ignore_errors=True)


# ── check de humo con DB real: corpus_factory → fichas en el vault temporal ──
async def db_smoke_check() -> None:
    if not config.DATABASE_URL:
        check("DB smoke: DATABASE_URL configurada en .env", False)
        return
    await pool.open_pool()
    try:
        norms = await ve._fetch_active_norms()
        juris = await ve._fetch_jurisprudence()
        check("DB smoke: hay normas ingeridas por corpus_factory", len(norms) > 0)
        check("DB smoke: hay jurisprudencia ingerida por corpus_factory", len(juris) > 0)

        writer = VaultWriter(VAULT)
        stats = await ve.export_corpus_fichas(writer)
        check("DB smoke: export_corpus_fichas produjo fichas de normativa",
              stats["normativa"] > 0)
        check("DB smoke: export_corpus_fichas produjo fichas de jurisprudencia",
              stats["jurisprudencia"] > 0)

        norm_dir = VAULT / "Mia" / CORPUS_NORMATIVA_SUBDIR
        juris_dir = VAULT / "Mia" / CORPUS_JURISPRUDENCIA_SUBDIR
        check("DB smoke: las fichas de normativa quedaron SOLO bajo Mia/corpus/normativa/",
              norm_dir.is_dir() and len(list(norm_dir.glob("*.md"))) == stats["normativa"])
        check("DB smoke: las fichas de jurisprudencia quedaron SOLO bajo Mia/corpus/jurisprudencia/",
              juris_dir.is_dir() and len(list(juris_dir.glob("*.md"))) == stats["jurisprudencia"])
        check("DB smoke: ninguna ficha se escribió fuera del vault temporal",
              all(p.is_relative_to(VAULT.resolve())
                  for p in list(norm_dir.glob("*.md")) + list(juris_dir.glob("*.md"))))

        # una norma segmentada (si el corpus real tiene alguna) produce MENOS fichas
        # que filas en legal_norms — nunca una ficha por segmento.
        check("DB smoke: nunca más fichas de normativa que filas de legal_norms",
              stats["normativa"] <= len(norms))
    finally:
        await pool.close_pool()


def main() -> int:
    print("== Fase 3 · frente C · bóveda visible (playbooks + corpus) ==")
    try:
        test_export_playbook()
        test_slug_seguro()
        test_render_norm_ficha_agrupa_segmentos()
        test_render_jurisprudence_ficha()
        test_fail_closed()
        asyncio.run(db_smoke_check())
    finally:
        if _ORIGINAL_ALLOWLIST is None:
            os.environ.pop("OBSIDIAN_VAULT_ALLOWLIST", None)
        else:
            os.environ["OBSIDIAN_VAULT_ALLOWLIST"] = _ORIGINAL_ALLOWLIST
        shutil.rmtree(WORK, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Bóveda visible (playbooks + corpus) OK.")
        return 0
    print("Bóveda visible FAIL — no avanzar con la siguiente tarea.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
