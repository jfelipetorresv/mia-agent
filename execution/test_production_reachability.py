from __future__ import annotations

import importlib.util
from pathlib import Path


SCRIPT = Path(__file__).parents[1] / "scripts" / "production_reachability.py"
SPEC = importlib.util.spec_from_file_location("production_reachability", SCRIPT)
assert SPEC and SPEC.loader
reachability = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reachability)


def put(root: Path, name: str, text: str) -> None:
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def fixture(tmp_path: Path) -> Path:
    put(tmp_path, "backend/mia/api/main.py", "from mia.live import live\nlive()\n")
    put(tmp_path, "backend/mia/live.py", "def live():\n    return 1\n")
    put(tmp_path, "backend/mia/dead.py", "def test_only():\n    return 2\n")
    put(tmp_path, "frontend/app/page.tsx", "import {live} from '@/lib/live'; export default function Page(){return live()}\n")
    put(tmp_path, "frontend/lib/live.ts", "export const live = () => 1\n")
    put(tmp_path, "frontend/lib/dead.ts", "export const onlyTest = () => 2\n")
    put(tmp_path, "desktop/src-tauri/src/main.rs", "mod live; fn main(){ live::go(); }\n")
    put(tmp_path, "desktop/src-tauri/src/live.rs", "pub fn go() {}\n")
    put(tmp_path, "desktop/src-tauri/src/dead.rs", "pub fn only_test() {}\n")
    put(tmp_path, "execution/test_dead.py", "from mia.dead import test_only\n# onlyTest only_test\n")
    return tmp_path


def test_cross_language_graph_and_test_only_is_not_live(tmp_path: Path) -> None:
    report = reachability.audit(fixture(tmp_path))
    reachable = {edge["to"] for edge in report["edges"]} | {edge["from"] for edge in report["edges"]}
    assert "backend/mia/live.py" in reachable
    assert "frontend/lib/live.ts" in reachable
    assert "desktop/src-tauri/src/live.rs" in reachable
    found = {(c.get("symbol"), c["path"]): c for c in report["candidates"]}
    for key in (("test_only", "backend/mia/dead.py"), ("onlyTest", "frontend/lib/dead.ts"), ("only_test", "desktop/src-tauri/src/dead.rs")):
        assert key in found
        assert "pruebas" in found[key]["reason"]


def test_report_is_deterministic_and_never_deletes(tmp_path: Path) -> None:
    root = fixture(tmp_path)
    first = reachability.audit(root)
    second = reachability.audit(root)
    assert first == second
    assert first["policy"]["automatic_deletion"] is False
    assert reachability.markdown(first) == reachability.markdown(second)


if __name__ == "__main__":  # verify.ps1 corre las suites como scripts: sin esto, "verde" sin correr nada
    import pytest
    raise SystemExit(pytest.main([__file__, "-q"]))
