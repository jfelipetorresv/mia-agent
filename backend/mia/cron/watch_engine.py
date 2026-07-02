"""Mia · cron.watch_engine — motor de vigilancia programada (CP-P1, Ola 2).

Eleva los recordatorios de CP-B3 a un MOTOR que vigila condiciones en el tiempo. Tres
capacidades sobre el scheduler existente (cron/scheduler.py):

1. AT-MOST-ONCE entre procesos (`claim_job`/`release_job`): un claim CAS en la tabla
   de sistema `scheduled_claims` asegura que, con >1 worker de uvicorn, solo UNO corre
   cada vigilancia por ciclo (cierra el Riesgo #22/#35.3). Fail-OPEN si la DB admin no
   está disponible: una vigilancia no debe DETENERSE por falta de coordinación — en
   Modo B (single worker) no hay a quién duplicar de todos modos.

2. WAKE-GATE: cada vigilancia trae un chequeo BARATO (`check`) que decide si hay algo
   que reportar. Si no (`should_surface=False`), el ciclo termina en SILENCIO — sin
   aviso y, para las de tipo 'agent', SIN gastar LLM. Es el candado de costo.

3. Jobs `no_agent`: vigilancias que solo escanean la DB y avisan por el canal, con CERO
   tokens. Las de tipo 'agent' reservan el LLM para cuando el wake-gate ya confirmó que
   vale la pena despertarlo.

REGLA DURA (plazos procesales): las vigilancias NUNCA calculan un término legal. La
vigilancia de plazos próximos solo SUPERFICIE fechas que el abogado YA fijó (y confirmó)
en sus recordatorios; el aviso viaja con [VERIFICAR]. Mia no agenda ni computa plazos.
"""
from __future__ import annotations

import asyncio
import logging
import os
import socket
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Optional

logger = logging.getLogger("mia.cron.watch")

DEFAULT_CLAIM_TTL_SECONDS = 3600  # si un worker muere sosteniendo el claim, otro lo retoma en 1h


@dataclass
class WatchResult:
    """Salida del wake-gate de una vigilancia."""
    should_surface: bool                       # ¿hay algo que reportar? (wake-gate)
    message: str = ""                          # aviso a enviar (vigilancias no_agent)
    items: list = field(default_factory=list)  # ítems detectados (para after_surface/traza)
    meta: dict = field(default_factory=dict)   # contexto (tenant_id, motivo de omisión…)


@dataclass
class Watch:
    """Una vigilancia: chequeo barato en el tiempo + acción al superar el umbral."""
    name: str
    interval_hours: float
    check: Callable[[], Awaitable[WatchResult]]        # BARATO: decide si superficiar
    kind: str = "no_agent"                             # "no_agent" | "agent"
    on_surface: Optional[Callable[[WatchResult], Awaitable[Any]]] = None   # 'agent': despierta el LLM
    after_surface: Optional[Callable[[WatchResult, bool], Awaitable[None]]] = None  # post-aviso (result, ok)


# ── identificación del worker y conexión admin ──────────────────────────────────
def _worker_id() -> str:
    return f"{os.getpid()}@{socket.gethostname()}"


def _admin_conn():
    """Conexión admin (postgres) para la tabla de sistema `scheduled_claims`, o None.

    Igual que la enumeración cross-tenant de scheduler.py: el claim es una operación de
    INSTALACIÓN (no de un despacho), fuera de RLS. Sin PG_PASSWORD → None (fail-open)."""
    import psycopg

    pw = os.getenv("PG_PASSWORD", "")
    if not pw:
        return None
    kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres", password=pw)
    return psycopg.connect(autocommit=True, **kw)


