"""Gate estático: las rutas async nunca llaman embed_texts en el event loop."""
from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROUTES = (
    ROOT / "backend" / "mia" / "api" / "routes" / "ux.py",
    ROOT / "backend" / "mia" / "api" / "routes" / "matter_mail.py",
)


def _sync_embedding_calls(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    findings: list[str] = []
    for function in (node for node in ast.walk(tree) if isinstance(node, ast.AsyncFunctionDef)):
        for node in ast.walk(function):
            if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
                continue
            if node.func.attr == "embed_texts":
                findings.append(f"{function.name}:{node.lineno}")
    return findings


def main() -> None:
    findings = {str(path.relative_to(ROOT)): _sync_embedding_calls(path) for path in ROUTES}
    findings = {path: rows for path, rows in findings.items() if rows}
    assert not findings, f"embed_texts bloquea rutas async: {findings}"
    print("async embedding routes OK — llamadas síncronas enviadas a worker threads")


if __name__ == "__main__":
    main()
