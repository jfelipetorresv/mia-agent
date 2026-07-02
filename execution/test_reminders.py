"""
Mia · test_reminders.py — gate de CP-B3 (PROACTIVIDAD: recordatorios y avisos, Pilar B).

Verifica con DB REAL, LLM MOCKEADO y Telegram MOCKEADO (sin red):

  (p) Parser determinista de recordatorios en español: "mañana", "el viernes",
      "en 2 horas", "el 15 de agosto", horas ("a las 3 pm", "de la noche"),
      detección de plazos PROCESALES (is_procedural) y de la intención
      (¿recuerdas...? NO es un recordatorio; sin fecha → due None, se pregunta).
  (s) ReminderService con RLS: crear/listar/cancelar por tenant; el tenant B no
      ve ni cancela los recordatorios de A; `due()` solo devuelve vencidos.
  (d) Job reminders_due: despacha SOLO los vencidos por Telegram, marca 'sent'
      ÚNICAMENTE si Telegram aceptó (envío fallido → sigue 'pending' y se
      reintenta); los procesales viajan con [VERIFICAR] (regla dura del plan).
  (r) Job pending_review_notify: aviso agregado de borradores esperando revisión
      con DEBOUNCE de 24h por asunto; reset del debounce (approve) → re-avisa;
      envío fallido → NO marca (se reintenta).
  (w) Reporte semanal de Dreams → se envía por Telegram al tenant del canal.
  (a) Asistente (HTTP): "recuérdame..." crea el recordatorio SIN llamar al LLM
      (flujo determinista) y confirma con [VERIFICAR] si es procesal; sin fecha
      → pregunta y NO crea; "qué recordatorios tengo" → bloque de estado real
      bajo RLS solo en el mensaje que ve el modelo; endpoints GET/cancel.

Limpia sus datos al final. HALT si falla (CLAUDE.md §G). Exit 0 = PASS · 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_reminders.py
"""
from __future__ import annotations

import asyncio
import os
import sys
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

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

import init_assistant  # noqa: E402
import init_profiles  # noqa: E402
import init_reminders  # noqa: E402
import init_users  # noqa: E402
from mia import config  # noqa: E402
from mia.agent import llm  # noqa: E402
from mia.assistant.core import (  # noqa: E402
    REMINDER_BUSINESS_DAYS_REPLY,
    REMINDER_MISSING_DATE_REPLY,
    REMINDER_NO_CHANNEL_WARNING,
    REMINDER_PROCEDURAL_WARNING,
    REMINDERS_BLOCK_HEADER,
)
from mia.assistant.reminders import (  # noqa: E402
    ReminderService,
    format_due,
    parse_reminder,
    parse_when,
)
from mia.channels import notify  # noqa: E402
from mia.cron import scheduler  # noqa: E402
from mia.db import pool  # noqa: E402

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"),
    port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"),
    user="postgres",
    password=os.getenv("PG_PASSWORD", ""),
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def sb() -> psycopg.Connection:
    return psycopg.connect(autocommit=True, **PG)


def cleanup(tenant_ids: list[str]) -> None:
    if not tenant_ids:
        return
    with sb() as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s::uuid[])", (tenant_ids,))


def set_policy_nube(tenant_id: str) -> None:
    with sb() as c:
        c.execute(
            "UPDATE tenant_settings SET config = jsonb_set(config, '{model_policy}', '\"nube\"') "
            "WHERE tenant_id = %s::uuid",
            (tenant_id,),
        )


# ── cliente LLM falso (patrón test_assistant: guionado por alias, captura messages) ──
def ok_response(text: str):
    msg = SimpleNamespace(content=text)
    return SimpleNamespace(choices=[SimpleNamespace(message=msg)], usage=None)


class FakeCompletions:
    def __init__(self) -> None:
        self.script: dict[str, list[str]] = {}
        self.calls: list[dict] = []
        self._lock = threading.Lock()

    def create(self, **kwargs):
        model = kwargs["model"]
        with self._lock:
            self.calls.append({"model": model, "messages": kwargs["messages"]})
            outcomes = self.script.get(model)
            if not outcomes:
                raise AssertionError(f"llamada no guionada al alias {model}")
            text = outcomes.pop(0) if len(outcomes) > 1 else outcomes[0]
        return ok_response(text)

    def last_for(self, model: str) -> dict | None:
        for call in reversed(self.calls):
            if call["model"] == model:
                return call
        return None


