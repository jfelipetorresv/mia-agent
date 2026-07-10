"""
Mia · test_guide_interview.py — gate del Bloque B (evolución de producto): motor de
entrevista para crear guías de trabajo.

Ejercita `POST /api/guides/interview` (backend/mia/api/routes/guides.py + motor
backend/mia/memory/interviewer.py) contra la DB real, con el LLM MOCKEADO (sin red,
reasignación de módulo). Molde calcado de execution/test_projects.py (event loop
policy, .env, tenants propios con limpieza en finally, TestClient + JWT). Cubre:

  1. Auth: sin token -> 401/403.
  2. Validación 422 en llano: kind inválido, kind='agente', messages no-lista,
     mensaje sin contenido/rol.
  3. Flujo feliz: 3 preguntas (forzadas por el mínimo) y a la 4ª ronda el LLM decide
     'draft' -> done:true con el shape exacto, recortado a 200 chars server-side.
  4. Con <3 preguntas, si el LLM (mockeado) pide 'draft' se IGNORA y se fuerza una
     pregunta de respaldo determinista.
  5. A la 6ª pregunta se fuerza 'draft' aunque el LLM (mockeado) pida seguir
     preguntando -> borrador de respaldo determinista con las respuestas dadas.
  6. JSON inválido del LLM -> pregunta de respaldo, JAMÁS 500.
  7. matter_id de otro tenant -> 404 en llano.
  8. matter_id propio con transcript vacío -> resumen de confirmación (B3), sin
     tocar el LLM; el turno siguiente reinyecta el contexto del asunto (evidencia
     aprobada incluida) en el prompt que ve el LLM.
  9. GATE HITL: una entrevista completa (de vacío a borrador) SIN llamar a
     POST /api/playbooks no cambia ni una fila de playbooks/playbook_versions/
     feedback_proposals/matters.
  10. §G: nada de jerga técnica en lo que ve el abogado (question/draft/detail).

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_guide_interview.py
"""
from __future__ import annotations
import asyncio
import json
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

import init_playbook_versions               # noqa: E402  (migración 029, idempotente)
from mia import config                       # noqa: E402
from mia.agent import llm                    # noqa: E402
from mia.memory import interviewer           # noqa: E402
from mia.memory.trace_capture import TraceCapture  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── stub de LLM (sin red) ────────────────────────────────────────────────────
# Cola de respuestas canónicas: cada item es un dict (se serializa a JSON), una
# cadena cruda (para simular JSON inválido) o "RAISE" (para simular un fallo del
# proveedor). Si la cola está vacía, se devuelve una pregunta genérica.
_llm_queue: list[object] = []
_llm_calls: list[list[dict]] = []


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    _llm_calls.append(messages)
    item = _llm_queue.pop(0) if _llm_queue else {"action": "ask", "question": "¿Algo más?"}
    if item == "RAISE":
        raise RuntimeError("stub: fallo simulado del proveedor LLM")
    content = item if isinstance(item, str) else json.dumps(item, ensure_ascii=False)
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=5, total_tokens=10))


llm.call_llm = _fake_call_llm

PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
          dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))

FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "chunk", "embedding", "sync engine")


def make_tenant(name: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (name,)).fetchone()[0])


