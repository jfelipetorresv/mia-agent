"""
Mia · test_projects.py — gate del Bloque A (evolución de producto): PROYECTOS.

Ejercita, contra la DB real (migración 028), la superficie /api/matters con kind=
'asunto'|'proyecto' y los archivos que Mia produce dentro de un proyecto (outputs),
con el LLM y los embeddings MOCKEADOS (sin red). Molde calcado de
execution/test_matter_folder.py (event loop policy, .env, tenants propios con
limpieza en finally, TestClient + JWT). Cubre:

  1. Crear proyecto/asunto; GET /api/matters sin param NO trae proyectos; ?kind=proyecto
     los trae; ?kind=todos trae ambos; kind inválido al crear -> 422.
  2. Outputs: crear -> aparece en la lista y tiene chunks (consultable); dedupe por
     sha256 (segundo POST igual no duplica); descarga .docx con bytes y content-type
     correctos; outputs en un asunto -> 422; doc_id malformado -> 404; AISLAMIENTO:
     el tenant B no puede leer/descargar un output del tenant A (404).
  3. Turno de proyecto vía stream (LLM stubbeado): recibe 'reply' y NO deja
     pending_review=true; turno de asunto sigue emitiendo 'awaiting_review'
     (no-regresión del flujo HITL).
  4. Anti-jerga (§G) en todas las respuestas visibles al abogado.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_projects.py
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

# psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

# La consola de PowerShell es cp1252: forzar utf-8 evita un crash al imprimir.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import init_projects_multifolder                # noqa: E402  (migración 028)
from mia import config, embeddings               # noqa: E402
from mia.agent import llm                         # noqa: E402
from mia.agents.state import thread_id_for        # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red) ──────────────────────────────────────────────────────────
# H6: se capturan las llamadas (embeddings + LLM) para poder inspeccionar, turno a
# turno, exactamente qué texto vio cada uno — sin esto no hay forma de comprobar desde
# afuera que la memoria conversacional llegó al prompt del segundo turno.
_embed_calls: list[list[str]] = []
_llm_calls: list[list[dict]] = []


def _fake_embed(texts):
    _embed_calls.append(list(texts))
    return [[0.1] + [0.0] * (config.EMBED_DIM - 1) for _ in texts]


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    _llm_calls.append(messages)
    sysmsg = messages[0]["content"] if messages and isinstance(messages[0], dict) else ""
    if "PROYECTO" in sysmsg and "Tarea de este turno" in sysmsg:
        content = "RESPUESTA DEL PROYECTO: aquí tienes el análisis pedido. [VERIFICAR dato pendiente]"
    elif "Redacta el borrador" in sysmsg:
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

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "chunk", "embedding", "sync engine")


def make_tenant(name: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (name,)).fetchone()[0])


def cleanup(tenants: list[str], threads: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for th in threads:
            for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (th,))
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))


def count_chunks(doc_id: str) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM chunks WHERE document_id=%s::uuid", (doc_id,)).fetchone()[0]


def count_docs_by_sha(matter_id: str, sha256: str) -> int:
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute(
            "SELECT count(*) FROM documents WHERE matter_id=%s::uuid AND origin='mia' AND sha256=%s",
            (matter_id, sha256)).fetchone()[0]


def pending_review_of(matter_id: str) -> bool:
    with psycopg.connect(autocommit=True, **PG) as c:
        row = c.execute(
            "SELECT pending_review FROM matters WHERE id=%s::uuid", (matter_id,)).fetchone()
    return bool(row[0]) if row else False


def run_checks(client, auth_a, tid_a, auth_b, tid_b) -> list[str]:
    threads: list[str] = []
    visible: list[str] = []

    # ── 1 · kind en la creación y el listado ─────────────────────────────────
    r = client.post("/api/matters", headers=auth_a, json={"name": "Asunto normal"})
    check("crear sin kind -> 201 default 'asunto'",
          r.status_code == 201 and r.json().get("kind") == "asunto")
    asunto_id = r.json()["id"]
    visible.append(r.text)

    r = client.post("/api/matters", headers=auth_a,
                    json={"name": "Proyecto de prueba", "kind": "proyecto"})
    check("crear kind='proyecto' -> 201", r.status_code == 201 and r.json().get("kind") == "proyecto")
    proyecto_id = r.json()["id"]
    visible.append(r.text)
    threads += [thread_id_for(tid_a, asunto_id), thread_id_for(tid_a, proyecto_id)]

    r = client.post("/api/matters", headers=auth_a, json={"name": "Malo", "kind": "invalido"})
    check("crear kind inválido -> 422", r.status_code == 422)

    r = client.get("/api/matters", headers=auth_a)
    ids = {it["id"] for it in r.json()}
    check("GET /api/matters sin param NO trae el proyecto (compat)",
          asunto_id in ids and proyecto_id not in ids)
    visible.append(r.text)

    r = client.get("/api/matters", headers=auth_a, params={"kind": "proyecto"})
    ids_p = {it["id"] for it in r.json()}
    check("GET /api/matters?kind=proyecto trae SOLO el proyecto",
          proyecto_id in ids_p and asunto_id not in ids_p)
    visible.append(r.text)

    r = client.get("/api/matters", headers=auth_a, params={"kind": "todos"})
    ids_t = {it["id"] for it in r.json()}
    check("GET /api/matters?kind=todos trae ambos", asunto_id in ids_t and proyecto_id in ids_t)
    visible.append(r.text)

    r = client.get(f"/api/matters/{proyecto_id}", headers=auth_a)
    check("GET /api/matters/{id} de un proyecto expone kind='proyecto'",
          r.status_code == 200 and r.json().get("kind") == "proyecto")
    visible.append(r.text)

    # ── 2 · outputs (archivos producidos por Mia dentro del proyecto) ────────
    contenido = ("Memo de análisis: el proyecto reúne tres fuentes conectadas sobre "
                "la cláusula de indemnización de perjuicios. " * 5)
    r = client.post(f"/api/matters/{proyecto_id}/outputs", headers=auth_a,
                    json={"title": "Memo de análisis", "content": contenido})
    check("POST /outputs -> 201 con id", r.status_code == 201 and "id" in r.json())
    out_id = r.json()["id"]
    visible.append(r.text)

    r = client.get(f"/api/matters/{proyecto_id}/outputs", headers=auth_a)
    outs = r.json().get("outputs", [])
    check("GET /outputs -> aparece el archivo recién creado",
          r.status_code == 200 and any(o["id"] == out_id and o["title"] == "Memo de análisis"
                                       for o in outs))
    visible.append(r.text)
    check("el output tiene chunks (consultable después por el RAG)", count_chunks(out_id) >= 1)

    r_dup = client.post(f"/api/matters/{proyecto_id}/outputs", headers=auth_a,
                        json={"title": "Otro nombre, mismo contenido", "content": contenido})
    check("POST /outputs con el MISMO contenido -> 'duplicado' sin re-crear",
          r_dup.status_code == 200 and r_dup.json().get("status") == "duplicado"
          and r_dup.json().get("id") == out_id)
    visible.append(r_dup.text)
    import hashlib
    sha = hashlib.sha256(contenido.encode("utf-8")).hexdigest()
    check("dedupe: solo hay UNA fila con esa huella en el proyecto",
          count_docs_by_sha(proyecto_id, sha) == 1)

    r = client.get(f"/api/matters/{proyecto_id}/outputs/{out_id}.docx", headers=auth_a)
    check("GET /outputs/{id}.docx -> 200 con bytes y content-type correcto",
          r.status_code == 200 and len(r.content) > 0
          and "wordprocessingml.document" in r.headers.get("content-type", ""))

    # título/contenido fuera de rango -> 422 (Field min/max_length)
    r = client.post(f"/api/matters/{proyecto_id}/outputs", headers=auth_a,
                    json={"title": "", "content": "algo"})
    check("POST /outputs con title vacío -> 422", r.status_code == 422)

    # outputs en un ASUNTO -> 422 llano
    r = client.post(f"/api/matters/{asunto_id}/outputs", headers=auth_a,
                    json={"title": "No debería crearse", "content": "contenido cualquiera"})
    check("POST /outputs en un ASUNTO -> 422", r.status_code == 422)
    visible.append(r.text)
    r = client.get(f"/api/matters/{asunto_id}/outputs", headers=auth_a)
    check("GET /outputs en un ASUNTO -> 422", r.status_code == 422)

    # doc_id malformado -> 404
    r = client.get(f"/api/matters/{proyecto_id}/outputs/no-es-un-uuid.docx", headers=auth_a)
    check("GET /outputs/{doc_id malformado}.docx -> 404", r.status_code == 404)
    visible.append(r.text)

    # AISLAMIENTO: el tenant B, en SU PROPIO proyecto, no puede leer el output de A.
    r = client.post("/api/matters", headers=auth_b,
                    json={"name": "Proyecto de B", "kind": "proyecto"})
    proyecto_b = r.json()["id"]
    threads.append(thread_id_for(tid_b, proyecto_b))
    r = client.get(f"/api/matters/{proyecto_b}/outputs/{out_id}.docx", headers=auth_b)
    check("AISLAMIENTO: B no puede descargar el output de A -> 404", r.status_code == 404)
    visible.append(r.text)
    r = client.get(f"/api/matters/{proyecto_id}", headers=auth_b)
    check("AISLAMIENTO: B no ve el proyecto de A -> 401", r.status_code == 401)

    # ── 3 · turno de PROYECTO vía stream: 'reply', sin pending_review ────────
    with client.stream("GET", f"/api/matters/{proyecto_id}/stream",
                       params={"message": "Resume las fuentes conectadas"}, headers=auth_a) as s:
        ct = s.headers.get("content-type", "")
        body_p = "".join(s.iter_text())
    check("proyecto: stream -> text/event-stream", "text/event-stream" in ct)
    check("proyecto: stream emite 'reply' con la respuesta",
          '"reply":' in body_p and "RESPUESTA DEL PROYECTO" in body_p)
    check("proyecto: stream NUNCA emite 'awaiting_review'", "awaiting_review" not in body_p)
    check("proyecto: pending_review sigue false tras el turno", pending_review_of(proyecto_id) is False)
    visible.append(body_p)

    def _work_calls() -> list[list[dict]]:
        # work_node es el ÚNICO nodo del grafo de proyecto que llama al LLM (intake solo
        # embebe) — su system trae siempre "PROYECTO" + "Tarea de este turno" (prompt_builder).
        return [m for m in _llm_calls if m and isinstance(m[0], dict)
                and "PROYECTO" in m[0].get("content", "")
                and "Tarea de este turno" in m[0].get("content", "")]

    # ── H6: memoria conversacional CORTA del proyecto (turno 2 recuerda el turno 1) ──
    with client.stream("GET", f"/api/matters/{proyecto_id}/stream",
                       params={"message": "Ahora acórtalo"}, headers=auth_a) as s:
        body_p2 = "".join(s.iter_text())
    check("H6 turno 2: stream emite 'reply'", '"reply":' in body_p2)
    visible.append(body_p2)

    work_calls = _work_calls()
    check("H6: hay dos llamadas al LLM de 'work' (una por turno)", len(work_calls) == 2)
    turno2_user = work_calls[-1][1]["content"] if len(work_calls) == 2 else ""
    check("H6: el prompt del turno 2 trae el bloque de conversación reciente",
          "Conversación reciente de este proyecto" in turno2_user)
    check("H6: el turno 2 CONTIENE la reply del turno 1 (memoria real, no solo el rótulo)",
          "RESPUESTA DEL PROYECTO" in turno2_user)
    check("H6: el turno 2 también trae el mensaje del abogado del turno 1",
          "Resume las fuentes conectadas" in turno2_user)
    check("H6: el mensaje ACTUAL del turno 2 sigue presente y separado del historial",
          "Mensaje del abogado:\nAhora acórtalo" in turno2_user)

    # ── H6: la consulta de retrieval del intake queda LIMPIA (sin el historial) ──
    check("H6: intake sigue embebiendo SOLO el mensaje del turno (sin 'Conversación reciente')",
          bool(_embed_calls) and "Conversación reciente de este proyecto" not in _embed_calls[-1][0]
          and "Ahora acórtalo" in _embed_calls[-1][0])

    # ── no-regresión: el turno de ASUNTO sigue con HITL (awaiting_review) ────
    with client.stream("GET", f"/api/matters/{asunto_id}/stream",
                       params={"message": "¿Caducó la acción?"}, headers=auth_a) as s:
        body_a = "".join(s.iter_text())
    check("no-regresión: asunto sigue emitiendo 'awaiting_review'", "awaiting_review" in body_a)
    check("no-regresión: asunto marca pending_review=true", pending_review_of(asunto_id) is True)
    visible.append(body_a)

    # ── 4 · §G — sin jerga técnica en lo que ve el abogado ───────────────────
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)

    return threads


def main() -> int:
    print("== Bloque A · Proyectos (kind='proyecto' + outputs + turno sin HITL) ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    init_projects_multifolder.apply()   # idempotente: columnas/CHECK de la migración 028

    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    tid_a = make_tenant("A test proyectos")
    tid_b = make_tenant("B test proyectos")
    tok_a = jwt.encode({"tenant_id": tid_a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    tok_b = jwt.encode({"tenant_id": tid_b}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth_a = {"Authorization": f"Bearer {tok_a}"}
    auth_b = {"Authorization": f"Bearer {tok_b}"}
    threads: list[str] = []
    try:
        with TestClient(app) as client:
            threads = run_checks(client, auth_a, tid_a, auth_b, tid_b)
    finally:
        cleanup([tid_a, tid_b], threads)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Bloque A · Proyectos OK.")
        return 0
    print("Bloque A · Proyectos FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
