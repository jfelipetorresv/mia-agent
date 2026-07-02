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

OPEN_PATHS = {"/health", "/docs", "/openapi.json", "/redoc", "/api/auth/register", "/api/auth/login"}

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
            payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALG])
        except jwt.PyJWTError:
            return JSONResponse({"detail": "Token inválido"}, status_code=401)

        tenant_id = payload.get("tenant_id")
        if not tenant_id:
            return JSONResponse({"detail": "Token sin tenant_id"}, status_code=401)
        request.state.tenant_id = tenant_id
        request.state.email = payload.get("email")

        # CP2: política de modelo + CP-S3: opt-in de OpenRouter del tenant, para TODO
        # lo que corra en este request. Ambos se resetean en finally.
        policy, allow_or = await _tenant_ctx(tenant_id)
        policy_token = llm.set_model_policy(policy)
        or_token = llm.set_openrouter_allowed(allow_or)
        try:
            return await call_next(request)
        finally:
            llm.reset_openrouter_allowed(or_token)
            llm.reset_model_policy(policy_token)