def cleanup(tenants: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", (tenants,))


def _row_counts() -> dict[str, int]:
    out = {}
    with psycopg.connect(autocommit=True, **PG) as c:
        for table in ("playbooks", "playbook_versions", "feedback_proposals", "matters"):
            out[table] = c.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
    return out


def _ask(client, headers, kind="guia", messages=None, matter_id=None):
    body = {"kind": kind, "messages": messages if messages is not None else []}
    if matter_id is not None:
        body["matter_id"] = matter_id
    return client.post("/api/guides/interview", headers=headers, json=body)


def run_checks(client, auth_a, tid_a, auth_b, tid_b) -> None:
    visible: list[str] = []

    # ── 1 · auth ──────────────────────────────────────────────────────────────
    r = client.post("/api/guides/interview", json={"kind": "guia", "messages": []})
    check("sin token -> 401/403", r.status_code in (401, 403))

    # ── 2 · validación 422 en llano ──────────────────────────────────────────
    r = _ask(client, auth_a, kind="invalido")
    check("kind inválido -> 422", r.status_code == 422)
    visible.append(r.text)

    # Bloque C: kind='agente' YA es un flujo válido (diseñar un agente jurídico). Con el
    # transcript vacío y <3 preguntas, se fuerza una pregunta (done=False) — no 422.
    r = _ask(client, auth_a, kind="agente")
    check("kind='agente' -> 200 (agente ya es un flujo válido en el Bloque C)",
          r.status_code == 200 and r.json().get("done") is False
          and isinstance(r.json().get("question"), str))
    visible.append(r.text)

    r = client.post("/api/guides/interview", headers=auth_a,
                    json={"kind": "guia", "messages": "no es una lista"})
    check("messages no-lista -> 422", r.status_code == 422)
    visible.append(r.text)

    r = _ask(client, auth_a, messages=[{"role": "user"}])
    check("mensaje sin content -> 422", r.status_code == 422)
    visible.append(r.text)

    r = _ask(client, auth_a, messages=[{"role": "vecino", "content": "hola"}])
    check("mensaje con rol inválido -> 422", r.status_code == 422)
    visible.append(r.text)

    # ── 3 · flujo feliz: 3 preguntas forzadas -> el LLM decide 'draft' ───────
    transcript: list[dict] = []
    _llm_queue.clear()
    _llm_queue.append({"action": "ask", "question": "¿Qué tipo de caso resuelve esta guía?"})
    r = _ask(client, auth_a, messages=transcript)
    body1 = r.json()
    check("turno 1 (0 preguntas hechas): done=False + question del LLM",
          r.status_code == 200 and body1.get("done") is False
          and body1.get("question") == "¿Qué tipo de caso resuelve esta guía?")
    visible.append(r.text)
    transcript.append({"role": "assistant", "content": body1["question"]})
    transcript.append({"role": "user", "content": "Reclamaciones de seguro de cumplimiento."})

    _llm_queue.append({"action": "ask", "question": "¿Qué pasos sigues primero?"})
    r = _ask(client, auth_a, messages=transcript)
    body2 = r.json()
    check("turno 2 (1 pregunta hecha): sigue preguntando", body2.get("done") is False)
    visible.append(r.text)
    transcript.append({"role": "assistant", "content": body2["question"]})
    transcript.append({"role": "user", "content": "Reviso la póliza y el siniestro reportado."})

    _llm_queue.append({"action": "ask", "question": "¿Qué documentos necesitas?"})
    r = _ask(client, auth_a, messages=transcript)
    body3 = r.json()
    check("turno 3 (2 preguntas hechas): sigue preguntando (aún <3)", body3.get("done") is False)
    visible.append(r.text)
    transcript.append({"role": "assistant", "content": body3["question"]})
    transcript.append({"role": "user", "content": "La póliza, el clausulado y el siniestro."})

    largo = "X" * 250  # para probar el recorte server-side a 200 chars
    _llm_queue.append({
        "action": "draft",
        "title": largo, "summary": largo, "applies_when": largo,
        "content": "Paso 1: revisar póliza. Paso 2: revisar siniestro.",
        "explanation": "Con estas 3 respuestas ya hay material suficiente.",
    })
    r = _ask(client, auth_a, messages=transcript)
    body4 = r.json()
    check("turno 4 (3 preguntas hechas, dentro de 3-6): el LLM decide 'draft' -> done=True",
          r.status_code == 200 and body4.get("done") is True)
    draft = body4.get("draft", {})
    check("shape del draft: title/summary/applies_when/content + explanation",
          set(draft.keys()) == {"title", "summary", "applies_when", "content"}
          and "explanation" in body4)
    check("recorte server-side a 200 chars (title/summary/applies_when)",
          len(draft.get("title", "")) == 200 and len(draft.get("summary", "")) == 200
          and len(draft.get("applies_when", "")) == 200)
    visible.append(r.text)

    # ── 4 · <3 preguntas: el LLM que pide 'draft' se IGNORA, se fuerza pregunta ──
    _llm_queue.clear()
    _llm_queue.append({"action": "draft", "title": "T", "summary": "S",
                        "applies_when": "A", "content": "C", "explanation": "E"})
    r = _ask(client, auth_a, messages=[])
    body = r.json()
    check("<3 preguntas: 'draft' del LLM se ignora, se fuerza una pregunta",
          r.status_code == 200 and body.get("done") is False
          and body.get("question") == interviewer._FALLBACK_QUESTIONS[0])
    visible.append(r.text)

    # ── 5 · a la 6ª pregunta se fuerza 'draft' (aunque el LLM pida seguir) ──────
    seis_preguntas: list[dict] = []
    for i in range(6):
        seis_preguntas.append({"role": "assistant", "content": f"Pregunta {i + 1}"})
        seis_preguntas.append({"role": "user", "content": f"Respuesta {i + 1}"})
    _llm_queue.clear()
    _llm_queue.append({"action": "ask", "question": "¿Sigo preguntando?"})
    r = _ask(client, auth_a, messages=seis_preguntas)
    body = r.json()
    check("6 preguntas hechas: 'ask' del LLM se ignora, se fuerza el borrador",
          r.status_code == 200 and body.get("done") is True)
    check("borrador de respaldo determinista trae las respuestas dadas",
          "Respuesta 1" in body.get("draft", {}).get("content", "")
          and "Respuesta 6" in body.get("draft", {}).get("content", ""))
    visible.append(r.text)

    # ── 6 · JSON inválido del LLM -> respaldo, jamás 500 ────────────────────────
    cuatro_preguntas: list[dict] = []
    for i in range(4):
        cuatro_preguntas.append({"role": "assistant", "content": f"Pregunta {i + 1}"})
        cuatro_preguntas.append({"role": "user", "content": f"Respuesta {i + 1}"})
    _llm_queue.clear()
    _llm_queue.append("esto no es json {{{")
    r = _ask(client, auth_a, messages=cuatro_preguntas)
    body = r.json()
    check("JSON inválido del LLM (dentro de 3-6) -> 200 con pregunta de respaldo, NUNCA 500",
          r.status_code == 200 and body.get("done") is False
          and body.get("question") == interviewer._FALLBACK_QUESTIONS[4])
    visible.append(r.text)

    # ── 7/8 · B3: precarga de contexto de un asunto ─────────────────────────────
    r = client.post("/api/matters", headers=auth_a,
                    json={"name": "Reclamación EPM", "description": "Póliza de cumplimiento."})
    matter_a = r.json()["id"]

    trace_capture = TraceCapture()
    trace_capture.capture(
        tenant_id=tid_a, matter_id=matter_a,
        input="¿Caducó la acción?", output="No, sigue vigente.",
        model="stub", tokens={}, latency_ms=1.0,
        hitl_outcome="approved", draft_final="Se decidió alegar caducidad como excepción.",
    )

    r = client.post("/api/matters", headers=auth_b, json={"name": "Asunto de B"})
    matter_b = r.json()["id"]

    r = _ask(client, auth_a, messages=[], matter_id=matter_b)
    check("matter_id de OTRO tenant -> 404 en llano", r.status_code == 404)
    visible.append(r.text)

    r = _ask(client, auth_a, messages=[], matter_id="no-es-un-uuid")
    check("matter_id malformado (no-UUID) -> 404 en llano, JAMÁS 500", r.status_code == 404)
    visible.append(r.text)

    _llm_queue.clear()
    calls_before = len(_llm_calls)
    r = _ask(client, auth_a, messages=[], matter_id=matter_a)
    body = r.json()
    check("matter_id propio + transcript vacío -> resumen de confirmación",
          r.status_code == 200 and body.get("done") is False
          and "Reclamación EPM" in body.get("question", ""))
    check("la precarga de confirmación NO llama al LLM", len(_llm_calls) == calls_before)
    visible.append(r.text)

    confirm_transcript = [
        {"role": "assistant", "content": body["question"]},
        {"role": "user", "content": "Sí, así es. Agrégale que primero se revisa la fecha del hecho."},
    ]
    _llm_queue.append({"action": "ask", "question": "¿Qué más revisas de la póliza?"})
    r = _ask(client, auth_a, messages=confirm_transcript, matter_id=matter_a)
    check("turno siguiente con matter_id sigue respondiendo bien (200, done=False)",
          r.status_code == 200 and r.json().get("done") is False)
    visible.append(r.text)
    last_system = _llm_calls[-1][0]["content"] if _llm_calls else ""
    check("B3: el contexto del asunto se reinyecta en el prompt del LLM (título)",
          "Reclamación EPM" in last_system)
    check("B3: la evidencia aprobada del asunto llega al prompt del LLM",
          "caducidad" in last_system.lower())

    # ── 9 · GATE HITL: la entrevista jamás escribe en la DB ──────────────────────
    antes = _row_counts()
    gate_transcript: list[dict] = []
    _llm_queue.clear()
    for i in range(3):
        _llm_queue.append({"action": "ask", "question": f"Pregunta gate {i + 1}"})
    _llm_queue.append({
        "action": "draft", "title": "Guía de prueba", "summary": "Resumen",
        "applies_when": "Cuando aplique", "content": "Contenido de prueba",
        "explanation": "Listo",
    })
    for _ in range(4):
        r = _ask(client, auth_a, messages=gate_transcript)
        body = r.json()
        if body.get("done"):
            break
        gate_transcript.append({"role": "assistant", "content": body["question"]})
        gate_transcript.append({"role": "user", "content": "Respuesta de prueba del gate."})
    despues = _row_counts()
    check(f"GATE HITL: 0 cambios en playbooks/playbook_versions/feedback_proposals/matters "
          f"(antes={antes}, despues={despues})", antes == despues)

    # ── 10 · §G — sin jerga técnica en lo que ve el abogado ──────────────────────
    blob = " ".join(visible).lower()
    leaked = [w for w in FORBIDDEN if w in blob]
    check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)


def main() -> int:
    print("== Bloque B · Guías de trabajo asistidas (motor de entrevista) ==")
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1

    init_playbook_versions.apply()   # idempotente: tabla playbook_versions (migración 029)

    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    tid_a = make_tenant("A test guías")
    tid_b = make_tenant("B test guías")
    tok_a = jwt.encode({"tenant_id": tid_a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    tok_b = jwt.encode({"tenant_id": tid_b}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth_a = {"Authorization": f"Bearer {tok_a}"}
    auth_b = {"Authorization": f"Bearer {tok_b}"}
    try:
        with TestClient(app) as client:
            run_checks(client, auth_a, tid_a, auth_b, tid_b)
    finally:
        cleanup([tid_a, tid_b])

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Bloque B · Guías de trabajo OK.")
        return 0
    print("Bloque B · Guías de trabajo FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
