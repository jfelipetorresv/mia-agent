"""
Mia · test_doc_citation_guard.py — gate del guardián de referencias [doc n] fantasma.

Standalone, SIN DB y SIN red. Verifica que el especialista de verificación
(agents/verification.py) marca [VERIFICAR] junto a toda referencia [doc n] cuyo
número esté FUERA del rango 1..N de documentos recuperados en el turno (un documento
inventado por el modelo — el análogo de citar un identificador inexistente), sin
tocar las referencias legítimas ni bloquear el borrador.

    .venv\\Scripts\\python.exe execution\\test_doc_citation_guard.py

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

from mia.agents import verification  # noqa: E402

MARK = verification.VERIFY_MARK

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def run() -> None:
    flag = verification.flag_phantom_doc_citations

    # 1 · Referencia dentro de rango NO se marca (5 documentos, se cita [doc 3]).
    txt, rep = flag("Según el contrato [doc 3], la obligación es clara.", 5)
    check("dentro de rango [doc 3] con N=5 → intacta",
          MARK not in txt and rep["fantasmas"] == 0 and rep["refs_doc"] == 1)

    # 2 · Referencia fantasma SÍ se marca (5 documentos, se cita [doc 9]).
    txt, rep = flag("El poder [doc 9] acredita la representación.", 5)
    check("fantasma [doc 9] con N=5 → marcada [VERIFICAR]",
          MARK in txt and rep["fantasmas"] == 1
          and rep["detalle"][0]["fuera_de_rango"] == [9])

    # 3 · La marca va JUNTO a la referencia fantasma (justo tras el corchete).
    txt, _ = flag("El poder [doc 9] acredita la representación.", 5)
    check("la marca se inserta tras el ] de la referencia",
          "[doc 9] " + MARK in txt)

    # 4 · Sin documentos (N=0) cualquier [doc k] es fantasma.
    txt, rep = flag("La demanda [doc 1] es infundada.", 0)
    check("N=0 → [doc 1] es fantasma", MARK in txt and rep["fantasmas"] == 1)

    # 5 · Lista de documentos: marca si CUALQUIER número está fuera de rango.
    txt, rep = flag("Los anexos [docs 1, 2 y 8] lo prueban.", 3)
    check("lista [docs 1, 2 y 8] con N=3 → marca (8 fuera)",
          MARK in txt and rep["detalle"][0]["fuera_de_rango"] == [8])

    # 6 · Lista enteramente en rango NO se marca.
    txt, rep = flag("Los anexos [docs 1, 2 y 3] lo prueban.", 3)
    check("lista [docs 1, 2 y 3] con N=3 → intacta",
          MARK not in txt and rep["fantasmas"] == 0)

    # 7 · Variantes de formato: [doc. 4], [Doc 4], [DOCUMENTO 4] (aquí en singular 'doc').
    txt, rep = flag("Ver [doc. 4] y [Doc 7].", 5)
    check("variantes [doc. 4] (ok) y [Doc 7] (fantasma) → solo 7 marcada",
          rep["refs_doc"] == 2 and rep["fantasmas"] == 1
          and rep["detalle"][0]["fuera_de_rango"] == [7])

    # 8 · No hay falso positivo con corchetes NO numéricos ([doc 2023-cv-1]).
    txt, rep = flag("El radicado [doc 2023-cv-1] figura en el expediente.", 2)
    check("corchete no numérico [doc 2023-cv-1] → ignorado (0 refs)",
          MARK not in txt and rep["refs_doc"] == 0)

    # 9 · Idempotencia: si ya trae [VERIFICAR] al lado, no se duplica la marca.
    ya = "El poder [doc 9] " + MARK + " acredita."
    txt, rep = flag(ya, 5)
    check("ya marcada → no se duplica", txt == ya and rep["fantasmas"] == 0)

    # 10 · Integración en annotate_draft: sin num_documents = comportamiento previo.
    txt_sin, rep_sin = verification.annotate_draft("Ver [doc 9].")
    check("annotate_draft sin num_documents → no corre el guardián",
          MARK not in txt_sin and "docs_fantasma" not in rep_sin)

    # 11 · Integración en annotate_draft: con num_documents corre el guardián y reporta.
    txt_con, rep_con = verification.annotate_draft("Ver [doc 9].", num_documents=5)
    check("annotate_draft con num_documents=5 → marca y reporta docs_fantasma",
          MARK in txt_con and rep_con.get("docs_fantasma", {}).get("fantasmas") == 1)

    # 12 · annotate_draft combina guardián de docs + escáner de citas legales.
    draft = "La Sentencia C-355 de 2006 y el poder [doc 9] respaldan la tesis."
    txt_mix, rep_mix = verification.annotate_draft(draft, num_documents=5)
    check("annotate_draft marca la cita legal sin respaldo Y el [doc 9] fantasma",
          txt_mix.count(MARK) == 2
          and rep_mix["anotadas"] == 1
          and rep_mix["docs_fantasma"]["fantasmas"] == 1)

    # ── helper highest_sealed_doc_index (rango real que vio el modelo) ──────────
    hi = verification.highest_sealed_doc_index

    # 13 · sin sellos → 0.
    check("highest_sealed_doc_index sin sellos → 0", hi("texto sin sellos") == 0)

    # 14 · toma el MAYOR índice <<<DOC n>>> presente (RRF + @expediente adjunto).
    msg = ("Mensaje.\n<<<DOC 1>>>...<<<FIN DOC 1>>>\n"
           "--- Pruebas adjuntas por referencia ---\n"
           "<<<DOC 1 · poder>>>...<<<DOC 2 · contrato>>>...<<<DOC 3 · demanda>>>")
    check("highest_sealed_doc_index toma el máximo (3)", hi(msg) == 3)

    # 15 · el label ARCHIVO (@carpeta) NO cuenta como DOC.
    check("highest_sealed_doc_index ignora <<<ARCHIVO n>>>",
          hi("<<<ARCHIVO 8 · x>>> <<<DOC 2 · y>>>") == 2)

    # 16 · Falso positivo del revisor RESUELTO: [doc 7] legítimo (adjunto por
    # @expediente) NO se marca cuando el rango válido sube a 7, aunque el RRF traiga 3.
    rango = max(3, hi("<<<DOC 1>>> <<<DOC 7 · adjunto>>>"))
    txt16, rep16 = verification.annotate_draft(
        "El poder [doc 7] acredita la representación.", num_documents=rango)
    check("cita legítima [doc 7] a adjunto @expediente → NO se marca (rango=7)",
          MARK not in txt16 and rep16["docs_fantasma"]["fantasmas"] == 0)

    # 17 · pero un [doc 9] por ENCIMA de todo lo sellado (rango 7) SÍ es fantasma.
    txt17, rep17 = verification.annotate_draft(
        "El anexo [doc 9] lo prueba.", num_documents=7)
    check("[doc 9] por encima de todo lo sellado (rango=7) → fantasma",
          MARK in txt17 and rep17["docs_fantasma"]["fantasmas"] == 1)

    # 18 · variante deletreada "[documento 9]" también se cubre (fantasma con N=5).
    txt18, rep18 = flag("El [documento 9] no consta en el expediente.", 5)
    check("variante [documento 9] → detectada como fantasma",
          MARK in txt18 and rep18["fantasmas"] == 1)

    # 19 · "[documento 2]" legítimo (dentro de rango) NO se marca.
    txt19, rep19 = flag("El [documento 2] es la contestación.", 5)
    check("variante [documento 2] dentro de rango → intacta",
          MARK not in txt19 and rep19["fantasmas"] == 0)


def main() -> int:
    print("== Guardián de referencias [doc n] fantasma (refuerzo del gate de citas) ==")
    run()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("doc_citation_guard OK — refuerzo del gate de citas verificado.")
        return 0
    print("doc_citation_guard FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