# ── Telegram falso: captura los mensajes salientes, éxito/fallo configurable ──
class FakeNotify:
    def __init__(self) -> None:
        self.sent: list[str] = []
        self.succeed = True

    async def send_telegram(self, text, env=None, http=None) -> bool:
        if not self.succeed:
            return False
        self.sent.append(text)
        return True


# ── (p) parser determinista — sin DB, sin red ────────────────────────────────
def parser_checks() -> None:
    # miércoles 1 de julio de 2026, 10:00 hora local
    now = datetime(2026, 7, 1, 10, 0).astimezone()

    p = parse_reminder("Recuérdame radicar la tutela mañana a las 9", now)
    check("p1 · 'mañana a las 9' → día siguiente 09:00, subject limpio, PROCESAL (radicar)",
          p is not None and p.due_at is not None
          and p.due_at.date() == (now + timedelta(days=1)).date()
          and (p.due_at.hour, p.due_at.minute) == (9, 0)
          and "radicar la tutela" in p.subject and p.is_procedural)

    p = parse_reminder("ponme un recordatorio para llamar al cliente en 30 minutos", now)
    check("p2 · 'en 30 minutos' → now+30min, NO procesal",
          p is not None and p.due_at == now + timedelta(minutes=30)
          and "llamar al cliente" in p.subject and not p.is_procedural)

    p = parse_reminder("avísame el viernes a las 3 pm sobre la reunión", now)
    check("p3 · 'el viernes a las 3 pm' → próximo viernes 15:00",
          p is not None and p.due_at is not None
          and p.due_at.weekday() == 4 and (p.due_at.hour, p.due_at.minute) == (15, 0)
          and p.due_at.date() == datetime(2026, 7, 3).date())

    p = parse_reminder("recuérdame el miércoles revisar el contrato", now)
    check("p4 · día de la semana IGUAL a hoy → +7 días (nunca el pasado)",
          p is not None and p.due_at is not None
          and p.due_at.date() == datetime(2026, 7, 8).date())

    p = parse_reminder("recuérdame el 15 de junio renovar la póliza", now)
    check("p5 · fecha absoluta ya pasada este año → próxima ocurrencia (año siguiente)",
          p is not None and p.due_at is not None
          and (p.due_at.year, p.due_at.month, p.due_at.day) == (2027, 6, 15))

    p = parse_reminder("recuérdame hoy a las 7 enviar el correo", now)
    check("p6 · 'hoy a las 7' con la hora YA PASADA → mañana a las 07:00",
          p is not None and p.due_at is not None
          and p.due_at.date() == (now + timedelta(days=1)).date()
          and p.due_at.hour == 7)

    p = parse_reminder("recuérdame pasado mañana la audiencia de conciliación", now)
    check("p7 · 'pasado mañana' → +2 días 08:00 y PROCESAL (audiencia)",
          p is not None and p.due_at is not None
          and p.due_at.date() == (now + timedelta(days=2)).date()
          and p.due_at.hour == 8 and p.is_procedural)

    p = parse_reminder("recuérdame mañana a las 8 de la noche llamar a mi socio", now)
    check("p8 · 'a las 8 de la noche' → 20:00 (y 'de la noche' no rompe el subject)",
          p is not None and p.due_at is not None and p.due_at.hour == 20
          and "llamar a mi socio" in p.subject)

    p = parse_reminder("avísame a las 9 de la mañana lo del juzgado", now)
    check("p9 · 'a las 9 de la mañana' (hora pasada) → MAÑANA 09:00 — no se confunde con el día 'mañana'",
          p is not None and p.due_at is not None
          and p.due_at.date() == (now + timedelta(days=1)).date()
          and p.due_at.hour == 9 and p.is_procedural)

    p = parse_reminder("recuérdame en una semana hacer seguimiento", now)
    check("p10 · 'en una semana' → +7 días a la misma hora",
          p is not None and p.due_at == now + timedelta(weeks=1))

    check("p11 · '¿recuerdas el caso HDI?' NO es un recordatorio (pregunta de memoria)",
          parse_reminder("¿recuerdas el caso HDI?", now) is None)

    p = parse_reminder("recuérdame contestar la demanda cuando pueda", now)
    check("p12 · intención SÍ pero sin fecha reconocible → due None (el asistente pregunta)",
          p is not None and p.due_at is None and p.is_procedural)

    d = format_due(datetime(2026, 7, 2, 9, 0).astimezone())
    check("p13 · format_due en español sin depender del locale",
          d == "2 de julio a las 09:00")

    jobs = {j["name"]: j for j in scheduler.build_scheduler().list_jobs()}
    check("p14 · jobs registrados: reminders_due (5 min) y pending_review_notify (1h)",
          "reminders_due" in jobs and "pending_review_notify" in jobs
          and abs(jobs["reminders_due"]["interval_hours"] - 5 / 60) < 1e-9
          and jobs["pending_review_notify"]["interval_hours"] == 1)

    # ── correcciones del revisor (capa 2) como checks permanentes ────────────
    # B1 · vocabulario procesal ampliado: frases jurídicas cotidianas SIEMPRE [VERIFICAR]
    for frase in (
        "recuérdame que el emplazamiento del proceso ejecutivo es mañana",
        "recuérdame la sentencia del caso Pérez mañana",
        "recuérdame mi diligencia en la fiscalía mañana",
        "recuérdame el requerimiento del expediente mañana",
    ):
        pb = parse_reminder(frase, now)
        if not (pb and pb.is_procedural):
            check(f"b1 · procesal detectado: «{frase[:50]}…»", False)
            break
    else:
        check("b1 · emplazamiento/sentencia/diligencia/fiscalía/expediente → PROCESAL (regla dura)",
              True)

    # M5 · disparador débil: "avísame" SIN fecha es conversación, no recordatorio
    check("m5 · 'revisa el contrato de HDI y avísame qué opinas' NO se intercepta",
          parse_reminder("revisa el contrato de HDI y avísame qué opinas", now) is None)

    # M1 · "días hábiles" NUNCA se calculan → se pide la fecha exacta
    p = parse_reminder("recuérdame contestar la demanda en 10 días hábiles", now)
    check("m1 · 'en 10 días hábiles' → NO calcula: due None + business_days (pide fecha exacta)",
          p is not None and p.due_at is None and p.business_days and p.is_procedural)

    # M2 · el año explícito se respeta (y la fecha explícita en el pasado se pregunta)
    p = parse_reminder("recuérdame el 15 de agosto de 2027 renovar el registro de marca", now)
    check("m2a · 'el 15 de agosto de 2027' → agenda en 2027 y el subject no arrastra el año",
          p is not None and p.due_at is not None
          and (p.due_at.year, p.due_at.month, p.due_at.day) == (2027, 8, 15)
          and "renovar el registro de marca" in p.subject and "2027" not in p.subject)
    check("m2b · format_due incluye el año cuando NO es el año en curso",
          format_due(datetime(2027, 8, 15, 8, 0).astimezone()) == "15 de agosto de 2027 a las 08:00")
    p = parse_reminder("recuérdame el 15 de agosto de 2020 revisar el archivo", now)
    check("m2c · fecha explícita en el PASADO → pregunta (due None), nunca adivina",
          p is not None and p.due_at is None)

    # Menores: 29 de febrero sin año siguiente válido → pregunta (sin crash);
    # "en media semana" → pregunta; parse_when (turno de seguimiento) funciona solo.
    leap_now = datetime(2028, 3, 1, 10, 0).astimezone()
    p = parse_reminder("recuérdame el 29 de febrero pagar la renovación", leap_now)
    check("m6 · '29 de febrero' ya pasado en año bisiesto → pregunta, sin error",
          p is not None and p.due_at is None)
    p = parse_reminder("recuérdame en media semana revisar el borrador", now)
    check("m7 · 'en media semana' → pregunta (no lo confunde con media hora)",
          p is not None and p.due_at is None)
    check("p15 · parse_when: fecha sola sin disparador ('mañana a las 9') → fecha válida",
          parse_when("mañana a las 9", now) == (now + timedelta(days=1)).replace(hour=9, minute=0)
          and parse_when("no estoy seguro todavía", now) is None)


