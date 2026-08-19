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
  d. unit tests de shrink_documents (recorta POR PRESUPUESTO —no por mitades—, APROVECHA
     el cupo, prioriza lo más relevante, trunca, marca, nunca deja 0 docs) y shrink_text
     (protect_tail conserva el final) y budget_for.
  e. nodo SIN shrink (finalize/EDIT) → sigue usando el camino del ContextCompressor.
  f. camino de rescate CON material de AMPLIACIÓN presente (lectura adaptativa): lo que el
     modelo pidió sobrevive al recorte y el prompt reducido aprovecha su presupuesto.

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
from mia.agents import packs as legal_packs                # noqa: E402
from mia.agents import untrusted                           # noqa: E402
from mia.agents.graph import MatterGraphBuilder            # noqa: E402
from mia.memory.tokens import estimate_tokens              # noqa: E402
from mia.memory.trace_capture import TraceCapture          # noqa: E402

_results: list[tuple[str, bool]] = []


def rendered_tokens(docs: list[dict]) -> int:
    """Tokens de la sección 'Expediente' TAL COMO se renderiza (cabecera + sellos
    <<<DOC n>>> + contenido). Es la única medida honesta del presupuesto: comparar
    contra la suma cruda de los contenidos es lo que dejaba el recorte en la mitad."""
    return estimate_tokens(untrusted.render_documents(docs))


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


def content_text(msg: dict) -> str:
    """Texto REAL que el modelo recibe en `msg`, venga como string o como bloques.

    Desde que el prefix caching de Anthropic quedó CABLEADO (commit e8ce3b3), el embudo
    `llm._messages_with_cache` reemplaza —solo para los aliases directos de Anthropic, que
    son justamente la cadena que fija este gate: `set_model_policy("nube")` → claude-sonnet—
    el `content` del system de un `str` por una LISTA de bloques:
        [{"type":"text","text":<prefijo estable>,"cache_control":{...}},
         {"type":"text","text":<resto>}]
    El cliente falso se instala en `llm._client`, es decir POR DEBAJO de esa transformación,
    así que lo que queda registrado en `messages_seen` es la lista, no el string.

    Concatenar los bloques reconstruye el system original BYTE A BYTE — es el invariante
    que `prompt_builder.cache_split` declara y garantiza (`prefijo + resto == system_text`;
    el marcado de caché es metadata que el modelo no renderiza). Por eso esta función NO
    relaja nada: devuelve exactamente el texto que ve el modelo.

    Sin ella, un `"x" in msg["content"]` sobre una lista deja de ser "¿contiene el texto?"
    y pasa a ser "¿es 'x' uno de los bloques?" — que es False SIEMPRE. Ese es un gate que
    no puede ponerse verde: no medía la propiedad, medía el tipo del contenedor. Falla en
    seguro por diseño: ante una forma inesperada devuelve texto vacío o su `str()`, nunca
    algo que haga pasar una aserción de presencia por accidente.
    """
    c = msg.get("content")
    if isinstance(c, str):
        return c
    if isinstance(c, list):
        return "".join(str(b.get("text") or "") for b in c if isinstance(b, dict))
    return str(c or "")


def toks(messages: list[dict]) -> int:
    # Sobre el texto reconstruido (no sobre el repr de la lista de bloques): así a3/b3
    # comparan el tamaño del PROMPT, no el del contenedor con sus llaves y su cache_control.
    return sum(estimate_tokens(content_text(m)) for m in messages)


CONCLUSION = "CONCLUSIÓN Y RECOMENDACIÓN: procede la excepción de caducidad del medio de control."


def make_state(docs: list[dict] | None = None, metadata: dict | None = None) -> dict:
    return {
        "tenant_id": "t-gate-cp1", "matter_id": "m-gate-cp1",
        "messages": [{"role": "user", "content": "¿Caducó la acción de reparación directa?"}],
        "documents": docs or [],
        "profile_snapshot": {"despacho": "Defendemos aseguradoras."},
        "metadata": metadata or {},
    }


