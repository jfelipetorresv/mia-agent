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
from ...connectors import vault_writer as vault_writer_mod
from ...connectors.local_folders import detect_cloud_folders, list_sources
from ...db import pool
from ...onboarding.soul_interview import soul_status
from ...speech import engine as speech_engine

router = APIRouter(prefix="/setup", tags=["setup"])
logger = logging.getLogger("mia.api.setup")

# Los pasos del recorrido, en orden. El id es estable (lo usa la UI y el skip).
# "voz" va al final: es una capacidad opcional (CP-Z1b) — el "siguiente paso"
# no debe anteponerla a carpetas o guías, que dan más valor al arrancar.
# Obsidian reincorporado al recorrido (2026-07-18): antes se excluía por un
# hallazgo de latencia (winget list ~60s cuando no está instalado, MN3). El
# fix real NO es el caché (con caché fría, la primera carga igual esperaba a
# winget): el status usa obsidian_install.is_installed_fast(), que SOLO mira
# rutas locales y NUNCA invoca winget. El criterio de "listo" sigue siendo el
# vault conectado (dato en DB).
STEP_IDS = ("perfil", "motor", "obsidian", "carpetas", "guias", "telegram", "voz")

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
            "Abre Configuración con «Ir al paso».",
            "En la sección «Conexiones», busca la tarjeta «Motor de IA» y elige la opción que prefieras.",
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
            "Abre Configuración y ubica la tarjeta «Tu espacio de notas», en la sección «Conexiones».",
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
            "Registra la carpeta desde Configuración, sección «Carpetas».",
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
    "voz": {
        "que_es": (
            "Un botón de micrófono junto al chat de tus casos: dictas con tu "
            "voz y Mia escribe el texto por ti."),
        "para_que": (
            "Dictar es más rápido que teclear, y tu voz NUNCA sale del servidor "
            "del despacho: la transcripción ocurre completa ahí, sin enviar el "
            "audio a ningún servicio externo."),
        "como": [
            "Abre Configuración con «Ir al paso» y ubica la tarjeta «Dictado por voz», en la sección «Conexiones».",
            "Pulsa «Instalar dictado por voz» y confirma: la descarga (~700 MB) tarda unos minutos y puedes seguir el avance ahí mismo.",
            "Cuando termine, verás el botón de micrófono junto al campo de texto de tus casos.",
            "Toca el micrófono, dicta, y vuelve a tocarlo para que Mia escriba lo que dijiste.",
        ],
    },
}

