"""
Mia · test_hitl_flow.py — gate de integración del Módulo 1d (LangGraph + HITL + SSE).

Prueba el flujo completo contra la DB real (Módulo 0) + el checkpointer Postgres,
con el LLM y los embeddings MOCKEADOS (sin red):

  1. Crea tenants A/B y un asunto de A (como postgres).
  2. Corre el grafo de A hasta el interrupt(): se detiene EN hitl_checkpoint, con
     borrador listo y SIN traza (no llegó a finalize).
  3. Reanuda con Command(resume={"decision":"approved"}): finaliza y deja la traza
     JSONL en disco.
  4. RLS de dominio: A ve su asunto, B no. Checkpoint persistido en Postgres.
  5. HTTP: tenant cruzado (B) que aprueba el asunto de A → 401. Stream SSE del dueño
     llega a 'awaiting_review' sin jerga técnica (§G).

Gate mínimo (subconjunto): interrupt detiene ✓ · resume reanuda ✓ · cruzado→401 ✓
· traza JSONL ✓.

    .venv\\Scripts\\python.exe execution\\test_hitl_flow.py
"""
from __future__ import annotations
import asyncio
import os
import shutil
import sys
import tempfile
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

# La consola de PowerShell es cp1252: forzar utf-8 evita un crash al imprimir.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia import config, embeddings              # noqa: E402
from mia.agent import llm                        # noqa: E402
from mia.agents.checkpointer import open_checkpointer  # noqa: E402
from mia.agents.graph import build_matter_graph  # noqa: E402
from mia.agents.state import initial_state, thread_id_for  # noqa: E402
from mia.db import pool                          # noqa: E402
from mia.memory.trace_capture import TraceCapture  # noqa: E402
from langgraph.types import Command              # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── mocks (sin red) ────────────────────────────────────────────────────────
def _fake_embed(texts):
    return [[0.0] * config.EMBED_DIM for _ in texts]


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    sysmsg = messages[0]["content"] if messages and isinstance(messages[0], dict) else ""
    if "Redacta el borrador" in sysmsg:
        content = "BORRADOR: contestación de la demanda de responsabilidad civil. [VERIFICAR fecha del hecho]"
    elif "Incorpora al borrador" in sysmsg:
        content = "BORRADOR CORREGIDO con las indicaciones del abogado."
    else:
        content = "DIAGNÓSTICO: el eje del asunto es la caducidad de la acción."
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=20, total_tokens=32),
    )


embeddings.embed_texts = _fake_embed
llm.call_llm = _fake_call_llm

# ── conexión admin (postgres) para setup/teardown/asserts ──────────────────
PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def setup_data():
    with psycopg.connect(autocommit=True, **PG) as c:
        a = c.execute("INSERT INTO tenants(name) VALUES('A test 1d') RETURNING id").fetchone()[0]
        b = c.execute("INSERT INTO tenants(name) VALUES('B test 1d') RETURNING id").fetchone()[0]
        m = c.execute("INSERT INTO matters(tenant_id,title) VALUES(%s,'Asunto 1d') RETURNING id", (a,)).fetchone()[0]
        m2 = c.execute("INSERT INTO matters(tenant_id,title) VALUES(%s,'Asunto 1d stream') RETURNING id", (a,)).fetchone()[0]
        m3 = c.execute("INSERT INTO matters(tenant_id,title) VALUES(%s,'Asunto 1d rechazo') RETURNING id", (a,)).fetchone()[0]
    return str(a), str(b), str(m), str(m2), str(m3)


def cleanup(a, b, m, m2, m3):
    with psycopg.connect(autocommit=True, **PG) as c:
        for tid in (thread_id_for(a, m), thread_id_for(a, m2), thread_id_for(a, m3)):
            for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (tid,))
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([a, b],))


def checkpoint_count(thread_id):
    with psycopg.connect(autocommit=True, **PG) as c:
        return c.execute("SELECT count(*) FROM checkpoints WHERE thread_id=%s", (thread_id,)).fetchone()[0]


