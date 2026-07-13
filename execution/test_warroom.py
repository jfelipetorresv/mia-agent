"""
Mia · test_warroom.py — gate del motor de la Sala de estrategia (warroom).

Standalone, SIN DB y SIN red: el LLM del builder y el tope de gasto están MOCKEADOS.
Verifica el motor de agents/warroom.py:
  · selección de panel (propose_panel / build_panel);
  · orquestación de rondas (posturas → réplicas → dictamen) y sus eventos SSE;
  · que CADA intervención Y la síntesis pasan por annotate_draft (inyecta un [doc 9]
    fantasma y comprueba que se marca [VERIFICAR]);
  · parseo del dictamen del moderador al shape `conclusions`;
  · fail-soft del parseo (dictamen sin bloque → texto crudo en `estrategia`);
  · degradado por presupuesto (3 panelistas, sin ronda de réplicas);
  · guarda de "sin documentos".

    .venv\\Scripts\\python.exe execution\\test_warroom.py

Exit 0 = PASS · exit 1 = FAIL.
"""
from __future__ import annotations
import asyncio
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

from mia.agents import warroom  # noqa: E402
from mia.agents import verification  # noqa: E402
from mia.agents.warroom import (  # noqa: E402
    Panelist, WarRoomError, build_panel, parse_warroom_dictamen, propose_panel, run_warroom,
)

MARK = verification.VERIFY_MARK

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# Un dictamen bien formado que el FakeBuilder devuelve como salida del moderador.
_GOOD_DICTAMEN = (
    "El panel debatió con posturas encontradas.\n\n"
    f"{warroom.DICTAMEN_HEADER}\n"
    "Tesis viable: Con reservas\n"
    "Fortalezas:\n"
    "- La caducidad no operó según [doc 1]\n"
    "- Hay prueba documental del contrato\n"
    "Riesgos:\n"
    "- Falta acreditar la notificación\n"
    "Puntos ciegos:\n"
    "- No se analizó la competencia territorial\n"
    "Estrategia: Contestar oponiendo la excepción de pago y pedir la práctica de un dictamen.\n"
    "Próximo paso: Radicar la contestación antes del vencimiento del término.\n"
    f"{warroom.DICTAMEN_FOOTER}"
)


class FakeBuilder:
    """Sustituye a MatterGraphBuilder: solo necesita `_llm`. Los panelistas devuelven un
    texto con una cita [doc 9] FANTASMA (el expediente de prueba tiene 2 documentos) y una
    cita legal sin respaldo, para verificar que annotate_draft las marca [VERIFICAR]. El
    moderador devuelve `moderator_text`."""

    def __init__(self, moderator_text: str = _GOOD_DICTAMEN) -> None:
        self.moderator_text = moderator_text
        self.panelist_calls = 0
        self.moderator_calls = 0

    async def _llm(self, messages, *, task="main", state=None, md=None, node="",
                   model=None, shrink=None):
        if node == "warroom_moderator":
            self.moderator_calls += 1
            return self.moderator_text, None
        self.panelist_calls += 1
        # [doc 9] es fantasma (solo hay 2 docs); la Ley 9999 de 2020 no está respaldada.
        return ("Mi postura se apoya en el poder [doc 9] y en la Ley 9999 de 2020.", None)


