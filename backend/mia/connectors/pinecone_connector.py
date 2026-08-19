"""Mia · connectors.pinecone_connector — store vectorial EXTERNO y OPCIONAL (Módulo 3d).

Pinecone es un store secundario OPCIONAL (decisión #2): el primario sigue siendo
PostgreSQL + pgvector. Este conector es CONDICIONAL — se activa con la clave POR
TENANT (la que el despacho configuró en su pantalla, guardada en tenant_settings
bajo RLS y leída vía el scope de secretos de CP-S2); sin clave en el scope,
`get_pinecone_connector()` devuelve un `NoopPineconeConnector` que implementa la
misma interfaz, no hace nada y loggea un aviso. Sin SCOPE activo, lanza
`UnscopedSecretError` (fail-closed): antes de CP-S2 se leía `PINECONE_API_KEY`
del entorno — una clave de la instalación compartida entre TODOS los despachos.

AISLAMIENTO: Pinecone NO tiene RLS. El aislamiento entre despachos se hace por **namespace**:
`{namespace_prefix}_{tenant_id}`. Cada operación va acotada a su namespace. (La metadata del
vector se preserva intacta; el namespace —no un campo de metadata— es el mecanismo de
aislamiento idiomático de Pinecone.)

La librería `pinecone` (v3+) se importa de forma PEREZOSA dentro de `_get_index()`: el módulo
se puede importar y el `PineconeConnector` se puede construir sin tener el paquete instalado ni
tocar la red (la conexión real solo ocurre en la primera operación).
"""
from __future__ import annotations

import asyncio
import logging
from abc import ABC, abstractmethod
from contextlib import asynccontextmanager

from ..db import pool
from ..security import get_tenant_secret, secrets_from_tenant_config, tenant_secret_scope

logger = logging.getLogger("mia.connectors.pinecone")

DEFAULT_INDEX_NAME = "mia-legal"
DEFAULT_NAMESPACE_PREFIX = "tenant"
UPSERT_BATCH = 100   # máx vectores por llamada de upsert a Pinecone


class PineconeConnectorBase(ABC):
    """Interfaz común del conector (real y noop)."""

    is_configured: bool = False

    @abstractmethod
    async def upsert(self, tenant_id: str, vectors: list[dict]) -> dict:
        """Upsert de vectores [{id, values, metadata}] en el namespace del tenant."""

    @abstractmethod
    async def query(self, tenant_id: str, vector: list[float], top_k: int = 10,
                    metadata_filter: dict | None = None) -> list[dict]:
        """Consulta los `top_k` más cercanos en el namespace del tenant."""

    @abstractmethod
    async def delete(self, tenant_id: str, ids: list[str]) -> dict:
        """Borra vectores por id en el namespace del tenant."""

    @abstractmethod
    async def describe_index(self) -> dict:
        """Estadísticas/descripción del índice."""


class PineconeConnector(PineconeConnectorBase):
    """Conector real. El aislamiento es por namespace `{prefix}_{tenant_id}`."""

    is_configured = True

    def __init__(self, api_key: str, index_name: str, namespace_prefix: str) -> None:
        self.api_key = api_key
        self.index_name = index_name
        self.namespace_prefix = namespace_prefix
        self._index = None   # cliente perezoso (o inyectado en tests)

    def _namespace(self, tenant_id: str) -> str:
        """Namespace de aislamiento por tenant — Pinecone no tiene RLS."""
        return f"{self.namespace_prefix}_{tenant_id}"

    def _get_index(self):
        """Cliente del índice (perezoso). Importa `pinecone` solo aquí."""
        if self._index is None:
            from pinecone import Pinecone   # import diferido (v3+)

            pc = Pinecone(api_key=self.api_key)
            self._index = pc.Index(self.index_name)
        return self._index

    async def upsert(self, tenant_id: str, vectors: list[dict]) -> dict:
        ns = self._namespace(tenant_id)
        if not vectors:
            return {"upserted": 0, "batches": 0, "namespace": ns}
        index = self._get_index()
        upserted = batches = 0
        for i in range(0, len(vectors), UPSERT_BATCH):
            batch = vectors[i:i + UPSERT_BATCH]
            await asyncio.to_thread(index.upsert, vectors=batch, namespace=ns)
            upserted += len(batch)
            batches += 1
        return {"upserted": upserted, "batches": batches, "namespace": ns}

    async def query(self, tenant_id: str, vector: list[float], top_k: int = 10,
                    metadata_filter: dict | None = None) -> list[dict]:
        ns = self._namespace(tenant_id)
        index = self._get_index()
        kwargs = {"vector": vector, "top_k": top_k, "namespace": ns, "include_metadata": True}
        if metadata_filter:
            kwargs["filter"] = metadata_filter
        res = await asyncio.to_thread(lambda: index.query(**kwargs))
        matches = res["matches"] if isinstance(res, dict) else getattr(res, "matches", []) or []
        out = []
        for m in matches:
            if isinstance(m, dict):
                out.append({"id": m.get("id"), "score": m.get("score"),
                            "metadata": m.get("metadata")})
            else:
                out.append({"id": getattr(m, "id", None), "score": getattr(m, "score", None),
                            "metadata": getattr(m, "metadata", None)})
        return out

    async def delete(self, tenant_id: str, ids: list[str]) -> dict:
        ns = self._namespace(tenant_id)
        if not ids:
            return {"deleted": 0, "namespace": ns}
        index = self._get_index()
        await asyncio.to_thread(index.delete, ids=ids, namespace=ns)
        return {"deleted": len(ids), "namespace": ns}

    async def describe_index(self) -> dict:
        index = self._get_index()
        stats = await asyncio.to_thread(index.describe_index_stats)
        return dict(stats) if isinstance(stats, dict) else {"stats": stats}


