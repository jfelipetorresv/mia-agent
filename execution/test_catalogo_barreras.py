"""Gate: catálogo barrera ↔ productor ↔ invocador + lanzador /health 200."""
from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FAILED: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    if not ok:
        FAILED.append(name)


def _resolve(spec: str):
    mod_name, _, attr = spec.partition(":")
    mod = importlib.import_module(mod_name)
    obj = mod
    for part in attr.split("."):
        obj = getattr(obj, part)
    return obj


def main() -> int:
    catalog_path = ROOT / "config" / "catalogo-barreras.json"
    data = json.loads(catalog_path.read_text(encoding="utf-8"))
    invariantes = data.get("invariantes") or []
    check("el catálogo declara invariantes duras", bool(invariantes))
    for item in invariantes:
        if item.get("dureza") != "dura":
            continue
        iid = item.get("id") or "?"
        for spec in item.get("simbolos") or []:
            try:
                _resolve(spec)
                found = True
            except Exception:
                found = False
            check(f"{iid}: símbolo de producción {spec}", found)

    from fastapi.testclient import TestClient
    from mia.api.main import app

    with TestClient(app) as client:
        r = client.get("/health")
    check("lanzador: GET /health → 200 (python -m mia.api.run)", r.status_code == 200)
    body = r.json() if r.status_code == 200 else {}
    check("health identifica a Mia (db/status)", "status" in body and "db" in body)
    check("health expone capacidades OCR/voz (optional_capabilities vivo)",
          isinstance((body.get("capabilities") or {}).get("ocr"), dict)
          and isinstance((body.get("capabilities") or {}).get("voice"), dict)
          and "anydoc" in (body.get("capabilities") or {}))

    if FAILED:
        print("FAIL:", ", ".join(FAILED))
        return 1
    print("PASS: catálogo de barreras con invocador de producción.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
