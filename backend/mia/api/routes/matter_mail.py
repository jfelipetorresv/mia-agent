"""Mia · api.routes.matter_mail — CORREOS DEL CASO → EXPEDIENTE (Fase 2 · fuentes remotas).

El abogado BUSCA correos en su buzón conectado (Microsoft 365 o Google Workspace) y ELIGE
cuáles vincular a un expediente. Al vincularlos, el cuerpo del correo y sus adjuntos entran
al expediente por el MISMO pipeline de ingesta que la carpeta vinculada (documents + chunks,
origin='mail'), idempotente por huella sha256.

  GET  /api/matters/{id}/mail/search?q=...&provider=...  → busca; sin provider, en TODAS las
                                                            cuentas conectadas (une resultados)
  POST /api/matters/{id}/mail/link  {items:[{provider, message_id}]}  → vincula (máx 20)

Consentimiento: BUSCAR y VINCULAR son acciones EXPLÍCITAS del abogado — su consentimiento es
la propia acción. Por eso NO exigen el opt-in de análisis de contenido en segundo plano
(`allow_content_analysis`), que gobierna la VIGILANCIA automática de la bandeja, no una
importación pedida a mano. (Sí depende de que la cuenta se haya conectado con permiso de
leer el contenido de los correos; si no, la vinculación lo reporta en llano.)

El CUERPO de un correo es contenido NO confiable: se guarda como TEXTO PLANO del caso (el
pipeline ya lo trata como datos, no como órdenes). NO se le aplica ningún paso que lo
interprete como instrucciones. Mia NUNCA calcula plazos: las fechas del correo se guardan
como texto, no se interpretan como términos procesales.

§G: nada de jerga técnica al abogado (no "OAuth", "provider", "MIME", "adjunto no soportado"
en crudo). El campo `provider` es técnico y viaja en la API; los TEXTOS van en llano.
"""
from __future__ import annotations

import hashlib
import logging
import re
import unicodedata

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from ... import embeddings
from ...connectors.mailbox.base import PROVIDERS
from ...connectors.mailbox.providers import _max_attachment_bytes
from ...connectors.mailbox.service import MailboxService
from ...db import pool
from ...ingest.extract import extract_text
from ...ingest.ingest import chunk_text
from ...observability import audit
from ._common import _is_uuid

router = APIRouter(prefix="/api", tags=["matter_mail"])
logger = logging.getLogger("mia.api.matter_mail")

MAX_LINK_ITEMS = 20  # máx. correos por llamada de vinculación (evita lotes desmedidos)

# Extensiones que el extractor de texto sabe leer (mismo criterio que la carpeta vinculada).
_SUPPORTED_SUFFIXES = (".pdf", ".docx", ".txt", ".md")


def _make_mailbox_service() -> MailboxService:
    """Fabrica el servicio de buzón (tokens + refresco + conector). Seam de inyección:
    los gates lo reemplazan por un doble sin red ni cuentas reales."""
    return MailboxService()


def _tenant(request: Request) -> str:
    tid = getattr(request.state, "tenant_id", None)
    if not tid:
        raise HTTPException(status_code=401, detail="Sin sesión activa")
    return tid


async def _assert_matter_visible(tenant_id: str, matter_id: str) -> None:
    """404 si el expediente no existe o es de OTRO despacho (RLS lo hace invisible).

    A diferencia de otras superficies (401), aquí un expediente ajeno responde 404: para
    quien busca correos, un asunto que no puede ver simplemente NO EXISTE."""
    if not _is_uuid(matter_id):
        raise HTTPException(status_code=404, detail="No encontré ese expediente.")
    async with pool.tenant_connection(tenant_id) as conn:
        row = await (await conn.execute(
            "SELECT 1 FROM matters WHERE id = %s::uuid", (matter_id,)
        )).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="No encontré ese expediente.")


def _slug(text: str, max_len: int = 40) -> str:
    """Asunto → fragmento seguro para nombre de archivo (sin tildes ni signos)."""
    norm = unicodedata.normalize("NFKD", text or "").encode("ascii", "ignore").decode()
    norm = re.sub(r"[^a-zA-Z0-9]+", "-", norm).strip("-").lower()
    return (norm[:max_len].strip("-")) or "sin-asunto"


def _body_filename(meta: dict) -> str:
    """Nombre legible del documento del cuerpo: correo-AAAA-MM-DD-<asunto>.txt."""
    fecha = (meta.get("date") or "")[:10] or "sin-fecha"
    return f"correo-{fecha}-{_slug(meta.get('subject') or '')}.txt"