# ── checks async: notify + servicio + jobs (DB real, Telegram falso) ─────────
async def async_checks(tenant_a: str, tenant_b: str) -> None:
    await pool.open_pool()
    real_resolve = scheduler._resolve_notify_tenant
    real_send = notify.send_telegram
    real_configured = notify.telegram_configured
    try:
        # --- notify: unidad, con http falso (sin red) ---
        posted: list[tuple[str, dict]] = []

        class FakeHTTP:
            def __init__(self, status: int = 200) -> None:
                self.status = status

            async def post(self, url, json=None):
                posted.append((url, json))
                return SimpleNamespace(status_code=self.status)

        env_ok = {"TELEGRAM_BOT_TOKEN": "tok-secreto", "TELEGRAM_ALLOWED_CHAT_ID": "777"}
        ok = await real_send("hola abogado", env=env_ok, http=FakeHTTP())
        check("n1 · notify: POST a sendMessage con chat_id y texto → True",
              ok and len(posted) == 1
              and posted[0][0].endswith("/bottok-secreto/sendMessage")
              and posted[0][1] == {"chat_id": 777, "text": "hola abogado"})
        ok2 = await real_send("hola", env={}, http=FakeHTTP())
        check("n2 · notify: sin configuración → False sin llamar a la red (opt-in)",
              ok2 is False and len(posted) == 1)
        ok3 = await real_send("hola", env=env_ok, http=FakeHTTP(status=502))
        check("n3 · notify: Telegram responde error → False, sin lanzar", ok3 is False)

        class BoomHTTP:
            async def post(self, url, json=None):
                raise RuntimeError("red caída (simulada)")

        ok4 = await real_send("hola", env=env_ok, http=BoomHTTP())
        check("n4 · notify: red caída → False, sin lanzar (fail-soft)", ok4 is False)

        # --- servicio: crear / listar / cancelar bajo RLS ---
        service = ReminderService()
        now = datetime.now().astimezone()
        rid_future = await service.create(
            tenant_a, None, "preparar la reunión con el perito",
            now + timedelta(hours=3), False)
        rid_due = await service.create(
            tenant_a, None, "radicar el recurso de apelación",
            now - timedelta(minutes=5), True)
        pend_a = await service.list_pending(tenant_a)
        check("s1 · crear + listar: 2 pendientes del tenant A, el más próximo primero",
              len(pend_a) == 2 and pend_a[0]["id"] == rid_due
              and pend_a[1]["id"] == rid_future)
        check("s2 · RLS: el tenant B NO ve los recordatorios de A",
              await service.list_pending(tenant_b) == [])
        check("s3 · RLS: el tenant B NO puede cancelar un recordatorio de A",
              (await service.cancel(tenant_b, rid_future)) is False)
        due = await service.due(tenant_a)
        check("s4 · due(): solo devuelve los VENCIDOS (1 de 2)",
              len(due) == 1 and due[0]["id"] == rid_due and due[0]["is_procedural"])
        check("s5 · cancelar propio → True y desaparece de pendientes",
              (await service.cancel(tenant_a, rid_future)) is True
              and all(r["id"] != rid_future for r in await service.list_pending(tenant_a)))
        check("s6 · cancelar dos veces → False (ya no está 'pending')",
              (await service.cancel(tenant_a, rid_future)) is False)
        # mark_sent con guarda de estado: una cancelación en la ventana entre due()
        # y el envío GANA — un 'cancelled' jamás pasa a 'sent' (hallazgo menor #2).
        await service.mark_sent(tenant_a, rid_future)
        with sb() as c:
            st = c.execute("SELECT status FROM reminders WHERE id=%s::uuid",
                           (rid_future,)).fetchone()[0]
        check("s7 · mark_sent sobre un 'cancelled' NO lo cambia (la cancelación gana)",
              st == "cancelled")

        # --- job reminders_due: despacha vencidos, marca 'sent' solo si Telegram aceptó ---
        fake = FakeNotify()
        scheduler._resolve_notify_tenant = lambda: tenant_a
        notify.send_telegram = fake.send_telegram
        notify.telegram_configured = lambda env=None: True

        fake.succeed = False
        out_fail = await scheduler.reminders_due_dispatch()
        with sb() as c:
            status_fail = c.execute(
                "SELECT status FROM reminders WHERE id=%s::uuid", (rid_due,)
            ).fetchone()[0]
        check("d1 · envío FALLA → el recordatorio sigue 'pending' (se reintenta, no se pierde)",
              out_fail.get("sent") == 0 and status_fail == "pending")

        fake.succeed = True
        out_ok = await scheduler.reminders_due_dispatch()
        with sb() as c:
            row = c.execute(
                "SELECT status, sent_at FROM reminders WHERE id=%s::uuid", (rid_due,)
            ).fetchone()
        check("d2 · envío OK → despachado y marcado 'sent' con sent_at",
              out_ok.get("sent") == 1 and row[0] == "sent" and row[1] is not None)
        check("d3 · el mensaje lleva el texto y [VERIFICAR] por ser plazo procesal (regla dura)",
              len(fake.sent) == 1 and "radicar el recurso de apelación" in fake.sent[0]
              and REMINDER_PROCEDURAL_WARNING in fake.sent[0])
        out_again = await scheduler.reminders_due_dispatch()
        check("d4 · segundo ciclo → nada que despachar (no re-envía los 'sent')",
              out_again.get("sent") == 0 and len(fake.sent) == 1)

        # --- job pending_review_notify: aviso agregado con debounce de 24h ---
        with sb() as c:
            m1 = c.execute(
                "INSERT INTO matters (tenant_id, title, status, pending_review) "
                "VALUES (%s::uuid, 'Demanda contractual HDI', 'active', true) RETURNING id",
                (tenant_a,),
            ).fetchone()[0]
            c.execute(
                "INSERT INTO matters (tenant_id, title, status, pending_review) "
                "VALUES (%s::uuid, 'Tutela salud EPS', 'active', false)",
                (tenant_a,),
            )
        fake.sent.clear()
        out_r1 = await scheduler.pending_review_notify()
        check("r1 · aviso enviado con el asunto pendiente (y SOLO el pendiente)",
              out_r1.get("notified") == 1 and len(fake.sent) == 1
              and "Demanda contractual HDI" in fake.sent[0]
              and "Tutela salud EPS" not in fake.sent[0]
              and "borrador" in fake.sent[0])
        out_r2 = await scheduler.pending_review_notify()
        check("r2 · DEBOUNCE: sigue pendiente pero ya se avisó → no re-avisa",
              out_r2.get("notified") == 0 and len(fake.sent) == 1)
        with sb() as c:  # simular approve (hitl.py): pending false + debounce NULL
            c.execute(
                "UPDATE matters SET pending_review = false, pending_review_notified_at = NULL "
                "WHERE id = %s::uuid", (m1,))
        out_r3 = await scheduler.pending_review_notify()
        check("r3 · tras la decisión del abogado no hay pendientes → no avisa",
              out_r3.get("notified") == 0 and len(fake.sent) == 1)
        with sb() as c:  # borrador NUEVO en el mismo asunto → avisa de inmediato
            c.execute("UPDATE matters SET pending_review = true WHERE id = %s::uuid", (m1,))
        out_r4 = await scheduler.pending_review_notify()
        check("r4 · borrador NUEVO tras el reset del debounce → avisa de inmediato",
              out_r4.get("notified") == 1 and len(fake.sent) == 2)
        fake.succeed = False
        with sb() as c:
            c.execute(
                "UPDATE matters SET pending_review_notified_at = NULL WHERE id = %s::uuid",
                (m1,))
        out_r5 = await scheduler.pending_review_notify()
        with sb() as c:
            marked = c.execute(
                "SELECT pending_review_notified_at FROM matters WHERE id=%s::uuid", (m1,)
            ).fetchone()[0]
        check("r5 · envío FALLA → NO se marca el debounce (el siguiente ciclo reintenta)",
              out_r5.get("notified") == 0 and marked is None)
        fake.succeed = True

        # --- reporte semanal de Dreams → Telegram del tenant del canal ---
        import mia.memory.dreams as dreams_mod

        class FakeDreams:
            async def run_all_tenants(self):
                return {tenant_a: {"report": "Esta semana el despacho trabajó 3 asuntos."}}

        real_dreams = dreams_mod.Dreams
        dreams_mod.Dreams = FakeDreams
        try:
            fake.sent.clear()
            await scheduler.dreams_run_all_tenants()
        finally:
            dreams_mod.Dreams = real_dreams
        check("w1 · el reporte semanal llega por Telegram (encabezado + contenido)",
              len(fake.sent) == 1 and "Reporte semanal" in fake.sent[0]
              and "trabajó 3 asuntos" in fake.sent[0])
    finally:
        scheduler._resolve_notify_tenant = real_resolve
        notify.send_telegram = real_send
        notify.telegram_configured = real_configured
        await pool.close_pool()


