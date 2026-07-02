"""
Mia · test_blueprints.py — gate de CP-P2 (plantillas + sugerencias consent-first — Ola 2).

Verifica OFFLINE (catálogo, validación de plantillas, REGLA DURA) y contra DB REAL
(sugerencias consent-first, latch, máx 5, accept→automatización, RLS, ventana configurable):

  A. Catálogo: plantillas con campos en español; deadline_heads_up es procesal, calendar_heads_up no.
  B. fill_blueprint: valida rangos/tipos; defaults; plantilla desconocida → error.
  C. REGLA DURA: una plantilla procesal NUNCA calcula un término (fill solo trae params, sin
     fechas) y NUNCA se auto-activa (generate_suggestions PROPONE, crea 0 automatizaciones).
  D. Sugerencias consent-first: propose respeta el latch por dedup_key (aceptada/descartada
     no se re-ofrece) y el tope de 5 pendientes; accept crea la automatización; dismiss latchea.
  E. Automatizaciones: create/list/delete bajo RLS; B no ve las de A.
  F. Ventana configurable: la automatización deadline_heads_up cambia la ventana de aviso de
     la vigilancia de plazos (CP-P1) — sin calcular términos, solo la anticipación.

Exit 0 = PASS · 1 = FAIL.        .venv\\Scripts\\python.exe execution\\test_blueprints.py
"""
import asyncio
import os
import sys
from datetime import datetime, timedelta, timezone
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


def run_gate() -> None:
    from mia.cron import blueprints as bp

    # ── A · catálogo ─────────────────────────────────────────────────────────
    check("bp-01 · catálogo trae deadline_heads_up (procesal) y calendar_heads_up (no procesal)",
          bp.get_blueprint("deadline_heads_up").is_procedural is True
          and bp.get_blueprint("calendar_heads_up").is_procedural is False)
    entries = bp.catalog_entries()
    dhu = next((e for e in entries if e["key"] == "deadline_heads_up"), None)
    check("bp-02 · catalog_entries: nombre en español + campos con etiqueta y rango",
          dhu is not None and dhu["nombre"] and dhu["toca_plazo_procesal"] is True
          and dhu["campos"][0]["etiqueta"] and dhu["campos"][0]["min"] == 1)

    # ── B · fill_blueprint ───────────────────────────────────────────────────
    spec = bp.fill_blueprint("deadline_heads_up", {"dias_antes": 5})
    check("bp-03 · fill: valores válidos → spec con kind/is_procedural/params",
          spec["kind"] == "deadline_heads_up" and spec["is_procedural"] is True
          and spec["params"] == {"dias_antes": 5})
    spec_def = bp.fill_blueprint("deadline_heads_up", {})
    check("bp-04 · fill: sin valor → usa el default de la plantilla",
          spec_def["params"]["dias_antes"] == 3)

    def _raises(fn):
        try:
            fn()
            return False
        except bp.BlueprintFillError:
            return True

    check("bp-05 · fill: fuera de rango / no numérico / plantilla desconocida → error claro",
          _raises(lambda: bp.fill_blueprint("deadline_heads_up", {"dias_antes": 0}))
          and _raises(lambda: bp.fill_blueprint("deadline_heads_up", {"dias_antes": 99}))
          and _raises(lambda: bp.fill_blueprint("deadline_heads_up", {"dias_antes": "x"}))
          and _raises(lambda: bp.fill_blueprint("no_existe", {})))

    # ── C · REGLA DURA (offline): fill de una plantilla procesal NO calcula fechas ──
    proc_spec = bp.fill_blueprint("deadline_heads_up", {"dias_antes": 7})
    keys = set(proc_spec["params"].keys())
    check("bp-06 · regla dura: una plantilla procesal NO produce fechas/plazos (solo params)",
          proc_spec["is_procedural"] is True and keys == {"dias_antes"}
          and not any(k in str(proc_spec["params"]).lower() for k in ("due", "fecha", "vence")))


def _sb():
    import psycopg
    kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres",
              password=os.getenv("PG_PASSWORD", ""))
    return psycopg.connect(autocommit=True, **kw)


