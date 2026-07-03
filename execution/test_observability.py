"""
Mia · test_observability.py — gate de CP-E1 (Ola 5): auditoría + tope de gasto.

Verifica contra Postgres REAL (RLS) el sink de auditoría y la política de gasto,
y con dobles la auditoría genérica del middleware y el mapeo a 402 del turno:

  A. observability.audit: record() escribe en audit_logs bajo RLS; sin tenant =
     no-op; campos largos recortados; FAIL-OPEN (tenant malformado no lanza);
     record_on_conn() escribe en una conexión transaccional; aislamiento por tenant.
  B. middleware: _maybe_audit audita métodos mutantes autenticados; NO audita GET,
     ni /api/speech/*, ni sin tenant.
  C. policy.budget: set/get del tope (roundtrip; null/<=0 = ilimitado);
     month_to_date_cost suma solo el mes en curso; budget_status; enforce_budget
     (ilimitado/bajo → pasa, superado → BudgetExceeded); FAIL-OPEN ante error de lectura.
  D. ruta del turno: BudgetExceeded → HTTP 402 con mensaje en llano.

Exit 0 = PASS · 1 = FAIL.     .venv\\Scripts\\python.exe execution\\test_observability.py
"""
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

_results: list = []


def check(name: str, ok) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _sb():
    import psycopg
    kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres",
              password=os.getenv("PG_PASSWORD", ""))
    return psycopg.connect(autocommit=True, **kw)


# ── B · middleware _maybe_audit (dobles) ─────────────────────────────────────────
async def middleware_checks() -> None:
    from mia.api import middleware as mw

    captured: list = []

    async def _fake_record(action, **kw):
        captured.append({"action": action, **kw})

    real = mw.audit.record
    mw.audit.record = _fake_record
    try:
        def _req(method, path, email="a@lexia.co"):
            return SimpleNamespace(method=method,
                                   url=SimpleNamespace(path=path),
                                   state=SimpleNamespace(email=email))
        resp = SimpleNamespace(status_code=200)

        captured.clear()
        await mw.TenantContextMiddleware._maybe_audit(
            _req("POST", "/api/matters/x/approve"), resp, "t-1")
        check("b-01 · POST autenticado → una fila de auditoría con método y ruta",
              len(captured) == 1 and captured[0]["action"] == "api_call"
              and captured[0]["entity_type"] == "POST"
              and captured[0]["entity_id"] == "/api/matters/x/approve"
              and captured[0]["payload"]["status"] == 200
              and captured[0]["tenant_id"] == "t-1")

        captured.clear()
        await mw.TenantContextMiddleware._maybe_audit(
            _req("GET", "/api/matters/x"), resp, "t-1")
        check("b-02 · GET (lectura) → NO se audita", captured == [])

        captured.clear()
        await mw.TenantContextMiddleware._maybe_audit(
            _req("POST", "/api/speech/transcribe"), resp, "t-1")
        check("b-03 · /api/speech/* (alta frecuencia) → NO se audita", captured == [])
    finally:
        mw.audit.record = real