# ── flujo del grafo (interrupt → resume) ───────────────────────────────────
async def graph_flow(a, b, m, trace_dir):
    await pool.open_pool()
    try:
        tc = TraceCapture(trace_dir)
        cfg = {"configurable": {"thread_id": thread_id_for(a, m)}}
        inp = initial_state(a, m, "¿Caducó la acción de reparación directa?",
                            profile_snapshot={"despacho": "Defendemos aseguradoras."})
        obs = {}

        # Fase 1 — correr hasta el interrupt.
        async with open_checkpointer() as cp:
            graph = build_matter_graph(cp, trace_capture=tc)
            chunks = [ch async for ch in graph.astream(inp, cfg, stream_mode="updates")]
            st1 = await graph.aget_state(cfg)
        obs["interrupted"] = any("__interrupt__" in ch for ch in chunks)
        obs["nodes1"] = [n for ch in chunks for n in ch if n != "__interrupt__"]
        obs["draft1"] = st1.values.get("draft")
        obs["next1"] = list(st1.next)
        obs["trace1"] = len(tc.read(a))

        # RLS de dominio.
        async with pool.tenant_connection(a) as conn:
            obs["a_sees"] = (await (await conn.execute("SELECT 1 FROM matters WHERE id=%s::uuid", (m,))).fetchone()) is not None
        async with pool.tenant_connection(b) as conn:
            obs["b_sees"] = (await (await conn.execute("SELECT 1 FROM matters WHERE id=%s::uuid", (m,))).fetchone()) is not None

        # Fase 2 — reanudar (approved).
        async with open_checkpointer() as cp:
            graph = build_matter_graph(cp, trace_capture=tc)
            chunks2 = [ch async for ch in graph.astream(Command(resume={"decision": "approved"}), cfg, stream_mode="updates")]
            st2 = await graph.aget_state(cfg)
        obs["nodes2"] = [n for ch in chunks2 for n in ch if n != "__interrupt__"]
        obs["next2"] = list(st2.next)
        obs["draft2"] = st2.values.get("draft")
        obs["trace_id"] = st2.values.get("trace_id")
        traces = tc.read(a)
        obs["trace2"] = len(traces)
        obs["trace_out"] = traces[-1]["output"] if traces else None
        req = {"tenant_id", "matter_id", "timestamp", "input", "output", "model", "tokens", "latency_ms"}
        obs["trace_fields"] = bool(traces) and req.issubset(traces[-1].keys())
        return obs
    finally:
        await pool.close_pool()


# ── B1 (frente B): el motivo del rechazo llega a la traza ──────────────────
async def reject_flow(a, m3, trace_dir):
    """Corre el grafo hasta el interrupt y lo reanuda con un RECHAZO + motivo; verifica que
    la traza final registra hitl_outcome='rejected' y el motivo textual en rejection_reason."""
    await pool.open_pool()
    try:
        tc = TraceCapture(trace_dir)
        cfg = {"configurable": {"thread_id": thread_id_for(a, m3)}}
        inp = initial_state(a, m3, "¿Prescribió la acción?",
                            profile_snapshot={"despacho": "Defendemos aseguradoras."})
        async with open_checkpointer() as cp:
            graph = build_matter_graph(cp, trace_capture=tc)
            _ = [ch async for ch in graph.astream(inp, cfg, stream_mode="updates")]
        motivo = "Confundió la caducidad con la prescripción; la excepción correcta era otra."
        async with open_checkpointer() as cp:
            graph = build_matter_graph(cp, trace_capture=tc)
            _ = [ch async for ch in graph.astream(
                Command(resume={"decision": "rejected", "feedback": motivo}),
                cfg, stream_mode="updates")]
        traces = tc.read(a)
        last = traces[-1] if traces else {}
        return {"outcome": last.get("hitl_outcome"), "reason": last.get("rejection_reason") or ""}
    finally:
        await pool.close_pool()


