"""Mia · agents.delegation — primitiva de delegación multi-agente en paralelo (CP-E5, Ola 5).

Patrón swarm (raíz → trabajadores en paralelo → verificador → sintetizador) adaptado de
Hermes (`hermes_cli/kanban_swarm.py`, `tools/delegate_tool.py`) al grafo async de Mia.

Distinción clave con `graph.py::_maybe_delegate` (+ `gateway/agent_hub.py`): AQUELLO delega
a CLIs EXTERNOS (subprocess). ESTO coordina SUBTAREAS INTERNAS del turno — varios
investigadores LLM a la vez sobre el mismo estado del asunto — con:

  - concurrencia ACOTADA (`asyncio.Semaphore`): no dispara el costo (cada subtarea mide su
    gasto por el hook de `call_llm` → el tope de gasto de CP-E1 sigue vigente turno a turno);
  - FAIL-SOFT por subtarea: una que reviente queda registrada y NO tumba el lote ni el turno
    del abogado (misma filosofía que el resto del grafo: ante la duda, seguir sin caerse);
  - orden ESTABLE de resultados (el sintetizador necesita determinismo, no orden de llegada);
  - tope DURO de subtareas por lote (`MAX_WORKERS`): guarda anti-costo aunque llegue una lista
    enorme de claves.

Este módulo es PURO mecánica de concurrencia (sin DB, sin LLM, sin dominio jurídico): lo
específico de investigación —fuentes, memoria, verificación de citas— vive en
`graph.py::research_node`. Así se puede probar la primitiva sin infraestructura y reusarla
para futuras fan-outs (p. ej. por tipo de fuente) sin reescribir la mecánica.
"""
from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Awaitable, Callable, Optional, TypeVar

logger = logging.getLogger("mia.agents.delegation")

# Techo de trabajadores SIMULTÁNEOS (no de subtareas totales). Mantiene acotado el número
# de llamadas concurrentes al gateway LLM; el resto espera en el semáforo.
DEFAULT_MAX_CONCURRENT = 4
# Tope DURO de subtareas por lote. Guarda anti-costo: aunque un despacho tuviera decenas de
# jurisdicciones configuradas, un solo turno jamás abre más de este número de investigadores.
MAX_WORKERS = 8

T = TypeVar("T")


@dataclass
class SubtaskResult:
    """Resultado de UNA subtarea delegada. `ok=False` = falló y se ignoró (fail-soft)."""

    key: str                        # identifica la subtarea (p. ej. el código de jurisdicción)
    ok: bool
    value: Optional[object] = None  # lo que devolvió el worker (None si falló)
    error: Optional[str] = None     # str(exc) si falló (para la traza; nunca se propaga)


async def run_parallel(
    keys: list[str],
    worker: Callable[[str], Awaitable[T]],
    *,
    max_concurrent: int = DEFAULT_MAX_CONCURRENT,
) -> list[SubtaskResult]:
    """Corre `worker(key)` para cada `key` en paralelo, con concurrencia acotada.

    - Devuelve resultados en el MISMO orden que `keys` (estable → el sintetizador es
      determinista, no depende del orden de llegada de los workers).
    - FAIL-SOFT por subtarea: si `worker(k)` lanza, queda como `SubtaskResult(ok=False,
      error=...)` y las demás continúan. `run_parallel` NUNCA propaga (el turno del abogado
      no se cae porque un investigador reventó).
    - Recorta a `MAX_WORKERS` claves (con log si sobran): guarda anti-costo dura.
    - `max_concurrent` se satura a [1, MAX_WORKERS]; una lista vacía devuelve [].
    """
    if not keys:
        return []
    if len(keys) > MAX_WORKERS:
        logger.warning(
            "run_parallel: %d subtareas exceden el tope %d; se recortan a las primeras %d",
            len(keys), MAX_WORKERS, MAX_WORKERS,
        )
        keys = keys[:MAX_WORKERS]
    limit = max(1, min(int(max_concurrent), MAX_WORKERS))
    sem = asyncio.Semaphore(limit)

    async def _guarded(k: str) -> SubtaskResult:
        async with sem:
            try:
                value = await worker(k)
                return SubtaskResult(key=k, ok=True, value=value)
            except Exception as exc:  # noqa: BLE001 — fail-soft por subtarea (ver docstring)
                logger.warning("subtarea '%s' falló (se ignora): %s", k, exc, exc_info=True)
                return SubtaskResult(key=k, ok=False, error=str(exc))

    # return_exceptions=False es seguro: _guarded nunca lanza (captura todo adentro).
    return await asyncio.gather(*(_guarded(k) for k in keys))
