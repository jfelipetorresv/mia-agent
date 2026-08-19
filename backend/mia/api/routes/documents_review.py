"""Mia · api.routes.documents_review — "Documentos por confirmar" (Fase 1 · la DUDA del clasificador).

El clasificador de ingesta (ingest/classify.py) INFIERE la ficha de cada documento y separa por
confianza (decisión del dueño 2026-07-18): lo que tiene claro lo escribe DIRECTO en la columna real
(045: tipo/parte/folio_radicado/fecha_documento); lo que duda lo deja como SUGERENCIA en
`documents.metadata_sugerida` (046) para que el abogado lo confirme CAMPO POR CAMPO.

Esta superficie expone esa lista y su confirmación. Vive en su propia lista "Documentos por
confirmar" — NO se reutiliza la Pantalla 4 / feedback_proposals (decisión de diseño):

  GET  /api/matters/{id}/documents/pending          → documentos del asunto con dudas: por cada uno,
                                                       su nombre + campos en duda (valor sugerido por
                                                       Mia + confianza) + campos ya confirmados.
  POST /api/matters/{id}/documents/confirm           {document_id, campo, valor}
                                                       → mueve ESE campo de metadata_sugerida a la
                                                       columna real (valor = el sugerido aceptado o uno
                                                       corregido por el abogado) y lo quita de la duda.
                                                       Si ya no queda ninguna duda, el documento sale de
                                                       la lista (metadata_sugerida → NULL).

FUENTE DE VERDAD ÚNICA (decisión de la fase base, ver 046): NO hay flag/status aparte. Un documento
está "por confirmar" sii `metadata_sugerida IS NOT NULL`. Confirmar un campo = quitar su clave del
jsonb; confirmar el último (o que no queden claves) = poner la columna en NULL. Sin desincronización
posible entre un flag y el jsonb.

REGLAS DURAS que respeta:
  · AGNÓSTICO DE JURISDICCIÓN. `tipo` y `parte` son TEXTO LIBRE: aquí no se valida ni se acota a
    ningún vocabulario de ningún país. Solo se valida el NOMBRE del campo (allowlist de columnas del
    esquema), jamás su contenido.
  · COLUMNA POR LISTA BLANCA. El `campo` recibido se mapea a un literal de columna del código; JAMÁS
    se interpola en el SQL una cadena venida del cliente (misma disciplina que _persist_classification).
  · RLS del tenant + pertenencia del asunto (assert_owns_matter). Un documento de otro despacho o de
    otro expediente es invisible/no confirmable.
  · §G: mensajes en lenguaje llano, sin jerga técnica.
"""
from __future__ import annotations

import logging
from datetime import date

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ...db import pool
from ._common import assert_owns_matter, require_uuid

router = APIRouter(prefix="/api", tags=["documents_review"])
logger = logging.getLogger("mia.api.documents_review")

# Allowlist de campos confirmables → literal de columna REAL en `documents` (migración 045).
# El cliente manda una CLAVE de este dict; el valor (literal del código) es lo único que entra al SQL.
_CONFIRMABLE_COLS = {
    "tipo": "tipo",
    "parte": "parte",
    "folio_radicado": "folio_radicado",
    "fecha_documento": "fecha_documento",
}

# Longitud máxima defensiva de un valor de texto libre confirmado (evita blobs).
_MAX_VALOR_LEN = 2000


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


def _pendientes(metadata_sugerida: dict | None) -> list[dict]:
    """Convierte el jsonb {campo:{valor,confianza}} en una lista estable y ordenada para la UI.
    Fail-soft: cualquier entrada malformada se ignora (nunca rompe la lista)."""
    if not isinstance(metadata_sugerida, dict):
        return []
    out: list[dict] = []
    for campo in _CONFIRMABLE_COLS:  # orden estable, solo campos conocidos
        entry = metadata_sugerida.get(campo)
        if not isinstance(entry, dict):
            continue
        valor = entry.get("valor")
        if valor in (None, ""):
            continue
        conf = entry.get("confianza")
        try:
            conf = round(float(conf), 2)
        except (TypeError, ValueError):
            conf = None
        out.append({"campo": campo, "valor": str(valor), "confianza": conf})
    return out


def _confirmados(row: dict) -> list[dict]:
    """Campos de la ficha REAL ya poblados (columnas 045). Lo que el clasificador escribió con alta
    confianza o el abogado ya confirmó — se muestra como contexto de lo que Mia ya dio por bueno."""
    out: list[dict] = []
    for campo in _CONFIRMABLE_COLS:
        valor = row.get(campo)
        if valor in (None, ""):
            continue
        if isinstance(valor, date):
            valor = valor.isoformat()
        out.append({"campo": campo, "valor": str(valor)})
    return out