# ── HTTP (401 cruzado + stream SSE del dueño) ──────────────────────────────
def api_checks(a, b, m, m2):
    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    out = {}
    tok_a = jwt.encode({"tenant_id": a}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    tok_b = jwt.encode({"tenant_id": b}, config.JWT_SECRET, algorithm=config.JWT_ALG)
    with TestClient(app) as client:
        r = client.post(f"/matters/{m}/approve", headers={"Authorization": f"Bearer {tok_b}"})
        out["xtenant_status"] = r.status_code
        with client.stream("GET", f"/matters/{m2}/stream",
                           params={"message": "¿Caducó la acción?"},
                           headers={"Authorization": f"Bearer {tok_a}"}) as s:
            out["stream_status"] = s.status_code
            body = "".join(s.iter_text())
    out["stream_awaiting"] = "awaiting_review" in body
    out["stream_borrador"] = "Borrador listo" in body
    jargon = ("LangGraph", "interrupt", "HITL", "pgvector", "tenant", "checkpoint")
    out["stream_no_jargon"] = not any(j in body for j in jargon)
    return out


def main() -> int:
    print("== Módulo 1d · LangGraph StateGraph + SSE + HITL ==")
    if not config.JWT_SECRET:
        print("  [FAIL] JWT_SECRET vacío en .env — necesario para el test HTTP")
        return 1

    a, b, m, m2, m3 = setup_data()
    trace_dir = tempfile.mkdtemp(prefix="mia_traces_")
    try:
        obs = asyncio.run(graph_flow(a, b, m, trace_dir))

        # 1 · interrupt detiene el grafo antes de finalizar
        check("interrupt() dispara __interrupt__ y detiene el grafo", obs["interrupted"])
        # CP9: el equipo de especialistas completo corre antes de la pausa HITL.
        check("nodos corren en orden hasta draft",
              obs["nodes1"] == ["intake", "facts", "research", "analysis",
                                "draft", "verification"])
        check("borrador generado antes del checkpoint", (obs["draft1"] or "").startswith("BORRADOR"))
        check("grafo pausado EN hitl_checkpoint (antes de finalize)", "hitl_checkpoint" in obs["next1"])
        check("sin traza antes de aprobar (no llegó a finalize)", obs["trace1"] == 0)

        # RLS de dominio + persistencia del checkpoint
        check("RLS dominio: A ve su asunto, B no", obs["a_sees"] and not obs["b_sees"])
        check("checkpoint persistido en Postgres (AsyncPostgresSaver)", checkpoint_count(thread_id_for(a, m)) > 0)

        # 2 · resume reanuda y finaliza
        check("Command(resume=...) ejecuta finalize", "finalize" in obs["nodes2"])
        check("grafo finaliza tras resume (done, next vacío)", obs["next2"] == [])
        check("borrador final presente", (obs["draft2"] or "").startswith("BORRADOR"))
        check("trace_id asignado al finalizar", bool(obs["trace_id"]))

        # 4 · traza JSONL generada al finalizar
        check("traza JSONL generada al finalizar", obs["trace2"] == 1)
        check("la traza tiene los 8 campos requeridos", obs["trace_fields"])
        check("la traza guarda el borrador final como output", obs["trace_out"] == obs["draft2"])

        # B1 · el rechazo con motivo escribe rejection_reason en la traza
        rej = asyncio.run(reject_flow(a, m3, trace_dir))
        check("B1: el rechazo registra hitl_outcome='rejected' en la traza",
              rej["outcome"] == "rejected")
        check("B1: el motivo del abogado queda en rejection_reason de la traza",
              rej["reason"].startswith("Confundió la caducidad"))

        # 3 · HTTP
        api = api_checks(a, b, m, m2)
        check("tenant cruzado (B aprueba asunto de A) -> 401", api["xtenant_status"] == 401)
        check("stream SSE del dueño responde 200", api["stream_status"] == 200)
        check("stream emite 'awaiting_review'", api["stream_awaiting"])
        check("stream muestra 'Borrador listo' (frase del oficio)", api["stream_borrador"])
        check("stream SIN jerga técnica (§G)", api["stream_no_jargon"])
    finally:
        shutil.rmtree(trace_dir, ignore_errors=True)
        cleanup(a, b, m, m2, m3)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