class NoopPineconeConnector(PineconeConnectorBase):
    """Sin Pinecone configurado: misma interfaz, no hace nada, loggea un aviso."""

    is_configured = False
    _MSG = "Pinecone no configurado para este despacho; operación ignorada."

    async def upsert(self, tenant_id: str, vectors: list[dict]) -> dict:
        logger.info(self._MSG)
        return {"upserted": 0, "batches": 0, "skipped": True}

    async def query(self, tenant_id: str, vector: list[float], top_k: int = 10,
                    metadata_filter: dict | None = None) -> list[dict]:
        logger.info(self._MSG)
        return []

    async def delete(self, tenant_id: str, ids: list[str]) -> dict:
        logger.info(self._MSG)
        return {"deleted": 0, "skipped": True}

    async def describe_index(self) -> dict:
        logger.info(self._MSG)
        return {"is_configured": False}


def get_pinecone_connector() -> PineconeConnectorBase:
    """Factory: PineconeConnector con la clave DEL TENANT del scope activo; sin
    clave configurada → NoopPineconeConnector (solo pgvector).

    CP-S2 (fail-closed): requiere un `tenant_secret_scope(...)` activo — sin
    scope lanza UnscopedSecretError en vez de leer `PINECONE_API_KEY` del
    entorno (esa clave era de la instalación, no del despacho: compartirla
    entre tenants es una fuga de credenciales entre clientes)."""
    api_key = get_tenant_secret("pinecone_api_key")
    if not api_key:
        logger.info("Pinecone no configurado para este despacho: NoopPineconeConnector "
                    "(solo pgvector).")
        return NoopPineconeConnector()
    index_name = get_tenant_secret("pinecone_index_name", DEFAULT_INDEX_NAME)
    return PineconeConnector(api_key, index_name or DEFAULT_INDEX_NAME,
                             DEFAULT_NAMESPACE_PREFIX)


@asynccontextmanager
async def pinecone_scope_for_tenant(tenant_id: str):
    """Contexto ÚNICO para operar Pinecone de UN despacho (Módulo A · cableado como
    store secundario opt-in): lee la config de `tenant_settings` (bajo RLS, vía
    `pool.tenant_connection`), instala el `tenant_secret_scope` con esos secretos y
    entrega el connector ya resuelto — real si el despacho configuró su clave,
    `NoopPineconeConnector` si no.

    FAIL-SOFT (mismo patrón que `wiki_notes` / `_notebooklm_context`): cualquier error
    leyendo o desencriptando la config del despacho (DB caída, fila corrupta, llave de
    recuperación distinta) degrada a un scope VACÍO — el connector resultante es Noop.
    Nunca se propaga la excepción al llamador: el sync/turno del abogado sigue con
    pgvector como si Pinecone no estuviera configurado."""
    secrets: dict[str, str] = {}
    try:
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config FROM tenant_settings WHERE tenant_id=%s::uuid", (tenant_id,)
            )).fetchone()
        secrets = secrets_from_tenant_config(row[0] if row else {}, tenant_id=tenant_id)
    except Exception:  # noqa: BLE001 — Pinecone es opcional, jamás tumba al llamador
        logger.warning("pinecone: no pude resolver la config del despacho (tenant=%s); "
                       "se degrada a Noop (solo pgvector)", tenant_id, exc_info=True)
        secrets = {}
    with tenant_secret_scope(tenant_id, secrets):
        yield get_pinecone_connector()
