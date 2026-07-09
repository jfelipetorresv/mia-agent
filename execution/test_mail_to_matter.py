"""
Mia · test_mail_to_matter.py — gate de la Fase 2 "correos del caso → expediente".

El abogado BUSCA correos en su buzón conectado y ELIGE cuáles vincular a un expediente; al
vincularlos, cuerpo + adjuntos entran a documents + chunks (origin='mail') por el pipeline de
ingesta, idempotentes por huella. Consent-first: nada se importa solo.

Verifica OFFLINE (buzón doblado, sin red) contra la DB REAL (documents/chunks + RLS), en el
estilo de test_matter_folder.py (TestClient + JWT) y test_mailbox.py (dobles inyectados):

  · búsqueda une resultados de DOS proveedores y mapea la forma común (id/asunto/remitente/…)
  · vincular ingiere el CUERPO + un adjunto Word (.docx) y otro de texto → filas origin='mail'
    con chunks + embedding presente (embeddings stub)
  · dedupe: vincular el MISMO correo dos veces → 'ya estaba en el expediente'
  · adjunto no soportado (.exe) y adjunto gigante (>20 MB) → skipped con motivo en llano
  · tope de 20 correos por llamada → 422
  · expediente de OTRO despacho → 404 (aislamiento)
  · sin cuenta conectada → 503 en llano
  · RLS: los documentos vinculados quedan visibles SOLO para su despacho
  · §G: los textos que ve el abogado no llevan jerga técnica

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_mail_to_matter.py
"""
from __future__ import annotations

import asyncio
import io
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

from mia import config, embeddings                       # noqa: E402
from mia.db import pool                                   # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── embeddings stub (sin red): vector(EMBED_DIM) determinista ────────────────────
def _fake_embed(texts):
    return [[0.01 * (i + 1) for _ in range(config.EMBED_DIM)] for i, _ in enumerate(texts)]


embeddings.embed_texts = _fake_embed

FORBIDDEN = ("oauth", "provider", "tenant", "graph", "mime", "token", "scope",
             "hitl", "langgraph", "pgvector", "chunk", "embedding")

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)

CAP = 20 * 1024 * 1024


# ── fixtures de adjuntos reales (Word .docx / texto) para ejercitar extract_text ──
def make_docx(text: str) -> bytes:
    import docx
    d = docx.Document()
    d.add_paragraph(text)
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


# ── dobles del buzón (sin red ni cuentas reales) ─────────────────────────────────
class FakeConnector:
    """Un conector de proveedor doblado: sirve búsqueda + metadata + cuerpo + adjuntos
    desde datos en memoria (misma interfaz que Microsoft/GoogleMailbox de la Fase 2)."""

    def __init__(self, provider: str, results=None, messages=None):
        self.provider = provider
        self._results = results or []
        self._messages = messages or {}   # id -> {meta, body, attachments}

    async def search_messages(self, query, max_results=25):
        return list(self._results)

    async def fetch_meta(self, message_id):
        return self._messages[message_id]["meta"]

    async def fetch_body(self, message_id):
        return self._messages[message_id]["body"]

    async def fetch_attachments(self, message_id):
        return list(self._messages[message_id].get("attachments", []))


class FakeMailbox:
    """Doble de MailboxService: un dict {provider: conector} de cuentas conectadas."""

    def __init__(self, conns: dict):
        self._conns = conns

    async def connector_for(self, tid, provider=None):
        if provider:
            return self._conns.get(provider)
        return next(iter(self._conns.values()), None)

    async def connectors_for(self, tid):
        return dict(self._conns)

    async def aclose(self):
        pass


# ── dobles de HTTP (estilo test_mailbox: get/post async por subcadena de URL) ────
class FakeResp:
    def __init__(self, status, payload):
        self.status_code = status
        self._payload = payload

    def json(self):
        return self._payload


class RouteHttp:
    def __init__(self, routes: dict):
        self._routes = routes

    async def get(self, url, params=None, headers=None):
        for key in sorted(self._routes, key=len, reverse=True):
            if key in url:
                return self._routes[key]
        return FakeResp(404, {})


