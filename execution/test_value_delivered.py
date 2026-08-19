"""
Mia · test_value_delivered.py — gate de CP-V1 (valor entregado / ROI — Ola 4).

Verifica OFFLINE (precios, buffer, scope por contexto, hook de call_llm) y contra DB
REAL (persistencia en turn_usage bajo RLS, configuración de tarifa por despacho):

  A. Precios: costo por alias (sonnet $3/$15 · haiku $1/$5 · cli-*/mia-local = 0);
     alias desconocido → 0 con aviso, jamás inventa un precio.
  B. Buffer: record sin scope = no-op; con scope bufferiza tokens/costo/source;
     el scope viaja a asyncio.to_thread (donde corre call_llm); cota MAX_BUFFER poda.
  C. Hook: _record_usage tolera respuestas sin usage / con usage raro y NUNCA lanza.
  D. DB: flush inserta por tenant bajo RLS (B no ve lo de A); suma del mes correcta;
     tenant borrado → re-encola una vez y luego descarta (degradación, no crash).
  E. Tarifa: defaults declarados; PUT valida rangos y persiste (upsert, merge JSONB);
     el GET refleja el cambio sin pisar los otros estimados.

Exit 0 = PASS · 1 = FAIL.     .venv\\Scripts\\python.exe execution\\test_value_delivered.py
"""
import asyncio
import os
import sys
from types import SimpleNamespace
from pathlib import Path

from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

_results: list = []


def check(name: str, ok) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _usage(prompt=1000, completion=500):
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                           total_tokens=prompt + completion)


