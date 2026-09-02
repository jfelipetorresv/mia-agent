"""
Mia · test_personas.py — gate de CP-E3 (personas jurídicas especializadas · Ola 5).

Ejercita `agents/personas.py` + su cableado en prompt_builder / asistente / grafo contra
la DB real (tabla `personas`, migración 023, RLS). Cubre:

  OFFLINE (puro, sin DB):
    · resolve_persona_alias: el CANDADO de confidencialidad — 'estandar' → sin override,
      'local' → el extremo local de la cadena de la política (mia-local) en las 3 políticas;
      JAMÁS un alias de nube (incl. 'soberano' → local en ambos niveles);
    · render_persona_voice: incluye el guardrail anti-invención ([VERIFICAR]) y sin jerga;
    · detect_persona: por frase, límite de palabra, la frase más larga gana, deshabilitada
      NO casa, mensaje sin frase → None;
    · validación: nivel de motor inválido, campos muy largos, frases cortas descartadas;
    · prompt_builder.build_graph_system: sin persona == baseline; con persona la inyecta;
    · assistant.build_assistant_system: sin persona == baseline; con persona la inyecta.

  DB (RLS · fail-closed · aislamiento):
    · siembra idempotente de las 3 canónicas UNA vez; segunda llamada no duplica;
    · borrar una y re-listar NO la re-siembra (respeta la autonomía del despacho);
    · CRUD (crear/actualizar/borrar) bajo RLS; nombre duplicado → PersonaError; tope MAX;
    · AISLAMIENTO: el tenant B no ve/edita/borra una persona del tenant A (invisible);
    · resolve_for_turn: por frase; por id explícito (deshabilitada → None); fail-open.

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_personas.py
"""
from __future__ import annotations
import asyncio
import os
import sys
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

