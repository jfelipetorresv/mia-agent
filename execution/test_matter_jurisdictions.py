"""Gate offline: la jurisdicción del asunto prevalece sobre la organización.

No requiere PostgreSQL: simula la conexión RLS para fijar el contrato de precedencia y
verifica que el grafo entregue `matter_id` al resolutor antes de buscar fuentes/citas.
"""
from __future__ import annotations

import asyncio
import sys
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from fastapi import HTTPException

from mia.api.routes import ux
from mia.db import pool as pool_mod
from mia.jurisdiction import resolver


def check(name: str, condition: bool) -> bool:
    print(f"{'[OK]  ' if condition else '[FAIL]'} {name}")
    return bool(condition)


def fake_pool(matter_value, organization_value):
    @asynccontextmanager
    async def tenant_connection(_tenant_id):
        async def execute(sql, _params):
            value = matter_value if "FROM matters" in sql else organization_value

            async def fetchone():
                return (value,)

            return SimpleNamespace(fetchone=fetchone)
        yield SimpleNamespace(execute=execute)
    return tenant_connection


async def run() -> bool:
    old_connection = pool_mod.tenant_connection
    old_resolve = ux.resolve_jurisdictions
    results: list[bool] = []
    try:
        pool_mod.tenant_connection = fake_pool(["mx", "mx"], ["co", "mx"])
        results.append(check(
            "asunto no vacío prevalece y se deduplica",
            await resolver.resolve_jurisdictions("tenant", "matter") == ["mx"],
        ))

        pool_mod.tenant_connection = fake_pool([], ["co", "mx"])
        results.append(check(
            "asunto legado vacío hereda la firma u organización",
            await resolver.resolve_jurisdictions("tenant", "matter") == ["co", "mx"],
        ))

        pool_mod.tenant_connection = fake_pool(None, None)
        results.append(check(
            "sin selección queda modo general seguro",
            await resolver.resolve_jurisdictions("tenant", "matter") == ["generic"],
        ))

        async def allowed(_tenant):
            return ["co", "mx"]
        ux.resolve_jurisdictions = allowed
        results.append(check(
            "API acepta únicamente el subconjunto de la organización",
            await ux._matter_jurisdictions("tenant", ["mx"]) == ["mx"],
        ))
        try:
            await ux._matter_jurisdictions("tenant", ["ar"])
            rejected = False
        except HTTPException as exc:
            rejected = exc.status_code == 422
        results.append(check("API rechaza jurisdicción no declarada", rejected))

        graph = (ROOT / "backend" / "mia" / "agents" / "graph.py").read_text(encoding="utf-8")
        results.append(check(
            "grafo pasa matter_id al resolver para investigación y citas",
            graph.count('state["tenant_id"], state.get("matter_id")') >= 3,
        ))
    finally:
        pool_mod.tenant_connection = old_connection
        ux.resolve_jurisdictions = old_resolve
    return all(results)


if __name__ == "__main__":
    raise SystemExit(0 if asyncio.run(run()) else 1)
