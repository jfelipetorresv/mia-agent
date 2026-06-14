"""
Mia · test_ux.py — gate de la superficie /api/* que consumen las 5 pantallas (Fase 3 backend).

Tests de integración ligeros con TestClient + JWT del tenant de prueba. El LLM y los embeddings
van MOCKEADOS (sin red). Documentos sintéticos (PDF con PyMuPDF, Word con python-docx). Verifica
que cada endpoint existe y responde, y que las respuestas no exponen jerga técnica (§G).

HALT: si falla, no se avanza (CLAUDE.md §G). Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_ux.py
"""
from __future__ import annotations
import asyncio
import io
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import init_profiles                                 # noqa: E402  (migración 007)
from mia import config, embeddings                   # noqa: E402
from mia.agent import llm                             # noqa: E402
from mia.agents.state import thread_id_for           # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red) ──────────────────────────────────────────────────────────
def _fake_embed(texts):
    return [[0.1] + [0.0] * (config.EMBED_DIM - 1) for _ in texts]


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    sysmsg = messages[0]["content"] if messages and isinstance(messages[0], dict) else ""
    if "Redacta el borrador" in sysmsg:
        content = "BORRADOR: contestación de la demanda. [VERIFICAR fecha del hecho]"
    elif "Incorpora al borrador" in sysmsg:
        content = "BORRADOR CORREGIDO con las indicaciones."
    else:
        content = "DIAGNÓSTICO: el eje es la caducidad de la acción."
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=20, total_tokens=32))


embeddings.embed_texts = _fake_embed
llm.call_llm = _fake_call_llm

PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "tool_call", "embedding")


def make_tenant() -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES('UX_TEST') RETURNING id").fetchone()[0])


def seed_proposal(tid: str) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute(
            "INSERT INTO feedback_proposals (tenant_id, proposal_type, suggested_content, rationale) "
            "VALUES (%s::uuid, 'flag_gap', 'Conviene reforzar la caducidad en reparación directa.', "
            "'Apareció dos veces en el periodo.')", (tid,))


def cleanup(tid: str, threads: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for th in threads:
            for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (th,))
        c.execute("DELETE FROM tenants WHERE id=%s", (tid,))


def make_pdf() -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((72, 72), "Contrato de prueba. Responsabilidad civil del Estado.")
    data = doc.tobytes()
    doc.close()
    return data


def make_docx() -> bytes:
    import docx
    d = docx.Document()
    d.add_paragraph("Documento Word de prueba. Cláusula de indemnización de perjuicios.")
    buf = io.BytesIO()
    d.save(buf)
    return buf.getvalue()