# ── (a) asistente por HTTP: crear/preguntar/cancelar sin jerga ────────────────
def http_checks(client, fake_llm: FakeCompletions, tenants: list[str]) -> None:
    # Canal de avisos SIN configurar (estado por defecto): se limpia el entorno para
    # que las confirmaciones incluyan la advertencia honesta (hallazgo M3).
    saved_env = {k: os.environ.pop(k, None) for k in
                 ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_ID", "MIA_BRIDGE_EMAIL")}
    try:
        _http_checks_inner(client, fake_llm, tenants, saved_env)
    finally:
        for k, v in saved_env.items():
            os.environ.pop(k, None)
            if v is not None:
                os.environ[k] = v


def _http_checks_inner(client, fake_llm: FakeCompletions, tenants: list[str],
                       saved_env: dict) -> None:
    stamp = int(time.time() * 1000)
    email_c = f"reminders-{stamp}-c@example.com"
    email_d = f"reminders-{stamp}-d@example.com"
    rc = client.post("/api/auth/register", json={
        "email": email_c, "password": "Password-12345",
        "firm_name": "Reminders Test C"})
    rd = client.post("/api/auth/register", json={
        "email": email_d, "password": "Password-12345",
        "firm_name": "Reminders Test D"})
    assert rc.status_code == 201 and rd.status_code == 201, "registro de tenants de prueba falló"
    tenant_c, tenant_d = rc.json()["tenant_id"], rd.json()["tenant_id"]
    tenants.extend([tenant_c, tenant_d])
    auth_c = {"Authorization": f"Bearer {rc.json()['token']}"}
    auth_d = {"Authorization": f"Bearer {rd.json()['token']}"}
    set_policy_nube(tenant_c)
    set_policy_nube(tenant_d)

    # a1 · crear por chat: DETERMINISTA (el LLM falso NO tiene guion: si se llamara → 502)
    r1 = client.post("/api/assistant/chat", headers=auth_c,
                     json={"message": "Recuérdame radicar la tutela mañana a las 9"})
    with sb() as c:
        rows = c.execute(
            "SELECT tenant_id, text, is_procedural, status FROM reminders "
            "WHERE tenant_id=%s::uuid", (tenant_c,),
        ).fetchall()
    check("a1 · 'recuérdame...' crea el recordatorio SIN llamar al modelo (determinista)",
          r1.status_code == 200 and fake_llm.last_for("claude-sonnet") is None
          and len(rows) == 1 and str(rows[0][0]) == tenant_c
          and "radicar la tutela" in rows[0][1] and rows[0][3] == "pending")
    check("a2 · confirmación con fecha legible y [VERIFICAR] (plazo procesal, regla dura)",
          "Listo. Te lo recordaré el" in r1.json()["reply"]
          and REMINDER_PROCEDURAL_WARNING in r1.json()["reply"]
          and rows[0][2] is True)
    check("a2b · sin canal de Telegram → la confirmación AVISA que no sonará (promesa honesta)",
          REMINDER_NO_CHANNEL_WARNING in r1.json()["reply"])
    conv = r1.json()["conversation_id"]
    with sb() as c:
        persisted = c.execute(
            "SELECT role, content FROM assistant_messages WHERE conversation_id=%s::uuid "
            "ORDER BY created_at, id", (conv,),
        ).fetchall()
    check("a3 · el turno determinista queda persistido (user + assistant)",
          len(persisted) == 2 and [p[0] for p in persisted] == ["user", "assistant"]
          and persisted[1][1] == r1.json()["reply"])

    # a4 · sin fecha → pregunta y NO crea
    r2 = client.post("/api/assistant/chat", headers=auth_c,
                     json={"message": "Ponme un recordatorio para llamar al perito"})
    with sb() as c:
        n = c.execute("SELECT count(*) FROM reminders WHERE tenant_id=%s::uuid",
                      (tenant_c,)).fetchone()[0]
    check("a4 · sin fecha reconocible → Mia pregunta cuándo y NO crea nada",
          r2.status_code == 200 and r2.json()["reply"] == REMINDER_MISSING_DATE_REPLY
          and n == 1)

    # a4b · TURNO DE SEGUIMIENTO (fix B2): el abogado responde SOLO la fecha en la
    # misma conversación → se crea con el QUÉ del mensaje anterior (sin LLM).
    conv_ask = r2.json()["conversation_id"]
    r2b = client.post("/api/assistant/chat", headers=auth_c,
                      json={"message": "mañana a las 9", "conversation_id": conv_ask})
    with sb() as c:
        row_fu = c.execute(
            "SELECT text, status FROM reminders WHERE tenant_id=%s::uuid "
            "ORDER BY created_at DESC LIMIT 1", (tenant_c,),
        ).fetchone()
    check("a4b · '¿cuándo?' → 'mañana a las 9' crea el recordatorio con el QUÉ anterior",
          r2b.status_code == 200 and "Listo. Te lo recordaré el" in r2b.json()["reply"]
          and fake_llm.last_for("claude-sonnet") is None
          and row_fu is not None and "llamar al perito" in row_fu[0]
          and row_fu[1] == "pending")
    # a4c · 'N días hábiles' → Mia NO calcula: pide la fecha exacta (fix M1)
    r2c = client.post("/api/assistant/chat", headers=auth_c,
                      json={"message": "Recuérdame enviar el informe en 5 días hábiles"})
    check("a4c · 'en 5 días hábiles' → pide la fecha exacta (no calcula hábiles)",
          r2c.status_code == 200 and r2c.json()["reply"] == REMINDER_BUSINESS_DAYS_REPLY)
    # limpiar el recordatorio del seguimiento para dejar UN pendiente (el de la tutela)
    with sb() as c:
        fu_id = c.execute(
            "SELECT id FROM reminders WHERE tenant_id=%s::uuid AND text LIKE %s",
            (tenant_c, "%llamar al perito%"),
        ).fetchone()[0]
    r_cleanup = client.post(f"/api/assistant/reminders/{fu_id}/cancel", headers=auth_c)
    assert r_cleanup.status_code == 200, "no se pudo cancelar el recordatorio de seguimiento"

    # a5 · "qué recordatorios tengo" → bloque real bajo RLS solo hacia el modelo
    fake_llm.script["claude-sonnet"] = ["Tienes un recordatorio para mañana a las 9."]
    r3 = client.post("/api/assistant/chat", headers=auth_c,
                     json={"message": "¿Qué recordatorios tengo pendientes?"})
    sent = fake_llm.last_for("claude-sonnet")
    last_user = sent["messages"][-1]["content"] if sent else ""
    check("a5 · el modelo ve el bloque de recordatorios con el estado real",
          r3.status_code == 200 and REMINDERS_BLOCK_HEADER in last_user
          and "radicar la tutela" in last_user and "[VERIFICAR]" in last_user)
    with sb() as c:
        persisted_q = c.execute(
            "SELECT content FROM assistant_messages WHERE conversation_id=%s::uuid "
            "AND role='user' ORDER BY created_at DESC LIMIT 1",
            (r3.json()["conversation_id"],),
        ).fetchone()[0]
    check("a6 · el mensaje PERSISTIDO es el original (el bloque no se guarda)",
          REMINDERS_BLOCK_HEADER not in persisted_q)

    # a7 · endpoints: listar y cancelar (RLS: el tenant D no toca lo de C)
    lst = client.get("/api/assistant/reminders", headers=auth_c).json()
    check("a7 · GET /assistant/reminders lista el pendiente con is_procedural",
          len(lst) == 1 and "radicar la tutela" in lst[0]["text"]
          and lst[0]["is_procedural"] is True)
    rid = lst[0]["id"]
    cross = client.post(f"/api/assistant/reminders/{rid}/cancel", headers=auth_d)
    check("a8 · el tenant D cancela un recordatorio de C → 404 (RLS, nunca datos)",
          cross.status_code == 404
          and client.get("/api/assistant/reminders", headers=auth_c).json() != [])
    own = client.post(f"/api/assistant/reminders/{rid}/cancel", headers=auth_c)
    check("a9 · cancelar propio → 200 y desaparece del listado",
          own.status_code == 200
          and client.get("/api/assistant/reminders", headers=auth_c).json() == [])
    check("a10 · cancelar de nuevo → 404 (ya no está pendiente)",
          client.post(f"/api/assistant/reminders/{rid}/cancel",
                      headers=auth_c).status_code == 404)
    check("a11 · sin token → 401",
          client.get("/api/assistant/reminders").status_code == 401)

    # ── cancelación POR CHAT, determinista (fix M4) — con el tenant D ────────
    client.post("/api/assistant/chat", headers=auth_d,
                json={"message": "Recuérdame radicar la tutela mañana"})
    client.post("/api/assistant/chat", headers=auth_d,
                json={"message": "Recuérdame llamar al perito pasado mañana"})
    rc1 = client.post("/api/assistant/chat", headers=auth_d,
                      json={"message": "Cancela el recordatorio de la tutela"})
    with sb() as c:
        st_tutela = c.execute(
            "SELECT status FROM reminders WHERE tenant_id=%s::uuid AND text LIKE %s",
            (tenant_d, "%tutela%")).fetchone()[0]
        st_perito = c.execute(
            "SELECT status FROM reminders WHERE tenant_id=%s::uuid AND text LIKE %s",
            (tenant_d, "%perito%")).fetchone()[0]
    check("x1 · 'cancela el recordatorio de la tutela' → confirmación determinista",
          rc1.status_code == 200
          and "Listo, cancelé el recordatorio" in rc1.json()["reply"]
          and "tutela" in rc1.json()["reply"])
    check("x2 · el de la tutela quedó 'cancelled' y el del perito sigue 'pending'",
          st_tutela == "cancelled" and st_perito == "pending")
    rc2 = client.post("/api/assistant/chat", headers=auth_d,
                      json={"message": "cancela el recordatorio"})
    with sb() as c:
        st_perito2 = c.execute(
            "SELECT status FROM reminders WHERE tenant_id=%s::uuid AND text LIKE %s",
            (tenant_d, "%perito%")).fetchone()[0]
    check("x3 · 'cancela el recordatorio' con UNO solo pendiente → lo cancela directo",
          rc2.status_code == 200 and "Listo, cancelé el recordatorio" in rc2.json()["reply"]
          and st_perito2 == "cancelled")
    rc3 = client.post("/api/assistant/chat", headers=auth_d,
                      json={"message": "cancela el recordatorio"})
    check("x4 · sin pendientes → respuesta honesta (no hay nada que cancelar)",
          rc3.status_code == 200 and "no hay nada que cancelar" in rc3.json()["reply"].lower())

    # ── canal de avisos PROPIO vs ajeno (fix M3) ─────────────────────────────
    os.environ["TELEGRAM_BOT_TOKEN"] = "tok-de-prueba"
    os.environ["TELEGRAM_ALLOWED_CHAT_ID"] = "777"
    os.environ["MIA_BRIDGE_EMAIL"] = email_c
    try:
        rp = client.post("/api/assistant/chat", headers=auth_c,
                         json={"message": "Recuérdame enviar la factura mañana"})
        check("x5 · el tenant DUEÑO del canal no recibe la advertencia (le va a sonar)",
              rp.status_code == 200
              and REMINDER_NO_CHANNEL_WARNING not in rp.json()["reply"])
        rq = client.post("/api/assistant/chat", headers=auth_d,
                         json={"message": "Recuérdame revisar el contrato mañana"})
        check("x6 · OTRO despacho (canal ajeno) SÍ recibe la advertencia (no le sonará)",
              rq.status_code == 200
              and REMINDER_NO_CHANNEL_WARNING in rq.json()["reply"])
    finally:
        for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ALLOWED_CHAT_ID", "MIA_BRIDGE_EMAIL"):
            os.environ.pop(k, None)


def make_tenants() -> tuple[str, str]:
    with sb() as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A test cpb3') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test cpb3') RETURNING id").fetchone()[0]
    return str(a), str(b)


def main() -> int:
    print("== CP-B3 · proactividad (recordatorios + avisos por Telegram) ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1
    init_profiles.apply()
    init_users.apply()
    init_assistant.apply()
    init_reminders.apply()

    parser_checks()

    tenants: list[str] = []
    a, b = make_tenants()
    tenants.extend([a, b])
    try:
        asyncio.run(async_checks(a, b))

        fake_llm = FakeCompletions()
        llm._client = SimpleNamespace(chat=SimpleNamespace(completions=fake_llm))
        llm.time.sleep = lambda *_a, **_k: None
        from fastapi.testclient import TestClient
        from mia.api.main import app

        try:
            with TestClient(app) as client:
                http_checks(client, fake_llm, tenants)
        finally:
            llm._client = None
    finally:
        cleanup(tenants)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Proactividad OK — CP-B3 verificado (parser + RLS + despacho + debounce + asistente).")
        return 0
    print("Proactividad FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
