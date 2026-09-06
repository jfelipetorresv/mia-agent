"""
Mia · test_context_compressor.py — gate del Módulo 2c (ContextCompressor).

Offline: el cliente OpenAI se reemplaza por uno falso inyectado en llm._client, así
que el routing real call_llm→resolve_model SÍ corre y se verifica el BLOQUEO a
mia-local end-to-end (sin red). Verifica:
  1. No comprime bajo el threshold (55%).
  2. Comprime cuando lo supera.
  3. protect_first_n=5 y protect_last_n=30 intactos tras comprimir.
  4. El modelo usado es SIEMPRE mia-local bajo política 'soberano' (CP2, decisión #27):
     este gate fija esa política explícitamente porque su gateway falso espera
     model=mia-local; el bloqueo de compression bajo las 3 políticas lo cubre
     execution/test_model_policy.py.
  5. Los mensajes con [VERIFICAR] no se comprimen (se preservan verbatim).
  6. El resumen está en español jurídico (+ prefijo [RESUMEN DE CONTEXTO ANTERIOR]).
  7. El evento context_compressed queda en la traza JSONL.
  8. (A) resumen iterativo: la 2ª compresión actualiza el resumen previo.
  9. (B) anti-thrashing: tras 2 compresiones inefectivas, no recomprime.

    .venv\\Scripts\\python.exe execution\\test_context_compressor.py
"""
from __future__ import annotations
import sys
import tempfile
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agent import llm
from mia.agent.context_compressor import ContextCompressor, SUMMARY_PREFIX, SUMMARY_END_MARKER, _text
from mia.memory.trace_capture import TraceCapture

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


SPANISH_SUMMARY = (
    "## Hechos jurídicos clave\nEl demandante alega responsabilidad civil "
    "extracontractual del Estado.\n\n## Decisiones tomadas\nSe optó por la excepción "
    "de caducidad de la acción de reparación directa."
)


class _FakeCompletions:
    def __init__(self):
        self.last = None
        self.calls = 0

    def create(self, **kw):
        self.last = kw
        self.calls += 1
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=SPANISH_SUMMARY))])


class _FakeClient:
    def __init__(self):
        self.chat = SimpleNamespace(completions=_FakeCompletions())


def make_convo(n=50, marker_at=None):
    msgs = []
    for i in range(n):
        role = "user" if i % 2 == 0 else "assistant"
        body = ("[VERIFICAR] art. 90 CPACA. " if marker_at == i else "") + ("x" * 180)
        msgs.append({"role": role, "content": f"Turno {i}: {body}"})
    return msgs


