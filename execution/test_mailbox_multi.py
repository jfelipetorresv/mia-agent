"""
Mia · test_mailbox_multi.py — gate de la Fase 1 "fuentes remotas del expediente":
cimientos OAuth MULTI-PROVEEDOR (un despacho puede tener Microsoft Y Google conectados
a la vez). Complementa test_mailbox.py (que ya cubre CP-P3/CP-P4 de proveedor único);
aquí solo lo que CAMBIA al permitir dos conexiones simultáneas:

  A. oauth.scopes_for: features -> scopes por proveedor ("mail"/"mail_content"/"drive"),
     "drive" restringido a Microsoft, sin features reconocidas cae al mínimo de "mail".
  B. service.MailboxService.connectors_for: UN conector por CADA proveedor conectado
     (doblado, sin red ni DB); un proveedor sin refresco posible se omite sin tumbar
     a los demás.
  C. watch_engine: calendar_events_watch/urgent_mail_watch vigilan AMBOS proveedores a
     la vez, sin duplicar avisos (debounce prefijado por proveedor); el resumen de
     contenido (CP-P4) trae el cuerpo del proveedor CORRECTO por cabecera.
  D. DB real: tenant_oauth_tokens con PK (tenant_id, provider) — Microsoft Y Google
     coexisten para el mismo tenant; disconnect de uno no borra el otro; RLS entre
     tenants; load_tokens sin `provider` conserva compatibilidad (primera conexión);
     list_connections no expone tokens/secretos.

Exit 0 = PASS · 1 = FAIL.   .venv\\Scripts\\python.exe execution\\test_mailbox_multi.py
"""
from __future__ import annotations

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
    from mia.connectors.mailbox import oauth
    from mia.connectors.mailbox.base import CalendarEvent, MailHeader, OAuthCreds
    from mia.connectors.mailbox.service import MailboxService
    from mia.cron import watch_engine as we

    now = datetime(2026, 7, 8, 12, 0, tzinfo=timezone.utc)

    # ── A · scopes por feature ────────────────────────────────────────────────
    check("mx-01 · mail (default): Microsoft trae Calendars.Read/Mail.Read sin Files.Read",
          "Calendars.Read" in oauth.scopes_for("microsoft", features=("mail",))
          and "Mail.Read" in oauth.scopes_for("microsoft", features=("mail",))
          and "Files.Read" not in oauth.scopes_for("microsoft", features=("mail",)))
    check("mx-02 · mail_content: Google cambia gmail.metadata por gmail.readonly",
          any("gmail.readonly" in s for s in oauth.scopes_for("google", features=("mail_content",)))
          and not any("gmail.metadata" in s
                     for s in oauth.scopes_for("google", features=("mail_content",))))
    check("mx-03 · drive: Microsoft añade Files.Read AL LADO de mail (no lo reemplaza)",
          set(oauth.scopes_for("microsoft", features=("mail", "drive")))
          == set(oauth.scopes_for("microsoft", features=("mail",))) | {"Files.Read"})

    def _raises_value_error(fn) -> bool:
        try:
            fn()
            return False
        except ValueError:
            return True

    check("mx-04 · drive: Google la rechaza (solo Microsoft/OneDrive)",
          _raises_value_error(lambda: oauth.scopes_for("google", features=("mail", "drive"))))
    check("mx-05 · feature desconocida: se rechaza (ValueError, no silencio)",
          _raises_value_error(lambda: oauth.scopes_for("microsoft", features=("volar",))))
    check("mx-06 · authorize_url: features compone la URL con Files.Read cuando se pide drive",
          "Files.Read" in oauth.authorize_url(
              "microsoft", client_id="cid", redirect_uri="https://x/cb", state="s",
              features=("mail", "drive")))

    # ── B · service.connectors_for (doblado, sin red/DB) ─────────────────────
    class FakeStoreMulti:
        """Dos conexiones para el mismo tenant: microsoft y google, ambas vigentes."""
        def __init__(self, conns: dict):
            self._conns = conns   # provider -> OAuthCreds
            self.saved: list = []

        async def list_connections(self, tid):
            return [{"provider": p, "scopes": c.scopes, "expires_at": c.expires_at,
                     "connected_at": now} for p, c in self._conns.items()]

        async def load_tokens(self, tid, provider=None):
            if provider is not None:
                return self._conns.get(provider)
            return next(iter(self._conns.values()), None)

        async def save_tokens(self, tid, creds):
            self.saved.append((tid, creds))
            self._conns[creds.provider] = creds

    class NoRefreshOauth:
        def needs_refresh(self, creds):
            return False   # ambos tokens vigentes: no hace falta refrescar

    conns = {
        "microsoft": OAuthCreds("microsoft", "AT-ms", "RT-ms", now + timedelta(hours=1)),
        "google": OAuthCreds("google", "AT-gg", "RT-gg", now + timedelta(hours=1)),
    }
    svc = MailboxService(http=object(), store_mod=FakeStoreMulti(conns),
                         oauth_mod=NoRefreshOauth(), client_credentials=lambda p: ("id", "sec"))
    resolved = await svc.connectors_for("t-multi")
    check("mx-07 · connectors_for: un conector por CADA proveedor conectado (microsoft Y google)",
          set(resolved.keys()) == {"microsoft", "google"}
          and resolved["microsoft"].provider == "microsoft"
          and resolved["google"].provider == "google")

    # sin conexiones -> {} (silencio, mismo criterio que connector_for)
    svc_none = MailboxService(http=object(), store_mod=FakeStoreMulti({}),
                              oauth_mod=NoRefreshOauth(), client_credentials=lambda p: ("id", "sec"))
    check("mx-08 · connectors_for: sin cuentas conectadas -> {} (silencio)",
          await svc_none.connectors_for("t-none") == {})

    # list_connections que revienta (migración ausente / DB caída) -> {} (no tumba nada)
    class BoomStore:
        async def list_connections(self, tid):
            raise RuntimeError("tabla ausente")

    svc_boom = MailboxService(http=object(), store_mod=BoomStore(), oauth_mod=NoRefreshOauth(),
                              client_credentials=lambda p: ("id", "sec"))
    check("mx-09 · connectors_for: list_connections cae -> {} (degradación, no revienta)",
          await svc_boom.connectors_for("t-boom") == {})

    # ── C · watch_engine vigila AMBOS proveedores sin duplicar avisos ────────
    class FakeConnector:
        def __init__(self, provider, events=None, mail=None, bodies=None):
            self.provider = provider
            self._events = events or []
            self._mail = mail or []
            self._bodies = bodies or {}

        async def upcoming_events(self, within_hours, now=None):
            return list(self._events)

        async def recent_mail(self, max_results=25, unread_only=True):
            return list(self._mail)

        async def fetch_body(self, external_id):
            return self._bodies.get(external_id, "")

    class FakeMailboxMulti:
        """MailboxService doblado con VARIOS proveedores conectados a la vez."""
        def __init__(self, connectors: dict):
            self._c = connectors

        async def connector_for(self, tid, provider=None):
            if provider:
                return self._c.get(provider)
            return next(iter(self._c.values()), None)

        async def connectors_for(self, tid):
            return dict(self._c)

        async def aclose(self):
            pass

    class FakeWatchStore:
        def __init__(self, already=None):
            self.already = set(already or [])
            self.marked: list = []

        async def filter_unnotified(self, tid, kind, ids):
            return {i for i in ids if i not in self.already}

        async def mark_notified(self, tid, kind, ids):
            self.marked.append((kind, list(ids)))

    sent: list = []

    async def fake_notify(msg):
        sent.append(msg)
        return True

    ev_ms = CalendarEvent("microsoft", "ev1", "Audiencia HDI (Outlook)", now + timedelta(hours=10))
    ev_gg = CalendarEvent("google", "ev1", "Reunión cliente (Google)", now + timedelta(hours=20))
    mailbox2 = FakeMailboxMulti({
        "microsoft": FakeConnector("microsoft", events=[ev_ms]),
        "google": FakeConnector("google", events=[ev_gg]),
    })
    ws = FakeWatchStore()
    watch = we.calendar_events_watch(resolve_tenant=lambda: "t-multi", mailbox=mailbox2,
                                     store_mod=ws, telegram_configured=lambda: True)
    r = await we.run_watch(watch, notify_fn=fake_notify, claim=False)
    check("mx-10 · calendario: eventos de AMBOS proveedores se superfician juntos "
          "(mismo external_id crudo 'ev1', proveedores distintos)",
          r.get("surfaced") is True and "Audiencia HDI (Outlook)" in sent[0]
          and "Reunión cliente (Google)" in sent[0])
    check("mx-11 · calendario: el debounce queda prefijado por proveedor (no colisiona "
          "aunque ambos usen el id crudo 'ev1')",
          set(ws.marked[0][1]) == {"microsoft:ev1", "google:ev1"})

    # segunda pasada: ya avisado en AMBOS proveedores -> silencio total (no se re-notifica
    # ni siquiera parcialmente)
    ws2 = FakeWatchStore(already=["microsoft:ev1", "google:ev1"])
    watch2 = we.calendar_events_watch(resolve_tenant=lambda: "t-multi", mailbox=mailbox2,
                                      store_mod=ws2, telegram_configured=lambda: True)
    sent.clear()
    r2 = await we.run_watch(watch2, notify_fn=fake_notify, claim=False)
    check("mx-12 · calendario: con debounce ya marcado en ambos proveedores -> silencio",
          r2.get("surfaced") is False and sent == [])

    # un proveedor falla (API caída) -> el otro sigue reportando (no tumba el ciclo)
    class BoomConnector:
        provider = "microsoft"
        async def upcoming_events(self, within_hours, now=None):
            raise RuntimeError("Graph caído")

    mailbox3 = FakeMailboxMulti({"microsoft": BoomConnector(), "google": FakeConnector("google", events=[ev_gg])})
    watch3 = we.calendar_events_watch(resolve_tenant=lambda: "t-multi", mailbox=mailbox3,
                                      store_mod=FakeWatchStore(), telegram_configured=lambda: True)
    sent.clear()
    r3 = await we.run_watch(watch3, notify_fn=fake_notify, claim=False)
    check("mx-13 · calendario: un proveedor caído no calla al otro (Google sigue avisando)",
          r3.get("surfaced") is True and "Reunión cliente (Google)" in sent[0])

    # correo urgente de dos proveedores + resumen de contenido: fetch_body va al conector
    # CORRECTO por cabecera (nunca el cuerpo de un proveedor con las credenciales de otro)
    h_ms = MailHeader("microsoft", "m1", "URGENTE traslado (Outlook)",
                      sender="x@ramajudicial.gov.co", importance="high")
    h_gg = MailHeader("google", "m1", "URGENTE requerimiento (Gmail)",
                      sender="y@procuraduria.gov.co", importance="high")
    mail_mailbox = FakeMailboxMulti({
        "microsoft": FakeConnector("microsoft", mail=[h_ms], bodies={"m1": "cuerpo de Outlook"}),
        "google": FakeConnector("google", mail=[h_gg], bodies={"m1": "cuerpo de Gmail"}),
    })

    captured: dict = {"bodies": []}

    def fake_summarize(messages):
        captured["bodies"].append(messages[1]["content"])
        return "resumen combinado. [VERIFICAR]"

    async def content_on(tid):
        return True

    async def policy_soberano(tid):
        return "soberano"

    wsc = FakeWatchStore()
    cwatch = we.urgent_mail_watch(
        resolve_tenant=lambda: "t-multi", mailbox=mail_mailbox, store_mod=wsc,
        telegram_configured=lambda: True, notify_fn=fake_notify, content_allowed=content_on,
        summarize_fn=fake_summarize, policy_fn=policy_soberano)
    sent.clear()
    r4 = await we.run_watch(cwatch, claim=False)
    check("mx-14 · correo: dos proveedores urgentes, mismo external_id crudo -> ambos se "
          "recogen (debounce por proveedor)",
          r4.get("surfaced") is True and set(wsc.marked[0][1]) == {"microsoft:m1", "google:m1"})
    check("mx-15 · correo: el resumen trae el cuerpo del conector CORRECTO por cabecera "
          "(Outlook->Outlook, Gmail->Gmail; nunca cruzados)",
          any("cuerpo de Outlook" in b for b in captured["bodies"])
          and any("cuerpo de Gmail" in b for b in captured["bodies"]))


