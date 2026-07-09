"""Mia · connectors.mailbox.oauth — flujo OAuth2 de Microsoft y Google (CP-P3).

Solo la parte de AUTORIZACIÓN y TOKENS (endpoints, scopes, canje y refresco). Las
llamadas a las APIs de datos (calendario/correo) viven en providers.py.

Modelo estándar "authorization code + refresh token":
  1. `authorize_url(...)` — URL a la que el abogado va UNA vez a dar consentimiento.
  2. `exchange_code(...)` — canjea el `code` del callback por access+refresh token.
  3. `refresh_access_token(...)` — cuando el access token expira, se renueva con el
     refresh token (sin volver a molestar al abogado).

`http` (get/post async, estilo httpx) se inyecta para probar sin red. `now` se inyecta
para tests deterministas del cálculo de expiración.

NOTA [VERIFICAR]: endpoints y scopes son los estándar publicados de cada proveedor;
el gate mockea el HTTP, así que no se ejercitan en vivo. Confirmar al conectar la
primera cuenta real (mismo criterio que agent_hub.build_args)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional
from urllib.parse import urlencode

from .base import OAuthCreds

# Margen para renovar ANTES de que expire de verdad (evita usar un token recién vencido
# por desfase de reloj / latencia).
_REFRESH_SKEW_SECONDS = 120

# Scopes de LECTURA. Por defecto, calendario + METADATA de correo (sin cuerpo): es lo
# que la vigilancia metadata-only de CP-P3 necesita. Para el análisis de contenido con
# IA (CP-P4, opt-in) se usarán los scopes de lectura completa (`_CONTENT_SCOPES`).
PROVIDER_OAUTH: dict[str, dict] = {
    "microsoft": {
        # `common` sirve a cuentas de organización y personales; `offline_access` es lo
        # que hace que Microsoft entregue refresh_token.
        "authorize_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "scopes": ("offline_access", "openid", "email",
                   "Calendars.Read", "Mail.Read"),
        "extra_authorize": {"response_mode": "query"},
    },
    "google": {
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        # gmail.metadata = cabeceras sin cuerpo (metadata-only de CP-P3).
        "scopes": ("https://www.googleapis.com/auth/calendar.readonly",
                   "https://www.googleapis.com/auth/gmail.metadata",
                   "openid", "email"),
        # `access_type=offline` + `prompt=consent` fuerzan a Google a dar refresh_token.
        "extra_authorize": {"access_type": "offline", "prompt": "consent"},
    },
}

# Scopes para el ANÁLISIS DE CONTENIDO con IA (CP-P4, opt-in): incluyen la LECTURA del
# cuerpo del correo. En Google, gmail.readonly reemplaza a gmail.metadata (metadata no
# puede leer el cuerpo → reconectar con estos scopes). En Microsoft, Mail.Read ya
# devuelve el cuerpo, así que los scopes de contenido son los MISMOS que los de metadata
# (no hace falta reconsentir).
_CONTENT_SCOPES: dict[str, tuple[str, ...]] = {
    "microsoft": PROVIDER_OAUTH["microsoft"]["scopes"],
    "google": ("https://www.googleapis.com/auth/calendar.readonly",
               "https://www.googleapis.com/auth/gmail.readonly",
               "openid", "email"),
}

# Scopes para "drive" (Fase 1 de fuentes remotas — cimiento de OneDrive remoto selectivo,
# feature que construye OTRA fase; aquí solo se prepara el scope). SOLO Microsoft: Google
# no ofrece esta feature en este proyecto (Google Drive no es el conector en alcance).
# Mínimo de lectura: Files.Read (no Files.Read.All — no hace falta leer TODO el drive,
# el abogado elige qué carpeta compartir en la fase que consuma esto).
_DRIVE_SCOPES: dict[str, tuple[str, ...]] = {
    "microsoft": ("Files.Read",),
}

# Features de conexión reconocidas. Cada una exige su propio scope mínimo — ver
# `scopes_for`. "mail" es la base (CP-P3, siempre presente salvo que se pida solo
# "drive"); "mail_content" es el opt-in de leer el CUERPO del correo (CP-P4, lo que antes
# viajaba como `?content=1`); "drive" es el cimiento de OneDrive remoto (solo Microsoft).
FEATURES: tuple[str, ...] = ("mail", "mail_content", "drive")


def _cfg(provider: str) -> dict:
    cfg = PROVIDER_OAUTH.get(provider)
    if cfg is None:
        raise ValueError(f"proveedor OAuth desconocido: {provider!r}")
    return cfg


def _validate_features(provider: str, features: set[str]) -> None:
    unknown = features - set(FEATURES)
    if unknown:
        raise ValueError(f"funciones de conexión desconocidas: {sorted(unknown)}")
    if "drive" in features and provider != "microsoft":
        raise ValueError(f"la función 'drive' no está disponible para {provider!r} "
                         f"(solo Microsoft / OneDrive)")


def scopes_for(provider: str, features: Iterable[str] = ("mail",)) -> tuple[str, ...]:
    """Scopes de lectura que exige el conjunto de FEATURES pedido, compuestos sin
    duplicar. Documentado por feature (qué exige cada una):

      - "mail" (default): calendario + METADATA de correo (CP-P3, sin cuerpo).
      - "mail_content": añade la lectura del CUERPO del correo (CP-P4, opt-in). En
        Google, gmail.readonly reemplaza a gmail.metadata (metadata no trae cuerpo);
        en Microsoft, Mail.Read ya lo cubre (no cambia scopes, no hace falta reconsentir).
      - "drive" (SOLO Microsoft): añade Files.Read — cimiento de OneDrive remoto
        selectivo (Fase 1; la feature que lo CONSUME la construye otra fase).

    Sin features reconocidas (p.ej. conjunto vacío) cae al mínimo de "mail"."""
    feats = set(features)
    _validate_features(provider, feats)
    scopes: list[str] = []
    seen: set[str] = set()

    def add(items: Iterable[str]) -> None:
        for s in items:
            if s not in seen:
                seen.add(s)
                scopes.append(s)

    if "mail_content" in feats:
        add(_CONTENT_SCOPES.get(provider) or _cfg(provider)["scopes"])
    elif "mail" in feats:
        add(_cfg(provider)["scopes"])
    if "drive" in feats:
        add(_DRIVE_SCOPES["microsoft"])
    if not scopes:   # ninguna feature reconocida aportó scopes → mínimo de siempre
        add(_cfg(provider)["scopes"])
    return tuple(scopes)


def authorize_url(provider: str, *, client_id: str, redirect_uri: str, state: str,
                  login_hint: str = "", features: Iterable[str] = ("mail",)) -> str:
    """URL de consentimiento a la que el abogado va una vez para conectar su cuenta.
    `features` compone los scopes pedidos (ver `scopes_for`); default solo "mail"."""
    cfg = _cfg(provider)
    params = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes_for(provider, features)),
        "state": state,
        **cfg.get("extra_authorize", {}),
    }
    if login_hint:
        params["login_hint"] = login_hint
    return cfg["authorize_url"] + "?" + urlencode(params)


def _creds_from_token_response(provider: str, data: dict, *, prev: Optional[OAuthCreds],
                               now: datetime) -> OAuthCreds:
    """Construye OAuthCreds desde la respuesta del token endpoint.

    En un REFRESH, algunos proveedores (Microsoft a veces, Google casi siempre) NO
    reenvían refresh_token: se conserva el anterior (`prev`)."""
    access = str(data.get("access_token") or "")
    refresh = str(data.get("refresh_token") or "") or (prev.refresh_token if prev else "")
    expires_in = data.get("expires_in")
    expires_at = None
    if expires_in is not None:
        try:
            expires_at = now + timedelta(seconds=int(expires_in))
        except (TypeError, ValueError):
            expires_at = None
    raw_scope = data.get("scope")
    scopes = tuple(str(raw_scope).split()) if raw_scope else (prev.scopes if prev else ())
    return OAuthCreds(provider=provider, access_token=access, refresh_token=refresh,
                      expires_at=expires_at, scopes=scopes)


async def _post_token(provider: str, form: dict, *, http) -> dict:
    cfg = _cfg(provider)
    resp = await http.post(cfg["token_url"], data=form,
                           headers={"Accept": "application/json"})
    status = getattr(resp, "status_code", 0)
    if status != 200:
        raise OAuthError(f"token endpoint de {provider} devolvió status {status}")
    return resp.json()


class OAuthError(RuntimeError):
    """Fallo en canje/refresco de token OAuth (se degrada con gracia arriba)."""


async def exchange_code(provider: str, *, code: str, client_id: str, client_secret: str,
                        redirect_uri: str, http,
                        now: Optional[datetime] = None) -> OAuthCreds:
    """Canjea el `code` del callback de consentimiento por access+refresh token."""
    now = now or datetime.now(timezone.utc)
    form = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
    }
    data = await _post_token(provider, form, http=http)
    return _creds_from_token_response(provider, data, prev=None, now=now)


async def refresh_access_token(creds: OAuthCreds, *, client_id: str, client_secret: str,
                               http, now: Optional[datetime] = None) -> OAuthCreds:
    """Renueva el access token usando el refresh token (sin molestar al abogado)."""
    if not creds.refresh_token:
        raise OAuthError(f"sin refresh_token para {creds.provider}: reconectar la cuenta")
    now = now or datetime.now(timezone.utc)
    form = {
        "grant_type": "refresh_token",
        "refresh_token": creds.refresh_token,
        "client_id": client_id,
        "client_secret": client_secret,
    }
    data = await _post_token(creds.provider, form, http=http)
    return _creds_from_token_response(creds.provider, data, prev=creds, now=now)


def needs_refresh(creds: OAuthCreds, *, now: Optional[datetime] = None,
                  skew_seconds: int = _REFRESH_SKEW_SECONDS) -> bool:
    """True si el access token falta o está por expirar (dentro del margen de skew)."""
    if not creds.access_token:
        return True
    if creds.expires_at is None:
        return True  # sin expiración conocida → refrescar por seguridad
    now = now or datetime.now(timezone.utc)
    return creds.expires_at <= now + timedelta(seconds=skew_seconds)
