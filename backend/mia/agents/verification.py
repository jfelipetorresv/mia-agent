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
) -> tuple[str, dict]:
    """Anota el borrador y produce el informe del especialista de verificación.

    Devuelve (borrador_anotado, informe). El informe es dict serializable (viaja en
    metadata del checkpoint y a la pantalla):
      {"citas": N, "marcadas": n, "respaldadas": n, "anotadas": n,
       "detalle": [{"cita", "estado", "fuente"?}...]}   estado ∈ marcada|respaldada|anotada
    `fuente` solo aparece en las respaldadas: {"tipo", "referencia", "titulo"} — la
    fuente compacta del corpus que dio el respaldo (Fase 1b: citas en línea).

    Determinista y sin efectos: nunca borra texto, solo INSERTA " [VERIFICAR]" tras
    las citas sin marca ni respaldo en el corpus.
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
    return text, report
