"""
Mia · test_context_recovery.py — gate de CP1 (Riesgo #33: rescate real de CONTEXT_TOO_LONG).

Verifica OFFLINE (sin red, sin proxy, sin DB), con el cliente LLM MOCKEADO y la política
de modelo fijada a 'nube' (cadena main = claude-sonnet→mia-local):

  a. analysis: la 1ª llamada lanza CONTEXT_TOO_LONG → la 2ª recibe un prompt ESTRICTAMENTE
     menor en tokens estimados (documentos recortados) y el turno completa.
  b. draft: igual; los playbooks activos se descartan (queda el índice + marcador) y la
     CONCLUSIÓN del diagnóstico sobrevive al recorte (shrink_text protect_tail=True).
  c. doble fallo: la 2ª llamada también CONTEXT_TOO_LONG → se propaga la excepción original
     y hay UNA sola compresión por turno (contrato TurnLLMState).
  d. unit tests de shrink_documents (reduce cantidad, trunca, marca, nunca deja 0 docs)
     y shrink_text (protect_tail conserva el final) y budget_for.
  e. nodo SIN shrink (finalize/EDIT) → sigue usando el camino del ContextCompressor.

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_context_recovery.py
"""
from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia import config                                     # noqa: E402
from mia.agent import llm                                  # noqa: E402
from mia.agents import context_recovery as cr              # noqa: E402
from mia.agents import graph as graph_mod                  # noqa: E402
from mia.agents.graph import MatterGraphBuilder            # noqa: E402
from mia.memory.tokens import estimate_tokens              # noqa: E402
from mia.memory.trace_capture import TraceCapture          # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── fábricas de resultados para el cliente falso (patrón test_llm_fallback) ──────
def ok_response(text: str = "ok"):
    msg = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)


def context_exc():
    # Sin status: classify_llm_error detecta CONTEXT_TOO_LONG por el mensaje.
    return Exception("This model's maximum context length exceeded by 5000 tokens")


class FakeCompletions:
    """Programable por alias (el último resultado se repite). Registra los MESSAGES
    de cada llamada para comparar tamaños de prompt entre intento 1 y 2."""

    def __init__(self, script: dict[str, list]) -> None:
        self.script = script
        self.calls: list[str] = []
        self.messages_seen: list[list[dict]] = []

    def create(self, **kwargs):
        model = kwargs["model"]
        self.calls.append(model)
        self.messages_seen.append([dict(m) for m in kwargs["messages"]])
        outcomes = self.script[model]
        idx = min(sum(1 for m in self.calls if m == model) - 1, len(outcomes) - 1)
        outcome = outcomes[idx]
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    def count(self, model: str) -> int:
        return sum(1 for m in self.calls if m == model)


def install(script: dict[str, list]) -> FakeCompletions:
    fc = FakeCompletions(script)
    llm._client = SimpleNamespace(chat=SimpleNamespace(completions=fc))
    return fc


def toks(messages: list[dict]) -> int:
    return sum(estimate_tokens(str(m.get("content") or "")) for m in messages)


CONCLUSION = "CONCLUSIÓN Y RECOMENDACIÓN: procede la excepción de caducidad del medio de control."


def make_state(docs: list[dict] | None = None, metadata: dict | None = None) -> dict:
    return {
        "tenant_id": "t-gate-cp1", "matter_id": "m-gate-cp1",
        "messages": [{"role": "user", "content": "¿Caducó la acción de reparación directa?"}],
        "documents": docs or [],
        "profile_snapshot": {"despacho": "Defendemos aseguradoras."},
        "metadata": metadata or {},
    }


