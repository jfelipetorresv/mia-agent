"""Mia · api.routes.setup — asistente de configuración guiado (CP-C4, cierre del Pilar C).

Cualquier abogado — no solo el fundador — debe poder dejar a Mia completamente
conectada (perfil, motor de IA, Obsidian, carpetas de trabajo, guías, Telegram)
sin saber nada técnico. Este router expone el ESTADO del recorrido:

  · GET /api/setup/status — detecta qué hay en el equipo y qué falta, paso a paso,
    en lenguaje llano (§G). Es SOLO LECTURA: detectar jamás instala ni registra nada.
  · POST /api/setup/steps/{id}/skip · /unskip — cada paso es opcional y RETOMABLE;
    lo omitido se recuerda en tenant_settings.config['setup'].

Las ACCIONES de cada paso viven en sus endpoints propios, ya construidos y con sus
propias confirmaciones/allowlists (nada se ejecuta desde aquí): instalar Obsidian
(POST /api/obsidian/install, confirmación explícita), registrar carpetas
(POST /api/folders, allowlist), importar guías (POST /api/playbooks/import), motor
(PUT /settings/model-policy). Telegram es un paso GUIADO (docs/telegram-setup.md):
crear el bot exige acción humana.
"""
from __future__ import annotations

import asyncio
import logging
import shutil
import time

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Json

from ...channels import notify
from ...connectors import obsidian_install
from ...connectors.local_folders import detect_cloud_folders, list_sources
from ...connectors import vault_writer as vault_writer_mod
from ...db import pool
from ...onboarding.soul_interview import soul_status

router = APIRouter(prefix="/setup", tags=["setup"])
logger = logging.getLogger("mia.api.setup")

# Los pasos del recorrido, en orden. El id es estable (lo usa la UI y el skip).
STEP_IDS = ("perfil", "motor", "obsidian", "carpetas", "guias", "telegram")

# Caché de detecciones que tocan disco/subprocesos (revisor CP-C4, M2/M3):
# `winget list` puede tardar hasta 60s cuando Obsidian NO está instalado —
# exactamente el escenario del wizard — y sondear unidades de red caídas
# bloquea segundos. TTL corto: el estado del EQUIPO no cambia por segundo.
_DETECT_TTL_SECONDS = 60.0
_detect_cache: dict[str, tuple[float, object]] = {}


async def _detected(key: str, fn) -> object:
    """Corre un detector SÍNCRONO en un thread (no bloquea el event loop) y
    cachea su resultado por _DETECT_TTL_SECONDS."""
    now = time.monotonic()
    hit = _detect_cache.get(key)
    if hit is not None and (now - hit[0]) < _DETECT_TTL_SECONDS:
        return hit[1]
    value = await asyncio.to_thread(fn)
    _detect_cache[key] = (time.monotonic(), value)
    return value


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


async def _skipped(tenant_id: str) -> set[str]:
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT config->'setup'->'skipped' FROM tenant_settings "
            "WHERE tenant_id = %s::uuid",
            (tenant_id,),
        )).fetchone()
    value = row[0] if row else None
    return {str(s) for s in value} if isinstance(value, list) else set()


async def _write_skipped(tenant_id: str, skipped: set[str]) -> None:
    # jsonb_set NO crea rutas intermedias ('{setup,skipped}' sin 'setup' = no-op):
    # se construye el objeto anidado con merges (||), preservando otras claves de
    # config Y otras claves dentro de config['setup'].
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = COALESCE(tenant_settings.config, '{}'::jsonb) || "
            "  jsonb_build_object('setup', "
            "    COALESCE(tenant_settings.config->'setup', '{}'::jsonb) || "
            "    jsonb_build_object('skipped', %s::jsonb)), "
            "updated_at = now()",
            (tenant_id, Json({"setup": {"skipped": sorted(skipped)}}),
             Json(sorted(skipped))),
        )


async def _count_playbooks(tenant_id: str) -> int:
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT count(*) FROM playbooks WHERE status = 'active'"
        )).fetchone()
    return int(row[0]) if row else 0


@router.get("/status")
async def setup_status(request: Request):
    """El recorrido "Configura a Mia": qué está listo, qué falta y cuál es el
    siguiente paso — en lenguaje llano. SOLO LECTURA (detectar no ejecuta nada)."""
    return await collect_setup_status(_tenant(request))