async def provider_checks() -> None:
    """Mapeo REAL del JSON de cada proveedor a la forma común / bytes de adjunto, con HTTP
    doblado (sin red) — mismo estilo que test_mailbox.fetch_body."""
    import base64

    from mia.connectors.mailbox import providers
    from mia.connectors.mailbox.base import OAuthCreds

    # ── Microsoft (Graph) ──
    file_bytes = b"%PDF-1.4 contenido de prueba"
    ms_http = RouteHttp({
        "/me/messages/m1/attachments": FakeResp(200, {"value": [
            {"@odata.type": "#microsoft.graph.fileAttachment", "name": "poliza.pdf",
             "contentType": "application/pdf", "size": len(file_bytes),
             "contentBytes": base64.b64encode(file_bytes).decode()},
            {"@odata.type": "#microsoft.graph.itemAttachment", "name": "correo-adjunto"},
        ]}),
        "/me/messages/m1": FakeResp(200, {
            "subject": "Traslado", "from": {"emailAddress": {"name": "Juzgado", "address": "j@r.gov.co"}},
            "receivedDateTime": "2026-07-02T10:00:00Z"}),
        "/me/messages": FakeResp(200, {"value": [
            {"id": "m1", "subject": "Traslado", "hasAttachments": True,
             "bodyPreview": "Se corre traslado",
             "from": {"emailAddress": {"name": "Juzgado", "address": "j@r.gov.co"}},
             "receivedDateTime": "2026-07-02T10:00:00Z"}]}),
    })
    ms = providers.MicrosoftMailbox(OAuthCreds("microsoft", "AT"), http=ms_http)
    res = await ms.search_messages("traslado")
    check("Microsoft.search_messages: JSON de Graph → forma común",
          len(res) == 1 and res[0]["id"] == "m1" and res[0]["sender"] == "j@r.gov.co"
          and res[0]["has_attachments"] is True and res[0]["snippet"] == "Se corre traslado"
          and res[0]["date"] is not None)
    meta = await ms.fetch_meta("m1")
    check("Microsoft.fetch_meta: asunto/remitente/fecha del correo",
          meta["subject"] == "Traslado" and meta["sender"] == "j@r.gov.co")
    atts = await ms.fetch_attachments("m1")
    check("Microsoft.fetch_attachments: fileAttachment se decodifica; itemAttachment se ignora",
          len(atts) == 1 and atts[0]["filename"] == "poliza.pdf" and atts[0]["data"] == file_bytes)

    # ── Google (Gmail) ──
    att_bytes = b"contenido del adjunto gmail"
    g_http = RouteHttp({
        "/users/me/messages/gm1/attachments/att1": FakeResp(200, {
            "data": base64.urlsafe_b64encode(att_bytes).decode()}),
        "/users/me/messages/gm1": FakeResp(200, {
            "id": "gm1", "snippet": "adjunto mis notas", "internalDate": "1751457600000",
            "payload": {"headers": [
                {"name": "From", "value": "Ana Ruiz <ana@cliente.co>"},
                {"name": "Subject", "value": "Consulta"}],
                "parts": [
                    {"mimeType": "text/plain", "body": {"data": ""}, "filename": ""},
                    {"mimeType": "application/pdf", "filename": "notas.pdf",
                     "body": {"attachmentId": "att1", "size": len(att_bytes)}}]}}),
        "/users/me/messages": FakeResp(200, {"messages": [{"id": "gm1"}]}),
    })
    g = providers.GoogleMailbox(OAuthCreds("google", "AT"), http=g_http)
    gres = await g.search_messages("notas")
    check("Google.search_messages: metadata de Gmail → forma común (has_attachments por MIME)",
          len(gres) == 1 and gres[0]["id"] == "gm1" and gres[0]["sender"] == "ana@cliente.co"
          and gres[0]["sender_name"] == "Ana Ruiz" and gres[0]["has_attachments"] is True)
    gatts = await g.fetch_attachments("gm1")
    check("Google.fetch_attachments: recorre el MIME y descarga base64url del adjunto",
          len(gatts) == 1 and gatts[0]["filename"] == "notas.pdf" and gatts[0]["data"] == att_bytes)


def make_tenants() -> tuple[str, str]:
    with psycopg.connect(autocommit=True, **PG) as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A test mail') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test mail') RETURNING id").fetchone()[0]
    return str(a), str(b)


def make_matter(tenant_id: str, title: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO matters(tenant_id, title) VALUES(%s::uuid, %s) RETURNING id",
            (tenant_id, title)).fetchone()[0])


def drop_tenants(a: str, b: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([a, b],))


# Conteos directos (postgres es superusuario → ignora RLS): cuenta filas REALES por asunto.
# Se usan DENTRO del TestClient (el pool async del app corre en otro event loop; no se toca).
def sql_count_docs(matter_id: str, origin: str | None = None) -> int:
    q = "SELECT count(*) FROM documents WHERE matter_id=%s::uuid"
    args: list = [matter_id]
    if origin is not None:
        q += " AND origin=%s"
        args.append(origin)
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(q, tuple(args)).fetchone()[0]


def sql_chunks_with_embedding(matter_id: str) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM chunks ch JOIN documents d ON d.id=ch.document_id "
            "WHERE d.matter_id=%s::uuid AND d.origin='mail' AND ch.embedding IS NOT NULL",
            (matter_id,)).fetchone()[0]


