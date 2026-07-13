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
# Ventana hacia adelante en la que una marca existente "cubre" la cita. Cubre el
# patrón usual del redactor: la marca va al lado o al final de la frase de la cita.
MARK_WINDOW_CHARS = 160

# Patrones BASE (léxico jurídico genérico en español — ver docstring). Cada pack de
# jurisdicción puede AÑADIR los suyos vía citation_style.json → "citation_patterns".
BASE_CITATION_PATTERNS: tuple[str, ...] = (
    # Normas con número: "Ley 1437 de 2011", "Decreto Ley 19 de 2012", "Resolución 123"
    r"\b(?:Ley|Decreto(?:\s+(?:Ley|Legislativo))?|Resoluci[oó]n|Acuerdo|Circular|Ordenanza)"
    r"\s+(?:No\.?\s*)?\d+[\w./-]*(?:\s+de\s+\d{4})?",
    # Providencias: "Sentencia C-355 de 2006", "Sentencia SU-230/15", "Sentencia 12345"
    r"\bSentencias?\s+(?:No\.?\s*)?[A-Z]{0,3}[-\s]?\d+[\w./-]*(?:\s+de\s+\d{4})?",
    # Autos con fecha: "Auto 123 de 2020"
    r"\bAutos?\s+(?:No\.?\s*)?\d+[\w./-]*\s+de\s+\d{4}",
    # Artículo CON su cuerpo normativo: "artículo 164 del CPACA", "artículos 21 de la Ley 640 de 2001",
    # "artículo 90 de la Constitución Política". El artículo suelto ("el artículo 5")
    # NO se marca: suele referirse a la norma ya citada en la misma frase.
    # OJO (revisión capa 2, M2): el separador de la lista de artículos es EXPLÍCITO
    # (", " o " y ") y el sufijo del número excluye dígitos — sin ambigüedad entre
    # cuantificadores anidados no hay backtracking exponencial (ReDoS) ante texto
    # adversarial (el escáner corre sobre borradores que citan documentos de terceros).
    r"\bart[ií]culos?\s+\d+[A-Za-z°º]*(?:(?:\s*,\s*|\s+y\s+)\d+[A-Za-z°º]*)*"
    r"\s+(?:de\s+la\s+|del?\s+)"
    r"(?:C[oó]digo\s+[\wáéíóúñÁÉÍÓÚÑ]+(?:\s+[\wáéíóúñÁÉÍÓÚÑ]+){0,4}"
    r"|Ley\s+\d+(?:\s+de\s+\d{4})?"
    r"|Decreto\s+\d+(?:\s+de\s+\d{4})?"
    r"|Constituci[oó]n(?:\s+Pol[ií]tica)?(?:\s+de\s+\d{4})?"
    r"|[A-ZÁÉÍÓÚÑ]{3,10}\b)",
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


def _normalize(text: str) -> str:
    """minúsculas · sin tildes · separadores colapsados a un espacio (para comparar)."""
    text = unicodedata.normalize("NFD", text or "")
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return re.sub(r"[\s.\-/]+", " ", text.lower()).strip()


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
    """La cita coincide con alguna fuente del corpus (match por inclusión normalizada,
    en ambos sentidos: 'Ley 1437 de 2011' ⊂ 'artículo 164 de la Ley 1437 de 2011')."""
    c = _normalize(citation)
    if not c:
        return False
    return any(k in c or c in k for k in keys if k)


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


def _backing_source(citation: str, index: list[tuple[str, dict]]) -> Optional[dict]:
    """La fuente del corpus que respalda la cita, o None (mismo match por inclusión
    normalizada de `_is_backed` — gana la primera coincidencia, que llega en el orden
    de relevancia con que investigó el turno)."""
    c = _normalize(citation)
    if not c:
        return None
    for k, s in index:
        if k and (k in c or c in k):
            return s
    return None


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


def annotate_draft(
    draft: str,
    sources: Optional[list[dict]] = None,
    extra_patterns: Optional[list[str]] = None,
    num_documents: Optional[int] = None,
) -> tuple[str, dict]:
    """Anota el borrador y produce el informe del especialista de verificación.

    Devuelve (borrador_anotado, informe). El informe es dict serializable (viaja en
    metadata del checkpoint y a la pantalla):
      {"citas": N, "marcadas": n, "respaldadas": n, "anotadas": n,
       "detalle": [{"cita", "estado", "fuente"?}...]}   estado ∈ marcada|respaldada|anotada
    `fuente` solo aparece en las respaldadas: {"tipo", "referencia", "titulo"} — la
    fuente compacta del corpus que dio el respaldo (Fase 1b: citas en línea).

    Si se pasa `num_documents` (documentos del expediente recuperados en el turno),
    corre ADEMÁS el guardián de referencias [doc n] fantasma y añade su informe bajo
    la clave "docs_fantasma". Sin ese parámetro el comportamiento es idéntico al de
    antes (retrocompatible: los llamadores que solo verifican citas legales no cambian).

    Determinista y sin efectos: nunca borra texto, solo INSERTA " [VERIFICAR]" tras
    las citas sin marca ni respaldo en el corpus (y tras las referencias a documentos
    inexistentes cuando se conoce `num_documents`).
    """
    text = draft or ""
    citations = scan_citations(text, compile_patterns(extra_patterns))
    index = source_index(sources)
    detalle: list[dict] = []
    marcadas = respaldadas = anotadas = 0
    inserts: list[int] = []  # posiciones (end) donde insertar la marca

    for c in citations:
        fuente = None
        if c["marked"]:
            marcadas += 1
            estado = "marcada"
        elif (fuente := _backing_source(c["citation"], index)) is not None:
            respaldadas += 1
            estado = "respaldada"
        else:
            anotadas += 1
            estado = "anotada"
            inserts.append(c["end"])
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

    # insertar de atrás hacia adelante para no desplazar los offsets pendientes
    for pos in sorted(inserts, reverse=True):
        text = text[:pos] + " " + VERIFY_MARK + text[pos:]

    report = {
        "citas": len(citations),
        "marcadas": marcadas,
        "respaldadas": respaldadas,
        "anotadas": anotadas,
        "detalle": detalle,
    }
    # Guardián de referencias [doc n] fantasma DESPUÉS del escáner legal: así el
    # escáner de citas legales evalúa su ventana de marcado sobre el borrador crudo
    # (sin ver las marcas del guardián) y no hay diafonía entre ambos tipos de marca.
    if num_documents is not None:
        text, docs_fantasma = flag_phantom_doc_citations(text, num_documents)
        report["docs_fantasma"] = docs_fantasma
    return text, report