async def collect_setup_status(tid: str) -> dict:
    """La lógica del status, reutilizable sin Request — la consume también el
    asistente (CP-B1) para guiar la configuración por chat."""
    skipped = await _skipped(tid)

    # Detecciones (todas fail-soft: un detector caído = "pendiente", nunca 500).
    # Las que tocan disco/subprocesos van en thread + caché (revisor CP-C4, M2/M3).
    soul = {}
    try:
        soul = (await _detected(f"soul:{tid}", lambda: soul_status(tid))) or {}
    except Exception:  # noqa: BLE001
        logger.exception("setup: no pude leer el estado del perfil (tenant=%s)", tid)
    try:
        obsidian_ok = bool(await _detected("obsidian", obsidian_install.is_installed))
    except Exception:  # noqa: BLE001
        obsidian_ok = False
    vault_path = None
    try:
        vault_path = await vault_writer_mod.get_tenant_vault_path(tid)
    except Exception:  # noqa: BLE001
        pass
    try:
        sources = [s for s in await list_sources(tid, include_disabled=False)]
    except Exception:  # noqa: BLE001
        sources = []
    detected = []
    if not sources:
        # Las nubes espejo solo se sondean cuando hacen falta (sin carpetas aún):
        # recorrer unidades A:–Z: con una unidad de red caída bloquea segundos.
        try:
            detected = list(await _detected("clouds", detect_cloud_folders) or [])
        except Exception:  # noqa: BLE001
            detected = []
    playbooks_n = 0
    try:
        playbooks_n = await _count_playbooks(tid)
    except Exception:  # noqa: BLE001
        pass
    claude_ok = bool(await _detected("which:claude", lambda: shutil.which("claude")))
    ollama_ok = bool(await _detected("which:ollama", lambda: shutil.which("ollama")))
    telegram_ok = notify.telegram_configured()

    def step(sid: str, titulo: str, listo: bool, detalle: str, accion: str,
             enlace: str | None = None) -> dict:
        estado = "listo" if listo else ("omitido" if sid in skipped else "pendiente")
        return {"id": sid, "titulo": titulo, "estado": estado, "detalle": detalle,
                "accion": accion, "enlace": enlace}

    steps = [
        step("perfil", "Tu perfil y la voz del despacho",
             bool(soul.get("completed")),
             "El perfil está completo." if soul.get("completed")
             else "Responde la entrevista inicial para que Mia hable con la voz de tu despacho.",
             "guiada", "/onboarding"),
        step("motor", "El motor de IA de Mia",
             claude_ok or ollama_ok,
             ("Detecté el motor de tu suscripción en este equipo."
              if claude_ok else
              "Detecté un motor local en este equipo."
              if ollama_ok else
              "No detecté un motor en este equipo. Puedes elegir la opción de nube en el Panel de control."),
             "automatica", "/dashboard"),
        step("obsidian", "Tu archivo de notas (Obsidian)",
             obsidian_ok and bool(vault_path),
             ("Obsidian está instalado y conectado con Mia."
              if obsidian_ok and vault_path else
              "Obsidian está instalado; falta conectar tu espacio de notas."
              if obsidian_ok else
              "Obsidian no está instalado. Mia puede instalarlo por ti (es gratis)."),
             "automatica", "/dashboard"),
        step("carpetas", "Tus carpetas de trabajo",
             len(sources) > 0,
             (f"Mia conoce {len(sources)} carpeta{'s' if len(sources) != 1 else ''} de trabajo."
              if sources else
              (f"Detecté {len(detected)} carpeta{'s' if len(detected) != 1 else ''} en la nube "
               "(OneDrive/Google Drive) lista(s) para conectar."
               if detected else
               "Registra las carpetas donde guardas tu trabajo para que Mia las conozca.")),
             "automatica", "/dashboard"),
        step("guias", "Las guías de trabajo del despacho",
             playbooks_n > 0,
             (f"Hay {playbooks_n} guía{'s' if playbooks_n != 1 else ''} cargada{'s' if playbooks_n != 1 else ''}."
              if playbooks_n else
              "Importa tus guías de trabajo (.md, .txt o Word) para que Mia siga tu método."),
             "automatica", "/memoria"),
        step("telegram", "Mia en tu celular (Telegram)",
             telegram_ok,
             ("El canal de Telegram está activo: Mia te escribe y te recuerda."
              if telegram_ok else
              "Crea tu bot privado (5 minutos, te doy la guía) para hablar con Mia desde el celular."),
             "guiada", None),
    ]

    hechos = sum(1 for s in steps if s["estado"] == "listo")
    siguiente = next((s for s in steps if s["estado"] == "pendiente"), None)
    return {
        "pasos": steps,
        "completados": hechos,
        "total": len(steps),
        "siguiente": siguiente["id"] if siguiente else None,
        "mensaje": (
            "Mia está completamente configurada. Todo listo."
            if hechos == len(steps) else
            f"Vas {hechos} de {len(steps)}. Siguiente: {siguiente['titulo'].lower()}."
            if siguiente else
            f"Vas {hechos} de {len(steps)}; el resto lo dejaste para después — retómalo cuando quieras."
        ),
    }


@router.post("/steps/{step_id}/skip")
async def setup_skip(step_id: str, request: Request):
    """Marca un paso como "para después" (retomable cuando el abogado quiera)."""
    tid = _tenant(request)
    if step_id not in STEP_IDS:
        raise HTTPException(status_code=404, detail="No conozco ese paso.")
    skipped = await _skipped(tid)
    skipped.add(step_id)
    await _write_skipped(tid, skipped)
    return {"status": "omitido", "paso": step_id}


@router.post("/steps/{step_id}/unskip")
async def setup_unskip(step_id: str, request: Request):
    """Retoma un paso que se había dejado para después."""
    tid = _tenant(request)
    if step_id not in STEP_IDS:
        raise HTTPException(status_code=404, detail="No conozco ese paso.")
    skipped = await _skipped(tid)
    skipped.discard(step_id)
    await _write_skipped(tid, skipped)
    return {"status": "pendiente", "paso": step_id}
