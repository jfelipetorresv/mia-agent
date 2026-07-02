"""
Mia · test_mailbox.py — gate de CP-P3 (conectores de calendario y correo — Ola 2).

Verifica OFFLINE (sin red: HTTP y store doblados) y contra DB REAL (tokens + debounce
+ RLS + opt-in), en el estilo de test_watch_engine.py:

  A. OAuth: authorize_url arma la URL con scopes/state; exchange_code parsea el token;
     refresh conserva el refresh_token viejo si el proveedor no lo reenvía; needs_refresh
     decide bien (sin token / sin expiración / vencido / vigente).
  B. Proveedores: Microsoft (Graph) y Google (Calendar/Gmail) NORMALIZAN su JSON a
     CalendarEvent/MailHeader (metadata-only — nunca el cuerpo).
  C. Heurística: mail_looks_urgent (bandera alta / remitente institucional / palabra);
     event_is_procedural (audiencia sí, almuerzo no); parse_dt (Z/offset/date/naive).
  D. Servicio: connector_for → None sin cuenta; refresca y PERSISTE el token vencido;
     sin app OAuth (client_id/secret) → None (degradación).
  E. Vigilancias (no_agent): calendario y correo superficia solo lo NUEVO y urgente;
     debounce; [VERIFICAR] en evento procesal; silencio sin cuenta / sin canal.
  F. Confidencialidad: la vigilancia de correo mira SOLO metadata (asunto/remitente),
     nunca el cuerpo; content_analysis_allowed es fail-closed (default False).
  G. Cableado: build_scheduler registra 'calendar_events' y 'urgent_mail'.

  DB real (mp-db*): store.save/load/disconnect, preservación del refresh_token, debounce
  (filter_unnotified/mark_notified), RLS entre tenants y el opt-in de análisis.

Exit 0 = PASS · 1 = FAIL.        .venv\\Scripts\\python.exe execution\\test_mailbox.py
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


# ── dobles de HTTP (estilo channels/notify: objeto con get/post async) ───────────
class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class RouteHttp:
    """get/post que responde según subcadenas de la URL (para probar sin red)."""
    def __init__(self, routes: dict, post_resp=None):
        self._routes = routes           # {subcadena_url: FakeResp}
        self._post_resp = post_resp
        self.calls: list = []

    async def get(self, url, params=None, headers=None):
        self.calls.append(("GET", url, params, headers))
        # match más específico primero (URLs con id de mensaje contienen "/messages/")
        for key in sorted(self._routes, key=len, reverse=True):
            if key in url:
                return self._routes[key]
        return FakeResp(404, {})

    async def post(self, url, data=None, headers=None):
        self.calls.append(("POST", url, data, headers))
        return self._post_resp


async def run_gate() -> None:
    from mia.connectors.mailbox import base, oauth, providers
    from mia.connectors.mailbox.base import CalendarEvent, MailHeader, OAuthCreds
    from mia.connectors.mailbox.service import MailboxService
    from mia.cron import build_scheduler
    from mia.cron import watch_engine as we

    now = datetime(2026, 7, 2, 12, 0, tzinfo=timezone.utc)

    # ── A · OAuth ────────────────────────────────────────────────────────────
    url = oauth.authorize_url("microsoft", client_id="cid", redirect_uri="https://x/cb",
                              state="st8", login_hint="a@b.co")
    check("mp-01 · authorize_url arma la URL de consentimiento con scopes/state/redirect",
          url.startswith(oauth.PROVIDER_OAUTH["microsoft"]["authorize_url"])
          and "client_id=cid" in url and "state=st8" in url
          and "Calendars.Read" in url and "redirect_uri=https" in url)

    http_tok = RouteHttp({}, post_resp=FakeResp(200, {
        "access_token": "AT1", "refresh_token": "RT1", "expires_in": 3600,
        "scope": "Calendars.Read Mail.Read"}))
    creds = await oauth.exchange_code("microsoft", code="c", client_id="cid",
                                      client_secret="sec", redirect_uri="https://x/cb",
                                      http=http_tok, now=now)
    check("mp-02 · exchange_code parsea access/refresh/expiración del token",
          creds.access_token == "AT1" and creds.refresh_token == "RT1"
          and creds.expires_at == now + timedelta(seconds=3600))

    # refresh que NO reenvía refresh_token → se conserva el viejo (Google típico).
    http_ref = RouteHttp({}, post_resp=FakeResp(200, {
        "access_token": "AT2", "expires_in": 3600}))
    creds2 = await oauth.refresh_access_token(creds, client_id="cid", client_secret="sec",
                                              http=http_ref, now=now)
    check("mp-03 · refresh conserva el refresh_token si el proveedor no lo reenvía",
          creds2.access_token == "AT2" and creds2.refresh_token == "RT1")

    fresh = OAuthCreds("microsoft", "AT", "RT", now + timedelta(hours=1))
    expired = OAuthCreds("microsoft", "AT", "RT", now - timedelta(minutes=1))
    no_exp = OAuthCreds("microsoft", "AT", "RT", None)
    check("mp-04 · needs_refresh: vigente=No, vencido=Sí, sin-expiración=Sí, sin-token=Sí",
          oauth.needs_refresh(fresh, now=now) is False
          and oauth.needs_refresh(expired, now=now) is True
          and oauth.needs_refresh(no_exp, now=now) is True
          and oauth.needs_refresh(OAuthCreds("microsoft", ""), now=now) is True)

    # ── B · proveedores normalizan su JSON ───────────────────────────────────
    ms_creds = OAuthCreds("microsoft", "AT")
    ms_http = RouteHttp({
        "/me/calendarView": FakeResp(200, {"value": [
            {"id": "ev1", "subject": "Audiencia HDI", "isAllDay": False,
             "start": {"dateTime": "2026-07-03T14:00:00"},
             "end": {"dateTime": "2026-07-03T15:00:00"},
             "location": {"displayName": "Juzgado 5"}}]}),
        "/me/messages": FakeResp(200, {"value": [
            {"id": "m1", "subject": "URGENTE traslado", "isRead": False,
             "importance": "high", "hasAttachments": True,
             "receivedDateTime": "2026-07-02T10:00:00Z",
             "from": {"emailAddress": {"name": "Juzgado", "address": "sec@ramajudicial.gov.co"}}}]}),
    })
    ms = providers.MicrosoftMailbox(ms_creds, http=ms_http)
    evs = await ms.upcoming_events(48, now=now)
    check("mp-05 · Microsoft: calendarView → CalendarEvent (título, fecha, lugar)",
          len(evs) == 1 and evs[0].title == "Audiencia HDI"
          and evs[0].external_id == "ev1" and evs[0].location == "Juzgado 5"
          and evs[0].start == datetime(2026, 7, 3, 14, 0, tzinfo=timezone.utc))
    mails = await ms.recent_mail()
    check("mp-06 · Microsoft: messages → MailHeader (asunto/remitente/bandera, sin cuerpo)",
          len(mails) == 1 and mails[0].subject == "URGENTE traslado"
          and mails[0].sender == "sec@ramajudicial.gov.co" and mails[0].importance == "high"
          and not hasattr(mails[0], "body"))

    g_creds = OAuthCreds("google", "AT")
    g_http = RouteHttp({
        "/calendars/primary/events": FakeResp(200, {"items": [
            {"id": "g1", "summary": "Reunión cliente",
             "start": {"dateTime": "2026-07-03T09:00:00-05:00"},
             "end": {"dateTime": "2026-07-03T10:00:00-05:00"}}]}),
        "/users/me/messages/gm1": FakeResp(200, {
            "id": "gm1", "labelIds": ["UNREAD", "IMPORTANT"],
            "snippet": "hola", "internalDate": "1751457600000",
            "payload": {"headers": [
                {"name": "From", "value": "Ana Ruiz <ana@cliente.co>"},
                {"name": "Subject", "value": "Consulta contrato"}]}}),
        "/users/me/messages": FakeResp(200, {"messages": [{"id": "gm1"}]}),
    })
    g = providers.GoogleMailbox(g_creds, http=g_http)
    gevs = await g.upcoming_events(48, now=now)
    check("mp-07 · Google: events → CalendarEvent (offset -05:00 respetado)",
          len(gevs) == 1 and gevs[0].title == "Reunión cliente"
          and gevs[0].start == datetime(2026, 7, 3, 14, 0, tzinfo=timezone.utc))
    gmails = await g.recent_mail()
    check("mp-08 · Google: Gmail metadata (2 pasos) → MailHeader con From/Subject/labels",
          len(gmails) == 1 and gmails[0].subject == "Consulta contrato"
          and gmails[0].sender == "ana@cliente.co" and gmails[0].sender_name == "Ana Ruiz"
          and gmails[0].is_unread is True and gmails[0].importance == "high")

    # ── C · heurísticas ──────────────────────────────────────────────────────
    def mh(**kw):
        base_kw = dict(provider="x", external_id="i", subject="", sender="", sender_name="",
                       importance="normal")
        base_kw.update(kw)
        return MailHeader(**base_kw)

    check("mp-09 · mail_looks_urgent: bandera alta / institucional / palabra → True",
          base.mail_looks_urgent(mh(importance="high"))
          and base.mail_looks_urgent(mh(sender="x@ramajudicial.gov.co"))
          and base.mail_looks_urgent(mh(subject="Vence el plazo hoy")))
    check("mp-10 · mail_looks_urgent: correo trivial → False (no despierta)",
          base.mail_looks_urgent(mh(subject="Almuerzo del viernes", sender="amigo@gmail.com")) is False)

    def ce(title):
        return CalendarEvent("x", "i", title, now)
    check("mp-11 · event_is_procedural: 'audiencia' Sí, 'almuerzo' No (regla dura)",
          base.event_is_procedural(ce("Audiencia de conciliación")) is True
          and base.event_is_procedural(ce("Almuerzo equipo")) is False)
    check("mp-12 · parse_dt: Z, offset, date, naive→UTC, basura→None",
          base.parse_dt("2026-07-02T10:00:00Z") == datetime(2026, 7, 2, 10, tzinfo=timezone.utc)
          and base.parse_dt("2026-07-02") == datetime(2026, 7, 2, tzinfo=timezone.utc)
          and base.parse_dt("2026-07-02T10:00:00").tzinfo is not None
          and base.parse_dt("no-fecha") is None and base.parse_dt("") is None)

    # ── D · servicio (store + oauth doblados) ────────────────────────────────
    class FakeStore:
        def __init__(self, creds=None):
            self._creds = creds
            self.saved: list = []

        async def load_tokens(self, tid):
            return self._creds

        async def save_tokens(self, tid, creds):
            self.saved.append((tid, creds))

    class FakeOauth:
        def __init__(self, needs, refreshed=None, boom=False):
            self._needs = needs
            self._refreshed = refreshed
            self._boom = boom
            self.called = False

        def needs_refresh(self, creds):
            return self._needs

        async def refresh_access_token(self, creds, *, client_id, client_secret, http):
            self.called = True
            if self._boom:
                raise RuntimeError("refresh caído")
            return self._refreshed

    # sin cuenta conectada → None
    svc = MailboxService(http=RouteHttp({}), store_mod=FakeStore(None),
                         oauth_mod=FakeOauth(False), client_credentials=lambda p: ("id", "sec"))
    check("mp-13 · service: sin cuenta conectada → connector_for None (silencio)",
          await svc.connector_for("t") is None)

    # token vigente → conector directo (sin refrescar)
    st = FakeStore(OAuthCreds("microsoft", "AT", "RT", now + timedelta(hours=1)))
    oa = FakeOauth(False)
    svc = MailboxService(http=RouteHttp({}), store_mod=st, oauth_mod=oa,
                         client_credentials=lambda p: ("id", "sec"))
    conn = await svc.connector_for("t")
    check("mp-14 · service: token vigente → conector del proveedor (sin refrescar)",
          conn is not None and conn.provider == "microsoft" and oa.called is False)

    # token vencido → refresca y PERSISTE
    st = FakeStore(OAuthCreds("microsoft", "AT", "RT", now - timedelta(minutes=1)))
    refreshed = OAuthCreds("microsoft", "AT-new", "RT", now + timedelta(hours=1))
    oa = FakeOauth(True, refreshed=refreshed)
    svc = MailboxService(http=RouteHttp({}), store_mod=st, oauth_mod=oa,
                         client_credentials=lambda p: ("id", "sec"))
    conn = await svc.connector_for("t")
    check("mp-15 · service: token vencido → refresca y persiste el nuevo",
          conn is not None and oa.called is True
          and st.saved and st.saved[0][1].access_token == "AT-new")

    # token vencido pero SIN app OAuth (client_id/secret) → None (degradación)
    st = FakeStore(OAuthCreds("microsoft", "AT", "RT", now - timedelta(minutes=1)))
    oa = FakeOauth(True, refreshed=refreshed)
    svc = MailboxService(http=RouteHttp({}), store_mod=st, oauth_mod=oa,
                         client_credentials=lambda p: ("", ""))
    check("mp-16 · service: sin app OAuth configurada → None (no intenta refrescar)",
          await svc.connector_for("t") is None and oa.called is False)

    # ── E/F · vigilancias no_agent (mailbox + store doblados) ────────────────
    class FakeConnector:
        def __init__(self, events=None, mail=None):
            self._events = events or []
            self._mail = mail or []

        async def upcoming_events(self, within_hours, now=None):
            return list(self._events)

        async def recent_mail(self, max_results=25, unread_only=True):
            return list(self._mail)

    class FakeMailbox:
        def __init__(self, connector):
            self._c = connector

        async def connector_for(self, tid):
            return self._c

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

    ev_proc = CalendarEvent("microsoft", "ev1", "Audiencia HDI", now + timedelta(hours=20),
                            location="Juzgado 5")
    ws = FakeWatchStore()
    watch = we.calendar_events_watch(resolve_tenant=lambda: "t-1",
                                     mailbox=FakeMailbox(FakeConnector(events=[ev_proc])),
                                     store_mod=ws, telegram_configured=lambda: True)
    sent.clear()
    r = await we.run_watch(watch, notify_fn=fake_notify, claim=False)
    check("mp-17 · calendario: un evento nuevo se superficia con aviso",
          r.get("surfaced") is True and len(sent) == 1 and "Audiencia HDI" in sent[0])
    check("mp-18 · calendario: evento procesal lleva [VERIFICAR] (regla dura)",
          "[VERIFICAR]" in sent[0])
    check("mp-19 · calendario: tras avisar, marca el debounce (no re-avisa)",
          ws.marked == [("calendar", ["ev1"])])

    # ya avisado → silencio
    watch2 = we.calendar_events_watch(resolve_tenant=lambda: "t-1",
                                      mailbox=FakeMailbox(FakeConnector(events=[ev_proc])),
                                      store_mod=FakeWatchStore(already=["ev1"]),
                                      telegram_configured=lambda: True)
    sent.clear()
    r = await we.run_watch(watch2, notify_fn=fake_notify, claim=False)
    check("mp-20 · calendario: evento ya avisado → silencio (debounce)",
          r.get("surfaced") is False and sent == [])

    # sin cuenta conectada → silencio
    watch3 = we.calendar_events_watch(resolve_tenant=lambda: "t-1",
                                      mailbox=FakeMailbox(None), store_mod=FakeWatchStore(),
                                      telegram_configured=lambda: True)
    sent.clear()
    r = await we.run_watch(watch3, notify_fn=fake_notify, claim=False)
    check("mp-21 · calendario: sin cuenta conectada → silencio",
          r.get("surfaced") is False and sent == [])

    # correo urgente: solo el urgente y no-avisado se superficia
    urgente = MailHeader("microsoft", "m1", "URGENTE traslado", sender="x@ramajudicial.gov.co",
                         importance="high")
    trivial = MailHeader("microsoft", "m2", "Almuerzo", sender="amigo@gmail.com")
    wsm = FakeWatchStore()
    mwatch = we.urgent_mail_watch(resolve_tenant=lambda: "t-1",
                                  mailbox=FakeMailbox(FakeConnector(mail=[urgente, trivial])),
                                  store_mod=wsm, telegram_configured=lambda: True)
    sent.clear()
    r = await we.run_watch(mwatch, notify_fn=fake_notify, claim=False)
    check("mp-22 · correo: solo el que PARECE urgente se superficia (el trivial no)",
          r.get("surfaced") is True and "URGENTE traslado" in sent[0]
          and "Almuerzo" not in sent[0] and wsm.marked == [("mail", ["m1"])])
    check("mp-23 · correo: el aviso deja claro que NO se miró el contenido (confidencialidad)",
          "no el contenido" in sent[0].lower())

    # sin nada urgente → silencio
    mwatch2 = we.urgent_mail_watch(resolve_tenant=lambda: "t-1",
                                   mailbox=FakeMailbox(FakeConnector(mail=[trivial])),
                                   store_mod=FakeWatchStore(), telegram_configured=lambda: True)
    sent.clear()
    r = await we.run_watch(mwatch2, notify_fn=fake_notify, claim=False)
    check("mp-24 · correo: sin correos urgentes → silencio (wake-gate)",
          r.get("surfaced") is False and sent == [])

    # sin canal → silencio
    mwatch3 = we.urgent_mail_watch(resolve_tenant=lambda: "t-1",
                                   mailbox=FakeMailbox(FakeConnector(mail=[urgente])),
                                   store_mod=FakeWatchStore(), telegram_configured=lambda: False)
    sent.clear()
    r = await we.run_watch(mwatch3, notify_fn=fake_notify, claim=False)
    check("mp-25 · correo: sin canal de Telegram → silencio (opt-in)",
          r.get("surfaced") is False and sent == [])

    # ── G · cableado ─────────────────────────────────────────────────────────
    names = [j["name"] for j in build_scheduler().list_jobs()]
    check("mp-26 · build_scheduler registra 'calendar_events' y 'urgent_mail'",
          "calendar_events" in names and "urgent_mail" in names)

    # ── H · rutas OAuth: `state` firmado y gating (seguridad del flujo web) ───
    import jwt as _jwt
    from types import SimpleNamespace
    from urllib.parse import parse_qs, urlparse

    from fastapi import HTTPException
    from mia import config as _config
    from mia.api.routes import mailbox as mb

    tid, prov, non = mb.verify_state(mb.sign_state("t-9", "microsoft", "n1"))
    check("mp-r1 · state OAuth: sign→verify recupera (tenant, proveedor, nonce)",
          tid == "t-9" and prov == "microsoft" and non == "n1")

    def _raises_400(fn):
        try:
            fn()
            return False
        except HTTPException as e:
            return e.status_code == 400

    check("mp-r2 · state OAuth: un state manipulado se rechaza (400)",
          _raises_400(lambda: mb.verify_state("basura.no.jwt")))
    bad_purpose = _jwt.encode({"tenant_id": "t", "provider": "microsoft", "purpose": "otro"},
                              _config.JWT_SECRET, algorithm=_config.JWT_ALG)
    check("mp-r3 · state OAuth: un JWT con propósito distinto se rechaza (anti-reuso)",
          _raises_400(lambda: mb.verify_state(bad_purpose)))

    class FakeReq:
        def __init__(self, tenant_id=None, email="", query=None, body=None, cookies=None):
            self.state = SimpleNamespace(tenant_id=tenant_id, email=email)
            self.query_params = query or {}
            self.cookies = cookies or {}
            self._body = body

        async def json(self):
            if self._body is None:
                raise ValueError("sin cuerpo")
            return self._body

    class FakeCookieResp:
        def __init__(self):
            self.cookies_set: list = []

        def set_cookie(self, key, value, **kw):
            self.cookies_set.append((key, value, kw))

    async def _status(fn):
        try:
            await fn()
            return None
        except HTTPException as e:
            return e.status_code

    st = await _status(lambda: mb.connect("desconocido", FakeReq(tenant_id="t-1"), FakeCookieResp()))
    check("mp-r4 · connect: proveedor no soportado → 404", st == 404)

    saved_id, saved_sec = _config.MS_OAUTH_CLIENT_ID, _config.MS_OAUTH_CLIENT_SECRET
    _config.MS_OAUTH_CLIENT_ID, _config.MS_OAUTH_CLIENT_SECRET = "", ""
    try:
        st = await _status(lambda: mb.connect("microsoft", FakeReq(tenant_id="t-1"), FakeCookieResp()))
        check("mp-r5 · connect: sin app OAuth registrada → 503 (no expone flujo roto)",
              st == 503)
        _config.MS_OAUTH_CLIENT_ID, _config.MS_OAUTH_CLIENT_SECRET = "cid", "sec"
        resp_c = FakeCookieResp()
        out = await mb.connect("microsoft", FakeReq(tenant_id="t-1", email="a@b.co"), resp_c)
        qs = parse_qs(urlparse(out["url"]).query)
        tid2, prov2, non2 = mb.verify_state(qs["state"][0])
        cookie_set = resp_c.cookies_set and resp_c.cookies_set[0]
        check("mp-r6 · connect: con app OAuth → URL de consentimiento con state válido del tenant",
              out["url"].startswith(oauth.PROVIDER_OAUTH["microsoft"]["authorize_url"])
              and tid2 == "t-1" and prov2 == "microsoft" and qs["client_id"][0] == "cid")
        # binding: la cookie-nonce que se fija == el nonce firmado en el state, y es HttpOnly
        check("mp-r6b · connect: fija cookie-nonce (HttpOnly) igual al nonce del state (binding)",
              cookie_set and cookie_set[0] == "mia_oauth_nonce" and cookie_set[1] == non2
              and cookie_set[2].get("httponly") is True)
    finally:
        _config.MS_OAUTH_CLIENT_ID, _config.MS_OAUTH_CLIENT_SECRET = saved_id, saved_sec

    resp = await mb.oauth_callback(FakeReq(query={"error": "access_denied"}))
    check("mp-r7 · callback: si el proveedor niega el permiso → redirige (no revienta)",
          getattr(resp, "status_code", 0) == 302)
    st = await _status(lambda: mb.oauth_callback(FakeReq(query={"state": "x"})))
    check("mp-r8 · callback: sin código de autorización → 400", st == 400)

    # binding sesión↔state (hallazgo #1): state válido pero cookie-nonce que NO coincide.
    good_state = mb.sign_state("t-1", "microsoft", "NONCE-A")
    st = await _status(lambda: mb.oauth_callback(
        FakeReq(query={"code": "c", "state": good_state}, cookies={"mia_oauth_nonce": "NONCE-B"})))
    check("mp-r9 · callback: nonce del state ≠ cookie → 400 (bloquea fijación de cuenta)",
          st == 400)
    st = await _status(lambda: mb.oauth_callback(
        FakeReq(query={"code": "c", "state": good_state}, cookies={})))
    check("mp-r10 · callback: sin cookie-nonce → 400 (consentimiento no atado a la sesión)",
          st == 400)


# ═══ Checks contra DB REAL: tokens (save/load/refresh-preserve/disconnect), debounce
# (filter_unnotified/mark_notified), RLS entre tenants y opt-in de análisis.
def _sb():
    import psycopg
    kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres",
              password=os.getenv("PG_PASSWORD", ""))
    return psycopg.connect(autocommit=True, **kw)


async def db_checks() -> None:
    import init_mailbox
    from mia.connectors.mailbox import store
    from mia.connectors.mailbox.base import OAuthCreds
    from mia.db import pool

    init_mailbox.apply()
    await pool.open_pool()

    now = datetime.now(timezone.utc)
    tenants: list[str] = []
    with _sb() as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A mailbox cpp3') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B mailbox cpp3') RETURNING id").fetchone()[0]
    ta, tb = str(a), str(b)
    tenants.extend([ta, tb])
    try:
        # save/load
        await store.save_tokens(ta, OAuthCreds("microsoft", "AT1", "RT1",
                                               now + timedelta(hours=1), ("Calendars.Read",)))
        got = await store.load_tokens(ta)
        check("mp-db1 · store: save→load devuelve el token (provider/access/refresh)",
              got is not None and got.access_token == "AT1" and got.refresh_token == "RT1"
              and got.provider == "microsoft")

        # re-save con refresh_token vacío → conserva el viejo (regla del ON CONFLICT)
        await store.save_tokens(ta, OAuthCreds("microsoft", "AT2", "",
                                               now + timedelta(hours=2), ("Calendars.Read",)))
        got2 = await store.load_tokens(ta)
        check("mp-db2 · store: re-save sin refresh_token conserva el refresh viejo",
              got2.access_token == "AT2" and got2.refresh_token == "RT1")

        # RLS: B no ve el token de A
        check("mp-db3 · RLS: el tenant B no ve los tokens de A",
              await store.load_tokens(tb) is None)

        # debounce ledger
        fresh = await store.filter_unnotified(ta, "calendar", ["e1", "e2"])
        check("mp-db4 · debounce: nada avisado aún → todos los ids son nuevos",
              fresh == {"e1", "e2"})
        await store.mark_notified(ta, "calendar", ["e1"])
        fresh2 = await store.filter_unnotified(ta, "calendar", ["e1", "e2"])
        check("mp-db5 · debounce: tras mark_notified, e1 ya NO es nuevo (no re-avisa)",
              fresh2 == {"e2"})
        # RLS del ledger: B ve todos como nuevos (los de A no le aplican)
        check("mp-db6 · RLS: el ledger de avisos de A no afecta a B",
              await store.filter_unnotified(tb, "calendar", ["e1"]) == {"e1"})

        # poda del ledger (hallazgo #3): una fila > 30 días se borra en el siguiente
        # mark_notified; una reciente sobrevive (no rompe el debounce de la ventana 48h).
        with _sb() as c:
            c.execute("INSERT INTO mailbox_notifications (tenant_id, kind, external_id, notified_at) "
                      "VALUES (%s::uuid, 'calendar', 'viejo', now() - interval '40 days') "
                      "ON CONFLICT DO NOTHING", (ta,))
        await store.mark_notified(ta, "calendar", ["reciente"])   # dispara la poda
        still_new = await store.filter_unnotified(ta, "calendar", ["viejo", "reciente"])
        check("mp-db6b · poda: entrada > 30 días se borra (reaparece como nueva); la reciente sobrevive",
              "viejo" in still_new and "reciente" not in still_new)

        # opt-in de análisis de contenido: default False, luego True
        before = await store.content_analysis_allowed(ta)
        with _sb() as c:
            c.execute(
                "INSERT INTO tenant_settings (tenant_id, config) "
                "VALUES (%s::uuid, jsonb_build_object('mailbox', "
                "  jsonb_build_object('allow_content_analysis', true))) "
                "ON CONFLICT (tenant_id) DO UPDATE SET config = jsonb_set("
                "  coalesce(tenant_settings.config,'{}'::jsonb), '{mailbox}', "
                "  jsonb_build_object('allow_content_analysis', true), true)",
                (ta,))
        after = await store.content_analysis_allowed(ta)
        check("mp-db7 · opt-in análisis: default False; tras autorizar en settings → True",
              before is False and after is True)

        # disconnect
        removed = await store.disconnect(ta)
        check("mp-db8 · store: disconnect elimina los tokens del tenant",
              removed is True and await store.load_tokens(ta) is None)
    finally:
        with _sb() as c:
            c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))
        await pool.close_pool()


if __name__ == "__main__":
    asyncio.run(run_gate())
    if os.getenv("PG_PASSWORD"):
        asyncio.run(db_checks())
    else:
        check("mp-db · SKIP (sin PG_PASSWORD): no se ejercitó la DB real", False)
    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks PASS")
    if all(ok for _, ok in _results):
        print("conectores de calendario/correo OK — CP-P3 verificado (Graph+Google "
              "metadata-only, refresco de token, debounce y RLS, [VERIFICAR] en eventos).")
        sys.exit(0)
    sys.exit(1)
