"""Gate real del candado mensual atómico. Exit 0 = PASS."""
from __future__ import annotations

import asyncio
import concurrent.futures
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def admin():
    return psycopg.connect(
        host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "mia"), user="postgres",
        password=os.getenv("PG_PASSWORD", ""), autocommit=True,
    )


def reserve(tenant: str, amount: float) -> str | None:
    from mia.policy import budget
    try:
        return budget.reserve_call_sync(tenant, amount, model="claude-sonnet", task="main")
    except budget.BudgetExceeded:
        return None


async def main() -> None:
    import init_atomic_ai_budget
    from mia.db import pool
    from mia.metrics import usage
    from mia.policy import budget

    init_atomic_ai_budget.apply()
    tenant_a, tenant_b = str(uuid.uuid4()), str(uuid.uuid4())
    try:
        with admin() as c:
            for tid, name in ((tenant_a, "Atomic A"), (tenant_b, "Atomic B")):
                c.execute("INSERT INTO tenants(id,name) VALUES (%s::uuid,%s)", (tid, name))
                c.execute(
                    "INSERT INTO tenant_settings(tenant_id,config) VALUES "
                    "(%s::uuid,jsonb_build_object('policy',jsonb_build_object(" 
                    "'monthly_budget_usd',1.0)))",
                    (tid,),
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as ex:
            holds = list(ex.map(lambda _: reserve(tenant_a, 0.25), range(12)))
        accepted = [h for h in holds if h]
        check("a-01 · concurrencia: exactamente 4 reservas caben en USD 1", len(accepted) == 4)
        with admin() as c:
            row = c.execute(
                "SELECT spent_usd,reserved_usd FROM ai_budget_months WHERE tenant_id=%s::uuid",
                (tenant_a,),
            ).fetchone()
        check("a-02 · suma reservada nunca supera el tope", float(row[1]) == 1.0)

        budget.finish_call_sync(tenant_a, accepted[0], 0.05)
        replacement = reserve(tenant_a, 0.20)
        check("a-03 · liquidar por menos libera el excedente", replacement is not None)

        other = reserve(tenant_b, 0.75)
        check("a-04 · otro despacho tiene saldo independiente", other is not None)

        with admin() as c:
            c.execute("UPDATE ai_budget_holds SET expires_at=now()-interval '1 second' "
                      "WHERE id=%s::uuid", (replacement,))
        blocked_after_expiry = reserve(tenant_a, 0.01) is None
        with admin() as c:
            expired = c.execute("SELECT status,actual_usd FROM ai_budget_holds "
                                "WHERE id=%s::uuid", (replacement,)).fetchone()
        check("a-05 · corte incierto vence y conserva la estimación como gasto",
              blocked_after_expiry and expired[0] == "expired"
              and abs(float(expired[1]) - 0.20) < 1e-9)

        check("a-06 · motores local y suscripción reservan cero",
              usage.estimated_call_cost("mia-local", [], None) == 0
              and usage.estimated_call_cost("cli-claude", [], None) == 0)
        check("a-07 · alias pagado desconocido no evade el candado",
              usage.estimated_call_cost("modelo-nuevo", [{"content": "x"}], 100) > 0
              and usage.cost_usd("modelo-nuevo", 100, 100) > 0)

        # RLS: A no puede ver las reservas de B con la conexión de la aplicación.
        await pool.open_pool()
        async with pool.tenant_connection(tenant_a) as conn:
            visible_b = await (await conn.execute(
                "SELECT count(*) FROM ai_budget_holds WHERE tenant_id=%s::uuid", (tenant_b,)
            )).fetchone()
        check("a-08 · RLS oculta las reservas de otro despacho", int(visible_b[0]) == 0)

        # El router central degrada a local si el candado rechaza el motor pagado.
        from mia.agent import llm
        real_chains = dict(llm._TASK_FALLBACK_CHAINS)
        real_call = llm._call_with_retries
        real_reserve = budget.reserve_call_sync
        called: list[str] = []

        def reject_paid(*_args, **_kwargs):
            raise budget.BudgetExceeded("tope")

        def fake_call(_client, kwargs, _retries, **_kwargs):
            called.append(kwargs["model"])
            return SimpleNamespace(usage=SimpleNamespace(
                prompt_tokens=10, completion_tokens=10, total_tokens=20))

        token = usage.set_usage_scope(tenant_a)
        try:
            budget.reserve_call_sync = reject_paid
            llm._call_with_retries = fake_call
            llm._TASK_FALLBACK_CHAINS["atomic-test"] = ["claude-sonnet", "mia-local"]
            llm.call_llm([{"role": "user", "content": "hola"}], task="atomic-test")
            check("a-09 · tope alcanzado degrada a local sin frenar el trabajo",
                  called == ["mia-local"])

            llm._TASK_FALLBACK_CHAINS["atomic-paid-only"] = ["claude-sonnet"]
            paid_only_blocked = False
            try:
                llm.call_llm([{"role": "user", "content": "hola"}], task="atomic-paid-only")
            except budget.BudgetExceeded:
                paid_only_blocked = True
            check("a-10 · sin respaldo gratuito, una llamada pagada no evade el tope",
                  paid_only_blocked)
        finally:
            usage.reset_usage_scope(token)
            budget.reserve_call_sync = real_reserve
            llm._call_with_retries = real_call
            llm._TASK_FALLBACK_CHAINS.clear()
            llm._TASK_FALLBACK_CHAINS.update(real_chains)

        # Una caída transitoria al liberar no debe convertir una falla conocida en gasto.
        retry_hold = reserve(tenant_b, 0.10)
        real_once = budget._finish_call_once
        attempts = 0

        def flaky_finish(*args, **kwargs):
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                return False
            return real_once(*args, **kwargs)

        budget._finish_call_once = flaky_finish
        try:
            released = budget.finish_call_sync(tenant_b, retry_hold, None)
        finally:
            budget._finish_call_once = real_once
        with admin() as c:
            release_status = c.execute("SELECT status FROM ai_budget_holds WHERE id=%s::uuid",
                                       (retry_hold,)).fetchone()[0]
        check("a-11 · liberación reintenta una caída transitoria y evita gasto fantasma",
              released and attempts == 3 and release_status == "released")
    finally:
        await pool.close_pool()
        with admin() as c:
            for tid in (tenant_a, tenant_b):
                c.execute("DELETE FROM ai_budget_holds WHERE tenant_id=%s::uuid", (tid,))
                c.execute("DELETE FROM ai_budget_months WHERE tenant_id=%s::uuid", (tid,))
                c.execute("DELETE FROM tenant_settings WHERE tenant_id=%s::uuid", (tid,))
                c.execute("DELETE FROM tenants WHERE id=%s::uuid", (tid,))

    failed = [name for name, ok in results if not ok]
    print(f"\nAtomic budget: {len(results)-len(failed)}/{len(results)} PASS")
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    asyncio.run(main())
