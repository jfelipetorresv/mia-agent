"""Mia · eval.banco04.evaluador_congelado — copia VENDORIZADA de la segmentación y el cotejo.

DECISIÓN DEL DIRECTOR (C11, 2026-10-12): el evaluador del banco 0.4 es UN ÚNICO ARTEFACTO
CONGELADO para las dos versiones (§9.6). Si `agents/verification.py` (código del PRODUCTO) cambia
en 0.4, el Bloque 7 segmentaría y cotejaría distinto que el Bloque 0. Por eso todo `eval/banco04`
importa de aquí y NUNCA de `mia.agents.verification` (gate en `execution/test_banco04_juicio.py`).

ORIGEN (copia literal, sin editar el cuerpo de ninguna definición):
  · commit 7b9aaa0 · backend/mia/agents/verification.py
      sha256 del archivo de origen: ebbdcc359c659ec33d6b8492a0be2adc3461c6923b98fd89d6135217118606e1
      definiciones: segment_sentences, scan_citations, _normalize, _DOC_REF_RE y su cierre
      transitivo de dependencias de nivel superior (BASE_CITATION_PATTERNS, MARK_WINDOW_CHARS,
      VERIFY_MARK, _ARTICLE_NUMBERS, _ASSERT_ABBREVIATIONS, _INNER_SEPARATORS, _NORM_BODY,
      _SENT_TERMINATORS, _SENT_TRAILING_CLOSERS, _machine_block_boundaries, _norm_token,
      _preceding_token, compile_patterns), en el orden del original.
  · commit 7b9aaa0 · backend/mia/eval/scoring.py
      sha256 del archivo de origen: 13d15446c6a3814e333ef0f47ae4412da04eb3ebfd5f1c5fc38f26a1c9e18e5f
      definiciones: _normalize_cita, FLAG_MISSING_BURIED_FACT, recall_markers_signal.

ÚNICA ADAPTACIÓN: `_normalize_cita` llama a `verification._normalize`; aquí el nombre
`verification` se enlaza a un espacio de nombres cuyo `_normalize` es la copia de este módulo.
Extracción reproducible: `git show 7b9aaa0:<ruta>` + cierre transitivo por AST.
"""
# ── Copia literal de backend/mia/agents/verification.py @ 7b9aaa0 ──────────────────
from __future__ import annotations


import re


import unicodedata


import hashlib


from typing import Optional


VERIFY_MARK = "[VERIFICAR]"


# Ventana hacia adelante en la que una marca existente "cubre" la cita. Cubre el
# patrón usual del redactor: la marca va al lado o al final de la frase de la cita.
MARK_WINDOW_CHARS = 160


# ── Piezas compartidas por las formas del artículo (completa y abreviada) ─────
# Cuerpo normativo que DEBE seguir a un artículo para que cuente como cita (y no el
# "artículo" periodístico): un Código nombrado, una Ley/Decreto con número, la
# Constitución, o una SIGLA en mayúsculas (3-10 letras contiguas, p. ej. "CPACA").
# Léxico genérico del Civil Law hispano — ningún país, corte ni código concreto.
_NORM_BODY = (
    r"(?:C[oó]digo\s+[\wáéíóúñÁÉÍÓÚÑ]+(?:\s+[\wáéíóúñÁÉÍÓÚÑ]+){0,4}"
    r"|Ley\s+\d+(?:\s+de\s+\d{4})?"
    r"|Decreto\s+\d+(?:\s+de\s+\d{4})?"
    r"|Constituci[oó]n(?:\s+Pol[ií]tica)?(?:\s+de\s+\d{4})?"
    r"|[A-ZÁÉÍÓÚÑ]{3,10}\b)"
)


