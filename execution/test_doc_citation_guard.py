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
from mia.jurisdiction.pack import load_pack  # noqa: E402

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

    run_frontera_identificadores()
    run_abreviadas_y_siglas()
    run_ancla_fuente_de_verdad()


# ── Frontera de identificadores: el respaldo NO puede truncar un número ────────
# El defecto que cierra esta sección es el PEOR que puede producir el producto: el
# guardián declaraba "Con respaldo" (check verde en la pantalla, atribuido a un
# archivo y folio concretos del expediente) una norma que Mia INVENTÓ, solo porque
# su texto era prefijo del de una fuente real ("Decreto 108" ⊂ "Decreto 1082 de
# 2015"). Marcar de más es inofensivo; respaldar de más destruye la única razón por
# la que un abogado confiaría en esto.
#
# Los casos vienen en AMBAS direcciones (clave ⊂ cita y cita ⊂ clave) porque el
# cotejo es bidireccional y blindar una sola mitad deja el defecto vivo.

def _informe(draft: str, referencias: list[str]) -> dict:
    """(anotado, informe) de un borrador contra unas referencias de fuente."""
    fuentes = [{"tipo": "norma", "referencia": r, "titulo": "demanda.pdf · folio 3"}
               for r in referencias]
    return verification.annotate_draft(draft, sources=fuentes)


def _no_respalda(nombre: str, draft: str, referencias: list[str], cita: str) -> None:
    """La cita NO puede quedar respaldada: debe salir anotada y con su [VERIFICAR]."""
    anotado, rep = _informe(draft, referencias)
    estados = {d["cita"]: d["estado"] for d in rep["detalle"]}
    ok = (rep["respaldadas"] == 0
          and estados.get(cita) == "anotada"
          and (cita + " " + MARK) in anotado
          and not any("fuente" in d for d in rep["detalle"]))
    check(nombre, ok)
    if not ok:  # diagnóstico legible cuando falla
        print(f"         cita={cita!r} estados={estados} respaldadas={rep['respaldadas']}")


def _si_respalda(nombre: str, draft: str, referencias: list[str], cita: str) -> None:
    """La cita legítima DEBE seguir respaldada (sin marca): el arreglo no puede
    convertir el guardián en un sello que marca el 100% y no confirma nunca nada."""
    anotado, rep = _informe(draft, referencias)
    estados = {d["cita"]: d["estado"] for d in rep["detalle"]}
    ok = (estados.get(cita) == "respaldada"
          and MARK not in anotado
          and rep["respaldadas"] >= 1)
    check(nombre, ok)
    if not ok:
        print(f"         cita={cita!r} estados={estados} anotado={anotado!r}")


