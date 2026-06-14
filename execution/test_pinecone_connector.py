"""
Mia · test_pinecone_connector.py — gate del Módulo 3d (Pinecone connector · store opcional).

NO requiere Pinecone real ni red: usa `NoopPineconeConnector` y un índice FALSO inyectado en
`PineconeConnector._index`. La librería `pinecone` se importa de forma perezosa dentro del
conector, así que el gate corre aunque el paquete no esté instalado.

Manipula `os.environ['PINECONE_API_KEY']` para probar la factory en ambos modos (con/sin key)
y lo restaura al final.

HALT: si este gate falla, NO se avanza (CLAUDE.md §G). Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_pinecone_connector.py
"""
from __future__ import annotations
import asyncio
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.connectors.pinecone_connector import (   # noqa: E402
    NoopPineconeConnector,
    PineconeConnector,
    PineconeConnectorBase,
    get_pinecone_connector,
)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def run(coro):
    return asyncio.run(coro)


# ── índice Pinecone FALSO (registra llamadas; sin red) ───────────────────────
class FakeIndex:
    def __init__(self) -> None:
        self.upserts: list[dict] = []
        self.queries: list[dict] = []
        self.deletes: list[dict] = []

    def upsert(self, vectors=None, namespace=None, **kw):
        self.upserts.append({"n": len(vectors), "namespace": namespace, "vectors": vectors})
        return {"upserted_count": len(vectors)}

    def query(self, **kwargs):
        self.queries.append(kwargs)
        return {"matches": [{"id": "v1", "score": 0.9, "metadata": {"k": "v"}}]}

    def delete(self, ids=None, namespace=None, **kw):
        self.deletes.append({"ids": ids, "namespace": namespace})
        return {}

    def describe_index_stats(self):
        return {"namespaces": {}}


def _connector_with_fake() -> tuple[PineconeConnector, FakeIndex]:
    c = PineconeConnector(api_key="fake-key", index_name="mia-legal", namespace_prefix="tenant")
    fake = FakeIndex()
    c._index = fake   # inyección: evita la conexión real (perezosa)
    return c, fake


def main() -> int:
    print("== Módulo 3d · Pinecone connector (store externo opcional) ==")
    original_key = os.environ.get("PINECONE_API_KEY")
    try:
        # === factory: sin key -> Noop ===
        os.environ.pop("PINECONE_API_KEY", None)
        c_noop = get_pinecone_connector()
        check("sin PINECONE_API_KEY -> get_pinecone_connector() devuelve Noop",
              isinstance(c_noop, NoopPineconeConnector))
        check("noop.is_configured == False", c_noop.is_configured is False)

        # === noop: ninguna operación lanza, query devuelve [] ===
        up = run(c_noop.upsert("t-1", [{"id": "a", "values": [0.0] * 8, "metadata": {}}]))
        check("noop.upsert() no lanza y devuelve dict", isinstance(up, dict))
        q = run(c_noop.query("t-1", [0.0] * 8))
        check("noop.query() devuelve lista vacía", q == [])
        dl = run(c_noop.delete("t-1", ["a"]))
        check("noop.delete() no lanza y devuelve dict", isinstance(dl, dict))

        # === interfaz completa (sin métodos abstractos pendientes) ===
        noop_complete = NoopPineconeConnector.__abstractmethods__ == frozenset()
        real_complete = PineconeConnector.__abstractmethods__ == frozenset()
        has_all = all(callable(getattr(c_noop, m, None))
                      for m in ("upsert", "query", "delete", "describe_index"))
        check("NoopPineconeConnector implementa toda la interfaz de la base",
              noop_complete and real_complete and has_all
              and isinstance(c_noop, PineconeConnectorBase))

        # === namespace por tenant ===
        conn = PineconeConnector("fake-key", "mia-legal", "tenant")
        ns = conn._namespace("t-123")
        check("el namespace incluye el tenant_id (aislamiento sin RLS)",
              ns == "tenant_t-123" and "t-123" in ns)

        # === batch de upsert: 250 vectores -> 3 batches (100,100,50) ===
        c, fake = _connector_with_fake()
        vecs = [{"id": f"v{i}", "values": [0.0] * 8, "metadata": {"i": i}} for i in range(250)]
        stats = run(c.upsert("t-9", vecs))
        sizes = [u["n"] for u in fake.upserts]
        check("upsert de 250 vectores se parte en batches de 100",
              sizes == [100, 100, 50] and stats["batches"] == 3 and stats["upserted"] == 250)
        check("cada batch va al namespace del tenant",
              all(u["namespace"] == "tenant_t-9" for u in fake.upserts))

        # === factory con key (mock) -> conector real, sin red ===
        os.environ["PINECONE_API_KEY"] = "fake-key-en-test"
        c_real = get_pinecone_connector()
        check("con PINECONE_API_KEY -> get_pinecone_connector() devuelve PineconeConnector",
              isinstance(c_real, PineconeConnector) and c_real.is_configured is True)

        # === metadata preservada intacta en el upsert ===
        c, fake = _connector_with_fake()
        run(c.upsert("t-2", [{"id": "x", "values": [0.1] * 8, "metadata": {"a": 1, "b": "x"}}]))
        sent = fake.upserts[0]["vectors"][0]
        check("la metadata del vector llega intacta al upsert",
              sent["metadata"] == {"a": 1, "b": "x"})

        # === query: top_k se pasa al cliente + namespace correcto ===
        c, fake = _connector_with_fake()
        res = run(c.query("t-5", [0.2] * 8, top_k=5))
        check("query pasa top_k al cliente con el namespace del tenant",
              fake.queries[0]["top_k"] == 5 and fake.queries[0]["namespace"] == "tenant_t-5")
        check("query normaliza los matches a list[dict] {id,score,metadata}",
              res == [{"id": "v1", "score": 0.9, "metadata": {"k": "v"}}])

        # === delete: los ids llegan al cliente en el namespace correcto ===
        c, fake = _connector_with_fake()
        run(c.delete("t-7", ["a", "b", "c"]))
        check("delete pasa los ids al cliente con el namespace del tenant",
              fake.deletes[0]["ids"] == ["a", "b", "c"] and fake.deletes[0]["namespace"] == "tenant_t-7")
    finally:
        if original_key is None:
            os.environ.pop("PINECONE_API_KEY", None)
        else:
            os.environ["PINECONE_API_KEY"] = original_key

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Pinecone connector OK — Módulo 3d verificado.")
        return 0
    print("Pinecone connector FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
