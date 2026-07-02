"""Mia · cron.scheduler — registro de jobs periódicos en memoria (Módulo 3c · decisión #17 C3).

No usa APScheduler ni ninguna dependencia externa: es un registro simple
{name -> (func async, interval_hours)} con `list_jobs()`, `run_job(name)` (dispara ya) y
`start()` (loop asyncio que dispara cada job según su intervalo).

Job del sistema: `sync_obsidian_all_tenants` cada 6h — itera los tenants con
`tenant_settings.config->>'obsidian_vault_path'` configurado y corre `ObsidianSync().sync`.

NOTA DE AISLAMIENTO (Riesgo #15): enumerar "qué tenants tienen Obsidian configurado" es una
operación de SISTEMA, cross-tenant, que bajo RLS (fail-closed) no es visible desde una sola
conexión `mia_app`. La enumeración usa una conexión admin (`postgres`); la ESCRITURA por
tenant sigue pasando por `pool.tenant_connection` (RLS). Acotar esto (función SECURITY DEFINER
o rol dedicado) queda para multi-tenant en producción.
"""
from __future__ import annotations

import logging
import os
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable

logger = logging.getLogger("mia.cron")

Job = Callable[[], Awaitable]


class Scheduler:
    """Registro de jobs periódicos en memoria."""

    def __init__(self) -> None:
        self._jobs: dict[str, dict] = {}

    def register_job(self, name: str, func: Job, interval_hours: float) -> None:
        if name in self._jobs:
            raise ValueError(f"job ya registrado: {name}")
        self._jobs[name] = {
            "name": name, "func": func, "interval_hours": float(interval_hours),
            "last_run": None, "next_run": None,
        }

    def list_jobs(self) -> list[dict]:
        """Jobs registrados (sin el callable), para inspección/monitoreo."""
        return [
            {"name": j["name"], "interval_hours": j["interval_hours"],
             "last_run": j["last_run"], "next_run": j["next_run"]}
            for j in self._jobs.values()
        ]

    async def run_job(self, name: str):
        """Dispara un job inmediatamente y actualiza last_run/next_run."""
        job = self._jobs[name]
        now = datetime.now(timezone.utc)
        job["last_run"] = now
        job["next_run"] = now + timedelta(hours=job["interval_hours"])
        return await job["func"]()

    async def start(self, poll_seconds: int = 60) -> None:
        """Loop asyncio: dispara cada job cuando vence su next_run. Bloquea; correrlo como
        tarea de fondo en el lifespan de la app.

        La PRIMERA ejecución de cada job se agenda a un intervalo de distancia (no al
        arrancar): un job diario/semanal NO debe correr en cada reinicio de la app. Para
        forzar una corrida inmediata, usar `run_job(name)`."""
        import asyncio

        now = datetime.now(timezone.utc)
        for job in self._jobs.values():
            if job["next_run"] is None:
                job["next_run"] = now + timedelta(hours=job["interval_hours"])
        self._running = True
        while getattr(self, "_running", False):
            now = datetime.now(timezone.utc)
            for job in list(self._jobs.values()):
                if job["next_run"] is not None and now >= job["next_run"]:
                    try:
                        await self.run_job(job["name"])
                    except Exception:
                        logger.exception("job %s falló", job["name"])
            await asyncio.sleep(poll_seconds)

    def stop(self) -> None:
        self._running = False


# ── job del sistema ──────────────────────────────────────────────────────────
def _enumerate_obsidian_targets() -> list[tuple[str, str]]:
    """[(tenant_id, vault_path)] de los tenants con Obsidian configurado. Lee
    tenant_settings con conexión admin (cross-tenant, operación de sistema — ver nota de
    aislamiento). Fallback: OBSIDIAN_VAULT_PATH de .env como default del tenant de
    desarrollo si su setting no trae vault."""
    import psycopg

    pw = os.getenv("PG_PASSWORD", "")
    if not pw:
        logger.warning("PG_PASSWORD vacío: el job de Obsidian no puede enumerar tenants")
        return []
    kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres", password=pw)
    default = os.getenv("OBSIDIAN_VAULT_PATH", "")
    targets: list[tuple[str, str]] = []
    with psycopg.connect(autocommit=True, **kw) as c:
        rows = c.execute(
            "SELECT tenant_id, config->>'obsidian_vault_path' FROM tenant_settings"
        ).fetchall()
    for tid, vault in rows:
        path = vault or default
        if path:
            targets.append((str(tid), path))
    return targets


async def sync_obsidian_all_tenants() -> dict:
    """Sincroniza el vault de Obsidian de cada tenant configurado. Devuelve
    {tenant_id: stats}. La escritura por tenant pasa por RLS (ObsidianSync)."""
    from ..connectors import ObsidianSync

    sync = ObsidianSync()
    out: dict[str, dict] = {}
    for tenant_id, vault_path in _enumerate_obsidian_targets():
        try:
            out[tenant_id] = await sync.sync(vault_path, tenant_id)
        except Exception as e:  # un tenant no debe tumbar a los demás
            out[tenant_id] = {"error": str(e)}
            logger.exception("sync de Obsidian falló para tenant %s", tenant_id)
    return out


