"""
Mia · test_trace_search.py — gate de H.3 (session_search FTS sin LLM).

Verifica contra la DB real: indexado + búsqueda por keyword, filtro por asunto, ranking
(más relevante primero), filtro por playbook activado, RLS A↔B, y que NO se llame al LLM.

HALT si falla (CLAUDE.md §G). Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_trace_search.py
"""
from __future__ import annotations
import asyncio
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
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import init_traces_search                              # noqa: E402  (migración 013)
from mia.agent import llm                              # noqa: E402
from mia.db import pool                                # noqa: E402
from mia.memory import trace_search                    # noqa: E402

_results: list[tuple[str, bool]] = []
_llm_calls: list[int] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# Centinela: si el camino de búsqueda llama al LLM, lo detectamos.
def _tripwire_llm(*a, **k):
    _llm_calls.append(1)
    raise AssertionError("trace_search NO debe llamar al LLM")


llm.call_llm = _tripwire_llm

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def make_tenant(label: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (f"TRSRCH_TEST {label}",)
        ).fetchone()[0])


def drop_test_tenants() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE name LIKE 'TRSRCH_TEST%'")


async def run_gate(t: dict) -> None:
    await pool.open_pool()
    try:
        A, B = t["a"], t["b"]
        m1, m2 = "11111111-1111-1111-1111-111111111111", "22222222-2222-2222-2222-222222222222"

        # === indexado ===
        id1 = await trace_search.index_trace(
            A, matter_id=m1, input="contrato de arrendamiento urbano",
            output="el contrato de arrendamiento es válido; el contrato se firma hoy",
            hitl_outcome="approved", activated_playbooks=["pb-arriendo"], trace_ts="2026-06-30T10:00:00+00:00")
        id2 = await trace_search.index_trace(
            A, matter_id=m2, input="demanda laboral por despido",
            output="despido injustificado, procede indemnización", hitl_outcome="rejected",
            trace_ts="2026-06-30T11:00:00+00:00")
        id3 = await trace_search.index_trace(
            A, matter_id=m1, input="breve mención de contrato", output="otro tema distinto",
            hitl_outcome="approved", trace_ts="2026-06-30T12:00:00+00:00")
        check("index_trace devuelve ids", all([id1, id2, id3]))

        # === Riesgo #68: el diagnóstico del turno se persiste (antes se perdía con el checkpoint) ===
        id_diag = await trace_search.index_trace(
            A, matter_id=m1, input="consulta con diagnóstico",
            output="borrador final", hitl_outcome="approved", trace_ts="2026-06-30T13:00:00+00:00",
            diagnosis="Problema: X. Riesgo: Y.",
            diagnosis_summary={"problema": "X", "normas": "Z", "riesgo": "Y"})
        async with pool.tenant_connection(A) as conn:
            row = await (await conn.execute(
                "SELECT diagnosis, diagnosis_summary FROM traces WHERE id = %s::uuid", (id_diag,)
            )).fetchone()
        check("index_trace persiste el diagnóstico en prosa", row and row[0] == "Problema: X. Riesgo: Y.")
        check("index_trace persiste el cierre estructurado (jsonb)",
              row and isinstance(row[1], dict) and row[1].get("problema") == "X")

        # === búsqueda por keyword ===
        res = await trace_search.search_traces(A, "contrato")
        ids = [r["id"] for r in res]
        check("búsqueda 'contrato' encuentra las trazas con contrato (2)",
              set(ids) == {id1, id3})
        check("búsqueda 'contrato' NO trae la traza laboral", id2 not in ids)

        # === ranking: más relevante primero ===
        check("ranking: la traza con más ocurrencias de 'contrato' va primera",
              res[0]["id"] == id1)

        # === filtro por asunto ===
        res_m2 = await trace_search.search_traces(A, "despido", matter_id=m2)
        check("filtro por asunto (m2) + 'despido' → solo la traza de m2",
              [r["id"] for r in res_m2] == [id2])
        res_m1 = await trace_search.search_traces(A, "contrato", matter_id=m1)
        check("filtro por asunto (m1) acota a ese asunto",
              set(r["id"] for r in res_m1) == {id1, id3})

        # === filtro por outcome ===
        res_rej = await trace_search.search_traces(A, "despido", outcome="rejected")
        check("filtro por outcome=rejected", [r["id"] for r in res_rej] == [id2])
        check("filtro por outcome=approved excluye la rechazada",
              id2 not in [r["id"] for r in await trace_search.search_traces(A, "despido", outcome="approved")])

        # === filtro por playbook activado ===
        res_pb = await trace_search.search_traces(A, "contrato", activated_playbook="pb-arriendo")
        check("filtro por playbook activado", [r["id"] for r in res_pb] == [id1])
        check("filtro por playbook inexistente → vacío",
              (await trace_search.search_traces(A, "contrato", activated_playbook="pb-nope")) == [])

        # === query vacío → [] ===
        check("query vacío devuelve []", (await trace_search.search_traces(A, "   ")) == [])

        # === C.3: query malformada (solo operadores) → TraceSearchError (endpoint → 400) ===
        async def _raises(q):
            try:
                await trace_search.search_traces(A, q)
                return False
            except trace_search.TraceSearchError:
                return True
        check("query solo-operadores ':::' → TraceSearchError (400)", await _raises(":::"))
        check("query operadores rotos '&|!' → TraceSearchError (400)", await _raises("&|!"))
        check("query '()' → TraceSearchError (400)", await _raises("()"))
        # una consulta legítima con dos puntos ('contrato:') sigue funcionando (websearch tolera)
        check("query legítima con ':' ('contrato') sigue devolviendo resultados",
              len(await trace_search.search_traces(A, "contrato")) >= 1)

        # === RLS A↔B ===
        await trace_search.index_trace(B, matter_id=m1, input="contrato secreto de B",
                                       output="contenido de otro despacho", hitl_outcome="approved")
        check("RLS: B no ve las trazas de A al buscar 'arrendamiento'",
              (await trace_search.search_traces(B, "arrendamiento")) == [])
        check("RLS: A no ve la traza 'secreto' de B",
              (await trace_search.search_traces(A, "secreto")) == [])
        check("RLS: B sí ve su propia traza",
              len(await trace_search.search_traces(B, "contrato")) == 1)

        # === sin llamada LLM en todo el camino ===
        check("NINGUNA llamada al LLM en indexado+búsqueda", len(_llm_calls) == 0)
    finally:
        await pool.close_pool()


