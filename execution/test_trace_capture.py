"""
Mia · test_trace_capture.py — gate del Módulo 2d (TraceCapture JSONL).

Verifica:
  1. Una traza de prueba SE GENERA y SE ESCRIBE en disco (en un dir temporal).
  2. El archivo es JSONL VÁLIDO (cada línea parsea como JSON).
  3. Es LEGIBLE con los CAMPOS CORRECTOS: los 8 requeridos (tenant_id, matter_id,
     timestamp, input, output, model, tokens, latency_ms) con sus valores.
  4. El directorio se crea solo (mkdir parents); un archivo por tenant; append.
  5. timestamp auto es ISO 8601 válido; to_sft_example() da formato de chat.
  6. El dir por defecto resuelve a mia-data/traces.

Salida: exit 0 = PASS.
    .venv\\Scripts\\python.exe execution\\test_trace_capture.py
"""
from __future__ import annotations
import json
import sys
import tempfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))  # para `import mia.*`

from mia.memory.trace_capture import REQUIRED_FIELDS, TraceCapture, _default_traces_dir

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def main() -> int:
    print("== Módulo 2d · TraceCapture JSONL ==")

    with tempfile.TemporaryDirectory() as tmp:
        # Dir inexistente a propósito → debe crearlo (mkdir parents).
        traces_dir = Path(tmp) / "sub" / "traces"
        tc = TraceCapture(traces_dir)
        check("crea el directorio de trazas (mkdir parents)", traces_dir.is_dir())

        # 1 · generar y escribir una traza.
        trace = tc.capture(
            tenant_id="t-1",
            matter_id="m-1",
            input="¿Caducó la acción de reparación directa?",
            output="No: el término de dos años aún no se cumple. [VERIFICAR fecha del daño]",
            model="claude-sonnet",
            tokens={"prompt": 120, "completion": 80, "total": 200},
            latency_ms=1234.5,
        )
        path = tc._path_for("t-1")
        check("la traza se escribió en disco", path.is_file())
        check("el archivo es por-tenant ({tenant}.jsonl)", path.name == "t-1.jsonl")

        # 2 · JSONL válido (cada línea parsea).
        raw = path.read_text(encoding="utf-8").splitlines()
        jsonl_ok = True
        for line in raw:
            if line.strip():
                try:
                    json.loads(line)
                except Exception:
                    jsonl_ok = False
        check("cada línea es JSON válido (JSONL)", jsonl_ok and len(raw) == 1)

        # 3 · legible con los campos correctos.
        records = tc.read("t-1")
        check("se lee de vuelta 1 traza", len(records) == 1)
        rec = records[0]
        check("tiene los 8 campos requeridos", set(REQUIRED_FIELDS).issubset(rec.keys()))
        check("tenant_id correcto", rec["tenant_id"] == "t-1")
        check("matter_id correcto", rec["matter_id"] == "m-1")
        check("input correcto", rec["input"].startswith("¿Caducó"))
        check("output correcto", "[VERIFICAR" in rec["output"])
        check("model correcto", rec["model"] == "claude-sonnet")
        check("tokens round-trip (dict)", rec["tokens"] == {"prompt": 120, "completion": 80, "total": 200})
        check("latency_ms correcto", rec["latency_ms"] == 1234.5)
        check("schema versionado presente", rec.get("schema") == "mia.trace.v1")

        # 5 · timestamp ISO 8601 válido.
        ts_ok = True
        try:
            datetime.fromisoformat(rec["timestamp"])
        except Exception:
            ts_ok = False
        check("timestamp es ISO 8601 válido", ts_ok)

        # 4 · append + aislamiento por tenant.
        tc.capture(tenant_id="t-1", matter_id="m-2", input="i2", output="o2",
                   model="claude-haiku", tokens=50, latency_ms=300.0)
        check("append: el JSONL del tenant crece a 2", len(tc.read("t-1")) == 2)

        tc.capture(tenant_id="t-2", matter_id="m-9", input="i", output="o",
                   model="claude-sonnet", tokens=10, latency_ms=99.0)
        check("aislamiento: t-2 en su propio archivo", tc._path_for("t-2").is_file())
        check("aislamiento: t-1 sigue con 2 trazas, t-2 con 1",
              len(tc.read("t-1")) == 2 and len(tc.read("t-2")) == 1)

        # 5 · to_sft_example.
        sft = trace.to_sft_example()
        check("to_sft_example da {messages:[user, assistant]}",
              [m["role"] for m in sft["messages"]] == ["user", "assistant"]
              and sft["messages"][0]["content"] == trace.input
              and sft["messages"][1]["content"] == trace.output)

        # 7 · CP-C3 (Riesgo #31): activated_playbooks viaja en la traza v2 y hace
        # roundtrip por el JSONL — es la materia prima del circuito de aprendizaje.
        v2 = tc.capture(tenant_id="t-3", matter_id="m-1", input="i", output="o",
                        model="claude-sonnet", tokens=10, latency_ms=50.0,
                        hitl_outcome="approved",
                        activated_playbooks=["pb-tutela", "pb-caducidad"])
        rec3 = tc.read("t-3")[0]
        check("CP-C3: capture con activated_playbooks sube el schema a v2",
              v2.schema == "mia.trace.v2" and rec3.get("schema") == "mia.trace.v2")
        check("CP-C3: activated_playbooks hace roundtrip (lista de 2 ids intacta)",
              rec3.get("activated_playbooks") == ["pb-tutela", "pb-caducidad"])
        v2solo = tc.capture(tenant_id="t-3", matter_id="m-2", input="i", output="o",
                            model="claude-sonnet", tokens=10, latency_ms=50.0,
                            activated_playbooks=["pb-solo"])
        check("CP-C3: activated_playbooks SOLO (sin otros campos HITL) también es v2",
              v2solo.schema == "mia.trace.v2")

    # 6 · dir por defecto.
    default = _default_traces_dir()
    check("el dir por defecto termina en mia-data/traces",
          default.parts[-2:] == ("mia-data", "traces"))

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