def expediente_docs(user: str) -> str:
    """Material de documentos del user prompt, sin la instrucción de packs.

    El cupo de analysis recorta DOCUMENTOS (`shrink_documents`). STRATEGY_PACK_INSTRUCTION
    se concatena después del expediente y no entra en ese cupo: medirla como expediente
    inflaba ~100 tokens (1304 vs 1200) sin que el recorte hubiera violado su contrato.
    """
    after = user.split("Expediente:\n", 1)[1]
    instr = legal_packs.STRATEGY_PACK_INSTRUCTION
    if instr in after:
        after = after.split(instr, 1)[0].rstrip()
    return after


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
          # CP-S1: los documentos van sellados (<<<DOC n>>>) en vez de "[doc n]".
          "<<<DOC 1>>>" in user2 and "hecho jurídico relevante" in user2)
    # RUPTURA ESPERADA del contrato viejo. Antes este check exigía "se tira la mitad"
    # (doc 5..8 fuera) — codificaba el defecto, no la propiedad: `shrink_documents` partía
    # por la mitad A CIEGAS, sin mirar si cabían. Con el recorte por presupuesto los 8
    # extractos caben en el cupo del nodo (medido: 1195 de 1200 tokens renderizados) y
    # ninguno se descarta; lo que se recorta es el LARGO. No se debilita nada: se sustituye
    # por dos aserciones más exigentes —ninguna pieza de evidencia se pierde Y el contenido
    # sí se acortó de verdad— que el check anterior no podía distinguir.
    docs_2 = expediente_docs(user2)
    check("a6 · ya no se descarta evidencia que CABE: los 8 extractos siguen presentes",
          all(f"[doc original {i}]" in user2 for i in range(8)))
    check("a6d · el retry conserva la instrucción del strategy-pack (no se recorta)",
          legal_packs.STRATEGY_PACK_INSTRUCTION in user2)
    check("a7b · pero el contenido sí se acortó (ningún documento entra íntegro)",
          all(d["content"] not in docs_2 for d in docs))
    budget_a = cr.budget_for("analysis", config.MIA_CONTEXT_WINDOW)
    usado_a = estimate_tokens(docs_2)
    check(f"a6b · el expediente reducido CABE en el presupuesto del nodo "
          f"({usado_a} <= {budget_a})", usado_a <= budget_a)
    check(f"a6c · y APROVECHA ese presupuesto en vez de quedarse en la mitad "
          f"({usado_a * 100 // budget_a}% >= 80%)", usado_a >= int(budget_a * 0.8))
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
        state_b = make_state(metadata={"diagnosis": diag, **legal_packs.example_metadata_packs()})
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
    # CP6: el índice de playbooks vive en el SYSTEM (capa L9 de la fachada), no en el
    # user — el marcador de recorte lo acompaña allí.
    # El system se lee con content_text (ver arriba) porque en esta cadena (claude-sonnet)
    # llega partido en bloques de content por el prefix caching. La propiedad que se mide
    # es la MISMA de siempre y sigue siendo exigente en los tres frentes: el índice está en
    # el system, el marcador de recorte lo acompaña, y el índice NO se coló al user.
    sys2 = content_text(fc.messages_seen[1][0])
    check("b5 · queda solo el índice de playbooks + marcador (en el system, capa L9)",
          pb_index in sys2 and cr.PLAYBOOKS_TRIMMED_MARKER in sys2
          and pb_index not in user2)
    check("b6 · la CONCLUSIÓN del diagnóstico sobrevive al recorte (protect_tail)",
          CONCLUSION in user2)
    check("b7 · el diagnóstico sí se recortó (marcador de sección en el 2º prompt)",
          cr.TEXT_CUT_MARKER in user2)
    check("b8 · el perfil del despacho se conserva", "Defendemos aseguradoras." in user2)
    check("b9 · el retry conserva la instrucción de seleccionados + locators",
          "Desarrolla SOLO estos argumentos seleccionados" in user2
          and "A1:" in user2 and "[doc 1]" in user2)

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
    # CONTRATO NUEVO de shrink_documents (sustituye al viejo "parte por la mitad"):
    #   1. la CANTIDAD la fija el presupuesto, no una división a ciegas;
    #   2. el presupuesto descuenta el peso del SELLADO, así que lo renderizado se acerca
    #      al cupo en vez de quedarse en la mitad;
    #   3. lo más relevante —incluido lo que el modelo PIDIÓ en la lectura adaptativa, que
    #      llega al final de la lista— no es lo primero en caer.
    many = [{"id": f"d{i}", "content": "contenido jurídico útil " * 100} for i in range(8)]
    entero = rendered_tokens(many)  # 4968 medido

    holgado = cr.shrink_documents(many, budget_tokens=entero - 200)
    check(f"d1 · con cupo casi suficiente NO se descarta ningún extracto (8→{len(holgado)}); "
          "el recorte viejo habría tirado 4 sin mirar el presupuesto", len(holgado) == 8)
    small = cr.shrink_documents(many, budget_tokens=400)
    mas_cupo = cr.shrink_documents(many, budget_tokens=800)
    # Esta es la aserción que separa "recorte por presupuesto" de "recorte por mitades":
    # con mitades ciegas los dos cupos dan 4 y 4, y este check no podría ponerse verde.
    check(f"d1b · doblar el cupo conserva MÁS extractos ({len(small)}→{len(mas_cupo)}): "
          "la cantidad la manda el presupuesto", len(mas_cupo) > len(small))
    check("d2 · shrink_documents trunca el contenido al presupuesto proporcional",
          all(estimate_tokens(d["content"]) < estimate_tokens(many[0]["content"]) for d in small))
    check("d3 · los documentos truncados llevan el sufijo marcador",
          all(d["content"].endswith("ver expediente completo]") for d in small))

    # d2b/d2c · CHECK DE UTILIZACIÓN (el que faltaba y por eso el desperdicio era invisible).
    # La aserción "<= presupuesto" sola mira el TECHO y no puede detectar jamás que se
    # desperdicie la mitad del cupo; hace falta mirar también el SUELO.
    for etiqueta, cupo in (("cupo apretado", 400), ("cupo casi suficiente", entero - 200)):
        res = cr.shrink_documents(many, budget_tokens=cupo)
        usado = rendered_tokens(res)
        check(f"d2b · {etiqueta}: lo recortado CABE renderizado ({usado} <= {cupo})",
              usado <= cupo)
        check(f"d2c · {etiqueta}: y OCUPA el cupo, no la mitad "
              f"({usado * 100 // cupo}% >= 80%)", usado >= int(cupo * 0.8))

    one = cr.shrink_documents([{"id": "d0", "content": "x" * 100000}], budget_tokens=100)
    check("d4 · nunca deja 0 documentos y conserva contenido útil",
          len(one) == 1 and len(one[0]["content"]) >= cr.MIN_DOC_TOKENS
          and one[0]["content"].startswith("x"))
    check("d5 · lista vacía → lista vacía (sin inventar documentos)",
          cr.shrink_documents([], budget_tokens=100) == [])
    check("d6 · los dicts de entrada no se mutan",
          many[0]["content"] == "contenido jurídico útil " * 100)

    # d1c..d1f · PRIORIDAD: lo que el modelo pidió deja de ser lo primero en caer.
    # La lectura adaptativa añade las ampliaciones AL FINAL de la lista, así que un recorte
    # que se queda con el principio las tiraba primero. Escenario calcado del medido por el
    # verificador: 8 iniciales + 12 ampliaciones, todas del mismo tamaño.
    inicial = [{"id": f"INICIAL-{i}", "content": f"INICIAL-{i} :: " + "x" * 8000,
                "score": 0.030 - i * 0.001} for i in range(8)]
    ampliado = [{"id": f"AMPL-{i}", "content": f"AMPL-{i} :: " + "x" * 8000,
                 "score": 0.032 - i * 0.001} for i in range(12)]
    mezcla = inicial + ampliado
    # Cupo elegido para que sobrevivan EXACTAMENTE 10 de 20, igual que en la medición del
    # recorte viejo (`docs[:len//2]`): a igual número de supervivientes se compara qué
    # sobrevive. Viejo: 2 de 12 ampliaciones. Aquí se exige el triple.
    recortado = cr.shrink_documents(mezcla, budget_tokens=900)
    vivos = [d["id"] for d in recortado]
    viejas = sum(1 for d in mezcla[: len(mezcla) // 2] if d["id"].startswith("AMPL"))
    n_ampl = sum(1 for i in vivos if i.startswith("AMPL"))
    check(f"d1c · a igual número de supervivientes ({len(vivos)} de 20), lo que el modelo "
          f"PIDIÓ ya no es lo primero en caer ({n_ampl} de 12 ampliaciones; el recorte por "
          f"mitades dejaba {viejas})", len(vivos) == 10 and n_ampl >= 3 * viejas)
    check("d1d · la salida conserva el ORDEN DE LLEGADA: la prioridad decide QUIÉN "
          "sobrevive, nunca quién es el [doc 1]",
          vivos == [d["id"] for d in mezcla if d["id"] in set(vivos)])
    # Correspondencia sello ↔ pieza: si se rompe, cada [doc n] del modelo apunta a otra
    # pieza que la que cuenta el guardián de citas.
    bloques = untrusted.render_documents(recortado).split("<<<DOC ")[1:]
    check("d1e · el bloque sellado n es exactamente el n-ésimo extracto entregado",
          len(bloques) == len(recortado)
          and all(b.startswith(f"{i + 1}>>>\n{recortado[i]['id']} ::")
                  for i, b in enumerate(bloques)))
    # Fail-soft: lo que el abogado adjunta a mano no trae `score`. Sin señal comparable NO
    # se reordena — degradar el material del abogado por no traer score sería el error
    # contrario y más grave.
    sin_score = [{"id": f"S{i}", "content": "x" * 8000} for i in range(20)]
    vivos_s = [d["id"] for d in cr.shrink_documents(sin_score, budget_tokens=900)]
    check("d1f · sin señal de relevancia se conserva el orden de llegada tal cual",
          0 < len(vivos_s) < 20
          and vivos_s == [f"S{i}" for i in range(len(vivos_s))])

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

    # === f · rescate CON material de AMPLIACIÓN presente (lectura adaptativa) ==========
    # Este camino no se ejercitaba: los gates de la lectura adaptativa terminan en el
    # `return` de agentic_expand y los de aquí usaban listas homogéneas. Es justo el cruce
    # donde la función se anulaba a sí misma: la lectura agéntica AÑADE material (hace el
    # recorte más probable) y el recorte tiraba primero lo añadido.
    docs_f = [dict(d) for d in inicial + ampliado]
    state_f = make_state(docs=docs_f)
    fc = install({"claude-sonnet": [context_exc(), ok_response("DIAGNÓSTICO: con ampliación.")]})
    out_f = asyncio.run(builder.analysis_node(state_f))
    check("f1 · el turno completa tras el rescate con ampliaciones en el expediente",
          out_f["metadata"].get("diagnosis") == "DIAGNÓSTICO: con ampliación.")
    user_f = fc.messages_seen[1][1]["content"]
    docs_f2 = expediente_docs(user_f)
    check("f4b · el retry conserva la instrucción del strategy-pack",
          legal_packs.STRATEGY_PACK_INSTRUCTION in user_f)
    vistos = [d["id"] for d in docs_f if f"{d['id']} ::" in docs_f2]
    ampl_vistas = sum(1 for i in vistos if i.startswith("AMPL"))
    check(f"f2 · tras el rescate el modelo SIGUE viendo lo que pidió "
          f"({ampl_vistas} de 12 ampliaciones en el prompt reducido)", ampl_vistas >= 6)
    check("f3 · y sigue viendo material inicial (no se cambió un sesgo por el opuesto)",
          len(vistos) - ampl_vistas >= 2)
    usado_f = estimate_tokens(docs_f2)
    check(f"f4 · el expediente reducido cabe en el presupuesto ({usado_f} <= {budget_a})",
          usado_f <= budget_a)
    check(f"f5 · y lo aprovecha ({usado_f * 100 // budget_a}% >= 80%): sin este check el "
          "desperdicio de la mitad del cupo era invisible", usado_f >= int(budget_a * 0.8))
    check("f6 · los documentos del estado NO se mutan en el rescate",
          all(len(d["content"]) > 8000 for d in docs_f))


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
