"""Mia · cron.suggestions — automatizaciones y sugerencias consent-first (CP-P2, Ola 2).

Dos servicios, todo bajo RLS (`pool.tenant_connection`):

  · AutomationService — automatizaciones ACTIVAS del despacho. La ÚNICA forma de crear
    una es un acto humano explícito (rellenar una plantilla o aceptar una sugerencia);
    ni este módulo ni el generador de sugerencias crean una automatización por su cuenta.

  · SuggestionService — Mia PROPONE automatizaciones y el abogado acepta/descarta. Nunca
    auto-activa (consent-first). Máx. MAX_PENDING pendientes (no se convierte en un muro
    de avisos). `dedup_key` LATCHEA: una propuesta aceptada o descartada no se re-ofrece.

REGLA DURA (regla 5 del propietario): una automatización procesal (is_procedural) SIEMPRE
pasa por aceptación humana; jamás se auto-activa. Al ejecutarse (p. ej. el aviso anticipado
de plazos) solo superficie fechas que el abogado ya fijó y lleva [VERIFICAR] — Mia no
calcula ni agenda términos. El generador de sugerencias solo PROPONE; crear queda en accept().
"""
from __future__ import annotations

import logging

from psycopg.types.json import Json

from ..db import pool
from . import blueprints

logger = logging.getLogger("mia.cron.suggestions")

# Tope de sugerencias pendientes: la lista nunca debe volverse un muro de avisos.
MAX_PENDING = 5


class AutomationService:
    """CRUD de automatizaciones activas del tenant (RLS). Crear = acto humano explícito."""

    async def create(self, tenant_id: str, blueprint_key: str, values: dict | None) -> dict:
        """Crea una automatización desde una plantilla, validando los valores.

        `fill_blueprint` valida y arma el spec (lanza BlueprintFillError si no cuadra).
        NO calcula ni agenda nada: persiste el spec; la ejecución la hace la vigilancia
        que lo lee (p. ej. el aviso de plazos usa la ventana configurada aquí)."""
        spec = blueprints.fill_blueprint(blueprint_key, values)   # valida (puede lanzar)
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "INSERT INTO automations (tenant_id, blueprint_key, kind, params, is_procedural) "
                "VALUES (%s::uuid, %s, %s, %s, %s) RETURNING id",
                (tenant_id, spec["blueprint_key"], spec["kind"], Json(spec["params"]),
                 spec["is_procedural"]),
            )).fetchone()
        return {"id": str(row[0]), **spec, "enabled": True}

    async def list_active(self, tenant_id: str) -> list[dict]:
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT id, blueprint_key, kind, params, is_procedural, enabled "
                "FROM automations WHERE enabled ORDER BY created_at",
            )).fetchall()
        return [
            {"id": str(r[0]), "blueprint_key": r[1], "kind": r[2], "params": r[3],
             "is_procedural": r[4], "enabled": r[5]}
            for r in rows
        ]

    async def delete(self, tenant_id: str, automation_id: str) -> bool:
        async with pool.tenant_connection(tenant_id) as conn:
            cur = await conn.execute(
                "DELETE FROM automations WHERE id = %s::uuid", (automation_id,))
        return cur.rowcount > 0

    async def active_of_kind(self, tenant_id: str, kind: str) -> list[dict]:
        """Automatizaciones activas de un tipo (para que la vigilancia las lea)."""
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT id, params, is_procedural FROM automations "
                "WHERE enabled AND kind = %s ORDER BY created_at",
                (kind,),
            )).fetchall()
        return [{"id": str(r[0]), "params": r[1], "is_procedural": r[2]} for r in rows]


