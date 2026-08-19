"""Mia · api.routes.mailbox — conectar calendario y correo (CP-P3, Ola 2; Fase 1 "fuentes
remotas": multi-proveedor — Microsoft Y Google a la vez).

GET    /api/mailbox/status                  → conexiones POR PROVEEDOR + opt-in IA
POST   /api/mailbox/connect/{provider}      → URL de consentimiento (con `state` FIRMADO);
                                               ?features= (default "mail") compone scopes
GET    /api/mailbox/oauth/callback          → el proveedor devuelve el code; canjea y guarda
DELETE /api/mailbox/disconnect?provider=... → borra los tokens de ESE proveedor (o de
                                               todos si se omite — compatibilidad)
PUT    /api/mailbox/content-analysis        → opt-in de análisis de contenido con IA (CP-P4)

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
from typing import Optional

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


def _parse_features(raw: str) -> set[str]:
    """`?features=mail,drive` -> {"mail","drive"}. Vacío -> {"mail"} (default).
    Funciones no reconocidas → 400 en llano (§G: nunca "scope" ni "OAuth" al abogado)."""
    feats = {f.strip() for f in (raw or "").split(",") if f.strip()}
    if not feats:
        return {"mail"}
    invalid = feats - set(oauth.FEATURES)
    if invalid:
        raise HTTPException(status_code=400,
                            detail=f"No se reconoce lo que pediste conectar: {', '.join(sorted(invalid))}")
    return feats


def _funciones_en_llano(scopes: tuple[str, ...]) -> list[str]:
    """Traduce los scopes técnicos otorgados a una lista en lenguaje llano (§G): nunca
    'scope', 'OAuth' ni 'Graph' — solo lo que el abogado autorizó, en sus palabras."""
    out = ["calendario y correo"]
    if any("gmail.readonly" in s for s in scopes):
        out = ["calendario y correo, incluido el contenido de correos"]
    if "Files.Read" in scopes:
        out.append("archivos de OneDrive")
    return out


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
    """Estado de conexión POR PROVEEDOR (un despacho puede tener Microsoft Y Google a la
    vez desde la Fase 1 de fuentes remotas) + si autorizó el análisis de contenido con IA.

    Mantiene compatibilidad razonable de forma con la versión anterior (un solo
    proveedor): si hay AL MENOS una conexión, `proveedor`/`proveedor_nombre` reflejan la
    primera (mismo campo de antes); `conexiones` es la lista completa, nueva."""
    tenant_id = _tenant(request)
    conexiones_db = await store.list_connections(tenant_id)
    by_provider = {c["provider"]: c for c in conexiones_db}
    analisis_contenido = await store.content_analysis_allowed(tenant_id)

    conexiones = [
        {
            "proveedor": p,
            "proveedor_nombre": _PROVIDER_LABELS[p],
            "conectado": p in by_provider,
            "funciones": _funciones_en_llano(by_provider[p]["scopes"]) if p in by_provider else [],
            # ¿Esta conexión ya otorgó permiso de archivos de OneDrive? Lo consume la UI para
            # ofrecer "Añadir permiso de archivos" en una cuenta Microsoft YA conectada (M3).
            "archivos": ("Files.Read" in by_provider[p]["scopes"]) if p in by_provider else False,
            # Honestidad de UI (F3): la app OAuth de la instalación puede no estar registrada
            # todavía. La UI solo ofrece "Conectar" cuando de verdad se puede — el mismo
            # criterio con el que POST /connect responde 503.
            "disponible": all(config.mailbox_oauth_client(p)),
        }
        for p in PROVIDERS
    ]
    resp = {
        "conectado": bool(conexiones_db),
        "conexiones": conexiones,
        "analisis_contenido": analisis_contenido,
    }
    if conexiones_db:
        primero = conexiones_db[0]["provider"]
        resp["proveedor"] = primero
        resp["proveedor_nombre"] = _PROVIDER_LABELS.get(primero, primero)
    else:
        resp["proveedores"] = [{"id": p, "nombre": _PROVIDER_LABELS[p]} for p in PROVIDERS]
    return resp


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
        # Mensaje en llano (§G): el abogado no puede resolver esto él mismo — es un
        # paso único de instalación que hace su administrador, con guía en Configuración.
        raise HTTPException(
            status_code=503,
            detail=f"La conexión con {_PROVIDER_LABELS[provider]} aún no está habilitada "
                   f"en este equipo. Es un paso único del administrador — pídele que "
                   f"registre la conexión (guía en Configuración).")
    # ?features=mail,mail_content,drive compone los scopes pedidos (default "mail"). En
    # Google, "mail_content" exige reconsentir (gmail.readonly); en Microsoft Mail.Read ya
    # lo cubre. "drive" (cimiento de OneDrive remoto, solo Microsoft) valida en scopes_for.
    features = _parse_features(request.query_params.get("features") or "")
    nonce = secrets.token_urlsafe(24)
    state = sign_state(tenant_id, provider, nonce)
    # SameSite=Lax: la cookie viaja en la navegación de nivel superior con que el
    # proveedor redirige de vuelta al callback. HttpOnly: JS no la ve. secure en prod.
    # path acotado al callback. max_age = ventana del state (10 min).
    response.set_cookie(_NONCE_COOKIE, nonce, max_age=_STATE_TTL_MINUTES * 60,
                        httponly=True, samesite="lax", secure=config.IS_PRODUCTION,
                        path="/api/mailbox")
    try:
        url = oauth.authorize_url(
            provider, client_id=client_id,
            redirect_uri=config.MAILBOX_OAUTH_REDIRECT_URI, state=state,
            login_hint=getattr(request.state, "email", "") or "", features=features)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
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
async def disconnect(request: Request, provider: Optional[str] = None):
    """Desconecta la cuenta del despacho (borra los tokens).

    Con `?provider=microsoft|google`, desconecta SOLO esa conexión (deja la otra
    intacta si hay dos). Sin él (compatibilidad), desconecta todas las conectadas."""
    tenant_id = _tenant(request)
    if provider is not None and provider not in PROVIDERS:
        raise HTTPException(status_code=404, detail="Proveedor no soportado")
    removed = await store.disconnect(tenant_id, provider)
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
    patch = {"allow_content_analysis": activar}
    async with pool.tenant_connection(tenant_id) as conn:
        # jsonb_set con path anidado NO crea el objeto intermedio 'mailbox' si falta
        # (tenants nacen con config='{}'). Se fusiona el padre 'mailbox' entero (||),
        # mismo patrón que budget.py / value.py.
        await conn.execute(
            "INSERT INTO tenant_settings (tenant_id, config) "
            "VALUES (%s::uuid, jsonb_build_object('mailbox', %s::jsonb)) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "config = jsonb_set("
            "  COALESCE(tenant_settings.config, '{}'::jsonb), '{mailbox}', "
            "  COALESCE(tenant_settings.config->'mailbox', '{}'::jsonb) || %s::jsonb, true), "
            "updated_at = now()",
            (tenant_id, Json(patch), Json(patch)),
        )
    return {"analisis_contenido": activar}


def _redirect_frontend(estado: str) -> RedirectResponse:
    """Devuelve al abogado a la pantalla de configuración con el resultado. Consume la
    cookie-nonce (el flujo terminó: que no quede reutilizable)."""
    base = config.CORS_ORIGINS[0] if config.CORS_ORIGINS else "http://localhost:3000"
    resp = RedirectResponse(url=f"{base}/configurar?mailbox={estado}", status_code=302)
    resp.delete_cookie(_NONCE_COOKIE, path="/api/mailbox")
    return resp