# Lista de números de artículo: "N", "N, M", "N y M", "N a M" (rango), cerrando con
# "y ss."/"y siguientes" opcional. El separador es EXPLÍCITO (", ", " y ", " a ") y el
# sufijo del número excluye dígitos: sin ambigüedad entre cuantificadores anidados no hay
# backtracking exponencial (ReDoS) ante el texto de documentos de terceros.
_ARTICLE_NUMBERS = (
    r"\d+[A-Za-z°º]*(?:(?:\s*,\s*|\s+y\s+|\s+a\s+)\d+[A-Za-z°º]*)*"
    r"(?:\s+y\s+s(?:s|iguientes)\.?)?"
)


# Patrones BASE (léxico jurídico genérico en español — ver docstring). Cada pack de
# jurisdicción puede AÑADIR los suyos vía citation_style.json → "citation_patterns" y sus
# siglas de código vía "code_abbreviations" (ver code_abbreviation_patterns).
BASE_CITATION_PATTERNS: tuple[str, ...] = (
    # Normas con número: "Ley 1437 de 2011", "Decreto Ley 19 de 2012", "Resolución 123"
    r"\b(?:Ley|Decreto(?:\s+(?:Ley|Legislativo))?|Resoluci[oó]n|Acuerdo|Circular|Ordenanza)"
    r"\s+(?:No\.?\s*)?\d+[\w./-]*(?:\s+de\s+\d{4})?",
    # Providencias: "Sentencia C-355 de 2006", "Sentencia SU-230/15", "Sentencia 12345"
    r"\bSentencias?\s+(?:No\.?\s*)?[A-Z]{0,3}[-\s]?\d+[\w./-]*(?:\s+de\s+\d{4})?",
    # Autos con fecha: "Auto 123 de 2020"
    r"\bAutos?\s+(?:No\.?\s*)?\d+[\w./-]*\s+de\s+\d{4}",
    # Artículo CON su cuerpo normativo, forma COMPLETA o ABREVIADA:
    #   "artículo 164 del CPACA", "artículos 21 de la Ley 640 de 2001",
    #   "art. 90 de la Constitución Política", "arts. 1 a 3 del Código Civil".
    # El artículo suelto ("el art. 5") NO se marca: sin cuerpo normativo suele referirse a
    # la norma ya citada en la misma frase (y evita el "artículo" periodístico). La forma
    # abreviada ligada a una SIGLA del pack ("arts. 1516 y ss. C.C.") entra por
    # code_abbreviation_patterns, no aquí (la sigla es dato del pack, no del código).
    r"\b(?:art[ií]culos?|arts?\.)\s+" + _ARTICLE_NUMBERS
    + r"\s+(?:de\s+la\s+|del?\s+)" + _NORM_BODY,
    # Subdivisión de un artículo nombrado: "inciso 2 del artículo 5", "parágrafo del
    # artículo 90", "numeral 3 del artículo 12". Nombrar un artículo concreto ya es una
    # cita legal — el cuerpo normativo puede ir o no.
    r"\b(?:inciso|numeral|par[aá]grafo|literal|ordinal)s?\s+(?:\d+[A-Za-z°º]*\s+)?"
    r"del?\s+art[ií]culos?\s+\d+[A-Za-z°º]*",
    # Radicados / expedientes con número largo
    r"\b(?:Radicado|Radicaci[oó]n|Expediente)\s+(?:No\.?\s*)?\d[\d.\-/]{4,}",
)


def compile_patterns(extra: Optional[list[str]] = None) -> list[re.Pattern]:
    """Patrones compilados: base + los del pack de jurisdicción (si los trae).

    Un patrón extra inválido se IGNORA (fail-soft): un pack mal editado no puede
    tumbar el turno del abogado.
    """
    compiled = [re.compile(p, re.IGNORECASE) for p in BASE_CITATION_PATTERNS]
    for p in extra or []:
        try:
            compiled.append(re.compile(str(p), re.IGNORECASE))
        except re.error:
            continue
    return compiled


# Separadores que pueden ir DENTRO de un identificador ("C-355", "25.326",
# "25000-23-41-000-2024", "SU-230/15") o entre palabras ("art. 5", "21, 22 y 23").
# Se conservan solo cuando van entre dos alfanuméricos: ahí son parte del número.
_INNER_SEPARATORS = ".,-/"


