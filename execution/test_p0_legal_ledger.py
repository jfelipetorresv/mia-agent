"""Gate P0: huellas, recibos y edición literal antes de tocar una base real.

Es un test puro deliberadamente: prueba los invariantes que no pueden depender de
que una instalación local ya haya aplicado las migraciones 051--053.
"""
from __future__ import annotations

import sys
import asyncio
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.memory import legal_ledger, citation_seals  # noqa: E402
from mia.api.routes.hitl import ApproveBody  # noqa: E402


FAILED: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    if not ok:
        FAILED.append(name)


def main() -> int:
    original = "Texto de Mia."
    abogado = "Texto final exacto de la abogada."
    check("la huella es estable", legal_ledger.content_hash(original) == legal_ledger.content_hash(original))
    check("una edición invalida la huella anterior",
          legal_ledger.content_hash(original) != legal_ledger.content_hash(abogado))

    check("un informe sin alertas y APTO habilita el gate de citas",
          legal_ledger.verification_passes({"citas": 0, "marcadas": 0, "anotadas": 0,
                                             "omitidas": 0, "quemadas": 0,
                                             "gate_llm": {"veredicto": "apto"}}))
    for key in ("marcadas", "anotadas", "omitidas", "quemadas"):
        check(f"{key} bloquea un final", not legal_ledger.verification_passes({key: 1}))
    check("hallazgos independientes bloquean un final",
          not legal_ledger.verification_passes({"gate_llm": {"veredicto": "hallazgos"}}))
    check("sin informe nunca equivale a verificado", not legal_ledger.verification_passes(None))
    check("verificador no disponible bloquea final",
          not legal_ledger.verification_passes({"gate_llm": {"veredicto": "unavailable"}}))

    graph = (ROOT / "backend/mia/agents/graph.py").read_text(encoding="utf-8")
    editing = graph[graph.index("if status == \"editing\":"):graph.index("else:\n            # approved / rejected", graph.index("if status == \"editing\":"))]
    check("la edición usa exactamente edited_text", "final = str(decision.get(\"edited_text\") or \"\")" in editing)
    check("el LLM posterior solo verifica y no reescribe la edición",
          "Devuelve el borrador corregido" not in editing
          and "Versión exacta editada por el abogado (no la reescribas)" in editing)
    check("el final exige ambos recibos", all(g in legal_ledger.REQUIRED_FINAL_GATES for g in
                                               ("citation_verification", "human_approval")))

    try:
        ApproveBody()
        missing_hash_rejected = False
    except Exception:
        missing_hash_rejected = True
    check("la API rechaza aprobar sin huella", missing_hash_rejected)
    try:
        ApproveBody(draft_hash="a" * 64)
        missing_attestation_rejected = False
    except Exception:
        missing_attestation_rejected = True
    check("la API rechaza aprobar sin atestación humana", missing_attestation_rejected)
    check("la atestación válida queda ligada al hash",
          ApproveBody(draft_hash="a" * 64, attested=True).attested is True)
    sel = ApproveBody(
        draft_hash="a" * 64, attested=True,
        argument_selection={"include": ["A1"], "exclude": ["A2"]})
    check("ApproveBody acepta argument_selection (ids incluir/excluir)",
          sel.argument_selection is not None
          and sel.argument_selection.include == ["A1"]
          and sel.argument_selection.exclude == ["A2"])

    sql = (ROOT / "backend/mia/db/migrations/052_legal_gate_receipts.sql").read_text(encoding="utf-8")
    check("recibos quedan ligados a artifact_hash", "artifact_hash" in sql and "passed boolean NOT NULL" in sql)
    seal_sql = (ROOT / "backend/mia/db/migrations/053_citation_seals_hash_bound.sql").read_text(encoding="utf-8")
    check("sellos fijan pasaje, artefacto y jurisdicción",
          all(col in seal_sql for col in ("source_passage_hash", "artifact_hash", "jurisdiction_codes")))
    history_sql = (ROOT / "backend/mia/db/migrations/057_legal_ledger_history.sql").read_text(encoding="utf-8")
    check("recibos conservan corrida, traza, versión y contexto",
          all(col in history_sql for col in ("run_id", "trace_id", "checker_version",
                                              "context_hash", "source_hashes")))
    ledger_source = (ROOT / "backend/mia/memory/legal_ledger.py").read_text(encoding="utf-8")
    check("el último recibo decide y permite FAIL a PASS posterior",
          "PARTITION BY gate_name ORDER BY created_at DESC, id DESC" in ledger_source)
    check("cada exportación final queda registrada", "legal_export_events" in ledger_source)
    check("las salidas finales tienen lector (no write-only)", "def list_exports" in ledger_source)
    check("un hash distinto invalida el recibo HITL", "recibo-invalidado" in graph)
    check("los sellos nacen solo después de final_ready",
          'and md.get("final_ready")' in graph
          and "seal_from_approved_report" in graph)
    # Auditoría 2026-08-14: el LEDGER decide antes de capturar la traza; una traza
    # 'approved' sin final registrado alimentaba wiki/banco de oro/skills con turnos no
    # verificados. El desenlace efectivo (verification_required si no hay final) es el
    # que viaja a la traza y al índice.
    i_ledger = graph.index("md[\"final_ready\"] = await legal_ledger.finalise_if_gated")
    i_outcome = graph.index("outcome_efectivo = HITL_OUTCOME.get(status")
    i_capture = graph.index("trace = self.trace_capture.capture")
    check("el ledger corre ANTES de capturar la traza", i_ledger < i_capture)
    check("la traza y el índice llevan el desenlace EFECTIVO, no el crudo",
          i_outcome < i_capture
          and graph.count("hitl_outcome=outcome_efectivo") == 2
          and '"verification_required"' in graph)

    passage = hashlib.sha256(b"pasaje vigente").hexdigest()
    seal = {"citation": "Ley 1", "source_passage_hash": passage,
            "artifact_hash": "a" * 64, "jurisdiction_codes": ["co"]}
    old_list = citation_seals.list_seals
    async def _fake_list(_tenant: str):
        return [seal]
    citation_seals.list_seals = _fake_list
    try:
        compatible = asyncio.run(citation_seals.list_compatible_seals(
            "t", source_hashes={passage}, jurisdictions=["co"]))
        changed = asyncio.run(citation_seals.list_compatible_seals(
            "t", source_hashes={hashlib.sha256(b"pasaje cambiado").hexdigest()}, jurisdictions=["co"]))
    finally:
        citation_seals.list_seals = old_list
    check("el sello solo se reutiliza con el mismo pasaje", compatible == [seal])
    check("mutar la fuente invalida el sello", changed == [])

    if FAILED:
        print("FAIL:", ", ".join(FAILED))
        return 1
    print("PASS: P0 conserva la versión humana y no emite final sin recibos de su huella.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