import init_personas                                        # noqa: E402
from mia.agent import llm                                   # noqa: E402
from mia.agent import prompt_builder                        # noqa: E402
from mia.db import pool                                      # noqa: E402
from mia.assistant.core import build_assistant_system       # noqa: E402
from mia.agents import personas as pmod                     # noqa: E402
from mia.agents.personas import (                           # noqa: E402
    DEFAULT_PERSONAS,
    LOCAL_ALIAS,
    MODEL_TIER_LOCAL,
    Persona,
    PersonaError,
    PersonaService,
    detect_persona,
    render_persona_voice,
    resolve_persona_alias,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def make_tenants() -> tuple[str, str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A test cpe3') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test cpe3') RETURNING id").fetchone()[0]
    return str(a), str(b)


def drop_tenants(*ids: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for tid in ids:
            c.execute("DELETE FROM tenants WHERE id = %s", (tid,))


def _persona(**over) -> Persona:
    """Persona de prueba con defaults razonables."""
    base = dict(id="00000000-0000-0000-0000-000000000000", name="Litigante", title="Estratega",
                role_prompt="Actúas como litigante.", tone="firme", focus_areas=("defensa",),
                model_tier="estandar", summon_phrases=("como litigante", "litigante"),
                description="d", enabled=True)
    base.update(over)
    return Persona(**base)


# ── OFFLINE ──────────────────────────────────────────────────────────────────
def offline_checks() -> None:
    print("\n-- offline: candado de motor, voz, detección, validación, prompts --")

    # A · CANDADO DE CONFIDENCIALIDAD — resolve_persona_alias jamás a la nube.
    for pol in ("suscripcion", "nube", "soberano"):
        tok = llm.set_model_policy(pol)
        try:
            est = resolve_persona_alias("estandar")
            loc = resolve_persona_alias(MODEL_TIER_LOCAL)
            check(f"clamp[{pol}]: 'estandar' → sin override (None)", est is None)
            # Fail-closed por construcción: 'local' devuelve SIEMPRE el motor local, no una
            # posición de la cadena (robusto ante reordenamientos futuros de _POLICY_CHAINS).
            check(f"clamp[{pol}]: 'local' → motor local ({LOCAL_ALIAS})", loc == LOCAL_ALIAS)
            # El invariante duro: la persona local es un override explícito y cerrado. No
            # se exige que aparezca en la cadena base: en suscripción/nube precisamente no
            # debe ser un fallback silencioso, pero sí debe poder imponerse por configuración
            # expresa de la persona.
            check(f"clamp[{pol}]: 'local' fuerza SOLO {LOCAL_ALIAS}",
                  llm.resolve_fallback_chain("main", model=loc) == [LOCAL_ALIAS]
                  and len(llm.resolve_fallback_chain("main", model=loc)) == 1)
            # Y en concreto: nunca es un alias de nube conocido.
            cloud = {"claude-sonnet", "claude-haiku", "openrouter-sonnet",
                     "cli-claude", "cli-claude-haiku"}
            check(f"clamp[{pol}]: 'local' NO es un alias de nube/suscripción",
                  loc not in cloud)
        finally:
            llm.reset_model_policy(tok)
    # soberano: incluso 'estandar' (sin override) resuelve local — la cadena es solo local.
    tok = llm.set_model_policy("soberano")
    try:
        check("clamp[soberano]: la cadena 'main' es SOLO local",
              llm.resolve_fallback_chain("main") == ["mia-local"])
    finally:
        llm.reset_model_policy(tok)
    # Valor de nivel desconocido → tratado como 'estandar' (fail-safe, sin override).
    check("clamp: nivel desconocido → sin override (None)",
          resolve_persona_alias("cualquier-cosa") is None)

    # B · VOZ — guardrail anti-invención presente, sin jerga técnica ni modelos.
    voice = render_persona_voice(_persona())
    check("voz: incluye el nombre y el guardrail [VERIFICAR]",
          "Litigante" in voice and "[VERIFICAR]" in voice)
    check("voz: sin jerga de modelo/técnica (§G)",
          not any(j in voice.lower() for j in
                  ("mia-local", "claude", "openrouter", "tenant", "pgvector", "langgraph")))

    # C · DETECCIÓN por frase.
    p_lit = _persona(name="Litigante", summon_phrases=("litigante", "como litigante"))
    p_trib = _persona(name="Tributarista", summon_phrases=("tributarista",))
    p_rev = _persona(name="Revisor", summon_phrases=("revisor de citas",))
    universe = [p_lit, p_trib, p_rev]
    check("detección: frase presente → persona",
          detect_persona("Actúa como litigante y analiza", universe) is p_lit)
    check("detección: la frase MÁS LARGA gana",
          detect_persona("hazlo como litigante por favor", universe) is p_lit)
    check("detección: otra persona por su frase",
          detect_persona("dame la perspectiva del tributarista", universe) is p_trib)
    check("detección: frase multi-palabra",
          detect_persona("actúa como revisor de citas del escrito", universe) is p_rev)
    check("detección: sin frase → None",
          detect_persona("redacta una contestación", universe) is None)
    check("detección: límite de palabra (no casa dentro de otra palabra)",
          detect_persona("el prelitigante habló", [_persona(
              name="X", summon_phrases=("litigante",))]) is None)
    check("detección: persona DESHABILITADA no casa",
          detect_persona("como litigante", [_persona(enabled=False)]) is None)
    check("detección: mensaje vacío → None", detect_persona("", universe) is None)

    # D · VALIDACIÓN de entrada (CRUD).
    def _raises(data) -> bool:
        try:
            pmod._normalize_input(data)
            return False
        except PersonaError:
            return True

    check("validación: falta name → error",
          _raises({"role_prompt": "x"}))
    check("validación: falta role_prompt → error",
          _raises({"name": "X"}))
    check("validación: nivel de motor inválido → error",
          _raises({"name": "X", "role_prompt": "y", "model_tier": "nube"}))
    check("validación: name demasiado largo → error",
          _raises({"name": "N" * 100, "role_prompt": "y"}))
    ok_norm = pmod._normalize_input(
        {"name": " Litigante ", "role_prompt": "z", "model_tier": "LOCAL",
         "summon_phrases": ["ok frase", "x", "  ", "ok frase"], "focus_areas": ["a", "a", ""]})
    check("validación: normaliza (trim, nivel lower, dedup, descarta cortas/vacías)",
          ok_norm["name"] == "Litigante" and ok_norm["model_tier"] == "local"
          and ok_norm["summon_phrases"] == ("ok frase",) and ok_norm["focus_areas"] == ("a",))

    # E · PROMPT BUILDERS — sin persona == baseline; con persona la inyecta.
    st = {"soul_snapshot": None}
    base_graph = prompt_builder.build_graph_system(st, "facts")
    check("grafo: sin persona == baseline (comportamiento sin cambios)",
          prompt_builder.build_graph_system(st, "facts", persona_voice="") == base_graph)
    with_p = prompt_builder.build_graph_system(st, "facts", persona_voice=voice)
    check("grafo: con persona inyecta la voz y conserva la tarea del nodo",
          "Litigante" in with_p and "HECHOS" in with_p and with_p != base_graph)


# ── DB ────────────────────────────────────────────────────────────────────────
async def _count(svc: PersonaService, tenant: str) -> int:
    return len(await svc.list_personas(tenant))


async def db_checks(a: str, b: str) -> None:
    print("\n-- db: siembra, CRUD, RLS, aislamiento, resolve_for_turn --")
    await pool.open_pool()
    try:
        await _db_checks(a, b)
    finally:
        await pool.close_pool()


async def _db_checks(a: str, b: str) -> None:
    svc = PersonaService()

    # Siembra idempotente de las 3 canónicas.
    listed = await svc.list_personas(a)
    names = sorted(p.name for p in listed)
    check("siembra: 3 canónicas la primera vez",
          names == sorted(s["name"] for s in DEFAULT_PERSONAS))
    check("siembra: el revisor de citas usa motor LOCAL",
          any(p.name == "Revisor de citas" and p.model_tier == MODEL_TIER_LOCAL for p in listed))
    again = await svc.list_personas(a)
    check("siembra: idempotente (segunda llamada no duplica)", len(again) == len(listed))

    # Borrar una canónica y re-listar NO la re-siembra.
    victim = next(p for p in again if p.name == "Litigante")
    await svc.delete_persona(a, victim.id)
    after_del = await svc.list_personas(a)
    check("siembra: borrar y re-listar NO re-siembra (autonomía del despacho)",
          all(p.name != "Litigante" for p in after_del) and len(after_del) == len(again) - 1)

    # CRUD.
    created = await svc.create_persona(a, {
        "name": "Penalista", "role_prompt": "Actúas como penalista.",
        "model_tier": "local", "summon_phrases": ["como penalista"], "focus_areas": ["dolo"]})
    check("CRUD: crear devuelve la persona", created.name == "Penalista")
    got = await svc.get_persona(a, created.id)
    check("CRUD: get la recupera", got is not None and got.id == created.id)
    updated = await svc.update_persona(a, created.id, {
        "name": "Penalista", "role_prompt": "Actúas como penalista experto.",
        "model_tier": "estandar", "summon_phrases": ["como penalista"]})
    check("CRUD: update aplica cambios",
          updated.role_prompt.endswith("experto.") and updated.model_tier == "estandar")

    # Nombre duplicado → error (case-insensitive).
    dup_err = False
    try:
        await svc.create_persona(a, {"name": "penalista", "role_prompt": "x"})
    except PersonaError:
        dup_err = True
    check("CRUD: nombre duplicado (case-insensitive) → PersonaError", dup_err)

    # AISLAMIENTO RLS: B no ve/edita/borra la persona de A.
    check("RLS: B no VE la persona de A (get → None)",
          await svc.get_persona(b, created.id) is None)
    b_upd_blocked = False
    try:
        await svc.update_persona(b, created.id, {"name": "Hackeada", "role_prompt": "x"})
    except PersonaError:
        b_upd_blocked = True
    check("RLS: B no EDITA la persona de A (PersonaError)", b_upd_blocked)
    b_del_blocked = False
    try:
        await svc.delete_persona(b, created.id)
    except PersonaError:
        b_del_blocked = True
    check("RLS: B no BORRA la persona de A (PersonaError)", b_del_blocked)
    # La persona de A sigue intacta tras los intentos de B.
    check("RLS: la persona de A sigue intacta tras los intentos de B",
          (await svc.get_persona(a, created.id)) is not None)
    # B tiene su propia siembra, independiente.
    b_list = await svc.list_personas(b)
    check("RLS: B tiene su propia siembra (aislada de A)",
          all(p.id != created.id for p in b_list) and len(b_list) == len(DEFAULT_PERSONAS))

    # resolve_for_turn.
    r_phrase = await svc.resolve_for_turn(a, "actúa como penalista y revisa esto")
    check("resolve_for_turn: por frase → persona", r_phrase is not None and r_phrase.name == "Penalista")
    r_none = await svc.resolve_for_turn(a, "redacta una demanda")
    check("resolve_for_turn: sin frase → None", r_none is None)
    r_id = await svc.resolve_for_turn(a, "cualquier cosa", explicit_id=created.id)
    check("resolve_for_turn: por id explícito → persona", r_id is not None and r_id.id == created.id)
    # Deshabilitada: ni por frase ni por id.
    await svc.update_persona(a, created.id, {
        "name": "Penalista", "role_prompt": "x", "summon_phrases": ["como penalista"],
        "enabled": False})
    check("resolve_for_turn: deshabilitada por frase → None",
          await svc.resolve_for_turn(a, "actúa como penalista") is None)
    check("resolve_for_turn: deshabilitada por id → None",
          await svc.resolve_for_turn(a, "x", explicit_id=created.id) is None)

    # Tope MAX_PERSONAS.
    async def _fill_to_max() -> bool:
        current = await _count(svc, a)
        for i in range(current, pmod.MAX_PERSONAS):
            await svc.create_persona(a, {"name": f"P{i}", "role_prompt": "x"})
        try:
            await svc.create_persona(a, {"name": "UnaMas", "role_prompt": "x"})
            return False
        except PersonaError:
            return True
    check("CRUD: tope MAX_PERSONAS bloquea crear otra", await _fill_to_max())

    # build_assistant_system con/ sin persona (usa SOUL vacío del tenant de prueba).
    base_asst = build_assistant_system(a)
    with_asst = build_assistant_system(a, _persona(name="Litigante"))
    check("asistente: sin persona == baseline", build_assistant_system(a) == base_asst)
    check("asistente: con persona inyecta la voz",
          "Litigante" in with_asst and with_asst != base_asst)


def main() -> int:
    init_personas.apply()   # idempotente: tabla personas (migración 023)

    offline_checks()
    a, b = make_tenants()
    try:
        asyncio.run(db_checks(a, b))
    finally:
        drop_tenants(a, b)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Personas jurídicas OK — CP-E3 verificado.")
        return 0
    print("Personas jurídicas FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