def run(trace_dir: str) -> None:
    llm.time.sleep = lambda *_a, **_k: None  # reintentos instantáneos (no aplica a contexto)
    builder = MatterGraphBuilder(trace_capture=TraceCapture(trace_dir))

    # === a · analysis: CONTEXT_TOO_LONG → 2º prompt estrictamente menor y turno completo ===
    docs = [{"id": f"d{i}", "content": f"[doc original {i}] " + ("hecho jurídico relevante " * 200)}
            for i in range(8)]
    state = make_state(docs=docs)
    fc = install({"claude-sonnet": [context_exc(), ok_response("DIAGNÓSTICO: caducidad.")]})
    out = asyncio.run(builder.analysis_node(state))
    md_a = out["metadata"]
    check("a1 · analysis completa tras el rescate (diagnóstico presente)",
          md_a.get("diagnosis") == "DIAGNÓSTICO: caducidad.")
    check("a2 · exactamente 2 llamadas LLM (fallo + reintento reducido)",
          fc.count("claude-sonnet") == 2 and len(fc.messages_seen) == 2)
    t1, t2 = toks(fc.messages_seen[0]), toks(fc.messages_seen[1])
    check(f"a3 · el 2º prompt es ESTRICTAMENTE menor en tokens estimados ({t2} < {t1})", t2 < t1)
    user2 = fc.messages_seen[1][1]["content"]
    check("a4 · los documentos truncados llevan el marcador de recorte",
          "[... documento recortado por límite de contexto" in user2)
    check("a5 · el 2º prompt conserva al menos 1 documento con contenido útil",
          "[doc 1]" in user2 and "hecho jurídico relevante" in user2)
    check("a6 · la mitad de los documentos se descarta (doc 5..8 fuera)",
          "[doc original 4]" not in user2 and "[doc original 7]" not in user2)
    check("a7 · los documents del estado NO se mutan (recorte sobre copias)",
          docs[0]["content"].endswith("relevante ") and len(docs) == 8)
    check("a8 · TurnLLMState registra la compresión del turno (una sola vez)",
          md_a.get("llm_turn", {}).get("compression_attempted") is True)

    # === b · draft: playbooks → índice + marcador; la conclusión del diagnosis sobrevive ===
    diag = ("análisis de los hechos y fundamentos de derecho del asunto " * 400) + CONCLUSION
    pb_index = "ÍNDICE DE PLAYBOOKS: [pb1] contestación de demanda · [pb2] excepciones."
    pb_active = "PLAYBOOK ACTIVO pb1:\n" + ("paso metodológico del despacho " * 500)

    async def fake_prepare(_state, _diag):
        return pb_index, pb_active, ["pb1"]

    saved_prepare = graph_mod._prepare_playbooks
    graph_mod._prepare_playbooks = fake_prepare
    try:
        state_b = make_state(metadata={"diagnosis": diag})
        fc = install({"claude-sonnet": [context_exc(), ok_response("BORRADOR: contestación.")]})
        out_b = asyncio.run(builder.draft_node(state_b))
    finally:
        graph_mod._prepare_playbooks = saved_prepare
    check("b1 · draft completa tras el rescate (borrador presente)",
          out_b.get("draft") == "BORRADOR: contestación.")
    check("b2 · exactamente 2 llamadas LLM", fc.count("claude-sonnet") == 2)
    t1, t2 = toks(fc.messages_seen[0]), toks(fc.messages_seen[1])
    check(f"b3 · el 2º prompt es ESTRICTAMENTE menor en tokens estimados ({t2} < {t1})", t2 < t1)
    user2 = fc.messages_seen[1][1]["content"]
    check("b4 · los playbooks activos se descartan PRIMERO (texto del playbook fuera)",
          "paso metodológico del despacho" not in user2)
    check("b5 · queda solo el índice de playbooks + marcador",
          pb_index in user2 and cr.PLAYBOOKS_TRIMMED_MARKER in user2)
    check("b6 · la CONCLUSIÓN del diagnóstico sobrevive al recorte (protect_tail)",
          CONCLUSION in user2)
    check("b7 · el diagnóstico sí se recortó (marcador de sección en el 2º prompt)",
          cr.TEXT_CUT_MARKER in user2)
    check("b8 · el perfil del despacho se conserva", "Defendemos aseguradoras." in user2)

    # === c · doble fallo: 2ª llamada también CONTEXT_TOO_LONG → propaga y UNA compresión ===
    shrink_calls = {"n": 0}

    def shrink_small():
        shrink_calls["n"] += 1
        return [{"role": "system", "content": "s"}, {"role": "user", "content": "reducido"}]

    fc = install({"claude-sonnet": [context_exc(), context_exc()]})
    md_c: dict = {}
    err = None
    try:
        asyncio.run(builder._llm(
            [{"role": "system", "content": "s"}, {"role": "user", "content": "x" * 4000}],
            task="main", state=make_state(), md=md_c, shrink=shrink_small))
    except Exception as e:  # noqa: BLE001 — esperamos la excepción ORIGINAL de contexto
        err = e
    check("c1 · doble CONTEXT_TOO_LONG → propaga la excepción original (no LLMError)",
          err is not None and not isinstance(err, llm.LLMError)
          and "context length" in str(err).lower())
    check("c2 · exactamente 2 llamadas LLM y 1 sola invocación de shrink",
          fc.count("claude-sonnet") == 2 and shrink_calls["n"] == 1)
    check("c3 · TurnLLMState quedó marcado (compression_attempted=True)",
          md_c.get("llm_turn", {}).get("compression_attempted") is True)
    # Una llamada MÁS en el mismo turno (mismo md) que vuelva a fallar por contexto NO
    # recomprime: el cupo del turno ya se gastó (contrato una-sola-compresión-por-turno).
    fc = install({"claude-sonnet": [context_exc()]})
    err2 = None
    try:
        asyncio.run(builder._llm(
            [{"role": "system", "content": "s"}, {"role": "user", "content": "y" * 4000}],
            task="main", state=make_state(), md=md_c, shrink=shrink_small))
    except Exception as e:  # noqa: BLE001
        err2 = e
    check("c4 · el mismo turno NO recomprime (1 llamada, shrink NO se re-invoca)",
          err2 is not None and fc.count("claude-sonnet") == 1 and shrink_calls["n"] == 1)

    # === d · unit tests de los helpers puros ===
    many = [{"id": f"d{i}", "content": "contenido jurídico útil " * 100} for i in range(8)]
    small = cr.shrink_documents(many, budget_tokens=400)
    check("d1 · shrink_documents reduce la cantidad a la mitad (8→4)", len(small) == 4)
    check("d2 · shrink_documents trunca el contenido al presupuesto proporcional",
          all(estimate_tokens(d["content"]) < estimate_tokens(many[0]["content"]) for d in small))
    check("d3 · los documentos truncados llevan el sufijo marcador",
          all(d["content"].endswith("ver expediente completo]") for d in small))
    one = cr.shrink_documents([{"id": "d0", "content": "x" * 100000}], budget_tokens=100)
    check("d4 · nunca deja 0 documentos y conserva contenido útil",
          len(one) == 1 and len(one[0]["content"]) >= cr.MIN_DOC_TOKENS
          and one[0]["content"].startswith("x"))
    check("d5 · lista vacía → lista vacía (sin inventar documentos)",
          cr.shrink_documents([], budget_tokens=100) == [])
    check("d6 · los dicts de entrada no se mutan",
          many[0]["content"] == "contenido jurídico útil " * 100)

    txt = ("relato de hechos " * 500) + CONCLUSION
    kept = cr.shrink_text(txt, budget_tokens=300, protect_tail=True)
    check("d7 · shrink_text(protect_tail=True) conserva el FINAL (la conclusión)",
          kept.endswith(CONCLUSION) and estimate_tokens(kept) < estimate_tokens(txt))
    check("d8 · protect_tail recorta el MEDIO con el marcador de sección",
          cr.TEXT_CUT_MARKER in kept and kept.startswith("relato de hechos"))
    head = cr.shrink_text(txt, budget_tokens=300, protect_tail=False)
    check("d9 · shrink_text sin protect_tail conserva el INICIO",
          head.startswith("relato de hechos") and CONCLUSION not in head
          and cr.TEXT_CUT_MARKER in head)
    check("d10 · texto bajo el presupuesto se devuelve intacto",
          cr.shrink_text("corto", budget_tokens=100) == "corto")
    check("d11 · budget_for: 60% analysis · 50% draft · 50% default",
          cr.budget_for("analysis", 1000) == 600 and cr.budget_for("draft", 1000) == 500
          and cr.budget_for("otro-nodo", 1000) == 500)

    # === e · nodo SIN shrink (finalize/EDIT) → sigue el camino del ContextCompressor ===
    class SpyCompressor:
        def __init__(self) -> None:
            self.calls = 0

        def compress(self, messages, _window, *, tenant_id=None, matter_id=None):
            self.calls += 1
            return [messages[0], {"role": "user", "content": "[RESUMEN] historial comprimido"}]

    spy = SpyCompressor()
    saved_comp = builder._compressor
    builder._compressor = spy
    try:
        fc = install({"claude-sonnet": [context_exc(), ok_response("BORRADOR CORREGIDO.")]})
        md_e: dict = {}
        content, _usage = asyncio.run(builder._llm(
            [{"role": "system", "content": "Incorpora al borrador"},
             {"role": "user", "content": "Borrador:\n" + "z" * 8000}],
            task="main", state=make_state(), md=md_e))  # SIN shrink (como finalize)
    finally:
        builder._compressor = saved_comp
    check("e1 · sin shrink, el rescate usa ContextCompressor.compress (1 vez)", spy.calls == 1)
    check("e2 · el reintento usa los mensajes del compresor y completa",
          content == "BORRADOR CORREGIDO." and fc.count("claude-sonnet") == 2
          and "[RESUMEN]" in fc.messages_seen[1][1]["content"])
    check("e3 · el cupo del turno también se consume por este camino",
          md_e.get("llm_turn", {}).get("compression_attempted") is True)


def main() -> int:
    print("== CP1 · Riesgo #33 · recuperación real de CONTEXT_TOO_LONG por nodo ==")
    saved_window = config.MIA_CONTEXT_WINDOW
    config.MIA_CONTEXT_WINDOW = 2000  # ventana chica para forzar recortes visibles en el gate
    tok = llm.set_model_policy("nube")  # cadena main = claude-sonnet→mia-local (como en H.5)
    trace_dir = tempfile.mkdtemp(prefix="mia_traces_cp1_")
    try:
        run(trace_dir)
    finally:
        llm.reset_model_policy(tok)
        llm._client = None
        config.MIA_CONTEXT_WINDOW = saved_window
        shutil.rmtree(trace_dir, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("context recovery OK — CP1 verificado (Riesgo #33: shrink por nodo + contrato "
              "una-compresión-por-turno + camino del compresor intacto).")
        return 0
    print("context recovery FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
