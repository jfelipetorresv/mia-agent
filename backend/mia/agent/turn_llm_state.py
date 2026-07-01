"""Mia · agent.turn_llm_state — estado LLM por turno (cadena de fallback + compresión, H.5).

Un turno del grafo puede tocar el LLM varias veces (análisis, borrador, finalización) y cada
llamada recorre la cadena de fallback de `llm.call_llm`. Este dataclass acumula lo que ya se
intentó DENTRO del turno para que los nodos coordinen dos mecanismos que no deben pelearse:

  - la cadena de proveedores (la resuelve `llm.resolve_fallback_chain`), y
  - la compresión de contexto (una sola vez por turno ante CONTEXT_TOO_LONG).

Sin este estado, un CONTEXT_TOO_LONG podría disparar compresión en cada nodo (bucle) o, peor,
saltar de proveedor cuando el problema es el tamaño del prompt (que ningún modelo arregla).
Adaptado del patrón `TurnRetryState` de Hermes v0.17.0.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .error_classifier import LLMErrorKind


@dataclass
class TurnLLMState:
    """Estado mutable de las llamadas LLM de UN turno del grafo.

    - `task_model_tried`: por task, los aliases ya intentados (para diagnóstico/telemetría).
    - `compression_attempted`: True si ya se comprimió el contexto en este turno (una sola vez).
    - `fallback_exhausted`: True si una llamada agotó la cadena entera (ALL_PROVIDERS_EXHAUSTED).
    - `last_error_kind`: el último `LLMErrorKind` observado (None si aún no hubo error).
    """

    task_model_tried: dict[str, list[str]] = field(default_factory=dict)
    compression_attempted: bool = False
    fallback_exhausted: bool = False
    last_error_kind: LLMErrorKind | None = None

    def record_attempt(self, task: str, alias: str) -> None:
        """Anota que `alias` se intentó para `task` (sin duplicar)."""
        tried = self.task_model_tried.setdefault(task, [])
        if alias not in tried:
            tried.append(alias)

    def mark_compressed(self) -> None:
        """Marca que ya se comprimió el contexto en este turno (idempotente)."""
        self.compression_attempted = True

    def should_compress(self, kind: LLMErrorKind) -> bool:
        """True si conviene comprimir: el error es de contexto y aún no se comprimió."""
        return kind is LLMErrorKind.CONTEXT_TOO_LONG and not self.compression_attempted

    # ── (de)serialización JSON-safe para viajar en state.metadata entre nodos del grafo ──
    def to_dict(self) -> dict:
        """Forma serializable (para guardar en metadata; el checkpointer la persiste)."""
        return {
            "task_model_tried": {k: list(v) for k, v in self.task_model_tried.items()},
            "compression_attempted": self.compression_attempted,
            "fallback_exhausted": self.fallback_exhausted,
            "last_error_kind": self.last_error_kind.value if self.last_error_kind else None,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "TurnLLMState":
        """Reconstruye desde metadata (o un estado nuevo si no había nada)."""
        if not data:
            return cls()
        kind_raw = data.get("last_error_kind")
        return cls(
            task_model_tried={k: list(v) for k, v in (data.get("task_model_tried") or {}).items()},
            compression_attempted=bool(data.get("compression_attempted")),
            fallback_exhausted=bool(data.get("fallback_exhausted")),
            last_error_kind=LLMErrorKind(kind_raw) if kind_raw else None,
        )
