"""
Mia · test_workspace.py — gate del andamiaje en disco por despacho (Fase 1, incremento 1).

Ejercita `onboarding/workspace.py` contra un $MIA_HOME TEMPORAL (nunca el real):
estructura del despacho (.mia/ con despacho.md, baseline-<fecha>.md, aprendizajes.md PINNED,
memoria/INDICE.md), estructura del expediente (ficha.md, HANDOFF.md y carpetas neutras
bitacora/inbox/fuente/fichas/_archivo), separación estado-de-Mia vs fuente verbatim,
idempotencia (segunda corrida no crea ni pisa nada), no-destrucción (contenido editado se
conserva), agnosticismo de jurisdicción (sin carpetas país por defecto; `extra_carpetas`
opcional) y saneo de alias (un alias no puede escapar del árbol).

OFFLINE y sin DB: solo config + stdlib. Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_workspace.py
"""
from __future__ import annotations

import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia import config                                   # noqa: E402
from mia.onboarding import workspace as ws               # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def run(work: Path) -> None:
    config.MIA_HOME = work                                # apuntar el estado a un tempdir
    tenant = "11111111-1111-1111-1111-111111111111"

    # ── despacho (.mia/) ──────────────────────────────────────────────────────
    res = ws.scaffold_despacho_workspace(tenant, despacho_nombre="Despacho Demo")
    mia_dir = ws.mia_state_dir(tenant)
    check("despacho.md creado", (mia_dir / "despacho.md").is_file())
    check("aprendizajes.md PINNED creado", (mia_dir / "aprendizajes.md").is_file())
    check("aprendizajes.md marca PINNED",
          "PINNED" in (mia_dir / "aprendizajes.md").read_text(encoding="utf-8"))
    check("memoria/INDICE.md creado", (mia_dir / "memoria" / "INDICE.md").is_file())
    baselines = list(mia_dir.glob("baseline-*.md"))
    check("baseline-<fecha>.md creado (exactamente 1)", len(baselines) == 1)
    check("expedientes/ creado", ws.expedientes_dir(tenant).is_dir())
    check("scaffold despacho reporta creados", len(res["created"]) >= 4)

    # ── idempotencia + no-destrucción del despacho ────────────────────────────
    (mia_dir / "aprendizajes.md").write_text("# EDITADO POR MIA\ncontenido vivo\n",
                                             encoding="utf-8")
    res2 = ws.scaffold_despacho_workspace(tenant, despacho_nombre="Despacho Demo")
    check("segunda corrida del despacho no crea nada", res2["created"] == [])
    check("no pisa contenido editado",
          "EDITADO POR MIA" in (mia_dir / "aprendizajes.md").read_text(encoding="utf-8"))

    # ── expediente (expedientes/<alias>/) ─────────────────────────────────────
    m = ws.scaffold_matter_workspace(tenant, "caso-demo", titulo="Caso Demo Didáctico")
    mdir = ws.matter_workspace_dir(tenant, "caso-demo")
    check("ficha.md del caso creada", (mdir / "ficha.md").is_file())
    check("HANDOFF.md del caso creado", (mdir / "HANDOFF.md").is_file())
    for d in ("bitacora", "inbox", "fuente", "fichas", "_archivo"):
        check(f"carpeta {d}/ creada", (mdir / d).is_dir())
    check("fuente/ documenta inmutabilidad (LEEME)", (mdir / "fuente" / "LEEME.md").is_file())
    check("caso queda DENTRO de expedientes/",
          ws.expedientes_dir(tenant) in mdir.parents)

    # ── idempotencia del expediente ───────────────────────────────────────────
    m2 = ws.scaffold_matter_workspace(tenant, "caso-demo", titulo="Caso Demo Didáctico")
    check("segunda corrida del caso no crea nada", m2["created"] == [])

    # ── agnóstico de jurisdicción ─────────────────────────────────────────────
    country_like = {"colombia", "juzgados", "tribunales", "co", "sentencias-co"}
    present = {p.name.lower() for p in mdir.iterdir() if p.is_dir()}
    check("sin carpetas de país por defecto (agnóstico)", not (present & country_like))
    mx = ws.scaffold_matter_workspace(tenant, "caso-pack",
                                      extra_carpetas=["Actuaciones", "Pruebas"])
    mxdir = ws.matter_workspace_dir(tenant, "caso-pack")
    check("extra_carpetas del pack se crean",
          (mxdir / "Actuaciones").is_dir() and (mxdir / "Pruebas").is_dir())

    # ── saneo de alias (no escapar del árbol) ─────────────────────────────────
    ws.scaffold_matter_workspace(tenant, "../escape/x")
    escaped = (ws.expedientes_dir(tenant).parent / "escape").exists()
    check("alias con '../' no escapa del despacho", not escaped)


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="mia_workspace_"))
    try:
        run(work)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Andamiaje en disco OK — Fase 1 inc.1 verificado.")
        return 0
    print("Andamiaje en disco FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