def _body_text(meta: dict, body: str) -> str:
    """Texto que se guarda: encabezado De/Fecha/Asunto (para reconocerlo al citarlo) + cuerpo.
    Es contenido NO confiable guardado como DATO del caso — nunca se interpreta como orden."""
    de = meta.get("sender_name") or meta.get("sender") or "(desconocido)"
    if meta.get("sender") and meta.get("sender_name"):
        de = f"{meta['sender_name']} <{meta['sender']}>"
    encabezado = (
        f"De: {de}\n"
        f"Fecha: {meta.get('date') or '(sin fecha)'}\n"
        f"Asunto: {meta.get('subject') or '(sin asunto)'}\n"
        f"{'-' * 40}\n\n"
    )
    return encabezado + (body or "").strip()


class LinkItem(BaseModel):
    provider: str
    message_id: str = Field(min_length=1, max_length=2048)


class LinkBody(BaseModel):
    items: list[LinkItem] = Field(default_factory=list)


# ── búsqueda ─────────────────────────────────────────────────────────────────
@router.get("/matters/{matter_id}/mail/search")
async def search_mail(matter_id: str, request: Request, q: str = "", provider: str | None = None):
    """Busca correos en el buzón conectado y devuelve resultados en forma común (cada uno
    marcado con su `provider`). Sin `provider`, busca en TODAS las cuentas conectadas."""
    tid = _tenant(request)
    await _assert_matter_visible(tid, matter_id)
    if not q or not q.strip():
        raise HTTPException(status_code=422, detail="Escribe qué quieres buscar en tu correo.")
    if provider is not None and provider not in PROVIDERS:
        raise HTTPException(status_code=422, detail="No reconozco esa cuenta de correo.")

    svc = _make_mailbox_service()
    try:
        conns = await _connectors(svc, tid, provider)
        if not conns:
            raise HTTPException(
                status_code=503,
                detail="Conecta tu correo primero desde el Panel de control.")
        resultados: list[dict] = []
        for prov, conn in conns.items():
            try:
                msgs = await conn.search_messages(q.strip())
            except Exception:  # noqa: BLE001 — una cuenta que falla no tumba a las demás
                logger.warning("mail/search: falló la búsqueda en %s", prov)
                continue
            for m in msgs:
                resultados.append({**m, "provider": prov})
        return {"resultados": resultados}
    finally:
        await svc.aclose()


# ── vinculación (ingesta al expediente) ──────────────────────────────────────
@router.post("/matters/{matter_id}/mail/link")
async def link_mail(matter_id: str, body: LinkBody, request: Request):
    """Vincula los correos elegidos al expediente: por cada uno, cuerpo + adjuntos entran
    como documentos (origin='mail'), idempotentes por huella. Respuesta en llano para la UI."""
    tid = _tenant(request)
    await _assert_matter_visible(tid, matter_id)
    if not body.items:
        raise HTTPException(status_code=422, detail="Elige al menos un correo para vincular.")
    if len(body.items) > MAX_LINK_ITEMS:
        raise HTTPException(
            status_code=422,
            detail=f"Puedes vincular hasta {MAX_LINK_ITEMS} correos a la vez. "
                   f"Elige menos e inténtalo de nuevo.")

    added: list[str] = []
    already: list[str] = []
    skipped: list[dict] = []

    svc = _make_mailbox_service()
    try:
        conns = await _connectors(svc, tid, None)
        if not conns:
            raise HTTPException(
                status_code=503,
                detail="Conecta tu correo primero desde el Panel de control.")
        for item in body.items:
            conn = conns.get(item.provider)
            if conn is None:
                skipped.append({"name": "Un correo",
                                "reason": "No tienes esa cuenta de correo conectada."})
                continue
            try:
                await _link_one(tid, matter_id, conn, item.message_id, added, already, skipped)
            except Exception:  # noqa: BLE001 — un fallo en un correo (embeddings/DB) no aborta el lote
                logger.exception("mail/link: fallo inesperado vinculando un correo")
                skipped.append({"name": "Un correo",
                                "reason": "No pude agregar ese correo por un problema temporal. "
                                          "Intenta de nuevo más tarde."})
    finally:
        await svc.aclose()

    # Auditoría (CP-E1): SOLO metadatos de la acción — nunca asunto ni cuerpo.
    await audit.record(
        "mail_link", tenant_id=tid, user_email=getattr(request.state, "email", None),
        entity_type="matter", entity_id=matter_id,
        payload={"added": len(added), "already": len(already), "skipped": len(skipped),
                 "providers": sorted({i.provider for i in body.items})})

    return {"added": added, "skipped": skipped, "already": already}


