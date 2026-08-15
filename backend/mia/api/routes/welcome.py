"""Mia · api.routes.welcome — bienvenida + activación de llaves (F3, sesión 44).

La primera vez que un abogado abre Mia necesita, en este orden: saber si ya
hay un despacho creado en este equipo (para ir a "crear despacho" o a
"iniciar sesión"), y — tras iniciar sesión — activar el mínimo de llaves para
que la búsqueda en sus documentos funcione. Este router expone:

  · GET  /api/welcome/status      — foto del estado (público, ver nota de
    seguridad más abajo).
  · POST /api/welcome/keys        — guarda llaves GLOBALES de la instalación
    en el `.env` (AUTENTICADO).
  · POST /api/welcome/keys/test   — ping mínimo de una llave SIN guardarla
    (AUTENTICADO).

── Modelo de confianza (decisión de seguridad, sesión 44) ──────────────────
Estas llaves (búsqueda documental / respaldo del motor / proveedor en la
nube) son GLOBALES de la INSTALACIÓN — viven en el `.env` de `config.
PROJECT_ROOT`, no por despacho (a diferencia de `tenant_settings`). Mia es
mono-despacho por instalación (un abogado o despacho por equipo/instancia):
el modelo de confianza asumido es que CUALQUIER usuario ya autenticado de
ESTE despacho puede configurar la instancia completa — no hay un rol
"administrador" separado hoy. Por eso basta con exigir sesión (Bearer válido,
lo hace `TenantContextMiddleware`) para `/keys` y `/keys/test`; no se agrega
un chequeo de rol adicional. Si Mia deja de ser mono-despacho (varios
despachos independientes por instalación), este endpoint necesitará un rol
"admin de instalación" — anotado aquí para la próxima auditoría.

La escritura se permite tanto en modo instalado como en modo desarrollo:
`config.PROJECT_ROOT` ya resuelve al lugar correcto en ambos casos (carpeta
de datos del usuario si `sys.frozen`/`MIA_APP_DIR`, o la raíz del repo en
dev — ver `config.py`). No se distingue el modo porque el mismo criterio de
confianza (sesión del despacho) aplica igual en un repo de desarrollo de un
solo desarrollador que en la instalación de un abogado real.

── /welcome/status: qué es público y por qué ───────────────────────────────
Es un OPEN_PATH (sin Bearer) porque el frontend lo necesita ANTES de que
exista sesión, para decidir "crear despacho" vs "iniciar sesión". Los campos
que devuelve siempre, con o sin sesión, son deliberadamente NO sensibles:
  - `instalado`, `hay_usuario`: si ya existe algún despacho en este equipo
    (cuenta tenants — no distingue CUÁL despacho, ni sus datos).
  - `faltan_llaves`: si el `.env` de la instalación tiene o no la clave de
    búsqueda/respaldo puesta — un booleano, nunca el valor de la clave.
  - `motor_detectado`: si el equipo detecta Claude Code, Codex o un motor local
    (`shutil.which`) — dato del EQUIPO, no del despacho. Es detección, no promesa
    de sesión autenticada; esa validación ocurre antes de la primera inferencia.
Los campos que SÍ dependen del despacho concreto (`onboarding_completo`,
`politica` real de un tenant) solo se calculan si la request YA trae un JWT
válido (el middleware ya fijó `request.state.tenant_id`); sin sesión se
devuelven valores por defecto seguros (`onboarding_completo=False`, la
política default de la instalación) que no revelan nada del despacho.
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import sys

import jwt
from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool
from typing import Literal

from ... import config
from ...agent import codex_subscription_llm, llm
from ...db import pool
from ...onboarding.soul_interview import soul_status
from ...setup.env_writer import read_env_values, upsert_env_keys

router = APIRouter(prefix="/welcome", tags=["welcome"])
logger = logging.getLogger("mia.api.welcome")

# Mapea el nombre en llano del body a la variable real del .env (§G: el abogado
# nunca ve estos nombres; solo viajan entre el frontend y este backend).
_ENV_KEY_MAP = {
    "busqueda": "VOYAGE_API_KEY",
    "respaldo": "ANTHROPIC_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
}

# Saneo de la clave: rechaza saltos de línea (romperían el .env, una línea por
# variable) y cualquier "=" (evita que una clave pegada mal inyecte "OTRA_VAR=x"
# en la misma línea). El resto del charset cubre los formatos reales de
# proveedor (prefijos con guiones/puntos/dos puntos/slash, p. ej. claves con
# guion bajo o con ':' de algunos proveedores en la nube).
_CLAVE_RE = re.compile(r"^[A-Za-z0-9_.:\-/+]+$")
_CLAVE_MIN = 10
_CLAVE_MAX = 300  # tope LÓGICO: se valida en llano (§G) dentro de _clave_invalida.
# Tope de Pydantic MUY por encima del lógico: si dejáramos max_length=_CLAVE_MAX,
# una clave larguísima dispararía el 422 técnico en inglés de Pydantic ANTES de
# nuestra validación, y el abogado vería jerga. Con el techo alto, el chequeo de
# longitud cae en _clave_invalida y sale un mensaje en español llano. Sigue
# habiendo un techo (para no aceptar payloads absurdos), solo que más arriba.
_CLAVE_MAX_FIELD = 4096


def _clave_invalida(valor: str) -> str | None:
    """None si `valor` tiene forma razonable de clave; si no, el motivo (en
    llano, sin tecnicismos) para mostrarle al abogado."""
    if "\n" in valor or "\r" in valor:
        return "Esa clave trae un salto de línea; cópiala de nuevo sin dejar espacios extra."
    if valor != valor.strip():
        return "Esa clave trae espacios de más al inicio o al final; revísala."
    if len(valor) < _CLAVE_MIN or len(valor) > _CLAVE_MAX:
        return "Esa clave no tiene el largo que esperaba; revisa que la copiaste completa."
    if not _CLAVE_RE.match(valor):
        return "Esa clave tiene caracteres que no reconozco; cópiala de nuevo desde el origen."
    return None


def _instalado() -> bool:
    """MIA_APP_DIR presente (la cáscara ya ancló una instancia) O producción
    O el binario empaquetado (PyInstaller) — mismo criterio de config.py."""
    return (
        bool(os.getenv("MIA_APP_DIR", "").strip())
        or config.IS_PRODUCTION
        or bool(getattr(sys, "frozen", False))
    )


async def _hay_usuario() -> bool:
    """True si YA existe algún despacho en este equipo. `tenants` tiene RLS
    FORCE (id = app_current_tenant()): mia_app SIN contexto de tenant ve 0 filas
    (fail-closed), así que un SELECT normal nunca podría responder esto. Se usa
    la función SECURITY DEFINER `mia_any_tenant_exists` (migración 031, mismo
    patrón que `auth_user_by_email`): devuelve SOLO un booleano de EXISTENCIA,
    ningún dato de ningún despacho."""
    async with pool.connection() as conn:
        row = await (await conn.execute("SELECT mia_any_tenant_exists()")).fetchone()
    return bool(row and row[0])


def _optional_tenant(request: Request) -> str | None:
    """tenant_id del Bearer si viene y es válido, si no None (anónimo).

    `/api/welcome/status` es OPEN_PATH: el middleware devuelve la request ANTES
    de decodificar el JWT, así que `request.state.tenant_id` siempre llega None
    aquí. Para poder ENRIQUECER la respuesta cuando SÍ hay sesión (post-login)
    sin dejar de ser público (pre-login), decodificamos el token nosotros mismos,
    con el mismo secreto/algoritmo/opciones que el middleware. Token ausente o
    inválido → None: la respuesta cae a los defaults seguros (no revela despacho)."""
    auth = request.headers.get("authorization", "")
    if not auth.lower().startswith("bearer "):
        return None
    token = auth[7:].strip()
    # En producción el token DEBE traer `exp` (igual que el middleware): un JWT
    # sin expiración sería una sesión eterna. En dev se tolera.
    options = {"require": ["exp"]} if config.IS_PRODUCTION else None
    try:
        payload = jwt.decode(
            token, config.JWT_SECRET, algorithms=[config.JWT_ALG], options=options
        )
    except jwt.PyJWTError:
        return None
    return payload.get("tenant_id")


@router.get("/status")
async def welcome_status(request: Request):
    tenant_id = _optional_tenant(request)

    instalado = _instalado()
    hay_usuario = await _hay_usuario()
    # Fuente de verdad: el VALOR REAL del `.env` en disco (lo que POST /keys acaba
    # de escribir). NO se lee de os.environ/config porque las claves diferidas
    # (respaldo/openrouter) ya NO se inyectan al proceso vivo; leer el archivo hace
    # que el status refleje lo guardado sin depender de un reinicio.
    env_values = await run_in_threadpool(read_env_values, config.PROJECT_ROOT / ".env")
    # MENOR 3 (revisión capa 2): `openrouter` también se reporta como booleano de PRESENCIA
    # (nunca el valor). El frontend lo necesita para NO auto-saltar el wizard cuando el motor
    # elegido es la cuenta de OpenRouter y esa clave falta (si no, Mia razonaría en local en
    # silencio). Es imprescindible solo cuando la política del tenant es 'openrouter'; se
    # incluye siempre porque es un dato no sensible del `.env` y el frontend decide según la
    # política. La clave la sirve el proxy (proceso aparte); aquí solo se refleja si está en disco.
    faltan_llaves = {
        "busqueda": not env_values.get("VOYAGE_API_KEY", "").strip(),
        "respaldo": not env_values.get("ANTHROPIC_API_KEY", "").strip(),
        "openrouter": not env_values.get("OPENROUTER_API_KEY", "").strip(),
    }
    motor_detectado = {
        "claude": bool(shutil.which("claude")),
        "codex": codex_subscription_llm.is_available(),
        "ollama": bool(shutil.which("ollama")),
    }

    if tenant_id:
        try:
            soul = soul_status(tenant_id) or {}
        except Exception:  # noqa: BLE001 — fail-soft: el status nunca 500 por esto
            logger.exception("welcome.status: no pude leer el estado del perfil")
            soul = {}
        onboarding_completo = bool(soul.get("completed"))
        politica = await llm.model_policy_for(tenant_id)
    else:
        # Sin sesión: valores por defecto seguros, no leen nada de un despacho
        # concreto (no hay uno identificado todavía).
        onboarding_completo = False
        politica = llm._default_policy()

    return {
        "instalado": instalado,
        "hay_usuario": hay_usuario,
        "faltan_llaves": faltan_llaves,
        "onboarding_completo": onboarding_completo,
        "motor_detectado": motor_detectado,
        "politica": politica,
    }


class KeysBody(BaseModel):
    busqueda: str | None = Field(default=None, max_length=_CLAVE_MAX_FIELD)
    respaldo: str | None = Field(default=None, max_length=_CLAVE_MAX_FIELD)
    openrouter: str | None = Field(default=None, max_length=_CLAVE_MAX_FIELD)


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


@router.post("/keys")
async def set_keys(body: KeysBody, request: Request):
    """Guarda en el `.env` de la instalación SOLO las claves que vengan en el
    body (las demás variables del archivo quedan intactas). AUTENTICADO: ver
    el modelo de confianza en el docstring del módulo."""
    _tenant(request)  # exige sesión; el valor no se usa (llaves son globales)

    # Un campo vacío o solo-espacios se trata como NO PROVISTO (se ignora), no como
    # una clave inválida: así, mandar {busqueda: <válida>, respaldo: ""} guarda la
    # búsqueda y no revienta por la hermana vacía. Se conserva el valor original
    # (sin strip) para que _clave_invalida siga detectando "espacios de más".
    provided = {
        campo: valor
        for campo, valor in body.model_dump().items()
        if valor is not None and valor.strip() != ""
    }
    if not provided:
        raise HTTPException(status_code=400, detail="No mandaste ninguna clave para guardar.")

    for campo, valor in provided.items():
        motivo = _clave_invalida(valor)
        if motivo:
            raise HTTPException(status_code=400, detail=motivo)

    updates = {_ENV_KEY_MAP[campo]: valor for campo, valor in provided.items()}
    env_path = config.PROJECT_ROOT / ".env"
    await run_in_threadpool(upsert_env_keys, env_path, updates)

    # Hot-reload EN CALIENTE: SOLO la clave de BÚSQUEDA (Voyage), que el backend
    # usa in-process vía config.VOYAGE_API_KEY (embeddings.py). Las otras dos son
    # DIFERIDAS a propósito:
    #   · `respaldo` (Anthropic) y `openrouter` las lee el proxy mia-litellm.exe
    #     SOLO al arrancar (proceso SEPARADO, no relee el .env). Setearlas aquí en
    #     caliente es INÚTIL para el proxy y peligroso: si pusiéramos
    #     config.OPENROUTER_API_KEY en vivo, agent/llm.py empezaría a insertar el
    #     alias `openrouter-sonnet` en la cadena en-proceso ANTES de que el proxy
    #     pueda servir esa clave → intento de auth fallido. Tampoco tocamos
    #     os.environ (ANTHROPIC/OPENROUTER): no ayuda al proxy y ensancha el radio.
    #     Ambas quedan solo en el .env y se avisan con "cierra y reabre".
    if "busqueda" in provided:
        os.environ["VOYAGE_API_KEY"] = provided["busqueda"]
        config.VOYAGE_API_KEY = provided["busqueda"]

    partes = []
    if "busqueda" in provided:
        partes.append("la clave de búsqueda en tus documentos")
    if "respaldo" in provided:
        partes.append("la clave de respaldo del motor")
    if "openrouter" in provided:
        partes.append("la clave de tu proveedor en la nube")
    mensaje = "Guardé " + " y ".join(partes) + "." if partes else "No había nada que guardar."

    # Aviso FUERTE cuando la clave la sirve el proxy (respaldo/openrouter): el
    # motor no queda activo hasta reiniciar Mia. El frontend lo muestra prominente.
    aviso = None
    if "respaldo" in provided or "openrouter" in provided:
        aviso = ("Para terminar de activar el motor de Mia, cierra Mia por completo "
                 "y vuelve a abrirla; hasta la próxima vez que la abras, esa clave "
                 "todavía no queda activa.")

    return {
        "guardado": {campo: True for campo in provided},
        "mensaje": mensaje,
        "aviso": aviso,
    }


class KeyTestBody(BaseModel):
    tipo: Literal["busqueda", "respaldo", "openrouter"]
    clave: str = Field(min_length=1, max_length=_CLAVE_MAX_FIELD)


def _probar_busqueda(clave: str) -> dict:
    import litellm  # import diferido: solo hace falta para este ping

    try:
        litellm.embedding(
            model=config.litellm_embed_model(),
            input=["hola"],
            api_key=clave,
            timeout=8,
            num_retries=0,
        )
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 — fail-soft: nunca filtrar la clave ni el traceback
        # SOLO el tipo de excepción; NADA de exc_info ni del texto de la excepción,
        # que el proveedor podría rellenar con la clave enviada.
        logger.error("welcome.keys.test fallo (%s)", type(exc).__name__)
        return {"ok": False, "motivo": "No pude confirmar esa clave; revisa que esté completa y activa."}


def _probar_respaldo(clave: str) -> dict:
    import litellm  # import diferido, mismo criterio que _probar_busqueda

    try:
        litellm.completion(
            model="anthropic/claude-haiku-4-5-20251001",
            messages=[{"role": "user", "content": "hola"}],
            api_key=clave,
            max_tokens=8,
            timeout=8,
            num_retries=0,
        )
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 — fail-soft: nunca filtrar la clave ni el traceback
        logger.error("welcome.keys.test fallo (%s)", type(exc).__name__)
        return {"ok": False, "motivo": "No pude confirmar esa clave; revisa que esté completa y activa."}


def _probar_openrouter(clave: str) -> dict:
    """Ping mínimo a la cuenta de OpenRouter (CP-OR): confirma que la clave sirve y
    tiene crédito. Usa el MISMO modelo del alias openrouter-sonnet del gateway, con la
    clave del abogado (sin pasar por el proxy: es un ping directo, como respaldo). Igual
    criterio fail-soft que _probar_respaldo: nunca filtra la clave ni el traceback."""
    import litellm  # import diferido, mismo criterio que _probar_busqueda

    try:
        litellm.completion(
            model="openrouter/anthropic/claude-sonnet-4.6",
            messages=[{"role": "user", "content": "hola"}],
            api_key=clave,
            max_tokens=1,
            timeout=8,
            num_retries=0,
        )
        return {"ok": True}
    except Exception as exc:  # noqa: BLE001 — fail-soft: nunca filtrar la clave ni el traceback
        logger.error("welcome.keys.test fallo (%s)", type(exc).__name__)
        return {"ok": False, "motivo": "No pude confirmar esa clave; revisa que esté completa, activa y con saldo."}


@router.post("/keys/test")
async def test_key(body: KeyTestBody, request: Request):
    """Ping mínimo y real de una clave, SIN guardarla. AUTENTICADO (mismo
    modelo de confianza que /keys)."""
    _tenant(request)

    motivo = _clave_invalida(body.clave)
    if motivo:
        return {"ok": False, "motivo": motivo}

    if body.tipo == "busqueda":
        return await run_in_threadpool(_probar_busqueda, body.clave)
    if body.tipo == "openrouter":
        return await run_in_threadpool(_probar_openrouter, body.clave)
    return await run_in_threadpool(_probar_respaldo, body.clave)
