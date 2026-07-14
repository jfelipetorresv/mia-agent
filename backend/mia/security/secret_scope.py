"""Mia · security.secret_scope — secretos por tenant, fail-closed (CP-S2).

Patrón Hermes (`agent/secret_scope.py`) adaptado a Mia: en Hermes el fail-closed
se activa con el "multiplexing"; Mia es un servidor multi-tenant SIEMPRE, así que
el scope es obligatorio desde el día uno para todo secreto de clase tenant.

Modelo:
- Un `ContextVar` lleva el scope activo `(tenant_id, {nombre: valor})`. Los
  ContextVar se propagan solos a través de `await` y `asyncio.to_thread` — cada
  request/tarea ve su propio scope, sin locks.
- `get_tenant_secret(nombre)` lee SOLO del scope activo. Sin scope → lanza
  `UnscopedSecretError`. Jamás cae a `os.environ`: una variable global del
  entorno vale para TODA la instalación, y servírsela a un tenant cualquiera
  es compartir credenciales entre despachos.
- El scope se construye en el borde (el endpoint/tarea que ya tiene la fila de
  `tenant_settings` bajo RLS) con `secrets_from_tenant_config`, y se instala
  con `tenant_secret_scope(...)` alrededor del código que consume la clave.

Los secretos GLOBALES de la instalación (PG_PASSWORD, LITELLM_API_KEY,
JWT_SECRET…) NO pasan por aquí: son de la máquina, no de un despacho, y los
sigue leyendo `config.py` del entorno como siempre.
"""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from typing import Iterator, Mapping, Optional

# Scope activo: (tenant_id, mapping de secretos). None = sin scope.
_SCOPE: ContextVar[Optional[tuple[str, Mapping[str, str]]]] = ContextVar(
    "_MIA_TENANT_SECRET_SCOPE", default=None
)

# Claves de secretos por tenant que hoy viven en tenant_settings.config (RLS).
# Al crecer (token de Telegram por despacho — Riesgo #35), se agregan AQUÍ y en
# secrets_from_tenant_config: una sola lista, un solo camino de lectura.
TENANT_SECRET_KEYS = (
    "pinecone_api_key",
    "pinecone_index_name",
)


class UnscopedSecretError(RuntimeError):
    """Lectura de un secreto de tenant SIN scope activo (fail-closed).

    Señal de bug de cableado: el código que consume la clave corrió fuera del
    `tenant_secret_scope(...)` del request/tarea. La respuesta correcta jamás
    es leer del entorno: sería entregar la credencial de la instalación (o de
    otro despacho) "por si acaso"."""


@contextmanager
def tenant_secret_scope(tenant_id: str, secrets: Mapping[str, str]) -> Iterator[None]:
    """Instala el scope de secretos del tenant para el bloque; restaura al salir."""
    token = _SCOPE.set((str(tenant_id), dict(secrets or {})))
    try:
        yield
    finally:
        _SCOPE.reset(token)


def current_scoped_tenant() -> Optional[str]:
    """tenant_id del scope activo, o None si no hay scope."""
    scope = _SCOPE.get()
    return scope[0] if scope else None


def get_tenant_secret(name: str, default: Optional[str] = None) -> Optional[str]:
    """Valor del secreto `name` del tenant del scope activo.

    Sin scope activo → UnscopedSecretError (fail-closed). Con scope pero sin ese
    secreto configurado → `default` (el llamador decide qué significa "no hay":
    p. ej. el conector de Pinecone degrada a noop)."""
    scope = _SCOPE.get()
    if scope is None:
        raise UnscopedSecretError(
            f"get_tenant_secret({name!r}) sin scope de tenant activo. Este código "
            f"debe correr dentro de tenant_secret_scope(tenant_id, secretos) — "
            f"leer del entorno aquí arriesgaría entregar la credencial de la "
            f"instalación o de otro despacho."
        )
    value = scope[1].get(name)
    return value if value else default


def secrets_from_tenant_config(
    config_json: Optional[Mapping], *, tenant_id: str
) -> dict[str, str]:
    """Extrae los secretos por tenant de la fila `tenant_settings.config` (JSONB).

    El llamador ya leyó esa fila bajo RLS (su conexión de tenant): aquí solo se
    NORMALIZA al mapping plano que consume get_tenant_secret. Deliberadamente no
    hay semilla desde os.environ: la clave de un despacho es la que ESE despacho
    configuró en su pantalla, nada más."""
    cfg = dict(config_json or {})
    pinecone = dict(cfg.get("pinecone") or {})
    out: dict[str, str] = {}
    if pinecone.get("api_key"):
        value = str(pinecone["api_key"])
        from .at_rest import decrypt_secret, is_encrypted

        if is_encrypted(value) and not tenant_id:
            raise UnscopedSecretError(
                "Una credencial cifrada de Pinecone exige tenant_id explícito."
            )
        out["pinecone_api_key"] = (
            decrypt_secret(value, tenant_id=tenant_id, purpose="pinecone:api_key")
            if is_encrypted(value) else value
        )
    if pinecone.get("index_name"):
        out["pinecone_index_name"] = str(pinecone["index_name"])
    return out