def _normalize(text: str) -> str:
    """minúsculas · sin tildes · separadores colapsados a un espacio (para comparar).

    OJO (corrección del falso "Con respaldo"): los separadores que van DENTRO de un
    número NO se colapsan. Antes "Ley 25.326" quedaba "ley 25 326" y eso partía el
    identificador en dos, de modo que "Ley 25" lo respaldaba por prefijo. Ahora
    "25.326", "c-355" y "25000-23-41-000-2024" sobreviven como una sola pieza y solo
    respaldan a quien traiga el número COMPLETO.
    """
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn").lower()
    out: list[str] = []
    for i, ch in enumerate(text):
        if ch in _INNER_SEPARATORS:
            prev = text[i - 1] if i else ""
            nxt = text[i + 1] if i + 1 < len(text) else ""
            out.append(ch if (prev.isalnum() and nxt.isalnum()) else " ")
        else:
            out.append(ch)
    return re.sub(r"\s+", " ", "".join(out)).strip()


# ── Guardián de referencias al expediente ([doc n] fantasma) ─────────────────
# Los documentos del expediente se sellan como <<<DOC 1>>> … <<<DOC N>>>
# (ver agents/untrusted.render_documents) y el modelo los cita como [doc n]. El
# rango válido es 1..N, con N = documentos recuperados en el turno. Una cita
# [doc k] con k FUERA de ese rango es una referencia FANTASMA: el modelo inventó
# un documento que nunca se le entregó (el equivalente a citar un identificador
# inexistente). Hoy esa cita pasa como si estuviera respaldada — nadie valida que
# el número exista. Este guardián la trata como toda cita sin respaldo: le AÑADE
# [VERIFICAR] al lado (nunca borra ni bloquea — sobre-marcar es inofensivo, la
# misma filosofía de annotate_draft).
#
# El patrón es deliberadamente estrecho para no generar falsos positivos: exige
# que el corchete contenga SOLO uno o varios enteros ("[doc 3]", "[doc. 2]",
# "[documento 4]", "[docs 1, 2 y 3]"). Un corchete con texto no numérico
# ("[doc 2023-cv-1]") NO coincide y queda intacto.
# Limitación conocida (falso negativo, dirección segura): un rango con guion
# ("[docs 3-9]") no se descompone — solo se evalúa el primer entero.
_DOC_REF_RE = re.compile(
    r"\[\s*doc(?:umento)?s?\.?\s*(\d+(?:\s*(?:,|y)\s*\d+)*)\s*\]", re.IGNORECASE
)


def scan_citations(text: str, patterns: Optional[list[re.Pattern]] = None) -> list[dict]:
    """Todas las citas detectadas, sin solaparse (gana la más temprana/larga).

    Devuelve [{"citation", "start", "end", "marked"}] ordenado por posición.
    `marked` = ya hay un [VERIFICAR] dentro de la ventana POSTERIOR a la cita
    (limitación conocida: una marca ANTEPUESTA — "[VERIFICAR] Ley 100..." — no se
    detecta y la cita recibe una segunda marca; sobre-marcar es inofensivo por
    diseño, el estilo de la casa pone la marca después de la cita).
    """
    pats = patterns or compile_patterns()
    raw: list[tuple[int, int, str]] = []
    for pat in pats:
        for m in pat.finditer(text or ""):
            raw.append((m.start(), m.end(), m.group(0)))
    # dedupe por solape: orden (start asc, end desc) y descartar lo que pise lo ya aceptado
    raw.sort(key=lambda t: (t[0], -t[1]))
    out: list[dict] = []
    last_end = -1
    for start, end, cit in raw:
        if start < last_end:
            continue
        out.append({"citation": cit.strip(), "start": start, "end": end, "marked": False})
        last_end = end
    # `marked`: la marca pertenece SOLO a la cita inmediatamente anterior — la ventana
    # se corta donde arranca la SIGUIENTE cita (si no, un [VERIFICAR] lejano "cubriría"
    # citas previas que sí necesitan su propia marca).
    for i, c in enumerate(out):
        stop = c["end"] + MARK_WINDOW_CHARS
        if i + 1 < len(out):
            stop = min(stop, out[i + 1]["start"])
        window = (text or "")[c["end"]:stop]
        c["marked"] = VERIFY_MARK[:-1] in window  # "[VERIFICAR" cubre "[VERIFICAR ...]" largos
    return out


