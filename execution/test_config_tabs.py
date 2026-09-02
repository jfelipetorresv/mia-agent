"""
Mia · test_config_tabs.py — gate del checkpoint C3: Configuración en subtabs shadcn
con deep-links por hash.

No toca la DB ni el API: es un gate por string-literal sobre el código fuente del
frontend (mismo patrón de run_frontend_checks() en execution/test_second_brain_ui.py),
porque lo que hay que garantizar es texto/estructura presente en el archivo, no
comportamiento en runtime (eso lo cubre Playwright/QA manual).

ACTUALIZADO 2026-08-19 (bloque 3 del rediseño Luxury): la página pasó de OCHO
pestañas a CINCO. Este gate ya NO congela cuántas pestañas hay — congelaba una
disposición concreta, que es justo lo que había que poder mejorar. Lo que sí
congela, porque es lo que rompe a terceros, es que TODOS los anclas históricos
(#conexiones, #carpetas, #automatizaciones, #valor, #calidad, #proteccion,
#asistentes) sigan resolviendo a una pestaña Y a una sección con ese mismo `id`.

Cubre:
  1. configurar/page.tsx importa Tabs/TabsList/TabsTrigger/TabsContent de shadcn.
  2. Las 5 pestañas nuevas y el mapa hash→tab con TODOS los anclas históricos,
     cada uno con su <section id> todavía presente en la página.
  3. Sincronía con hash viva: 'hashchange' + 'replaceState'.
  4. 'La salud de Mia' se conserva; 'Primeros pasos' presente; contador en el trigger.
  5. Compatibilidad externa intacta: setup.py, dashboard/page.tsx, FuentesPanel.tsx y
     OneDriveFolderPicker.tsx siguen apuntando a los anclas /configurar#... de siempre.
  6. La nav de chips vieja (SECCIONES_NAV / <a href="#...">) desapareció.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_config_tabs.py
"""
from __future__ import annotations

