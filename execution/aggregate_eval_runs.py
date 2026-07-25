# -*- coding: utf-8 -*-
"""Agrega varios run-ids de eval (trozos de un mismo caso) en un run agregado.

Por qué existe: un factor externo de la máquina de desarrollo mata árboles de
procesos largos (2026-07-22, causa sin identificar), así que las N repeticiones
de un caso pueden correrse en TROZOS foreground cortos (`--repeat 1..2`) que
persisten cada uno su run-id. Este script reconstruye el run de N corridas:
concatena los crudos (cases.jsonl) y RECALCULA panel y tasa de fuga con las
mismas funciones del harness — no copia números de los resúmenes parciales, los
deriva de los crudos, que es lo que un auditor debe poder reproducir.

Regla dura: todas las partes deben compartir `version.prompt_hash`. Agregar
corridas de prompts distintos produce un baseline incomparable; se aborta.

Uso:
  python execution/aggregate_eval_runs.py --out f1_susc_fuga_20260722 \
      --case fuga-jurisdiccion-contrato-sin-pais \
      --parts f1_susc_fuga_20260722_p1 f1_susc_fuga_20260722_p2 ...
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from mia.eval import harness  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", required=True, help="run_id del agregado a escribir")
    ap.add_argument("--case", required=True, help="case_id que todas las partes deben compartir")
    ap.add_argument("--parts", nargs="+", required=True, help="run_ids de los trozos, en orden")
    ap.add_argument("--exige-evidencia", action="store_true",
                    help="reprueba si alguna parte corrió sin MIA_EVAL_PERSIST_FULL=1 (su "
                         "borrador quedó truncado al preview y no se puede releer). Úsalo en "
                         "sondas de RISK_CASES destinadas a revisión humana.")
    args = ap.parse_args()

    eval_dir = Path(harness._eval_dir())
    results: list[dict] = []
    hashes: dict[str, str] = {}
    modelos: dict[str, int] = {}
    spends: dict[str, dict] = {}
    for part in args.parts:
        run_dir = eval_dir / part
        summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
        version = summary.get("version") or {}
        hashes[part] = version.get("prompt_hash") or "?"
        for alias, n in (version.get("modelos_servidos") or {}).items():
            modelos[alias] = modelos.get(alias, 0) + n
        spends[part] = summary.get("spend") or {}
        with (run_dir / "cases.jsonl").open(encoding="utf-8") as f:
            part_results = [json.loads(line) for line in f if line.strip()]
        if not part_results:
            print(f"ERROR: {part} no tiene corridas en cases.jsonl")
            return 1
        results.extend(part_results)

    if len(set(hashes.values())) != 1 or "?" in hashes.values():
        print(f"ERROR: prompt_hash distinto o ausente entre partes — no son agregables: {hashes}")
        return 1

    leak = harness.jurisdiction_leak_rate(results)
    panel = harness.build_quality_panel(results)
    # EVIDENCIA AUDITABLE: los números salen del texto completo aunque no se haya persistido
    # (se calculan en run_case), pero sin `draft_full` nadie puede RELEER el borrador. Ver
    # `harness.evidence_audit`: el 2026-07-24 un agregado de sonda adversarial se publicó con
    # una corrida sin texto y nada lo advirtió.
    evidencia = harness.evidence_audit(results)
    report = {
        "run_id": args.out,
        "case_id": args.case,
        "n": len(results),
        "cases": results,
        "leak": leak,
        "panel": panel,
        "evidencia": evidencia,
        # El gasto NO se suma: cada snapshot es de su proceso. Se conservan por
        # parte para que el auditor los confronte uno a uno.
        "spend": {"agregado_de_partes": spends},
        "version": {"prompt_hash": next(iter(hashes.values())),
                    "modelos_servidos": modelos},
        "summary": {"repeat_agregado": {"case_id": args.case, "n": len(results),
                                        "leak": leak, "partes": args.parts}},
    }
    run_dir = harness.persist_report(report)
    print(f"Agregado {args.out}: {len(results)} corridas de {len(args.parts)} partes -> {run_dir}")
    print(f"  fuga: {leak['n_con_fuga']}/{leak['n']} ({leak['tasa']:.0%}) · prompt_hash: {report['version']['prompt_hash']}")
    if not evidencia["completa"]:
        print(f"  AVISO — EVIDENCIA INCOMPLETA: {evidencia['sin_texto']} de {evidencia['n']} "
              f"corridas se guardaron sin texto completo (corridas sin "
              f"MIA_EVAL_PERSIST_FULL=1; índices {evidencia['indices_sin_texto']}). Los "
              f"números NO están comprometidos —se calcularon sobre el texto entero—, pero "
              f"esos borradores YA NO SE PUEDEN RELEER: no los lleve a una revisión humana.")
        if args.exige_evidencia:
            print("REPRUEBA: se exigió evidencia completa y falta texto en alguna parte.")
            return 1
    else:
        print(f"  evidencia: {evidencia['con_texto']}/{evidencia['n']} corridas con texto "
              f"completo releíble.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
