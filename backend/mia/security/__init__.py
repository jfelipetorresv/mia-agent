"""Mia · security — aislamiento fail-closed de secretos + redacción de logs (CP-S2).

Dos defensas (Ola 1 · blindaje de confidencialidad, patrón Hermes adaptado):

1. `secret_scope`: los secretos POR TENANT (hoy: la clave de Pinecone que cada
   despacho configura en su pantalla) solo se leen dentro de un scope explícito
   del tenant. Sin scope activo → excepción, NUNCA se lee del entorno "por si
   acaso" (una clave global del entorno compartida entre despachos es una fuga
   de credenciales entre clientes esperando a ocurrir).

2. `redact`: todo lo que sale por logging pasa por un formateador que redacta
   patrones de credenciales (claves de API, tokens, contraseñas en URLs de
   conexión, JWTs, llaves privadas…). Encendido SIEMPRE — no existe interruptor
   de runtime que un modelo o un operador descuidado pueda apagar a mitad de
   sesión.

Módulo sin dependencias de Mia (solo stdlib): lo importan config-consumers,
conectores y puntos de entrada sin riesgo de ciclos.
"""
from .redact import (  # noqa: F401
    RedactingFormatter,
    install_redacting_logging,
    mask_secret,
    redact_text,
)
from .secret_scope import (  # noqa: F401
    UnscopedSecretError,
    current_scoped_tenant,
    get_tenant_secret,
    secrets_from_tenant_config,
    tenant_secret_scope,
)

__all__ = [
    "RedactingFormatter",
    "install_redacting_logging",
    "mask_secret",
    "redact_text",
    "UnscopedSecretError",
    "current_scoped_tenant",
    "get_tenant_secret",
    "secrets_from_tenant_config",
    "tenant_secret_scope",
]
