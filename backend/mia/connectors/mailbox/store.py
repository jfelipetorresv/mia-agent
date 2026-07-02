"""Mia · connectors.mailbox.store — persistencia de tokens y debounce (CP-P3).

Todo bajo RLS (`pool.tenant_connection`): los tokens OAuth y el ledger de avisos son
datos POR DESPACHO. El opt-in de análisis de contenido con IA vive en
`tenant_settings.config['mailbox']['allow_content_analysis']` (default False), leído
igual que `allow_openrouter` (agent/llm.py) — fail-closed."""
from __future__ import annotations

import logging
from typing import Optional

from ...db import pool
from .base import OAuthCreds

logger = logging.getLogger("mia.connectors.mailbox.store")


async def save_tokens(tenant_id: str, creds: OAuthCreds) -> None:
    """Guarda (o reemplaza) los tokens OAuth del tenant. Un proveedor por tenant (v1)."""
    scopes = " ".join(creds.scopes or ())
    async with pool.tenant_connection(tenant_id) as conn:
        await conn.execute(
            "INSERT INTO tenant_oauth_tokens "
            "  (tenant_id, provider, access_token, refresh_token, expires_at, scopes) "
            "VALUES (%s::uuid, %s, %s, %s, %s, %s) "
            "ON CONFLICT (tenant_id) DO UPDATE SET "
            "  provider = EXCLUDED.provider, access_token = EXCLUDED.access_token, "
            "  refresh_token = CASE WHEN EXCLUDED.refresh_token <> '' "
            "                       THEN EXCLUDED.refresh_token "
            "                       ELSE tenant_oauth_tokens.refresh_token END, "
            "  expires_at = EXCLUDED.expires_at, scopes = EXCLUDED.scopes, "
            "  updated_at = now()",
            (tenant_id, creds.provider, creds.access_token, creds.refresh_token,
             creds.expires_at, scopes),
        )


async def load_tokens(tenant_id: str) -> Optional[OAuthCreds]:
    """Tokens OAuth del tenant, o None si no ha conectado ninguna cuenta."""
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT provider, access_token, refresh_token, expires_at, scopes "
            "FROM tenant_oauth_tokens WHERE tenant_id = %s::uuid",
            (tenant_id,),
        )).fetchone()
    if not row:
        return None
    return OAuthCreds(
        provider=str(row[0]), access_token=str(row[1] or ""),
        refresh_token=str(row[2] or ""), expires_at=row[3],
        scopes=tuple((row[4] or "").split()),
    )


async def disconnect(tenant_id: str) -> bool:
    """Elimina los tokens del tenant (desconecta la cuenta). False si no había."""
    async with pool.tenant_connection(tenant_id) as conn:
        cur = await conn.execute(
            "DELETE FROM tenant_oauth_tokens WHERE tenant_id = %s::uuid", (tenant_id,))
    return cur.rowcount > 0


# ── debounce de avisos (no re-avisar del mismo evento/correo cada ciclo) ─────────
async def filter_unnotified(tenant_id: str, kind: str, external_ids: list[str]) -> set[str]:
    """De `external_ids`, los que AÚN NO se han avisado (no están en el ledger)."""
    if not external_ids:
        return set()
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT external_id FROM mailbox_notifications "
            "WHERE kind = %s AND external_id = ANY(%s)",
            (kind, list(external_ids)),
        )).fetchall()
    seen = {str(r[0]) for r in rows}
    return {eid for eid in external_ids if eid not in seen}


# Antigüedad tras la cual una entrada del ledger ya no aporta al debounce (un evento
# de hace más de un mes o ya venció, o ya no está en la bandeja) → se poda para acotar
# el crecimiento (revisión capa 2, hallazgo #3). La poda es por tenant (RLS) y barata.
_LEDGER_RETENTION_DAYS = 30


async def mark_notified(tenant_id: str, kind: str, external_ids: list[str]) -> None:
    """Marca en el ledger que ya se avisó de estos eventos/correos (debounce).

    Además PODA las entradas del tenant más viejas que _LEDGER_RETENTION_DAYS: un evento
    de hace un mes ya no vuelve a la ventana de 48h, así que su registro sobra (evita el
    crecimiento sin cota del ledger)."""
    if not external_ids:
        return
    async with pool.tenant_connection(tenant_id) as conn:
        async with conn.cursor() as cur:
            await cur.executemany(
                "INSERT INTO mailbox_notifications (tenant_id, kind, external_id) "
                "VALUES (%s::uuid, %s, %s) ON CONFLICT DO NOTHING",
                [(tenant_id, kind, eid) for eid in external_ids],
            )
        await conn.execute(
            "DELETE FROM mailbox_notifications "
            "WHERE notified_at < now() - make_interval(days => %s)",
            (_LEDGER_RETENTION_DAYS,),
        )


# ── opt-in de análisis de contenido con IA (confidencialidad, CP-P4) ─────────────
async def content_analysis_allowed(tenant_id: str) -> bool:
    """True si el despacho autorizó que Mia analice el CONTENIDO de correos con IA.

    De `tenant_settings.config->'mailbox'->>'allow_content_analysis'` (RLS). Ausente,
    inválido o error → False (fail-closed: nunca se manda el cuerpo de un correo a un
    LLM sin autorización explícita del despacho — regla dura del propietario)."""
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config->'mailbox'->>'allow_content_analysis' "
                "FROM tenant_settings WHERE tenant_id = %s::uuid",
                (tenant_id,),
            )).fetchone()
        return bool(row and str(row[0] or "").strip().lower() in ("true", "1", "yes", "on"))
    except Exception:  # noqa: BLE001 — sin fila/tabla o error de DB: fail-closed
        logger.warning("no se pudo leer allow_content_analysis del tenant %s", tenant_id)
        return False