@router.get("/matters/{matter_id}/documents/pending")
async def list_pending_documents(matter_id: str, request: Request):
    """Documentos del asunto con metadata por confirmar (`metadata_sugerida IS NOT NULL`).

    Por cada documento: su nombre, los campos EN DUDA (valor sugerido por Mia + confianza) y los
    campos YA CONFIRMADOS (columnas reales pobladas). RLS del tenant + pertenencia del asunto."""
    tid = _tenant(request)
    require_uuid(matter_id, "expediente")
    await assert_owns_matter(tid, matter_id)

    async with pool.tenant_connection(tid) as conn:
        rows = await (await conn.execute(
            "SELECT id, filename, origin, created_at, tipo, parte, folio_radicado, "
            "fecha_documento, metadata_sugerida "
            "FROM documents "
            "WHERE matter_id = %s::uuid AND metadata_sugerida IS NOT NULL "
            "ORDER BY created_at DESC",
            (matter_id,),
        )).fetchall()

    documentos: list[dict] = []
    for r in rows:
        row = {
            "id": str(r[0]), "filename": r[1], "origin": r[2], "created_at": r[3],
            "tipo": r[4], "parte": r[5], "folio_radicado": r[6], "fecha_documento": r[7],
        }
        pendientes = _pendientes(r[8])
        if not pendientes:
            # jsonb no NULL pero sin campos válidos (p. ej. '{}' residual): nada que confirmar aquí.
            continue
        documentos.append({
            "id": row["id"],
            "nombre": row["filename"] or "(sin nombre)",
            "origin": row["origin"],
            "created_at": r[3].isoformat() if r[3] is not None else None,
            "pendientes": pendientes,
            "confirmados": _confirmados(row),
        })
    return {"documentos": documentos}


class ConfirmBody(BaseModel):
    document_id: str = Field(min_length=1, max_length=64)
    campo: str = Field(min_length=1, max_length=64)
    valor: str = Field(min_length=1, max_length=_MAX_VALOR_LEN)


@router.post("/matters/{matter_id}/documents/confirm")
async def confirm_document_field(matter_id: str, body: ConfirmBody, request: Request):
    """Confirma (o corrige) UN campo de un documento: lo escribe en su columna real y lo quita de la
    duda. `valor` = el sugerido aceptado o uno corregido por el abogado. Si tras quitarlo no queda
    ninguna duda, `metadata_sugerida` pasa a NULL y el documento sale de "Documentos por confirmar".

    Devuelve el estado resultante: campo confirmado, cuántas dudas quedan y si el documento ya salió
    de la lista. RLS del tenant + pertenencia del asunto + documento perteneciente a ESE expediente."""
    tid = _tenant(request)
    require_uuid(matter_id, "expediente")
    require_uuid(body.document_id, "documento")
    await assert_owns_matter(tid, matter_id)

    campo = body.campo.strip()
    columna = _CONFIRMABLE_COLS.get(campo)  # literal del código; NUNCA se interpola el input
    if columna is None:
        raise HTTPException(status_code=422, detail="No reconozco ese dato del documento.")

    valor_raw = body.valor.strip()
    if not valor_raw:
        raise HTTPException(status_code=422, detail="Escribe un valor para confirmar.")

    # fecha_documento es una columna date: se normaliza y valida (nunca se inventa una fecha ambigua).
    if columna == "fecha_documento":
        valor: object = _parse_fecha(valor_raw)
        if valor is None:
            raise HTTPException(
                status_code=422,
                detail="Esa fecha no la entiendo. Usa el formato año-mes-día (por ejemplo 2026-07-19).")
    else:
        valor = valor_raw

    # UPDATE atómico: escribe la columna real (literal blanco) y quita la clave del jsonb; si el jsonb
    # queda vacío, NULLIF lo deja en NULL (el documento sale de la lista). RETURNING para el estado.
    # `metadata_sugerida - %s` elimina la clave; `- campo` es texto → se pasa como parámetro seguro.
    async with pool.tenant_connection(tid) as conn:
        row = await (await conn.execute(
            f"UPDATE documents SET {columna} = %s, "
            "metadata_sugerida = NULLIF(COALESCE(metadata_sugerida, '{}'::jsonb) - %s, '{}'::jsonb) "
            "WHERE id = %s::uuid AND matter_id = %s::uuid "
            "RETURNING metadata_sugerida",
            (valor, campo, body.document_id, matter_id),
        )).fetchone()

    if row is None:
        # RLS/pertenencia: el documento no existe, es de otro despacho, o no es de este expediente.
        raise HTTPException(status_code=404, detail="No encontré ese documento en el expediente.")

    restante = row[0] if isinstance(row[0], dict) else {}
    pendientes = _pendientes(restante)
    logger.info("documents_review: campo '%s' confirmado en doc %s (quedan %d dudas)",
                campo, body.document_id, len(pendientes))
    return {
        "document_id": body.document_id,
        "campo": campo,
        "valor": valor.isoformat() if isinstance(valor, date) else valor,
        "pendientes": pendientes,
        "restantes": len(pendientes),
        "completado": len(pendientes) == 0,  # ya no quedan dudas → salió de "Documentos por confirmar"
    }


def _parse_fecha(s: str) -> date | None:
    """Normaliza una fecha confirmada a `date`. Acepta ISO y formatos comunes; None si no es
    inequívoca (NUNCA se inventa una fecha). Espejo de ingest.classify._norm_fecha para la
    confirmación manual — aquí se devuelve el objeto `date` para insertarlo tipado."""
    from datetime import datetime

    s = (s or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date()
        except ValueError:
            continue
    try:
        return date.fromisoformat(s[:10])
    except ValueError:
        return None
