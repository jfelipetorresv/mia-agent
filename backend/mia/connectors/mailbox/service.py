"""Mia · connectors.mailbox.service — orquesta tokens + refresco + conector (CP-P3;
Fase 1 "fuentes remotas": multi-proveedor).

`MailboxService.connector_for(tenant_id, provider=None)` resuelve UN conector:
  1. carga los tokens del tenant (store, RLS) — sin cuenta conectada → None (silencio).
  2. si el access token expiró, lo REFRESCA con el refresh token y PERSISTE el nuevo.
  3. construye el conector del proveedor (Microsoft/Google) con `http` inyectado.
Sin `provider`, conserva compatibilidad (primera conexión); con él, esa conexión puntual.

`MailboxService.connectors_for(tenant_id)` resuelve TODOS los conectores conectados
(dict provider -> conector) — es la puerta que usan las vigilancias desde que un tenant
puede tener Microsoft Y Google a la vez: cada proveedor conectado se vigila, sin que uno
tumbe al otro.

Degradación con gracia: cualquier fallo (sin app OAuth configurada, refresh caído,
proveedor desconocido) → None/{} + log. Una vigilancia nunca revienta por esto."""
from __future__ import annotations

import logging
from typing import Optional

from ... import config
from . import oauth, providers, store
from .base import OAuthCreds

logger = logging.getLogger("mia.connectors.mailbox.service")


class MailboxService:
    """Resuelve el conector de calendario/correo de un tenant, refrescando el token.

    `http` (get/post async estilo httpx) y `store_mod` se inyectan para probar sin red
    ni DB. `client_credentials` permite override en tests (default: config por proveedor).
    """

    def __init__(self, *, http=None, store_mod=None, oauth_mod=None,
                 client_credentials=None) -> None:
        self._http = http
        self._own_http = None
        self._store = store_mod or store
        self._oauth = oauth_mod or oauth
        # (provider) -> (client_id, client_secret). Default: las llaves de la instalación.
        self._client_credentials = client_credentials or config.mailbox_oauth_client

    def _client_http(self):
        """Cliente HTTP: el inyectado (gate), o uno propio httpx creado al vuelo."""
        if self._http is not None:
            return self._http
        if self._own_http is None:
            import httpx
            self._own_http = httpx.AsyncClient(timeout=httpx.Timeout(30.0, connect=10.0))
        return self._own_http

    async def aclose(self) -> None:
        """Cierra el cliente HTTP propio (si se creó). No toca uno inyectado."""
        if self._own_http is not None:
            try:
                await self._own_http.aclose()
            except Exception:  # noqa: BLE001
                pass
            self._own_http = None

    def _client(self, provider: str) -> tuple[str, str]:
        creds = self._client_credentials(provider)
        return (creds or ("", ""))

    async def _ensure_fresh(self, tenant_id: str, creds: OAuthCreds) -> Optional[OAuthCreds]:
        """Refresca el access token si hace falta y persiste el nuevo. None si no se pudo."""
        if not self._oauth.needs_refresh(creds):
            return creds
        client_id, client_secret = self._client(creds.provider)
        if not client_id or not client_secret:
            logger.warning("mailbox: sin app OAuth de %s configurada (client_id/secret); "
                           "no se puede refrescar el token del tenant %s",
                           creds.provider, tenant_id)
            return None
        try:
            refreshed = await self._oauth.refresh_access_token(
                creds, client_id=client_id, client_secret=client_secret,
                http=self._client_http())
        except Exception:  # noqa: BLE001 — refresh caído: degradar (reconectar la cuenta)
            logger.warning("mailbox: no se pudo refrescar el token de %s (tenant %s)",
                           creds.provider, tenant_id)
            return None
        if not refreshed.access_token:
            return None
        try:
            await self._store.save_tokens(tenant_id, refreshed)
        except Exception:  # noqa: BLE001 — persistir es best-effort; el token sirve igual
            logger.warning("mailbox: token refrescado pero no se pudo persistir (tenant %s)",
                           tenant_id)
        return refreshed

    async def connector_for(self, tenant_id: str, provider: Optional[str] = None):
        """Conector listo para el tenant, o None (sin cuenta / error → silencio).

        Con `provider`, la conexión de ESE proveedor puntual; sin él (compatibilidad),
        la primera conexión disponible (ver `store.load_tokens`)."""
        try:
            creds = await self._store.load_tokens(tenant_id, provider)
        except Exception:  # noqa: BLE001 — migración ausente u otra falla: no hay conector
            logger.warning("mailbox: no se pudieron leer los tokens del tenant %s", tenant_id)
            return None
        if creds is None:
            return None
        fresh = await self._ensure_fresh(tenant_id, creds)
        if fresh is None:
            return None
        return providers.build_connector(fresh, http=self._client_http())

    async def connectors_for(self, tenant_id: str) -> dict:
        """Un conector por CADA proveedor conectado del tenant (dict provider -> conector).

        Sin cuentas conectadas o si `list_connections` falla (migración ausente, DB
        caída) → {} (silencio, igual criterio que connector_for). Un proveedor cuyo
        refresh falle se omite (no tumba a los demás)."""
        try:
            conexiones = await self._store.list_connections(tenant_id)
        except Exception:  # noqa: BLE001
            logger.warning("mailbox: no se pudieron listar las conexiones del tenant %s",
                           tenant_id)
            return {}
        out: dict = {}
        for c in conexiones:
            provider = c.get("provider") if isinstance(c, dict) else None
            if not provider:
                continue
            conn = await self.connector_for(tenant_id, provider)
            if conn is not None:
                out[provider] = conn
        return out
