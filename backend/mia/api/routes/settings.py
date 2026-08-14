"""Mia · api.routes.settings — ajustes del Agent Hub por tenant (1e · PASO 3).

GET  /settings/agents                  → estado de cada conector para el tenant
POST /settings/agents/{agent_id}/enable
POST /settings/agents/{agent_id}/disable
GET  /settings/model-policy            → política de modelo efectiva + opciones (CP2)
PUT  /settings/model-policy            → valida y persiste la política del tenant (CP2)
GET  /settings/eval-consent            → ¿el despacho autorizó usar asuntos reales en calidad?
PUT  /settings/eval-consent            → concede o revoca esa autorización (Banco de oro)

§G: el abogado ve solo nombres en español ("Asistente de investigación jurídica",
"Editor de documentos"…) y un id neutro (slug); NUNCA la marca del CLI. El estado
persiste por tenant en `tenant_settings` bajo RLS (decisión #12).
"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Json

from ...agent import llm
from ...db import pool
from ...eval.harness import read_eval_policy
from ...gateway import hub_config, hub_gate
from ...gateway.agent_hub import CONNECTORS, AgentHub, slug_to_key
from ..middleware import invalidate_policy_cache

router = APIRouter(tags=["settings"])
_hub = AgentHub()

# §G: etiquetas SIN jerga técnica — el abogado nunca ve "CLI", "API" ni "Ollama".
_POLICY_LABELS: dict[str, str] = {
    "quality_adaptive": "Calidad adaptativa (recomendado)",
    "suscripcion": "Mi suscripción (configuración directa)",
    "nube": "Nube",
    "soberano": "Todo en mi equipo",
    "openrouter": "Tu cuenta de OpenRouter",
}


def _tenant(request: Request) -> str:
    t = getattr(request.state, "tenant_id", None)
    if not t:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    return t


@router.get("/settings/agents")
async def list_agents(request: Request):
    """Lista los conectores con su estado para el tenant. Solo español, sin marcas.

    `bloqueado_por_politica` refleja el candado de `gateway/hub_gate.py`: con 'soberano'
    NO se delega aunque el ayudante esté habilitado (el toggle no es una excepción a la
    política, es una opción DENTRO de ella). La UI lo necesita para no prometer una
    delegación que el gate va a bloquear — mismo criterio que `notebooklm_disponible`.
    `aviso_consentimiento` viaja con la lista para que el opt-in sea INFORMADO: el texto
    lo redacta el gate (fuente única) y la UI lo muestra literal, sin reescribirlo.
    """
    tenant_id = _tenant(request)
    available = _hub.list_available()
    enabled_map = await hub_config.get_hub_config(tenant_id)
    policy = await llm.model_policy_for(tenant_id)
    agentes = [
        {
            "id": info["slug"],                 # id público neutro (sin marca)
            "nombre": info["display_name"],     # español (§G)
            "instalado": info["installed"],
            "habilitado": bool(enabled_map.get(key, False)),
        }
        for key, info in available.items()
    ]
    return {
        "agentes": agentes,
        "bloqueado_por_politica": policy == "soberano",
        "aviso_consentimiento": hub_gate.CONSENT_NOTICE,
        # CP-HUB2: cuánta iniciativa tiene Mia con estos ayudantes. Viaja con la lista
        # porque es la misma decisión del abogado ("¿quién manda aquí?") y verla junto a
        # los interruptores es lo que la vuelve comprensible.
        "modo": await hub_config.get_delegation_mode(tenant_id),
        "modos": _delegation_mode_options(),
    }


# ── CP-HUB2 · cuánta iniciativa tiene Mia con los ayudantes externos ────────────
# §G: el abogado elige en su idioma, no en el de la máquina. Las etiquetas describen QUIÉN
# DECIDE, que es lo que él está eligiendo — no el mecanismo.
_DELEGATION_MODE_LABELS: dict[str, str] = {
    hub_config.MODE_ASK: "Mia propone y yo apruebo (recomendado)",
    hub_config.MODE_AUTO: "Mia decide sola",
    hub_config.MODE_ONLY_EXPLICIT: "Solo cuando yo se lo pida",
}

_DELEGATION_MODE_HINTS: dict[str, str] = {
    hub_config.MODE_ASK: (
        "Cuando Mia crea que un ayudante te ahorra trabajo, te muestra cuál y el texto "
        "exacto que saldría de este computador. No sale nada hasta que apruebes."
    ),
    hub_config.MODE_AUTO: (
        "Mia le pide ayuda a un asistente externo sin consultarte. Te avisa en el mismo "
        "turno de que tu texto salió del computador, pero cuando ya salió."
    ),
    hub_config.MODE_ONLY_EXPLICIT: (
        "Mia nunca toma la iniciativa. Solo usa un ayudante si lo nombras en tu mensaje."
    ),
}


def _delegation_mode_options() -> list[dict]:
    return [{"id": k, "nombre": v, "explicacion": _DELEGATION_MODE_HINTS[k]}
            for k, v in _DELEGATION_MODE_LABELS.items()]


@router.get("/settings/delegation-mode")
async def get_delegation_mode(request: Request):
    """Modo de iniciativa vigente + las 3 opciones (español, sin jerga)."""
    tenant_id = _tenant(request)
    return {"modo": await hub_config.get_delegation_mode(tenant_id),
            "modos": _delegation_mode_options()}


@router.put("/settings/delegation-mode")
async def put_delegation_mode(request: Request, body: dict[str, Any]):
    """Fija el modo. 422 si no es uno de los tres (nunca se persiste un modo inventado).

    OJO: esto NO decide si se puede delegar — eso es la política de modelo ('Todo en mi
    equipo' sigue bloqueando todo) y el interruptor de cada ayudante. Esto decide solo
    QUIÉN TOMA LA INICIATIVA dentro de lo que ya está permitido."""
    tenant_id = _tenant(request)
    modo = (body or {}).get("modo")
    if modo not in hub_config.VALID_DELEGATION_MODES:
        raise HTTPException(
            status_code=422,
            detail="Elige una de las opciones disponibles para decidir quién toma la "
                   "iniciativa con los asistentes externos.")
    await hub_config.set_delegation_mode(tenant_id, modo)
    return {"modo": modo, "nombre": _DELEGATION_MODE_LABELS[modo],
            "modos": _delegation_mode_options()}


async def _set(request: Request, agent_id: str, enabled: bool):
    tenant_id = _tenant(request)
    key = slug_to_key(agent_id) or (agent_id if agent_id in CONNECTORS else None)
    if key is None:
        raise HTTPException(status_code=404, detail="Asistente no encontrado")
    await hub_config.set_enabled(tenant_id, key, enabled)
    c = CONNECTORS[key]
    return {"id": c.slug, "nombre": c.display_name, "habilitado": enabled}


@router.post("/settings/agents/{agent_id}/enable")
async def enable_agent(agent_id: str, request: Request):
    return await _set(request, agent_id, True)


@router.post("/settings/agents/{agent_id}/disable")
async def disable_agent(agent_id: str, request: Request):
    return await _set(request, agent_id, False)


# ── CP2 · política de modelo por tenant (decisión #27) ──────────────────────────
def _policy_options() -> list[dict]:
    return [{"id": k, "nombre": v} for k, v in _POLICY_LABELS.items()]


def _model_capabilities() -> dict[str, Any]:
    """Capacidades comprobables de la instalación, sin prometer planes ni modelos ajenos.

    El resultado se entrega a la UI junto con la política: una recomendación solo es honesta si
    Mia puede comprobar que el ejecutable existe. La disponibilidad concreta de un plan/modelo
    sigue siendo responsabilidad del CLI en cada llamada y se refleja en la cadena de fallback.
    """
    from ...agent import subscription_llm

    claude_ready = subscription_llm.is_available()
    return {
        "claude_code": {
            "installed": claude_ready,
            "recommended_for": "análisis jurídico complejo",
            "recommendation_basis": "se valida con las pruebas de calidad de Mia",
            "max_is_exceptional": True,
            "available_efforts": subscription_llm.supported_efforts(),
        },
        "codex": {
            "installed": bool(_hub.list_available().get("codex", {}).get("installed")),
            "role": "verificación independiente o respaldo",
        },
    }


@router.get("/settings/model-policy")
async def get_model_policy(request: Request):
    """Política efectiva del tenant + las 3 opciones (etiquetas en español, sin jerga).

    CP-NLM: incluye el estado de la consulta a NotebookLM (opt-in + notebook elegido) para
    que la UI de Conexiones pinte el toggle. `notebooklm_disponible` es True solo si la
    política NO es 'soberano' (en soberano la consulta está bloqueada de raíz)."""
    tenant_id = _tenant(request)
    policy = await llm.model_policy_for(tenant_id)
    from ...connectors import notebooklm  # import diferido (evita ciclos al cargar rutas)
    return {
        "politica": policy,
        "nombre": _POLICY_LABELS[policy],
        "opciones": _policy_options(),
        "allow_notebooklm": await llm.notebooklm_allowed_for(tenant_id),
        "notebooklm_notebook": await notebooklm.configured_notebook(tenant_id) or "",
        "notebooklm_disponible": policy != "soberano",
        "capabilities": _model_capabilities(),
    }


# ── Autorización para usar asuntos reales en las pruebas de calidad ────────────
# La LEE `eval/harness.py::read_eval_policy` desde `config['eval']['allow_eval_real_data']`
# (default False, fail-closed) y la exige el Banco de oro (`gold_cases.py::_consent_guard`)
# y el examen de calidad. Hasta ahora SOLO se leía: sin este par GET/PUT el abogado veía un
# 403 que lo mandaba "a Configuración" donde no había nada que tocar.
#
# §G: al abogado se le habla de "usar asuntos reales en las pruebas de calidad", nunca de
# 'eval', 'gold set' ni 'allow_eval_real_data'.
@router.get("/settings/eval-consent")
async def get_eval_consent(request: Request):
    """¿El despacho autorizó que sus asuntos reales se usen en las pruebas de calidad?

    Fail-closed: `read_eval_policy` devuelve False si no hay fila en `tenant_settings`, si no
    existe la clave, o si la lectura falla. Ausencia = NO permitido, nunca lo contrario."""
    tenant_id = _tenant(request)
    return {"permitido": (await read_eval_policy(tenant_id))["allow_real_data"]}


@router.put("/settings/eval-consent")
async def put_eval_consent(request: Request):
    """Concede (true) o revoca (false) esa autorización.

    MERGE jsonb ANIDADO y atómico, sin read-modify-write (mismo criterio que
    `put_model_policy`): el `||` de arriba conserva TODAS las demás claves del config
    ('model_policy', 'allow_openrouter', 'notebooklm_notebook'…) y el `||` de adentro conserva
    las demás claves de 'eval'. Un `config || {"eval": {...}}` a secas NO servía: reemplazaría
    el objeto 'eval' entero y borraría cualquier otro ajuste de eval.

    QUÉ IMPLICA REVOCAR (permitido=false):
      - A futuro: vuelve el 403 al intentar guardar un caso de oro desde un asunto REAL
        (`gold_cases.py::_consent_guard`) y el examen deja de correr casos no sintéticos
        (`eval/harness.py`). Aplica de inmediato: la política se lee de la DB en cada
        llamada, no se cachea (el `_policy_cache` del middleware solo guarda 'model_policy'
        y 'allow_openrouter'; por eso aquí NO hay que invalidar nada).
      - Hacia atrás: NO borra ni oculta los casos de oro ya guardados. Son texto ANONIMIZADO
        (a la DB nunca llegó el mapa marcador→valor real, solo su hash), así que ya no son
        datos reales del cliente y siguen siendo el examen de no-regresión del despacho.
        Revocar cierra la CAPTURA de asuntos reales, que es lo que toca datos identificables;
        no destruye el trabajo de revisión que el abogado ya confirmó. Para retirar un caso
        concreto existe `DELETE /api/gold-cases/{id}`.
    """
    tenant_id = _tenant(request)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — cuerpo no-JSON → 422 uniforme
        body = None
    permitido = (body or {}).get("permitido") if isinstance(body, dict) else None
    if not isinstance(permitido, bool):
        raise HTTPException(
            status_code=422,
            detail="Indica si autorizas o no: 'permitido' debe ser verdadero o falso.",
        )
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) "
            "VALUES (%s::uuid, jsonb_build_object('eval', %s::jsonb)) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = COALESCE(tenant_settings.config, '{}'::jsonb) "
            "         || jsonb_build_object('eval', "
            "              COALESCE(tenant_settings.config->'eval', '{}'::jsonb) "
            "              || (EXCLUDED.config->'eval')), "
            "updated_at = now()",
            (tenant_id, Json({"allow_eval_real_data": permitido})),
        )
    # Se releé de la DB (no se devuelve el valor de entrada): lo que responde es lo que el
    # candado va a ver, no lo que el cliente pidió.
    return {"permitido": (await read_eval_policy(tenant_id))["allow_real_data"]}


@router.put("/settings/model-policy")
async def put_model_policy(request: Request):
    """Valida y persiste la política en tenant_settings.config['model_policy'] con un
    MERGE jsonb atómico (config || {"model_policy": …}): solo toca esa clave, sin
    read-modify-write que pise cambios concurrentes de otros settings (revisión CP2).
    Invalida el caché del middleware: aplica de inmediato.

    CP-S3 (opt-in de confidencialidad): el body puede traer opcionalmente
    `allow_openrouter` (bool). Si viene no-nulo, se incluye en el MISMO merge jsonb
    atómico junto a `model_policy` — una sola escritura, sin pisar otras claves del
    config. Sin el campo (o null), el comportamiento es idéntico al de antes
    (retrocompatible): solo se toca 'model_policy'."""
    tenant_id = _tenant(request)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001 — cuerpo no-JSON → 422 uniforme
        body = None
    raw = (body or {}).get("politica") if isinstance(body, dict) else None
    policy = str(raw or "").strip().lower()
    if policy not in _POLICY_LABELS:
        raise HTTPException(
            status_code=422,
            detail=("Opción no válida. Usa 'quality_adaptive', 'suscripcion', 'nube', "
                    "'soberano' u 'openrouter'."),
        )
    allow_or_raw = (body or {}).get("allow_openrouter") if isinstance(body, dict) else None
    merge: dict[str, Any] = {"model_policy": policy}
    if allow_or_raw is not None:
        if not isinstance(allow_or_raw, bool):
            raise HTTPException(
                status_code=422,
                detail="allow_openrouter debe ser verdadero o falso.",
            )
        merge["allow_openrouter"] = allow_or_raw
    # CP-NLM: opt-in de consulta a NotebookLM + notebook elegido, en el MISMO merge jsonb
    # atómico (una sola escritura, sin pisar otras claves del config). Ambos opcionales.
    allow_nlm_raw = (body or {}).get("allow_notebooklm") if isinstance(body, dict) else None
    if allow_nlm_raw is not None:
        if not isinstance(allow_nlm_raw, bool):
            raise HTTPException(
                status_code=422,
                detail="allow_notebooklm debe ser verdadero o falso.",
            )
        merge["allow_notebooklm"] = allow_nlm_raw
    nlm_notebook_raw = (body or {}).get("notebooklm_notebook") if isinstance(body, dict) else None
    if nlm_notebook_raw is not None:
        if not isinstance(nlm_notebook_raw, str):
            raise HTTPException(
                status_code=422,
                detail="notebooklm_notebook debe ser un texto (id del notebook).",
            )
        merge["notebooklm_notebook"] = nlm_notebook_raw.strip()
    async with pool.tenant_connection(tenant_id) as conn:
        # Upsert con merge jsonb: `config || {claves nuevas}` en el propio UPDATE —
        # atómico, last-write-wins SOLO sobre las claves de `merge`, el resto del
        # config queda intacto.
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = COALESCE(tenant_settings.config, '{}'::jsonb) || EXCLUDED.config, "
            "updated_at = now()",
            (tenant_id, Json(merge)),
        )
    invalidate_policy_cache(tenant_id)
    # Devuelve la MISMA forma enriquecida que el GET para que la UI (motor + NotebookLM)
    # quede consistente tras cualquier PUT sin re-consultar (CP-NLM).
    from ...connectors import notebooklm  # import diferido (evita ciclos al cargar rutas)
    return {
        "politica": policy,
        "nombre": _POLICY_LABELS[policy],
        "opciones": _policy_options(),
        "allow_notebooklm": await llm.notebooklm_allowed_for(tenant_id),
        "notebooklm_notebook": await notebooklm.configured_notebook(tenant_id) or "",
        "notebooklm_disponible": policy != "soberano",
        "capabilities": _model_capabilities(),
    }
