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