# ── Segmentación en ORACIONES para el INFORME (NUNCA para editar el texto) ────
# Invariante central (§2.1): la segmentación alimenta SOLO el informe por oración; las
# decisiones de marcar/omitir siguen saliendo, byte a byte, de scan_citations/annotate_draft.
# Un error de segmentación jamás puede producir fuga ni falso bloqueo — a lo sumo atribuye una
# cita a la oración vecina. Por eso es defendible construir un segmentador heurístico.
_SENT_TERMINATORS = frozenset(".?!")


# Comillas y paréntesis de cierre que, tras un terminador, pertenecen a la oración que TERMINA
# (no arrancan la siguiente): «…afirmación.»  ·  (…afirmación).  ·  "…afirmación."
_SENT_TRAILING_CLOSERS = frozenset("\"'»”’)]}")


# Abreviaturas de FORMA (no de país): tras ellas un `.` no cierra oración. Léxico genérico del
# español jurídico del Civil Law — ningún nombre de código, corte ni país (esos entran por el
# pack, jamás aquí). Normalizadas (sin tildes, minúsculas) para el cotejo.
_ASSERT_ABBREVIATIONS: frozenset = frozenset(
    {"art", "arts", "inc", "num", "ord", "par", "pag", "p", "ss", "no", "nro", "cfr", "vs"})


def _norm_token(tok: str) -> str:
    """minúsculas · sin tildes, para un solo token (guarda de abreviaturas)."""
    t = unicodedata.normalize("NFD", tok or "")
    return "".join(c for c in t if unicodedata.category(c) != "Mn").lower()


def _preceding_token(text: str, i: int) -> str:
    """Caracteres alfanuméricos inmediatamente ANTES del índice i (el token que precede al `.`)."""
    j = i
    while j > 0 and text[j - 1].isalnum():
        j -= 1
    return text[j:i]


def _machine_block_boundaries(text: str) -> set[int]:
    """Fronteras DURAS del bloque de máquina del cierre (regla 50): ninguna oración cruza un
    marcador `=== … ===`, y CADA línea etiquetada del interior (`Problema jurídico:` /
    `Normas y fuentes:` / `Riesgo y recomendación:`) es su propia frontera. Se hace por FORMA
    —las líneas entre dos fences `===`—, sin hardcodear las etiquetas (agnóstico): así las tres
    líneas del cierre no se funden aunque no traigan puntuación terminal."""
    bounds: set[int] = set()
    lines: list[tuple[int, int, bool]] = []
    pos = 0
    for line in (text or "").splitlines(keepends=True):
        is_fence = "===" in line
        lines.append((pos, pos + len(line), is_fence))
        if is_fence:
            bounds.add(pos)
            bounds.add(pos + len(line))
        pos += len(line)
    # Interior de un bloque fenced (líneas entre dos `===` consecutivos): cada línea es frontera.
    fence_idx = [i for i, (_s, _e, f) in enumerate(lines) if f]
    for a, b in zip(fence_idx, fence_idx[1:]):
        for i in range(a + 1, b):
            bounds.add(lines[i][1])   # frontera al final de cada línea interior
    return bounds


