"""Gate estático de migraciones: vocabularios acumulados e inmutabilidad histórica.

Dos propiedades, ambas con mutación posible:
  1 · VOCABULARIO ACUMULADO: la ÚLTIMA migración que define cada CHECK enumerado
      contiene el vocabulario completo del esquema vigente (regla 2026-08-12:
      una migración reejecutable no recorta tipos añadidos después).
      2 · INMUTABILIDAD: ninguna migración listada en config/migration_shas.json
      cambia después de registrada. El SHA es canónico LF (CRLF de un checkout
      Windows no cuenta como cambio). El ledger de db_bootstrap es fail-closed
      (MigrationChecksumError) y una edición "inofensiva" de un SQL histórico
      bloquea el arranque de TODA instalación existente al actualizar (P0
      encontrado 2026-08-14: el commit 05c8f8c editó 010/027/040/049).
      Una migración NUEVA se registra aquí a propósito:
        python execution/test_migration_contracts.py --sellar
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
MIG = ROOT / "backend" / "mia" / "db" / "migrations"
MANIFEST = ROOT / "config" / "migration_shas.json"

from mia.setup.db_bootstrap import migration_sha256  # noqa: E402


def last_owner(constraint: str) -> Path:
    """La migración con número más alto que define (ADD CONSTRAINT) el CHECK."""
    owners = [p for p in sorted(MIG.glob("*.sql"))
              if re.search(rf"ADD CONSTRAINT\s+{re.escape(constraint)}\b",
                           p.read_text(encoding="utf-8"), flags=re.IGNORECASE)]
    if not owners:
        raise AssertionError(f"ninguna migración define {constraint}")
    return owners[-1]


def values(path: Path, constraint: str) -> set[str]:
    text = path.read_text(encoding="utf-8")
    match = re.search(
        rf"ADD CONSTRAINT\s+{re.escape(constraint)}\s+CHECK\s*\([^;]+?IN\s*\(([^)]+)\)",
        text,
        flags=re.IGNORECASE | re.DOTALL,
    )
    if not match:
        raise AssertionError(f"{path.name}: no se encontró {constraint}")
    return set(re.findall(r"'([^']+)'", match.group(1)))


def main() -> int:
    if "--sellar" in sys.argv:
        manifest = {p.name: migration_sha256(p) for p in sorted(MIG.glob("*.sql"))}
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n",
                            encoding="utf-8")
        print(f"manifiesto sellado: {len(manifest)} migraciones")
        return 0

    checks: list[tuple[str, bool]] = []

    # 1 · vocabulario acumulado en la última dueña de cada CHECK
    origin = {"upload", "folder", "mail", "drive", "mia"}
    owner = last_owner("ck_documents_origin")
    checks.append((f"{owner.name}: origen acumulativo (última dueña)",
                   origin <= values(owner, "ck_documents_origin")))

    proposals = {
        "improve_playbook", "new_playbook", "flag_gap", "wiki_correction",
        "weekly_report", "soul_rule", "harvest_lessons",
    }
    owner = last_owner("feedback_proposals_proposal_type_check")
    checks.append((f"{owner.name}: tipos acumulativos (última dueña)",
                   proposals <= values(owner, "feedback_proposals_proposal_type_check")))

    durable_once = (MIG / "056_durable_learning_once.sql").read_text(encoding="utf-8")
    checks.append((
        "056_durable_learning_once.sql: señales inmutables no se duplican",
        "CREATE UNIQUE INDEX IF NOT EXISTS uq_durable_learning_once" in durable_once
        and all(name in durable_once for name in (
            "wiki_approved_artifact", "learn_approved_artifact",
            "skill_improvement", "harvest_lessons")),
    ))

    # 2 · inmutabilidad contra el manifiesto sellado
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    current = {p.name: migration_sha256(p) for p in sorted(MIG.glob("*.sql"))}
    changed = sorted(n for n in manifest if n in current and current[n] != manifest[n])
    missing = sorted(n for n in manifest if n not in current)
    new = sorted(n for n in current if n not in manifest)
    checks.append(("ninguna migración registrada cambió "
                   + (f"(CAMBIARON: {changed} — crea una migración nueva)" if changed else ""),
                   not changed))
    checks.append(("ninguna migración registrada desapareció "
                   + (f"(FALTAN: {missing})" if missing else ""), not missing))
    checks.append(("toda migración nueva está sellada en el manifiesto "
                   + (f"(SIN SELLAR: {new} — corre --sellar a propósito)" if new else ""),
                   not new))

    for name, ok in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    passed = sum(ok for _, ok in checks)
    print(f"\n{passed}/{len(checks)} checks PASS")
    return 0 if passed == len(checks) else 1


if __name__ == "__main__":
    raise SystemExit(main())
