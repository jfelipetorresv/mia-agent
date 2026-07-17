"""Mia · api.routes.gold_cases — Banco de oro (gold-set de calidad por-despacho, Fase 1).

El abogado, tras aprobar un asunto ejemplar, lo guarda como "caso de oro": Mia lo ANONIMIZA,
propone las claves (citas y conclusiones), y él revisa la versión anonimizada (con los datos
identificables que hayan quedado resaltados) y confirma. Nada entra al examen sin su confirmación.

Contrato (§G: todo en español llano, sin jerga técnica al abogado):
  POST /api/matters/{id}/gold-cases:draft  → anonimiza el asunto + propone rúbrica; guarda draft.
      Basta el matter_id: el backend LEE el asunto (traces + chunks), lo anonimiza y devuelve
      solo lo anonimizado. El body es opcional (si trae `message`, manda el cliente).
  GET  /api/gold-cases/{id}                → relee el caso completo (mismo shape que :draft).
  PATCH /api/gold-cases/{id}               → edita texto anonimizado + rúbrica (rechaza si trae PII).
  POST /api/gold-cases/{id}:confirm        → status='confirmed' (ÚNICA vía; descarta el mapa).
  GET  /api/gold-cases                     → lista el banco del despacho.
  DELETE /api/gold-cases/{id}              → retira un caso.

Confidencialidad: a la DB solo llega texto YA anonimizado + el HASH del mapa (nunca el mapa en
claro). Guardar un caso desde un asunto REAL reusa el candado de consentimiento del despacho
(`allow_eval_real_data`): el caso confirmado ya es anónimo, pero la CAPTURA toca datos reales.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request
from psycopg.types.json import Json
from pydantic import BaseModel, Field

from ...agent import prompt_builder
from ...agents import verification
from ...db import pool
from ...eval.harness import EvalConsentError, read_eval_policy
from ...security import anonymize
from ._common import assert_owns_matter, require_uuid

logger = logging.getLogger("mia.api.gold_cases")

router = APIRouter(tags=["gold_cases"])


def _tenant(request: Request) -> str:
    t = getattr(request.state, "tenant_id", None)
    if not t:
        raise HTTPException(status_code=401, detail="Sin contexto de tenant")
    return t


# Nota (decisión "enmascarar todo, siempre"): aquí VIVÍA `_tenant_jurisdictions`, que resolvía el
# pack del despacho para pasárselo al anonimizador. Ya no existe, y no debe volver: el anonimizador
# ya no acepta jurisdicción — enmascara con la base universal + TODOS los packs instalados + los
# respaldos por rol, siempre. Un despacho español atiende clientes colombianos, y el secreto
# profesional manda sobre la precisión del análisis. Al quitar la perilla desaparece toda la clase
# de fallos que consistía en resolverla mal (DB caída, 'generic' ambiguo, jurisdicción sin elegir).
# La jurisdicción SIGUE mandando en otras capas —el corpus, el wake-gate del correo—: ahí el error
# solo hace ruido, no filtra datos del cliente.


def _consent_guard(allow_real: bool) -> None:
    """Reusa el candado de datos reales del despacho: guardar un caso de oro desde un asunto real
    exige la misma autorización que correr el examen sobre datos reales. Puro y testeable."""
    if not allow_real:
        raise EvalConsentError(
            "Para guardar un caso de oro a partir de un asunto real necesitas autorizar el uso "
            "de datos reales en las pruebas de calidad (en Configuración).")


# ── modelos de request ────────────────────────────────────────────────────────
class _DocIn(BaseModel):
    filename: str = ""
    chunks: list[str] = Field(default_factory=list)


class DraftIn(BaseModel):
    """Body del `:draft`. TODO es opcional: sin `message`, el backend arma el caso leyendo el
    asunto (captura server-side). Con `message`, se respeta lo que mande el cliente — los
    llamadores viejos siguen funcionando igual."""
    title: str = ""
    message: str | None = None
    documents: list[_DocIn] | None = None
    gold_answer: str | None = None
    diagnosis: str = ""  # diagnóstico del turno (para proponer conclusiones clave); opcional


class Rubric(BaseModel):
    citas_clave: list[str] = Field(default_factory=list)
    conclusiones_clave: list[str] = Field(default_factory=list)


class PatchIn(BaseModel):
    title: str | None = None
    message: str | None = None
    documents: list[_DocIn] | None = None
    gold_answer: str | None = None
    rubric: Rubric | None = None


# ── proponer la rúbrica ────────────────────────────────────────────────────────
def _propose_rubric(gold_answer_anon: str, diagnosis_anon: str) -> dict:
    """Propone claves a partir del material YA anonimizado: las CITAS del borrador aprobado
    (escáner determinista de CP9) y las CONCLUSIONES del bloque de cierre del diagnóstico."""
    citas: list[str] = []
    seen: set[str] = set()
    for c in verification.scan_citations(gold_answer_anon or ""):
        cita = c["citation"].strip()
        key = verification._normalize(cita)
        if cita and key and key not in seen:
            seen.add(key)
            citas.append(cita)
    conclusiones: list[str] = []
    closing = prompt_builder.parse_diagnosis_closing(diagnosis_anon or "")
    if closing:
        for k in ("problema", "riesgo"):
            v = str(closing.get(k) or "").strip()
            if v:
                conclusiones.append(v)
    return {"citas_clave": citas, "conclusiones_clave": conclusiones}


class TitleWithPII(ValueError):
    """El título explícito que dio el abogado trae PII estructurada → se rechaza en llano."""


def _safe_title(explicit: str | None, anonymized_message: str) -> str:
    """Título del caso SIN filtrar PII (FIX 1). Si el abogado da un título explícito, se RECHAZA
    cuando trae PII estructurada (nunca se anonimiza en silencio un título que él quiso literal).
    Si no da título, el defecto sale del MENSAJE YA ANONIMIZADO —nunca del crudo— para no
    persistir nombres/cédulas en el título."""
    if explicit and explicit.strip():
        if anonymize.contains_pii(explicit):
            raise TitleWithPII()
        base = explicit
    else:
        base = anonymized_message or "Caso de oro"
    return base.strip()[:200] or "Caso de oro"


# Nota fija que acompaña a `spans_pii_restantes` en TODA vista del caso (draft y relectura):
# una lista vacía no es un certificado de limpieza. Constante única para que el abogado lea
# exactamente lo mismo las dos veces.
_NOTA_PII = ("Marcamos lo que detectamos; una lista vacía significa que no encontramos "
             "datos identificables, no que el caso esté garantizado 100% limpio.")


def _draft_aviso(ner_ran: bool, spans: list[dict]) -> str:
    """Aviso en llano para el abogado (FIX 3+4). SIEMPRE cauteloso cuando el NER no corrió o hay
    spans de SOSPECHA: nunca un "todo limpio" tranquilizador sin certeza."""
    sospechas = any(str(s.get("tipo", "")).startswith("sospecha") for s in spans)
    if not ner_ran:
        return ("Revisa con cuidado: no se pudieron ocultar automáticamente los nombres "
                "(faltó el motor local). Puede haber nombres o datos sin ocultar; "
                "bórralos antes de confirmar.")
    if sospechas:
        return ("Revisa con cuidado: puede haber nombres, empresas o direcciones sin ocultar. "
                "Bórralos antes de confirmar.")
    return ("Revisa la versión anonimizada antes de confirmar. Solo marcamos lo que detectamos; "
            "que no haya marcas no garantiza que el caso esté 100% limpio.")


# ── captura server-side: el material sale del asunto, no del navegador ────────
# Regla dura: el texto CRUDO del expediente no debe salir a la red para volver a entrar. Antes,
# la única forma de llamar al `:draft` era que el cliente reenviara el asunto entero SIN
# anonimizar; ahora el backend lo lee de la DB, lo anonimiza y al navegador solo le llega la
# versión ya anonimizada.
#
# De dónde sale cada pieza (investigado, no supuesto):
#   message      ← traces.input   del último turno que el abogado ACEPTÓ (013_traces_search.sql)
#   gold_answer  ← traces.output  de ese mismo turno (graph.py:1103 escribe `final`: el borrador
#                                 aprobado, o el ya corregido si el desenlace fue 'edited')
#   documents    ← chunks ⋈ documents del asunto (schema.sql:31-48)
#   diagnosis    ← NO EXISTE de forma durable: vive solo en el checkpoint de LangGraph, que
#                  `prepare_new_turn` borra al arrancar el turno siguiente (_common.py:110-111).
#                  Va vacío a propósito: sin diagnóstico, `_propose_rubric` propone las citas
#                  (que sí salen del borrador) y deja `conclusiones_clave` vacío para que el
#                  abogado las escriba en la revisión. NO se inventa un diagnóstico.
#
# `assistant_messages` NO sirve como fuente: no tiene matter_id — es el modo asistente libre,
# explícitamente "fuera de un asunto" (015_assistant.sql:5-11).

# Topes de captura. Un asunto puede tener cientos de chunks: anonimizar cada uno cuesta una
# llamada al NER local, y una pantalla con 300 fragmentos no se revisa de verdad. Se acota, pero
# NUNCA en silencio: lo que quede fuera se dice en `nota_captura`, en llano y con números.
MAX_CAPTURE_DOCS = 20
MAX_CAPTURE_CHUNKS = 60


class NoCaptureMaterial(ValueError):
    """El asunto no tiene un turno aceptado del que capturar. `str(e)` es apto para el abogado."""


async def _capture_from_matter(tenant_id: str, matter_id: str) -> dict:
    """Arma el material CRUDO del caso leyendo el asunto bajo RLS (`tenant_connection`: el
    material de otro despacho es invisible). Devuelve el bundle SIN anonimizar — el llamador lo
    pasa por `anonymize_bundle` antes de que nada salga hacia el cliente."""
    async with pool.tenant_connection(tenant_id) as conn:
        # Último turno ACEPTADO. 'edited' cuenta: el abogado se quedó con ese texto (es el
        # borrador que aprobó, ya corregido). 'rejected' NO: un borrador que rechazó no es oro.
        trace = await (await conn.execute(
            "SELECT input, output FROM traces "
            "WHERE matter_id = %s AND hitl_outcome IN ('approved', 'edited') "
            "ORDER BY COALESCE(trace_ts, created_at) DESC LIMIT 1",
            (str(matter_id),),
        )).fetchone()
        rows = await (await conn.execute(
            "SELECT d.id, d.filename, c.content FROM chunks c "
            "JOIN documents d ON d.id = c.document_id "
            "WHERE d.matter_id = %s::uuid ORDER BY d.created_at, c.ord",
            (matter_id,),
        )).fetchall()

    if not trace or not str(trace[0] or "").strip():
        raise NoCaptureMaterial(
            "Este asunto todavía no tiene un borrador que hayas aprobado, así que no hay nada "
            "que guardar como caso de oro. Resuelve el asunto y aprueba el borrador primero.")

    # Agrupa chunks por documento conservando el orden (d.created_at, c.ord).
    por_doc: dict[str, dict] = {}
    for doc_id, filename, content in rows:
        d = por_doc.setdefault(str(doc_id), {"filename": str(filename or ""), "chunks": []})
        d["chunks"].append(str(content or ""))
    documentos = list(por_doc.values())

    # Recorte explícito (nunca silencioso): se dice cuántos documentos y fragmentos quedaron
    # fuera, para que el abogado no crea que capturó el expediente entero.
    notas: list[str] = []
    if len(documentos) > MAX_CAPTURE_DOCS:
        notas.append(f"{len(documentos)} documentos: se tomaron los {MAX_CAPTURE_DOCS} primeros")
        documentos = documentos[:MAX_CAPTURE_DOCS]
    total_chunks = sum(len(d["chunks"]) for d in documentos)
    if total_chunks > MAX_CAPTURE_CHUNKS:
        restante = MAX_CAPTURE_CHUNKS
        recortados: list[dict] = []
        for d in documentos:
            if restante <= 0:
                break
            recortados.append({"filename": d["filename"], "chunks": d["chunks"][:restante]})
            restante -= len(recortados[-1]["chunks"])
        notas.append(f"{total_chunks} fragmentos de texto: se tomaron los {MAX_CAPTURE_CHUNKS} "
                     f"primeros")
        documentos = recortados

    nota_captura = ""
    if notas:
        nota_captura = ("Este asunto es grande (" + "; ".join(notas) + "). Lo que quedó fuera no "
                        "entra al examen: revisa que lo capturado baste, o completa el texto a mano.")
    return {
        "message": str(trace[0] or ""),
        "documents": documentos,
        "gold_answer": str(trace[1] or ""),
        # El diagnóstico del turno no se persiste en ninguna parte (ver la nota de arriba).
        "diagnosis": "",
        "nota_captura": nota_captura,
    }


# ── endpoints ──────────────────────────────────────────────────────────────────
@router.post("/matters/{matter_id}/gold-cases:draft")
async def draft_gold_case(matter_id: str, request: Request, body: DraftIn | None = None) -> dict:
    """Anonimiza el asunto resuelto y crea el borrador del caso de oro (status='draft').

    CAPTURA SERVER-SIDE (por defecto): basta con el `matter_id`. Sin `message` en el body, el
    backend lee el asunto de la DB, lo anonimiza y devuelve SOLO la versión anonimizada — el
    navegador nunca toca el texto crudo del expediente. Si el body trae `message`, se usa lo que
    mande el cliente (compatibilidad con los llamadores existentes).

    NO persiste PII: a la DB va solo lo anonimizado. Devuelve el texto anonimizado, la rúbrica
    propuesta y los datos identificables que hayan QUEDADO (para que el abogado los revise)."""
    tenant_id = _tenant(request)
    require_uuid(matter_id, "asunto")
    await assert_owns_matter(tenant_id, matter_id)
    body = body or DraftIn()

    # Candado de datos reales (reusado): capturar desde un asunto real exige autorización.
    # Va ANTES de leer nada del expediente: sin permiso no se toca el material.
    allow_real = (await read_eval_policy(tenant_id))["allow_real_data"]
    try:
        _consent_guard(allow_real)
    except EvalConsentError as e:
        raise HTTPException(status_code=403, detail=str(e))

    nota_captura = ""
    if body.message is None:
        # Captura server-side: el material sale del asunto (RLS), no del cliente.
        try:
            cap = await _capture_from_matter(tenant_id, matter_id)
        except NoCaptureMaterial as e:
            raise HTTPException(status_code=409, detail=str(e))
        message, docs, gold_answer = cap["message"], cap["documents"], cap["gold_answer"]
        diagnosis, nota_captura = cap["diagnosis"], cap["nota_captura"]
    else:
        message = body.message
        docs = [{"filename": d.filename, "chunks": d.chunks} for d in (body.documents or [])]
        gold_answer = body.gold_answer or ""
        diagnosis = body.diagnosis or ""

    bundle = anonymize.anonymize_bundle(message, docs, gold_answer)
    diagnosis_anon = (anonymize.anonymize_text(diagnosis).text if diagnosis else "")
    rubric = _propose_rubric(bundle["gold_answer"], diagnosis_anon)

    # FIX 1: el título por defecto sale del MENSAJE YA ANONIMIZADO (nunca del crudo); un título
    # explícito con PII estructurada se rechaza en llano.
    try:
        title = _safe_title(body.title, bundle["message"])
    except TitleWithPII:
        raise HTTPException(
            status_code=400,
            detail=("El título que escribiste contiene datos identificables (por ejemplo una "
                    "cédula, un NIT, un correo o un teléfono). Quítalos del título."))
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "INSERT INTO gold_cases "
            "(tenant_id, source_matter_id, title, message, documents, gold_answer, rubric, "
            " anon_map_ref, status) "
            "VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, %s, %s, 'draft') RETURNING id",
            (tenant_id, matter_id, title, bundle["message"], Json(bundle["documents"]),
             bundle["gold_answer"], Json(rubric), bundle["anon_map_hash"]),
        )).fetchone()

    aviso = _draft_aviso(bundle["ner_ran"], bundle["spans_pii_restantes"])
    return {
        "gold_case_id": str(row[0]),
        "status": "draft",
        # `title` viaja también aquí (antes faltaba) para que el shape del draft y el de
        # `GET /api/gold-cases/{id}` sean IDÉNTICOS y la pantalla use un solo tipo.
        "title": title,
        "message_anon": bundle["message"],
        "documents_anon": bundle["documents"],
        "gold_answer_anon": bundle["gold_answer"],
        "rubric_propuesta": rubric,
        "spans_pii_restantes": bundle["spans_pii_restantes"],
        "nota_pii": _NOTA_PII,
        # Qué quedó FUERA cuando el asunto era grande (vacío si se capturó todo o si el material
        # lo mandó el cliente). Se dice AQUÍ, en la única pantalla donde el abogado aún puede
        # completar el texto a mano antes de confirmar.
        "nota_captura": nota_captura,
        "aviso": aviso,
    }


def _scan_saved(message: str, documents: list[dict], gold_answer: str) -> list[dict]:
    """Recalcula `spans_pii_restantes` sobre el texto YA GUARDADO, igual que la verificación
    global de `anonymize_bundle`: mismo blob (pregunta + borrador + chunks unidos por saltos de
    línea), mismo par de escáneres (`scan_pii` estructurados + `scan_suspects` heurística), mismo
    orden por posición. No se persisten los spans: se recomputan, así la relectura refleja las
    ediciones del PATCH y no una foto vieja.

    `scan_pii`/`scan_suspects` NO aceptan jurisdicción (decisión "enmascarar todo, siempre"):
    pasársela revienta con TypeError."""
    todo = "\n".join([str(message or ""), str(gold_answer or "")]
                     + [str(c) for d in (documents or []) for c in (d.get("chunks") or [])])
    spans = anonymize.scan_pii(todo) + anonymize.scan_suspects(todo)
    spans.sort(key=lambda x: x["start"])
    return spans


@router.get("/gold-cases/{gold_case_id}")
async def get_gold_case(gold_case_id: str, request: Request) -> dict:
    """Relee un caso de oro COMPLETO — mismo shape que la respuesta de `:draft`, para que la
    pantalla use un solo tipo y el abogado pueda recargar a mitad de revisión sin perder la vista
    (el `:draft` solo devolvía esto una vez).

    CONFIDENCIALIDAD: devuelve SOLO texto ya anonimizado. NUNCA sale `anon_map` (marcador→valor
    real) — no se persiste en claro, no existe aquí — ni `anon_map_hash`: el hash es auditoría
    interna, no tiene nada que hacer en la pantalla.

    RLS: la lectura va bajo `tenant_connection`, así que el caso de otro despacho es INVISIBLE y
    cae por el mismo 404 que un id inexistente (no se distingue "no existe" de "no es tuyo")."""
    tenant_id = _tenant(request)
    require_uuid(gold_case_id, "caso")
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT id, status, title, message, documents, gold_answer, rubric "
            "FROM gold_cases WHERE id = %s::uuid",
            (gold_case_id,),
        )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró ese caso de oro.")
    _id, status, title, message, documents, gold_answer, rubric = row

    documents_anon = [{"filename": str(d.get("filename") or ""),
                       "chunks": [str(c) for c in (d.get("chunks") or [])]}
                      for d in (documents or []) if isinstance(d, dict)]
    rubric = rubric or {}
    spans = _scan_saved(str(message or ""), documents_anon, str(gold_answer or ""))
    # `ner_ran` no se persiste, así que no se puede afirmar que el motor local faltó en su día:
    # decirlo sería inventarle al abogado una falla que quizá no ocurrió. No hace falta, y no
    # relaja la cautela: si el NER hubiera fallado, los nombres seguirían crudos en el texto
    # guardado y `scan_suspects` los marca como 'sospecha_nombre' → `_draft_aviso` entra igual
    # por la rama "Revisa con cuidado". Sin sospechas, el aviso genérico ya advierte que no hay
    # garantía de limpieza; nunca dice "todo limpio".
    aviso = _draft_aviso(True, spans)
    return {
        "gold_case_id": str(_id),
        "status": str(status),
        "title": str(title or ""),
        "message_anon": str(message or ""),
        "documents_anon": documents_anon,
        "gold_answer_anon": str(gold_answer or ""),
        "rubric_propuesta": {
            "citas_clave": [str(c) for c in (rubric.get("citas_clave") or [])],
            "conclusiones_clave": [str(c) for c in (rubric.get("conclusiones_clave") or [])],
        },
        "spans_pii_restantes": spans,
        "nota_pii": _NOTA_PII,
        # Siempre "" al releer: el recorte de captura es una decisión del momento de capturar, y
        # lo guardado ES el caso. No se persiste (no hay dónde) — mismo tipo para la UI.
        "nota_captura": "",
        "aviso": aviso,
    }


@router.patch("/gold-cases/{gold_case_id}")
async def patch_gold_case(gold_case_id: str, body: PatchIn, request: Request) -> dict:
    """El abogado edita el texto anonimizado y/o la rúbrica. Segundo pase de PII: si el texto
    reeditado trae datos identificables, se RECHAZA (no se guarda) para no ensuciar el banco."""
    tenant_id = _tenant(request)
    require_uuid(gold_case_id, "caso")

    # Verificación de PII sobre todo texto entrante (incluye el título — FIX 1).
    textos: list[str] = []
    if body.title is not None:
        textos.append(body.title)
    if body.message is not None:
        textos.append(body.message)
    if body.gold_answer is not None:
        textos.append(body.gold_answer)
    if body.documents is not None:
        for d in body.documents:
            textos.extend(d.chunks)
    for t in textos:
        if anonymize.contains_pii(t):
            raise HTTPException(
                status_code=400,
                detail=("El texto todavía contiene datos identificables (por ejemplo una cédula, "
                        "un NIT, un radicado, un correo o un teléfono). Quítalos antes de guardar."))

    sets: list[str] = []
    params: list = []
    if body.title is not None:
        sets.append("title = %s"); params.append(body.title.strip()[:200])
    if body.message is not None:
        sets.append("message = %s"); params.append(body.message)
    if body.gold_answer is not None:
        sets.append("gold_answer = %s"); params.append(body.gold_answer)
    if body.documents is not None:
        sets.append("documents = %s")
        params.append(Json([{"filename": d.filename, "chunks": d.chunks} for d in body.documents]))
    if body.rubric is not None:
        sets.append("rubric = %s")
        params.append(Json({"citas_clave": body.rubric.citas_clave,
                            "conclusiones_clave": body.rubric.conclusiones_clave}))
    if not sets:
        raise HTTPException(status_code=400, detail="No hay cambios para guardar.")
    sets.append("updated_at = now()")

    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            f"UPDATE gold_cases SET {', '.join(sets)} WHERE id = %s::uuid RETURNING id, status",
            (*params, gold_case_id),
        )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró ese caso de oro.")
    return {"gold_case_id": str(row[0]), "status": str(row[1])}


@router.post("/gold-cases/{gold_case_id}:confirm")
async def confirm_gold_case(gold_case_id: str, request: Request) -> dict:
    """Confirma el caso (status='confirmed') — ÚNICA vía a 'confirmed', tras la revisión humana.
    Verificación final: si quedó PII estructurada, no deja confirmar. El mapa en claro nunca se
    persistió (solo su hash), así que 'descartarlo' es simplemente no tenerlo en DB."""
    tenant_id = _tenant(request)
    require_uuid(gold_case_id, "caso")
    async with pool.tenant_connection(tenant_id) as conn:
        cur = await conn.execute(
            "SELECT title, message, gold_answer, documents FROM gold_cases WHERE id = %s::uuid",
            (gold_case_id,))
        found = await cur.fetchone()
        if not found:
            raise HTTPException(status_code=404, detail="No se encontró ese caso de oro.")
        title, message, gold_answer, documents = found
        # FIX 1: el título también se re-escanea (pudo persistirse desde un draft anterior).
        blob = "\n".join([str(title or ""), str(message or ""), str(gold_answer or "")]
                         + [str(c) for d in (documents or []) for c in (d.get("chunks") or [])])
        if anonymize.contains_pii(blob):
            raise HTTPException(
                status_code=400,
                detail=("Aún quedan datos identificables en el caso. Edítalos antes de confirmarlo."))
        await conn.execute(
            "UPDATE gold_cases SET status = 'confirmed', updated_at = now() WHERE id = %s::uuid",
            (gold_case_id,))
    return {"gold_case_id": gold_case_id, "status": "confirmed"}


@router.get("/gold-cases")
async def list_gold_cases(request: Request) -> dict:
    """Lista el banco de oro del despacho (todos los estados), lo más reciente primero."""
    tenant_id = _tenant(request)
    async with pool.tenant_connection(tenant_id) as conn:
        rows = await (await conn.execute(
            "SELECT id, title, status, "
            "  jsonb_array_length(COALESCE(rubric->'citas_clave','[]'::jsonb)) AS n_citas, "
            "  jsonb_array_length(COALESCE(rubric->'conclusiones_clave','[]'::jsonb)) AS n_concl, "
            "  updated_at "
            "FROM gold_cases ORDER BY updated_at DESC",
        )).fetchall()
    casos = [{
        "gold_case_id": str(r[0]), "title": str(r[1] or ""), "status": str(r[2]),
        "n_citas_clave": int(r[3] or 0), "n_conclusiones_clave": int(r[4] or 0),
        "updated_at": r[5].isoformat() if r[5] else None,
    } for r in rows]
    return {"casos": casos, "total": len(casos)}


@router.delete("/gold-cases/{gold_case_id}")
async def delete_gold_case(gold_case_id: str, request: Request) -> dict:
    """Retira un caso del banco."""
    tenant_id = _tenant(request)
    require_uuid(gold_case_id, "caso")
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "DELETE FROM gold_cases WHERE id = %s::uuid RETURNING id", (gold_case_id,),
        )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No se encontró ese caso de oro.")
    return {"gold_case_id": gold_case_id, "eliminado": True}
