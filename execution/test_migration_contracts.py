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

from dotenv import load_dotenv  # noqa: E402

# Sin esto, la comprobación de conducta buscaba la base en el puerto por defecto
# (5432), no la encontraba, y devolvía «no evaluado» — que antes pasaba como
# verde. Un gate que aprueba porque no pudo medir es peor que no tenerlo.
load_dotenv(ROOT / ".env")

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


def _vocabulario_tras_ejecutar(helper: str, constraint: str) -> set | None:
    """Ejecuta el helper de init y devuelve los valores del CHECK que quedan en la base.

    None si no hay base con la que medir (el gate lo dice en vez de aprobar en silencio).
    Se ejecuta en un proceso aparte, con el mismo intérprete y el mismo PYTHONPATH que usa
    la suite, para que el efecto medido sea exactamente el que tendría en una máquina real.
    """
    import os
    import subprocess
    try:
        import psycopg
    except Exception:  # noqa: BLE001
        return None
    kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres",
              password=os.getenv("PG_PASSWORD", ""))
    try:
        with psycopg.connect(connect_timeout=5, **kw):
            pass
    except Exception:  # noqa: BLE001
        return None

    entorno = dict(os.environ, PYTHONPATH=str(ROOT / "backend"), PYTHONUTF8="1")
    res = subprocess.run([sys.executable, str(ROOT / "execution" / helper)],
                         cwd=str(ROOT), capture_output=True, text=True, env=entorno,
                         timeout=180)
    if res.returncode != 0:
        # Que el helper REVIENTE es precisamente el síntoma del defecto (CheckViolation
        # sobre una fila legítima): se cuenta como vocabulario vacío, o sea culpable.
        return set()
    with psycopg.connect(autocommit=True, **kw) as c:
        fila = c.execute(
            "SELECT pg_get_constraintdef(oid) FROM pg_constraint WHERE conname = %s",
            (constraint,)).fetchone()
    if not fila:
        return set()
    return set(re.findall(r"'([^']+)'::", fila[0])) or set(re.findall(r"'([^']+)'", fila[0]))


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

    # 1-bis · NINGÚN helper de init retrocede un vocabulario acumulado.
    # Dos veces en dos sesiones el mismo defecto: `init_dreams.py` re-aplicaba la 010 y
    # `init_soul_versions.py` la 040, y ambas reemplazan el CHECK de `feedback_proposals`
    # con la lista de tipos de SU momento. El síntoma es un CheckViolation que parece «fila
    # corrupta en la base» y en realidad es el helper.
    #
    # SE MIDE LA CONDUCTA, NO EL TEXTO. La primera versión de este check exoneraba al helper
    # si el nombre de la migración vigente aparecía en su código: una constante sin usar, o
    # un comentario, bastaban para absolverlo — o sea, vigilaba una cadena de texto, no un
    # comportamiento. Ahora se EJECUTA el helper contra la base y se lee el CHECK que deja.
    # Un gate escrito para que un defecto no vuelva una tercera vez no puede depender de que
    # alguien conserve un literal.
    sospechosos: list[tuple[str, str, str, set]] = []   # (helper, sql, constraint, vigente)
    for constraint in ("feedback_proposals_proposal_type_check", "ck_documents_origin"):
        duena = last_owner(constraint)
        vigente = values(duena, constraint)
        for sql in sorted(MIG.glob("*.sql")):
            if sql.name == duena.name:
                continue
            texto = sql.read_text(encoding="utf-8")
            if not re.search(rf"ADD CONSTRAINT\s+{re.escape(constraint)}\b", texto,
                             flags=re.IGNORECASE):
                continue
            # Protegida por una guarda `IF NOT EXISTS`: no reemplaza nada (caso de la 025).
            if not re.search(rf"DROP CONSTRAINT IF EXISTS\s+{re.escape(constraint)}", texto,
                             flags=re.IGNORECASE):
                continue
            # Con el vocabulario COMPLETO: aplicarla no retrocede (caso de la 028).
            if not (values(sql, constraint) < vigente):
                continue
            for helper in sorted((ROOT / "execution").glob("init_*.py")):
                if sql.name in helper.read_text(encoding="utf-8"):
                    sospechosos.append((helper.name, sql.name, constraint, vigente))

    culpables: list[str] = []
    no_evaluados: list[str] = []
    for helper, sql_name, constraint, vigente in sospechosos:
        veredicto = _vocabulario_tras_ejecutar(helper, constraint)
        if veredicto is None:
            no_evaluados.append(f"{helper} (sin base)")
            continue
        faltan = vigente - veredicto
        if faltan:
            culpables.append(
                f"{helper} re-aplica {sql_name} y deja {constraint} SIN {sorted(faltan)}")
    # NO EVALUADO NO ES APROBADO. Si hay helpers sospechosos y la base no está disponible
    # para ejecutarlos, este check REPRUEBA diciendo por qué: aprobar sin haber medido es la
    # forma más silenciosa de que el defecto vuelva por tercera vez.
    if culpables:
        detalle = "CULPABLES: " + "; ".join(culpables)
    elif no_evaluados:
        detalle = ("NO SE PUDO MEDIR (hace falta la base para ejecutarlos): "
                   + ", ".join(no_evaluados))
    else:
        detalle = f"{len(sospechosos)} helper(s) sospechoso(s) EJECUTADO(s) y verificado(s)"
    checks.append((
        "ningún helper de init retrocede un vocabulario acumulado · " + detalle,
        not culpables and not no_evaluados))

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