class FailingRoundBuilder:
    """MAYOR 1 · un panelista (el de `fail_stance_label`) FALLA en la ronda 1 → la lista de
    turnos de la ronda 1 queda COMPACTADA. Cada panelista emite un marcador único
    ('POSTURA-<label>') en la ronda 1; se capturan los prompts de la ronda 2 para verificar
    que NINGÚN panelista recibe su propia intervención como si fuera de otro."""

    def __init__(self, fail_stance_label: str) -> None:
        self.fail_stance_label = fail_stance_label
        self.round2_prompts: dict[str, str] = {}  # stance_label → user prompt de la ronda 2
        self.moderator_calls = 0

    @staticmethod
    def _stance_of(messages) -> str:
        # Primera línea del user: "Postura que te toca defender: <label>."
        first = messages[1]["content"].splitlines()[0]
        return first.split(":", 1)[1].strip().rstrip(".")

    async def _llm(self, messages, *, task="main", state=None, md=None, node="",
                   model=None, shrink=None):
        if node == "warroom_moderator":
            self.moderator_calls += 1
            return _GOOD_DICTAMEN, None
        user = messages[1]["content"]
        stance = self._stance_of(messages)
        if "Entrega tu réplica" in user:  # ronda 2
            self.round2_prompts[stance] = user
            return (f"REPLICA-{stance}", None)
        # ronda 1
        if stance == self.fail_stance_label:
            raise RuntimeError("panelista caído en ronda 1 (simulado)")
        return (f"POSTURA-{stance}", None)


def _state(docs=None, tenant="11111111-1111-1111-1111-111111111111"):
    return {
        "tenant_id": tenant,
        "matter_id": "22222222-2222-2222-2222-222222222222",
        "messages": [{"role": "user", "content": "¿Cómo contesto esta demanda?"}],
        "documents": docs if docs is not None else [
            {"id": "d1", "content": "Contrato de arrendamiento."},
            {"id": "d2", "content": "Demanda ejecutiva."},
        ],
        "metadata": {},
    }


async def _budget_ok(_tenant):
    return {"over_budget": False, "unlimited": True}


async def _budget_over(_tenant):
    return {"over_budget": True, "unlimited": False}


async def _no_extra_patterns(_tenant):
    return None