# ── A · audit sink (DB real) + C · budget (DB real) ──────────────────────────────
async def db_checks() -> None:
    from mia.db import pool
    from mia.observability import audit
    from mia.policy import budget

    await pool.open_pool()
    ta = tb = None
    with _sb() as c:
        ta = str(c.execute("INSERT INTO tenants(name) VALUES('A obs cpe1') RETURNING id")
                 .fetchone()[0])
        tb = str(c.execute("INSERT INTO tenants(name) VALUES('B obs cpe1') RETURNING id")
                 .fetchone()[0])

    def _count_audit(tenant, action=None):
        with _sb() as c:
            if action:
                return c.execute("SELECT count(*) FROM audit_logs WHERE tenant_id=%s::uuid "
                                 "AND action=%s", (tenant, action)).fetchone()[0]
            return c.execute("SELECT count(*) FROM audit_logs WHERE tenant_id=%s::uuid",
                             (tenant,)).fetchone()[0]

    try:
        # A · record() escribe bajo RLS
        await audit.record("matter_turn", tenant_id=ta, user_email="pipe@lexia.co",
                           entity_type="matter", entity_id="m-1", payload={"k": "v"})
        check("a-01 · record() persiste la acción en audit_logs (RLS del tenant)",
              _count_audit(ta, "matter_turn") == 1)

        # sin tenant → no-op
        await audit.record("x", tenant_id=None)
        check("a-02 · record() sin tenant → no-op (no escribe nada)",
              _count_audit(ta) == 1)

        # campos largos recortados (action 60, entity_id 200) — no revienta el INSERT
        await audit.record("A" * 200, tenant_id=ta, entity_id="B" * 500)
        with _sb() as c:
            got = c.execute("SELECT length(action), length(entity_id) FROM audit_logs "
                            "WHERE tenant_id=%s::uuid ORDER BY created_at DESC LIMIT 1",
                            (ta,)).fetchone()
        check("a-03 · campos largos se recortan a los topes de columna (60/200)",
              got == (60, 200))

        # FAIL-OPEN: tenant malformado → no lanza
        raised = False
        try:
            await audit.record("x", tenant_id="no-es-uuid")
        except Exception:  # noqa: BLE001
            raised = True
        check("a-04 · record() con tenant malformado → FAIL-OPEN (no lanza)", not raised)

        # aislamiento por tenant: lo de ta no aparece en tb
        check("a-05 · aislamiento RLS: la auditoría de un despacho no cruza a otro",
              _count_audit(tb) == 0)

        # record_on_conn dentro de una transacción del tenant
        async with pool.tenant_connection(tb) as conn:
            await audit.record_on_conn(conn, "curator_proposal_applied", tenant_id=tb,
                                       entity_type="curator_proposal", entity_id="p-1",
                                       payload={"n": 1})
        check("a-06 · record_on_conn() escribe en la conexión transaccional dada",
              _count_audit(tb, "curator_proposal_applied") == 1)

        # C · budget: roundtrip del tope
        check("c-01 · sin tope configurado → get_monthly_budget None (ilimitado)",
              await budget.get_monthly_budget(ta) is None)
        await budget.set_monthly_budget(ta, 50.0)
        check("c-02 · set/get del tope → 50.0", await budget.get_monthly_budget(ta) == 50.0)
        await budget.set_monthly_budget(ta, None)
        check("c-03 · set None → ilimitado (None)", await budget.get_monthly_budget(ta) is None)
        await budget.set_monthly_budget(ta, -5.0)
        check("c-04 · set <= 0 → se interpreta como ilimitado (None)",
              await budget.get_monthly_budget(ta) is None)

        # c-04b/c · rama de PRODUCCIÓN (hallazgo capa 2 BLOQUEANTE): TODO tenant nace
        # con una fila tenant_settings (config='{}'), así que fijar el tope SIEMPRE
        # cae en la rama UPDATE. Debe persistir Y no pisar otras claves de config.
        with _sb() as c:
            c.execute("INSERT INTO tenant_settings (tenant_id, config) "
                      "VALUES (%s::uuid, '{\"model_policy\":\"nube\"}'::jsonb) "
                      "ON CONFLICT (tenant_id) DO UPDATE SET config = EXCLUDED.config",
                      (tb,))
        await budget.set_monthly_budget(tb, 30.0)
        check("c-04b · fijar el tope sobre fila tenant_settings YA EXISTENTE → PERSISTE",
              await budget.get_monthly_budget(tb) == 30.0)
        with _sb() as c:
            mp = c.execute("SELECT config->>'model_policy' FROM tenant_settings "
                           "WHERE tenant_id=%s::uuid", (tb,)).fetchone()[0]
        check("c-04c · fijar el tope NO pisa otras claves de config (model_policy intacto)",
              mp == "nube")
        await budget.set_monthly_budget(tb, None)  # limpia para los checks c-09 de tb

        # month_to_date_cost: suma solo el mes en curso
        with _sb() as c:
            c.execute("INSERT INTO turn_usage (tenant_id, model, cost_usd, created_at) "
                      "VALUES (%s::uuid, 'claude-sonnet', 3.00, now())", (ta,))
            c.execute("INSERT INTO turn_usage (tenant_id, model, cost_usd, created_at) "
                      "VALUES (%s::uuid, 'claude-sonnet', 1.50, now())", (ta,))
            c.execute("INSERT INTO turn_usage (tenant_id, model, cost_usd, created_at) "
                      "VALUES (%s::uuid, 'claude-sonnet', 99.00, "
                      "date_trunc('month', now()) - interval '5 days')", (ta,))
        spent = await budget.month_to_date_cost(ta)
        check("c-05 · month_to_date_cost suma SOLO el mes en curso (4.50, no 103.50)",
              abs(spent - 4.50) < 1e-6)

        # budget_status
        await budget.set_monthly_budget(ta, 10.0)
        st = await budget.budget_status(ta)
        check("c-06 · budget_status: presupuesto, gasto, restante, no superado",
              st["monthly_budget_usd"] == 10.0 and abs(st["spent_this_month_usd"] - 4.50) < 1e-6
              and abs(st["remaining_usd"] - 5.50) < 1e-6 and st["over_budget"] is False
              and st["unlimited"] is False)

        # enforce_budget: bajo el tope → pasa
        await budget.enforce_budget(ta)
        check("c-07 · enforce_budget bajo el tope → permite el turno (no lanza)", True)

        # sube el gasto por encima del tope → bloquea
        with _sb() as c:
            c.execute("INSERT INTO turn_usage (tenant_id, model, cost_usd, created_at) "
                      "VALUES (%s::uuid, 'claude-sonnet', 10.00, now())", (ta,))
        blocked = False
        try:
            await budget.enforce_budget(ta)
        except budget.BudgetExceeded as e:
            blocked = "tope de gasto" in str(e)
        check("c-08 · enforce_budget superado → BudgetExceeded con mensaje en llano", blocked)

        # ilimitado → nunca bloquea aunque haya gasto
        await budget.set_monthly_budget(tb, None)
        await budget.enforce_budget(tb)
        check("c-09 · sin tope (ilimitado) → enforce nunca bloquea", True)

        # FAIL-OPEN: si la lectura del gasto falla, se permite el turno
        real_cost = budget.month_to_date_cost

        async def _boom(_t):
            raise RuntimeError("DB caída (simulada)")

        budget.month_to_date_cost = _boom
        try:
            await budget.set_monthly_budget(ta, 1.0)  # tope bajo, pero el gasto no se puede leer
            allowed = True
            try:
                await budget.enforce_budget(ta)
            except budget.BudgetExceeded:
                allowed = False
            check("c-10 · error al leer el gasto → FAIL-OPEN (permite, no frena al abogado)",
                  allowed)
        finally:
            budget.month_to_date_cost = real_cost
    finally:
        with _sb() as c:
            for t in (ta, tb):
                if t:
                    c.execute("DELETE FROM audit_logs WHERE tenant_id=%s::uuid", (t,))
                    c.execute("DELETE FROM turn_usage WHERE tenant_id=%s::uuid", (t,))
                    c.execute("DELETE FROM tenant_settings WHERE tenant_id=%s::uuid", (t,))
                    c.execute("DELETE FROM tenants WHERE id=%s::uuid", (t,))
        await pool.close_pool()


# ── D · ruta del turno mapea BudgetExceeded → 402 ────────────────────────────────
async def route_checks() -> None:
    from fastapi import HTTPException
    from mia.api.routes import assistant as route
    from mia.policy import budget

    real = route.policy_budget.enforce_budget

    async def _over(_t):
        raise budget.BudgetExceeded("Este despacho alcanzó su tope de gasto de este mes.")

    route.policy_budget.enforce_budget = _over
    try:
        req = SimpleNamespace(state=SimpleNamespace(tenant_id="t-1", email="a@lexia.co"))
        body = route.ChatBody(message="hola")
        try:
            await route.assistant_chat(body=body, request=req)
            check("d-01 · turno del asistente sobre el tope → HTTP 402", False)
        except HTTPException as e:
            check("d-01 · turno del asistente sobre el tope → HTTP 402 en llano",
                  e.status_code == 402 and "tope de gasto" in e.detail)
    finally:
        route.policy_budget.enforce_budget = real


def main() -> int:
    print("== test_observability (CP-E1 · auditoría + tope de gasto) ==")
    asyncio.run(middleware_checks())
    asyncio.run(db_checks())
    asyncio.run(route_checks())

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
