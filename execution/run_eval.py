"""
Mia · run_eval.py — corre el banco de pruebas de calidad EN VIVO (CP-E4, Ola 5).

Uso (con los servicios vivos: Postgres + LiteLLM :4000 + política de modelo):

    .venv\\Scripts\\python.exe execution\\run_eval.py                 # corrida "antes/después"
    .venv\\Scripts\\python.exe execution\\run_eval.py --run-id mi_corrida
    .venv\\Scripts\\python.exe execution\\run_eval.py --compare A B     # compara dos corridas ya hechas

Corre los CASOS DE ORO SINTÉTICOS de `mia.eval.cases` por el grafo completo de asunto,
puntúa cada uno con señales deterministas (disciplina de citas, cierre del diagnóstico,
borrador) y guarda la corrida en `mia-data/eval-runs/{run_id}/`. Para medir si un cambio
mejora o empeora la calidad: corre ANTES (en main), corre DESPUÉS (en la rama) y
`--compare antes despues`.

Crea un despacho EFÍMERO de prueba y lo borra al terminar (incl. sus checkpoints). NO usa
datos reales de cliente: eso exige el candado `allow_eval_real_data` del despacho (fail-closed).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agents.state import thread_id_for            # noqa: E402
from mia.db import pool                                # noqa: E402
from mia.eval import compare_reports                   # noqa: E402
from mia.eval import harness                           # noqa: E402

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)


def _make_eval_tenant() -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES('[eval] banco de pruebas') RETURNING id"
        ).fetchone()[0])


def _drop_eval_tenant(tenant_id: str, matter_ids: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for mid in matter_ids:
            tid = thread_id_for(tenant_id, mid)
            for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                try:
                    c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (tid,))
                except Exception:  # noqa: BLE001 — limpieza best-effort
                    pass
        c.execute("DELETE FROM tenants WHERE id = %s", (tenant_id,))


def _print_summary(report: dict) -> None:
    s = report.get("summary", {})
    print(f"\n=== Corrida {report['run_id']} ===")
    print(f"  Casos: {s.get('n_casos')} · llegaron a borrador: {s.get('n_llegaron_a_borrador')}"
          f" · sin problemas: {s.get('n_sin_problemas')} · con error: {s.get('n_con_error')}")
    print(f"  Total de citas SIN respaldo (a verificar): {s.get('total_citas_sin_respaldo')}")
    for c in report.get("cases", []):
        sc = c.get("score", {})
        flags = ", ".join(sc.get("flags", [])) or "ok"
        err = f" ERROR: {c['error']}" if c.get("error") else ""
        print(f"  · {c['case_id']}: citas={sc.get('citas')} sin_respaldo="
              f"{sc.get('citas_sin_respaldo')} cierre={sc.get('has_diagnosis_closing')} "
              f"borrador={sc.get('draft_chars')}c [{flags}]{err}")


def _load_report(run_id: str) -> dict:
    run_dir = Path(harness._eval_dir()) / run_id
    cases = []
    with (run_dir / "cases.jsonl").open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                cases.append(json.loads(line))
    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8")).get("summary", {})
    return {"run_id": run_id, "cases": cases, "summary": summary}


async def _run(run_id: str) -> dict:
    await pool.open_pool()
    tenant_id = _make_eval_tenant()
    matter_ids: list[str] = []
    try:
        report = await harness.run_suite(tenant_id, run_id=run_id)
        matter_ids = [c.get("matter_id") for c in report.get("cases", []) if c.get("matter_id")]
        harness.persist_report(report)
        return report
    finally:
        await pool.close_pool()
        _drop_eval_tenant(tenant_id, matter_ids)


def main() -> int:
    ap = argparse.ArgumentParser(description="Banco de pruebas de calidad de Mia (CP-E4)")
    ap.add_argument("--run-id", default=None, help="id de la corrida (default: eval_<fecha>)")
    ap.add_argument("--compare", nargs=2, metavar=("ANTES", "DESPUES"),
                    help="compara dos corridas ya guardadas por su run_id")
    args = ap.parse_args()

    if args.compare:
        before, after = _load_report(args.compare[0]), _load_report(args.compare[1])
        result = compare_reports(before, after)
        print(f"\n=== Comparación {args.compare[0]} → {args.compare[1]} ===")
        print(f"  Veredicto: {result['overall'].upper()}  "
              f"(regresiones={result['n_regresiones']} mejoras={result['n_mejoras']} "
              f"sin_cambio={result['n_sin_cambio']})")
        for c in result["cases"]:
            det = "; ".join(c["regressions"] + c["improvements"]) or "sin cambios"
            print(f"  · {c['case_id']}: {c['verdict'].upper()} — {det}")
        return 0

    run_id = args.run_id or f"eval_{datetime.now():%Y%m%d_%H%M%S}"
    report = asyncio.run(_run(run_id))
    _print_summary(report)
    print(f"\nGuardada en mia-data/eval-runs/{run_id}/. "
          f"Corre otra en la otra rama y usa --compare para el veredicto.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