def run_checks(client, auth, tid) -> list[str]:
    visible_payloads = []        # respuestas que ve el abogado → §G
    threads = []

    # 1 · lista de asuntos
    r = client.get("/api/matters", headers=auth)
    check("GET /api/matters -> 200", r.status_code == 200)
    visible_payloads.append(r.text)

    # 2 · crear asunto
    r = client.post("/api/matters", headers=auth, json={"name": "Asunto de prueba", "description": "demanda"})
    check("POST /api/matters -> 201 con id", r.status_code == 201 and "id" in r.json())
    mA = r.json()["id"]
    mB = client.post("/api/matters", headers=auth, json={"name": "Asunto vacío"}).json()["id"]
    mC = client.post("/api/matters", headers=auth, json={"name": "Asunto rechazo"}).json()["id"]
    threads += [thread_id_for(tid, mA), thread_id_for(tid, mC)]

    # 3 · detalle de asunto
    r = client.get(f"/api/matters/{mA}", headers=auth)
    check("GET /api/matters/{id} -> 200", r.status_code == 200 and r.json()["id"] == mA)
    visible_payloads.append(r.text)

    # 4 · documentos (lista vacía)
    r = client.get(f"/api/matters/{mA}/documents", headers=auth)
    check("GET /api/matters/{id}/documents -> 200", r.status_code == 200 and r.json() == [])
    visible_payloads.append(r.text)

    # 5 · subir PDF
    r = client.post(f"/api/matters/{mA}/documents", headers=auth,
                    files={"file": ("contrato.pdf", make_pdf(), "application/pdf")})
    check("POST documents (PDF) -> 201", r.status_code == 201 and r.json().get("fragments", 0) >= 1)

    # 6 · subir Word
    r = client.post(f"/api/matters/{mA}/documents", headers=auth,
                    files={"file": ("clausula.docx", make_docx(),
                                    "application/vnd.openxmlformats-officedocument.wordprocessingml.document")})
    check("POST documents (Word) -> 201", r.status_code == 201 and r.json().get("fragments", 0) >= 1)
    visible_payloads.append(client.get(f"/api/matters/{mA}/documents", headers=auth).text)

    # 7 · chat → devuelve stream_url
    r = client.post(f"/api/matters/{mA}/chat", headers=auth, json={"message": "¿Caducó la acción?"})
    check("POST /api/matters/{id}/chat -> 200 con stream_url",
          r.status_code == 200 and "stream_url" in r.json())

    # 8 · stream SSE existe (consumimos el turno completo → deja el borrador en el checkpoint)
    with client.stream("GET", f"/api/matters/{mA}/stream", params={"message": "¿Caducó la acción?"},
                       headers=auth) as s:
        ct = s.headers.get("content-type", "")
        body = "".join(s.iter_text())
    check("GET /api/matters/{id}/stream -> text/event-stream",
          "text/event-stream" in ct and "awaiting_review" in body)

    # 9 · borrador disponible tras el turno
    r = client.get(f"/api/matters/{mA}/draft", headers=auth)
    check("GET /api/matters/{id}/draft -> 200 con borrador",
          r.status_code == 200 and r.json().get("draft", "").startswith("BORRADOR"))

    # 10 · borrador 404 cuando el asunto no tiene turno
    r = client.get(f"/api/matters/{mB}/draft", headers=auth)
    check("GET draft sin borrador -> 404", r.status_code == 404)

    # 11 · aprobar borrador
    with client.stream("POST", f"/api/matters/{mA}/draft/approve", headers=auth, json={}) as s:
        ok_approve = s.status_code == 200
        _ = "".join(s.iter_text())
    check("POST /api/matters/{id}/draft/approve -> 200", ok_approve)

    # 12 · rechazar borrador (asunto C: correr el turno y rechazar)
    with client.stream("GET", f"/api/matters/{mC}/stream", params={"message": "Otra consulta"},
                       headers=auth) as s:
        _ = "".join(s.iter_text())
    with client.stream("POST", f"/api/matters/{mC}/draft/reject", headers=auth,
                       json={"reason": "No aplica"}) as s:
        ok_reject = s.status_code == 200
        _ = "".join(s.iter_text())
    check("POST /api/matters/{id}/draft/reject -> 200", ok_reject)

    # 13 · perfil (get vacío + put)
    r = client.get("/api/profile", headers=auth)
    check("GET /api/profile -> 200", r.status_code == 200)
    r = client.put("/api/profile", headers=auth, json={
        "name": "Lexia Abogados", "jurisdiction": "colombia",
        "practice_areas": ["seguros", "contencioso"], "voice_adjectives": ["claro", "firme", "preciso"]})
    check("PUT /api/profile -> 200 con datos",
          r.status_code == 200 and r.json().get("name") == "Lexia Abogados")
    visible_payloads.append(client.get("/api/profile", headers=auth).text)

    # 14 · playbooks (crear + listar)
    client.post("/api/playbooks", headers=auth, json={
        "title": "Caducidad reparación directa", "summary": "cómputo del término de 2 años",
        "applies_when": "daño imputable al Estado", "content": "El término es de dos años…"})
    r = client.get("/api/playbooks", headers=auth)
    check("GET /api/playbooks -> 200", r.status_code == 200 and len(r.json()) >= 1)
    visible_payloads.append(r.text)

    # 15 · sugerencias de Mia
    r = client.get("/api/proposals", headers=auth)
    check("GET /api/proposals -> 200",
          r.status_code == 200 and len(r.json()) >= 1 and r.json()[0]["type"] == "Brecha detectada")
    visible_payloads.append(r.text)

    # 16 · dashboard
    r = client.get("/api/dashboard/stats", headers=auth)
    keys = {"matters_active", "documents_indexed", "playbooks_active", "proposals_pending",
            "scheduler_jobs", "cost_month_usd", "connectors"}
    check("GET /api/dashboard/stats -> 200 con todas las claves",
          r.status_code == 200 and keys.issubset(r.json().keys()))
    visible_payloads.append(r.text)

    # 17 · §G — sin jerga técnica en lo que ve el abogado
    blob = " ".join(visible_payloads).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)

    return threads


def main() -> int:
    print("== Fase 3 (backend) · superficie /api/* ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    init_profiles.apply()

    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    tid = make_tenant()
    seed_proposal(tid)
    token = jwt.encode({"tenant_id": tid}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth = {"Authorization": f"Bearer {token}"}
    threads: list[str] = []
    try:
        with TestClient(app) as client:
            threads = run_checks(client, auth, tid)
    finally:
        cleanup(tid, threads)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Superficie /api/* OK — Fase 3 (backend) verificada.")
        return 0
    print("Fase 3 (backend) FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
