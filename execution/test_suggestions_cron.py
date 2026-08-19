"""Gate: generate_suggestions vive en el scheduler de producción."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.cron import build_scheduler  # noqa: E402
from mia.cron.scheduler import generate_suggestions_all_tenants  # noqa: E402
from mia.cron.suggestions import generate_suggestions  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    if not ok:
        FAILED.append(name)


def main() -> int:
    names = {j["name"] for j in build_scheduler().list_jobs()}
    check("build_scheduler registra generate_suggestions", "generate_suggestions" in names)
    check("el job apunta al productor all-tenants",
          callable(generate_suggestions_all_tenants) and callable(generate_suggestions))
    src = (ROOT / "backend" / "mia" / "cron" / "scheduler.py").read_text(encoding="utf-8")
    check("el invocador de producción nombra generate_suggestions",
          "generate_suggestions_all_tenants" in src
          and 'register_job("generate_suggestions"' in src)
    if FAILED:
        print("FAIL:", ", ".join(FAILED))
        return 1
    print("PASS: sugerencias cableadas al cron.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