def segment_sentences(text: str,
                      protected_spans: Optional[list] = None) -> list:
    """Parte `text` en oraciones para el INFORME por oración — NUNCA para editar el texto.

    Agnóstico (§2): corta en `.?!` y en línea en blanco; jamás DENTRO de una cita detectada
    (`protected_spans`, ya calculados por scan_citations — NO se re-escanea, m4) NI dentro de un
    ancla `[doc n]` (se protegen aquí con `_DOC_REF_RE`, una sola pasada barata — no es el
    escáner completo que m4 prohíbe); respeta una guarda de abreviaturas de FORMA (art./inc./No.
    …) y de iniciales/siglas de EXACTAMENTE un carácter (C.C., art. 5.); absorbe comillas y
    paréntesis de cierre finales en la oración que termina; y trata el bloque de máquina del
    cierre (`=== … ===` + sus líneas etiquetadas) como fronteras duras (regla 50).

    Devuelve las oraciones NO vacías [(inicio, fin) …]: cada cita cae en exactamente una por su
    offset de inicio. Su PEOR caso es granularidad imperfecta del informe (§2.1) — nunca una
    fuga ni un falso bloqueo."""
    text = text or ""
    n = len(text)
    if n == 0:
        return []
    prot = [(int(s), int(e)) for s, e in (protected_spans or []) if int(e) > int(s)]
    # Además de las citas, se protegen los anclas [doc n] para que `[doc 1].` corte DESPUÉS del
    # `]` y `[doc. 1]` no se parta por dentro (M1). Es una pasada de UN patrón estrecho, no el
    # escáner de citas completo (base+pack) que m4 pide no repetir.
    for m in _DOC_REF_RE.finditer(text):
        prot.append((m.start(), m.end()))
    prot.sort()

    def _in_citation(idx: int) -> bool:
        for s, e in prot:
            if s <= idx < e:
                return True
            if s > idx:
                break
        return False

    forced = _machine_block_boundaries(text)
    cuts: set[int] = set()
    i = 0
    while i < n:
        ch = text[i]
        if ch == "\n":
            j = i + 1
            while j < n and text[j] in " \t\r":
                j += 1
            if j < n and text[j] == "\n":
                cuts.add(j + 1)          # línea en blanco → frontera de oración
        elif ch in _SENT_TERMINATORS and not _in_citation(i):
            guarded = False
            if ch == ".":
                prev = _preceding_token(text, i)
                # Iniciales/siglas de EXACTAMENTE un carácter (C.C., art. 5.) y abreviaturas de
                # forma (art./inc./No.) no cierran oración. `prev==""` (p. ej. tras `]`) NO se
                # guarda: `[doc 1].` debe cortar (M1). Los identificadores con punto interno
                # (25.326) los cubre `protected_spans` (mecanismo primario, §2.2.1).
                guarded = len(prev) == 1 or _norm_token(prev) in _ASSERT_ABBREVIATIONS
            if not guarded:
                cut = i + 1
                # Absorber comillas/paréntesis de cierre en la oración que termina (no dejarlos
                # de arranque de la siguiente): «…afirmación.»  o  (…afirmación).
                while cut < n and text[cut] in _SENT_TRAILING_CLOSERS:
                    cut += 1
                cuts.add(cut)
        i += 1
    bounds = sorted((cuts | forced | {n}) - {0})
    spans: list = []
    start = 0
    for b in bounds:
        if start < b <= n:
            if text[start:b].strip():        # oraciones vacías / solo-espacio quedan FUERA (m1)
                spans.append((start, b))
            start = b
    return spans


ORIGEN_COMMIT = "7b9aaa0"
ORIGEN_SHA256 = {
    "backend/mia/agents/verification.py": "ebbdcc359c659ec33d6b8492a0be2adc3461c6923b98fd89d6135217118606e1",
    "backend/mia/eval/scoring.py": "13d15446c6a3814e333ef0f47ae4412da04eb3ebfd5f1c5fc38f26a1c9e18e5f",
}


# ── Copia literal de backend/mia/eval/scoring.py @ 7b9aaa0 ─────────────────────────────
from types import SimpleNamespace as _SimpleNamespace  # noqa: E402

