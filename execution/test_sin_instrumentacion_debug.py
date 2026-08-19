"""
Mia · test_sin_instrumentacion_debug.py — barrera: NINGUNA instrumentación de
depuración puede llegar al producto (ni al código fuente, ni al bundle que se
le instala al abogado).

POR QUÉ EXISTE (sesión 52, lección con barrera · regla 55-61 de APRENDIZAJES):
una sesión de depuración dejó bloques `#region agent log` inyectados en
`frontend/app/_components/MailboxSection.tsx`, `frontend/app/configurar/page.tsx`
y `backend/mia/api/routes/mailbox.py`. Nadie los quitó, el árbol de trabajo
siguió "sucio" sin que nada lo notara, y al recompilar los payloads ESE CÓDIGO
VIAJÓ DENTRO DEL INSTALADOR: un chunk de Next.js ya compilado hacía POST a
`http://127.0.0.1:7610/ingest/...` desde la máquina del abogado. Se detectó por
casualidad al revisar `git status` antes de un commit. Sin barrera, vuelve.

Qué se verifica (dos capas, ninguna opcional):

  1. FUENTE (siempre verificable, nunca puede quedar en PASS vacío): ningún
     archivo de `frontend/app/`, `frontend/lib/` ni `backend/mia/` contiene los
     marcadores que las herramientas de depuración agéntica inyectan.

  2. BUNDLE (cuando `packaging/dist/` existe, es decir tras un ensamblaje): los
     payloads ya compilados tampoco los contienen. Esta capa es la que de hecho
     falló: la capa 1 sola no basta porque el bundle puede venir de un árbol
     sucio anterior. Si `packaging/dist/` no existe, se declara explícitamente
     como NO EVALUADA en la salida (no se cuenta como check aprobado).

Los marcadores son literales de herramienta, no heurísticas de estilo: no
disparan sobre un `console.log` normal ni sobre logging legítimo del producto.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_sin_instrumentacion_debug.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Literales que inyectan las herramientas de depuración agéntica. Cada uno se
# eligió por ser inequívoco: ninguno aparece en código de producto legítimo.
MARCADORES = (
    "#region agent log",
    "#endregion agent log",
    "X-Debug-Session-Id",
    "127.0.0.1:7610",
    "/ingest/",
)

# Dónde miramos la FUENTE. Se listan carpetas de producto; no tests ni scripts
# de diagnóstico, que sí pueden instrumentar a propósito.
FUENTE_DIRS = (
    ROOT / "frontend" / "app",
    ROOT / "frontend" / "lib",
    ROOT / "backend" / "mia",
)
FUENTE_EXTS = {".ts", ".tsx", ".js", ".jsx", ".py"}

# Dónde miramos el BUNDLE ya compilado.
DIST = ROOT / "packaging" / "dist"
BUNDLE_EXTS = {".js", ".mjs", ".cjs", ".py", ".json", ".html"}
# El payload de LiteLLM y el de Postgres son dependencias de terceros: no son
# código nuestro y meterlos multiplica el barrido por decenas de miles de
# archivos sin ganar nada. Se barren los payloads que SÍ salen de este repo.
BUNDLE_SUBDIRS = ("mia-frontend", "mia-backend")

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    _results.append((nombre, ok))
    marca = "[OK]  " if ok else "[FAIL]"
    linea = f"  {marca} {nombre}"
    if not ok and detalle:
        linea += f" — {detalle}"
    print(linea)


def _archivos(base: Path, exts: set[str]) -> list[Path]:
    if not base.is_dir():
        return []
    return [p for p in base.rglob("*") if p.is_file() and p.suffix.lower() in exts]


def _buscar(archivos: list[Path]) -> dict[str, list[str]]:
    """marcador -> rutas (relativas al repo) donde aparece."""
    hallazgos: dict[str, list[str]] = {}
    for path in archivos:
        try:
            texto = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        for marcador in MARCADORES:
            if marcador in texto:
                hallazgos.setdefault(marcador, []).append(
                    str(path.relative_to(ROOT))
                )
    return hallazgos


def main() -> int:
    print("== barrera · sin instrumentación de depuración en el producto ==")

    # --- 1 · FUENTE ---------------------------------------------------------
    print("\n1 · código fuente del producto")
    fuente: list[Path] = []
    for d in FUENTE_DIRS:
        fuente.extend(_archivos(d, FUENTE_EXTS))
    # Anti-gate-ciego: si el barrido no encontró archivos, el gate no está
    # probando NADA y debe reprobar en vez de quedarse verde para siempre.
    check(
        "el barrido de fuente encontró archivos que revisar (gate no ciego)",
        len(fuente) > 50,
        f"solo {len(fuente)} archivos; ¿cambió el layout del repo?",
    )
    hallazgos_fuente = _buscar(fuente)
    for marcador in MARCADORES:
        rutas = hallazgos_fuente.get(marcador, [])
        check(
            f"fuente sin el marcador {marcador!r}",
            not rutas,
            f"{len(rutas)} archivo(s): {', '.join(rutas[:4])}",
        )

    # --- 2 · BUNDLE ---------------------------------------------------------
    print("\n2 · payloads compilados (packaging/dist)")
    bundle: list[Path] = []
    for sub in BUNDLE_SUBDIRS:
        bundle.extend(_archivos(DIST / sub, BUNDLE_EXTS))
    if not bundle:
        print(
            "  [NO EVALUADO] no hay payloads en packaging/dist — esta capa se "
            "verifica tras ensamblar (packaging\\build_installer.ps1). "
            "NO cuenta como aprobada."
        )
    else:
        check(
            "el barrido del bundle encontró archivos que revisar (gate no ciego)",
            len(bundle) > 20,
            f"solo {len(bundle)} archivos en dist",
        )
        hallazgos_bundle = _buscar(bundle)
        for marcador in MARCADORES:
            rutas = hallazgos_bundle.get(marcador, [])
            check(
                f"bundle sin el marcador {marcador!r}",
                not rutas,
                f"{len(rutas)} archivo(s): {', '.join(rutas[:4])}",
            )

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed != total:
        print(
            "Instrumentación de depuración detectada. Quítala del código y "
            "RE-ENSAMBLA el instalador: un bundle viejo puede traerla aunque la "
            "fuente ya esté limpia."
        )
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
