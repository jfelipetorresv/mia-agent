"""Mia · ingest.classify — clasificador de metadata de un documento recién ingerido.

Fase 1. INFIERE la ficha del documento (tipo, parte, folio/radicado, fecha) a partir de su
texto y su nombre de archivo, y separa por CONFIANZA (decisión del dueño 2026-07-18):

  · ALTA confianza (>= umbral) → el campo va a `alta`: la capa de persistencia lo escribe
    DIRECTO en la columna real de `documents` (tipo/parte/folio_radicado/fecha_documento,
    migración 045).
  · BAJA confianza (< umbral)  → el campo va a `sugerida`: la persistencia lo guarda en
    `documents.metadata_sugerida` (migración 046) para que el abogado lo confirme campo por
    campo desde la lista "Documentos por confirmar".

REGLAS DURAS que este módulo respeta:
  · AGNÓSTICO DE JURISDICCIÓN. `tipo` y `parte` son TEXTO LIBRE: el prompt NO ofrece ni exige
    un vocabulario cerrado de ningún país. Cada despacho/jurisdicción los puebla a su criterio.
  · NUNCA INVENTA. Un campo sin evidencia en el texto queda AUSENTE (ni en `alta` ni en
    `sugerida`), nunca con un valor rellenado.
  · TRIAJE, no juicio jurídico. Clasificar metadata es barato y va a la cadena AUXILIAR (Haiku
    local en 'soberano'), task='doc_classification' (ver agent/llm.py, junto a curator_conflict).
    El juicio jurídico sustantivo NUNCA corre en el modelo local; esto no lo es.
  · FAIL-SOFT ABSOLUTO. Cualquier excepción (modelo caído, JSON roto, DB inaccesible) se loguea
    y se devuelve un resultado vacío o parcial. JAMÁS propaga: un clasificador opcional no puede
    romper la ingesta. El documento simplemente queda sin metadata.
  · `fecha_documento` FIDEDIGNA. Si el documento YA tiene fecha (p. ej. matter_mail.py la fijó
    desde la cabecera del correo, dato fidedigno), NO se pisa: se omite del resultado.

Se invoca vía `call_llm(task='doc_classification')` (síncrono) envuelto en
`asyncio.to_thread` y bajo la política de modelo del tenant (`llm.tenant_model_policy`).
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import re
from datetime import date, datetime
from typing import Any

from ..agent import llm

logger = logging.getLogger("mia.ingest.classify")

# Umbral por campo: confianza >= este valor => ALTA (columna real); si no => SUGERENCIA.
# Configurable por env (default 0.7). Se puede sobre-escribir por llamada con `min_confianza`.
MIN_CONFIANZA = float(os.getenv("MIA_CLASSIFY_MIN_CONFIANZA", "0.7"))

# Cuánto texto del documento ve el clasificador. El tipo/parte/radicado/fecha viven casi
# siempre en la cabecera/primera página; no hace falta (ni conviene, por costo) mandar todo.
_MAX_CHARS = int(os.getenv("MIA_CLASSIFY_MAX_CHARS", "6000"))

# Campos que se extraen. Orden estable (afecta solo la presentación del prompt).
_FIELDS = ("tipo", "parte", "folio_radicado", "fecha_documento")

_JSON_OBJ = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json(text: str) -> dict | None:
    """Extrae el objeto JSON de la respuesta. Tolera ```json … ``` y prosa alrededor (los
    modelos pequeños de 'soberano' la añaden). None si no hay JSON legible."""
    if not text:
        return None
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj
    except (ValueError, TypeError):
        pass
    m = _JSON_OBJ.search(text)
    if m:
        try:
            obj = json.loads(m.group(0))
            if isinstance(obj, dict):
                return obj
        except (ValueError, TypeError):
            return None
    return None


def _clamp_conf(v: Any) -> float:
    """Confianza a float en [0, 1]. Cualquier cosa rara => 0.0 (irá a sugerencia, no a alta)."""
    try:
        f = float(v)
    except (TypeError, ValueError):
        return 0.0
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return f


def _clean_str(v: Any) -> str:
    """Valor textual normalizado; '' si vacío/None/placeholder. NUNCA inventa: un valor vacío o
    un marcador tipo 'null'/'n/a' se trata como AUSENCIA de evidencia."""
    if v is None:
        return ""
    s = str(v).strip()
    if not s or s.lower() in {"null", "none", "n/a", "na", "-", "desconocido", "sin datos"}:
        return ""
    return s


def _norm_fecha(v: Any) -> str:
    """Normaliza una fecha a 'YYYY-MM-DD' si es parseable; '' si no. Sin invención de partes
    faltantes: un texto que no es una fecha ISO clara se descarta (queda ausente)."""
    s = _clean_str(v)
    if not s:
        return ""
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%Y/%m/%d"):
        try:
            return datetime.strptime(s[:10] if fmt == "%Y-%m-%d" else s, fmt).date().isoformat()
        except ValueError:
            continue
    # Último intento: ISO con hora ('2026-07-19T...').
    try:
        return date.fromisoformat(s[:10]).isoformat()
    except ValueError:
        return ""


def _build_messages(text: str, filename: str) -> list[dict]:
    """Prompt de extracción estructurada JSON, AGNÓSTICO de jurisdicción. Pide por cada campo un
    valor y una confianza 0..1; deja claro que un campo sin evidencia va vacío (no se inventa)."""
    system = (
        "Eres un clasificador de metadata de documentos. Recibes el nombre de archivo y el "
        "comienzo del texto de UN documento y extraes cuatro datos, cada uno con tu nivel de "
        "confianza. NO interpretas el fondo del documento ni das opinión jurídica: solo "
        "identificas datos que estén presentes en el texto.\n"
        "Campos:\n"
        "- \"tipo\": qué CLASE de documento es, en las palabras que usa el propio documento "
        "(por ejemplo el encabezado o el título). Es TEXTO LIBRE: no elijas de una lista fija "
        "ni traduzcas a categorías de ningún país o sistema legal. Si el documento se llama a "
        "sí mismo de cierta forma, usa esa forma.\n"
        "- \"parte\": la parte, persona u organización principal a la que se refiere o que "
        "firma el documento, tal como aparece. TEXTO LIBRE, sin categorías predefinidas.\n"
        "- \"folio_radicado\": número de radicado, expediente, folio o referencia que "
        "identifique el documento, si aparece literalmente.\n"
        "- \"fecha_documento\": la fecha propia del documento (no la de hoy), en formato "
        "YYYY-MM-DD, si aparece.\n"
        "REGLAS:\n"
        "1. Extrae SOLO lo que esté respaldado por el texto. Si un dato NO aparece o no estás "
        "seguro de cuál es, deja su \"valor\" como cadena vacía \"\" y su \"confianza\" baja. "
        "JAMÁS inventes ni deduzcas un valor que el texto no muestra.\n"
        "2. \"confianza\" (0.0 a 1.0) es cuán seguro estás de que ese valor es correcto y está "
        "de verdad en el documento.\n"
        "3. Responde ÚNICAMENTE un objeto JSON, sin texto alrededor, con esta forma exacta:\n"
        "{\"tipo\": {\"valor\": \"\", \"confianza\": 0.0}, "
        "\"parte\": {\"valor\": \"\", \"confianza\": 0.0}, "
        "\"folio_radicado\": {\"valor\": \"\", \"confianza\": 0.0}, "
        "\"fecha_documento\": {\"valor\": \"\", \"confianza\": 0.0}}"
    )
    user = f"NOMBRE DE ARCHIVO: {filename or '(sin nombre)'}\n\nTEXTO DEL DOCUMENTO:\n{text[:_MAX_CHARS]}"
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


async def _existing_fecha(tenant_id: str, document_id: str) -> bool:
    """True si el documento YA tiene `fecha_documento` (no debe pisarse). Cualquier fallo de DB
    => False (no bloquea la clasificación; en el peor caso la persistencia protege con COALESCE)."""
    try:
        from ..db import pool  # import diferido (mismo criterio que agent/llm.py)

        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT fecha_documento FROM documents WHERE id = %s::uuid",
                (document_id,),
            )).fetchone()
        return bool(row and row[0] is not None)
    except Exception:  # noqa: BLE001 — un fallo de DB no debe tumbar la clasificación
        logger.exception("classify: no se pudo leer fecha_documento del doc %s", document_id)
        return False


async def classify_document(
    tenant_id: str,
    document_id: str,
    text: str,
    filename: str,
    origin: str,
    *,
    min_confianza: float | None = None,
) -> dict:
    """Infiere la metadata de un documento y la separa por confianza.

    Devuelve SIEMPRE (fail-soft) un dict con dos claves:
      {
        "alta":     {campo: valor, ...},                      # >= umbral → columna real
        "sugerida": {campo: {"valor": valor, "confianza": c}} # < umbral  → metadata_sugerida
      }
    Un campo sin evidencia no aparece en ninguna de las dos. Cualquier excepción se loguea y se
    devuelve {"alta": {}, "sugerida": {}} (o el parcial ya calculado): NUNCA propaga.

    `origin` es informativo (upload/folder/drive/mail/text-plain); no cambia la lógica salvo por
    `fecha_documento`, que además se protege consultando si el documento ya la tiene fijada.
    """
    result: dict[str, dict] = {"alta": {}, "sugerida": {}}
    umbral = MIN_CONFIANZA if min_confianza is None else float(min_confianza)

    body = (text or "").strip()
    if not body:
        # Sin texto no hay nada que clasificar (p. ej. un binario sin OCR). No es un error.
        return result

    # ¿La fecha ya está fijada (dato fidedigno del correo, etc.)? Si sí, no la tocamos.
    fecha_ya_fijada = await _existing_fecha(tenant_id, document_id)

    try:
        messages = _build_messages(body, filename)
        async with llm.tenant_model_policy(tenant_id):
            resp = await asyncio.to_thread(llm.call_llm, messages, task="doc_classification")
        raw = (resp.choices[0].message.content or "").strip()
    except Exception:  # noqa: BLE001 — el modelo/gateway falló: fail-soft, sin metadata
        logger.exception("classify: el clasificador falló para el doc %s (origin=%s)",
                         document_id, origin)
        return result

    parsed = _parse_json(raw)
    if not isinstance(parsed, dict):
        logger.warning("classify: respuesta no parseable para el doc %s; queda sin metadata",
                       document_id)
        return result

    for campo in _FIELDS:
        if campo == "fecha_documento" and fecha_ya_fijada:
            continue  # no se pisa una fecha ya establecida (fidedigna)
        entry = parsed.get(campo)
        if not isinstance(entry, dict):
            continue
        if campo == "fecha_documento":
            valor = _norm_fecha(entry.get("valor"))
        else:
            valor = _clean_str(entry.get("valor"))
        if not valor:
            continue  # sin evidencia → ausente (nunca se inventa)
        conf = _clamp_conf(entry.get("confianza"))
        if conf >= umbral:
            result["alta"][campo] = valor
        else:
            result["sugerida"][campo] = {"valor": valor, "confianza": round(conf, 2)}

    return result