def main() -> int:
    print("== Módulo 2c · ContextCompressor ==")
    fake = _FakeClient()
    original_client = llm._client
    llm._client = fake
    # CP2: política 'soberano' explícita — compression→mia-local, que es lo que el
    # gateway falso de este gate espera recibir (patrón de test_model_policy.py).
    _tok = llm.set_model_policy("soberano")
    try:
        convo = make_convo(50)  # ~2600 tokens

        # 1 · no comprime bajo threshold (window grande → threshold 5500 > 2600)
        cc = ContextCompressor()
        out_under = cc.compress(convo, 10000)
        check("no comprime bajo el threshold (55%)", out_under is convo and not cc.last_compressed)

        # 2 · comprime sobre threshold (window chico → threshold 550 < 2600)
        cc2 = ContextCompressor()
        out = cc2.compress(convo, 1000)
        check("comprime cuando supera el threshold", cc2.last_compressed and out is not convo)
        check("tokens_despues < tokens_antes", cc2.last_tokens_after < cc2.last_tokens_before)

        # 3 · protect_first_n=5 y protect_last_n=30 intactos
        check("primeros 5 mensajes intactos", out[:5] == convo[:5])
        check("últimos 30 mensajes intactos", out[-30:] == convo[-30:])
        check("el resumen es 1 mensaje de USUARIO con el prefijo",
              out[5]["role"] == "user" and out[5]["content"].startswith(SUMMARY_PREFIX))
        check("estructura: first5 + [resumen] + last30 (sin [VERIFICAR])", len(out) == 36)

        # 4 · modelo mia-local bajo 'soberano' (CP2; bloqueo end-to-end + a nivel resolve_model)
        check("el gateway recibió model=mia-local", fake.chat.completions.last["model"] == "mia-local")
        check("resolve_model(compression, sonnet) IGNORA override -> mia-local (soberano)",
              llm.resolve_model("compression", model="claude-sonnet") == "mia-local")

        # 5 · [VERIFICAR] no se comprime (se preserva verbatim)
        cc3 = ContextCompressor()
        convo_v = make_convo(50, marker_at=12)  # el 12 está en el medio
        out_v = cc3.compress(convo_v, 1000)
        check("[VERIFICAR] preservado verbatim tras comprimir",
              any("[VERIFICAR] art. 90 CPACA" in _text(m) for m in out_v))
        check("el [VERIFICAR] NO quedó dentro del resumen",
              "[VERIFICAR] art. 90 CPACA" not in out_v[5]["content"])
        check("con [VERIFICAR] preservado la estructura crece a 37", len(out_v) == 37)

        # 6 · resumen en español jurídico
        summary_content = out[5]["content"]
        check("resumen en español (contiene 'Hechos jurídicos')", "Hechos jurídicos" in summary_content)
        check("el resumen NO trae marcador en inglés", "[CONTEXT SUMMARY]" not in summary_content)
        check("el preamble manda escribir en ESPAÑOL",
              "ESPAÑOL" in fake.chat.completions.last["messages"][0]["content"])

        # 7 · evento en la traza JSONL
        with tempfile.TemporaryDirectory() as tmp:
            tc = TraceCapture(tmp)
            cc_tr = ContextCompressor(trace_capture=tc)
            cc_tr.compress(convo, 1000, tenant_id="t-evt", matter_id="m-1")
            events = tc.read("t-evt")
            ev = events[-1] if events else {}
            check("se escribió 1 evento en la traza", len(events) == 1)
            check("el evento es context_compressed (schema event)",
                  ev.get("schema") == "mia.trace.event.v1" and ev.get("type") == "context_compressed")
            check("el evento trae tokens_antes/tokens_despues/ratio_compresion",
                  all(k in ev for k in ("tokens_antes", "tokens_despues", "ratio_compresion")))
            check("ratio_compresion = despues/antes", abs(ev["ratio_compresion"] - ev["tokens_despues"] / ev["tokens_antes"]) < 0.01)

        # 8 · (A) resumen iterativo
        cc_it = ContextCompressor()
        cc_it.compress(convo, 1000)
        check("guarda el resumen previo para iterar", bool(cc_it._previous_summary))
        cc_it.compress(convo, 1000)  # segunda → iterativa
        check("la 2ª compresión es iterativa (usa 'RESUMEN PREVIO')",
              "RESUMEN PREVIO" in fake.chat.completions.last["messages"][1]["content"])

        # 9 · (B) anti-thrashing
        cc_at = ContextCompressor()
        cc_at._ineffective_count = 2
        out_at = cc_at.compress(convo, 1000)
        check("anti-thrashing: tras 2 compresiones inefectivas, no recomprime",
              out_at is convo and not cc_at.last_compressed)

        # Regresiones de ahorro: nunca reemplazar contexto por un candidato mayor.
        rejected_trace = SimpleNamespace(capture_event=lambda **kw: rejected_events.append(kw))
        rejected_events = []
        cc_bad = ContextCompressor(trace_capture=rejected_trace)
        cc_bad._previous_summary = "checkpoint vigente"
        attempts = []
        def oversized(turns):
            attempts.append(turns)
            return "texto " * 10000
        cc_bad._summarize = oversized
        rejected_results = []
        for _ in range(3):
            rejected = cc_bad.compress(convo, 1000, tenant_id="t-rejected")
            rejected_results.append(rejected is convo and not cc_bad.last_compressed
                                    and cc_bad.last_tokens_after == cc_bad.last_tokens_before)
        check("resumen mayor rechazado sin cambiar historial", all(rejected_results))
        check("rechazo conserva estadísticas del contexto devuelto",
              not cc_bad.last_compressed and cc_bad.last_tokens_after == cc_bad.last_tokens_before
              and cc_bad.last_savings_pct == 0)
        check("rechazos activan antithrashing tras dos intentos", len(attempts) == 2)
        check("rechazo conserva checkpoint y no emite éxito",
              cc_bad._previous_summary == "checkpoint vigente" and not rejected_events)
        equal_convo = [convo[0], {"role": "user", "content":
            f"{SUMMARY_PREFIX}\n{SPANISH_SUMMARY}\n\n{SUMMARY_END_MARKER}"}, convo[-1]]
        cc_equal = ContextCompressor(protect_first_n=1, protect_last_n=1)
        equal_out = cc_equal.compress(equal_convo, 1)
        check("candidato de igual tamaño también se rechaza",
              equal_out is equal_convo and not cc_equal.last_compressed
              and cc_equal._ineffective_count == 1)

        cc_iter = ContextCompressor()
        first_out = cc_iter.compress(convo, 1000)
        # Su propia salida más turnos nuevos: ruta de recompresión real.
        cc_iter.compress(first_out + make_convo(40), 1000)
        iterative_payload = fake.chat.completions.last["messages"][1]["content"]
        check("checkpoint propio aparece una sola vez al recomprimir",
              iterative_payload.count(SPANISH_SUMMARY) == 1)
        foreign = {"role": "user", "content": SUMMARY_PREFIX + "\nOTRO resumen con dato único"}
        foreign_convo = first_out[:6] + [foreign] + first_out[6:] + make_convo(40)
        cc_iter.compress(foreign_convo, 1000)
        check("resumen ajeno no se descarta por compartir prefijo",
              "OTRO resumen con dato único" in fake.chat.completions.last["messages"][1]["content"])
        cc_pending = ContextCompressor()
        cc_pending._previous_summary = "[VERIFICAR] pendiente único"
        pending = {"role": "user", "content":
            f"{SUMMARY_PREFIX}\n{cc_pending._previous_summary}\n\n{SUMMARY_END_MARKER}"}
        pending_convo = convo[:5] + [pending] + convo[5:]
        pending_out = cc_pending.compress(pending_convo, 1000)
        check("checkpoint propio con [VERIFICAR] permanece verbatim",
              any(m is pending for m in pending_out))
    finally:
        llm.reset_model_policy(_tok)
        llm._client = original_client

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    raise SystemExit(main())
