"""
Mia · test_watch_engine.py — gate de CP-P1 (motor de vigilancia programada — Ola 2).

Verifica OFFLINE (sin red; el claim usa DB admin real si está, con fallback fail-open):
  A. Wake-gate: una vigilancia cuyo check dice "nada que reportar" NO avisa ni gasta
     LLM; si dice "sí", avisa (no_agent) o despierta al agente (agent).
  B. no_agent vs agent: la vigilancia no_agent nunca llama al LLM; la 'agent' solo
     invoca on_surface (el LLM) DESPUÉS de que el wake-gate confirmó.
  C. at-most-once: run_watch pide el claim ANTES del trabajo; si otro worker lo tiene,
     se omite. El claim CAS es fail-open sin DB admin.
  D. after_surface: se marca el estado (heads_up) SOLO si el aviso se entregó.
  E. Vigilancia de plazos próximos: solo superficie plazos PROCESALES que el abogado
     fijó, dentro de la ventana; sin plazos → silencio; el mensaje lleva [VERIFICAR].
  F. Regla dura: la vigilancia NO calcula fechas (solo lee is_procedural + due_at).
  G. Cableado: build_scheduler registra la vigilancia 'upcoming_deadlines'.

Exit 0 = PASS · 1 = FAIL.        .venv\\Scripts\\python.exe execution\\test_watch_engine.py
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


async def run_gate() -> None:
    from mia.cron import watch_engine as we
    from mia.cron import build_scheduler
    from mia.cron.watch_engine import Watch, WatchResult, run_watch, upcoming_deadlines_watch

    # ── A/B · wake-gate + no_agent/agent ─────────────────────────────────────
    sent: list = []

    async def fake_notify(msg):
        sent.append(msg)
        return True

    # Vigilancia no_agent que NO debe superficiar (wake-gate cierra).
    async def check_silent():
        return WatchResult(False)

    w_silent = Watch("silent", 1, check_silent, kind="no_agent")
    r = await run_watch(w_silent, notify_fn=fake_notify, claim=False)
    check("p1-01 · wake-gate: check sin nada que reportar NO avisa",
          r.get("surfaced") is False and sent == [])

    # Vigilancia no_agent que SÍ superficia.
    async def check_surface():
        return WatchResult(True, message="hay algo", items=[{"id": "a"}])

    w_surface = Watch("surface", 1, check_surface, kind="no_agent")
    r = await run_watch(w_surface, notify_fn=fake_notify, claim=False)
    check("p1-02 · no_agent: al superficiar, avisa por el canal (sin LLM)",
          r.get("surfaced") is True and sent == ["hay algo"])

    # Vigilancia 'agent': el LLM (on_surface) solo se llama tras el wake-gate.
    llm_calls: list = []

    async def on_surface(result):
        llm_calls.append(result.message)
        return "resumen del agente"

    async def check_agent_no():
        return WatchResult(False)   # wake-gate cierra → on_surface NO se llama

    w_agent_no = Watch("agent_no", 1, check_agent_no, kind="agent", on_surface=on_surface)
    await run_watch(w_agent_no, claim=False)
    check("p1-03 · agent: wake-gate cerrado NO despierta al LLM (cero gasto)",
          llm_calls == [])

    async def check_agent_yes():
        return WatchResult(True, message="despierta")

    w_agent_yes = Watch("agent_yes", 1, check_agent_yes, kind="agent", on_surface=on_surface)
    r = await run_watch(w_agent_yes, claim=False)
    check("p1-04 · agent: wake-gate abierto SÍ despierta al LLM (una vez)",
          llm_calls == ["despierta"] and r.get("result") == "resumen del agente")

    # ── C · at-most-once (claim inyectado) ───────────────────────────────────
    claimed: list = []
    saved_claim, saved_release = we.claim_job, we.release_job

    async def fake_claim_win(name, **kw):
        claimed.append(name)
        return True

    async def fake_claim_lose(name, **kw):
        return False

    async def fake_release(name, **kw):
        pass

    we.claim_job = fake_claim_win
    we.release_job = fake_release
    try:
        sent.clear()
        r = await run_watch(w_surface, notify_fn=fake_notify)
        check("p1-05 · at-most-once: run_watch pide el claim antes del trabajo",
              claimed == ["surface"] and r.get("surfaced") is True)

        we.claim_job = fake_claim_lose
        sent.clear()
        r = await run_watch(w_surface, notify_fn=fake_notify)
        check("p1-06 · at-most-once: si otro worker tiene el claim, se OMITE (no repite)",
              r.get("skipped") is not None and sent == [])
    finally:
        we.claim_job, we.release_job = saved_claim, saved_release

    # Claim CAS fail-open sin DB admin (PG ausente → corre igual, single worker).
    import os as _os
    saved_pw = _os.environ.get("PG_PASSWORD")
    _os.environ.pop("PG_PASSWORD", None)
    try:
        won = await we.claim_job("x-sin-db")
        check("p1-07 · claim CAS es fail-open sin DB admin (no detiene la vigilancia)", won is True)
    finally:
        if saved_pw is not None:
            _os.environ["PG_PASSWORD"] = saved_pw

    # ── D · after_surface: marca solo si el aviso se entregó ──────────────────
    marks: list = []

    async def after_surface(result, ok):
        marks.append(("ok" if ok else "fail", [it["id"] for it in result.items]))

    w_after = Watch("after", 1, check_surface, kind="no_agent", after_surface=after_surface)
    await run_watch(w_after, notify_fn=fake_notify, claim=False)
    check("p1-08 · after_surface recibe ok=True cuando el canal aceptó",
          marks == [("ok", ["a"])])

    async def notify_fail(msg):
        return False

    marks.clear()
    await run_watch(w_after, notify_fn=notify_fail, claim=False)
    check("p1-09 · after_surface recibe ok=False cuando el envío falló (se reintentará)",
          marks == [("fail", ["a"])])

    # ── E/F · vigilancia de plazos próximos (con servicio doblado) ───────────
    now = datetime.now(timezone.utc)

    class _FakeService:
        def __init__(self, items):
            self._items = items
            self.marked: list = []
            self.queried_within = None

        async def upcoming_procedural(self, tenant_id, within_hours):
            self.queried_within = within_hours
            return list(self._items)

        async def mark_heads_up(self, tenant_id, ids):
            self.marked.append((tenant_id, list(ids)))

    proximo = {"id": "r1", "text": "radicar la tutela", "due_at": now + timedelta(hours=48),
               "is_procedural": True}
    svc = _FakeService([proximo])
    watch = upcoming_deadlines_watch(
        within_hours=72, resolve_tenant=lambda: "t-1", service=svc,
        telegram_configured=lambda: True)
    sent.clear()
    r = await run_watch(watch, notify_fn=fake_notify, claim=False)
    check("p1-10 · plazos: un plazo procesal próximo se superficia con aviso",
          r.get("surfaced") is True and len(sent) == 1)
    check("p1-11 · plazos: el aviso lleva [VERIFICAR] y el texto del recordatorio",
          "[VERIFICAR]" in sent[0] and "radicar la tutela" in sent[0])
    check("p1-12 · plazos: tras avisar, se marca heads_up (no re-avisa)",
          svc.marked == [("t-1", ["r1"])])
    check("p1-13 · la vigilancia pasa la ventana al servicio (la regla dura se prueba en p1-db1/2)",
          svc.queried_within == 72)

    # Sin plazos próximos → wake-gate cierra (silencio, sin aviso).
    svc_empty = _FakeService([])
    watch_empty = upcoming_deadlines_watch(
        resolve_tenant=lambda: "t-1", service=svc_empty, telegram_configured=lambda: True)
    sent.clear()
    r = await run_watch(watch_empty, notify_fn=fake_notify, claim=False)
    check("p1-14 · plazos: sin nada próximo → silencio (no avisa, no marca)",
          r.get("surfaced") is False and sent == [] and svc_empty.marked == [])

    # Canal sin configurar → silencio (opt-in de CP-B2).
    watch_nochan = upcoming_deadlines_watch(
        resolve_tenant=lambda: "t-1", service=_FakeService([proximo]),
        telegram_configured=lambda: False)
    sent.clear()
    r = await run_watch(watch_nochan, notify_fn=fake_notify, claim=False)
    check("p1-15 · plazos: sin canal configurado → silencio (opt-in)",
          r.get("surfaced") is False and sent == [])

    # ── H · run_watch degrada si el check lanza excepción (H4) ───────────────
    async def check_boom():
        raise RuntimeError("check roto")

    w_boom = Watch("boom", 1, check_boom, kind="no_agent")
    sent.clear()
    r = await run_watch(w_boom, notify_fn=fake_notify, claim=False)
    check("p1-17 · un check que lanza NO tumba run_watch (degrada, no avisa)",
          r.get("error") is not None and sent == [])

    # ── G · cableado ─────────────────────────────────────────────────────────
    names = [j["name"] for j in build_scheduler().list_jobs()]
    check("p1-16 · build_scheduler registra la vigilancia 'upcoming_deadlines'",
          "upcoming_deadlines" in names)


# ═══ Checks contra DB REAL (revisión capa 2, H1): el SQL de la regla dura y el
# CAS deben verificarse EJECUTADOS, no doblados. Siembra reminders reales y ejercita
# ReminderService.upcoming_procedural / mark_heads_up + el claim CAS contra Postgres.
def _sb():
    import psycopg
    kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres",
              password=os.getenv("PG_PASSWORD", ""))
    return psycopg.connect(autocommit=True, **kw)


async def db_checks() -> None:
    import init_reminders
    import init_watch_engine
    from mia.assistant.reminders import ReminderService
    from mia.cron import watch_engine as we
    from mia.db import pool

    init_reminders.apply()
    init_watch_engine.apply()
    await pool.open_pool()

    import os as _os
    tenants: list[str] = []
    with _sb() as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A watch cpp1') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B watch cpp1') RETURNING id").fetchone()[0]
    ta, tb = str(a), str(b)
    tenants.extend([ta, tb])
    try:
        svc = ReminderService()
        now = datetime.now().astimezone()
        # (a) PROCESAL, futuro dentro de ventana (48h) → debe salir
        r_ok = await svc.create(ta, None, "radicar la tutela", now + timedelta(hours=48), True)
        # (b) NO procesal, dentro de ventana → NO debe salir (regla dura: solo procesales)
        await svc.create(ta, None, "llamar al cliente", now + timedelta(hours=48), False)
        # (c) PROCESAL pero fuera de ventana (10 días) → NO debe salir aún
        await svc.create(ta, None, "audiencia lejana", now + timedelta(days=10), True)
        # (d) PROCESAL ya vencido → NO es heads-up (eso es reminders_due)
        await svc.create(ta, None, "plazo vencido", now - timedelta(hours=2), True)

        got = await svc.upcoming_procedural(ta, 72)
        ids = {g["id"] for g in got}
        check("p1-db1 · regla dura (SQL real): solo el PROCESAL futuro en ventana sale",
              ids == {r_ok})
        check("p1-db2 · SQL real: un recordatorio NO procesal NO se superficia como plazo",
              all(g["is_procedural"] for g in got))

        # (e) marcar heads_up → deja de salir (debounce real, no re-avisa)
        await svc.mark_heads_up(ta, [r_ok])
        got2 = await svc.upcoming_procedural(ta, 72)
        check("p1-db3 · debounce real: tras mark_heads_up, el plazo ya NO se re-superficia",
              r_ok not in {g["id"] for g in got2})

        # RLS: el tenant B no ve los plazos de A
        check("p1-db4 · RLS: el tenant B no ve los plazos próximos de A",
              await svc.upcoming_procedural(tb, 72) == [])

        # CAS real contra Postgres: dos workers, uno gana, el otro pierde; release libera.
        jn = f"gate-cas-{_os.getpid()}"
        w1 = await we.claim_job(jn, worker_id="w1")
        w2 = await we.claim_job(jn, worker_id="w2")
        check("p1-db5 · CAS real: dos workers concurrentes → uno gana, el otro pierde",
              w1 is True and w2 is False)
        await we.release_job(jn, worker_id="w1")
        w3 = await we.claim_job(jn, worker_id="w2")
        check("p1-db6 · CAS real: tras soltar el claim, otro worker ya puede tomarlo", w3 is True)
        # release no borra el claim de OTRO worker (protección por claimed_by)
        await we.release_job(jn, worker_id="w1")  # w1 ya no es el dueño → no borra
        w4 = await we.claim_job(jn, worker_id="w-otro")
        check("p1-db7 · CAS real: release ajeno NO roba el claim vigente de otro worker",
              w4 is False)
        await we.release_job(jn, worker_id="w2")
        with _sb() as c:
            c.execute("DELETE FROM scheduled_claims WHERE job_name = %s", (jn,))
    finally:
        with _sb() as c:
            c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))
        await pool.close_pool()


if __name__ == "__main__":
    asyncio.run(run_gate())
    if os.getenv("PG_PASSWORD"):
        asyncio.run(db_checks())
    else:
        check("p1-db · SKIP (sin PG_PASSWORD): no se ejercitó la DB real", False)
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks PASS")
    if all(ok for _, ok in _results):
        print("motor de vigilancia OK — CP-P1 verificado (at-most-once CAS real + wake-gate + "
              "no_agent + regla dura del SQL de plazos con [VERIFICAR]).")
        sys.exit(0)
    sys.exit(1)