class SuggestionService:
    """Propuestas consent-first: Mia propone, el abogado acepta/descarta. Máx MAX_PENDING."""

    def __init__(self, automations: AutomationService | None = None) -> None:
        self._automations = automations or AutomationService()

    async def propose(self, tenant_id: str, blueprint_key: str, params: dict,
                      dedup_key: str, rationale: str) -> dict | None:
        """Registra una sugerencia PENDIENTE. Devuelve None si:
        - ya existe una con ese dedup_key (LATCH: aceptada/descartada/pendiente no se re-ofrece), o
        - ya hay MAX_PENDING pendientes (se descarta la nueva; el abogado limpia primero).
        Nunca crea la automatización — solo propone (consent-first)."""
        async with pool.tenant_connection(tenant_id) as conn:
            # Serializa propose POR TENANT (revisión capa 2, MENOR 1 y 2): el lock de
            # transacción cierra la carrera entre el conteo del tope y el INSERT, y hace
            # que dos propose concurrentes del mismo dedup_key se ordenen — el segundo ve
            # la fila ya commiteada por el latch y devuelve None (sin chocar con el UNIQUE
            # ni propagar un 500). Se libera al cerrar la transacción. Colisión de hash =
            # a lo sumo serialización innecesaria entre dos tenants, inofensiva.
            # MANTENIMIENTO: la ausencia de 500 depende de que propose sea el ÚNICO
            # insertador y tome este lock PRIMERO. Si a futuro otra ruta inserta en
            # automation_suggestions, DEBE tomar este mismo lock o volvería el UniqueViolation.
            await conn.execute("SELECT pg_advisory_xact_lock(hashtext(%s))", (tenant_id,))
            existing = await (await conn.execute(
                "SELECT 1 FROM automation_suggestions WHERE dedup_key = %s", (dedup_key,),
            )).fetchone()
            if existing:
                return None                                  # latch: no re-ofrecer
            pending = await (await conn.execute(
                "SELECT count(*) FROM automation_suggestions WHERE status = 'pending'",
            )).fetchone()
            if pending[0] >= MAX_PENDING:
                logger.info("tenant %s: cola de sugerencias llena (%s); se descarta %s",
                            tenant_id, MAX_PENDING, dedup_key)
                return None
            row = await (await conn.execute(
                "INSERT INTO automation_suggestions "
                "  (tenant_id, blueprint_key, params, dedup_key, rationale) "
                "VALUES (%s::uuid, %s, %s, %s, %s) RETURNING id",
                (tenant_id, blueprint_key, Json(params or {}), dedup_key, rationale),
            )).fetchone()
        return {"id": str(row[0]), "blueprint_key": blueprint_key, "params": params or {},
                "dedup_key": dedup_key, "rationale": rationale, "status": "pending"}

    async def list_pending(self, tenant_id: str) -> list[dict]:
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                "SELECT s.id, s.blueprint_key, s.params, s.rationale FROM automation_suggestions s "
                "WHERE s.status = 'pending' ORDER BY s.created_at",
            )).fetchall()
        out = []
        for r in rows:
            bp = blueprints.get_blueprint(r[1])
            out.append({
                "id": str(r[0]), "blueprint_key": r[1], "params": r[2], "rationale": r[3],
                "nombre": bp.display_name if bp else r[1],
                "toca_plazo_procesal": bool(bp.is_procedural) if bp else False,
            })
        return out

    async def accept(self, tenant_id: str, suggestion_id: str) -> dict | None:
        """Acepta una sugerencia PENDIENTE → crea la automatización (acto humano explícito)
        y marca la sugerencia 'accepted'. None si no existe o ya no está pendiente."""
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT blueprint_key, params FROM automation_suggestions "
                "WHERE id = %s::uuid AND status = 'pending'",
                (suggestion_id,),
            )).fetchone()
            if not row:
                return None
            blueprint_key, params = row[0], row[1]
        # Crear (valida la plantilla). Si la validación falla, la sugerencia queda pendiente.
        automation = await self._automations.create(tenant_id, blueprint_key, params)
        async with pool.tenant_connection(tenant_id) as conn:
            await conn.execute(
                "UPDATE automation_suggestions SET status = 'accepted', resolved_at = now() "
                "WHERE id = %s::uuid AND status = 'pending'",
                (suggestion_id,),
            )
        return automation

    async def dismiss(self, tenant_id: str, suggestion_id: str) -> bool:
        """Descarta una sugerencia pendiente (queda LATCHEADA: no se re-ofrece)."""
        async with pool.tenant_connection(tenant_id) as conn:
            cur = await conn.execute(
                "UPDATE automation_suggestions SET status = 'dismissed', resolved_at = now() "
                "WHERE id = %s::uuid AND status = 'pending'",
                (suggestion_id,),
            )
        return cur.rowcount > 0


# ── generador de sugerencias (consent-first): observa el estado y PROPONE ────────
async def generate_suggestions(tenant_id: str, *, service: SuggestionService | None = None,
                               automations: AutomationService | None = None) -> list[dict]:
    """Recorre reglas basadas en EVIDENCIA del despacho y propone automatizaciones.

    Consent-first y anti-invención: solo propone sobre lo que existe de verdad (no inventa);
    NUNCA crea automatizaciones (eso es accept()). Devuelve las propuestas nuevas creadas.

    Regla 1 (procesal): si el despacho tiene recordatorios PROCESALES pendientes y NO tiene
    ya una automatización de aviso anticipado, propone la plantilla 'deadline_heads_up'
    (que el abogado debe aceptar — regla dura: los plazos no se automatizan solos)."""
    autos = automations or AutomationService()
    svc = service or SuggestionService(automations=autos)
    proposed: list[dict] = []

    async with pool.tenant_connection(tenant_id) as conn:
        n_proc = await (await conn.execute(
            "SELECT count(*) FROM reminders WHERE status = 'pending' AND is_procedural",
        )).fetchone()
    if n_proc and n_proc[0] > 0:
        ya = await autos.active_of_kind(tenant_id, "deadline_heads_up")
        if not ya:
            p = await svc.propose(
                tenant_id, "deadline_heads_up", {"dias_antes": 3},
                dedup_key="deadline_heads_up",
                rationale=("Tienes plazos procesales en tus recordatorios. Puedo avisarte "
                           "con anticipación (tú confirmas cada fecha; nunca calculo términos)."))
            if p:
                proposed.append(p)
    return proposed
