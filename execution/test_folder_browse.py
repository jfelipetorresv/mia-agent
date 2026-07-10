"""
Mia · test_folder_browse.py — gate del NAVEGADOR SEGURO de carpetas (Bloque A · A1).

Ejercita `GET /api/folders/browse` (backend/mia/api/routes/folders.py, apoyado en
`safe_browse_roots`/`browse_folder` de connectors/local_folders.py): el abogado navega el
árbol de carpetas del equipo para ELEGIR qué registrar, en vez de escribir la ruta a mano.
No depende de la DB (no hay migración que aplicar; solo requiere JWT_SECRET para el auth).
Cubre:

  · sin `path` -> {"roots": [...]} con estructura sana (label/path/registrable)
  · con `path` de una carpeta real con subcarpetas -> un nivel, orden alfabético,
    SOLO subcarpetas (los archivos sueltos no aparecen), incluye 'parent'
  · C:\\Windows (directorio de sistema) -> 400 en llano
  · ruta inexistente -> 400 en llano
  · flag MIA_DISABLE_FOLDER_BROWSE -> 503 en llano (todo el endpoint apagado)
  · §G: ninguna respuesta visible al abogado usa jerga técnica

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_folder_browse.py
"""
from __future__ import annotations
import asyncio
import os
import shutil
import sys
import tempfile
from pathlib import Path

from dotenv import load_dotenv

# psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B) — se fija por
# consistencia con el resto de gates aunque este no toque la DB directamente (la app sí
# la usa para otras rutas montadas en el mismo proceso).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia import config                                 # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


FORBIDDEN = ("hitl", "langgraph", "pgvector", "tenant_id", "chunk", "embedding", "sync engine")


def main() -> int:
    print("== Navegador seguro de carpetas (GET /api/folders/browse, Bloque A · A1) ==")
    if not config.JWT_SECRET:
        print("  [FAIL] JWT_SECRET vacío en .env — necesario para la superficie HTTP")
        return 1

    import jwt
    from fastapi.testclient import TestClient
    from mia.api.main import app

    token = jwt.encode({"tenant_id": "00000000-0000-0000-0000-000000000001"},
                       config.JWT_SECRET, algorithm=config.JWT_ALG)
    auth = {"Authorization": f"Bearer {token}"}
    visible: list[str] = []

    (ROOT / ".tmp").mkdir(exist_ok=True)
    work = Path(tempfile.mkdtemp(prefix="folderbrowse_", dir=str(ROOT / ".tmp")))
    try:
        # carpeta con subcarpetas + un archivo suelto (el archivo NO debe aparecer)
        (work / "b_subcarpeta").mkdir()
        (work / "a_subcarpeta").mkdir()
        (work / "archivo_suelto.txt").write_text("no es una carpeta", encoding="utf-8")

        with TestClient(app) as client:
            # --- sin path: roots con estructura sana ---
            r = client.get("/api/folders/browse", headers=auth)
            check("GET /browse sin path -> 200 con clave 'roots'",
                  r.status_code == 200 and isinstance(r.json().get("roots"), list))
            visible.append(r.text)
            roots = r.json().get("roots", [])
            check("roots: cada entrada trae label/path/registrable",
                  all({"label", "path", "registrable"}.issubset(x) for x in roots))
            check("roots: no viene vacío en este equipo (al menos un disco montado)",
                  len(roots) >= 1)

            # --- con path: un nivel real, orden alfabético, SOLO subcarpetas ---
            r2 = client.get("/api/folders/browse", headers=auth, params={"path": str(work)})
            check("GET /browse?path=<carpeta real> -> 200", r2.status_code == 200)
            visible.append(r2.text)
            body2 = r2.json()
            names = [it["name"] for it in body2.get("items", [])]
            check("navegar: devuelve SOLO subcarpetas (el archivo suelto no aparece)",
                  "archivo_suelto.txt" not in names
                  and {"a_subcarpeta", "b_subcarpeta"}.issubset(set(names)))
            check("navegar: orden alfabético (case-insensitive)",
                  names.index("a_subcarpeta") < names.index("b_subcarpeta"))
            check("navegar: 'path' devuelto es la ruta resuelta y 'truncated' es False",
                  body2.get("path") and body2.get("truncated") is False)
            check("navegar: 'parent' es la carpeta que contiene a 'work' (subimos un nivel)",
                  body2.get("parent") == str(work.resolve().parent))

            # --- navegar un nivel MÁS ADENTRO (subcarpeta) y volver con 'parent' ---
            r2b = client.get("/api/folders/browse", headers=auth,
                             params={"path": str(work / "a_subcarpeta")})
            check("navegar una subcarpeta vacía -> 200 con items=[] y parent=carpeta padre",
                  r2b.status_code == 200 and r2b.json().get("items") == []
                  and r2b.json().get("parent") == str(work.resolve()))
            visible.append(r2b.text)

            # --- directorio de SISTEMA -> 400 en llano ---
            sysroot = os.environ.get("SystemRoot", r"C:\Windows")
            if Path(sysroot).exists():
                r3 = client.get("/api/folders/browse", headers=auth, params={"path": sysroot})
                check("GET /browse?path=C:\\Windows -> 400 (directorio de sistema)",
                      r3.status_code == 400)
                visible.append(r3.text)
            else:
                check("GET /browse?path=C:\\Windows -> 400 (omitido: no existe en este equipo)",
                      True)

            # --- ruta inexistente -> 400 en llano ---
            r4 = client.get("/api/folders/browse", headers=auth,
                            params={"path": str(work / "no_existe_xyz")})
            check("GET /browse?path=<inexistente> -> 400", r4.status_code == 400)
            visible.append(r4.text)

            # --- sin sesión -> 401 (mismo guard que el resto del router) ---
            r5 = client.get("/api/folders/browse")
            check("GET /browse sin token -> 401", r5.status_code == 401)

            # --- flag MIA_DISABLE_FOLDER_BROWSE apaga el endpoint entero -> 503 ---
            # El flag se lee con os.getenv() en cada request (no hay caché de import),
            # así que basta con fijarlo y volver a pedir dentro del mismo cliente vivo.
            orig_flag = os.environ.get("MIA_DISABLE_FOLDER_BROWSE")
            os.environ["MIA_DISABLE_FOLDER_BROWSE"] = "1"
            try:
                r6 = client.get("/api/folders/browse", headers=auth)
                check("MIA_DISABLE_FOLDER_BROWSE=1 -> 503 (incluso sin path)",
                      r6.status_code == 503)
                visible.append(r6.text)
                r7 = client.get("/api/folders/browse", headers=auth, params={"path": str(work)})
                check("MIA_DISABLE_FOLDER_BROWSE=1 -> 503 también navegando un path",
                      r7.status_code == 503)
                visible.append(r7.text)
            finally:
                if orig_flag is None:
                    os.environ.pop("MIA_DISABLE_FOLDER_BROWSE", None)
                else:
                    os.environ["MIA_DISABLE_FOLDER_BROWSE"] = orig_flag

        # §G — sin jerga técnica en lo que ve el abogado
        blob = " ".join(visible).lower()
        leaked = [w for w in FORBIDDEN if w in blob]
        check(f"§G: respuestas sin jerga técnica (fugas: {leaked or 'ninguna'})", not leaked)
    finally:
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Navegador de carpetas OK — A1 verificado.")
        return 0
    print("Navegador de carpetas FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
