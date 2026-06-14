"""Mia · api.middleware — fija el contexto de tenant a partir del JWT.

El `tenant_id` del JWT viaja a request.state y, en los handlers, al GUC
`app.tenant_id` vía db.pool.tenant_connection (donde RLS lo aplica).
"""
from __future__ import annotations

import jwt
from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

from .. import config

OPEN_PATHS = {"/health", "/docs", "/openapi.json", "/redoc"}


class TenantContextMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.tenant_id = None
        if request.url.path in OPEN_PATHS:
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
        return await call_next(request)
