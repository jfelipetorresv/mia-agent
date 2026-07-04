"""
Mia · test_research_swarm.py — gate de la investigación DELEGADA en paralelo (CP-E5 · Ola 5).

Ejercita la elevación de `research_node` en `agents/graph.py` SIN modelo ni DB vivos
(monkeypatch de `_llm`, `research.*` y `verification.annotate_draft`). Cubre:

  · UNA jurisdicción → camino simple (idéntico a antes de CP-E5): 1 llamada LLM, gather_sources
    acotado a esa jurisdicción, SIN clave `research_delegation` en metadata;
  · DOS jurisdicciones → swarm: un investigador por jurisdicción (verificación de citas por
    rama) + un sintetizador; metadata trae `research_delegation.workers == 2` y la memoria
    final es la del sintetizador; las fuentes se agregan de ambas ramas;
  · FAIL-SOFT: si TODOS los investigadores fallan, cae al camino simple (no tumba el turno);
  · aislamiento de md por worker: la coordinación de compresión de un worker no contamina el
    md real del turno.

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_research_swarm.py
"""
from __future__ import annotations
import asyncio
import re
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agents import graph as gmod                    # noqa: E402
from mia.agents import research, verification           # noqa: E402
from mia.agents.graph import MatterGraphBuilder          # noqa: E402
from mia.policy import budget as policy_budget           # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


_USAGE = {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}


def _base_state() -> dict:
    return {
        "tenant_id": "00000000-0000-0000-0000-000000000001",
        "matter_id": "00000000-0000-0000-0000-000000000002",
        "messages": [{"role": "user", "content": "¿Prescribió la acción?"}],
        "documents": [], "knowledge": [], "persona": None,
        "metadata": {"facts": "Hecho 1. Datos faltantes por confirmar: ninguno."},
    }


class _Recorder:
    """Instala stubs deterministas en graph/research/verification y registra las llamadas."""

    def __init__(self, jurisdictions: list[str], fail_workers: bool = False,
                 over_budget: bool = False):
        self.jurisdictions = jurisdictions
        self.fail_workers = fail_workers
        self.over_budget = over_budget
        self.llm_calls: list[str] = []          # "worker:<j>" | "synth" | "single"
        self.gather_juris: list[list[str]] = []  # jurisdicciones pedidas a gather_sources
        self.verify_calls = 0
        self.worker_md_seen: list[dict] = []
        self.worker_shrink_provided: list[bool] = []  # M1: el worker pasa su propio shrink

    def install(self, builder: MatterGraphBuilder):
        async def fake_resolve(_tenant):
            return list(self.jurisdictions)

        async def fake_budget_status(_tenant):
            return {"over_budget": self.over_budget, "unlimited": not self.over_budget}

        async def fake_gather(_tenant, _query, *, jurisdictions=None):
            self.gather_juris.append(list(jurisdictions or ["<none>"]))
            js = ",".join(jurisdictions or [])
            src = [{"tipo": "norma", "referencia": f"L-{js}", "titulo": f"Norma {js}"}]
            return (f"FUENTES[{js}]", src, list(jurisdictions or []))

        async def fake_patterns(_tenant):
            return []

        def fake_annotate(text, *, sources=None, extra_patterns=None):
            self.verify_calls += 1
            return text, {"marcadas": 0, "anotadas": 0}

        async def fake_llm(messages, *, task="main", state=None, md=None, shrink=None,
                           node="", model=None):
            content = messages[-1]["content"]
            m = re.search(r"jurisdicción '([^']+)'", content)
            if "Trabajas SOLO la jurisdicción" in content and m:
                juris = m.group(1)
                self.llm_calls.append(f"worker:{juris}")
                self.worker_md_seen.append(md if md is not None else {})
                self.worker_shrink_provided.append(shrink is not None)
                if self.fail_workers:
                    raise RuntimeError("investigador caído")
                return f"MEMO[{juris}]", dict(_USAGE)
            if "Consolida las siguientes memorias" in content:
                self.llm_calls.append("synth")
                return "MEMO-SINTESIS", dict(_USAGE)
            self.llm_calls.append("single")
            return "MEMO-SIMPLE", dict(_USAGE)

        research.resolve_jurisdictions_for = fake_resolve
        research.gather_sources = fake_gather
        research.citation_patterns_for = fake_patterns
        verification.annotate_draft = fake_annotate
        policy_budget.budget_status = fake_budget_status
        builder._llm = fake_llm


