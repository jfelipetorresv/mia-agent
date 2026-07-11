"""Mia · api.middleware — fija el contexto de tenant a partir del JWT.

El `tenant_id` del JWT viaja a request.state y, en los handlers, al GUC
`app.tenant_id` vía db.pool.tenant_connection (donde RLS lo aplica).

CP2 (decisión #27): tras autenticar, el middleware también fija la POLÍTICA DE MODELO
del tenant (suscripcion/nube/soberano) en el ContextVar de agent/llm.py, leyendo
`tenant_settings.config['model_policy']` con un caché en memoria por tenant (TTL 60s)
para no pagar un roundtrip de DB en cada request. Se resetea en finally.
"""
from __future__ import annotations

import time

import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .. import config
from ..agent import llm
from ..metrics import usage as usage_metrics
from ..observability import audit

# CP-E1: se audita CADA acción mutante (POST/PUT/PATCH/DELETE) autenticada. Los GET
# (lecturas/polling) no son "acciones" y no ensucian el rastro. Se excluye el
# dictado/voz (alta frecuencia, latencia sensible, sin valor de cumplimiento).
_AUDITED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_AUDIT_SKIP_PREFIXES = ("/api/speech/",)

# Rutas sin token. Las docs interactivas (/docs, /redoc, /openapi.json) solo quedan
# abiertas en desarrollo: en producción exponen el mapa completo del API a cualquiera
# (auditoría 2026-07; en main.py además se apagan del todo con MIA_ENV=production).
# El callback de OAuth de calendario/correo (CP-P3) no trae Bearer: lo invoca el
# navegador redirigido por Microsoft/Google. Su autenticidad se verifica con el `state`
# FIRMADO (routes/mailbox.verify_state), no con el JWT de sesión.
OPEN_PATHS = {"/health", "/api/auth/register", "/api/auth/login",
              "/api/mailbox/oauth/callback",
              # F3 (bienvenida): el frontend necesita saber si ya hay un despacho
              # creado ANTES de que exista sesión, para decidir "crear despacho" vs
              # "iniciar sesión". El handler (routes/welcome.py) solo expone campos
              # NO sensibles sin sesión (ver docstring del módulo); con Bearer válido
              # enriquece la respuesta con datos del despacho. `/keys` y `/keys/test`
              # NO están aquí: exigen sesión (llaves globales de instalación).
              "/api/welcome/status"}
if not config.IS_PRODUCTION:
    OPEN_PATHS |= {"/docs", "/openapi.json", "/redoc"}

# En producción el token DEBE traer expiración: un JWT sin `exp` sería una sesión
# eterna imposible de invalidar. En dev se tolera (los gates acuñan tokens sin exp).
_JWT_DECODE_OPTIONS = {"require": ["exp"]} if config.IS_PRODUCTION else None

# Caché {tenant_id: (política, opt-in OpenRouter, monotonic_ts)} — TTL corto: un cambio
# desde el Dashboard se aplica en ≤60s (y el PUT del endpoint lo invalida de inmediato).
_POLICY_TTL_SECONDS = 60.0
_policy_cache: dict[str, tuple[str, bool, float]] = {}


def invalidate_policy_cache(tenant_id: str | None = None) -> None:
    """Invalida el caché de política (de un tenant o todo). La usa el PUT del endpoint
    /settings/model-policy para que el cambio aplique en el siguiente request."""
    if tenant_id is None:
        _policy_cache.clear()
    else:
        _policy_cache.pop(tenant_id, None)


async def _tenant_ctx(tenant_id: str) -> tuple[str, bool]:
    """Política de modelo + opt-in de OpenRouter del tenant, con caché TTL. Ambos
    se leen de `tenant_settings.config`; sus helpers validan y caen a un default
    seguro (política → config; opt-in OpenRouter → False)."""
    now = time.monotonic()
    hit = _policy_cache.get(tenant_id)
    if hit is not None and (now - hit[2]) < _POLICY_TTL_SECONDS:
        return hit[0], hit[1]
    policy = await llm.model_policy_for(tenant_id)
    allow_or = await llm.openrouter_allowed_for(tenant_id)
    _policy_cache[tenant_id] = (policy, allow_or, now)
    return policy, allow_or


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.tenant_id = None
        request.state.email = None
        # El preflight CORS (OPTIONS) no trae token; lo maneja CORSMiddleware.
        # No verificar JWT aqui evita devolver 401 antes del preflight.
        if request.method == "OPTIONS" or request.url.path in OPEN_PATHS:
            return await call_next(request)

        auth = request.headers.get("authorization", "")
        if not auth.lower().startswith("bearer "):
            return JSONResponse({"detail": "Falta token Bearer"}, status_code=401)
        token = auth[7:].strip()
        try:
            payload = jwt.decode(
                token, config.JWT_SECRET, algorithms=[config.JWT_ALG],
                options=_JWT_DECODE_OPTIONS,
            )
        except jwt.PyJWTError:
            return JSONResponse({"detail": "Token inválido"}, status_code=401)

        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            return JSONResponse({"detail": "Token sin tenant_id"}, status_code=401)
        request.state.tenant_id = tenant_id
        request.state.email = payload.get("email")

        # CP2: política de modelo + CP-S3: opt-in de OpenRouter del tenant, para TODO
        # lo que corra en este request. CP-V1: scope de registro de uso del LLM
        # (tokens reales → turn_usage → "valor neto" del panel). Todo se resetea
        # en finally.
        policy, allow_or = await _tenant_ctx(tenant_id)
        policy_token = llm.set_model_policy(policy)
        or_token = llm.set_openrouter_allowed(allow_or)
        usage_token = usage_metrics.set_usage_scope(tenant_id, source="api")
        try:
            response = await call_next(request)
            await self._maybe_audit(request, response, tenant_id)
            return response
        finally:
            usage_metrics.reset_usage_scope(usage_token)
            llm.reset_openrouter_allowed(or_token)
            llm.reset_model_policy(policy_token)

    @staticmethod
    async def _maybe_audit(request: Request, response, tenant_id: str) -> None:
        """CP-E1: deja rastro de cada acción mutante en audit_logs (read-only,
        fail-open — audit.record nunca lanza)."""
        if request.method not in _AUDITED_METHODS:
            return
        path = request.url.path
        if any(path.startswith(p) for p in _AUDIT_SKIP_PREFIXES):
            return
        await audit.record(
            "api_call",
            tenant_id=tenant_id,
            user_email=getattr(request.state, "email", None),
            entity_type=request.method,
            entity_id=path,
            payload={"status": getattr(response, "status_code", None)},
        )
