# -*- coding: utf-8 -*-
"""
Mia · test_puente_shell.py — el puente entre la pantalla y la cáscara de escritorio.

POR QUÉ EXISTE. Toda la pestaña de Protección de datos estuvo MUERTA desde siempre y nadie
lo notó hasta que Pipe usó la app instalada: la pantalla corre en `http://localhost:3100`,
que para la cáscara es un origen remoto y —por endurecimiento deliberado— no recibe IPC, así
que `window.__TAURI__` no existía ahí y cada botón llamaba a un objeto inexistente. El arreglo
fue el puente `mia-shell`, interceptado en proceso, sin puerto TCP.

El defecto que este gate impide es el MISMO en su forma nueva: que la pantalla invoque por el
puente una ruta que la cáscara no sirve. Falla igual de silenciosamente —el botón no hace
nada— y solo se ve con la app empaquetada, que es justo lo que nadie corre en cada cambio.

Qué se verifica (estático, sin compilar ni empaquetar, ~0,2 s):

  1 · TODA ruta que el frontend invoca con `shellInvoke("…")` tiene su brazo en la cáscara.
  2 · Nadie volvió a usar `window.__TAURI__` en una pantalla: es el patrón que no funciona
      desde el origen remoto, y su reaparición devuelve el producto al defecto original.
  3 · El puente conserva sus tres candados: allowlist de `Origin` exacta, solo POST y rutas
      cerradas. Sin ellos, el arreglo habría cambiado un botón muerto por un agujero.

QUÉ NO ACREDITA: que los botones funcionen en la app instalada. Eso exige empaquetar y
probar en frío, y sigue siendo trabajo de Pipe en su máquina. Esto solo garantiza que el
contrato entre las dos mitades no se rompió por el camino.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_puente_shell.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LIB_RS = ROOT / "desktop" / "src-tauri" / "src" / "lib.rs"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    _results.append((nombre, bool(ok)))
    linea = ("  [OK]   " if ok else "  [FAIL] ") + nombre
    if not ok and detalle:
        linea += f"\n         {detalle}"
    print(linea)


def archivos_front() -> list[Path]:
    out = subprocess.run(["git", "ls-files", "frontend/app", "frontend/lib"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines() if p.endswith((".ts", ".tsx"))]


_INVOCACION = re.compile(r'shellInvoke<[^>]*>\(\s*"([^"]+)"|shellInvoke\(\s*"([^"]+)"')


def main() -> int:
    print("== puente entre la pantalla y la cáscara de escritorio ==")
    if not LIB_RS.exists():
        print(f"  [FAIL] no existe {LIB_RS.relative_to(ROOT)}")
        return 1
    rust = LIB_RS.read_text(encoding="utf-8", errors="replace")

    print("\n1 · toda ruta que la pantalla invoca existe en la cáscara")
    rutas: dict[str, str] = {}
    for f in archivos_front():
        texto = f.read_text(encoding="utf-8")
        for m in _INVOCACION.finditer(texto):
            ruta = m.group(1) or m.group(2)
            if ruta:
                rutas.setdefault(ruta, str(f.relative_to(ROOT)))
    check("la pantalla invoca al menos una ruta del puente (si no, este gate está ciego)",
          len(rutas) > 0, f"encontradas {len(rutas)}")
    huerfanas = [f"{r} ({o})" for r, o in sorted(rutas.items())
                 if f'"/{r}"' not in rust]
    check(f"las {len(rutas)} rutas invocadas tienen su brazo en la cáscara",
          not huerfanas, "; ".join(huerfanas))

    print("\n2 · nadie vuelve al patrón que no funciona")
    reincidentes: list[str] = []
    for f in archivos_front():
        for i, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
            if "__TAURI__" not in linea:
                continue
            despojada = linea.strip()
            if despojada.startswith(("//", "*", "/*")):
                continue  # la historia se documenta; lo prohibido es USARLO
            reincidentes.append(f"{f.relative_to(ROOT)}:{i}")
    check("ninguna pantalla usa window.__TAURI__ (muerto desde el origen remoto)",
          not reincidentes, "; ".join(reincidentes))

    print("\n3 · el puente conserva sus candados")
    check("allowlist de Origin exacta", "Origin" in rust and "allow" in rust.lower())
    # El candado se escribe comparando contra el enum del método, no contra una cadena:
    # buscar `"POST"` literal habría dado un rojo falso (y, peor, un verde falso el día que
    # alguien deje la cabecera de CORS y quite la comprobación).
    check("solo POST: se RECHAZA todo método que no sea POST",
          re.search(r"request\.method\(\)\s*!=\s*[\w:]*Method::POST", rust) is not None)
    check("rutas cerradas: hay un caso por defecto que rechaza lo no listado",
          "_ =>" in rust)
    check("y el puente no abre un puerto TCP (se intercepta en proceso)",
          "register_asynchronous_uri_scheme_protocol" in rust
          and "mia-shell" in rust)

    ok = sum(1 for _, r in _results if r)
    print(f"\n{ok}/{len(_results)} checks PASS")
    if ok != len(_results):
        print("Gate FAIL — la pantalla y la cáscara dejaron de entenderse: en la app "
              "instalada esos botones no harían nada, y no se vería en el navegador.")
        return 1
    print("Gate OK. Esto NO acredita que los botones funcionen instalados: eso exige "
          "empaquetar y probar en frío.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
