"""
Mia · test_medicion_por_nodo.py — DENUNCIAR LA AUSENCIA DE MEDICIÓN (AVISO · del harness).

El defecto que este gate caza: Mia atribuye tokens por nodo vía ContextVar
(metrics/usage.set_node, envuelto en graph._llm) y NADA comprobaba que un turno que
corrió nodos hubiera ESCRITO sus filas. Si `set_node()` se rompe en un refactor, el
desglose de turn_usage queda en NULL y todo sigue verde — la optimización por nodo se
vuelve inmedible sin que nadie lo note.

La aserción (portada del harness de litigio: la ausencia de señal ES el hallazgo):
    tras un turno que corrió nodos, CADA nodo ejecutado tiene ≥1 fila en turn_usage
    con `node` no nulo — y desde la 063, con `latency_ms` medido y `tool_calls` contado.

Por qué vive aquí y no en eval/harness.py (decisión razonada): el harness de eval corre
con LLM real y se paga; este gate corre la CADENA REAL de registro (graph._llm →
llm.call_llm → _record_usage → usage.record → flush_pending → turn_usage) con el único
doble en `_call_with_retries` (el POST físico al proveedor). Así el wiring completo se
verifica en cada pasada de gates, gratis y determinista, no solo cuando alguien paga
una corrida de eval. La verdad de «qué nodos corrieron» es md["node_metrics"], que se
acumula en el MISMO try/finally que fija el nodo: si set_node desaparece del wrapper,
las filas pierden el nodo y este gate se pone rojo.

Requiere la DB portable (.env). Crea un tenant de prueba y lo borra al final.

    .venv\\Scripts\\python.exe execution\\test_medicion_por_nodo.py

Exit 0 = PASS · 1 = FAIL.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
load_dotenv(ROOT / ".env")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agent import llm  # noqa: E402
from mia.agents.graph import MatterGraphBuilder  # noqa: E402
from mia.metrics import usage as usage_metrics  # noqa: E402

SUPER = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
             dbname=os.getenv("PG_DB", "mia"), user="postgres",
             password=os.getenv("PG_PASSWORD", ""))

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(f"  [{'OK' if ok else 'FAIL'}] {name}")


def _fake_resp(with_tools: bool = False):
    tool_calls = None
    if with_tools:
        tool_calls = [
            SimpleNamespace(id="tc1", function=SimpleNamespace(name="buscar", arguments="{}")),
            SimpleNamespace(id="tc2", function=SimpleNamespace(name="buscar", arguments="{}")),
        ]
    return SimpleNamespace(
        choices=[SimpleNamespace(
            message=SimpleNamespace(content="respuesta de prueba", tool_calls=tool_calls),
            finish_reason="tool_calls" if with_tools else "stop")],
        usage=SimpleNamespace(prompt_tokens=11, completion_tokens=7, total_tokens=18),
    )


NODOS = ["facts", "research", "analysis", "draft", "verificador_citas"]


async def _turno_simulado(tenant_id: str) -> dict:
    """Corre la cadena REAL graph._llm→call_llm→record por cada nodo del turno.

    El único doble es `_call_with_retries` (el POST al proveedor): todo lo demás —
    resolución de cadena, set_node, node_metrics, record(), flush— es código de
    producción tal cual corre en un turno.
    """
    md: dict = {}
    fake_self = SimpleNamespace(_compressor=None)  # _llm solo lo usa en el rescate
    state = {"tenant_id": tenant_id, "matter_id": None}
    for i, node in enumerate(NODOS):
        # la última llamada pide herramientas: verifica el conteo de tool_calls
        _ = await MatterGraphBuilder._llm(
            fake_self, [{"role": "system", "content": "s"},
                        {"role": "user", "content": f"nodo {node}"}],
            task="main", state=state, md=md, node=node)
    return md


async def _correr(tenant_id: str) -> None:
    from mia.db import pool
    await pool.open_pool()
    token = usage_metrics.set_usage_scope(tenant_id, source="gate")
    try:
        md = await _turno_simulado(tenant_id)
    finally:
        usage_metrics.reset_usage_scope(token)

    nm = md.get("node_metrics") or {}
    check("el turno acumuló node_metrics para TODOS los nodos ejecutados "
          f"({len(nm)}/{len(NODOS)})", set(nm) == set(NODOS))
    check("node_metrics trae llamadas ≥1 y latency_ms > 0 por nodo",
          all(int(v.get("llamadas") or 0) >= 1 and float(v.get("latency_ms") or 0) > 0
              for v in nm.values()))

    inserted = await usage_metrics.flush_pending()
    check(f"flush_pending persistió las filas del turno ({inserted} filas)",
          inserted >= len(NODOS))

    # LA ASERCIÓN CENTRAL: cada nodo ejecutado tiene ≥1 fila con node NO nulo.
    with psycopg.connect(autocommit=True, **SUPER) as c:
        rows = c.execute(
            "SELECT node, count(*), sum(coalesce(latency_ms,0)), sum(coalesce(tool_calls,0)) "
            "FROM turn_usage WHERE tenant_id=%s::uuid GROUP BY node", (tenant_id,)).fetchall()
    por_nodo = {r[0]: (int(r[1]), float(r[2] or 0), int(r[3] or 0)) for r in rows}
    sin_nodo = por_nodo.get(None, (0, 0, 0))[0]
    faltantes = [n for n in (md.get("node_metrics") or {}) if n not in por_nodo]
    check("cada nodo ejecutado tiene ≥1 fila en turn_usage con node no nulo "
          f"(faltantes: {faltantes or 'ninguno'})", not faltantes)
    check("ninguna fila del turno quedó con node NULL (la atribución no se perdió)",
          sin_nodo == 0)
    check("cada fila trae latency_ms medido (> 0) — el reloj por nodo de la 063",
          all(v[1] > 0 for n, v in por_nodo.items() if n is not None))
    check("los tool_calls de la respuesta quedaron contados (verificador_citas pidió 2)",
          por_nodo.get("verificador_citas", (0, 0, 0))[2] == 2)

    # usage_by_node (eval/harness) agrega el reloj y las herramientas sin romper con
    # filas viejas (coalesce).
    from mia.eval.harness import usage_by_node
    agg = await usage_by_node(tenant_id)
    check("usage_by_node expone llamadas, latency_ms y tool_calls por nodo",
          bool(agg) and all(k in agg[0] for k in ("llamadas", "latency_ms", "tool_calls")))

    # AUTO-MUTACIÓN: se simula el refactor que rompe set_node (no-op) y el gate DEBE
    # ver la fila sin nodo. Si esta detección dejara de funcionar, el gate estaría
    # verde por la razón equivocada.
    original = usage_metrics.set_node
    try:
        usage_metrics.set_node = lambda node=None: original(None)  # el refactor roto
        token = usage_metrics.set_usage_scope(tenant_id, source="gate")
        try:
            md2: dict = {}
            _ = await MatterGraphBuilder._llm(
                SimpleNamespace(_compressor=None),
                [{"role": "user", "content": "nodo roto"}],
                task="main", state={"tenant_id": tenant_id}, md=md2, node="draft")
        finally:
            usage_metrics.reset_usage_scope(token)
        await usage_metrics.flush_pending()
    finally:
        usage_metrics.set_node = original
    with psycopg.connect(autocommit=True, **SUPER) as c:
        nulos = c.execute(
            "SELECT count(*) FROM turn_usage WHERE tenant_id=%s::uuid AND node IS NULL",
            (tenant_id,)).fetchone()[0]
    check("auto-mutación: con set_node roto la fila queda SIN nodo y el gate lo ve "
          f"({nulos} fila(s) NULL tras romperlo)", nulos >= 1)
    from mia.db import pool as _pool
    await _pool.close_pool()


def main() -> int:
    if not SUPER["password"]:
        print("FAIL: falta PG_PASSWORD en .env (este gate necesita la DB portable)")
        return 1
    tenant_id = str(uuid.uuid4())
    with psycopg.connect(autocommit=True, **SUPER) as c:
        cols = [r[0] for r in c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='tenants'"
        ).fetchall()]
        if "name" in cols:
            c.execute("INSERT INTO tenants (id, name) VALUES (%s, %s)",
                      (tenant_id, "PRUEBA medición por nodo"))
        else:
            c.execute("INSERT INTO tenants (id) VALUES (%s)", (tenant_id,))

    # Doble del POST físico: todo lo demás es la cadena real de registro.
    llamadas: list[str] = []

    def _fake_call_with_retries(client, kwargs, max_retries, *, task=None, alias=None,
                                next_alias=None, **kw):
        llamadas.append(str(alias))
        # la 5ª llamada (verificador_citas) responde pidiendo 2 herramientas
        return _fake_resp(with_tools=(len(llamadas) == 5))

    original = llm._call_with_retries
    llm._call_with_retries = _fake_call_with_retries
    try:
        asyncio.run(_correr(tenant_id))
    finally:
        llm._call_with_retries = original
        usage_metrics.drain()  # nada de este gate queda en el buffer
        with psycopg.connect(autocommit=True, **SUPER) as c:
            c.execute("DELETE FROM tenants WHERE id=%s::uuid", (tenant_id,))

    failed = [n for n, ok in _results if not ok]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} checks OK")
    if failed:
        print("FAIL:", "; ".join(failed))
        return 1
    print("PASS: la medición por nodo existe, se persiste y su ausencia se detecta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