def _enumerate_local_folder_tenants() -> list[str]:
    """Tenants con al menos una carpeta de trabajo registrada y habilitada (CP-C1).
    Hereda el Riesgo #15: enumerar tenants es una operación de SISTEMA, cross-tenant,
    invisible bajo RLS fail-closed desde `mia_app` — se usa conexión admin (`postgres`)
    SOLO para leer qué tenants sincronizar; la escritura por tenant sigue pasando por
    `pool.tenant_connection` (RLS). Acotar (SECURITY DEFINER o rol dedicado) queda para
    multi-tenant en producción, igual que el job de Obsidian."""
    import psycopg

    pw = os.getenv("PG_PASSWORD", "")
    if not pw:
        logger.warning("PG_PASSWORD vacío: el job de carpetas locales no puede enumerar tenants")
        return []
    kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres", password=pw)
    try:
        with psycopg.connect(autocommit=True, **kw) as c:
            rows = c.execute(
                "SELECT DISTINCT tenant_id FROM local_folder_sources WHERE enabled"
            ).fetchall()
    except psycopg.errors.UndefinedTable:
        # migración 016 aún no aplicada — no hay nada que sincronizar.
        return []
    return [str(r[0]) for r in rows]


async def sync_local_folders_all_tenants() -> dict:
    """Sincroniza las carpetas de trabajo registradas (allowlist) de cada tenant (CP-C1).
    Devuelve {tenant_id: stats}. La enumeración de tenants usa conexión admin (hereda el
    Riesgo #15 — ver _enumerate_local_folder_tenants); la escritura por tenant pasa por
    RLS (LocalFolderSync). NUNCA se escanea nada fuera de las fuentes registradas."""
    from ..connectors.local_folders import LocalFolderSync

    sync = LocalFolderSync()
    out: dict[str, dict] = {}
    for tenant_id in _enumerate_local_folder_tenants():
        try:
            out[tenant_id] = await sync.sync_tenant(tenant_id)
        except Exception as e:  # un tenant no debe tumbar a los demás
            out[tenant_id] = {"error": str(e)}
            logger.exception("sync de carpetas locales falló para tenant %s", tenant_id)
    return out


async def curator_run_all_tenants() -> dict:
    """Mantenimiento semántico de playbooks de todos los tenants (Módulo 3b).
    Domingos 2am — el scheduler NO tiene timezone awareness en v1; el intervalo es de 168h
    (7 días). Ajustar si se necesita la hora exacta del domingo.

    H.2 (cierra Riesgo #19): el cron ahora solo PROPONE (dry-run + persistencia como `pending`);
    ninguna fusión/poda se ejecuta sin que un abogado la apruebe (endpoints /api/curator/*)."""
    from ..memory.curator import Curator

    return await Curator().propose_all_tenants()


async def feedback_run_all_tenants() -> dict:
    """Procesa las trazas de todos los tenants y genera propuestas de mejora (Módulo 3e).
    Diario 1am — sin timezone en v1; intervalo de 24h (decisión #19)."""
    from ..memory.feedback_processor import FeedbackProcessor

    return await FeedbackProcessor().run_all_tenants()


async def gepa_run_all_tenants() -> dict:
    """Evolución procedural semanal de playbooks por tenant."""
    from ..memory.gepa import GEPALoop

    return await GEPALoop().run_all_tenants()


async def dreams_run_all_tenants() -> dict:
    """Consolidación semanal profunda del second brain por tenant."""
    from ..memory.dreams import Dreams

    return await Dreams().run_all_tenants()


def build_scheduler() -> Scheduler:
    """Scheduler con los jobs del sistema (Obsidian 6h, Curator 168h, Feedback 24h)."""
    sched = Scheduler()
    sched.register_job("sync_obsidian_all_tenants", sync_obsidian_all_tenants, interval_hours=6)
    # carpetas de trabajo (CP-C1): diaria — cadencia menor que Obsidian a propósito
    # (carpetas grandes con PDF/Word; la incremental por hash hace barato el re-sync).
    sched.register_job("sync_local_folders_all_tenants", sync_local_folders_all_tenants,
                       interval_hours=24)
    # domingos 2am — sin timezone en v1; intervalo semanal de 168h (decisión #18).
    sched.register_job("curator_weekly", curator_run_all_tenants, interval_hours=168)
    # domingos 4am — Dreams llama GEPA internamente; no hay job GEPA separado.
    sched.register_job("dreams_weekly", dreams_run_all_tenants, interval_hours=168)
    # diario 1am — sin timezone en v1; intervalo de 24h (decisión #19).
    sched.register_job("feedback_daily", feedback_run_all_tenants, interval_hours=24)
    return sched
