"""Mia · connectors.mailbox — conectores de calendario y correo (CP-P3, Ola 2).

Da a Mia ojos sobre la agenda y la bandeja del abogado para volverse proactiva sin
que él pregunte: avisa de eventos próximos del calendario (posibles audiencias/plazos)
y de correos que PARECEN urgentes. Multi-proveedor desde el día uno — Microsoft 365
(Graph) y Google Workspace (Calendar/Gmail) — porque es producto para muchos despachos.

Principios (heredados de Waves 1-2):
- CONFIDENCIALIDAD primero: en CP-P3 las vigilancias son "metadata-only" — leen
  FECHAS, remitentes y asuntos, y NUNCA envían el cuerpo de un correo a ningún LLM.
  El análisis de contenido con IA es opt-in por despacho y llega en CP-P4.
- FAIL-OPEN / degradación con gracia: sin tokens, sin app OAuth o ante error de red,
  el conector calla (None / lista vacía). Una vigilancia caída no tumba el ciclo.
- REGLA DURA de plazos: un evento del calendario es una fecha que el ABOGADO ya fijó;
  Mia la superficie con [VERIFICAR] pero NUNCA calcula un término legal.
- TOKENS por tenant, fail-closed: los tokens OAuth viven en `tenant_oauth_tokens`
  bajo RLS (nunca en el entorno global); las llaves de la app OAuth (client_id/secret)
  son de la INSTALACIÓN (una por despliegue de Mia), en config.py.
- HTTP inyectable: los conectores reciben un cliente `http` (get/post async) para que
  el gate pruebe todo SIN red — mismo patrón que channels/notify.py.
"""
from .base import CalendarEvent, MailHeader, OAuthCreds, PROVIDERS, mail_looks_urgent

__all__ = [
    "CalendarEvent",
    "MailHeader",
    "OAuthCreds",
    "PROVIDERS",
    "mail_looks_urgent",
]
