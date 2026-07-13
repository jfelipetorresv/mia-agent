"""
Mia · test_reasoning_filter.py — gate del filtro de "razonamiento en voz alta".

Standalone, SIN DB, SIN red, SIN Ollama. Verifica que agents/reasoning_filter.
strip_reasoning elimina la cadena de pensamiento que los modelos de razonamiento
locales anteponen a su respuesta (<think>…</think> y variantes) SIN alterar el texto
legítimo del borrador — el análogo, aguas arriba, del guardián de citas.

REGLA DURA (arreglo del hallazgo bloqueante, 2026-07-13): el razonamiento SOLO se
elimina cuando está ANCLADO AL INICIO. Una etiqueta `<think>`/`</think>` a MITAD del
contenido es texto CITADO legítimo (peritaje de IA, código como prueba, análisis de un
fallo automatizado) y se CONSERVA intacta. Se prueba también el gate por modelo
(is_reasoning_model).

    .venv\\Scripts\\python.exe execution\\test_reasoning_filter.py

Exit 0 = PASS · exit 1 = FAIL.
"""
from __future__ import annotations
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agents import reasoning_filter, verification  # noqa: E402

strip = reasoning_filter.strip_reasoning
is_local = reasoning_filter.is_reasoning_model
MARK = verification.VERIFY_MARK

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def run() -> None:
    # ── Bloques LÍDERES (anclados al inicio) → se eliminan ────────────────────

    # (a) Bloque <think>…</think> LÍDER → se elimina, queda la respuesta.
    out = strip("<think>Debo analizar el caso y estructurar la contestación.</think>"
                "La demanda es infundada por falta de legitimación.")
    check("(a) bloque <think> líder → solo la respuesta",
          out == "La demanda es infundada por falta de legitimación.")

    # (b) SIN etiquetas → texto IDÉNTICO byte a byte (no-op crítico, modo Claude).
    original = ("Señor Juez:\n\nEn nombre de mi representada, con todo respeto,\n"
                "  presento la siguiente contestación.   \n\nAtentamente.")
    check("(b) sin etiquetas → byte a byte idéntico (no-op)",
          strip(original) == original)

    # (b2) cadena vacía → intacta.
    check("(b2) cadena vacía → intacta", strip("") == "")

    # (c) Cierre huérfano LÍDER `</think>` (stray al inicio, sin preámbulo real) →
    #     se elimina la etiqueta, queda la respuesta.
    out = strip("</think>Se solicita declarar probada la excepción de caducidad.")
    check("(c) cierre huérfano líder </think> → elimina la etiqueta, conserva la respuesta",
          out == "Se solicita declarar probada la excepción de caducidad.")

    # (c2) Cierre huérfano líder con blancos y saltos previos → limpio.
    out = strip("  \n</think>\n\nSe solicita la nulidad.")
    check("(c2) cierre huérfano líder con blancos → limpio",
          out == "Se solicita la nulidad.")

    # (d2) apertura huérfana LÍDER (todo es razonamiento truncado) → queda vacío.
    check("(d2) apertura huérfana líder → vacío",
          strip("<think>razonando sin terminar la respuesta") == "")

    # (e) Anidado LÍDER → se colapsa correctamente y queda solo la respuesta.
    out = strip("<think>nivel 1 <think>nivel 2</think> vuelta al 1</think>Respuesta final.")
    check("(e) bloques anidados líderes → colapsan, queda la respuesta",
          out == "Respuesta final.")

    # (f) Varios bloques LÍDERES contiguos (separados solo por blancos) → todos fuera.
    out = strip("<think>plan A</think>\n\n  <think>plan B</think>El escrito definitivo.")
    check("(f) bloques líderes contiguos (solo blancos entre ellos) → todos eliminados",
          out == "El escrito definitivo.")

    # (g) Variantes <thinking> y <reasoning> LÍDERES (case-insensitive) → se eliminan.
    out_thinking = strip("<Thinking>razono en voz alta</Thinking>Texto del borrador.")
    out_reasoning = strip("<reasoning>otra forma de razonar</reasoning>Texto del borrador.")
    check("(g) variante <thinking> líder (case-insensitive) → eliminada",
          out_thinking == "Texto del borrador.")
    check("(g) variante <reasoning> líder → eliminada",
          out_reasoning == "Texto del borrador.")

    # (h) CRÍTICO: cita legal dentro de un bloque LÍDER <think> → desaparece y NO llega
    #     al escáner (no se marca [VERIFICAR] injustificado sobre un pensamiento del modelo).
    con_cita_interna = ("<think>Creo que aplica el art. 90 del CPACA y la "
                        "Sentencia C-543 de 1992.</think>"
                        "La entidad demandada carece de legitimación en la causa.")
    filtrado = strip(con_cita_interna)
    check("(h) cita legal dentro de <think> líder → desaparece del texto filtrado",
          "art. 90" not in filtrado and "C-543" not in filtrado
          and filtrado == "La entidad demandada carece de legitimación en la causa.")
    _, rep = verification.annotate_draft(filtrado)
    check("(h) tras el filtro el escáner NO marca la cita que estaba en el <think>",
          rep["citas"] == 0 and MARK not in filtrado)

    # (i) cita legal FUERA del bloque líder → se conserva intacta y SÍ llega al escáner.
    con_cita_externa = ("<think>razonamiento interno del modelo</think>"
                        "Con fundamento en la Sentencia C-543 de 1992, se solicita "
                        "declarar la nulidad.")
    filtrado_ext = strip(con_cita_externa)
    check("(i) cita legal fuera del bloque líder → se conserva intacta",
          "Sentencia C-543 de 1992" in filtrado_ext
          and filtrado_ext.startswith("Con fundamento"))
    anotado, rep_ext = verification.annotate_draft(filtrado_ext)
    check("(i) la cita conservada SÍ llega al escáner (la detecta y anota)",
          rep_ext["citas"] == 1 and MARK in anotado)

    # (j) multilínea LÍDER: el pensamiento ocupa varias líneas → se elimina completo y se
    #     limpian los blancos-gap sobrantes (pero no la sangría del cuerpo).
    out = strip("<think>\nprimero esto\nluego lo otro\n</think>\n\n\nEscrito definitivo.")
    check("(j) bloque multilínea líder → eliminado y blancos-gap limpios",
          out == "Escrito definitivo.")

    # ── CASOS ADVERSARIOS DEL REVISOR: texto CITADO a media respuesta → se CONSERVA ──

    # (4) bloque pareado CITADO a media respuesta → NO se toca (texto legítimo del dolo).
    caso4 = "La clausula rezaba: <think>we must consider</think> lo cual es prueba del dolo."
    check("(4) bloque pareado citado a media respuesta → intacto (byte a byte)",
          strip(caso4) == caso4 and "we must consider" in strip(caso4))

    # (5) apertura huérfana a media respuesta (glitch tras contenido real) → se conserva
    #     TODO (la etiqueta a media respuesta es contenido citado, no razonamiento líder).
    caso5 = ("Contestación al hecho primero.\n<think>ahora debo pensar el hecho segundo")
    check("(5) apertura huérfana a media respuesta → se conserva todo (intacto)",
          strip(caso5) == caso5)

    # (8) <think/> self-closing CITADO a media respuesta → intacto.
    caso8 = "El perito describió la etiqueta <think/> como marca de razonamiento automatizado."
    check("(8) <think/> self-closing a media respuesta → intacto (byte a byte)",
          strip(caso8) == caso8)

    # (10) apertura huérfana en un PERITAJE (etiqueta como prueba) + petición posterior →
    #      NO se pierde ni la etiqueta citada ni la petición.
    caso10 = ("El sistema contenia la etiqueta <think> seguida del razonamiento, prueba de "
              "que la decision fue automatizada. Por ello se solicita la nulidad.")
    out10 = strip(caso10)
    check("(10) apertura huérfana citada en peritaje → conserva etiqueta y petición",
          out10 == caso10 and "se solicita la nulidad" in out10)

    # (12) .strip() NO debe comerse la sangría/espaciado legítimo del cuerpo: tras un
    #      bloque LÍDER, la sangría de la primera línea real y el espaciado interno se
    #      conservan; solo se limpian las líneas-gap del borrado.
    caso12 = ("<think>razono</think>\n\n    PRIMERO. Los hechos:\n"
              "        a) sangría profunda legítima\n        b) otra viñeta\n\nAtentamente.")
    out12 = strip(caso12)
    check("(12) tras bloque líder, la sangría legítima del cuerpo se conserva",
          out12 == ("    PRIMERO. Los hechos:\n"
                    "        a) sangría profunda legítima\n        b) otra viñeta\n\nAtentamente."))

    # (13) cierre huérfano CITADO a media respuesta (tras contenido real) → NO se toca.
    caso13 = "El documento decia </think> como cierre de la etiqueta de razonamiento."
    check("(13) cierre huérfano citado a media respuesta → intacto (byte a byte)",
          strip(caso13) == caso13)

    # (13b) cierre huérfano tras una oración completa (preámbulo legítimo) → se conserva
    #       TODO (no se borra el preámbulo: solo el líder al inicio se elimina).
    caso13b = "El actor pretende una nulidad, veamos.</think>Se solicita la caducidad."
    check("(13b) cierre huérfano tras oración legítima → intacto (se conserva el preámbulo)",
          strip(caso13b) == caso13b)

    # ── GATE POR MODELO (FIX 2 · is_reasoning_model) ──────────────────────────
    check("(gate) claude-sonnet → NO es modelo de razonamiento (no corre el filtro)",
          is_local("claude-sonnet") is False)
    check("(gate) anthropic/claude-sonnet-4-6 → NO es de razonamiento",
          is_local("anthropic/claude-sonnet-4-6") is False)
    check("(gate) cli-claude → NO es de razonamiento (suscripción nube)",
          is_local("cli-claude") is False)
    check("(gate) vacío/None → NO es de razonamiento",
          is_local("") is False and is_local(None) is False)
    check("(gate) mia-local (alias) → SÍ es de razonamiento (corre el filtro)",
          is_local("mia-local") is True)
    check("(gate) ollama/qwen2.5:7b-instruct (modelo real) → SÍ es de razonamiento",
          is_local("ollama/qwen2.5:7b-instruct") is True)


def main() -> int:
    print("== Filtro de razonamiento en voz alta (refuerzo previo al gate de citas) ==")
    run()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("reasoning_filter OK — el pensamiento del modelo no llega al borrador ni al escáner.")
        return 0
    print("reasoning_filter FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