async def _checks() -> None:
    # Neutraliza la lectura del pack de jurisdicción (evita DB); base patterns bastan.
    warroom._extra_patterns = _no_extra_patterns  # type: ignore[assignment]

    # ── 1 · propose_panel ────────────────────────────────────────────────────
    panel = propose_panel(_state())
    check("propose_panel con expediente → 4 panelistas", len(panel) == 4)
    stances = [p.stance for p in panel]
    check("propose_panel incluye las 4 posturas",
          stances == ["defensor", "contraparte", "juez", "especialista"])
    check("panelistas sintéticos → persona_id None",
          all(p.persona_id is None for p in panel))
    labels = {p.stance: p.stance_label for p in panel}
    check("stance_label defensor = 'Defiende tu tesis'",
          labels["defensor"] == "Defiende tu tesis")
    check("stance_label contraparte = 'Perspectiva de la contraparte'",
          labels["contraparte"] == "Perspectiva de la contraparte")
    check("stance_label juez = 'Juez escéptico'", labels["juez"] == "Juez escéptico")
    check("stance_label especialista lleva el área (default 'derecho procesal')",
          "derecho procesal" in labels["especialista"])
    check("cada panelista tiene un Persona con role_prompt no vacío",
          all(p.persona.role_prompt.strip() for p in panel))
    check("to_public expone el shape Panelist del contrato",
          set(panel[0].to_public().keys()) == {"persona_id", "stance", "name",
                                                "stance_label", "focus"})

    # Área concreta desde metadata → especialista con esa área.
    st_area = _state()
    st_area["metadata"]["area"] = "derecho tributario"
    p_area = propose_panel(st_area)
    check("especialista deriva el área de metadata",
          "derecho tributario" in p_area[-1].stance_label)

    # Sin expediente y sin señal → panel de 3 (sin especialista).
    p3 = propose_panel({"documents": [], "metadata": {}})
    check("propose_panel sin expediente ni área → 3 panelistas (sin especialista)",
          len(p3) == 3 and all(x.stance != "especialista" for x in p3))

    # ── 2 · build_panel (puente desde la selección del abogado) ──────────────
    bp = build_panel(_state(), [{"persona_id": None, "stance": "juez"},
                                {"persona_id": None, "stance": "defensor"}])
    check("build_panel respeta las posturas seleccionadas",
          [x.stance for x in bp] == ["juez", "defensor"])
    bp_bad = build_panel(_state(), [{"persona_id": None, "stance": "no_existe"}])
    check("build_panel con stance desconocido → cae a 'defensor'",
          bp_bad[0].stance == "defensor")
    bp_empty = build_panel(_state(), [])
    check("build_panel con selección vacía → propone panel completo", len(bp_empty) == 4)

    # MENOR 5 · varias sillas con persona_id que NO resuelve (list_personas cayó a [] /
    # persona_id fantasma) y stance no conocido: NO se clonan N 'Defensor' idénticos, se
    # degrada a posturas sintéticas DIVERSAS (fail-soft, sin crashear).
    bp_div = build_panel(_state(), [
        {"persona_id": "ghost-1", "stance": "personalizado"},
        {"persona_id": "ghost-2", "stance": "personalizado"},
        {"persona_id": "ghost-3", "stance": "personalizado"},
    ], personas_disponibles=[])
    div_stances = [x.stance for x in bp_div]
    check("MENOR 5: personas no resueltas NO clonan 'defensor' (3 posturas distintas)",
          len(bp_div) == 3 and len(set(div_stances)) == 3)

    # ── 3 · guarda: sin documentos ───────────────────────────────────────────
    raised = False
    try:
        await run_warroom(FakeBuilder(), _state(docs=[]), propose_panel(_state()))
    except WarRoomError as e:
        raised = True
        msg_ok = "Sube documentos del expediente" in str(e)
    check("run_warroom sin documentos → WarRoomError", raised)
    check("el mensaje de la guarda es en llano (§G)", raised and msg_ok)

    # ── 4 · orquestación completa (presupuesto OK) ───────────────────────────
    warroom.policy_budget.budget_status = _budget_ok  # type: ignore[assignment]
    events: list[tuple[str, dict]] = []

    def emit(event, payload):
        events.append((event, payload))

    state = _state()
    builder = FakeBuilder()
    panel = propose_panel(state)
    result = await run_warroom(builder, state, panel, question="Contestación", emit=emit)

    ev_names = [e for e, _ in events]
    check("emite al menos un evento 'thinking'", ev_names.count("thinking") >= 1)
    counsel = [p for e, p in events if e == "counsel_turn"]
    check("ronda 1 + ronda 2 → 8 intervenciones (4 panelistas × 2 rondas)",
          len(result.debate) == 8 and len(counsel) == 8)
    check("hay intervenciones de la ronda 2",
          any(t["round"] == 2 for t in result.debate))
    check("emite exactamente un 'conclusions_ready'",
          ev_names.count("conclusions_ready") == 1)

    # Cada intervención pasó por annotate_draft: el [doc 9] fantasma quedó marcado.
    check("TODA intervención del panel quedó anotada ([doc 9] fantasma → [VERIFICAR])",
          all(MARK in t["text"] for t in result.debate))
    check("panelist_calls = 8 (una llamada LLM por panelista y ronda)",
          builder.panelist_calls == 8)
    check("moderator_calls = 1", builder.moderator_calls == 1)

    # Verificación agregada: 8 intervenciones, cada una con 1 [doc n] fantasma ≥ 8.
    check("verification.docs_fantasma agregado ≥ 8", result.verification["docs_fantasma"] >= 8)
    check("verification.anotadas cuenta las citas legales sin respaldo (≥ 8)",
          result.verification["anotadas"] >= 8)

    # Panel persistido + resultado en el estado.
    check("result.panel tiene 4 panelistas (shape público)", len(result.panel) == 4)
    check("state['warroom_result'] persistido", isinstance(state.get("warroom_result"), dict))
    check("state['panel'] persistido", isinstance(state.get("panel"), list)
          and len(state["panel"]) == 4)
    check("generated_at es un ISO con zona horaria", "T" in result.generated_at
          and ("+" in result.generated_at or "Z" in result.generated_at))

    # ── 5 · parseo del dictamen ──────────────────────────────────────────────
    conc = result.conclusions
    check("dictamen: tesis_viable parseada", conc["tesis_viable"] == "Con reservas")
    check("dictamen: fortalezas como lista (2 ítems)", len(conc["fortalezas"]) == 2)
    check("dictamen: riesgos como lista (1 ítem)", len(conc["riesgos"]) == 1)
    check("dictamen: puntos_ciegos como lista (1 ítem)", len(conc["puntos_ciegos"]) == 1)
    check("dictamen: estrategia no vacía", conc["estrategia"].startswith("Contestar"))
    check("dictamen: proximo_paso no vacío", conc["proximo_paso"].startswith("Radicar"))

    # Parser unitario: normalización de la tesis y toma del último bloque.
    p_si = parse_warroom_dictamen(
        f"{warroom.DICTAMEN_HEADER}\nTesis viable: Sí, es viable\n"
        f"Estrategia: X\n{warroom.DICTAMEN_FOOTER}")
    check("parser normaliza 'Sí, es viable' → 'Sí'", p_si["tesis_viable"] == "Sí")
    p_riesgo = parse_warroom_dictamen(
        f"{warroom.DICTAMEN_HEADER}\nTesis viable: Riesgosa\n"
        f"Estrategia: X\n{warroom.DICTAMEN_FOOTER}")
    check("parser normaliza 'Riesgosa'", p_riesgo["tesis_viable"] == "Riesgosa")
    check("parser sin bloque → None", parse_warroom_dictamen("texto sin bloque") is None)

    # ── 6 · fail-soft del parseo ─────────────────────────────────────────────
    state_fs = _state()
    result_fs = await run_warroom(
        FakeBuilder(moderator_text="El panel concluyó pero no emití el bloque estructurado."),
        state_fs, propose_panel(state_fs))
    check("fail-soft: tesis_viable por defecto 'Con reservas'",
          result_fs.conclusions["tesis_viable"] == "Con reservas")
    check("fail-soft: el texto crudo del moderador va en 'estrategia'",
          "no emití el bloque" in result_fs.conclusions["estrategia"])
    check("fail-soft: listas vacías",
          result_fs.conclusions["fortalezas"] == []
          and result_fs.conclusions["riesgos"] == []
          and result_fs.conclusions["puntos_ciegos"] == [])

    # ── 7 · degradado por presupuesto ────────────────────────────────────────
    warroom.policy_budget.budget_status = _budget_over  # type: ignore[assignment]
    state_d = _state()
    builder_d = FakeBuilder()
    result_d = await run_warroom(builder_d, state_d, propose_panel(state_d))
    check("degradado: panel recortado a 3", len(result_d.panel) == 3)
    check("degradado: sin ronda de réplicas (solo 3 intervenciones)",
          len(result_d.debate) == 3 and all(t["round"] == 1 for t in result_d.debate))
    check("degradado: 3 llamadas de panelista (una ronda) + 1 moderador",
          builder_d.panelist_calls == 3 and builder_d.moderator_calls == 1)

    # MENOR 3 · degradación FUNCIONAL: cerca del tope (90% del presupuesto) SIN haberlo
    # superado (over_budget=False) — antes esta rama era código muerto porque usaba el mismo
    # umbral que enforce_budget (que 402ea al 100% antes del SSE).
    async def _budget_near(_tenant):
        return {"over_budget": False, "unlimited": False,
                "monthly_budget_usd": 100.0, "spent_this_month_usd": 90.0}

    warroom.policy_budget.budget_status = _budget_near  # type: ignore[assignment]
    state_n = _state()
    builder_n = FakeBuilder()
    result_n = await run_warroom(builder_n, state_n, propose_panel(state_n))
    check("MENOR 3: cerca del tope (90%) degrada aunque no lo haya superado",
          len(result_n.panel) == 3 and len(result_n.debate) == 3
          and all(t["round"] == 1 for t in result_n.debate))

    # Contraprueba: gasto bajo (30% del tope) NO degrada → panel completo + réplicas.
    async def _budget_low(_tenant):
        return {"over_budget": False, "unlimited": False,
                "monthly_budget_usd": 100.0, "spent_this_month_usd": 30.0}

    warroom.policy_budget.budget_status = _budget_low  # type: ignore[assignment]
    state_l = _state()
    result_l = await run_warroom(FakeBuilder(), state_l, propose_panel(state_l))
    check("MENOR 3: gasto bajo (30%) NO degrada (panel completo + réplicas)",
          len(result_l.panel) == 4 and len(result_l.debate) == 8)
    warroom.policy_budget.budget_status = _budget_ok  # type: ignore[assignment]

    # ── 8 · la SÍNTESIS del moderador también pasa por annotate_draft ─────────
    warroom.policy_budget.budget_status = _budget_ok  # type: ignore[assignment]
    dictamen_fantasma = (
        f"{warroom.DICTAMEN_HEADER}\n"
        "Tesis viable: Riesgosa\n"
        "Estrategia: Apoyarse en el anexo [doc 9] que respalda la excepción.\n"
        f"{warroom.DICTAMEN_FOOTER}"
    )
    state_s = _state()
    result_s = await run_warroom(
        FakeBuilder(moderator_text=dictamen_fantasma), state_s, propose_panel(state_s))
    check("la síntesis pasó por annotate_draft ([doc 9] fantasma en la estrategia → [VERIFICAR])",
          MARK in result_s.conclusions["estrategia"])

    # ── 9 · MAYOR 1 · réplicas alineadas ante fallo parcial de la ronda 1 ─────
    # 'contraparte' (índice 1 del panel) cae en la ronda 1 → round1_turns queda compactado.
    # Con el bug (exclusión por índice de lista) los panelistas de índice > 1 recibirían su
    # PROPIA intervención en la ronda 2. Con el fix (exclusión por panel_idx) nadie la recibe.
    warroom.policy_budget.budget_status = _budget_ok  # type: ignore[assignment]
    state_m1 = _state()
    panel_m1 = propose_panel(state_m1)  # defensor, contraparte, juez, especialista
    fail_label = next(p.stance_label for p in panel_m1 if p.stance == "contraparte")
    builder_m1 = FailingRoundBuilder(fail_stance_label=fail_label)
    result_m1 = await run_warroom(builder_m1, state_m1, panel_m1, question="Contestación")

    r1 = [t for t in result_m1.debate if t["round"] == 1]
    r2 = [t for t in result_m1.debate if t["round"] == 2]
    check("MAYOR 1: ronda 1 compactada (3 turnos; el caído no aparece)",
          len(r1) == 3 and all(t["stance_label"] != fail_label for t in r1))
    check("MAYOR 1: la ronda 2 corre para los 4 panelistas (incl. el que falló en R1)",
          len(r2) == 4 and len(builder_m1.round2_prompts) == 4)

    # El corazón del hallazgo: el prompt de réplica de cada panelista NO contiene su propio
    # marcador de la ronda 1.
    own_leak = [label for label, prompt in builder_m1.round2_prompts.items()
                if f"POSTURA-{label}" in prompt]
    check("MAYOR 1: NINGÚN panelista recibe su propia intervención en la ronda 2",
          own_leak == [])

    # Y sí recibe las de los DEMÁS supervivientes (otras no quedaron vacías por el fix).
    survivors = [p.stance_label for p in panel_m1 if p.stance_label != fail_label]
    def _sees_all_others(label: str) -> bool:
        prompt = builder_m1.round2_prompts.get(label, "")
        return all(f"POSTURA-{o}" in prompt for o in survivors if o != label)
    check("MAYOR 1: cada panelista sí recibe las intervenciones de los demás supervivientes",
          all(_sees_all_others(s) for s in survivors))


def main() -> int:
    print("== Motor de la Sala de estrategia (warroom) ==")
    asyncio.run(_checks())
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("warroom OK — motor de la Sala de estrategia verificado.")
        return 0
    print("warroom FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