def _claim_sync(job_name: str, ttl_seconds: int, worker_id: str) -> bool:
    """Claim CAS atómico: gana quien inserta la fila o retoma un claim VENCIDO (>ttl).

    El `ON CONFLICT ... WHERE claimed_at < now()-ttl` es la puerta atómica: si hay un
    claim FRESCO (otro worker corriendo), el UPDATE no aplica y `RETURNING` no trae
    fila → perdimos. Fail-OPEN ante cualquier error de coordinación (sin DB, tabla
    ausente): devolvemos True para no detener la vigilancia."""
    try:
        conn = _admin_conn()
    except Exception:  # noqa: BLE001 — sin coordinación no bloqueamos la vigilancia
        logger.warning("watch claim: sin conexión admin; se corre sin at-most-once")
        return True
    if conn is None:
        return True
    try:
        with conn:
            row = conn.execute(
                "INSERT INTO scheduled_claims (job_name, claimed_at, claimed_by) "
                "VALUES (%s, now(), %s) "
                "ON CONFLICT (job_name) DO UPDATE "
                "  SET claimed_at = now(), claimed_by = EXCLUDED.claimed_by "
                "  WHERE scheduled_claims.claimed_at < now() - make_interval(secs => %s) "
                "RETURNING job_name",
                (job_name, worker_id, ttl_seconds),
            ).fetchone()
        return row is not None
    except Exception:  # noqa: BLE001 — tabla ausente u otra falla: fail-open
        logger.exception("watch claim: fallo de coordinación en %s; se corre sin claim", job_name)
        return True
    finally:
        try:
            conn.close()
        except Exception:  # noqa: BLE001
            pass


def _release_sync(job_name: str, worker_id: str) -> None:
    """Suelta el claim PROPIO (para que el próximo ciclo pueda retomarlo sin esperar el ttl)."""
    try:
        conn = _admin_conn()
        if conn is None:
            return
        with conn:
            conn.execute(
                "DELETE FROM scheduled_claims WHERE job_name = %s AND claimed_by = %s",
                (job_name, worker_id),
            )
        conn.close()
    except Exception:  # noqa: BLE001 — soltar es best-effort; el ttl lo retoma igual
        logger.warning("watch release: no se pudo soltar el claim de %s", job_name)


async def claim_job(job_name: str, *, ttl_seconds: int = DEFAULT_CLAIM_TTL_SECONDS,
                    worker_id: Optional[str] = None) -> bool:
    """True si este worker ganó el claim de `job_name` (at-most-once). Ver _claim_sync."""
    return await asyncio.to_thread(_claim_sync, job_name, ttl_seconds, worker_id or _worker_id())


async def release_job(job_name: str, *, worker_id: Optional[str] = None) -> None:
    await asyncio.to_thread(_release_sync, job_name, worker_id or _worker_id())


# ── ejecución de una vigilancia ─────────────────────────────────────────────────
async def run_watch(watch: Watch, *, notify_fn: Optional[Callable[[str], Awaitable[bool]]] = None,
                    claim: bool = True, worker_id: Optional[str] = None,
                    claim_ttl_seconds: int = DEFAULT_CLAIM_TTL_SECONDS) -> dict:
    """Corre una vigilancia: claim (at-most-once) → wake-gate → aviso/despertar del agente.

    Orden deliberado: el claim va PRIMERO (dos workers no repiten el trabajo); el
    wake-gate va antes del gasto (sin nada que reportar, ni se avisa ni se llama al LLM).
    `notify_fn` inyectable (default: Telegram de channels.notify)."""
    wid = worker_id or _worker_id()
    if claim and not await claim_job(watch.name, ttl_seconds=claim_ttl_seconds, worker_id=wid):
        return {"watch": watch.name, "skipped": "otro worker tiene el claim"}
    try:
        result = await watch.check()          # BARATO — el wake-gate
        if not result.should_surface:
            return {"watch": watch.name, "surfaced": False, **({"meta": result.meta} if result.meta else {})}

        if watch.kind == "no_agent":
            fn = notify_fn or _default_notify
            ok = await fn(result.message)
            if watch.after_surface is not None:
                await watch.after_surface(result, bool(ok))
            return {"watch": watch.name, "surfaced": bool(ok), "kind": "no_agent",
                    "items": len(result.items)}

        # kind == "agent": SOLO aquí se gasta LLM (el wake-gate ya dijo que vale la pena).
        if watch.on_surface is None:
            logger.warning("vigilancia 'agent' %s sin on_surface; nada que hacer", watch.name)
            return {"watch": watch.name, "surfaced": False, "error": "sin on_surface"}
        out = await watch.on_surface(result)
        if watch.after_surface is not None:
            await watch.after_surface(result, True)
        return {"watch": watch.name, "surfaced": True, "kind": "agent", "result": out}
    except Exception:  # noqa: BLE001 — una vigilancia rota se DEGRADA (no tumba el ciclo)
        # revisión capa 2 (H4): run_watch es autocontenido — captura aquí en vez de
        # apoyarse en el try/except del scheduler; el claim se libera igual en finally.
        logger.exception("vigilancia %s falló", watch.name)
        return {"watch": watch.name, "surfaced": False, "error": "vigilancia falló"}
    finally:
        if claim:
            await release_job(watch.name, worker_id=wid)