# Conteo tenant-scoped (RLS aplica: mia_app NO es superusuario) — solo para la prueba de RLS.
async def count_docs_rls(tenant_id: str, matter_id: str, origin: str = "mail") -> int:
    async with pool.tenant_connection(tenant_id) as conn:
        return (await (await conn.execute(
            "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin=%s",
            (matter_id, origin))).fetchone())[0]


def api_checks(a: str, b: str, matter_a: str) -> None:
    import jwt
    from fastapi.testclient import TestClient
    from mia.api import main as main_mod
    from mia.api.routes import matter_mail

    token_a = jwt.encode({"tenant_id": a, "email": "abogado@a.co"},
                         config.JWT_SECRET, algorithm=config.JWT_ALG)
    token_b = jwt.encode({"tenant_id": b, "email": "abogado@b.co"},
                         config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth_a = {"Authorization": f"Bearer {token_a}"}
    auth_b = {"Authorization": f"Bearer {token_b}"}
    visible: list[str] = []

    def use_mailbox(conns: dict) -> None:
        matter_mail._make_mailbox_service = lambda: FakeMailbox(conns)

    # correo de Microsoft con cuerpo + 2 adjuntos (uno Word soportado, uno .exe no soportado)
    docx_bytes = make_docx("Cláusulas y coberturas de la póliza del expediente de prueba.")
    ms_msg = {
        "meta": {"subject": "Traslado de la demanda", "sender": "sec@ramajudicial.gov.co",
                 "sender_name": "Juzgado 5", "date": "2026-07-02T10:00:00+00:00"},
        "body": "Se corre traslado de la demanda. Adjunto la póliza y un ejecutable.",
        "attachments": [
            {"filename": "poliza.docx", "content_type": "application/docx",
             "data": docx_bytes, "size": len(docx_bytes)},
            {"filename": "virus.exe", "content_type": "application/octet-stream",
             "data": b"MZ...", "size": 5},
            {"filename": "gigante.pdf", "content_type": "application/pdf",
             "data": b"x", "size": CAP + 1},   # >20 MB: se omite sin descargar
        ],
    }
    g_msg = {
        "meta": {"subject": "Consulta del cliente", "sender": "ana@cliente.co",
                 "sender_name": "Ana Ruiz", "date": "2026-07-01T09:00:00+00:00"},
        "body": "Buenas tardes, adjunto mis notas.",
        "attachments": [
            {"filename": "notas.txt", "content_type": "text/plain",
             "data": "Notas del cliente sobre el caso.".encode("utf-8"), "size": 33},
        ],
    }

    ms_conn = FakeConnector("microsoft", results=[{
        "id": "m1", "subject": "Traslado de la demanda", "sender": "sec@ramajudicial.gov.co",
        "sender_name": "Juzgado 5", "date": "2026-07-02T10:00:00+00:00",
        "snippet": "Se corre traslado", "has_attachments": True}],
        messages={"m1": ms_msg})
    g_conn = FakeConnector("google", results=[{
        "id": "g1", "subject": "Consulta del cliente", "sender": "ana@cliente.co",
        "sender_name": "Ana Ruiz", "date": "2026-07-01T09:00:00+00:00",
        "snippet": "adjunto mis notas", "has_attachments": True}],
        messages={"g1": g_msg})

    with TestClient(main_mod.app) as client:
        # ── búsqueda: une resultados de DOS proveedores + forma común ──
        use_mailbox({"microsoft": ms_conn, "google": g_conn})
        r = client.get(f"/api/matters/{matter_a}/mail/search", headers=auth_a, params={"q": "demanda"})
        visible.append(r.text)
        res = r.json().get("resultados", []) if r.status_code == 200 else []
        provs = {x.get("provider") for x in res}
        shape_ok = all(
            set(x) >= {"id", "subject", "sender", "date", "snippet", "has_attachments", "provider"}
            for x in res)
        check("búsqueda: une resultados de las dos cuentas conectadas (2 correos)",
              r.status_code == 200 and len(res) == 2 and provs == {"microsoft", "google"})
        check("búsqueda: cada resultado trae la forma común (asunto/remitente/fecha/…)", shape_ok)

        # query vacía → 422
        r = client.get(f"/api/matters/{matter_a}/mail/search", headers=auth_a, params={"q": "  "})
        check("búsqueda: query vacía → 422 en llano", r.status_code == 422)
        visible.append(r.text)

        # sin cuenta conectada → 503
        use_mailbox({})
        r = client.get(f"/api/matters/{matter_a}/mail/search", headers=auth_a, params={"q": "x"})
        check("búsqueda: sin cuenta conectada → 503 en llano", r.status_code == 503)
        visible.append(r.text)

        # ── vincular: cuerpo + adjunto Word + skips ──
        use_mailbox({"microsoft": ms_conn, "google": g_conn})
        r = client.post(f"/api/matters/{matter_a}/mail/link", headers=auth_a,
                        json={"items": [{"provider": "microsoft", "message_id": "m1"}]})
        visible.append(r.text)
        payload = r.json() if r.status_code == 200 else {}
        added = payload.get("added", [])
        skipped = payload.get("skipped", [])
        skip_names = {s.get("name") for s in skipped}
        check("vincular: 200 con cuerpo + adjunto Word agregados (added=2)",
              r.status_code == 200 and len(added) == 2)
        check("vincular: adjunto no soportado (.exe) → omitido con motivo",
              "virus.exe" in skip_names)
        check("vincular: adjunto gigante (>20 MB) → omitido con motivo",
              "gigante.pdf" in skip_names)
        check("vincular: los motivos de omisión van en llano (sin jerga)",
              all(isinstance(s.get("reason"), str) and s["reason"] for s in skipped))

        # documents/chunks con origin='mail' y embedding presente
        check("vincular: 2 documentos origin='mail' (cuerpo + Word) en el expediente",
              sql_count_docs(matter_a, origin="mail") == 2)
        check("vincular: los documentos vinculados tienen fragmentos con embedding",
              sql_chunks_with_embedding(matter_a) >= 2)

        # ── dedupe: vincular el MISMO correo otra vez → 'already' ──
        r = client.post(f"/api/matters/{matter_a}/mail/link", headers=auth_a,
                        json={"items": [{"provider": "microsoft", "message_id": "m1"}]})
        visible.append(r.text)
        payload = r.json() if r.status_code == 200 else {}
        check("dedupe: re-vincular el mismo correo → 'ya estaba' (added=0, already=2)",
              r.status_code == 200 and len(payload.get("added", [])) == 0
              and len(payload.get("already", [])) == 2)
        check("dedupe: no se duplicaron documentos (siguen 2 origin='mail')",
              sql_count_docs(matter_a, origin="mail") == 2)

        # ── tope de 20 correos → 422 ──
        many = [{"provider": "microsoft", "message_id": f"x{i}"} for i in range(21)]
        r = client.post(f"/api/matters/{matter_a}/mail/link", headers=auth_a, json={"items": many})
        check("vincular: más de 20 correos en una llamada → 422", r.status_code == 422)
        visible.append(r.text)

        # ── expediente de OTRO despacho → 404 (aislamiento) ──
        r = client.get(f"/api/matters/{matter_a}/mail/search", headers=auth_b, params={"q": "x"})
        check("aislamiento: buscar en un expediente de otro despacho → 404", r.status_code == 404)
        r = client.post(f"/api/matters/{matter_a}/mail/link", headers=auth_b,
                        json={"items": [{"provider": "microsoft", "message_id": "m1"}]})
        check("aislamiento: vincular a un expediente de otro despacho → 404", r.status_code == 404)

        # ── vincular sin cuenta conectada → 503 ──
        use_mailbox({})
        r = client.post(f"/api/matters/{matter_a}/mail/link", headers=auth_a,
                        json={"items": [{"provider": "microsoft", "message_id": "m1"}]})
        check("vincular: sin cuenta conectada → 503 en llano", r.status_code == 503)
        visible.append(r.text)

    # ── RLS: B no ve los documentos vinculados de A ──
    async def rls_probe() -> tuple[int, int]:
        await pool.open_pool()
        try:
            seen_a = await count_docs_rls(a, matter_a)
            seen_b = await count_docs_rls(b, matter_a)
            return seen_a, seen_b
        finally:
            await pool.close_pool()

    seen_a, seen_b = asyncio.run(rls_probe())
    check("RLS: el despacho dueño ve sus 2 documentos vinculados", seen_a == 2)
    check("RLS: otro despacho NO ve los documentos vinculados (0)", seen_b == 0)

    # §G — sin jerga técnica en lo que ve el abogado
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    # "provider" es campo técnico legítimo de la API (no un texto para el abogado): se excluye.
    leaked = [w for w in leaked if w != "provider"]
    check(f"§G: textos sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def main() -> int:
    print("== Correos del caso → expediente (buscar + vincular) ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env — necesario para la DB real")
        return 1
    if not config.JWT_SECRET:
        print("  [FAIL] JWT_SECRET vacío en .env — necesario para la superficie HTTP")
        return 1

    import init_remote_sources
    init_remote_sources.apply()   # documents.origin admite 'mail' (migración 027)

    asyncio.run(provider_checks())   # mapeo del JSON de cada proveedor (offline, sin DB)

    a, b = make_tenants()
    matter_a = make_matter(a, "Asunto A (correos del caso)")
    try:
        api_checks(a, b, matter_a)
    finally:
        drop_tenants(a, b)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Correos del caso → expediente OK — buscar + vincular verificados.")
        return 0
    print("Correos del caso → expediente FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
