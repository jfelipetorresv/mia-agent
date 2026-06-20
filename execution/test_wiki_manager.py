"""
Mia · test_wiki_manager.py — gate del Second Brain / WikiManager.

Verifica estructura por tenant, compilación de conceptos, búsqueda, lint,
archivo y conexión HITL en background.
"""
from __future__ import annotations

import asyncio
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agent import llm  # noqa: E402
from mia.memory.trace_capture import TraceCapture  # noqa: E402
from mia.memory.wiki_manager import WikiManager  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def fake_llm(messages, *, task=None, **kwargs):
    content = messages[-1]["content"]
    if "JSON array" in content:
        out = '["Concepto Alfa", "Concepto Beta"]'
    else:
        out = (
            "## Definicion (segun la practica de este despacho)\n"
            "Definicion desde evidencia aprobada.\n\n"
            "## Patrones identificados\n"
            "- Patron reutilizable.\n\n"
            "## Casos que lo soportan (referencias anonimas)\n"
            "- matter anonimo.\n\n"
            "## Conexiones con otros conceptos\n"
            "- Concepto Beta.\n\n"
            "## Lo que NO funciona (aprendido de rechazos)\n"
            "- Sin rechazos registrados.\n"
        )
    return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=out))])


async def run_checks() -> None:
    original = llm.call_llm
    llm.call_llm = fake_llm
    try:
        with tempfile.TemporaryDirectory() as tmp:
            traces = Path(tmp) / "traces"
            mgr = WikiManager(home=tmp, trace_capture=TraceCapture(traces))
            tenant = "tenant-wiki"
            matter = "matter-1"

            await mgr.init_wiki(tenant)
            root = Path(tmp) / "wiki" / tenant
            check("init_wiki crea root", root.exists())
            check("init_wiki crea concepts y archived", (root / "concepts" / "archived").exists())
            check("init_wiki crea sources/index/schema", all((root / p).exists() for p in ("sources.md", "index.md", "schema.md")))
            schema = (root / "schema.md").read_text(encoding="utf-8")
            check("schema es generico y horizontal", "Colombia" not in schema and "jurisdiccion" in schema)

            compiled = await mgr.compile_concept(tenant, "Concepto Alfa", ["Evidencia aprobada de prueba"])
            check("compile_concept escribe frontmatter", "confidence:" in compiled and "case_count:" in compiled)
            check("compile_concept escribe archivo", mgr.concept_path(tenant, "Concepto Alfa").exists())
            check("compile_concept incluye secciones requeridas", "## Patrones identificados" in compiled and "## Lo que NO funciona" in compiled)

            concepts = await mgr.extract_concepts(tenant, "Texto aprobado con Concepto Alfa")
            check("extract_concepts devuelve lista libre", concepts == ["Concepto Alfa", "Concepto Beta"])

            mgr.trace_capture.capture(
                tenant_id=tenant,
                matter_id=matter,
                input="Diagnostico aprobado con Concepto Alfa",
                output="Borrador aprobado con Concepto Beta",
                model="test",
                tokens=1,
                latency_ms=1,
                hitl_outcome="approved",
                draft_final="Borrador aprobado con Concepto Beta",
            )
            updated = await mgr.update_from_approved_matter(tenant, matter)
            check("update_from_approved_matter actualiza conceptos", updated == ["Concepto Alfa", "Concepto Beta"])
            check("update_from_approved_matter actualiza sources", f"matter:{matter}" in (root / "sources.md").read_text(encoding="utf-8"))
            check("update_from_approved_matter actualiza index", "[[Concepto Alfa]] -- [[Concepto Beta]]" in (root / "index.md").read_text(encoding="utf-8"))

            listed = await mgr.list_concepts(tenant)
            check("list_concepts devuelve metadata", any(x["name"] == "Concepto Alfa" and x["case_count"] >= 1 for x in listed))
            got = await mgr.get_concept(tenant, "Concepto Alfa")
            check("get_concept devuelve markdown", got is not None and "# Concepto Alfa" in got)
            hits = await mgr.search_wiki(tenant, "Patron")
            check("search_wiki devuelve excerpt y metadata", bool(hits) and {"concept", "excerpt", "confidence", "case_count"}.issubset(hits[0].keys()))

            old = mgr.concept_path(tenant, "Concepto Viejo")
            old.write_text(
                "---\nconcept: Concepto Viejo\nconfidence: 0.20\nlast_updated: 2000-01-01\ncase_count: 1\n---\n# Concepto Viejo\n",
                encoding="utf-8",
            )
            lint = await mgr.lint_wiki(tenant)
            check("lint_wiki detecta stale", "Concepto Viejo" in lint["stale"])
            check("lint_wiki detecta low_confidence", "Concepto Viejo" in lint["low_confidence"])
            await mgr.archive_concept(tenant, "Concepto Viejo")
            check("archive_concept mueve sin borrar", (root / "concepts" / "archived" / "concepto_viejo.md").exists() and not old.exists())

            hitl_src = (ROOT / "backend" / "mia" / "api" / "routes" / "hitl.py").read_text(encoding="utf-8")
            check("HITL dispara wiki en background", "asyncio.create_task" in hitl_src and "update_from_approved_matter" in hitl_src)
    finally:
        llm.call_llm = original


def main() -> int:
    print("== WikiManager second brain ==")
    asyncio.run(run_checks())
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("WikiManager OK — second brain verificado.")
        return 0
    print("WikiManager FAIL — no avanzar con la siguiente tarea.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