def run_frontera_identificadores() -> None:
    print("\n-- Frontera de identificadores (falso 'Con respaldo') --")

    # 20-21 · La sonda del verificador: "Decreto 108" no existe; el expediente dice
    # "Decreto 1082 de 2015". Ambas direcciones del cotejo.
    _no_respalda("clave ⊂ cita: 'Decreto 108' NO lo respalda 'Decreto 1082 de 2015'",
                 "Segun el Decreto 108 la entidad debia publicar el aviso.",
                 ["Decreto 1082 de 2015"], "Decreto 108")
    _no_respalda("cita ⊂ clave: 'Decreto 1082 de 2015' NO lo respalda 'Decreto 108'",
                 "Segun el Decreto 1082 de 2015 la entidad debia publicar el aviso.",
                 ["Decreto 108"], "Decreto 1082 de 2015")

    # 22-23 · "Ley 143" dentro de "Ley 1437 de 2011".
    _no_respalda("clave ⊂ cita: 'Ley 143' NO la respalda 'Ley 1437 de 2011'",
                 "La actuacion se rige por la Ley 143 y sus decretos.",
                 ["Ley 1437 de 2011"], "Ley 143")
    _no_respalda("cita ⊂ clave: 'Ley 1437 de 2011' NO la respalda 'Ley 143'",
                 "La actuacion se rige por la Ley 1437 de 2011 y sus decretos.",
                 ["Ley 143"], "Ley 1437 de 2011")

    # 24-25 · "Sentencia C-35" dentro de "Sentencia C-355 de 2006" (guion + dígito).
    _no_respalda("clave ⊂ cita: 'Sentencia C-35' NO la respalda 'Sentencia C-355 de 2006'",
                 "Asi lo definio la Sentencia C-35 al estudiar el punto.",
                 ["Sentencia C-355 de 2006"], "Sentencia C-35")
    _no_respalda("cita ⊂ clave: 'Sentencia C-355 de 2006' NO la respalda 'Sentencia C-35'",
                 "Asi lo definio la Sentencia C-355 de 2006 al estudiar el punto.",
                 ["Sentencia C-35"], "Sentencia C-355 de 2006")

    # 26-27 · Separador de millares: la normalización NO puede partir "25.326" en dos
    # números y dejar que "Ley 25" respalde por prefijo (jurisdicciones que numeran
    # sin año — la clase de defecto es la misma).
    _no_respalda("punto de millares: 'Ley 25' NO la respalda 'Ley 25.326'",
                 "Se aplica la Ley 25 en lo pertinente.",
                 ["Ley 25.326"], "Ley 25")
    _no_respalda("punto de millares: 'Ley 25.326' NO la respalda 'Ley 25'",
                 "Se aplica la Ley 25.326 en lo pertinente.",
                 ["Ley 25"], "Ley 25.326")

    # 28 · Sufijo de letra pegado al número: "Resolución 123" ≠ "Resolución 123A".
    _no_respalda("sufijo de letra: 'Resolución 123' NO la respalda 'Resolución 123A'",
                 "La Resolución 123 ordeno el archivo.",
                 ["Resolución 123A"], "Resolución 123")

    # 29 · Palabra pegada que cambia la disposición: "Ley 5" ≠ "Ley 5 bis".
    _no_respalda("extensión que no es un año: 'Ley 5' NO la respalda 'Ley 5 bis'",
                 "El deber nace de la Ley 5 vigente.",
                 ["Ley 5 bis"], "Ley 5")

    # 30 · Radicado truncado: los guiones internos son parte del identificador.
    _no_respalda("radicado truncado: 'Radicado 25000-23-41' NO lo respalda el completo",
                 "Consta en el Radicado 25000-23-41 del expediente.",
                 ["Radicado 25000-23-41-000-2024"], "Radicado 25000-23-41")

    # 31 · Prefijo de tipo de norma: "Ley 19" ≠ "Decreto Ley 19 de 2012".
    _no_respalda("tipo de norma distinto: 'Ley 19' NO la respalda 'Decreto Ley 19 de 2012'",
                 "Lo dispone la Ley 19 sobre el tramite.",
                 ["Decreto Ley 19 de 2012"], "Ley 19")

    # ── Los legítimos DEBEN seguir respaldándose (no basta con marcar todo) ──────

    # 32 · El caso legítimo del informe: la cita corta de una fuente con año.
    _si_respalda("legítimo: 'Ley 80' SÍ la respalda 'Ley 80 de 1993'",
                 "El contrato se rige por la Ley 80 y sus modificaciones.",
                 ["Ley 80 de 1993"], "Ley 80")

    # 33 · Cita idéntica a la fuente (con tilde y mayúsculas distintas).
    _si_respalda("legítimo: cita idéntica a la fuente (sin importar tildes ni mayúsculas)",
                 "Ver la RESOLUCION 1234 de 2020 del expediente.",
                 ["Resolución 1234 de 2020"], "RESOLUCION 1234 de 2020")

    # 34 · Anidamiento "artículo N de la Ley M": la clave va DENTRO de la cita.
    _si_respalda("legítimo: 'Ley 640 de 2001' respalda 'artículo 21 de la Ley 640 de 2001'",
                 "Se funda en el artículo 21 de la Ley 640 de 2001.",
                 ["Ley 640 de 2001"], "artículo 21 de la Ley 640 de 2001")

    # 35 · Providencia citada sin el año que sí trae la fuente.
    _si_respalda("legítimo: 'Sentencia C-355' SÍ la respalda 'Sentencia C-355 de 2006'",
                 "Asi lo definio la Sentencia C-355 al estudiar el punto.",
                 ["Sentencia C-355 de 2006"], "Sentencia C-355")

    # 36 · Norma citada sin el año que sí trae la fuente (mismo número completo).
    _si_respalda("legítimo: 'Ley 1437' SÍ la respalda 'Ley 1437 de 2011'",
                 "La actuacion se rige por la Ley 1437 y sus decretos.",
                 ["Ley 1437 de 2011"], "Ley 1437")

    # 37 · El respaldo legítimo conserva la atribución de la fuente en el informe.
    _, rep37 = _informe("El contrato se rige por la Ley 80 y sus modificaciones.",
                        ["Ley 80 de 1993"])
    check("legítimo: la cita respaldada conserva su fuente atribuida en el informe",
          rep37["detalle"][0].get("fuente", {}).get("referencia") == "Ley 80 de 1993")

    # 38 · Expediente grande (mezcla): las inventadas se marcan y la real se respalda,
    # en un mismo borrador y con varias claves compitiendo.
    draft38 = ("Segun el Decreto 108 y la Ley 143, y conforme a la Ley 1437 de 2011, "
               "la entidad debia publicar el aviso.")
    anotado38, rep38 = _informe(draft38, ["Decreto 1082 de 2015", "Ley 1437 de 2011",
                                          "Sentencia C-355 de 2006"])
    est38 = {d["cita"]: d["estado"] for d in rep38["detalle"]}
    check("mezcla: en un mismo borrador solo la cita real queda respaldada",
          est38.get("Decreto 108") == "anotada"
          and est38.get("Ley 143") == "anotada"
          and est38.get("Ley 1437 de 2011") == "respaldada"
          and rep38["respaldadas"] == 1 and rep38["anotadas"] == 2
          and anotado38.count(MARK) == 2)


