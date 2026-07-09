"""Mia · memory.trace_capture — captura de trazas en JSONL (2d).

Cada turno del agente puede registrarse como una TRAZA en JSONL bajo
`mia-data/traces/` (gitignored). El formato es directamente usable para SFT/LoRA
posterior (compatible con hermes-agent-self-evolution, MIT): cada línea es un JSON
con el par input/output más metadata. `Trace.to_sft_example()` lo convierte al
formato de chat estándar `{"messages": [user, assistant]}`.

Aislamiento multi-tenant: un archivo JSONL por tenant (`{tenant_id}.jsonl`), para
que exportar los datos de un despacho para entrenar NO mezcle los de otro (mismo
principio que el RLS de la DB, §G).

Campos de cada traza (los 8 requeridos + schema):
    tenant_id · matter_id · timestamp (ISO 8601 UTC) · input · output ·
    model · tokens · latency_ms

Wiring: lo llama el turno del agente (run_turn / grafo de 1d) tras cada respuesta,
con `tokens` y `latency_ms` medidos. En 2d es un componente con su gate; el
cableado al turno va en 1d.
"""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

TRACE_SCHEMA = "mia.trace.v1"
TRACE_SCHEMA_V2 = "mia.trace.v2"            # traza con señales HITL (3e, decisión #19)
TRACE_EVENT_SCHEMA = "mia.trace.event.v1"   # eventos (p. ej. context_compressed, 2c)

# Los 8 campos requeridos por el spec (sin contar `schema`).
REQUIRED_FIELDS = (
    "tenant_id", "matter_id", "timestamp", "input", "output", "model", "tokens", "latency_ms",
)

_SAFE = re.compile(r"[^A-Za-z0-9._-]+")


def _default_traces_dir() -> Path:
    """Las trazas son estado de INSTANCIA (flywheel HITL, decisión #19): viven bajo
    config.MIA_HOME, que ya respeta MIA_APP_DIR / modo empaquetado (Fase 4 · R1).
    En desarrollo resuelve al mismo lugar histórico (mia/mia-data/traces). Se lee
    config en cada llamada para que los tests puedan reasignar config.MIA_HOME."""
    from mia import config
    return Path(config.MIA_HOME) / "traces"


def _safe_name(s: str) -> str:
    """Nombre de archivo seguro a partir de un tenant_id arbitrario."""
    return _SAFE.sub("_", s) or "unknown"


@dataclass
class Trace:
    """Una traza de un turno. `tokens` admite int o dict (prompt/completion/total)."""

    tenant_id: str
    matter_id: str
    input: str
    output: str
    model: str
    tokens: Any
    latency_ms: float
    timestamp: str = ""           # ISO 8601 UTC; se rellena al capturar si viene vacío
    schema: str = TRACE_SCHEMA
    # Señales HITL (mia.trace.v2, decisión #19). Opcionales: una traza v1 las deja en None/[]
    # y sigue siendo válida (el Feedback processor trata ausencia = None).
    hitl_outcome: Optional[str] = None        # 'approved' | 'rejected' | 'edited'
    draft_original: Optional[str] = None      # borrador antes de la edición del abogado
    draft_final: Optional[str] = None         # texto final (== output)
    retrieved_doc_ids: Optional[list] = None  # ids de docs citados; [] = NO_RESULT
    activated_playbooks: Optional[list] = None  # ids activados en draft (GEPA/Dreams)
    # Motivo textual que dio el abogado al RECHAZAR el borrador (frente B · B1). El
    # oro del loop de aprendizaje: sin esto la propuesta ataca el síntoma, no el porqué.
    # Vacío ("") en trazas que no son rechazo y en trazas viejas (compat hacia atrás).
    rejection_reason: str = ""

    def to_dict(self) -> dict:
        return asdict(self)

    def to_sft_example(self) -> dict:
        """Formato de chat para SFT/LoRA: {"messages": [user, assistant]}."""
        return {
            "messages": [
                {"role": "user", "content": self.input},
                {"role": "assistant", "content": self.output},
            ]
        }


class TraceCapture:
    """Escribe trazas en JSONL (append), un archivo por tenant. Crea el directorio."""

    def __init__(self, traces_dir: str | Path | None = None) -> None:
        self.traces_dir = Path(traces_dir) if traces_dir else _default_traces_dir()
        self.traces_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, tenant_id: str) -> Path:
        return self.traces_dir / f"{_safe_name(tenant_id)}.jsonl"

    def capture(
        self,
        *,
        tenant_id: str,
        matter_id: str,
        input: str,
        output: str,
        model: str,
        tokens: Any,
        latency_ms: float,
        timestamp: str | None = None,
        hitl_outcome: str | None = None,
        draft_original: str | None = None,
        draft_final: str | None = None,
        retrieved_doc_ids: list | None = None,
        activated_playbooks: list | None = None,
        rejection_reason: str | None = None,
    ) -> Trace:
        """Genera una traza y la añade (append) al JSONL del tenant. Devuelve la traza.

        Si se pasa alguno de los campos de señal HITL (3e), el `schema` sube a
        `mia.trace.v2`; sin ellos, la traza es `mia.trace.v1` (compat hacia atrás)."""
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        is_v2 = any(v is not None for v in (
            hitl_outcome, draft_original, draft_final, retrieved_doc_ids, activated_playbooks,
            rejection_reason,
        ))
        trace = Trace(
            tenant_id=tenant_id,
            matter_id=matter_id,
            input=input,
            output=output,
            model=model,
            tokens=tokens,
            latency_ms=latency_ms,
            timestamp=ts,
            schema=TRACE_SCHEMA_V2 if is_v2 else TRACE_SCHEMA,
            hitl_outcome=hitl_outcome,
            draft_original=draft_original,
            draft_final=draft_final,
            retrieved_doc_ids=retrieved_doc_ids,
            activated_playbooks=activated_playbooks,
            rejection_reason=rejection_reason or "",
        )
        path = self._path_for(tenant_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(trace.to_dict(), ensure_ascii=False) + "\n")
        return trace

    def capture_event(
        self,
        *,
        tenant_id: str,
        matter_id: str | None,
        event_type: str,
        timestamp: str | None = None,
        **fields: Any,
    ) -> dict:
        """Añade un EVENTO (no una traza de turno) al JSONL del tenant.

        Se distingue de las trazas por `schema='mia.trace.event.v1'` + `type`. Lo usa
        el ContextCompressor (2c) para registrar `context_compressed`
        (tokens_antes/tokens_despues/ratio_compresion). Para SFT se filtran por schema.
        """
        ts = timestamp or datetime.now(timezone.utc).isoformat()
        record = {
            "schema": TRACE_EVENT_SCHEMA,
            "type": event_type,
            "timestamp": ts,
            "tenant_id": tenant_id,
            "matter_id": matter_id,
            **fields,
        }
        path = self._path_for(tenant_id)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        return record

    def read(self, tenant_id: str) -> list[dict]:
        """Lee de vuelta las trazas de un tenant ([] si no hay archivo)."""
        path = self._path_for(tenant_id)
        if not path.exists():
            return []
        return self.read_jsonl(path)

    @staticmethod
    def read_jsonl(path: str | Path) -> list[dict]:
        """Lee un archivo JSONL a una lista de dicts (ignora líneas en blanco)."""
        out: list[dict] = []
        with Path(path).open("r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    out.append(json.loads(line))
        return out