async def _connectors(svc, tenant_id: str, provider: str | None) -> dict:
    """Conectores del tenant: uno (si se pidió `provider`) o todos los conectados."""
    if provider:
        conn = await svc.connector_for(tenant_id, provider)
        return {provider: conn} if conn is not None else {}
    return await svc.connectors_for(tenant_id)


async def _link_one(tenant_id: str, matter_id: str, conn, message_id: str,
                    added: list, already: list, skipped: list) -> None:
    """Vincula UN correo: trae metadata + cuerpo + adjuntos e ingiere lo soportado."""
    try:
        meta = await conn.fetch_meta(message_id)
        body_text = await conn.fetch_body(message_id)
        attachments = await conn.fetch_attachments(message_id)
    except Exception:  # noqa: BLE001 — §G: no exponer el error técnico al abogado
        logger.warning("mail/link: no se pudo traer un correo de %s",
                       getattr(conn, "provider", "?"))
        skipped.append({"name": "Un correo",
                        "reason": "No pude abrir ese correo. Puede que tu cuenta no tenga "
                                  "permiso para leer el contenido; vuelve a conectarla."})
        return

    provider = getattr(conn, "provider", "")
    asunto = meta.get("subject") or "(sin asunto)"

    # 1) el cuerpo → documento .txt legible (encabezado De/Fecha/Asunto + texto)
    filename = _body_filename(meta)
    full_text = _body_text(meta, body_text)
    await _ingest_document(
        tenant_id, matter_id, filename, "text/plain",
        full_text.encode("utf-8"), full_text,
        source_path=f"{provider}:{message_id}",
        display_name=f"Correo: {asunto}",
        added=added, already=already, skipped=skipped)

    # 2) cada adjunto soportado → documento propio
    cap = _max_attachment_bytes()
    for att in attachments:
        name = att.get("filename") or "adjunto"
        data = att.get("data") or b""
        size = int(att.get("size") or len(data))
        if size > cap or not data:
            skipped.append({"name": name,
                            "reason": "Ese archivo adjunto pesa más de 20 MB; no lo agregué."})
            continue
        if not name.lower().endswith(_SUPPORTED_SUFFIXES):
            skipped.append({"name": name,
                            "reason": "Ese tipo de archivo adjunto no lo puedo leer "
                                      "(uso PDF, Word, texto)."})
            continue
        try:
            text = extract_text(name, data)
        except Exception:  # noqa: BLE001 — adjunto ilegible: se omite en llano
            skipped.append({"name": name,
                            "reason": "No pude leer ese archivo adjunto; puede estar dañado."})
            continue
        await _ingest_document(
            tenant_id, matter_id, name, att.get("content_type") or None, data, text,
            source_path=f"{provider}:{message_id}/{name}",
            display_name=name, added=added, already=already, skipped=skipped)


async def _ingest_document(tenant_id: str, matter_id: str, filename: str, mime: str | None,
                           raw: bytes, text: str, *, source_path: str, display_name: str,
                           added: list, already: list, skipped: list) -> None:
    """Ingesta UN documento origin='mail' (dedupe por sha256): extrae→trocea→embebe→inserta.
    Molde de LocalFolderSync._ingest_matter_file, pero la clave de dedupe es la HUELLA del
    contenido (como la subida manual): re-vincular el mismo correo NO duplica nada."""
    sha256 = hashlib.sha256(raw).hexdigest()
    async with pool.tenant_connection(tenant_id) as conn:
        dup = await (await conn.execute(
            "SELECT 1 FROM documents WHERE matter_id=%s::uuid AND sha256=%s LIMIT 1",
            (matter_id, sha256))).fetchone()
    if dup:
        already.append(display_name)
        return
    chunks = chunk_text(text)
    if not chunks:
        skipped.append({"name": display_name,
                        "reason": "Ese correo o archivo no tenía texto para agregar."})
        return
    vectors = embeddings.embed_texts(chunks)
    async with pool.tenant_connection(tenant_id) as conn:
        doc_id = (await (await conn.execute(
            "INSERT INTO documents (tenant_id, matter_id, filename, mime, sha256, "
            "source_path, origin) VALUES (%s::uuid, %s::uuid, %s, %s, %s, %s, 'mail') "
            "RETURNING id",
            (tenant_id, matter_id, filename, mime, sha256, source_path))).fetchone())[0]
        for i, (content, vec) in enumerate(zip(chunks, vectors)):
            await conn.execute(
                "INSERT INTO chunks (tenant_id, document_id, ord, content, embedding) "
                "VALUES (%s::uuid, %s, %s, %s, %s)", (tenant_id, doc_id, i, content, vec))
    added.append(display_name)