# ── Citas ABREVIADAS + SIGLAS por pack ────────────────────────────────────────
# En la prueba en vivo el guardián detectó 1 de 5 citas: los patrones exigían la palabra
# completa "artículo" y no veían "art./arts. N", "y ss." ni las siglas con puntos ("C.C.").
# El código común aporta la MECÁNICA (formas abreviadas con cuerpo normativo); las siglas
# son DATOS del pack (citation_style.json → "code_abbreviations"), que el verificador compone
# con las formas abreviadas en runtime. Ningún nombre de código de país vive en el código.

def run_abreviadas_y_siglas() -> None:
    print("\n-- Citas abreviadas + siglas por pack (co) --")
    ann = verification.annotate_draft
    # Las siglas salen del PACK (dato), no de un literal del test: se prueba el cableado real.
    siglas = load_pack("co").citation_style.get("code_abbreviations") or []
    extra = verification.code_abbreviation_patterns(siglas)
    check("el pack co aporta siglas de código como DATOS (no vacío)", len(siglas) >= 1)

    # 39 · forma abreviada con "y ss." ligada a la sigla del pack ("C.C.").
    _, r1 = ann("Se aplican los arts. 1516 y ss. C.C. al contrato.", extra_patterns=extra)
    check("abreviada 'arts. 1516 y ss. C.C.' con pack co → detectada (1 cita)",
          r1["citas"] == 1 and r1["anotadas"] == 1)

    # 40 · forma abreviada con CUERPO NORMATIVO explícito (base genérica, sin pack).
    _, r2 = ann("Ver el art. 90 de la Constitución Política.")
    check("abreviada con cuerpo 'art. 90 de la Constitución Política' → detectada (base)",
          r2["citas"] == 1)

    # 41 · subdivisión de un artículo nombrado (inciso / parágrafo).
    _, r3 = ann("El inciso 2 del artículo 5 lo dispone; ver también el parágrafo del artículo 90.")
    check("subdivisión 'inciso 2 del artículo 5' / 'parágrafo del artículo 90' → detectadas (2)",
          r3["citas"] == 2)

    # 42-43 · SIGLA por pack: con el pack la sigla se reconoce; SIN el pack NO — la sigla es
    # un dato del pack, no del código común (una sigla con puntos no es 3+ mayúsculas contiguas).
    _, r4con = ann("Conforme al art. 5 del C.C. procede el archivo.", extra_patterns=extra)
    _, r4sin = ann("Conforme al art. 5 del C.C. procede el archivo.")
    check("sigla por pack 'art. 5 del C.C.': con pack co → detectada", r4con["citas"] == 1)
    check("sigla por pack 'art. 5 del C.C.': SIN pack → NO detectada (sigla = dato del pack)",
          r4sin["citas"] == 0)

    # 44 · rango con sigla del pack ("arts. 1 a 3 C.P.C.").
    _, r5 = ann("Los arts. 1 a 3 C.P.C. regulan el punto.", extra_patterns=extra)
    check("rango con sigla 'arts. 1 a 3 C.P.C.' con pack co → detectada", r5["citas"] == 1)

    # 45 · DISCIPLINA: 'art. 5' suelto (sin cuerpo normativo ni sigla) NO se marca — la forma
    # abreviada conserva la misma exigencia que la completa (evita el "art." periodístico).
    _, r6 = ann("El art. 5 zanja la cuestión sin más trámite.", extra_patterns=extra)
    check("disciplina: 'art. 5' suelto (sin cuerpo ni sigla) → NO detectado (0 citas)",
          r6["citas"] == 0)


