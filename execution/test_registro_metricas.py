"""
Mia · test_registro_metricas.py — BARRERA: ninguna cifra sin definición literal.

═══ POR QUÉ EXISTE ════════════════════════════════════════════════════════════════
Regla operativa §18 (portada del harness de Lexia el 2026-08-19): «el panel no es la
evidencia; el crudo lo es… y toda métrica con nombre evaluativo declara qué mide
literalmente: LA ETIQUETA ES PARTE DE LA MÉTRICA».

Mia ya pagó dos veces este defecto:
  · un aviso que le decía al abogado «lo resolví con crédito de pago» cuando el turno
    había caído al motor local, que es gratis — un cobro inventado en pantalla;
  · gates en verde que no corrían nada.

En ambos casos el código medía una cosa y la etiqueta afirmaba otra, y nadie lo veía
porque la etiqueta se escribe una vez y se lee para siempre. La barrera no puede ser
«acordarse»: es que cada cifra visible del panel tenga su definición literal registrada
en `validation/registro-metricas.json`, y que una métrica nueva sin definición ponga
esto en rojo el mismo día que aparece.

═══ QUÉ COMPRUEBA ═════════════════════════════════════════════════════════════════
  1 · el registro carga y cada entrada trae sus campos obligatorios;
  2 · toda métrica del registro sigue viva: su `ancla` aparece en su `archivo_ui`
      (una definición que describe una etiqueta ya borrada es peor que ninguna);
  3 · DIRECCIÓN QUE IMPORTA — toda `<StatCard label="…">` de las pantallas de métricas
      tiene entrada en el registro. Una tarjeta nueva sin definición = ROJO;
  4 · toda métrica marcada `estimacion: true` declara en su pantalla que lo es
      (la palabra «estimad*» tiene que estar cerca de su ancla, no en un tooltip);
  5 · ninguna pantalla de métricas rellena un dato ausente con cero: se prohíbe el
      patrón `?? 0` / `|| 0` sobre los campos del bloque `value` del servidor, que es
      exactamente cómo «no medido» se convertía en «cero real».

NACE COMO AVISO en su mensaje al humano: no bloquea la entrega mientras el inventario
se termina de poblar. Pero corre en verde/rojo de verdad — exit 1 cuando falla — para
que no sea una de esas barreras que nadie invoca (regla §20).

    .venv\\Scripts\\python.exe execution\\test_registro_metricas.py
    .venv\\Scripts\\python.exe execution\\test_registro_metricas.py --selftest
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REGISTRO = ROOT / "validation" / "registro-metricas.json"

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:  # noqa: BLE001 — consolas viejas de Windows
    pass

VERBOSE = "--verbose" in sys.argv

# Las pantallas que le presentan CIFRAS al abogado. Si mañana nace otra, se añade aquí
# y sus tarjetas entran automáticamente al inventario obligatorio.
PANTALLAS_DE_METRICAS = (
    "frontend/app/dashboard/page.tsx",
    "frontend/app/configurar/page.tsx",
)

CAMPOS = ("etiqueta", "mide", "fuente", "archivo_ui", "ancla", "estimacion", "sin_medir")

# Campos del bloque `value` del servidor: son CIFRAS del mes del abogado, y un cero
# fabricado sobre ellos afirma algo falso sobre su trabajo.
CAMPOS_VALUE = (
    "net_usd", "gross_usd", "cost_usd", "hours_saved", "hourly_rate_usd",
    "drafts_approved", "consultations", "weekly_approval_rate",
)
_CERO_FABRICADO = re.compile(
    r"\b(" + "|".join(CAMPOS_VALUE) + r")\b\s*(\?\?|\|\|)\s*0\b"
)

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> bool:
    _results.append((nombre, ok))
    print(f"  [{'PASS' if ok else 'FAIL'}] {nombre}")
    if detalle and (not ok or VERBOSE):
        for linea in detalle.splitlines():
            print(f"         {linea}")
    return ok


def etiquetas_de_statcard(texto: str) -> list[str]:
    """Extrae los `label="…"` de cada `<StatCard …/>` del archivo.

    Se recorta hasta el `/>` de cierre de la propia tarjeta para no capturar el label
    de un componente vecino. Un `label={expresión}` se ignora a propósito: no es un
    literal que se pueda inventariar, y hoy no existe ninguno.
    """
    etiquetas: list[str] = []
    for m in re.finditer(r"<StatCard\b", texto):
        fin = texto.find("/>", m.end())
        bloque = texto[m.end(): fin if fin != -1 else m.end() + 800]
        lab = re.search(r'label="([^"]+)"', bloque)
        if lab:
            etiquetas.append(lab.group(1))
    return etiquetas


def cargar(registro_path: Path) -> list[dict]:
    data = json.loads(registro_path.read_text(encoding="utf-8"))
    return list(data.get("metricas") or [])


def run(root: Path, registro_path: Path) -> None:
    print("\n1 · el registro existe y cada entrada está completa")
    if not check("1a · validation/registro-metricas.json existe", registro_path.exists()):
        return
    try:
        metricas = cargar(registro_path)
        cargo = True
    except Exception as exc:  # noqa: BLE001
        metricas, cargo = [], False
        check("1b · el registro es JSON válido", False, str(exc))
    if not cargo:
        return
    check("1b · el registro es JSON válido", True)
    incompletas = [
        f"{e.get('etiqueta', '(sin etiqueta)')}: falta {c}"
        for e in metricas for c in CAMPOS if c not in e
    ]
    check(f"1c · las {len(metricas)} entradas traen sus {len(CAMPOS)} campos",
          not incompletas, "\n".join(incompletas))
    vacias = [e.get("etiqueta", "?") for e in metricas
              if len(str(e.get("mide", "")).strip()) < 30]
    check("1d · ninguna definición de «qué mide» es un relleno de una línea",
          not vacias, "definiciones demasiado cortas: " + ", ".join(vacias))

    print("\n2 · toda definición del registro sigue viva en su pantalla")
    muertas = []
    for e in metricas:
        archivo = root / str(e.get("archivo_ui", ""))
        if not archivo.exists():
            muertas.append(f"{e.get('etiqueta')}: no existe {e.get('archivo_ui')}")
            continue
        if str(e.get("ancla", "")) not in archivo.read_text(encoding="utf-8"):
            muertas.append(f"{e.get('etiqueta')}: el ancla ya no aparece en {e.get('archivo_ui')}")
    check("2a · ningún ancla del registro quedó huérfana", not muertas, "\n".join(muertas))

    print("\n3 · ninguna cifra del panel sin definición registrada")
    registradas = {str(e.get("etiqueta")) for e in metricas}
    huerfanas = []
    vistas = 0
    for rel in PANTALLAS_DE_METRICAS:
        f = root / rel
        if not f.exists():
            continue
        for et in etiquetas_de_statcard(f.read_text(encoding="utf-8")):
            vistas += 1
            if et not in registradas:
                huerfanas.append(f"{rel}: «{et}» no tiene definición en el registro")
    check(f"3a · las {vistas} cifras visibles tienen definición literal",
          not huerfanas,
          "\n".join(huerfanas) + "\n→ añade su entrada en validation/registro-metricas.json "
                                 "(etiqueta · qué mide LITERALMENTE · fuente).")

    print("\n4 · las estimaciones se declaran en pantalla")
    calladas = []
    for e in metricas:
        if not e.get("estimacion"):
            continue
        archivo = root / str(e.get("archivo_ui", ""))
        if not archivo.exists():
            continue
        texto = archivo.read_text(encoding="utf-8")
        pos = texto.find(str(e.get("ancla", "")))
        if pos == -1:
            continue
        ventana = texto[max(0, pos - 1200): pos + 1200].lower()
        if "estimad" not in ventana:
            calladas.append(f"{e.get('etiqueta')}: es un estimado y no lo dice cerca de su cifra")
    check("4a · toda cifra estimada lo declara junto a la cifra", not calladas,
          "\n".join(calladas))

    print("\n5 · «no medido» nunca se rellena con cero")
    ceros = []
    for rel in (*PANTALLAS_DE_METRICAS, "frontend/app/_components/ValorGastoSection.tsx"):
        f = root / rel
        if not f.exists():
            continue
        for i, linea in enumerate(f.read_text(encoding="utf-8").splitlines(), 1):
            # `value?.campo ?? 0` es el patrón exacto que fabricaba el cero: el objeto
            # entero puede faltar y el `?? 0` lo convierte en «cero real». Dentro de una
            # rama que YA comprobó `value != null` se escribe `value.campo ?? 0`, que es
            # legítimo (el objeto está, el campo puntual puede no venir) y se exceptúa
            # por el acceso sin `?.`.
            if not _CERO_FABRICADO.search(linea):
                continue
            if re.search(r"\bvalue\.[A-Za-z_]", linea):
                continue
            ceros.append(f"{rel}:{i}: {linea.strip()[:110]}")
    check("5a · ninguna pantalla de métricas convierte un dato ausente en 0",
          not ceros,
          "\n".join(ceros) + "\n→ usa el estado «Sin medir todavía» con su razón "
                             "(StatCard `sinMedir`), no un cero.")


# ── SELFTEST: se prueba en los dos sentidos ──────────────────────────────────────
def selftest() -> int:
    """Prueba que la barrera DETECTA lo que dice detectar y no dispara sin causa.

    Regla §22: «el primer hallazgo de una barrera nueva es una hipótesis». Aquí se
    fabrican los dos casos en un árbol temporal — uno sano y uno con una métrica nueva
    sin definición — y se comprueba que el veredicto cambia.
    """
    print("== SELFTEST · la barrera en los dos sentidos ==")
    ok_total = True
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        (base / "validation").mkdir(parents=True)
        (base / "frontend/app/dashboard").mkdir(parents=True)
        (base / "frontend/app/configurar").mkdir(parents=True)
        reg = base / "validation" / "registro-metricas.json"
        reg.write_text(json.dumps({"metricas": [{
            "etiqueta": "Consultas atendidas",
            "mide": "Turnos del mes no rechazados con texto final corto; atendidas no es resueltas.",
            "fuente": "metrics/value.py::summarize_traces",
            "archivo_ui": "frontend/app/dashboard/page.tsx",
            "ancla": 'label="Consultas atendidas"',
            "estimacion": False,
            "sin_medir": "Raya + Sin dato ahora mismo",
        }]}, ensure_ascii=False), encoding="utf-8")
        dash = base / "frontend/app/dashboard/page.tsx"
        conf = base / "frontend/app/configurar/page.tsx"
        conf.write_text("export default function C() { return null; }\n", encoding="utf-8")

        sano = '<StatCard icon={X} label="Consultas atendidas" value={s?.value?.consultations} />\n'
        dash.write_text(sano, encoding="utf-8")
        _results.clear()
        run(base, reg)
        paso_sano = all(ok for _, ok in _results)
        ok_total &= paso_sano
        print(f"\n  caso QUE PASA (solo métricas registradas) → {'PASS' if paso_sano else 'FAIL (mal)'}")

        # Caso 2: alguien añade una tarjeta nueva y no la define.
        dash.write_text(sano + '<StatCard icon={Y} label="Éxito del mes" value={s?.value?.exito} />\n',
                        encoding="utf-8")
        _results.clear()
        print()
        run(base, reg)
        fallo_esperado = any(not ok for n, ok in _results if n.startswith("3a"))
        ok_total &= fallo_esperado
        print(f"\n  caso QUE FALLA (métrica nueva sin definición) → "
              f"{'PASS (la detectó)' if fallo_esperado else 'FAIL (se le escapó)'}")

        # Caso 3: cero fabricado sobre una cifra del mes.
        dash.write_text(sano + "const n = value?.net_usd ?? 0;\n", encoding="utf-8")
        _results.clear()
        print()
        run(base, reg)
        cero_detectado = any(not ok for n, ok in _results if n.startswith("5a"))
        ok_total &= cero_detectado
        print(f"\n  caso QUE FALLA (dato ausente rellenado con 0) → "
              f"{'PASS (la detectó)' if cero_detectado else 'FAIL (se le escapó)'}")

    print("\nSELFTEST " + ("OK" if ok_total else "FALLÓ"))
    return 0 if ok_total else 1


def main() -> int:
    if "--selftest" in sys.argv:
        return selftest()
    print("== BARRERA · registro de definiciones literales de las métricas (regla §18) ==")
    print("   AVISO: nace como inventario congelado. Rojo = hay una cifra en pantalla que")
    print("   afirma algo que nadie definió, no que el producto esté roto.\n")
    run(ROOT, REGISTRO)
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("registro de métricas OK — toda cifra visible declara qué mide literalmente.")
        return 0
    print("registro de métricas FAIL — define la métrica antes de mostrarla.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