# CP-C4b · Qué hace cada sección de Mia — el mapa de la casa, en lenguaje llano.
# EL MANUAL DE MIA (punto 15 de la bitácora 2026-08-19). Era un acordeón plegado dentro de
# Configuración → «Primeros pasos», con tres frases por sección; el abogado que abre Mia por
# primera vez no encuentra ahí un manual y no sabía para qué servía cada pantalla. Ahora esta
# lista alimenta una pantalla propia (`/ayuda`), y por eso cada sección trae además:
#   · `ruta`      — a dónde lleva el botón, para no obligar a buscarla en el menú;
#   · `como`      — los pasos concretos, en el orden en que se hacen;
#   · `cuando`    — en qué momento del trabajo real sirve, que es lo que faltaba.
# Sin jerga (regla del proyecto): no aparece «HITL», «tenant» ni el nombre de un endpoint.
MIA_SECTIONS: list[dict] = [
    {"titulo": "Panel",
     "ruta": "/dashboard",
     "que_es": ("Lo accionable del día: sugerencias y borradores esperando tu decisión, "
                "recordatorios, recomendaciones de Mia y un resumen del mes."),
     "para_que": "Es lo primero que ves al entrar: qué necesita tu atención hoy.",
     "cuando": "Al empezar el día, y cada vez que quieras saber qué quedó pendiente.",
     "como": ["Mira «Para tu decisión»: ahí está lo que espera tu visto bueno.",
              "Abre cada tarjeta y decide; nada avanza mientras no decidas tú.",
              "Revisa los recordatorios y el gasto del mes antes de cerrar."]},
    {"titulo": "Casos",
     "ruta": "/casos",
     "que_es": "La pantalla principal: un espacio de trabajo por cada caso.",
     "para_que": ("Aquí subes el expediente, conectas carpetas y le preguntas a Mia. "
                  "En cada caso eliges si te entrega un borrador para aprobar o te "
                  "responde directo."),
     "cuando": "Siempre que trabajes un asunto concreto con su expediente.",
     "como": ["Crea el caso y ponle el nombre con el que tú lo llamas.",
              "Sube el expediente, o conecta la carpeta donde ya vive.",
              "Elige cómo quieres trabajarlo: borrador para aprobar, o respuesta directa.",
              "Pregúntale en tus palabras; Mia lee el expediente antes de responder."]},
    {"titulo": "Revisión de borradores",
     "ruta": "/casos",
     "que_es": "Donde apruebas, corriges o rechazas lo que Mia redacta.",
     "para_que": ("Nada sale del despacho sin tu visto bueno: revisas el borrador "
                  "y las citas que Mia marcó para verificar antes de aprobarlo."),
     "cuando": "Cada vez que Mia termina un borrador en un caso con aprobación.",
     "como": ["Lee el borrador y el diagnóstico que lo acompaña.",
              "Revisa las citas: Mia te dice cuáles respaldó y cuáles debes verificar tú.",
              "Mira los puntos que la revisión dejó abiertos antes de decidir.",
              "Aprueba, pide cambios con tus comentarios, o recházalo con el motivo."]},
    {"titulo": "Conocimiento",
     "ruta": "/memoria",
     "que_es": ("La memoria del despacho: tu perfil, tus guías de trabajo y lo "
                "que Mia va aprendiendo."),
     "para_que": ("Aquí importas guías, apruebas las sugerencias de mejora de Mia "
                  "y ves qué tan bien le va con cada procedimiento."),
     "cuando": "Cuando quieras enseñarle tu forma de trabajar, o revisar qué aprendió.",
     "como": ["Revisa tu perfil: es lo que Mia da por sabido de tu despacho.",
              "Importa o escribe una guía para un tipo de escrito que hagas seguido.",
              "Aprueba o descarta lo que Mia propone aprender; no aprende nada sola."]},
    {"titulo": "Agentes jurídicos",
     "ruta": "/personas",
     "que_es": "Ayudantes con un encargo propio, que tú defines y puedes llamar por su nombre.",
     "para_que": ("Cada uno tiene su especialidad y su forma de trabajar, para no repetirle "
                  "las mismas instrucciones a Mia en cada turno."),
     "cuando": "Cuando repites un tipo de encargo y quieres que salga siempre igual.",
     "como": ["Crea el ayudante y dile qué hace y cómo quieres que trabaje.",
              "Marca las capacidades que necesita para su tarea.",
              "Llámalo por su nombre desde cualquier conversación."]},
    {"titulo": "Configuración",
     "ruta": "/configurar",
     "que_es": ("El hogar de conexiones (Obsidian, correo, motor de IA), carpetas, "
                "automatizaciones, protección de datos y el cálculo de valor y gasto."),
     "para_que": ("Detecta qué está listo y qué falta, te explica cada pieza y te "
                  "lleva al lugar exacto donde se hace. Todo es opcional y "
                  "retomable."),
     "cuando": "Al empezar, y cada vez que quieras conectar algo nuevo.",
     "como": ["Mira el recorrido de primeros pasos: te dice qué falta y por qué importa.",
              "Conecta lo que uses: tus carpetas, tu correo, tu bóveda de notas.",
              "Revisa protección de datos y el tope de gasto antes de trabajar en serio."]},
    {"titulo": "Mia en tu celular (Telegram)",
     "ruta": "/configurar#conexiones",
     "que_es": "Ayuda en lenguaje normal desde el celular, una vez lo actives.",
     "para_que": ("Ejemplos: «recuérdame radicar mañana a las 9» o «¿cómo va mi "
                  "configuración?» — Mia responde por Telegram."),
     "cuando": "Cuando estés fuera de la oficina y necesites consultarle algo.",
     "como": ["Crea tu bot privado con la guía paso a paso de Configuración.",
              "Pega el código que te da Telegram y listo.",
              "Escríbele como a cualquier contacto: te responde y te recuerda."]},
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


@router.get("/manual")
async def setup_manual(request: Request):
    """El manual de Mia: qué es cada sección, cuándo sirve y cómo se usa.

    Sale del mismo `MIA_SECTIONS` que ya viajaba dentro de `/setup/status`: una sola fuente,
    para que la pantalla de ayuda y el recorrido de configuración nunca digan cosas
    distintas de la misma pantalla. Es contenido fijo — no consulta nada del despacho — pero
    va tras la sesión como el resto del API.
    """
    _tenant(request)
    return {"secciones": MIA_SECTIONS}


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
    obsidian_installed = False
    vault_path = None
    try:
        # RÁPIDA a propósito (sin winget, MN3): este status se sirve en caliente a
        # una petición HTTP y no puede pagar el fallback de ~60s de winget list.
        # is_installed() completa (con winget) sigue viva para folders.py y para
        # el propio install() — aquí NUNCA se invoca.
        obsidian_installed = bool(await _detected(
            "obsidian:installed", obsidian_install.is_installed_fast))
    except Exception:  # noqa: BLE001
        logger.exception("setup: no pude detectar Obsidian (tenant=%s)", tid)
    try:
        vault_path = await vault_writer_mod.get_tenant_vault_path(tid)
    except Exception:  # noqa: BLE001
        logger.exception("setup: no pude leer el vault configurado (tenant=%s)", tid)
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
    try:
        # available() toca disco (stat de los pesos) → thread + caché 60 s. Tras
        # instalar desde el Panel, este paso puede tardar ≤60 s en verse "listo".
        voz_ok = bool(await _detected(
            "speech", lambda: speech_engine.get_engine().available()[0]))
    except Exception:  # noqa: BLE001
        voz_ok = False

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
              "No detecté un motor en este equipo. Puedes elegir la opción de nube en el menú Configuración."),
             "automatica", "/configurar#conexiones"),
        # Obsidian reincorporado al recorrido (2026-07-18): el criterio de listo
        # es el vault conectado (dato en DB); "instalado" se detecta con
        # is_installed_fast() (sin winget, MN3) — nunca invoca el subproceso.
        step("obsidian", "Tu espacio de notas (Obsidian)",
             bool(vault_path),
             ("Tu espacio de notas ya está conectado con Mia."
              if vault_path else
              "Obsidian está instalado; conecta tu espacio de notas desde el menú Configuración."
              if obsidian_installed else
              "Instala Obsidian (gratuito) y conecta tu espacio de notas desde el menú Configuración."),
             "guiada", "/configurar#conexiones"),
        step("carpetas", "Tus carpetas de trabajo",
             len(sources) > 0,
             (f"Mia conoce {len(sources)} carpeta{'s' if len(sources) != 1 else ''} de trabajo."
              if sources else
              (f"Detecté {len(detected)} carpeta{'s' if len(detected) != 1 else ''} en la nube "
               "(OneDrive/Google Drive) lista(s) para conectar."
               if detected else
               "Registra las carpetas donde guardas tu trabajo para que Mia las conozca.")),
             "automatica", "/configurar#carpetas"),
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
        step("voz", "Dictado por voz",
             voz_ok,
             ("El dictado por voz está instalado: busca el micrófono junto al chat de tus asuntos."
              if voz_ok else
              "Instala el dictado por voz desde el menú Configuración para dictar en vez de teclear."),
             "automatica", "/configurar#conexiones"),
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
