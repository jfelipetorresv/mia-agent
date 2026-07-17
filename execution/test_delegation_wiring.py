"""
Mia · test_delegation_wiring.py — gate del CABLEADO de la delegación (CP-HUB).

Ejercita la cadena completa que antes estaba MUERTA (`metadata['delegate']` lo leía el
grafo y nadie lo escribía nunca):

  A · delegate_intent (puro): detecta la orden explícita; falla al lado SEGURO.
  B · hub_gate (DB real): el candado. 'soberano' BLOQUEA aunque esté habilitado;
      sin habilitar bloquea; error de DB bloquea (fail-closed).
  C · graph._maybe_delegate (DB real): delega cuando debe, NO delega con 'soberano',
      degrada limpio si el CLI no está o falla, y la salida sigue SELLADA.
  D · hub_config.set_enabled: el merge jsonb atómico no pisa otras claves del config.

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_delegation_wiring.py
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agents import delegate_intent, untrusted           # noqa: E402
from mia.agents.graph import MatterGraphBuilder             # noqa: E402
from mia.db import pool                                     # noqa: E402
from mia.gateway import agent_hub, hub_config, hub_gate     # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))


def setup_data():
    with psycopg.connect(autocommit=True, **PG) as c:
        t = c.execute("INSERT INTO tenants(name) VALUES('T cableado CP-HUB') RETURNING id").fetchone()[0]
    return str(t)


def cleanup(t):
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = %s", (t,))


def set_policy(tenant_id: str, policy: str) -> None:
    """Fija config['model_policy'] del tenant por fuera de la app (postgres, sin RLS)."""
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s::jsonb) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = COALESCE(tenant_settings.config,'{}'::jsonb) || EXCLUDED.config",
            (tenant_id, f'{{"model_policy": "{policy}"}}'),
        )


def _state(tenant_id: str, message: str) -> dict:
    return {"tenant_id": tenant_id, "matter_id": "m-1", "metadata": {},
            "messages": [{"role": "user", "content": message}]}


class FakeHub:
    """Hub falso: registra qué prompt SALIÓ del equipo. `result` es lo que devuelve."""

    def __init__(self, result: agent_hub.InvokeResult) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def invoke_result(self, key, prompt, tenant_id):
        self.calls.append((key, prompt))
        return self.result


def _ok_hub(stdout: str = "el radicado está al despacho") -> FakeHub:
    return FakeHub(agent_hub.InvokeResult(
        agent_hub.STATUS_OK,
        untrusted.wrap_untrusted("salida de 'Asistente de navegación web'", stdout)))


# ── A · intención explícita (módulo puro) ──────────────────────────────────
def test_intent():
    d = delegate_intent.detect
    check("intención: 'usa el asistente de navegación web para…' → openclaw",
          d("usa el asistente de navegación web para buscar el estado del radicado") == "openclaw")
    check("intención: sin tildes ni mayúsculas (voz a texto) → openclaw",
          d("USA EL ASISTENTE DE NAVEGACION para revisar la rama judicial") == "openclaw")
    check("intención: 'pídele al editor de documentos que…' → claude_code",
          d("pídele al editor de documentos que arregle el formato") == "claude_code")
    check("intención: consulta jurídica normal → None (no delega, silencio)",
          d("resume los hechos del expediente y dime si prescribió la acción") is None)
    check("intención: mención SIN verbo de orden → None",
          d("el editor de documentos no me sirvió la semana pasada") is None)
    check("intención: NEGACIÓN ('no uses el…') → None (fail-closed)",
          d("no uses el asistente de navegación web, hazlo tú") is None)
    check("intención: DOS ayudantes nombrados → None (ambiguo, fail-closed)",
          d("usa el asistente de navegación web y el editor de documentos") is None)
    check("intención: verbo DESPUÉS del nombre no es orden → None",
          d("el asistente de navegación web ya lo usé ayer") is None)
    check("intención: la palabra suelta 'documentos' NO nombra a un ayudante",
          d("revisa los documentos del expediente y ejecuta el análisis") is None)
    check("intención: mensaje vacío → None", d("") is None and d(None) is None)


# ── B/C/D · candado + cableado + merge (DB real) ───────────────────────────
async def db_tests(t: str) -> dict:
    await pool.open_pool()
    obs = {}
    try:
        # ── B · el candado ────────────────────────────────────────────────
        set_policy(t, "suscripcion")
        obs["gate_no_optin"] = await hub_gate.delegation_allowed(t, "openclaw") == (
            False, hub_gate.REASON_NO_OPTIN)

        await hub_config.set_enabled(t, "openclaw", True)
        obs["gate_ok"] = await hub_gate.delegation_allowed(t, "openclaw") == (
            True, hub_gate.REASON_OK)

        # EL CANDADO: soberano bloquea AUNQUE esté habilitado.
        set_policy(t, "soberano")
        obs["gate_soberano"] = await hub_gate.delegation_allowed(t, "openclaw") == (
            False, hub_gate.REASON_SOBERANO)
        obs["still_enabled"] = await hub_config.is_enabled(t, "openclaw")  # sigue habilitado

        # fail-closed: la política no se puede leer (DB caída) → BLOQUEA.
        from mia.agent import llm as llm_mod
        orig = llm_mod.model_policy_for_strict

        async def boom(_tid):
            raise RuntimeError("DB caída")

        llm_mod.model_policy_for_strict = boom
        try:
            obs["gate_db_error"] = await hub_gate.delegation_allowed(t, "openclaw") == (
                False, hub_gate.REASON_ERROR)
        finally:
            llm_mod.model_policy_for_strict = orig

        # ── C · el cableado del grafo ─────────────────────────────────────
        msg = "usa el asistente de navegación web para buscar el estado del radicado"

        # C.1 · soberano → NO delega, NO invoca el CLI, y se lo dice al abogado.
        hub = _ok_hub()
        deleg = await MatterGraphBuilder(agent_hub=hub)._maybe_delegate(_state(t, msg))
        obs["sob_no_invoke"] = hub.calls == []          # ← cero bytes salieron del equipo
        obs["sob_blocked"] = (deleg or {}).get("estado") == "bloqueado"
        obs["sob_reason"] = (deleg or {}).get("motivo_interno") == hub_gate.REASON_SOBERANO
        obs["sob_no_salida"] = (deleg or {}).get("salida") is None
        obs["sob_plain"] = "Todo en mi equipo" in ((deleg or {}).get("mensaje") or "")

        # C.2 · sin pedirlo → None y el CLI NO se invoca (aunque todo esté permitido).
        set_policy(t, "suscripcion")
        hub = _ok_hub()
        gb = MatterGraphBuilder(agent_hub=hub)
        obs["no_intent_none"] = (await gb._maybe_delegate(
            _state(t, "resume los hechos del expediente"))) is None
        obs["no_intent_no_invoke"] = hub.calls == []

        # C.3 · pedido + habilitado + política OK → DELEGA.
        hub = _ok_hub()
        deleg = await MatterGraphBuilder(agent_hub=hub)._maybe_delegate(_state(t, msg))
        obs["fires_status"] = (deleg or {}).get("estado") == "ok"
        obs["fires_agent"] = (deleg or {}).get("agente") == "navegacion"  # slug neutro (§G)
        obs["fires_invoked"] = len(hub.calls) == 1 and hub.calls[0][0] == "openclaw"
        # Lo ÚNICO que salió es el mensaje del abogado (ni documentos ni hechos).
        obs["fires_prompt"] = hub.calls and hub.calls[0][1] == msg
        obs["fires_aviso"] = hub_gate.EXIT_NOTICE == (deleg or {}).get("aviso")
        # La salida sigue SELLADA como no confiable.
        salida = (deleg or {}).get("salida") or ""
        obs["fires_sealed"] = (salida.lstrip().startswith(untrusted.UNTRUSTED_NOTICE[:40])
                               and f"<<<{untrusted.GENERIC_LABEL}" in salida
                               and "<<<FIN" in salida)

        # C.4 · pedido pero el despacho NO lo habilitó → no sale nada.
        await hub_config.set_enabled(t, "openclaw", False)
        hub = _ok_hub()
        deleg = await MatterGraphBuilder(agent_hub=hub)._maybe_delegate(_state(t, msg))
        obs["off_no_invoke"] = hub.calls == []
        obs["off_blocked"] = (deleg or {}).get("estado") == "bloqueado"
        obs["off_reason"] = (deleg or {}).get("motivo_interno") == hub_gate.REASON_NO_OPTIN
        await hub_config.set_enabled(t, "openclaw", True)

        # C.5 · habilitado pero NO instalado → degrada limpio, en llano, sin jerga.
        hub = FakeHub(agent_hub.InvokeResult(
            agent_hub.STATUS_NOT_INSTALLED,
            "«Asistente de navegación web» no está instalado en este equipo. Puedes seguir "
            "sin él: Mia responde igual con el expediente y el corpus del despacho.",
            detail="binario no encontrado"))
        deleg = await MatterGraphBuilder(agent_hub=hub)._maybe_delegate(_state(t, msg))
        obs["ni_status"] = (deleg or {}).get("estado") == agent_hub.STATUS_NOT_INSTALLED
        obs["ni_plain"] = "no está instalado" in ((deleg or {}).get("mensaje") or "")
        obs["ni_no_jerga"] = not any(
            w in ((deleg or {}).get("mensaje") or "").lower()
            for w in ("cli", "binario", "subprocess", "exit", "stderr", "openclaw"))
        obs["ni_no_salida"] = (deleg or {}).get("salida") is None

        # C.6 · el CLI falla (D3: flag equivocado, exit≠0) → error limpio, turno vivo.
        hub = FakeHub(agent_hub.InvokeResult(
            agent_hub.STATUS_ERROR, "«Asistente de navegación web» no pudo completar la tarea.",
            detail="exit=2 stderr=unknown flag -p"))
        deleg = await MatterGraphBuilder(agent_hub=hub)._maybe_delegate(_state(t, msg))
        obs["err_status"] = (deleg or {}).get("estado") == agent_hub.STATUS_ERROR
        obs["err_no_salida"] = (deleg or {}).get("salida") is None
        obs["err_no_stderr"] = "unknown flag" not in ((deleg or {}).get("mensaje") or "")

        # C.7 · el hub REVIENTA → None, sin propagar (el turno del abogado no se rompe).
        class Exploding:
            def invoke_result(self, *a, **k):
                raise RuntimeError("kaboom")

        obs["raise_none"] = (await MatterGraphBuilder(agent_hub=Exploding())._maybe_delegate(
            _state(t, msg))) is None

        # ── D · merge jsonb atómico: no pisa otras claves del config ──────
        await hub_config.set_enabled(t, "hermes", True)
        cfg = await hub_config.get_hub_config(t)
        obs["merge_coexist"] = cfg.get("hermes") is True and cfg.get("openclaw") is True
        with psycopg.connect(autocommit=True, **PG) as c:
            pol = c.execute("SELECT config->>'model_policy' FROM tenant_settings "
                            "WHERE tenant_id = %s::uuid", (t,)).fetchone()
        # El bug del read-modify-write: habilitar un ayudante NO puede borrar la política.
        obs["merge_keeps_policy"] = pol and pol[0] == "suscripcion"
        return obs
    finally:
        await pool.close_pool()


def main() -> int:
    print("== CP-HUB · cableado de la delegación ==")
    test_intent()

    t = setup_data()
    try:
        obs = asyncio.run(db_tests(t))
    finally:
        cleanup(t)

    check("candado: habilitado + política normal → PERMITE", obs["gate_ok"])
    check("candado: sin habilitar → BLOQUEA (sin-opt-in)", obs["gate_no_optin"])
    check("CANDADO: política 'soberano' BLOQUEA aunque esté habilitado", obs["gate_soberano"])
    check("candado: 'soberano' no desactiva el toggle (el bloqueo es de política)",
          obs["still_enabled"])
    check("candado: no se puede leer la política (DB caída) → BLOQUEA (fail-closed)",
          obs["gate_db_error"])

    check("SOBERANO: el CLI NO se invoca — cero bytes salen del equipo", obs["sob_no_invoke"])
    check("soberano: el bloque queda estado='bloqueado'", obs["sob_blocked"])
    check("soberano: el motivo interno es 'soberano'", obs["sob_reason"])
    check("soberano: no hay salida del ayudante", obs["sob_no_salida"])
    check("soberano: al abogado se le explica en llano (sin jerga)", obs["sob_plain"])

    check("sin pedirlo: no delega (None)", obs["no_intent_none"])
    check("sin pedirlo: el CLI NO se invoca", obs["no_intent_no_invoke"])

    check("pedido + habilitado + política OK → DELEGA (estado='ok')", obs["fires_status"])
    check("delegación: el id público es el slug neutro, sin marca (§G)", obs["fires_agent"])
    check("delegación: se invoca el conector correcto, una sola vez", obs["fires_invoked"])
    check("delegación: sale SOLO el mensaje del abogado (ni documentos ni hechos)",
          obs["fires_prompt"])
    check("delegación: el turno lleva el aviso de que el texto salió del equipo",
          obs["fires_aviso"])
    check("delegación: la salida del CLI sigue SELLADA como no confiable (CP-S1)",
          obs["fires_sealed"])

    check("pedido pero NO habilitado: el CLI NO se invoca", obs["off_no_invoke"])
    check("pedido pero NO habilitado: se le dice al abogado (bloqueado)", obs["off_blocked"])
    check("pedido pero NO habilitado: motivo interno 'sin-opt-in'", obs["off_reason"])

    check("no instalado: degrada con estado='no_instalado'", obs["ni_status"])
    check("no instalado: mensaje en llano para el abogado", obs["ni_plain"])
    check("no instalado: sin jerga ni marca del CLI (§G)", obs["ni_no_jerga"])
    check("no instalado: no hay salida", obs["ni_no_salida"])

    check("CLI falla (D3, flag equivocado): estado='error', turno vivo", obs["err_status"])
    check("CLI falla: no hay salida", obs["err_no_salida"])
    check("CLI falla: el stderr NO se le muestra al abogado (va al log)", obs["err_no_stderr"])
    check("el hub revienta: _maybe_delegate devuelve None, no propaga", obs["raise_none"])

    check("merge jsonb: varios ayudantes coexisten", obs["merge_coexist"])
    check("merge jsonb: habilitar un ayudante NO pisa 'model_policy'", obs["merge_keeps_policy"])

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total}")
    if passed == total:
        print("Cableado de la delegación OK — CP-HUB verificado.")
        return 0
    print("Cableado FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