async def db_checks() -> None:
    import init_automations
    import init_reminders
    from mia.assistant.reminders import ReminderService
    from mia.cron import watch_engine as we
    from mia.cron.suggestions import (AutomationService, SuggestionService,
                                      generate_suggestions, MAX_PENDING)
    from mia.db import pool

    init_reminders.apply()
    init_automations.apply()
    await pool.open_pool()

    tenants: list[str] = []
    with _sb() as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A auto cpp2') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B auto cpp2') RETURNING id").fetchone()[0]
    ta, tb = str(a), str(b)
    tenants.extend([ta, tb])
    autos, sugg = AutomationService(), SuggestionService()
    try:
        # ── E · automatizaciones CRUD + RLS ──────────────────────────────────
        created = await autos.create(ta, "deadline_heads_up", {"dias_antes": 5})
        active = await autos.list_active(ta)
        check("bp-db1 · automatización: create→list_active la muestra con sus params",
              len(active) == 1 and active[0]["params"]["dias_antes"] == 5
              and active[0]["is_procedural"] is True)
        check("bp-db2 · RLS: el tenant B no ve las automatizaciones de A",
              await autos.list_active(tb) == [])

        # ── F · ventana configurable de la vigilancia de plazos (CP-P1) ──────
        win = await we._deadline_window_for(ta, 72)
        check("bp-db3 · ventana: la automatización (5 días) cambia la anticipación a 120h (5×24)",
              win == 120)
        check("bp-db4 · ventana: sin automatización, B usa el default (72h) — no calcula nada",
              await we._deadline_window_for(tb, 72) == 72)

        # la plantilla NO procesal calendar_heads_up también está cableada: ajusta la
        # ventana de la vigilancia de calendario (CP-P3).
        cal = await autos.create(ta, "calendar_heads_up", {"dias_antes": 3})
        check("bp-db4b · ventana calendario: la automatización (3 días) → 72h; sin ella, default 48h",
              await we._calendar_window_for(ta, 48) == 72
              and await we._calendar_window_for(tb, 48) == 48)
        await autos.delete(ta, cal["id"])

        # end-to-end regla dura: un plazo procesal a 100h (fuera de 72, dentro de 120) se
        # superficia GRACIAS a la automatización aceptada, y SIGUE llevando [VERIFICAR].
        now = datetime.now().astimezone()
        rid = await ReminderService().create(ta, None, "contestar la demanda",
                                             now + timedelta(hours=100), True)
        sent: list = []

        async def fake_notify(m):
            sent.append(m)
            return True

        watch = we.upcoming_deadlines_watch(
            resolve_tenant=lambda: ta, telegram_configured=lambda: True,
            window_resolver=we._deadline_window_for)
        r = await we.run_watch(watch, notify_fn=fake_notify, claim=False)
        check("bp-db5 · regla dura e2e: la ventana ampliada superficie el plazo con [VERIFICAR] "
              "(no calcula, solo lee la fecha del abogado)",
              r.get("surfaced") is True and sent and "[VERIFICAR]" in sent[0]
              and "contestar la demanda" in sent[0])
        _ = rid

        await autos.delete(ta, created["id"])
        check("bp-db6 · automatización: delete la quita (y vuelve al default de ventana)",
              await autos.list_active(ta) == [] and await we._deadline_window_for(ta, 72) == 72)

        # ── C · REGLA DURA: generate_suggestions PROPONE, crea 0 automatizaciones ──
        # (ya hay un recordatorio procesal pendiente de ta) → debe proponer, no crear.
        proposed = await generate_suggestions(ta, service=sugg, automations=autos)
        check("bp-db7 · regla dura: generate_suggestions PROPONE el aviso de plazos (consent-first)",
              len(proposed) == 1 and proposed[0]["blueprint_key"] == "deadline_heads_up")
        check("bp-db8 · regla dura: generate NO auto-activó ninguna automatización (0 activas)",
              await autos.list_active(ta) == [])

        # ── D · consent-first: latch por dedup_key + accept crea la automatización ──
        again = await generate_suggestions(ta, service=sugg, automations=autos)
        check("bp-db9 · latch: no se re-propone lo ya pendiente (mismo dedup_key)", again == [])

        pend = await sugg.list_pending(ta)
        sug_id = pend[0]["id"]
        check("bp-db10 · sugerencia pendiente: nombre en español + marca de plazo procesal",
              pend[0]["toca_plazo_procesal"] is True and pend[0]["nombre"])
        accepted = await sugg.accept(ta, sug_id)
        check("bp-db11 · accept: crea la automatización (acto humano) y ya hay 1 activa",
              accepted and accepted["kind"] == "deadline_heads_up"
              and len(await autos.list_active(ta)) == 1)
        # aceptada → latcheada: generate ya no re-propone (hay automatización activa además)
        check("bp-db12 · tras aceptar, no se re-propone (latch de aceptada)",
              await generate_suggestions(ta, service=sugg, automations=autos) == [])

        # dismiss latch: proponer algo, descartarlo, y que no vuelva
        p = await sugg.propose(tb, "calendar_heads_up", {"dias_antes": 10},
                               dedup_key="calendar_heads_up", rationale="prueba")
        ok_dismiss = await sugg.dismiss(tb, p["id"])
        p2 = await sugg.propose(tb, "calendar_heads_up", {"dias_antes": 10},
                                dedup_key="calendar_heads_up", rationale="prueba")
        check("bp-db13 · dismiss: descartar latchea (mismo dedup_key no se re-ofrece)",
              ok_dismiss is True and p2 is None)

        # tope de 5 pendientes
        with _sb() as c:  # tenant limpio para contar el tope sin ruido
            t5 = str(c.execute("INSERT INTO tenants(name) VALUES('C tope cpp2') RETURNING id").fetchone()[0])
        tenants.append(t5)
        made = 0
        for i in range(7):
            got = await sugg.propose(t5, "calendar_heads_up", {"dias_antes": i + 2},
                                     dedup_key=f"k{i}", rationale="x")
            if got:
                made += 1
        pend5 = await sugg.list_pending(t5)
        check(f"bp-db14 · tope: solo {MAX_PENDING} sugerencias pendientes (las demás se descartan)",
              made == MAX_PENDING and len(pend5) == MAX_PENDING)

        # RLS de sugerencias
        check("bp-db15 · RLS: el tenant A no ve las sugerencias de C",
              all(s["id"] not in {x["id"] for x in pend5} for s in await sugg.list_pending(ta)))

        # ── concurrencia (revisión capa 2): el advisory lock serializa propose ──
        with _sb() as c:
            td = str(c.execute("INSERT INTO tenants(name) VALUES('D conc cpp2') RETURNING id").fetchone()[0])
            te = str(c.execute("INSERT INTO tenants(name) VALUES('E conc cpp2') RETURNING id").fetchone()[0])
        tenants.extend([td, te])
        # mismo dedup_key en paralelo → exactamente UNO gana, sin 500 (UNIQUE + lock)
        dup = await asyncio.gather(*[
            sugg.propose(td, "calendar_heads_up", {"dias_antes": 5},
                         dedup_key="dup", rationale="x") for _ in range(4)],
            return_exceptions=True)
        errs = [x for x in dup if isinstance(x, Exception)]
        wins = [x for x in dup if isinstance(x, dict)]
        check("bp-db16 · concurrencia: 4 propose del MISMO dedup → 1 gana, 0 errores, 1 fila",
              not errs and len(wins) == 1 and len(await sugg.list_pending(td)) == 1)
        # tope bajo carrera: 8 dedups distintos en paralelo → nunca más de MAX_PENDING
        await asyncio.gather(*[
            sugg.propose(te, "calendar_heads_up", {"dias_antes": i + 2},
                         dedup_key=f"c{i}", rationale="x") for i in range(8)],
            return_exceptions=True)
        check(f"bp-db17 · concurrencia: 8 propose distintos en paralelo → nunca > {MAX_PENDING} pendientes",
              len(await sugg.list_pending(te)) == MAX_PENDING)
    finally:
        with _sb() as c:
            c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))
        await pool.close_pool()


if __name__ == "__main__":
    run_gate()
    if os.getenv("PG_PASSWORD"):
        asyncio.run(db_checks())
    else:
        check("bp-db · SKIP (sin PG_PASSWORD): no se ejercitó la DB real", False)
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks PASS")
    if all(ok for _, ok in _results):
        print("plantillas + sugerencias OK — CP-P2 verificado (consent-first, latch, tope 5, "
              "regla dura: los plazos procesales no se auto-activan ni se calculan).")
        sys.exit(0)
    sys.exit(1)