def offline_checks() -> None:
    from mia.metrics import usage as um

    # ── A · precios ──────────────────────────────────────────────────────────
    check("v-01 · costo sonnet: 1M in + 1M out = $18.00",
          abs(um.cost_usd("claude-sonnet", 1_000_000, 1_000_000) - 18.0) < 1e-9)
    check("v-02 · costo haiku: 1M in + 1M out = $6.00",
          abs(um.cost_usd("claude-haiku", 1_000_000, 1_000_000) - 6.0) < 1e-9)
    check("v-03 · suscripción y local cuestan 0 (costo marginal del despacho)",
          um.cost_usd("cli-claude", 9_999_999, 9_999_999) == 0.0
          and um.cost_usd("cli-claude-haiku", 1, 1) == 0.0
          and um.cost_usd("mia-local", 1, 1) == 0.0)
    # v-04 · un alias SIN precio en la tabla se cobra a tarifa conservadora de Sonnet, no a 0.
    # El gate fijaba "costo 0 (no inventa precios)", pero f147fb9 (control atómico del gasto)
    # lo cambió a propósito y con razón: con 0, el gasto de un motor desconocido no se cuenta,
    # el tope mensual del despacho no frena y el abogado cree que no gastó. Sobreestimar es la
    # falla SEGURA cuando hay dinero de por medio; subestimar no lo es. Queda el warning que
    # avisa del alias sin precio.
    check("v-04 · alias desconocido → tarifa conservadora de Sonnet (el tope no se burla)",
          abs(um.cost_usd("modelo-fantasma", 1_000_000, 1_000_000)
              - sum(um.UNKNOWN_ALIAS_RATES)) < 1e-9)
    check("v-04b · los aliases gratis siguen costando 0 (no los toca la tarifa conservadora)",
          um.cost_usd("mia-local", 1_000_000, 1_000_000) == 0.0)

    # ── B · buffer y scope ───────────────────────────────────────────────────
    um.drain()
    um.record("claude-sonnet", "main", _usage())
    check("v-05 · record SIN scope es no-op (gates offline no ensucian métricas)",
          um.pending_count() == 0)

    tid = "11111111-1111-1111-1111-111111111111"
    tok = um.set_usage_scope(tid, source="api")
    try:
        um.record("claude-sonnet", "main", _usage(1000, 500))
        rows = um.drain()
        r = rows[0] if rows else {}
        check("v-06 · record CON scope: tenant/tokens/costo/source correctos",
              len(rows) == 1 and r.get("tenant_id") == tid
              and r.get("prompt_tokens") == 1000 and r.get("completion_tokens") == 500
              and r.get("total_tokens") == 1500
              and abs(r.get("cost_usd", 0) - 0.0105) < 1e-9
              and r.get("source") == "api" and r.get("model") == "claude-sonnet")

        # el scope viaja al thread (call_llm corre vía asyncio.to_thread)
        async def _in_thread():
            await asyncio.to_thread(um.record, "claude-haiku", "compression", _usage(10, 5))
        asyncio.run(_in_thread())
        rows = um.drain()
        check("v-07 · el scope viaja a asyncio.to_thread (contexto copiado)",
              len(rows) == 1 and rows[0]["tenant_id"] == tid
              and rows[0]["task"] == "compression")

        # usage estilo CLI de la suscripción (SimpleNamespace de subscription_llm)
        um.record("cli-claude", "main", _usage(2000, 800))
        rows = um.drain()
        check("v-08 · usage del CLI de la suscripción: tokens registrados, costo 0",
              rows and rows[0]["total_tokens"] == 2800 and rows[0]["cost_usd"] == 0.0)

        # cota del buffer: al llenarse poda lo más viejo, no crece sin límite
        old_max = um.MAX_BUFFER
        um.MAX_BUFFER = 10
        try:
            for i in range(12):
                um.record("mia-local", f"t{i}", _usage(1, 1))
            n = um.pending_count()
            check("v-09 · buffer acotado: con MAX=10 nunca supera el máximo",
                  n <= 10 and n > 0)
        finally:
            um.MAX_BUFFER = old_max
            um.drain()
    finally:
        um.reset_usage_scope(tok)

    # ── C · hook de call_llm jamás rompe un turno ────────────────────────────
    from mia.agent import llm as llm_mod
    tok = um.set_usage_scope(tid)
    try:
        llm_mod._record_usage("claude-sonnet", "main", SimpleNamespace())        # sin .usage
        llm_mod._record_usage("claude-sonnet", "main", None)                     # resp rara
        llm_mod._record_usage("claude-sonnet", "main", SimpleNamespace(usage="basura"))
        buffered = um.drain()
        # sin usage → no-op; usage no numérico → registro con 0s o descartado, sin excepción
        check("v-10 · _record_usage tolera respuestas sin/mal usage y no lanza",
              all(r["tenant_id"] == tid for r in buffered))
        llm_mod._record_usage("claude-sonnet", "main", SimpleNamespace(usage=_usage(7, 3)))
        rows = um.drain()
        check("v-11 · _record_usage con usage real bufferiza (hook cableado)",
              len(rows) == 1 and rows[0]["total_tokens"] == 10)
    finally:
        um.reset_usage_scope(tok)

    # ── B2 · fórmula de horas (capa 2 CP-V1, hallazgo A1: la tarjeta del panel) ──
    from mia.metrics.value import summarize_traces, DRAFT_MIN_CHARS

    mes = "2026-07"
    traces = [
        # borrador REAL: escrito sustancial aprobado este mes
        {"schema": "mia.trace.v2", "timestamp": "2026-07-02T10:00:00+00:00",
         "hitl_outcome": "approved", "draft_final": "x" * (DRAFT_MIN_CHARS + 1),
         "tokens": {"total": 1000}},
        # consulta: respuesta corta aprobada (hitl_outcome viene SIEMPRE del grafo)
        {"schema": "mia.trace.v2", "timestamp": "2026-07-02T11:00:00+00:00",
         "hitl_outcome": "approved", "output": "La acción no ha caducado.",
         "tokens": {"total": 200}},
        # EVENTO técnico (compresión de contexto): NO es trabajo del abogado
        {"schema": "mia.trace.event.v1", "timestamp": "2026-07-02T12:00:00+00:00",
         "tokens": {"total": 50}},
        # rechazado: no ahorró tiempo (conservador)
        {"schema": "mia.trace.v2", "timestamp": "2026-07-02T13:00:00+00:00",
         "hitl_outcome": "rejected", "draft_final": "y" * (DRAFT_MIN_CHARS + 1),
         "tokens": {"total": 900}},
        # de OTRO mes: fuera de conteos Y de tokens legacy (hallazgo M1)
        {"schema": "mia.trace.v2", "timestamp": "2026-06-15T10:00:00+00:00",
         "hitl_outcome": "approved", "draft_final": "z" * (DRAFT_MIN_CHARS + 1),
         "tokens": {"total": 5000}},
    ]
    r = summarize_traces(traces, mes)
    check("v-12 · fórmula: 1 borrador (escrito largo aprobado) y 1 consulta (respuesta corta)",
          r["drafts"] == 1 and r["turns"] == 1)
    check("v-13 · fórmula: eventos técnicos y turnos rechazados NO cuentan horas",
          r["drafts"] + r["turns"] == 2)
    check("v-14 · fórmula: los tokens legacy son SOLO del mes (no toda la historia)",
          r["legacy_tokens_month"] == 1000 + 200 + 50 + 900)
    r_junio = summarize_traces(traces, "2026-06")
    check("v-15 · fórmula: en junio solo cuenta el borrador de junio",
          r_junio["drafts"] == 1 and r_junio["turns"] == 0
          and r_junio["legacy_tokens_month"] == 5000)
    check("v-16 · fórmula: trazas raras (no-dict, sin timestamp) no rompen ni cuentan",
          summarize_traces([None, "x", {}], mes) == {"drafts": 0, "turns": 0,
                                                     "legacy_tokens_month": 0})