verification = _SimpleNamespace(_normalize=_normalize)  # única adaptación (ver cabecera)


def _normalize_cita(text: str) -> str:
    """Normaliza una cita para comparar (minúsculas, sin tildes, sin puntuación) y unifica la
    abreviatura 'art.' con 'artículo' — así 'art. 90' casa con 'artículo 90'."""
    s = verification._normalize(text)          # minúsculas · sin tildes · separadores colapsados
    return re.sub(r"\bart\b", "articulo", s)


FLAG_MISSING_BURIED_FACT = "dato_enterrado_ausente_en_la_respuesta"


def recall_markers_signal(diagnosis: str, draft: str, markers: tuple[str, ...] | list[str]) -> dict:
    """¿La respuesta demuestra haber leído los fragmentos enterrados del expediente?

    Devuelve siempre la misma forma (aunque no haya marcadores) para que el panel y el
    comparador puedan leerla sin ramas especiales. Sin marcadores declarados: `aplica=False`
    — y NO se reporta como 1.0, para que un caso sin marcadores no se lea como recuperación
    perfecta (sería un PASS vacío, del que este proyecto ya tiene historia).
    """
    limpios = [str(m) for m in (markers or []) if str(m).strip()]
    if not limpios:
        return {
            "aplica": False, "cobertura": None, "encontrados": [], "faltantes": [],
            "n_marcadores": 0, "flags": [], "ok": True,
        }

    texto_norm = _normalize_cita(f"{diagnosis or ''}\n{draft or ''}")
    encontrados = [m for m in limpios if _normalize_cita(m) in texto_norm]
    faltantes = [m for m in limpios if m not in encontrados]
    return {
        "aplica": True,
        "cobertura": round(len(encontrados) / len(limpios), 4),
        "encontrados": encontrados,
        "faltantes": faltantes,
        "n_marcadores": len(limpios),
        "flags": [FLAG_MISSING_BURIED_FACT] if faltantes else [],
        "ok": not faltantes,
    }




# ── R2-C-N4 · `jurisdiction_leak_signal` vendorizada Y CORREGIDA ───────────────────────
# Origen: backend/mia/eval/scoring.py en HEAD 3611b75 (árbol de trabajo sin cambios en ese archivo;
# sha256 en `ORIGEN_FUGA`). Se copian `_NEGATION_NEAR_CITATION`, `_NEGATION_NORM`, `_SENTENCE_SPLIT`
# y `_oracion_de` LITERALES (con `verification._normalize` → `_normalize` de esta copia).
#
# CORRECCIÓN (única diferencia con el producto): en el producto, `_mencion_negada` mira si la
# ORACIÓN tiene alguna negación (scoring.py:188-192), así que «La Ley 100 de 1993 es aplicable al
# caso, aunque no consta la fecha del contrato» deja de ser fuga por un «no consta» que niega OTRA
# cosa. Aquí la negación tiene que estar en la MISMA CLÁUSULA que la cita: la oración se parte en
# cláusulas por coma (salvo la que abre una relativa: «, que…», «, cuyo…», «, la cual…») y por los
# conectores que abren otra proposición (aunque, pero, sino, mientras, porque, pues, ya que, dado
# que, puesto que, si bien, no obstante, sin embargo, pese a que, a pesar de que). Una coma DENTRO
# de la cita no parte nada. El defecto PERSISTE en el producto (`scoring.py` no se tocó: es código
# del producto, fuera del frente del banco).
ORIGEN_FUGA = {"archivo": "backend/mia/eval/scoring.py", "commit": "3611b75",
               "sha256": "f7765c505b3e4bd32c54288f916977cc25117430f1cf43a9f50b1165bbbad15c"}