import sys
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def main() -> int:
    print("== Configuración: subtabs shadcn + deep-links por hash (CP-C3) ==")

    configurar = (ROOT / "frontend" / "app" / "configurar" / "page.tsx").read_text(encoding="utf-8")

    # 1. Import de shadcn Tabs
    check(
        "importa Tabs/TabsList/TabsTrigger/TabsContent de @/components/ui/tabs",
        "TabsList" in configurar
        and "TabsTrigger" in configurar
        and "TabsContent" in configurar
        and '@/components/ui/tabs"' in configurar,
    )

    # 2. Las 5 pestañas + el mapa hash→tab con TODOS los anclas históricos
    check(
        "las 5 pestañas están presentes (value=)",
        all(
            f'value="{tid}"' in configurar
            for tid in ["primeros-pasos", "conexiones", "automatizaciones", "valor", "sistema"]
        ),
    )
    check(
        "el mapa hash→tab conserva TODOS los anclas históricos",
        all(
            f'"{h}"' in configurar
            for h in ["#conexiones", "#carpetas", "#automatizaciones", "#valor",
                      "#calidad", "#proteccion", "#asistentes"]
        ),
    )
    # Un hash que resuelve a una pestaña pero no encuentra su sección deja al
    # abogado mirando otra cosa: la sección tiene que seguir existiendo con su id.
    proteccion_tsx = (ROOT / "frontend" / "app" / "_components" / "ProteccionDatosSection.tsx").read_text(encoding="utf-8")
    check(
        "cada ancla histórico tiene todavía su <section id=...>",
        all(f'id="{sec}"' in configurar
            for sec in ["conexiones", "carpetas", "asistentes", "automatizaciones", "calidad", "sistema"])
        and 'id="proteccion"' in proteccion_tsx,
    )
    check(
        "el deep-link a una sección sin pestaña propia hace scroll a su id",
        "scrollToAnchor" in configurar and "anchorFromHash" in configurar,
    )

    # 3. Deep-link vivo (sincronía con hash, no solo al montar)
    check("escucha 'hashchange'", "hashchange" in configurar)
    check("usa 'replaceState' al cambiar de tab", "replaceState" in configurar)

    # 4. Literales de producto conservados + contador en el trigger
    check("'La salud de Mia' se conserva", "La salud de Mia" in configurar)
    check("'Primeros pasos' presente", "Primeros pasos" in configurar)
    check(
        "el trigger de Primeros pasos muestra el contador (s.completados/s.total)",
        "s.completados" in configurar and "s.total" in configurar,
    )
    # Las filas cerradas son selectores de un paso, no un acordeón persistente: al hacer
    # clic se reemplazan por la tarjeta abierta. No deben declarar `aria-controls` hacia un
    # panel que no existe mientras la fila está cerrada.
    check(
        "las filas cerradas no apuntan por ARIA a paneles inexistentes",
        "aria-controls={idPanel}" not in configurar and "const idPanel" not in configurar,
    )

    # 5. Compatibilidad externa: nadie que enlace a /configurar#... quedó roto
    setup_py = (ROOT / "backend" / "mia" / "api" / "routes" / "setup.py").read_text(encoding="utf-8")
    dashboard = (ROOT / "frontend" / "app" / "dashboard" / "page.tsx").read_text(encoding="utf-8")
    fuentes = (ROOT / "frontend" / "app" / "_components" / "FuentesPanel.tsx").read_text(encoding="utf-8")
    onedrive = (ROOT / "frontend" / "app" / "_components" / "OneDriveFolderPicker.tsx").read_text(encoding="utf-8")

    check("setup.py sigue enlazando a /configurar#conexiones", "/configurar#conexiones" in setup_py)
    check("setup.py sigue enlazando a /configurar#carpetas", "/configurar#carpetas" in setup_py)
    check("dashboard/page.tsx sigue enlazando a /configurar#valor", "/configurar#valor" in dashboard)
    check("FuentesPanel.tsx sigue enlazando a /configurar#conexiones", "/configurar#conexiones" in fuentes)
    check("OneDriveFolderPicker.tsx sigue enlazando a /configurar#conexiones", "/configurar#conexiones" in onedrive)

    # 6. La nav de chips vieja desapareció (los triggers la reemplazan)
    check(
        "SECCIONES_NAV / <a href=\"#...\"> viejos ya no están",
        "SECCIONES_NAV" not in configurar and '<a href="#' not in configurar,
    )

    # 7. CP-HUB/CP-ORO · las dos capacidades que tenían API pero ninguna pantalla.
    # Los ayudantes viven DENTRO de Conexiones (son otra cosa que Mia puede usar);
    # el Banco de oro tiene tab propio y NO va en "Valor y gasto": aquello es dinero
    # y esto es un examen de calidad.
    root = Path(__file__).resolve().parents[1]
    asistentes = (root / "frontend" / "app" / "_components" / "AsistentesSection.tsx").read_text(encoding="utf-8")
    oro = (root / "frontend" / "app" / "_components" / "BancoOroSection.tsx").read_text(encoding="utf-8")
    check("Ayudantes externos montados en Configuración",
          "AsistentesSection" in configurar and 'id="asistentes"' in configurar)
    # El Banco de oro dejó de tener pestaña propia (bloque 3): vive dentro de
    # "Trabajo automático", que es donde tiene sentido — sigue SIN mezclarse con
    # "Valor y gasto", que era el riesgo real que este check protegía.
    check("Banco de oro montado, con deep-link #calidad a su sección",
          "BancoOroSection" in configurar
          and '"#calidad": { tab: "automatizaciones", anchor: "calidad" }' in configurar
          and 'id="calidad"' in configurar)
    # El riesgo que este check protege: que "calidad" acabe leyéndose como dinero.
    # Basta con que el Banco de oro no viva en el mismo TabsContent que el valor.
    check("el Banco de oro NO quedó dentro de «Valor y gasto»",
          configurar.index("<BancoOroSection />") < configurar.index("<ValorGastoSection"))
    # El contrato que costó encontrar: el router de settings NO lleva prefijo /api
    # (mismo bug que en su día dejó la bienvenida sin guardar el motor elegido).
    check("Ayudantes: ruta real /settings/agents (sin el prefijo /api)",
          "/settings/agents" in asistentes and "/api/settings/agents" not in asistentes)
    check("Banco de oro: permiso por /settings/eval-consent (sin /api) y casos por /api/gold-cases",
          "/settings/eval-consent" in oro and "/api/settings/eval-consent" not in oro
          and "/api/gold-cases" in oro)
    # La captura la arma el servidor: el material sin anonimizar no debe pasar por el
    # navegador. Si alguien vuelve a mandar el texto en el body, este check lo caza.
    check("Banco de oro: la captura se pide sin cuerpo (el servidor arma el caso)",
          "gold-cases:draft" in oro)
    # §G y honestidad: el aviso del gate y las notas del backend se muestran, no se
    # reescriben; y la pantalla nunca promete que el caso quedó limpio.
    check("Ayudantes: la pantalla usa el aviso y el bloqueo que manda el backend",
          "aviso_consentimiento" in asistentes and "bloqueado_por_politica" in asistentes)
    check("Banco de oro: muestra las notas del backend (aviso, nota_pii, nota_captura)",
          all(k in oro for k in ("aviso", "nota_pii", "nota_captura")))

    # 8. BLOQUE 3 · la galería de herramientas reconocibles y su honestidad.
    galeria = (ROOT / "frontend" / "app" / "_components" / "GaleriaHerramientas.tsx").read_text(encoding="utf-8")
    check("la galería está montada al frente de Conexiones",
          "GaleriaHerramientas" in configurar and 'id="herramientas"' in configurar)
    check("la galería lee el estado REAL de los endpoints que ya existían",
          all(ep in galeria for ep in ("/api/welcome/status", "/api/mailbox/status",
                                       "/api/obsidian/status", "/api/notebooklm/status", "/health")))
    # 2026-08-19 · decisión de Pipe: Google Drive SÍ es conector de Mia, al nivel de
    # OneDrive. El check se invierte, pero solo vale si el conector es REAL: la tarjeta
    # tiene que leer el estado del mismo campo `archivos` que ya reporta
    # /api/mailbox/status, y el backend tiene que traer de verdad el cliente de Drive y su
    # scope de solo lectura. Si mañana se borra el conector, este gate cae.
    check("la galería ofrece Google Drive con el estado real de conexiones[].archivos",
          'nombre: "Google Drive"' in galeria and "google?.archivos" in galeria)
    google_drive_py = ROOT / "backend" / "mia" / "connectors" / "google_drive.py"
    check("el conector de Google Drive existe y pide solo lectura (drive.readonly)",
          google_drive_py.exists()
          and "drive.readonly" in google_drive_py.read_text(encoding="utf-8"))
    oauth_py = (ROOT / "backend" / "mia" / "connectors" / "mailbox" / "oauth.py").read_text(encoding="utf-8")
    check("el permiso de archivos de Google se pide como scope incremental",
          "https://www.googleapis.com/auth/drive.readonly" in oauth_py
          and "include_granted_scopes" in oauth_py)
    # Honestidad: mientras la instalación no registre la aplicación de Google, la tarjeta
    # dice eso, no un estado inventado.
    check("la galería dice la verdad si falta registrar la aplicación de Google",
          "todavía no tiene registrada la aplicación de Google" in galeria)
    check("cada pestaña dice para qué sirve (TAB_HINTS)", "TAB_HINTS" in configurar)

    # 9. P3 · Badge (<div>) dentro de <p> en /configurar#conexiones: HTML inválido
    # que rompía la hidratación. No debe volver.
    asistentes_src = (ROOT / "frontend" / "app" / "_components" / "AsistentesSection.tsx").read_text(encoding="utf-8")
    check("Ayudantes: ningún <Badge> vive dentro de un <p>",
          "<p className=\"flex items-center gap-2 text-sm text-muted-foreground\">" not in asistentes_src)

    # 10. Protección de datos usa la primitiva Card, no clases de tarjeta cableadas.
    check("Protección de datos usa <Card>, no 'border-border bg-card shadow-sm' a mano",
          "<Card variant=" in proteccion_tsx
          and "rounded-xl border border-border bg-card" not in proteccion_tsx)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("Config tabs OK.")
        return 0
    print("Config tabs FAIL.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
