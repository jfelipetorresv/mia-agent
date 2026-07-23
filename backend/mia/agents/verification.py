"""Mia · agents.verification — verificación determinista de citas del borrador (CP9).

El especialista de VERIFICACIÓN del equipo no es un LLM: es un escáner determinista
(sin red, sin DB, sin costo) que recorre el borrador buscando citas legales
(normas, providencias, artículos con su cuerpo normativo, radicados) y garantiza
la disciplina [VERIFICAR]:

  - Una cita ya marcada con [VERIFICAR] cerca → se respeta (cuenta como "marcada").
  - Una cita que coincide con una fuente recuperada del corpus del sistema en este
    turno → "respaldada" (el corpus es curado; aun así el abogado verifica antes
    de radicar — regla de siempre).
  - Una cita SIN marca y SIN respaldo → se le AÑADE " [VERIFICAR]" al lado
    ("anotada"). Añadir una marca de más es inofensivo (el abogado revisa algo que
    estaba bien); no añadirla es el riesgo real detectado en la comparación A/B de
    CP6 (sentencias específicas sin marca).

Horizontalidad (regla de Fase 5): los patrones base cubren el español jurídico
GENÉRICO del Civil Law hispano (Ley/Decreto/Sentencia/artículo/radicado — léxico
común, no conocimiento de un país). Lo específico de cada jurisdicción entra por
su pack (`citation_style.json → "citation_patterns"`), nunca por código.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Optional

VERIFY_MARK = "[VERIFICAR]"
# Reemplazo de una cita SIN respaldo bajo jurisdicción desconocida (`omit_unbacked` de
# annotate_draft): el span de la cita se sustituye por esta marca — visible, en lenguaje
# del abogado, sin nombrar ningún país (el módulo sigue agnóstico). El texto original de
# la cita omitida queda en el informe de verificación, no en el texto emitido.
OMIT_MARK = "[referencia normativa omitida: ordenamiento no configurado]"
# Ventana hacia adelante en la que una marca existente "cubre" la cita. Cubre el
# patrón usual del redactor: la marca va al lado o al final de la frase de la cita.
MARK_WINDOW_CHARS = 160
# Ventana en la que un ancla [doc n] "abraza" una cita (ANTES o DESPUÉS de ella). Es la
# cercanía que exige el respaldo por ancla (ver annotate_draft y _anchored_doc_backing):
# el redactor pone la referencia al documento pegada a la cita, no a tres párrafos.
ANCHOR_WINDOW_CHARS = 200

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


def code_abbreviation_patterns(abbreviations: Optional[list[str]]) -> list[str]:
    """Regex EXTRA que ligan una forma de artículo a una SIGLA de código del pack.

    Mecánica pura (código común, sin país): las siglas son DATOS del pack
    (citation_style.json → "code_abbreviations", p. ej. "C.C.", "C. Co."). Por cada sigla
    se compone un patrón "artículo(s)/art(s). N [y ss.] [de la|del]? SIGLA", con los puntos
    de la sigla ESCAPADOS (así "C.C." casa literal, no "CxC") y los espacios internos
    flexibles ("C. Co." con uno o más espacios). Una sigla vacía se ignora.

    A diferencia de la forma con cuerpo normativo (que va en los patrones BASE, genérica),
    aquí el "de la/del" es OPCIONAL: el redactor escribe "arts. 1516 y ss. C.C." pegando la
    sigla al número. La sigla ES el cuerpo normativo, así que tampoco hay falso positivo
    periodístico. El lookahead final impide que una sigla corta ("C.P.") muerda a otra más
    larga que la contiene ("C.P.A.C.A.": esa la reconoce su propio patrón, entero).

    Estos patrones se pasan como `extra_patterns` (mismo canal que citation_patterns del
    pack) — el puente lo tiende agents/research.citation_patterns_for."""
    pats: list[str] = []
    for raw in abbreviations or []:
        ab = str(raw).strip()
        if not ab:
            continue
        sigla = r"\s*".join(re.escape(part) for part in ab.split())
        pats.append(
            r"\b(?:art[ií]culos?|arts?\.)\s+" + _ARTICLE_NUMBERS
            + r"\s+(?:de\s+la\s+|del?\s+)?" + sigla + r"(?![A-Za-z.])"
        )
    return pats


# Separadores que pueden ir DENTRO de un identificador ("C-355", "25.326",
# "25000-23-41-000-2024", "SU-230/15") o entre palabras ("art. 5", "21, 22 y 23").
# Se conservan solo cuando van entre dos alfanuméricos: ahí son parte del número.
_INNER_SEPARATORS = ".,-/"
# Basura de borde que no aporta identidad (comillas, paréntesis, marcas de ordinal).
_EDGE_TRIM = "\"'`()[]{}«»¡!¿?;:*_" + _INNER_SEPARATORS + "°ºª"


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


# ── Cotejo cita ↔ fuente: por qué NO basta con "una está dentro de la otra" ───
# El cotejo de respaldo era `k in c or c in k` sobre el texto normalizado. Eso
# respaldaba en VERDE ("Con respaldo", atribuido a un archivo y folio concretos del
# expediente) citas que Mia INVENTÓ, con solo ser prefijo de una fuente real:
#
#     fuente "Decreto 1082 de 2015"  →  respaldaba  "Decreto 108"
#     fuente "Ley 1437 de 2011"      →  respaldaba  "Ley 143"
#     fuente "Sentencia C-355 de 2006" → respaldaba "Sentencia C-35"
#
# Es la regla dura del producto exactamente al revés: afirmar respaldo sin tenerlo.
# Marcar de más es inofensivo (el abogado revisa algo que estaba bien); respaldar de
# más destruye la única razón por la que un abogado confiaría en esto.
#
# La regla que cierra la CLASE de defecto (no los tres ejemplos):
#   1. Se compara por PIEZAS (tokens), no por substring: un identificador nunca se
#      puede partir por la mitad. "108" y "1082" son piezas distintas; "123" y
#      "123a" también; "25.326" es UNA pieza, no "25" y "326".
#   2. Las piezas comunes deben ser CONTIGUAS y en el mismo orden.
#   3. Si la fuente tiene piezas de MÁS pegadas al tramo común, esas piezas solo se
#      toleran si son conectores ("de", "del", "la"...). Así sobrevive el caso
#      legítimo ("Ley 80" respaldada por "Ley 80 de 1993", "Sentencia C-355" por
#      "Sentencia C-355 de 2006", "Ley 640 de 2001" dentro de "artículo 21 de la
#      Ley 640 de 2001") y se rechaza lo que cambia de disposición o de tipo de
#      norma ("Ley 5" vs "Ley 5 bis", "Ley 19" vs "Decreto Ley 19 de 2012").
#
# Los conectores son palabras vacías del español jurídico (el mismo léxico genérico
# de BASE_CITATION_PATTERNS — sin país, corte ni moneda). Y su AUSENCIA nunca
# produce un falso verde: solo hace que la cita quede marcada, que es la dirección
# segura. Una jurisdicción con otra convención de citación pierde confirmaciones,
# jamás gana un respaldo falso.
_QUALIFIER_TOKENS = frozenset({"de", "del", "la", "el", "los", "las", "y", "en"})


def _match_tokens(text: str) -> tuple[str, ...]:
    """Piezas comparables de una cita o de una referencia de fuente."""
    toks = []
    for raw in _normalize(text).split(" "):
        tok = raw.strip(_EDGE_TRIM)
        if tok:
            toks.append(tok)
    return tuple(toks)


def _covers(long_t: tuple[str, ...], short_t: tuple[str, ...]) -> bool:
    """`short_t` aparece completo y contiguo dentro de `long_t`, sin que las piezas
    sobrantes de los bordes cambien de qué norma se está hablando (ver bloque arriba)."""
    n, m = len(long_t), len(short_t)
    if not m or m > n:
        return False
    for i in range(n - m + 1):
        if long_t[i:i + m] != short_t:
            continue
        if i > 0 and long_t[i - 1] not in _QUALIFIER_TOKENS:
            continue  # la fuente antepone algo que cambia la norma ("Decreto" Ley 19)
        j = i + m
        if j < n and long_t[j] not in _QUALIFIER_TOKENS:
            continue  # la fuente continúa el identificador ("Ley 5" + "bis")
        return True
    return False


def _tokens_match(a: tuple[str, ...], b: tuple[str, ...]) -> bool:
    """Cotejo en ambos sentidos: la fuente puede estar dentro de la cita
    ('Ley 1437 de 2011' ⊂ 'artículo 164 de la Ley 1437 de 2011') o al revés
    ('Ley 80' ⊂ 'Ley 80 de 1993')."""
    if not a or not b:
        return False
    return _covers(a, b) or _covers(b, a)


def source_keys(sources: Optional[list[dict]]) -> list[str]:
    """Claves normalizadas de las fuentes del corpus recuperadas en el turno.

    Cada fuente (ver agents/research.py) trae `referencia` ("Ley 1437 de 2011",
    "Sentencia C-355 de 2006"). La clave normalizada permite el match textual
    contra la cita del borrador.
    """
    keys: list[str] = []
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        ref = _normalize(str(s.get("referencia") or ""))
        if ref:
            keys.append(ref)
    return keys


def _is_backed(citation: str, keys: list[str]) -> bool:
    """La cita coincide con alguna fuente del corpus, sin truncar identificadores
    (ver el bloque 'Cotejo cita ↔ fuente' arriba)."""
    c = _match_tokens(citation)
    if not c:
        return False
    return any(_tokens_match(c, _match_tokens(k)) for k in keys if k)


def source_index(sources: Optional[list[dict]]) -> list[tuple[str, dict]]:
    """[(clave_normalizada, fuente_compacta)] — como `source_keys` pero conservando la
    fuente, para que el informe pueda decir CUÁL fuente respaldó cada cita (Fase 1b:
    la pantalla muestra la referencia y deja saltar al texto)."""
    index: list[tuple[str, dict]] = []
    for s in sources or []:
        if not isinstance(s, dict):
            continue
        ref = _normalize(str(s.get("referencia") or ""))
        if ref:
            index.append((ref, s))
    return index


def _tokenize_index(index: list[tuple[str, dict]]) -> list[tuple[tuple[str, ...], dict]]:
    """Índice de fuentes ya troceado en piezas. Se calcula UNA vez por borrador: el
    material del expediente puede aportar cientos de claves y el cotejo corre por
    cada cita del borrador."""
    return [(_match_tokens(k), s) for k, s in index if k]


def _backing_source_tokenized(
    citation: str, tindex: list[tuple[tuple[str, ...], dict]]
) -> Optional[dict]:
    """La fuente que respalda la cita, o None. Gana la primera coincidencia, que llega
    en el orden de relevancia con que investigó el turno."""
    c = _match_tokens(citation)
    if not c:
        return None
    for kt, s in tindex:
        if _tokens_match(c, kt):
            return s
    return None


def _backing_source(citation: str, index: list[tuple[str, dict]]) -> Optional[dict]:
    """La fuente del corpus que respalda la cita, o None (mismo cotejo de `_is_backed`)."""
    return _backing_source_tokenized(citation, _tokenize_index(index))


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
_INT_RE = re.compile(r"\d+")


_SEALED_DOC_RE = re.compile(r"<<<\s*DOC\s+(\d+)", re.IGNORECASE)


def highest_sealed_doc_index(text: str) -> int:
    """Mayor índice n de un sello `<<<DOC n>>>` presente en `text` (0 si no hay).

    Un turno puede sellar documentos por DOS vías con numeración propia desde 1:
    los recuperados por RRF (agents/untrusted.render_documents) y los adjuntos por
    `@expediente` (agents/context_references, mismo label "DOC"). Ambos conviven en
    el mismo prompt. Para no marcar como fantasma una cita legítima a un adjunto,
    el rango válido de [doc n] debe cubrir el MAYOR índice sellado que vio el
    modelo — no solo el conteo de `state["documents"]`. Solo un [doc k] por encima
    de TODO lo sellado es fantasma con certeza. (`@carpeta` usa el label "ARCHIVO",
    no "DOC": no entra aquí y por eso no colisiona.)
    """
    idxs = [int(m.group(1)) for m in _SEALED_DOC_RE.finditer(text or "")]
    return max(idxs) if idxs else 0


def flag_phantom_doc_citations(text: str, num_documents: int) -> tuple[str, dict]:
    """Marca [VERIFICAR] junto a cada referencia [doc n] cuyo número no exista.

    `num_documents` = documentos recuperados en el turno (el rango válido es
    1..num_documents). Determinista y sin efectos (sin red, sin DB): nunca borra
    texto, solo INSERTA " [VERIFICAR]" tras las referencias a documentos fantasma.

    Devuelve (texto_anotado, informe):
      {"refs_doc": total, "fantasmas": n, "documentos_disponibles": N,
       "detalle": [{"cita", "numeros", "fuera_de_rango"}...]}
    """
    src = text or ""
    n = max(0, int(num_documents or 0))
    inserts: list[int] = []
    detalle: list[dict] = []
    fantasmas = 0
    total = 0
    for m in _DOC_REF_RE.finditer(src):
        total += 1
        nums = [int(x) for x in _INT_RE.findall(m.group(1))]
        fuera = [k for k in nums if k < 1 or k > n]
        # ya marcada = la marca va ADYACENTE al corchete (ventana estrecha, no los 160
        # chars del escáner legal). El guardián siempre inserta pegado al `]`, así que
        # detectar la adyacencia basta para ser idempotente; usar la ventana ancha
        # provocaría diafonía con un [VERIFICAR] de una cita legal cercana.
        tail = src[m.end():m.end() + len(VERIFY_MARK) + 2]
        already = VERIFY_MARK[:-1] in tail
        if fuera and not already:
            fantasmas += 1
            inserts.append(m.end())
            if len(detalle) < 50:
                detalle.append({
                    "cita": m.group(0).strip(),
                    "numeros": nums,
                    "fuera_de_rango": fuera,
                })
    # insertar de atrás hacia adelante para no desplazar los offsets pendientes
    for pos in sorted(inserts, reverse=True):
        src = src[:pos] + " " + VERIFY_MARK + src[pos:]
    return src, {
        "refs_doc": total,
        "fantasmas": fantasmas,
        "documentos_disponibles": n,
        "detalle": detalle,
    }


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


# ── Ancla como FUENTE DE VERDAD del respaldo por expediente ──────────────────
# El respaldo por cotejo textual GLOBAL (¿aparece la cita en ALGÚN documento?) es
# peligroso: certifica en verde una cita que el modelo puso donde no toca solo porque el
# número exista en otra pieza. La regla se invierte: una cita queda respaldada por el
# expediente únicamente si (i) lleva un ancla [doc n] cerca (ANTES o DESPUÉS, ventana
# ANCHOR_WINDOW_CHARS) y (ii) el CONTENIDO de ESE documento n contiene el texto de la cita,
# con el MISMO cotejo por piezas que el corpus (respeta fronteras numéricas: "Decreto 108"
# no lo respalda un doc que dice "Decreto 1082"). Que otro documento la contenga NO cuenta.
# Sin ancla → nunca respaldada por el expediente (queda para el corpus o [VERIFICAR]).


def _document_tokens(documents: Optional[list]) -> dict[int, tuple[str, ...]]:
    """{número_de_sello: piezas del contenido} para el cotejo por ancla.

    El documento en la posición i (0-based) se sella como <<<DOC i+1>>> (ver
    agents/untrusted.render_documents), así que su número de ancla [doc n] es i+1. Cada
    documento puede ser un dict con "content" o el texto pelado. Un contenido vacío no
    entra (no puede respaldar nada)."""
    out: dict[int, tuple[str, ...]] = {}
    for i, d in enumerate(documents or []):
        content = d.get("content") if isinstance(d, dict) else d
        toks = _match_tokens(str(content or ""))
        if toks:
            out[i + 1] = toks
    return out


def _document_titulo(documents: Optional[list], n: int) -> str:
    """Rótulo compacto del documento n para la atribución del informe (filename si lo trae)."""
    if not documents or n < 1 or n > len(documents):
        return ""
    d = documents[n - 1]
    if isinstance(d, dict):
        return str(d.get("filename") or d.get("titulo") or d.get("id") or "")
    return ""


def _anchored_doc_backing(
    citation: str, cit_start: int, cit_end: int, text: str,
    doc_tokens: dict[int, tuple[str, ...]],
) -> Optional[int]:
    """Número del documento anclado que RESPALDA la cita, o None.

    Ancla = una referencia [doc n] dentro de la ventana ANTES o DESPUÉS de la cita. La cita
    solo queda respaldada si el contenido de ESE documento n contiene sus piezas (cotejo
    LOCAL al documento anclado, no global). Solo se consideran documentos de los que se
    tiene contenido (`doc_tokens`): un ancla a un adjunto sin contenido cargado no respalda
    (dirección segura — marca de menos jamás inventa respaldo)."""
    if not doc_tokens:
        return None
    cit = _match_tokens(citation)
    if not cit:
        return None
    before = text[max(0, cit_start - ANCHOR_WINDOW_CHARS):cit_start]
    after = text[cit_end:cit_end + ANCHOR_WINDOW_CHARS]
    nums: set[int] = set()
    for window in (before, after):
        for m in _DOC_REF_RE.finditer(window):
            nums.update(int(x) for x in _INT_RE.findall(m.group(1)))
    for n in sorted(nums):
        toks = doc_tokens.get(n)
        if toks and _tokens_match(cit, toks):
            return n
    return None


def annotate_draft(
    draft: str,
    sources: Optional[list[dict]] = None,
    extra_patterns: Optional[list[str]] = None,
    num_documents: Optional[int] = None,
    documents: Optional[list] = None,
    omit_unbacked: bool = False,
) -> tuple[str, dict]:
    """Anota el borrador y produce el informe del especialista de verificación.

    Devuelve (borrador_anotado, informe). El informe es dict serializable (viaja en
    metadata del checkpoint y a la pantalla):
      {"citas": N, "marcadas": n, "respaldadas": n, "anotadas": n,
       "detalle": [{"cita", "estado", "fuente"?}...]}   estado ∈ marcada|respaldada|anotada
    `fuente` solo aparece en las respaldadas: {"tipo", "referencia", "titulo"} — la fuente
    compacta que dio el respaldo (Fase 1b: citas en línea). El respaldo puede venir de dos
    vías INDEPENDIENTES: el corpus curado del turno (`sources`) o el EXPEDIENTE por ancla
    (`documents`), esta última con la carga invertida (ver abajo).

    `documents` (opcional): los documentos del expediente vistos en el turno, en el mismo
    orden en que se sellaron <<<DOC n>>> (posición i → documento n=i+1). Habilita el
    respaldo por ANCLA: una cita solo queda respaldada por el expediente si lleva un ancla
    [doc n] cerca (antes o después) Y el contenido de ESE documento contiene su texto. Una
    cita SIN ancla NO se respalda por el expediente aunque el cotejo global la encontrara en
    otra pieza — queda al corpus o a [VERIFICAR]. Sin `documents` esta vía no corre y el
    respaldo depende solo del corpus (retrocompatible byte a byte).

    Si se pasa `num_documents` (documentos del expediente recuperados en el turno), corre
    ADEMÁS el guardián de referencias [doc n] fantasma y añade su informe bajo la clave
    "docs_fantasma". Sin ese parámetro el comportamiento es idéntico al de antes.

    Determinista y sin efectos: nunca borra texto, solo INSERTA " [VERIFICAR]" tras las
    citas sin marca ni respaldo (ni del corpus ni por ancla del expediente) y tras las
    referencias a documentos inexistentes cuando se conoce `num_documents`.

    `omit_unbacked` (F2 · jurisdicción desconocida): con True, la cita SIN respaldo no se
    marca — se REESCRIBE su span por `OMIT_MARK` antes de emitirse (la regla del prompt
    «aquí la cita no se marca, se omite» deja de ser una sugerencia al modelo y pasa a ser
    control determinista; medido en F1: el modelo la desobedece en el 40% de las corridas
    del caso de citas). Una cita marcada por el modelo también se omite si no tiene
    respaldo (marcarla no la autoriza); si lo tiene, se conserva. El texto original queda
    en el informe (estado "omitida") — el abogado ve QUÉ se omitió en el informe, no en el
    texto. Este módulo sigue agnóstico de jurisdicción: la DECISIÓN de activar el modo vive
    en el llamador (graph._verify_draft); aquí solo vive la mecánica. Con False (default)
    el comportamiento es idéntico byte a byte al de antes.
    """
    text = draft or ""
    citations = scan_citations(text, compile_patterns(extra_patterns))
    index = _tokenize_index(source_index(sources))
    doc_tokens = _document_tokens(documents)
    detalle: list[dict] = []
    marcadas = respaldadas = anotadas = omitidas = 0
    # ediciones (start, end, reemplazo); una inserción es (pos, pos, " [VERIFICAR]").
    # scan_citations garantiza spans disjuntos, así que aplicarlas de atrás hacia
    # adelante nunca desplaza offsets pendientes ni pisa otra edición.
    edits: list[tuple[int, int, str]] = []

    for c in citations:
        fuente = None
        anchor_n: Optional[int] = None
        if c["marked"] and not omit_unbacked:
            marcadas += 1
            estado = "marcada"
        elif (fuente := _backing_source_tokenized(c["citation"], index)) is not None:
            respaldadas += 1
            estado = "respaldada"
        elif (anchor_n := _anchored_doc_backing(
                c["citation"], c["start"], c["end"], text, doc_tokens)) is not None:
            # Respaldo por ANCLA al expediente: la cita lleva [doc n] cerca y el documento n
            # contiene su texto. Fuente sintética del expediente (no del corpus).
            respaldadas += 1
            estado = "respaldada"
            fuente = {"tipo": "expediente",
                      "referencia": f"[doc {anchor_n}]",
                      "titulo": _document_titulo(documents, anchor_n)}
        elif omit_unbacked:
            # Sin respaldo bajo jurisdicción desconocida: el span completo se sustituye.
            # (Si venía marcada, la marca [VERIFICAR] posterior puede quedar huérfana tras
            # el placeholder — redundante e inofensivo; jamás autoriza nada.)
            omitidas += 1
            estado = "omitida"
            edits.append((c["start"], c["end"], OMIT_MARK))
        else:
            anotadas += 1
            estado = "anotada"
            edits.append((c["end"], c["end"], " " + VERIFY_MARK))
        if len(detalle) < 50:
            entry: dict = {"cita": c["citation"], "estado": estado}
            if fuente is not None:
                # Solo los campos compactos y serializables (nada extra que traiga la fuente).
                entry["fuente"] = {
                    "tipo": str(fuente.get("tipo") or ""),
                    "referencia": str(fuente.get("referencia") or ""),
                    "titulo": str(fuente.get("titulo") or ""),
                }
            detalle.append(entry)

    # aplicar de atrás hacia adelante para no desplazar los offsets pendientes
    for start, end, repl in sorted(edits, key=lambda e: (e[0], e[1]), reverse=True):
        text = text[:start] + repl + text[end:]

    report = {
        "citas": len(citations),
        "marcadas": marcadas,
        "respaldadas": respaldadas,
        "anotadas": anotadas,
        "detalle": detalle,
    }
    if omit_unbacked:
        # La clave solo existe en el modo nuevo: el informe clásico queda idéntico.
        report["omitidas"] = omitidas
    # Guardián de referencias [doc n] fantasma DESPUÉS del escáner legal: así el
    # escáner de citas legales evalúa su ventana de marcado sobre el borrador crudo
    # (sin ver las marcas del guardián) y no hay diafonía entre ambos tipos de marca.
    if num_documents is not None:
        text, docs_fantasma = flag_phantom_doc_citations(text, num_documents)
        report["docs_fantasma"] = docs_fantasma
    return text, report