async def _checks() -> None:
    # Guardamos originales para restaurar.
    orig = (research.resolve_jurisdictions_for, research.gather_sources,
            research.citation_patterns_for, verification.annotate_draft,
            policy_budget.budget_status)
    try:
        # A · UNA jurisdicción → camino simple.
        b = MatterGraphBuilder()
        rec = _Recorder(["co"])
        rec.install(b)
        out = await b.research_node(_base_state())
        md = out["metadata"]
        check("1-juris: 1 sola llamada LLM (camino simple)", rec.llm_calls == ["single"])
        check("1-juris: gather_sources acotado a ['co']", rec.gather_juris == [["co"]])
        check("1-juris: memoria = la del camino simple", md.get("research") == "MEMO-SIMPLE")
        check("1-juris: SIN research_delegation en metadata", "research_delegation" not in md)
        check("1-juris: jurisdicciones registradas", md.get("research_jurisdictions") == ["co"])

        # B · DOS jurisdicciones → swarm (workers + sintetizador).
        b = MatterGraphBuilder()
        rec = _Recorder(["co", "ec"])
        rec.install(b)
        out = await b.research_node(_base_state())
        md = out["metadata"]
        workers = sorted(c for c in rec.llm_calls if c.startswith("worker:"))
        check("2-juris: un investigador por jurisdicción",
              workers == ["worker:co", "worker:ec"])
        check("2-juris: exactamente un sintetizador", rec.llm_calls.count("synth") == 1)
        check("2-juris: verificación de citas por rama (2)", rec.verify_calls == 2)
        check("2-juris: memoria final = la del sintetizador", md.get("research") == "MEMO-SINTESIS")
        check("2-juris: metadata trae research_delegation.workers == 2",
              (md.get("research_delegation") or {}).get("workers") == 2)
        check("2-juris: fuentes agregadas de ambas ramas",
              len(md.get("research_sources") or []) == 2)
        check("2-juris: gather_sources se llamó una vez por jurisdicción",
              sorted(rec.gather_juris) == [["co"], ["ec"]])
        check("2-juris: usage acumulado de 2 workers + sintetizador (3×15=45 total)",
              (md.get("usage") or {}).get("total") == 45)
        check("2-juris: md aislado por worker (el worker recibió un md distinto del real)",
              all(m is not md for m in rec.worker_md_seen))
        # M1 (revisión capa 2): cada worker pasa su PROPIO shrink → `_llm` nunca cae al
        # compresor compartido (stateful) que tendría carrera entre workers paralelos.
        check("2-juris: cada worker pasa su propio shrink (no usa el compresor compartido)",
              len(rec.worker_shrink_provided) == 2 and all(rec.worker_shrink_provided))

        # C · FAIL-SOFT: si TODOS los investigadores fallan, cae al camino simple.
        b = MatterGraphBuilder()
        rec = _Recorder(["co", "ec"], fail_workers=True)
        rec.install(b)
        out = await b.research_node(_base_state())
        md = out["metadata"]
        check("fail-soft: tras fallar los 2 workers, corre el camino simple",
              "single" in rec.llm_calls)
        check("fail-soft: memoria = la del camino simple", md.get("research") == "MEMO-SIMPLE")
        check("fail-soft: SIN research_delegation (no hubo síntesis)",
              "research_delegation" not in md)

        # D · m4 (revisión capa 2): despacho SOBRE el tope de gasto → NO amplifica el costo;
        # degrada al camino simple aunque haya 2 jurisdicciones.
        b = MatterGraphBuilder()
        rec = _Recorder(["co", "ec"], over_budget=True)
        rec.install(b)
        out = await b.research_node(_base_state())
        md = out["metadata"]
        check("m4: sobre el tope de gasto → camino simple (1 llamada, sin workers)",
              rec.llm_calls == ["single"])
        check("m4: sin research_delegation (no se amplificó)", "research_delegation" not in md)

        # E · m1 (revisión capa 2): dedup de jurisdicciones en resolve_jurisdictions_for.
        # Restauramos el resolve_jurisdictions_for REAL (install lo había parcheado) y
        # falseamos solo la fuente subyacente resolve_jurisdictions con duplicados.
        research.resolve_jurisdictions_for = orig[0]
        real_resolve = research.resolve_jurisdictions

        async def dup_resolve(_tenant):
            return ["co", "co", "ec", "ec", "co"]
        research.resolve_jurisdictions = dup_resolve
        try:
            deduped = await research.resolve_jurisdictions_for("t")
        finally:
            research.resolve_jurisdictions = real_resolve
        check("m1: resolve_jurisdictions_for deduplica preservando orden",
              deduped == ["co", "ec"])
    finally:
        (research.resolve_jurisdictions_for, research.gather_sources,
         research.citation_patterns_for, verification.annotate_draft,
         policy_budget.budget_status) = orig


def main() -> int:
    asyncio.run(_checks())
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Investigación delegada en paralelo OK — CP-E5 (swarm) verificado.")
        return 0
    print("Research swarm FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
