# -*- coding: utf-8 -*-
"""
Mia · test_sistema_de_diseno.py — barrera del rediseño Luxury en las pantallas del abogado.

POR QUÉ EXISTE. Tres veces el criterio de diseño se perdió en la ejecución: se entregaron
pantallas funcionales con las tarjetas dibujadas a mano —radio, borde y sombra cableados— y
cero usos de la primitiva del sistema, pese a que el encargo pedía el pack cada vez. La
corrección de Pipe del 2026-08-24 fue explícita: toda pantalla nueva o reescrita nace con el
rediseño, y el cotejo NO puede ser una instrucción en el encargo, porque la instrucción ya
falló tres veces. Esto es ese cotejo, ejecutable.

QUÉ COMPRUEBA (estático, sin navegador, ~0,3 s):

  1 · NINGUNA superficie dibuja una tarjeta a mano. Concretamente: no existe la combinación
      «radio + borde + fondo de tarjeta» escrita a pelo. O se usa `<Card>`, o se compone con
      el neumorfismo del sistema (`shadow-neu-raised` / `shadow-neu-sunken`).
  2 · Ninguna pantalla del abogado cablea un COLOR literal (hex o rgb) donde el sistema tiene
      un token. El tema claro/oscuro se rompe justo ahí: un `#060606` cableado fue la causa
      de la queja número uno de Pipe (la bienvenida salía negra con el tema claro).
  3 · La primitiva `<Card>` sigue construida sobre el neumorfismo del pack. Si alguien le
      quita la sombra a la primitiva, TODO el producto pierde el rediseño de una vez y
      ninguna de las dos comprobaciones anteriores se daría cuenta.

QUÉ NO COMPRUEBA, y hay que decirlo: que la pantalla se VEA bien. Esto mide propiedades
enumerables; la captura cotejada contra el render del pack sigue siendo necesaria y sigue
siendo trabajo de mirar la pantalla (regla 21: el verde de un gate no es calidad).

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_sistema_de_diseno.py
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend"

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


def pantallas() -> list[Path]:
    """Los .tsx del producto, por git (nunca un recorrido recursivo: el antivirus de esta
    máquina cuelga las búsquedas ingenuas sobre el árbol con node_modules)."""
    out = subprocess.run(["git", "ls-files", "frontend/app"], cwd=ROOT,
                         capture_output=True, text=True, check=True).stdout
    return [ROOT / p for p in out.splitlines() if p.endswith(".tsx")]


# Tarjeta a mano: radio + borde + fondo de tarjeta, sin el neumorfismo del sistema en la
# MISMA cadena de clases. `border-border/10` es la que compone la primitiva, así que una
# cadena que la use ya viene del sistema.
_RADIO = re.compile(r'\brounded-(?:md|lg|xl|2xl|3xl)\b')
_BORDE = re.compile(r'\bborder(?:-(?:border|white|black|input|primary|muted|foreground|'
                    r'accent|secondary|popover|card|dashed))?(?:/\d+)?\b')
_FONDO = re.compile(r'\bbg-(?:card|background|white|black|muted|secondary|popover|accent|'
                    r'primary)(?:/\d+)?\b')


def es_tarjeta_a_mano(cadena: str) -> bool:
    """¿Esta cadena de clases dibuja una superficie SIN pasar por el sistema?

    La primera versión exigía literalmente `border-border` y `bg-card`, así que una tarjeta
    escrita con `rounded-2xl border-white/10 bg-white/5` —el radio y los colores más
    habituales del pack— pasaba entera. El defecto tiene muchas formas de escribirse y el
    patrón reconocía una sola. Se buscan las TRES señales por separado dentro de la misma
    cadena; lo compuesto con el sistema queda exento por su marca, no por su forma.
    """
    if "shadow-neu" in cadena:
        return False                      # compuesta con el neumorfismo del sistema
    if "border-border/10" in cadena:
        return False                      # el borde hairline exacto de la primitiva
    # Un CAMPO no es una tarjeta. Un input, un área de texto o un desplegable llevan radio,
    # borde y fondo por su propia naturaleza, y su elevación en el sistema es hundida
    # (`shadow-neu-sunken`), no elevada: meterlos en el mismo saco convertía este check en
    # una lista de treinta falsos positivos que nadie iba a leer. Se reconocen por el token
    # de borde de campo y por las clases de foco, no por adivinar la etiqueta.
    if "border-input" in cadena or "outline-none" in cadena or "focus:" in cadena:
        return False
    return bool(_RADIO.search(cadena) and _BORDE.search(cadena) and _FONDO.search(cadena))

# Colores literales. Se permiten en el pack de diseño y en el propio globals.css (que es
# donde los tokens se DEFINEN); en una pantalla son una fuga del tema.
_LITERAL = re.compile(r'#[0-9a-fA-F]{6}\b|#[0-9a-fA-F]{3}\b|rgba?\([0-9]')

# Un color CON MATIZ dentro de una sombra: los tres canales no son iguales. El volumen del
# neumorfismo y del emblema se dibuja con negro y blanco puros, que no son «un color» del
# tema y no tienen token; un color con matiz cableado sí queda anclado a un tema y se rompe
# en el otro (fue exactamente el defecto del `#060606` de la bienvenida).
_MATIZ = re.compile(r'rgba?\(\s*(\d+)\s*,\s*(\d+)\s*,\s*(\d+)')


def _solo_grises(linea: str) -> bool:
    """True si todos los colores rgb/hex de la línea son grises puros (canales iguales)."""
    for r, g, b in _MATIZ.findall(linea):
        if not (r == g == b):
            return False
    for hexa in re.findall(r'#([0-9a-fA-F]{6})\b', linea):
        if not (hexa[0:2].lower() == hexa[2:4].lower() == hexa[4:6].lower()):
            return False
    for hexa in re.findall(r'#([0-9a-fA-F]{3})\b', linea):
        if not (hexa[0].lower() == hexa[1].lower() == hexa[2].lower()):
            return False
    return True


def main() -> int:
    print("== barrera del sistema de diseño (rediseño Luxury) ==")
    archivos = pantallas()
    print(f"   {len(archivos)} pantallas del producto")

    print("\n1 · nadie dibuja tarjetas a mano")
    a_mano: list[str] = []
    for f in archivos:
        for i, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
            if es_tarjeta_a_mano(linea):
                a_mano.append(f"{f.relative_to(ROOT)}:{i}")
    check("ninguna superficie cablea radio+borde+fondo de tarjeta sin el neumorfismo",
          not a_mano, "; ".join(a_mano[:8]))

    print("\n2 · el tema no se rompe con colores cableados")
    literales: list[str] = []
    for f in archivos:
        for i, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), start=1):
            m = _LITERAL.search(linea)
            if not m:
                continue
            # Un color dentro de un comentario documenta el pack; no llega al navegador.
            despojada = linea.strip()
            if despojada.startswith(("//", "*", "/*")):
                continue
            # Los logos de terceros (OneDrive, Google, Telegram) van con SUS colores de
            # marca: no son el tema de Mia y no pueden salir de un token nuestro. Pero la
            # exención cubre el ATRIBUTO, no la línea: saltar la línea entera dejaba pasar
            # cualquier color cableado que compartiera renglón con un `fill=`. Se despoja la
            # línea de sus atributos de dibujo y de sus sombras de grises, y se mira LO QUE
            # QUEDA — que es donde vive la fuga del tema.
            resto = re.sub(
                r'(?:fill|stroke|stop-color|stopColor)=(?:"[^"]*"|\'[^\']*\'|\{[^}]*\})',
                "", linea)
            # Sombras arbitrarias de Tailwind: el volumen del neumorfismo y del emblema se
            # dibujan con negro y blanco puros, que no son «un color» del tema y no tienen
            # token. Un color CON MATIZ dentro de una sombra sí queda anclado a un tema.
            resto = re.sub(
                r'(?:drop-)?shadow-\[[^\]]*\]',
                lambda mm: "" if _solo_grises(mm.group(0)) else mm.group(0), resto)
            m2 = _LITERAL.search(resto)
            if not m2:
                continue
            literales.append(f"{f.relative_to(ROOT)}:{i} → {m2.group(0)}")
    check("ninguna pantalla cablea un color literal donde hay token",
          not literales, "; ".join(literales[:8]))

    print("\n3 · la primitiva sigue trayendo el rediseño")
    card = (FRONT / "components" / "ui" / "card.tsx").read_text(encoding="utf-8")
    check("<Card> compone shadow-neu-raised en sus tres variantes",
          card.count("shadow-neu-raised") >= 3, f"encontradas {card.count('shadow-neu-raised')}")
    globals_css = (FRONT / "app" / "globals.css").read_text(encoding="utf-8")
    check("los tokens del neumorfismo existen en claro y en oscuro",
          globals_css.count("--neu-raised") >= 2 and globals_css.count("--neu-sunken") >= 2)
    check("el teal del pack es el primario del tema claro (188 100% 28%)",
          "188 100% 28%" in globals_css)

    ok = sum(1 for _, r in _results if r)
    print(f"\n{ok}/{len(_results)} checks PASS")
    if ok != len(_results):
        print("Gate FAIL — una pantalla salió del sistema de diseño. Corrígela antes de "
              "commitear (corrección sellada de Pipe, 2026-08-24).")
        return 1
    print("Gate OK. Recuerda: esto no dice que se VEA bien; la captura cotejada sigue "
          "haciendo falta.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