# ── El ANCLA [doc n] como fuente de verdad del respaldo por expediente ─────────
# El respaldo por cotejo textual GLOBAL certificaba en verde una cita solo porque su texto
# apareciera en ALGÚN documento. Se invierte la carga: una cita queda respaldada por el
# expediente únicamente si lleva un ancla [doc n] cerca (antes o después) Y el CONTENIDO de
# ESE documento la contiene (respetando fronteras numéricas). Sin ancla → siempre [VERIFICAR],
# aunque el cotejo global la hallara en otra pieza. Marcar de más es inofensivo; respaldar de
# más destruye la única razón por la que un abogado confiaría en esto.

def run_ancla_fuente_de_verdad() -> None:
    print("\n-- Ancla como fuente de verdad del respaldo por expediente --")
    ann = verification.annotate_draft
    doc_ley = [{"content": "El contrato invoca la Ley 1437 de 2011 en su cláusula tercera.",
                "filename": "contrato.pdf"}]

    # 46 · cita CON ancla [doc 1] a un documento cuyo contenido la respalda → respaldada.
    a7, r7 = ann("Según el contrato [doc 1], aplica la Ley 1437 de 2011.",
                 documents=doc_ley, num_documents=1)
    check("cita anclada [doc 1] a doc que la contiene → respaldada, sin [VERIFICAR]",
          r7["respaldadas"] == 1 and r7["anotadas"] == 0 and MARK not in a7)

    # 47 · INVERSIÓN: la MISMA cita SIN ancla queda [VERIFICAR], aunque el documento la
    # contenga — el cotejo global ya no basta (esta es la carga que se invierte).
    a8, r8 = ann("Aplica la Ley 1437 de 2011 al caso, sin más.",
                 documents=doc_ley, num_documents=1)
    check("cita SIN ancla, aunque el doc la contenga → [VERIFICAR] (carga invertida)",
          r8["respaldadas"] == 0 and r8["anotadas"] == 1 and MARK in a8)

    # 48 · cita con ancla a un documento cuyo contenido NO la respalda → [VERIFICAR].
    doc_otro = [{"content": "El contrato trata de arrendamiento, plazos y cánones mensuales."}]
    a9, r9 = ann("Según el contrato [doc 1], aplica la Ley 1437 de 2011.",
                 documents=doc_otro, num_documents=1)
    check("cita anclada [doc 1] a doc que NO la contiene → [VERIFICAR]",
          r9["respaldadas"] == 0 and r9["anotadas"] == 1 and MARK in a9)

    # 49 · ancla ANTEPUESTA (antes de la cita) también respalda.
    a10, r10 = ann("El [doc 1] establece que la Ley 1437 de 2011 rige la actuación.",
                   documents=doc_ley, num_documents=1)
    check("ancla ANTEPUESTA '[doc 1] ... Ley 1437 de 2011' → respaldada",
          r10["respaldadas"] == 1 and MARK not in a10)

    # 50 · frontera numérica CON ancla: 'Decreto 108' anclada a un doc que dice
    # 'Decreto 1082 de 2015' NO se certifica (el peor defecto: respaldar de más).
    doc_dec = [{"content": "El Decreto 1082 de 2015 regula la contratación estatal."}]
    a11, r11 = ann("Según [doc 1], el Decreto 108 obliga a publicar el aviso.",
                   documents=doc_dec, num_documents=1)
    est11 = {d["cita"]: d["estado"] for d in r11["detalle"]}
    check("frontera con ancla: 'Decreto 108' anclada a doc con 'Decreto 1082 de 2015' → NO respaldada",
          r11["respaldadas"] == 0 and est11.get("Decreto 108") == "anotada" and MARK in a11)

    # 51 · la cita respaldada por ancla conserva su atribución al EXPEDIENTE en el informe.
    check("respaldo por ancla: el informe atribuye la fuente al expediente ([doc 1])",
          r7["detalle"][0].get("fuente", {}).get("referencia") == "[doc 1]"
          and r7["detalle"][0].get("fuente", {}).get("tipo") == "expediente")

    # 52 · RETROCOMPAT: sin `documents`, el respaldo por corpus sigue funcionando sin ancla
    # (las dos vías son independientes; no se rompió la que ya existía).
    fuente = [{"tipo": "norma", "referencia": "Ley 1437 de 2011", "titulo": "corpus"}]
    a12, r12 = ann("Aplica la Ley 1437 de 2011 al caso.", sources=fuente)
    check("retrocompat: sin documents, el corpus respalda la cita sin ancla",
          r12["respaldadas"] == 1 and MARK not in a12)


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