async def _default_notify(message: str) -> bool:
    from ..channels import notify
    return await notify.send_telegram(message)


# ── vigilancia concreta: plazos procesales PRÓXIMOS (no_agent) ───────────────────
DEADLINE_HEADS_UP_HOURS = 72          # avisa cuando un plazo entra en la ventana de 3 días
DEADLINE_WATCH_INTERVAL_HOURS = 6     # escanea cada 6h (basta para una ventana de 72h)


def _resolve_notify_tenant() -> Optional[str]:
    # Import diferido para evitar el ciclo con scheduler (que registra esta vigilancia).
    from .scheduler import _resolve_notify_tenant as resolve
    return resolve()


def _format_due(due_at) -> str:
    from ..assistant.reminders import format_due  # reutiliza el formateo humano de CP-B3
    return format_due(due_at)


def _build_heads_up_message(items: list, within_hours: int) -> str:
    from ..assistant.core import REMINDER_PROCEDURAL_WARNING
    dias = max(1, within_hours // 24)
    encabezado = (f"Plazo{'s' if len(items) > 1 else ''} procesal{'es' if len(items) > 1 else ''} "
                  f"próximo{'s' if len(items) > 1 else ''} (en menos de {dias} día{'s' if dias > 1 else ''}):")
    lineas = [f"- {it['text']} — vence {_format_due(it['due_at'])}" for it in items]
    return encabezado + "\n" + "\n".join(lineas) + "\n\n" + REMINDER_PROCEDURAL_WARNING


def upcoming_deadlines_watch(
    *,
    within_hours: int = DEADLINE_HEADS_UP_HOURS,
    resolve_tenant: Optional[Callable[[], Optional[str]]] = None,
    service: Any = None,
    telegram_configured: Optional[Callable[[], bool]] = None,
) -> Watch:
    """Vigilancia no_agent: avisa con anticipación de los plazos procesales PRÓXIMOS.

    REGLA DURA: solo superficie fechas que el abogado YA fijó en sus recordatorios
    (is_procedural); NO calcula términos. Cada recordatorio recibe UN aviso anticipado
    (heads_up_sent_at). Wake-gate: sin plazos próximos → silencio total. Dependencias
    inyectables para el gate."""
    def _service():
        if service is not None:
            return service
        from ..assistant.reminders import ReminderService
        return ReminderService()

    async def check() -> WatchResult:
        tc = telegram_configured
        if tc is None:
            from ..channels import notify
            tc = notify.telegram_configured
        if not tc():
            return WatchResult(False, meta={"skipped": "canal sin configurar"})
        rt = resolve_tenant or _resolve_notify_tenant
        tenant_id = rt()
        if not tenant_id:
            return WatchResult(False, meta={"skipped": "sin tenant de canal"})
        try:
            items = await _service().upcoming_procedural(tenant_id, within_hours)
        except Exception:  # noqa: BLE001 — migración ausente u otra falla: no tumbar el loop
            logger.exception("vigilancia de plazos: lectura fallida (tenant %s)", tenant_id)
            return WatchResult(False, meta={"error": "lectura fallida"})
        if not items:
            return WatchResult(False, meta={"tenant_id": tenant_id})   # wake-gate: nada próximo
        return WatchResult(True, message=_build_heads_up_message(items, within_hours),
                           items=items, meta={"tenant_id": tenant_id})

    async def after_surface(result: WatchResult, ok: bool) -> None:
        # Marca el aviso anticipado SOLO si el canal lo aceptó (si falló, se reintenta).
        if ok and result.items and result.meta.get("tenant_id"):
            try:
                await _service().mark_heads_up(
                    result.meta["tenant_id"], [it["id"] for it in result.items])
            except Exception:  # noqa: BLE001 — marcar es best-effort; peor caso: re-aviso
                logger.warning("vigilancia de plazos: no se pudo marcar heads_up_sent_at")

    return Watch("upcoming_deadlines", DEADLINE_WATCH_INTERVAL_HOURS, check,
                 kind="no_agent", after_surface=after_surface)


# ── vigilancias de calendario y correo (CP-P3, metadata-only, no_agent) ──────────
CALENDAR_HEADS_UP_HOURS = 48          # avisa de eventos dentro de los próximos 2 días
CALENDAR_WATCH_INTERVAL_HOURS = 6     # escanea cada 6h (basta para una ventana de 48h)
MAIL_WATCH_INTERVAL_HOURS = 0.5       # correo urgente: cada 30 min (quiere rapidez)
MAIL_MAX_SCAN = 25                    # cuántos correos recientes mirar por ciclo


def _open_mailbox(mailbox):
    """(servicio, ¿es propio?). Si no se inyecta, crea un MailboxService propio que
    debe cerrarse tras usarlo (maneja su cliente httpx). Uno inyectado (gate) no se cierra."""
    if mailbox is not None:
        return mailbox, False
    from ..connectors.mailbox.service import MailboxService
    return MailboxService(), True


def _mailbox_store(store_mod):
    if store_mod is not None:
        return store_mod
    from ..connectors.mailbox import store as s
    return s


def _build_calendar_message(events: list) -> str:
    from ..assistant.core import REMINDER_PROCEDURAL_WARNING
    from ..connectors.mailbox.base import event_is_procedural
    n = len(events)
    encabezado = (f"Evento{'s' if n > 1 else ''} próximo{'s' if n > 1 else ''} "
                  f"en tu calendario:")
    lineas, hay_procesal = [], False
    for ev in events:
        cuando = _format_due(ev.start) if ev.start else "fecha por confirmar"
        titulo = " ".join((ev.title or "(sin título)").split())
        lugar = f" · {' '.join(ev.location.split())}" if getattr(ev, "location", "") else ""
        lineas.append(f"- {titulo} — {cuando}{lugar}")
        hay_procesal = hay_procesal or event_is_procedural(ev)
    msg = encabezado + "\n" + "\n".join(lineas)
    if hay_procesal:  # regla dura: si parece audiencia/plazo, el aviso lleva [VERIFICAR]
        msg += "\n\n" + REMINDER_PROCEDURAL_WARNING
    return msg


def _build_urgent_mail_message(headers: list) -> str:
    n = len(headers)
    encabezado = (f"Correo{'s' if n > 1 else ''} que parece{'n' if n > 1 else ''} "
                  f"urgente{'s' if n > 1 else ''} en tu bandeja:")
    lineas = []
    for h in headers:
        quien = " ".join((h.sender_name or h.sender or "remitente desconocido").split())
        asunto = " ".join((h.subject or "(sin asunto)").split())
        lineas.append(f"- {quien}: {asunto}")
    return (encabezado + "\n" + "\n".join(lineas)
            + "\n\nRevisa tu bandeja para el detalle. "
            + "(Mia solo miró el remitente y el asunto, no el contenido.)")


def calendar_events_watch(
    *,
    within_hours: int = CALENDAR_HEADS_UP_HOURS,
    resolve_tenant: Optional[Callable[[], Optional[str]]] = None,
    mailbox: Any = None,
    store_mod: Any = None,
    telegram_configured: Optional[Callable[[], bool]] = None,
) -> Watch:
    """Vigilancia no_agent: avisa de EVENTOS próximos del calendario (posibles audiencias).

    Metadata-only: lee título, fecha y lugar — nunca el detalle. REGLA DURA: un evento
    con pinta procesal (audiencia, plazo…) se superficia con [VERIFICAR]; Mia no calcula
    términos. Debounce: cada evento se avisa una sola vez (ledger mailbox_notifications).
    Wake-gate: sin eventos nuevos → silencio total."""
    async def check() -> WatchResult:
        tc = telegram_configured
        if tc is None:
            from ..channels import notify
            tc = notify.telegram_configured
        if not tc():
            return WatchResult(False, meta={"skipped": "canal sin configurar"})
        tenant_id = (resolve_tenant or _resolve_notify_tenant)()
        if not tenant_id:
            return WatchResult(False, meta={"skipped": "sin tenant de canal"})

        svc, own = _open_mailbox(mailbox)
        try:
            connector = await svc.connector_for(tenant_id)
            if connector is None:
                return WatchResult(False, meta={"skipped": "sin cuenta conectada",
                                                "tenant_id": tenant_id})
            events = await connector.upcoming_events(within_hours)
        except Exception:  # noqa: BLE001 — API caída/migración ausente: no tumbar el loop
            logger.exception("vigilancia de calendario: lectura fallida (tenant %s)", tenant_id)
            return WatchResult(False, meta={"error": "lectura fallida"})
        finally:
            if own:
                await svc.aclose()

        events = [e for e in events if e.external_id and e.start]
        if not events:
            return WatchResult(False, meta={"tenant_id": tenant_id})   # wake-gate
        try:
            fresh = await _mailbox_store(store_mod).filter_unnotified(
                tenant_id, "calendar", [e.external_id for e in events])
        except Exception:  # noqa: BLE001 — sin debounce, peor caso: re-aviso (no callar)
            logger.exception("vigilancia de calendario: debounce fallido (tenant %s)", tenant_id)
            fresh = {e.external_id for e in events}
        events = [e for e in events if e.external_id in fresh]
        if not events:
            return WatchResult(False, meta={"tenant_id": tenant_id})   # todo ya avisado
        return WatchResult(True, message=_build_calendar_message(events),
                           items=events, meta={"tenant_id": tenant_id})

    async def after_surface(result: WatchResult, ok: bool) -> None:
        if ok and result.items and result.meta.get("tenant_id"):
            try:
                await _mailbox_store(store_mod).mark_notified(
                    result.meta["tenant_id"], "calendar",
                    [e.external_id for e in result.items])
            except Exception:  # noqa: BLE001 — marcar es best-effort
                logger.warning("vigilancia de calendario: no se pudo marcar el debounce")

    return Watch("calendar_events", CALENDAR_WATCH_INTERVAL_HOURS, check,
                 kind="no_agent", after_surface=after_surface)


def _build_summary_message(headers: list, summary: str) -> str:
    n = len(headers)
    encabezado = (f"Correo{'s' if n > 1 else ''} urgente{'s' if n > 1 else ''} "
                  f"(resumen de Mia):")
    return (encabezado + "\n" + summary.strip()
            + "\n\nMia leyó el contenido solo para resumir; revisa tu bandeja antes de actuar.")


async def _summarize_urgent_mail(tenant_id: str, headers: list, mailbox, summarize_fn,
                                 policy_fn=None) -> Optional[str]:
    """Trae el cuerpo de los correos urgentes, lo SELLA y lo resume con IA bajo la política
    de modelo del tenant. None si no se pudo (el llamador degrada a aviso metadata)."""
    from ..agent import llm
    from ..connectors.mailbox import analyze

    # Política de modelo del tenant, PRIMERO y de forma ESTRICTA (revisión capa 2,
    # BLOQUEANTE): si no se puede determinar con certeza (error de DB), se ABORTA el
    # resumen y se degrada a metadata — NUNCA se cae al default de config, que sería
    # fail-OPEN (un tenant 'soberano'/local terminaría mandando el cuerpo a la nube por un
    # timeout de DB). Solo con la política CIERTA se lee el cuerpo y se llama al LLM.
    pf = policy_fn or llm.model_policy_for_strict
    try:
        policy = await pf(tenant_id)
    except Exception:  # noqa: BLE001 — sin política cierta NO se arriesga la confidencialidad
        logger.exception("resumen de correo: política del tenant %s indeterminada; se ABORTA "
                         "el análisis de contenido (fail-closed, degrada a metadata)", tenant_id)
        return None

    svc, own = _open_mailbox(mailbox)
    try:
        connector = await svc.connector_for(tenant_id)
        if connector is None or not hasattr(connector, "fetch_body"):
            return None
        items = []
        for h in headers:
            try:
                body = await connector.fetch_body(h.external_id)
            except Exception:  # noqa: BLE001 — un correo ilegible no tumba el resumen
                body = ""
            items.append((h, body))
    except Exception:  # noqa: BLE001
        logger.exception("resumen de correo: no se pudo leer el cuerpo (tenant %s)", tenant_id)
        return None
    finally:
        if own:
            await svc.aclose()

    # El ContextVar de política se propaga al hilo de call_llm (asyncio.to_thread copia el
    # contexto), así el resumen corre por la cadena que el despacho eligió (soberano=local).
    token = llm.set_model_policy(policy)
    try:
        summary = await analyze.summarize_urgent(items, llm_fn=summarize_fn)
    except Exception:  # noqa: BLE001 — LLM caído: degrada a metadata, nunca revienta
        logger.exception("resumen de correo urgente falló (tenant %s)", tenant_id)
        return None
    finally:
        llm.reset_model_policy(token)
    return summary or None


def urgent_mail_watch(
    *,
    resolve_tenant: Optional[Callable[[], Optional[str]]] = None,
    mailbox: Any = None,
    store_mod: Any = None,
    telegram_configured: Optional[Callable[[], bool]] = None,
    notify_fn: Optional[Callable[[str], Awaitable[bool]]] = None,
    content_allowed: Optional[Callable[[str], Awaitable[bool]]] = None,
    summarize_fn: Optional[Callable[[list], str]] = None,
    policy_fn: Optional[Callable[[str], Awaitable[str]]] = None,
    max_scan: int = MAIL_MAX_SCAN,
) -> Watch:
    """Vigilancia 'agent': avisa de correos NO leídos que PARECEN urgentes.

    WAKE-GATE (check, BARATO, metadata-only): mira SOLO remitente, asunto y banderas —
    jamás el cuerpo; sin correos urgentes nuevos → silencio, sin gastar LLM.
    ON_SURFACE (tras el wake-gate): si el despacho AUTORIZÓ el análisis de contenido
    (CP-P4, opt-in fail-closed), trae el cuerpo, lo SELLA (CP-S1) y lo resume con IA bajo
    la política del tenant; si no, envía el aviso metadata de siempre. Debounce por correo.
    Si el resumen con IA falla, degrada al aviso metadata (nunca se queda sin avisar)."""
    from ..connectors.mailbox.base import mail_looks_urgent

    async def check() -> WatchResult:
        tc = telegram_configured
        if tc is None:
            from ..channels import notify
            tc = notify.telegram_configured
        if not tc():
            return WatchResult(False, meta={"skipped": "canal sin configurar"})
        tenant_id = (resolve_tenant or _resolve_notify_tenant)()
        if not tenant_id:
            return WatchResult(False, meta={"skipped": "sin tenant de canal"})

        svc, own = _open_mailbox(mailbox)
        try:
            connector = await svc.connector_for(tenant_id)
            if connector is None:
                return WatchResult(False, meta={"skipped": "sin cuenta conectada",
                                                "tenant_id": tenant_id})
            headers = await connector.recent_mail(max_results=max_scan, unread_only=True)
        except Exception:  # noqa: BLE001
            logger.exception("vigilancia de correo: lectura fallida (tenant %s)", tenant_id)
            return WatchResult(False, meta={"error": "lectura fallida"})
        finally:
            if own:
                await svc.aclose()

        urgentes = [h for h in headers if h.external_id and mail_looks_urgent(h)]
        if not urgentes:
            return WatchResult(False, meta={"tenant_id": tenant_id})   # wake-gate
        try:
            fresh = await _mailbox_store(store_mod).filter_unnotified(
                tenant_id, "mail", [h.external_id for h in urgentes])
        except Exception:  # noqa: BLE001
            logger.exception("vigilancia de correo: debounce fallido (tenant %s)", tenant_id)
            fresh = {h.external_id for h in urgentes}
        urgentes = [h for h in urgentes if h.external_id in fresh]
        if not urgentes:
            return WatchResult(False, meta={"tenant_id": tenant_id})
        return WatchResult(True, items=urgentes, meta={"tenant_id": tenant_id})

    async def on_surface(result: WatchResult) -> dict:
        tenant_id = result.meta.get("tenant_id")
        headers = result.items
        nf = notify_fn or _default_notify
        ca = content_allowed or _mailbox_store(store_mod).content_analysis_allowed
        use_content = False
        if tenant_id:
            try:
                use_content = bool(await ca(tenant_id))
            except Exception:  # noqa: BLE001 — fail-closed: sin certeza, metadata
                use_content = False

        message, summarized = None, False
        if use_content:
            summary = await _summarize_urgent_mail(tenant_id, headers, mailbox, summarize_fn,
                                                   policy_fn=policy_fn)
            if summary:
                message, summarized = _build_summary_message(headers, summary), True
        if message is None:   # opt-in apagado o resumen fallido → aviso metadata
            message = _build_urgent_mail_message(headers)

        ok = await nf(message)
        if ok and tenant_id:   # debounce SOLO si el aviso se entregó (si falló, se reintenta)
            try:
                await _mailbox_store(store_mod).mark_notified(
                    tenant_id, "mail", [h.external_id for h in headers])
            except Exception:  # noqa: BLE001
                logger.warning("vigilancia de correo: no se pudo marcar el debounce")
        return {"sent": bool(ok), "summarized": summarized, "count": len(headers)}

    return Watch("urgent_mail", MAIL_WATCH_INTERVAL_HOURS, check,
                 kind="agent", on_surface=on_surface)
