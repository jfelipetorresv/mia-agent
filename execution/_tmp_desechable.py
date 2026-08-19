"""Mia · _tmp_desechable — directorio de trabajo DESECHABLE, fail-before-create (A-MAY2).

Helper COMÚN de los gates (extraído de test_eval_spend_guard.py en la ronda 3 de Codex, que
reprodujo `mkdtemp` a punto de escribir DENTRO del repo cuando el temporal del sistema resuelve
ahí). Dos reglas, y las dos se COMPRUEBAN en vez de confiarse:

1. NUNCA dentro del repo, y se FALLA ANTES de crear nada si no puede cumplirlo.
   `tempfile.gettempdir()` cae a `os.getcwd()` cuando TMP/TEMP/TMPDIR no están puestos o apuntan
   a algo que no existe — y como los gates se lanzan con el cwd en la raíz del repo, ahí es donde
   aparecían los temporales que ensuciaban el árbol de trabajo. Si el temporal del sistema
   resuelve dentro de la raíz del repo, se levanta `SystemExit` con instrucción clara ANTES de
   crear ningún desechable: fail-closed de arranque, no ensuciar y descubrirlo después.
2. Se BORRA al terminar (`atexit`), pase o falle el gate.

`repo_root` se detecta desde la ubicación de ESTE módulo (execution/ → raíz), de modo que el
criterio "dentro del repo" es el MISMO para todos los gates que lo importen.
"""
from __future__ import annotations

import atexit
import shutil
import tempfile
from pathlib import Path

# execution/_tmp_desechable.py → parents[1] = raíz del repo (la que NO se debe ensuciar).
REPO_ROOT = Path(__file__).resolve().parents[1]


def tmpdir_desechable(prefix: str, *, repo_root: Path = REPO_ROOT) -> Path:
    """Crea y devuelve un directorio temporal FUERA del repo, con limpieza garantizada.

    Levanta `SystemExit` (HALT) ANTES de crear nada si el temporal del sistema resuelve dentro
    de `repo_root` — no se ensucia el árbol de trabajo bajo ninguna circunstancia.
    """
    base = Path(tempfile.gettempdir()).resolve()
    try:
        dentro_del_repo = base == repo_root or repo_root in base.parents or base.is_relative_to(repo_root)
    except AttributeError:  # pragma: no cover — Python < 3.9
        dentro_del_repo = str(base).startswith(str(repo_root))
    if dentro_del_repo:
        # NO se crea un temporal dentro del repo: se corta aquí, antes de escribir nada.
        raise SystemExit(
            f"[HALT] el temporal del SISTEMA resuelve DENTRO del repo ({base}); este gate no "
            "puede crear su directorio desechable en el árbol de trabajo (ensuciaría el repo). "
            f"Pon TMP/TEMP (o TMPDIR) apuntando a una carpeta FUERA de {repo_root} y vuelve a "
            "lanzar el gate.")
    tmp = Path(tempfile.mkdtemp(prefix=prefix, dir=str(base)))
    atexit.register(lambda: shutil.rmtree(tmp, ignore_errors=True))
    return tmp