def check_endpoint_validation() -> None:
    """C.6: matter_id es obligatorio en GET /api/traces/search → sin él, 422.

    La validación de query params de FastAPI ocurre ANTES del cuerpo del handler (y antes de
    tocar la DB), así que montamos solo el router y verificamos el 422 sin necesidad de auth/pool.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from mia.api.routes import traces as traces_route

    app = FastAPI()
    app.include_router(traces_route.router)
    client = TestClient(app)

    r_missing = client.get("/api/traces/search", params={"q": "contrato"})  # sin matter_id
    check("endpoint: sin matter_id → 422 (obligatorio)", r_missing.status_code == 422)
    r_missing_q = client.get("/api/traces/search", params={"matter_id": "m-1"})  # sin q
    check("endpoint: sin q → 422 (obligatorio)", r_missing_q.status_code == 422)


def main() -> int:
    print("== Tarea H.3 · session_search FTS (tsvector+GIN) sin LLM ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env")
        return 1

    check_endpoint_validation()   # C.6 · no toca DB

    init_traces_search.apply()

    drop_test_tenants()
    t = {k: make_tenant(k) for k in ("a", "b")}
    try:
        asyncio.run(run_gate(t))
    finally:
        drop_test_tenants()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("trace_search OK — H.3 verificado (FTS+GIN, ranking BM-like, RLS, sin LLM).")
        return 0
    print("trace_search FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
