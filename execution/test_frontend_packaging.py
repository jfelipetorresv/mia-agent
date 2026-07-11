"""
Mia · test_frontend_packaging.py — gate EN FRÍO del empaquetado del frontend Next.js
(Fase 1 · bloque instalador · frente B).

Verifica por string-literal (sin correr npm, sin red, sin lanzar procesos) que:
  1. frontend/next.config.mjs sigue declarando `output: "standalone"` (la salida
     que empaqueta el frontend sin exigir `npm install` completo en la máquina
     del abogado) Y conserva las cabeceras de seguridad (headers()) verificadas
     en el spike de Fase 1 (X-Frame-Options, CSP frame-ancestors, nosniff, etc.).
  2. packaging/build_frontend.ps1 existe y referencia los tres insumos que
     ensambla: server.js (standalone), .next/static (assets del cliente que
     standalone NO incluye) y public/ (si aparece).
  3. Si packaging/dist/mia-frontend/ ya existe (build corrido), que el ensamblado
     tiene server.js y node.exe (el runtime portable con el que arranca sin
     depender del Node del sistema).

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_frontend_packaging.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
FRONTEND = ROOT / "frontend"
PACKAGING = ROOT / "packaging"

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def main() -> int:
    print("== Empaquetado del frontend Next.js: gate en frío (Fase 1 · frente B) ==")

    # 1 · next.config.mjs: standalone + cabeceras de seguridad conservadas.
    next_config_path = FRONTEND / "next.config.mjs"
    check("frontend/next.config.mjs existe", next_config_path.is_file())
    next_config = next_config_path.read_text(encoding="utf-8")

    check(
        'next.config.mjs declara output: "standalone"',
        'output: "standalone"' in next_config or "output: 'standalone'" in next_config,
    )
    check(
        "next.config.mjs conserva headers() con X-Frame-Options: DENY",
        "X-Frame-Options" in next_config and "DENY" in next_config,
    )
    check(
        "next.config.mjs conserva CSP frame-ancestors 'none'",
        "frame-ancestors 'none'" in next_config or 'frame-ancestors "none"' in next_config,
    )
    check(
        "next.config.mjs conserva X-Content-Type-Options: nosniff",
        "X-Content-Type-Options" in next_config and "nosniff" in next_config,
    )
    check(
        "next.config.mjs conserva Referrer-Policy",
        "Referrer-Policy" in next_config,
    )
    check(
        "next.config.mjs conserva Permissions-Policy",
        "Permissions-Policy" in next_config,
    )

    # 2 · build_frontend.ps1 existe y referencia el ensamblaje completo.
    build_script_path = PACKAGING / "build_frontend.ps1"
    check("packaging/build_frontend.ps1 existe", build_script_path.is_file())
    build_script = build_script_path.read_text(encoding="utf-8")

    check(
        "build_frontend.ps1 referencia server.js (salida de standalone)",
        "server.js" in build_script,
    )
    check(
        "build_frontend.ps1 referencia .next/static o .next\\static (assets del cliente)",
        ".next/static" in build_script or ".next\\static" in build_script,
    )
    check(
        "build_frontend.ps1 contempla public/ (aunque hoy no exista en el repo)",
        "public" in build_script,
    )
    check(
        "build_frontend.ps1 referencia node.exe (runtime portable, no el del PATH)",
        "node.exe" in build_script,
    )
    check(
        "build_frontend.ps1 corre `npm run build` (o permite saltarlo explícitamente)",
        "npm run build" in build_script,
    )
    check(
        "build_frontend.ps1 valida el ensamblado con una prueba de humo (no asume éxito ciego)",
        "Invoke-WebRequest" in build_script and "StatusCode" in build_script,
    )

    # Fix M3 (revisor adversarial): la prueba de humo puede dar PASS falso si
    # el puerto ya está ocupado por un proceso ajeno ("squatter") que responde
    # 200 en su lugar. El script debe: (a) detectar puerto ocupado y resolverlo
    # (buscar uno libre), (b) detectar si el proceso murió durante el polling
    # (HasExited) y abortar con el stderr real en vez de esperar el timeout
    # completo, y (c) verificar identidad mínima tras el 200 (el proceso sigue
    # vivo y es efectivamente quien escucha en el puerto).
    check(
        "build_frontend.ps1 detecta un puerto ya ocupado antes de lanzar (evita squatter dando PASS falso)",
        "Test-PortListening" in build_script,
    )
    check(
        "build_frontend.ps1 busca automáticamente un puerto libre si el pedido está ocupado",
        "3190" in build_script,
    )
    check(
        "build_frontend.ps1 revisa $proc.HasExited dentro del lazo de polling y vuelca stderr antes de abortar",
        build_script.count("HasExited") >= 2,
    )
    check(
        "build_frontend.ps1 verifica identidad mínima tras el 200 (OwningProcess del listener == PID de nuestro proceso)",
        "OwningProcess" in build_script and "$proc.Id" in build_script,
    )

    # Fix m6 (revisor adversarial): selección de Node no determinista si hay
    # dos versiones en tools\node-portable\. Debe existir un pin de versión
    # exacta y el script debe leerlo y exigir esa carpeta exacta.
    node_version_pin_path = PACKAGING / "node-version.txt"
    check(
        "packaging/node-version.txt existe (pin de versión exacta de Node portable)",
        node_version_pin_path.is_file(),
    )
    check(
        "build_frontend.ps1 lee el pin packaging/node-version.txt para seleccionar Node de forma determinista",
        "node-version.txt" in build_script,
    )

    # 3 · si el ensamblado ya fue construido, validar su contenido mínimo.
    dist_dir = PACKAGING / "dist" / "mia-frontend"
    if dist_dir.exists():
        check(
            "packaging/dist/mia-frontend/server.js existe (ensamblado presente)",
            (dist_dir / "server.js").is_file(),
        )
        check(
            "packaging/dist/mia-frontend/node.exe existe (Node portable empaquetado)",
            (dist_dir / "node.exe").is_file(),
        )
        check(
            "packaging/dist/mia-frontend/.next/static existe (assets del cliente ensamblados)",
            (dist_dir / ".next" / "static").is_dir(),
        )
        check(
            "packaging/dist/mia-frontend/node_modules existe (subconjunto mínimo de standalone)",
            (dist_dir / "node_modules").is_dir(),
        )
    else:
        print("  (packaging/dist/mia-frontend no existe todavía — se omiten los checks de contenido; corre packaging/build_frontend.ps1 primero)")

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
