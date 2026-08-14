"""Gate estático: migraciones reejecutables no pueden reducir vocabularios acumulados."""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MIG = ROOT / "backend" / "mia" / "db" / "migrations"


def values(path: str, constraint: str) -> set[str]:
    text = (MIG / path).read_text(encoding="utf-8")
    match = re.search(
        rf"ADD CONSTRAINT\s+{re.escape(constraint)}\s+CHECK\s*\([^;]+?IN\s*\(([^)]+)\)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"{path}: no se encontró {constraint}")
    return set(re.findall(r"'([^']+)'", match.group(1)))


def main() -> int:
    checks: list[tuple[str, bool]] = []

    origin = {"upload", "folder", "mail", "drive", "mia"}
    for path in ("027_remote_sources.sql", "028_projects_multifolder.sql"):
        checks.append((f"{path}: origen acumulativo", origin <= values(path, "ck_documents_origin")))

    proposals = {
        "improve_playbook", "new_playbook", "flag_gap", "wiki_correction",
        "weekly_report", "soul_rule", "harvest_lessons",
    }
    for path in (
        "010_feedback_proposal_types.sql",
        "040_soul_versions.sql",
        "049_feedback_proposal_harvest.sql",
    ):
        checks.append((f"{path}: tipos acumulativos", proposals <= values(
            path, "feedback_proposals_proposal_type_check")))

    durable_once = (MIG / "056_durable_learning_once.sql").read_text(encoding="utf-8")
    checks.append((
        "056_durable_learning_once.sql: señales inmutables no se duplican",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_durable_learning_once" in durable_once
        and all(name in durable_once for name in (
            "wiki_approved_artifact", "learn_approved_artifact",
            "skill_improvement", "harvest_lessons")),
    ))

    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n{passed}/{len(checks)} checks PASS")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