_NEGATION_NEAR_CITATION: tuple[str, ...] = (
    "no corresponde", "no reconozco", "no la reconozco", "no lo reconozco",
    "no existe", "no aparece", "no figura", "no consta",
    "no es verificable", "no puedo verificar", "no logro verificar", "no pude verificar",
    "no verificable", "sin verificar",
    "no citable", "no es citable",
    "no tengo respaldo", "sin respaldo", "no puedo respaldar",
    "no puedo confirmar", "no me consta",
    "no está configurado", "no configurado",
    "materialmente imposible", "no puede ser", "no coincide",
    "presunta", "presunto", "supuesta norma", "inexistente",
)
_NEGATION_NORM: tuple[str, ...] = tuple(
    verification._normalize(p) for p in _NEGATION_NEAR_CITATION)
_SENTENCE_SPLIT = re.compile(r"(?<=[.;:!?])\s+|\n+")


def _oracion_de(text: str, start: int, end: int) -> str:
    """La oración que contiene el tramo [start, end) del texto. Pura."""
    if not text:
        return ""
    ini = 0
    for m in _SENTENCE_SPLIT.finditer(text, 0, start):
        ini = m.end()
    fin = len(text)
    m2 = _SENTENCE_SPLIT.search(text, end)
    if m2 is not None:
        fin = m2.start()
    return text[ini:fin]


# ── Corrección R2-C-N4 (no está en el producto) ──
_CONECTORES_CLAUSULA = (
    "aunque", "pero", "sino", "mientras", "porque", "pues", "ya que", "dado que", "puesto que",
    "si bien", "no obstante", "sin embargo", "pese a que", "a pesar de que",
)
_CORTE_CLAUSULA = re.compile(
    r",(?!\s*(?:que|cuy[oa]s?|l[oa]s?\s+cual(?:es)?|el\s+cual|quien(?:es)?|donde)\b)"
    r"|\s+(?=(?:" + "|".join(c.replace(" ", r"\s+") for c in _CONECTORES_CLAUSULA) + r")\b)",
    re.IGNORECASE)


def _clausula_de(text: str, start: int, end: int) -> str:
    """La cláusula de la oración que contiene la cita [start, end): los cortes que caen DENTRO de
    la cita no cuentan (una cita con comas no se parte)."""
    ini = 0
    for m in _SENTENCE_SPLIT.finditer(text, 0, start):
        ini = m.end()
    fin = len(text)
    m2 = _SENTENCE_SPLIT.search(text, end)
    if m2 is not None:
        fin = m2.start()
    c_ini, c_fin = ini, fin
    for m in _CORTE_CLAUSULA.finditer(text, ini, fin):
        if m.end() <= start:
            c_ini = m.end()
        elif m.start() >= end:
            c_fin = m.start()
            break
    return text[c_ini:c_fin]


def _mencion_negada(text: str, start: int, end: int) -> bool:
    """¿La cita en [start, end) va acompañada de una negación explícita en SU MISMA CLÁUSULA?
    (N-1: mención ≠ uso; R2-C-N4: la negación tiene que regir la cita). Pura y determinista."""
    clausula = verification._normalize(_clausula_de(text, start, end))
    return any(p in clausula for p in _NEGATION_NORM)


def jurisdiction_leak_signal(text: str, extra_patterns: object = None) -> dict:
    """Copia de `scoring.jurisdiction_leak_signal` (misma forma de salida, `v` = 2) con la
    negación asociada a la cita (R2-C-N4; ver la cabecera de esta sección)."""
    pats = compile_patterns(extra_patterns if isinstance(extra_patterns, list) else None)
    t = text or ""
    citas = scan_citations(t, pats)
    usadas, negadas = [], []
    for c in citas:
        (negadas if _mencion_negada(t, c["start"], c["end"]) else usadas).append(c["citation"])
    return {
        "citas_detectadas": len(citas),
        "negadas": len(negadas),
        "citas_computadas": len(usadas),
        "detalle": usadas[:10],
        "detalle_negadas": negadas[:10],
        "leak": len(usadas) > 0,
        "v": 2,
        "negacion": "por_clausula",
    }
