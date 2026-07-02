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

# ── CP-C4b · La guía explicativa de cada paso (encargo de Pipe 2026-07-02) ────
# El recorrido no solo DETECTA: EXPLICA como un onboarding — qué es cada
# herramienta, para qué le sirve al despacho y cómo se implementa paso a paso,
# en lenguaje de negocio (§G). FUENTE ÚNICA: la consume la página /configurar y
# también el asistente por chat (assistant/core._setup_block).
STEP_GUIDES: dict[str, dict] = {
    "perfil": {
        "que_es": (
            "Una entrevista corta donde Mia aprende quién eres: tu despacho, tu "
            "jurisdicción, tus áreas de práctica, tu forma de escribir y las "
            "reglas de la casa."),
        "para_que": (
            "Todo lo que Mia analice y redacte saldrá con la voz de TU despacho, "
            "no con una voz genérica. Es la diferencia entre un asistente "
            "cualquiera y uno que trabaja como los tuyos."),
        "como": [
            "Pulsa «Ir al paso» (si es tu primera vez, Mia te lleva sola al entrar).",
            "Responde las preguntas de corrido; cada una trae un ejemplo. Ten a mano los datos: si cierras la pestaña antes de terminar, se empiezan de nuevo.",
            "Al final Mia te muestra lo que entendió de tu despacho para que lo revises y edites antes de guardarlo.",
            "Después puedes volver a ajustar tu perfil en la pantalla Conocimiento, pestaña «Mi despacho».",
        ],
    },
    "motor": {
        "que_es": (
            "El «cerebro» con el que Mia razona. Hay tres opciones: usar tu "
            "suscripción existente (recomendado), un servicio en la nube que se "
            "paga por uso, o un motor que corre completo en tu equipo."),
        "para_que": (
            "Define calidad, costo y privacidad para tu despacho: con tu "
            "suscripción aprovechas lo que ya pagas; con «todo en mi equipo» "
            "ningún dato del despacho sale de tu computador (a cambio es más "
            "lento y menos preciso)."),
        "como": [
            "Abre el Panel de control con «Ir al paso».",
            "Busca la sección «Motor de IA» y elige la opción que prefieras.",
            "Con solo elegirla queda aplicada al instante; puedes cambiarla cuando quieras.",
            "Si no detecto ningún motor en tu equipo, la opción de nube funciona sin instalar nada.",
        ],
    },
    "obsidian": {
        "que_es": (
            "Obsidian es una aplicación gratuita de notas. Mia la usa como su "
            "«cuaderno visible»: lo que aprende de tu despacho queda escrito ahí "
            "como notas normales que puedes abrir, leer y editar."),
        "para_que": (
            "Transparencia total: ves lo que Mia sabe y aprende (conceptos, "
            "reportes semanales) como si fueran notas tuyas. Mia escribe SOLO en "
            "su propia carpeta y jamás toca tus notas."),
        "como": [
            "Si aún no tienes Obsidian, su instalación es gratuita desde el sitio obsidian.md (o pídeme que lo instale por ti por Telegram, con tu confirmación).",
            "Abre el Panel de control con «Ir al paso» y ubica la tarjeta «Obsidian».",
            "Escribe ahí la ruta de tu espacio de notas de Obsidian y pulsa «Sincronizar».",
            "Desde ese momento, las notas de Mia aparecerán bajo la carpeta «Mia/» dentro de tu espacio.",
        ],
    },
    "carpetas": {
        "que_es": (
            "El permiso explícito que le das a Mia para leer las carpetas donde "
            "guardas tu trabajo — en el disco, OneDrive o Google Drive."),
        "para_que": (
            "Mia conoce los modelos, plantillas y documentos de referencia del "
            "despacho para trabajar con TU material. Solo lee lo que autorices; "
            "nunca entra a carpetas del sistema ni a nada fuera de tu lista."),
        "como": [
            "Ten a la mano la ruta de la carpeta donde guardas tu trabajo (por ejemplo, tu carpeta de OneDrive o de Google Drive en el equipo).",
            "Registra la carpeta desde el Panel de control (la administración de carpetas se está incorporando a esa pantalla).",
            "Mia lee y organiza su contenido para tenerlo presente al trabajar, solo de las carpetas que autorices.",
            "Puedes quitar una carpeta cuando quieras y Mia deja de verla al instante.",
        ],
    },
    "guias": {
        "que_es": (
            "Tus manuales, instructivos y formatos de trabajo: cómo contesta "
            "demandas tu despacho, qué revisa antes de radicar, qué cláusulas usa."),
        "para_que": (
            "Mia sigue TU método, no uno inventado: al redactar aplica los "
            "procedimientos del despacho y te dice cuáles usó. Además aprende de "
            "tus correcciones y te propone mejoras que tú apruebas o rechazas."),
        "como": [
            "Abre la pantalla Conocimiento con «Ir al paso».",
            "Usa «Importar guías» y sube tus documentos (.md, .txt o Word).",
            "Mia los divide en procedimientos y te muestra el detalle de lo que importó y lo que omitió.",
            "Revisa la lista de procedimientos: cada uno queda disponible para que Mia lo use al redactar.",
        ],
    },
    "telegram": {
        "que_es": (
            "Un canal privado para hablar con Mia desde el celular, con un bot "
            "que es TUYO — nadie más puede escribirle ni leerlo."),
        "para_que": (
            "Recordatorios a la hora pactada, aviso cuando un borrador queda "
            "esperando tu revisión y el reporte semanal del despacho — sin abrir "
            "el computador."),
        "como": [
            "En Telegram, busca @BotFather y envíale /newbot.",
            "Ponle nombre a tu bot y copia la clave que te entrega.",
            "Entrégale esa clave a tu administrador: con la guía de instalación la deja lista en un minuto.",
            "Abre Telegram en tu celular y escríbele a tu bot: quedará enlazado solo contigo.",
        ],
    },
}