def _sb():
    import psycopg
    kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres",
              password=os.getenv("PG_PASSWORD", ""))
    return psycopg.connect(autocommit=True, **kw)


async def db_checks() -> None:
    import init_turn_usage
    from mia.api.routes import value as value_routes
    from mia.db import pool
    from mia.metrics import usage as um

    init_turn_usage.apply()
    await pool.open_pool()

    tenants: list[str] = []
    with _sb() as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A valor cpv1') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B valor cpv1') RETURNING id").fetchone()[0]
    ta, tb = str(a), str(b)
    tenants.extend([ta, tb])
    um.drain()
    try:
        # ── D · persistencia bajo RLS ────────────────────────────────────────
        tok = um.set_usage_scope(ta, source="api")
        um.record("claude-sonnet", "main", _usage(1000, 500))    # $0.0105
        um.record("claude-haiku", "verification", _usage(100, 50))  # $0.00035
        um.reset_usage_scope(tok)
        tok = um.set_usage_scope(tb, source="cron")
        um.record("cli-claude", "main", _usage(5000, 2000))      # $0
        um.reset_usage_scope(tok)

        inserted = await um.flush_pending()
        check("v-db1 · flush persiste las 3 filas (2 de A, 1 de B)", inserted == 3)

        async with pool.tenant_connection(ta) as conn:
            rows_a = await (await conn.execute(
                "SELECT model, cost_usd, source FROM turn_usage ORDER BY model")).fetchall()
            month_a = await (await conn.execute(
                "SELECT coalesce(sum(cost_usd),0), count(*) FROM turn_usage "
                "WHERE created_at >= date_trunc('month', now())")).fetchone()
        check("v-db2 · A ve SOLO sus 2 filas con su costo real",
              len(rows_a) == 2 and abs(float(month_a[0]) - 0.010850) < 1e-6
              and int(month_a[1]) == 2)

        async with pool.tenant_connection(tb) as conn:
            rows_b = await (await conn.execute(
                "SELECT model, cost_usd, source FROM turn_usage")).fetchall()
        check("v-db3 · RLS: B ve solo SU fila (suscripción, costo 0, source cron)",
              len(rows_b) == 1 and rows_b[0][0] == "cli-claude"
              and float(rows_b[0][1]) == 0.0 and rows_b[0][2] == "cron")

        check("v-db4 · flush con buffer vacío devuelve 0", await um.flush_pending() == 0)

        # degradación: tenant borrado → re-encola una vez, luego descarta (sin crash)
        with _sb() as c:
            tc = str(c.execute(
                "INSERT INTO tenants(name) VALUES('C efimero cpv1') RETURNING id").fetchone()[0])
        tok = um.set_usage_scope(tc)
        um.record("claude-sonnet", "main", _usage(10, 10))
        um.reset_usage_scope(tok)
        with _sb() as c:
            c.execute("DELETE FROM tenants WHERE id = %s::uuid", (tc,))
        n1 = await um.flush_pending()
        pend_after_1 = um.pending_count()
        n2 = await um.flush_pending()
        pend_after_2 = um.pending_count()
        check("v-db5 · tenant inexistente: re-encola 1 vez y luego descarta con log",
              n1 == 0 and pend_after_1 == 1 and n2 == 0 and pend_after_2 == 0)

        # ── E · configuración de tarifa por despacho ─────────────────────────
        cfg = await value_routes.value_settings_for(ta)
        check("v-db6 · defaults declarados: 100 USD/h · borrador 120 min · consulta 15 min",
              cfg["hourly_rate_usd"] == 100.0 and cfg["draft_minutes"] == 120
              and cfg["turn_minutes"] == 15 and cfg["is_default"] is True)

        req_a = SimpleNamespace(state=SimpleNamespace(tenant_id=ta))
        body = value_routes.ValueSettingsBody(hourly_rate_usd=250.0)
        out = await value_routes.put_value_settings(body, req_a)
        check("v-db7 · PUT tarifa 250: persiste (upsert) y conserva los otros estimados",
              out["hourly_rate_usd"] == 250.0 and out["draft_minutes"] == 120
              and out["is_default"] is False)

        cfg_b = await value_routes.value_settings_for(tb)
        check("v-db8 · la tarifa es POR DESPACHO: B sigue en defaults",
              cfg_b["hourly_rate_usd"] == 100.0 and cfg_b["is_default"] is True)

        from fastapi import HTTPException
        try:
            await value_routes.put_value_settings(
                value_routes.ValueSettingsBody(hourly_rate_usd=0), req_a)
            bad = False
        except HTTPException as exc:
            bad = exc.status_code == 422
        try:
            await value_routes.put_value_settings(
                value_routes.ValueSettingsBody(draft_minutes=999), req_a)
            bad2 = False
        except HTTPException as exc:
            bad2 = exc.status_code == 422
        check("v-db9 · PUT valida rangos (tarifa 0 y 999 min → 422 en llano)", bad and bad2)

        # merge JSONB: cambiar minutos no pisa la tarifa ya fijada
        await value_routes.put_value_settings(
            value_routes.ValueSettingsBody(draft_minutes=90), req_a)
        cfg2 = await value_routes.value_settings_for(ta)
        check("v-db10 · merge: cambiar minutos conserva la tarifa (250) y viceversa",
              cfg2["hourly_rate_usd"] == 250.0 and cfg2["draft_minutes"] == 90)

        # RLS fail-closed: SIN GUC de tenant (conexión plana de la app), turn_usage
        # no entrega NINGUNA fila ajena (0 filas o error — jamás datos).
        try:
            async with pool.get_pool().connection() as conn:
                naked = await (await conn.execute(
                    "SELECT count(*) FROM turn_usage")).fetchone()
            closed = int(naked[0]) == 0
        except Exception:
            closed = True  # negar acceso también es fail-closed
        check("v-db11 · RLS fail-closed: sin contexto de tenant, turn_usage devuelve 0 filas",
              closed)
    finally:
        um.drain()
        await pool.close_pool()
        with _sb() as c:
            for t in tenants:
                c.execute("DELETE FROM tenants WHERE id = %s::uuid", (t,))


def main() -> None:
    print("== CP-V1 · valor entregado (ROI) ==")
    offline_checks()
    asyncio.run(db_checks())
    passed = sum(1 for _, ok in _results if ok)
    print(f"\nRESULT: {passed}/{len(_results)} checks PASS")
    if passed != len(_results):
        sys.exit(1)
    print("Valor entregado OK — uso real capturado, RLS intacto, tarifa por despacho.")


if __name__ == "__main__":
    main()