# ═══ Checks contra DB REAL: dos proveedores para el mismo tenant, RLS, disconnect
# selectivo, list_connections y compatibilidad de load_tokens sin `provider`.
def _sb():
    import psycopg
    kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres",
              password=os.getenv("PG_PASSWORD", ""))
    return psycopg.connect(autocommit=True, **kw)


async def db_checks() -> None:
    import init_mailbox
    import init_remote_sources
    from mia.connectors.mailbox import store
    from mia.connectors.mailbox.base import OAuthCreds
    from mia.db import pool

    init_mailbox.apply()
    init_remote_sources.apply()
    await pool.open_pool()

    now = datetime.now(timezone.utc)
    tenants: list[str] = []
    with _sb() as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A mailbox multi') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B mailbox multi') RETURNING id").fetchone()[0]
    ta, tb = str(a), str(b)
    tenants.extend([ta, tb])
    try:
        # dos proveedores para el MISMO tenant, a la vez
        await store.save_tokens(ta, OAuthCreds("microsoft", "AT-ms", "RT-ms",
                                               now + timedelta(hours=1), ("Mail.Read",)))
        await store.save_tokens(ta, OAuthCreds("google", "AT-gg", "RT-gg",
                                               now + timedelta(hours=1),
                                               ("https://www.googleapis.com/auth/gmail.metadata",)))
        got_ms = await store.load_tokens(ta, "microsoft")
        got_gg = await store.load_tokens(ta, "google")
        check("mxdb1 · store: Microsoft Y Google conectados A LA VEZ para el mismo tenant",
              got_ms is not None and got_ms.access_token == "AT-ms"
              and got_gg is not None and got_gg.access_token == "AT-gg")

        conexiones = await store.list_connections(ta)
        providers = {c["provider"] for c in conexiones}
        check("mxdb2 · list_connections: devuelve AMBAS conexiones, sin tokens/secretos",
              providers == {"microsoft", "google"}
              and all("access_token" not in c and "refresh_token" not in c for c in conexiones))

        # compatibilidad: load_tokens SIN provider -> la primera (orden por proveedor:
        # 'google' < 'microsoft' alfabéticamente)
        sin_provider = await store.load_tokens(ta)
        check("mxdb3 · load_tokens sin `provider` (compatibilidad): devuelve una conexión "
              "válida y determinista (la primera por orden alfabético de proveedor)",
              sin_provider is not None and sin_provider.provider == "google")

        # RLS: B no ve ninguna de las conexiones de A
        check("mxdb4 · RLS: el tenant B no ve las conexiones de A (ni Microsoft ni Google)",
              await store.load_tokens(tb, "microsoft") is None
              and await store.load_tokens(tb, "google") is None
              and await store.list_connections(tb) == [])

        # disconnect de UNO no borra el otro
        removed = await store.disconnect(ta, "google")
        check("mxdb5 · disconnect(provider='google'): borra SOLO Google; Microsoft sigue",
              removed is True
              and await store.load_tokens(ta, "google") is None
              and (await store.load_tokens(ta, "microsoft")) is not None)

        # reconectar Google y desconectar TODO (compatibilidad, sin provider)
        await store.save_tokens(ta, OAuthCreds("google", "AT-gg2", "RT-gg2", now + timedelta(hours=1)))
        removed_all = await store.disconnect(ta)
        check("mxdb6 · disconnect() sin `provider` (compatibilidad): borra TODAS las "
              "conexiones del tenant",
              removed_all is True and await store.list_connections(ta) == [])
    finally:
        with _sb() as c:
            c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))
        await pool.close_pool()


if __name__ == "__main__":
    asyncio.run(run_gate())
    if os.getenv("PG_PASSWORD"):
        asyncio.run(db_checks())
    else:
        check("mxdb · SKIP (sin PG_PASSWORD): no se ejercitó la DB real", False)
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks PASS")
    if all(ok for _, ok in _results):
        print("cimientos OAuth multi-proveedor OK — Fase 1 de fuentes remotas del "
              "expediente (Microsoft Y Google a la vez, RLS, debounce sin duplicar, "
              "scopes por feature).")
        sys.exit(0)
    sys.exit(1)
