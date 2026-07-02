"""Mia · api.routes.mailbox — conectar calendario y correo (CP-P3, Ola 2).

GET    /api/mailbox/status              → ¿hay cuenta conectada? proveedor + opt-in IA
POST   /api/mailbox/connect/{provider}  → URL de consentimiento (con `state` FIRMADO)
GET    /api/mailbox/oauth/callback      → el proveedor devuelve el code; canjea y guarda
DELETE /api/mailbox/disconnect          → borra los tokens (desconecta la cuenta)
PUT    /api/mailbox/content-analysis    → opt-in de análisis de contenido con IA (CP-P4)

Seguridad del flujo OAuth:
- El `state` que viaja al proveedor es un JWT FIRMADO (JWT_SECRET) con el tenant_id, el
  proveedor y un propósito acotado, y expira pronto. Así el callback —que NO trae Bearer,
  porque lo invoca el navegador redirigido por Microsoft/Google— recupera el tenant de
  forma verificable y resiste CSRF (nadie puede fabricar un state válido).
- Los tokens quedan por despacho bajo RLS (connectors.mailbox.store). Las llaves de la
  app OAuth (client_id/secret) son de la instalación (config.py) — sin ellas, el
  proveedor no se ofrece (degradación con gracia).

§G: el abogado ve "Calendario y correo", "Microsoft 365" / "Google Workspace" — nunca
"OAuth", "token" ni "Graph".
"""
from __future__ import annotations

import logging
import secrets
from datetime import datetime, timedelta, timezone

import jwt
from fastapi import APIRouter, HTTPException, Request, Response
from fastapi.responses import RedirectResponse
from psycopg.types.json import Json

from ... import config
from ...connectors.mailbox import oauth, store
from ...connectors.mailbox.base import PROVIDERS
from ...db import pool

logger = logging.getLogger("mia.api.mailbox")
router = APIRouter(tags=["mailbox"])

# Nombre en español por proveedor (§G — sin marcas técnicas del protocolo).
_PROVIDER_LABELS = {"microsoft": "Microsoft 365", "google": "Google Workspace"}

_STATE_PURPOSE = "mailbox_oauth"
_STATE_TTL_MINUTES = 10          # el consentimiento debe completarse pronto
_NONCE_COOKIE = "mia_oauth_nonce"  # ata el consentimiento a la sesión que lo inició


def _tenant(request: Request) -> str:
    t = getattr(request.state, "tenant_id", None)
    if not t:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    return t


def sign_state(tenant_id: str, provider: str, nonce: str,
               now: datetime | None = None) -> str:
    """Firma el `state` OAuth (tenant + proveedor + nonce + propósito, expiración corta).

    El `nonce` viaja tanto en el state (firmado) como en una cookie de la sesión que
    pulsó "conectar"; el callback exige que coincidan → ata el consentimiento a ese
    navegador y frustra la FIJACIÓN de cuenta cross-tenant (revisión capa 2, hallazgo #1)."""
    now = now or datetime.now(timezone.utc)
    return jwt.encode(
        {"tenant_id": tenant_id, "provider": provider, "purpose": _STATE_PURPOSE,
         "nonce": nonce, "exp": now + timedelta(minutes=_STATE_TTL_MINUTES)},
        config.JWT_SECRET, algorithm=config.JWT_ALG)


def verify_state(token: str) -> tuple[str, str, str]:
    """Valida el `state` del callback → (tenant_id, provider, nonce). Lanza si es inválido."""
    try:
        payload = jwt.decode(token, config.JWT_SECRET, algorithms=[config.JWT_ALG])
    except jwt.PyJWTError as exc:
        raise HTTPException(status_code=400, detail="Enlace de conexión inválido o vencido") from exc
    if payload.get("purpose") != _STATE_PURPOSE:
        raise HTTPException(status_code=400, detail="Enlace de conexión inválido")
    tenant_id, provider = payload.get("tenant_id"), payload.get("provider")
    if not tenant_id or provider not in PROVIDERS:
        raise HTTPException(status_code=400, detail="Enlace de conexión inválido")
    return str(tenant_id), str(provider), str(payload.get("nonce") or "")


@router.get("/mailbox/status")
async def status(request: Request):
    """¿El despacho tiene una cuenta conectada? Proveedor y si autorizó análisis con IA."""
    tenant_id = _tenant(request)
    creds = await store.load_tokens(tenant_id)
    if creds is None:
        return {"conectado": False,
                "proveedores": [{"id": p, "nombre": _PROVIDER_LABELS[p]} for p in PROVIDERS]}
    return {
        "conectado": True,
        "proveedor": creds.provider,
        "proveedor_nombre": _PROVIDER_LABELS.get(creds.provider, creds.provider),
        "analisis_contenido": await store.content_analysis_allowed(tenant_id),
    }


