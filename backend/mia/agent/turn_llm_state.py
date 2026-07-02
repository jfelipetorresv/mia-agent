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


# Etapa por defecto cuando el caller no identifica su nodo (contrato pre-CP9:
# cupo global del turno). Los nodos del grafo pasan su nombre real.
_DEFAULT_STAGE = "_turn"


@dataclass
class TurnLLMState:
    """Estado mutable de las llamadas LLM de UN turno del grafo.

    - `task_model_tried`: por task, los aliases ya intentados (para diagnóstico/telemetría).
    - `compressed_stages`: nodos que YA comprimieron su contexto en este turno. CP9
      (revisión capa 2, hallazgo M1): el cupo es POR NODO, no global — con 4 nodos LLM
      (facts/research/analysis/draft), un cupo global dejaba sin rescate al nodo
      siguiente cuando el anterior ya lo había gastado (el prompt del cruce es un
      superconjunto del de hechos → el turno entero moría en expedientes grandes).
      El guard anti-bucle se conserva: DENTRO de un mismo nodo solo se comprime una vez.
    - `fallback_exhausted`: True si una llamada agotó la cadena entera (ALL_PROVIDERS_EXHAUSTED).
    - `last_error_kind`: el último `LLMErrorKind` observado (None si aún no hubo error).
    """

    task_model_tried: dict[str, list[str]] = field(default_factory=dict)
    compressed_stages: list[str] = field(default_factory=list)
    fallback_exhausted: bool = False
    last_error_kind: LLMErrorKind | None = None

    @property
    def compression_attempted(self) -> bool:
        """True si ALGÚN nodo ya comprimió en este turno (compat con H.5/CP1)."""
        return bool(self.compressed_stages)

    def record_attempt(self, task: str, alias: str) -> None:
        """Anota que `alias` se intentó para `task` (sin duplicar)."""
        tried = self.task_model_tried.setdefault(task, [])
        if alias not in tried:
            tried.append(alias)

    def mark_compressed(self, stage: str = "") -> None:
        """Marca que `stage` ya comprimió su contexto en este turno (idempotente)."""
        s = stage or _DEFAULT_STAGE
        if s not in self.compressed_stages:
            self.compressed_stages.append(s)

    def should_compress(self, kind: LLMErrorKind, stage: str = "") -> bool:
        """True si conviene comprimir: error de contexto y `stage` aún no comprimió."""
        return (kind is LLMErrorKind.CONTEXT_TOO_LONG
                and (stage or _DEFAULT_STAGE) not in self.compressed_stages)

    # ── (de)serialización JSON-safe para viajar en state.metadata entre nodos del grafo ──
    def to_dict(self) -> dict:
        """Forma serializable (para guardar en metadata; el checkpointer la persiste).

        `compression_attempted` se conserva DERIVADO en el dict: los gates y cualquier
        consumidor de metadata previos a CP9 siguen leyendo el mismo campo."""
        return {
            "task_model_tried": {k: list(v) for k, v in self.task_model_tried.items()},
            "compression_attempted": self.compression_attempted,
            "compressed_stages": list(self.compressed_stages),
            "fallback_exhausted": self.fallback_exhausted,
            "last_error_kind": self.last_error_kind.value if self.last_error_kind else None,
        }

    @classmethod
    def from_dict(cls, data: dict | None) -> "TurnLLMState":
        """Reconstruye desde metadata (o un estado nuevo si no había nada).

        Un dict viejo (pre-CP9, sin `compressed_stages` pero con
        `compression_attempted=True`) se traduce al cupo global gastado."""
        if not data:
            return cls()
        kind_raw = data.get("last_error_kind")
        stages = data.get("compressed_stages")
        if stages is None:
            stages = [_DEFAULT_STAGE] if data.get("compression_attempted") else []
        return cls(
            task_model_tried={k: list(v) for k, v in (data.get("task_model_tried") or {}).items()},
            compressed_stages=[str(s) for s in stages],
            fallback_exhausted=bool(data.get("fallback_exhausted")),
            last_error_kind=LLMErrorKind(kind_raw) if kind_raw else None,
        )
