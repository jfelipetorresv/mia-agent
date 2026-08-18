"""
Mia · test_uso_por_nodo.py — F0.1 del plan de eficiencia (specs/todo/PLAN-principios-
harness-llos-eficiencia.md): la atribución del gasto POR NODO del grafo.

Qué prueba (con mutación incluida, regla de APRENDIZAJES #1-2):
  1. record() guarda el nodo fijado por ContextVar en la fila bufferizada.
  2. Sin nodo fijado, la fila lleva node=None (llamadas fuera del grafo) — la mutación:
     si set_node dejara de limpiar o record dejara de leer, este par de checks se cruza.
  3. El ContextVar VIAJA a asyncio.to_thread (el camino real de graph._llm → call_llm).
  4. graph._llm fija y RESTAURA el nodo (incluso si call_llm lanza).
  5. El INSERT de persistencia incluye la columna node y la columna existe en la DB dev.

Script directo (no pytest), estilo del repo: imprime [OK]/[FAIL] y sale 1 si algo falla.
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FALLOS = []
TOTAL = 0


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    global TOTAL
    TOTAL += 1
    print(f"  [{'OK' if ok else 'FAIL'}]   {nombre}" + (f" — {detalle}" if detalle and not ok else ""))
    if not ok:
        FALLOS.append(nombre)


def _usage(prompt=10, completion=5):
    return SimpleNamespace(prompt_tokens=prompt, completion_tokens=completion,
                           total_tokens=prompt + completion)


def main() -> int:
    from mia.metrics import usage as u

    # Scope de mentira para que record() no sea no-op.
    scope_token = u._scope.set(("00000000-0000-0000-0000-000000000001", None, "test"))
    try:
        print("1 · record() atribuye el nodo fijado")
        u.drain()
        node_token = u.set_node("draft")
        u.record("cli-claude", "main", _usage())
        u.reset_node(node_token)
        rows = u.drain()
        check("la fila lleva node='draft'", len(rows) == 1 and rows[0].get("node") == "draft",
              str(rows))

        print("2 · sin nodo fijado, node=None (mutación del check 1)")
        u.record("cli-claude", "main", _usage())
        rows = u.drain()
        check("la fila lleva node=None", len(rows) == 1 and rows[0].get("node") is None,
              str(rows))

        print("3 · el ContextVar viaja a asyncio.to_thread (camino real)")
        visto = {}

        async def _con_thread():
            tk = u.set_node("facts")
            try:
                await asyncio.to_thread(lambda: visto.setdefault("node", u._node.get()))
            finally:
                u.reset_node(tk)

        asyncio.run(_con_thread())
        check("el thread ve el nodo del contexto", visto.get("node") == "facts", str(visto))

        print("4 · graph._llm fija y restaura el nodo (incluso ante excepción)")
        from mia.agents import graph as g
        from mia.agent import llm as llm_mod

        capturado = []
        original = llm_mod.call_llm

        def _falso_call_llm(messages, **kw):
            capturado.append(u._node.get())
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content="ok"))],
                usage=_usage())

        def _call_llm_que_explota(messages, **kw):
            capturado.append(u._node.get())
            raise RuntimeError("bum")

        llm_mod.call_llm = _falso_call_llm
        try:
            builder = object.__new__(g.MatterGraphBuilder)  # sin __init__: _llm no usa self salvo _compressor
            asyncio.run(g.MatterGraphBuilder._llm(builder, [{"role": "user", "content": "x"}],
                                                  task="main", md={}, node="verificador_citas"))
        finally:
            llm_mod.call_llm = original
        check("call_llm corre con el nodo fijado", capturado and capturado[-1] == "verificador_citas",
              str(capturado))
        check("al salir, el contexto queda limpio", u._node.get() is None, str(u._node.get()))

        llm_mod.call_llm = _call_llm_que_explota
        try:
            try:
                asyncio.run(g.MatterGraphBuilder._llm(builder, [{"role": "user", "content": "x"}],
                                                      task="main", md=None, node="draft"))
                exploto = False
            except RuntimeError:
                exploto = True
        finally:
            llm_mod.call_llm = original
        check("la excepción se propaga", exploto)
        check("y el nodo queda restaurado igualmente", u._node.get() is None, str(u._node.get()))

        print("5 · persistencia: SQL y columna reales")
        check("el INSERT incluye la columna node",
              "node" in u._INSERT_SQL and "%(node)s" in u._INSERT_SQL)
        check("el INSERT incluye cost_status (no fingir USD 0)",
              "cost_status" in u._INSERT_SQL and "%(cost_status)s" in u._INSERT_SQL)
        import psycopg
        with psycopg.connect(host=os.getenv("PG_HOST", "127.0.0.1"),
                             port=os.getenv("PG_PORT", "5432"),
                             dbname=os.getenv("PG_DB", "mia"),
                             user="postgres", password=os.getenv("PG_PASSWORD", "")) as c:
            fila = c.execute(
                "SELECT 1 FROM information_schema.columns "
                "WHERE table_name='turn_usage' AND column_name='node'").fetchone()
        check("turn_usage.node existe en la DB", bool(fila))
    finally:
        u._scope.reset(scope_token)
        u.drain()

    ok = TOTAL - len(FALLOS)
    print(f"\nRESULT: {ok}/{TOTAL} checks PASS")
    if FALLOS:
        print("uso por nodo FALLA:", ", ".join(FALLOS))
        return 1
    print("uso por nodo OK — cada llamada del grafo queda atribuida a su etapa.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