@router.post("/mailbox/connect/{provider}")
async def connect(provider: str, request: Request, response: Response):
    """Devuelve la URL a la que el abogado va UNA vez para autorizar su cuenta.

    Fija además una cookie de sesión con el `nonce` que también va firmado en el state:
    el callback exige que coincidan (binding contra fijación de cuenta, hallazgo #1)."""
    tenant_id = _tenant(request)
    if provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Proveedor no soportado")
    client_id, client_secret = config.mailbox_oauth_client(provider)
    if not client_id or not client_secret:
        # La app OAuth de la instalación no está registrada aún (falta configurar .env).
        raise HTTPException(
            status_code=503,
            detail=f"La conexión con {_PROVIDER_LABELS[provider]} no está habilitada en "
                   f"este servidor todavía.")
    # ?content=1 pide además la lectura del CUERPO del correo (análisis con IA, CP-P4).
    # En Google exige reconsentir (gmail.readonly); en Microsoft Mail.Read ya lo cubre.
    content = str(request.query_params.get("content") or "").strip().lower() in ("1", "true", "yes", "on")
    nonce = secrets.token_urlsafe(24)
    state = sign_state(tenant_id, provider, nonce)
    # SameSite=Lax: la cookie viaja en la navegación de nivel superior con que el
    # proveedor redirige de vuelta al callback. HttpOnly: JS no la ve. secure en prod.
    # path acotado al callback. max_age = ventana del state (10 min).
    response.set_cookie(_NONCE_COOKIE, nonce, max_age=_STATE_TTL_MINUTES * 60,
                        httponly=True, samesite="lax", secure=config.IS_PRODUCTION,
                        path="/api/mailbox")
    url = oauth.authorize_url(
        provider, client_id=client_id,
        redirect_uri=config.MAILBOX_OAUTH_REDIRECT_URI, state=state,
        login_hint=getattr(request.state, "email", "") or "", content=content)
    return {"url": url, "proveedor_nombre": _PROVIDER_LABELS[provider]}


@router.get("/mailbox/oauth/callback")
async def oauth_callback(request: Request):
    """Callback de consentimiento: el proveedor trae ?code&state. Sin Bearer — el
    tenant se recupera del `state` firmado. Canjea el code por tokens y los guarda."""
    params = request.query_params
    if params.get("error"):
        return _redirect_frontend("error")
    code, state = params.get("code"), params.get("state")
    if not code or not state:
        raise HTTPException(status_code=400, detail="Falta el código de autorización")
    tenant_id, provider, nonce = verify_state(state)
    # Binding sesión↔state (hallazgo #1): el nonce del state DEBE coincidir con la cookie
    # que se fijó al pulsar "conectar". Sin cookie o distinta → rechazo (fijación de cuenta).
    cookie_nonce = request.cookies.get(_NONCE_COOKIE)
    if not nonce or not cookie_nonce or not secrets.compare_digest(cookie_nonce, nonce):
        raise HTTPException(status_code=400, detail="Enlace de conexión inválido o vencido")
    client_id, client_secret = config.mailbox_oauth_client(provider)
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="Conexión no habilitada")

    import httpx
    async with httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0)) as http:
        try:
            creds = await oauth.exchange_code(
                provider, code=code, client_id=client_id, client_secret=client_secret,
                redirect_uri=config.MAILBOX_OAUTH_REDIRECT_URI, http=http)
        except Exception:  # noqa: BLE001 — canje fallido: el abogado reintenta la conexión
            logger.warning("mailbox: canje de code falló para %s (tenant %s)", provider, tenant_id)
            return _redirect_frontend("error")
    if not creds.access_token:
        return _redirect_frontend("error")
    await store.save_tokens(tenant_id, creds)
    logger.info("mailbox: cuenta de %s conectada para el tenant %s", provider, tenant_id)
    return _redirect_frontend("conectado")


@router.delete("/mailbox/disconnect")
async def disconnect(request: Request):
    """Desconecta la cuenta del despacho (borra los tokens)."""
    tenant_id = _tenant(request)
    removed = await store.disconnect(tenant_id)
    return {"desconectado": bool(removed)}


@router.put("/mailbox/content-analysis")
async def set_content_analysis(request: Request):
    """Opt-in del despacho para que Mia analice el CONTENIDO de correos con IA (CP-P4).

    Alto impacto de confidencialidad: apagado por defecto; el abogado lo enciende a
    propósito. Persiste en tenant_settings.config['mailbox']['allow_content_analysis']
    con un MERGE jsonb atómico (no pisa otros settings)."""
    tenant_id = _tenant(request)
    try:
        body = await request.json()
    except Exception:  # noqa: BLE001
        body = None
    activar = bool((body or {}).get("activar")) if isinstance(body, dict) else False
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = jsonb_set(COALESCE(tenant_settings.config, '{}'::jsonb), "
            "  '{mailbox,allow_content_analysis}', %s::jsonb, true), updated_at = now()",
            (tenant_id, Json({"mailbox": {"allow_content_analysis": activar}}),
             "true" if activar else "false"),
        )
    return {"analisis_contenido": activar}


def _redirect_frontend(estado: str) -> RedirectResponse:
    """Devuelve al abogado a la pantalla de configuración con el resultado. Consume la
    cookie-nonce (el flujo terminó: que no quede reutilizable)."""
    base = config.CORS_ORIGINS[0] if config.CORS_ORIGINS else "http://localhost:3000"
    resp = RedirectResponse(url=f"{base}/configurar?mailbox={estado}", status_code=302)
    resp.delete_cookie(_NONCE_COOKIE, path="/api/mailbox")
    return resp
