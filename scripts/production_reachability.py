#!/usr/bin/env python3
"""Conservative, deterministic production reachability audit for Mia.

This tool reports candidates; it never edits or deletes application code.  A test
reference is recorded as evidence, but never makes a production symbol reachable.
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
from collections import Counter, deque
from pathlib import Path
from typing import Iterable

SOURCE_EXTENSIONS = {".py", ".ts", ".tsx", ".js", ".jsx", ".rs"}
NEXT_ROOT_NAMES = {"page", "layout", "route", "loading", "error", "not-found", "template", "default"}
TS_IMPORT = re.compile(r"(?:from\s+|import\s*\(|require\s*\()\s*['\"]([^'\"]+)['\"]")
TS_SYMBOL = re.compile(r"^(?:export\s+)?(?:async\s+)?(?:function|class|const|let|var|interface|type|enum)\s+([A-Za-z_$][\w$]*)", re.M)
RUST_MOD = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?mod\s+([A-Za-z_]\w*)\s*;", re.M)
RUST_SYMBOL = re.compile(r"^\s*(?:pub(?:\([^)]*\))?\s+)?(?:async\s+)?(?:fn|struct|enum|trait|type|const|static)\s+([A-Za-z_]\w*)", re.M)


def rel(path: Path, root: Path) -> str:
    return path.relative_to(root).as_posix()


def source_files(root: Path) -> list[Path]:
    areas = [root / "backend" / "mia", root / "frontend", root / "desktop" / "src-tauri" / "src"]
    ignored = {"node_modules", ".next", "target", "__pycache__"}
    found: list[Path] = []
    for area in areas:
        if not area.exists():
            continue
        for directory, dirs, names in os.walk(area):
            dirs[:] = sorted(d for d in dirs if d not in ignored)
            found.extend(Path(directory) / name for name in sorted(names) if Path(name).suffix in SOURCE_EXTENSIONS)
    return sorted(found)


def test_files(root: Path) -> list[Path]:
    area = root / "execution"
    return sorted(p for p in area.rglob("*") if p.is_file() and p.suffix in SOURCE_EXTENSIONS) if area.exists() else []


def resolve_python(name: str, current: Path, root: Path, level: int = 0) -> Path | None:
    base = root / "backend"
    if level:
        package = current.parent
        for _ in range(max(0, level - 1)):
            package = package.parent
        candidate = package.joinpath(*name.split(".")) if name else package
    else:
        if not name.startswith("mia"):
            return None
        candidate = base.joinpath(*name.split("."))
    for p in (candidate.with_suffix(".py"), candidate / "__init__.py"):
        if p.exists():
            return p
    return None


def python_edges(path: Path, root: Path) -> set[Path]:
    try:
        tree = ast.parse(path.read_text(encoding="utf-8-sig"))
    except (SyntaxError, UnicodeDecodeError):
        return set()
    edges: set[Path] = set()
    for node in ast.walk(tree):
        names: list[tuple[str, int]] = []
        if isinstance(node, ast.Import):
            names = [(alias.name, 0) for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            names = [(node.module or "", node.level)]
            names += [((node.module + "." if node.module else "") + a.name, node.level) for a in node.names]
        for name, level in names:
            target = resolve_python(name, path, root, level)
            if target:
                edges.add(target)
    return edges


def resolve_ts(spec: str, current: Path, root: Path) -> Path | None:
    if spec.startswith("@/"):
        base = root / "frontend" / spec[2:]
    elif spec.startswith("."):
        base = current.parent / spec
    else:
        return None
    choices = [base] if base.suffix in SOURCE_EXTENSIONS else [base.with_suffix(ext) for ext in (".ts", ".tsx", ".js", ".jsx")]
    choices += [base / ("index" + ext) for ext in (".ts", ".tsx", ".js", ".jsx")]
    return next((p.resolve() for p in choices if p.exists()), None)


def ts_edges(path: Path, root: Path) -> set[Path]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    return {target for spec in TS_IMPORT.findall(text) if (target := resolve_ts(spec, path, root))}


def rust_edges(path: Path) -> set[Path]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    result: set[Path] = set()
    for name in RUST_MOD.findall(text):
        for candidate in (path.parent / f"{name}.rs", path.parent / name / "mod.rs"):
            if candidate.exists():
                result.add(candidate.resolve())
                break
    return result


def roots_for(files: Iterable[Path], root: Path) -> tuple[set[Path], dict[str, list[str]]]:
    files = list(files)
    python = {p.resolve() for p in (root / "backend/mia/api/main.py", root / "backend/mia/api/run.py", root / "backend/mia/setup/first_run.py", root / "backend/mia/setup/maintenance.py") if p.exists()}
    ts = {p.resolve() for p in files if p.parent.is_relative_to(root / "frontend/app") and p.stem in NEXT_ROOT_NAMES}
    for name in ("middleware.ts", "middleware.tsx", "instrumentation.ts", "instrumentation.tsx", "next.config.ts", "next.config.js"):
        p = root / "frontend" / name
        if p.exists(): ts.add(p.resolve())
    rust = {p.resolve() for p in (root / "desktop/src-tauri/src/main.rs", root / "desktop/src-tauri/src/lib.rs") if p.exists()}
    all_roots = python | ts | rust
    return all_roots, {"python": sorted(rel(p, root) for p in python), "typescript": sorted(rel(p, root) for p in ts), "rust": sorted(rel(p, root) for p in rust)}


def symbols(path: Path) -> list[tuple[str, int, bool]]:
    text = path.read_text(encoding="utf-8-sig", errors="replace")
    if path.suffix == ".py":
        try: tree = ast.parse(text)
        except SyntaxError: return []
        return [(n.name, n.lineno, bool(getattr(n, "decorator_list", []))) for n in tree.body if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))]
    rx = RUST_SYMBOL if path.suffix == ".rs" else TS_SYMBOL
    return [(m.group(1), text.count("\n", 0, m.start()) + 1, False) for m in rx.finditer(text)]


def audit(root: Path) -> dict:
    root = root.resolve()
    files = source_files(root)
    canonical = {p.resolve(): p for p in files}
    roots, roots_by_language = roots_for(files, root)
    graph: dict[Path, set[Path]] = {}
    parse_errors: list[str] = []
    for p0 in files:
        p = p0.resolve()
        try:
            graph[p] = python_edges(p, root) if p.suffix == ".py" else rust_edges(p) if p.suffix == ".rs" else ts_edges(p, root)
            if p.suffix == ".py":
                package_root = (root / "backend" / "mia").resolve()
                parent = p.parent
                while parent.is_relative_to(package_root):
                    init = parent / "__init__.py"
                    if init.exists() and init.resolve() != p:
                        graph[p].add(init.resolve())
                    if parent == package_root:
                        break
                    parent = parent.parent
        except Exception as exc:  # audit must expose incomplete evidence
            graph[p] = set(); parse_errors.append(f"{rel(p, root)}: {type(exc).__name__}: {exc}")
    reachable: set[Path] = set()
    queue = deque(sorted(roots))
    while queue:
        p = queue.popleft()
        if p in reachable: continue
        reachable.add(p)
        queue.extend(sorted(graph.get(p, set()) - reachable))
    prod_counts = {p: Counter(re.findall(r"[A-Za-z_$][\w$]*", p.read_text(encoding="utf-8-sig", errors="replace"))) for p in reachable if p in canonical}
    total_prod = sum(prod_counts.values(), Counter())
    tests = test_files(root)
    test_counts = Counter(word for p in tests for word in re.findall(r"[A-Za-z_$][\w$]*", p.read_text(encoding="utf-8-sig", errors="replace")))
    candidates: list[dict] = []
    for p in files:
        rp = p.resolve(); is_live_file = rp in reachable
        if not is_live_file:
            candidates.append({"kind": "file", "path": rel(p, root), "confidence": "high", "reason": "No existe camino estático desde un entrypoint productivo.", "test_references": 0})
        for name, line, decorated in symbols(p):
            own_total = prod_counts.get(rp, Counter()).get(name, 0)
            prod_refs = total_prod.get(name, 0) - own_total
            own_refs = max(0, own_total - 1)
            test_refs = test_counts.get(name, 0)
            if is_live_file and (prod_refs or own_refs or decorated or name in {"main", "run"}):
                continue
            reason = "El símbolo aparece solo en pruebas; las pruebas no lo mantienen vivo." if test_refs else ("Su archivo no es alcanzable desde producción." if not is_live_file else "Sin referencias estáticas productivas fuera de su definición.")
            confidence = "high" if not is_live_file and not decorated else "medium"
            candidates.append({"kind": "symbol", "path": rel(p, root), "line": line, "symbol": name, "confidence": confidence, "reason": reason, "production_references": prod_refs + own_refs, "test_references": test_refs})
    edges = sorted({(rel(a, root), rel(b, root)) for a, bs in graph.items() for b in bs if b in canonical})
    candidates.sort(key=lambda c: (c["path"], c.get("line", 0), c["kind"]))
    payload = {"schema_version": 1, "policy": {"test_references_count_as_live": False, "automatic_deletion": False, "analysis": "conservative-static"}, "roots": roots_by_language, "summary": {"source_files": len(files), "reachable_files": len(reachable & set(canonical)), "unreachable_files": len(set(canonical) - reachable), "edges": len(edges), "candidates": len(candidates), "parse_errors": len(parse_errors)}, "parse_errors": sorted(parse_errors), "edges": [{"from": a, "to": b} for a, b in edges], "candidates": candidates}
    payload["fingerprint"] = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    return payload


def markdown(report: dict) -> str:
    s = report["summary"]
    lines = ["# Alcanzabilidad productiva de Mia", "", f"Huella reproducible: `{report['fingerprint']}`", "", "Este informe es informativo: no autoriza ni ejecuta eliminaciones. Las referencias desde pruebas no cuentan como uso productivo.", "", "## Resumen", "", f"- Archivos fuente: {s['source_files']}", f"- Alcanzables: {s['reachable_files']}", f"- No alcanzables: {s['unreachable_files']}", f"- Aristas: {s['edges']}", f"- Candidatos: {s['candidates']}", f"- Errores de análisis: {s['parse_errors']}", "", "## Candidatos", ""]
    for c in report["candidates"]:
        where = f"{c['path']}:{c['line']}" if "line" in c else c["path"]
        label = f" `{c.get('symbol')}`" if c.get("symbol") else ""
        lines.append(f"- **{c['confidence']}** · {c['kind']} · `{where}`{label}: {c['reason']} (tests: {c.get('test_references', 0)})")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--json", type=Path)
    parser.add_argument("--markdown", type=Path)
    parser.add_argument("--check", type=Path, help="Fail if deterministic JSON differs from this snapshot")
    args = parser.parse_args(argv)
    report = audit(args.root)
    rendered = json.dumps(report, indent=2, ensure_ascii=False, sort_keys=True) + "\n"
    if args.json: args.json.write_text(rendered, encoding="utf-8")
    if args.markdown: args.markdown.write_text(markdown(report), encoding="utf-8")
    if args.check and (not args.check.exists() or args.check.read_text(encoding="utf-8") != rendered):
        print(f"reachability snapshot differs: {args.check}", file=sys.stderr); return 1
    print(json.dumps(report["summary"], sort_keys=True))
    return 2 if report["parse_errors"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
