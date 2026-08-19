"""Gate: el puente de Telegram arranca con el API (opt-in)."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.channels import telegram_bridge as tb  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FAILED: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    if not ok:
        FAILED.append(name)


def main() -> int:
    check("sin token: skipped (opt-in, no tumba)",
          tb.start_bridge_if_configured({"TELEGRAM_BOT_TOKEN": ""}) == "skipped")
    check("token a medias: incomplete, no arranca el bot",
          tb.start_bridge_if_configured({"TELEGRAM_BOT_TOKEN": "123:AA"}) == "incomplete")
    lifespan = (ROOT / "backend" / "mia" / "api" / "main.py").read_text(encoding="utf-8")
    check("el lifespan del API invoca start_bridge_if_configured",
          "start_bridge_if_configured" in lifespan)
    docs = (ROOT / "docs" / "telegram-setup.md").read_text(encoding="utf-8")
    check("la guía documenta TELEGRAM_BOT_TOKEN y el arranque con el API",
          "TELEGRAM_BOT_TOKEN" in docs and "mia.api.run" in docs)
    if FAILED:
        print("FAIL:", ", ".join(FAILED))
        return 1
    print("PASS: puente Telegram opt-in en el lifespan.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