# CP-C4b · Qué hace cada sección de Mia — el mapa de la casa, en lenguaje llano.
MIA_SECTIONS: list[dict] = [
    {"titulo": "Asuntos",
     "que_es": "La pantalla principal: un espacio de trabajo por cada caso.",
     "para_que": ("Aquí subes el expediente, le preguntas a Mia y recibes el "
                  "diagnóstico y el borrador para tu aprobación.")},
    {"titulo": "Revisión de borradores",
     "que_es": "Donde apruebas, corriges o rechazas lo que Mia redacta.",
     "para_que": ("Nada sale del despacho sin tu visto bueno: revisas el borrador "
                  "y las citas que Mia marcó para verificar antes de aprobarlo.")},
    {"titulo": "Conocimiento",
     "que_es": ("La memoria del despacho: tu perfil, tus guías de trabajo y lo "
                "que Mia va aprendiendo."),
     "para_que": ("Aquí importas guías, apruebas las sugerencias de mejora de Mia "
                  "y ves qué tan bien le va con cada procedimiento.")},
    {"titulo": "Panel de control",
     "que_es": ("El tablero general: motor de IA, conexiones (Obsidian, carpetas, "
                "Telegram), recordatorios, actividad y costo del mes."),
     "para_que": "Es donde se hacen casi todos los pasos de esta configuración."},
    {"titulo": "Configura a Mia",
     "que_es": "Este recorrido.",
     "para_que": ("Detecta qué está listo y qué falta, te explica cada pieza y te "
                  "lleva al lugar exacto donde se hace. Todo es opcional y "
                  "retomable.")},
    {"titulo": "Mia en tu celular (Telegram)",
     "que_es": "Ayuda en lenguaje normal desde el celular, una vez lo actives.",
     "para_que": ("Ejemplos: «recuérdame radicar mañana a las 9» o «¿cómo va mi "
                  "configuración?» — Mia responde por Telegram.")},
]

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
                "accion": accion, "enlace": enlace,
                # CP-C4b: la guía explicativa viaja con el paso (qué es, para qué
                # sirve al despacho y cómo se implementa) — la pinta la página y
                # la usa el asistente por chat.
                "guia": STEP_GUIDES.get(sid)}

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
        "secciones": MIA_SECTIONS,  # CP-C4b: el mapa de las secciones de Mia
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
