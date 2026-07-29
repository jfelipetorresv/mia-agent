"""Mia · eval.scoring — señales OBJETIVAS de calidad de un turno (CP-E4).

Todo determinista, SIN LLM-juez (anti-invención por construcción, imprescindible en lo
legal): un LLM que puntúa a otro LLM introduce ruido y costo, y podría "premiar" un borrador
seguro-pero-vacío. Estas señales miden DISCIPLINA verificable, no exactitud sustantiva:

  · disciplina de citas (la más importante): del verificador determinista de CP9
    (`agents.verification`) — cuántas citas, cuántas SIN respaldo ni marca [VERIFICAR]
    (`anotadas`). Un borrador con citas sin respaldo es peor: obliga al abogado a rastrearlas.
  · estructura: ¿el diagnóstico trae el bloque de cierre problema/normas/riesgo
    (`prompt_builder.parse_diagnosis_closing`)? ¿el turno llegó a producir borrador?
  · forma: longitud del borrador (un borrador vacío o minúsculo es una señal de fallo).
  · INDICIOS de sustancia (`substance_signal`, INFORMATIVO — ver su docstring): ¿el borrador
    es prosa desarrollada o un esqueleto de títulos? ¿sus párrafos se apoyan en el expediente
    y en una norma concreta? NO mide si el argumento es bueno. No entra en `ok`.
  · costo/latencia: tokens y ms del turno (de la metadata del grafo).

`score_turn` es una función PURA sobre el resultado del turno: no toca DB, red ni reloj.
"""
from __future__ import annotations

import re
from typing import Any, Callable, Optional

from ..agent import prompt_builder
from ..agents import verification
# M1 · forma/léxico mudado a agents/verification.py (el informe por oración los necesita y
# scoring YA importa verification — moverlo al revés haría el ciclo scoring→verification→scoring).
# Se reimportan aquí (regla 6): mismo objeto, mismo valor, comportamiento byte a byte.
from ..agents.verification import (  # noqa: F401 — reexport de compatibilidad
    HEADER_MAX_CHARS,
    SUBSTANTIVE_PARAGRAPH_MIN_CHARS,
    _is_header,
)
from ..memory.tokens import estimate_tokens

# Umbral mínimo de caracteres para considerar que hubo un borrador "real" (por debajo es
# un fallo de redacción, no un borrador). Conservador: un borrador jurídico serio supera
# de sobra este piso; sirve para atrapar vacíos/errores, no para calificar extensión.
MIN_DRAFT_CHARS = 200

# Banderas de calidad (problemas objetivos detectados en el turno).
FLAG_NO_DRAFT = "sin_borrador"
FLAG_TINY_DRAFT = "borrador_minusculo"
FLAG_UNSUPPORTED_CITATIONS = "citas_sin_respaldo"
FLAG_NO_DIAGNOSIS_CLOSING = "sin_cierre_diagnostico"


# ── QUIÉN marcó: el MODELO obediente o el GUARDIÁN determinista ───────────────
# Son cosas distintas y el banco tiene que poder distinguirlas: que el guardián marque es una
# GARANTÍA (siempre ocurre); que el modelo se auto-marque es SUERTE (a veces ocurre). Un panel
# que las confunde le atribuye al modelo una disciplina que no tiene.
#
# El dato existe y es fiable POR UNA VÍA SOLA: el `verification_report` del grafo, calculado
# sobre el borrador ANTES de anotarlo (`agents/graph.py` → `md["verification"]`). Ahí
# `marcadas` = marcas que traía el modelo y `anotadas` = las que puso el guardián.
#
# HALLAZGO (Frente B): la vía de RESPALDO —re-escanear el borrador cuando no llega informe— NO
# es fiable, y falla en la dirección peligrosa. Para cuando el turno llega al HITL el borrador
# YA está anotado, así que un re-escaneo lee las marcas del GUARDIÁN como si fueran del modelo:
# medido en vivo sobre un borrador con 4 citas anotadas por el guardián, el re-escaneo reporta
# `marcadas=4, sin_respaldo=0` — es decir, convierte un turno indisciplinado en uno impecable y
# apaga `citas_sin_respaldo`, que es justo la señal que tumba `ok`.
#
# No se puede "arreglar" el re-escaneo (la información de quién marcó se destruye al anotar el
# texto: las dos marcas son el mismo literal). Lo que sí se puede es que el banco NUNCA presente
# una atribución no fiable como si lo fuera. Por eso la señal declara su ORIGEN:
ORIGEN_INFORME_GUARDIAN = "informe_guardian"   # atribución fiable
ORIGEN_REESCANEO = "reescaneo_borrador"        # atribución dudosa (ver abajo)

# Etiqueta con la que el panel nombra el aviso (`execution/run_eval.py` — frente C). Vive aquí
# para que el nombre no se escriba dos veces en dos archivos y se desincronice.
AVISO_ATRIBUCION_MARCAS = "atribucion_de_marcas_no_fiable"

# CUÁNDO exactamente el re-escaneo miente. No siempre: si el borrador re-escaneado no trae NI
# UNA marca, entonces `marcadas=0` y no hay nada que atribuir mal — el dato es trivialmente
# correcto (ese es el caso de las pruebas unitarias sobre borradores crudos). El re-escaneo solo
# es indistinguible cuando SÍ hay marcas, porque la marca del modelo y la del guardián son el
# MISMO literal `[VERIFICAR]` y el texto ya no recuerda quién la puso. Se afina así a propósito:
# un aviso que salta siempre se ignora siempre, y entonces no avisa de nada.


def _citation_signal(draft: str, sources: Any, extra_patterns: Any,
                     verification_report: Any = None) -> dict:
    """Disciplina de citas del borrador, vía el verificador determinista de CP9.

    Si el turno trae su `verification_report` (informe del grafo, calculado sobre el borrador
    ANTES de anotarlo), se usa TAL CUAL: es lo correcto, porque para cuando el turno llega al
    HITL el borrador YA fue anotado por el nodo de verificación (las citas sin marca recibieron
    su [VERIFICAR]) — re-escanear ese borrador anotado contaría 0 sin respaldo y borraría la
    señal. Sin informe (pruebas sobre un borrador crudo), se ESCANEA el borrador aquí.
    `anotadas` = citas sin marca [VERIFICAR] ni respaldo en el corpus = las riesgosas.

    `origen_marcas` dice por cuál de las dos vías salió el desglose modelo/guardián, y
    `atribucion_marcas_fiable` si ese desglose se puede leer (ver el bloque de arriba)."""
    if isinstance(verification_report, dict) and "citas" in verification_report:
        report = verification_report
        origen = ORIGEN_INFORME_GUARDIAN
    else:
        src = sources if isinstance(sources, list) else None
        extra = extra_patterns if isinstance(extra_patterns, list) else None
        _annotated, report = verification.annotate_draft(
            draft or "", sources=src, extra_patterns=extra)
        origen = ORIGEN_REESCANEO
    citas = int(report.get("citas", 0))
    anotadas = int(report.get("anotadas", 0))
    respaldadas = int(report.get("respaldadas", 0))
    marcadas = int(report.get("marcadas", 0))
    return {
        "citas": citas,
        "citas_sin_respaldo": anotadas,       # las riesgosas (ni marca ni respaldo)
        "citas_respaldadas": respaldadas,
        "citas_marcadas": marcadas,
        # fracción de citas "en regla" (marcadas o respaldadas) sobre el total; 1.0 sin citas.
        "citas_en_regla_ratio": round((citas - anotadas) / citas, 4) if citas else 1.0,
        # PROCEDENCIA DEL DATO (Frente B · B3): sin esto, `citas_marcadas` y `citas_sin_respaldo`
        # se leen igual vengan de donde vengan, y una de las dos vías miente.
        "origen_marcas": origen,
        "atribucion_marcas_fiable": origen == ORIGEN_INFORME_GUARDIAN or marcadas == 0,
    }


# ── Fuga de JURISDICCIÓN (riesgo capturado en vivo — INTERMITENTE) ────────────
# Cuando el despacho NO tiene ordenamiento configurado, `prompt_builder.JURISDICTION_UNKNOWN`
# le prohíbe al modelo citar articulado, ley, decreto, código o corporación de UN país
# concreto: debe razonar por INSTITUCIÓN jurídica y pedir el ordenamiento como siguiente paso
# (ver `execution/test_jurisdiction_agnostic.py::jurisdiccion_en_el_prompt`). El riesgo real
# capturado en vivo es que el modelo, pese a la instrucción, A VECES sí cita una norma
# concreta — y solo a veces: es INTERMITENTE, la peor clase de defecto (una corrida limpia
# no prueba que no vuelva a pasar; ver `harness.run_case_n` + `harness.jurisdiction_leak_rate`).
#
# La señal REUTILIZA el escáner del guardián de citas (`agents.verification.scan_citations` +
# `compile_patterns`) en vez de escribir vocabulario de país propio: la regla dura de
# agnosticismo de jurisdicción (CLAUDE.md) prohíbe literales de país/corte/base normativa en
# código común, y el escáner YA sabe reconocer la FORMA de una cita normativa concreta
# (Ley/Decreto/Resolución/Sentencia/artículo con su cuerpo normativo/Radicado) sin nombrar
# ningún país. No hace falta saber DE QUÉ país es la norma citada para saber que citarla, bajo
# jurisdicción desconocida, YA es la fuga: la forma de la cita es la señal, no su contenido.
# N-1 (decisión de Pipe 2026-07-27, `memory/decisions.md` #45) — MENCIÓN ≠ USO.
# La regla del muro es «no afirmar una norma como aplicable sin respaldo», NO «no escribir
# jamás el número de una norma». Nombrar una referencia PARA ADVERTIR que no se reconoce deja
# al abogado ADVERTIDO, no engañado, y es el mejor comportamiento posible cuando el número
# viene del propio expediente. Origen empírico: de 60 corridas (30 suscripción + 30 nube) la
# ÚNICA marca de fuga fue un falso positivo verificado — `f2nube_entail_i` escribió «La
# numeración "Ley 4137" no corresponde a ninguna ley del repertorio hispanoamericano que pueda
# verificarse en mi memoria» y el detector contó la aparición. Un falso positivo aquí hace
# REPROBAR al turno que se comportó mejor, y la fuga es métrica que decide (es el defecto que
# vino a cerrar F2), así que se corrige la MEDICIÓN, no el comportamiento.
#
# AGNOSTICISMO (regla dura de CLAUDE.md): cero léxico de país/corte/base normativa. Solo
# negación genérica del español — el mismo repertorio de forma que ya usa `ABSTENTION_PHRASES`.
# Se exige que la negación esté en la MISMA oración que la cita: una negación a tres párrafos
# de distancia no cubre nada y abriría la puerta a citar libre «desmintiendo» al final.
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
# Fin de oración: punto/;/:/salto de línea/viñeta. Deliberadamente estrecho — el punto de una
# abreviatura parte la oración de más, y partir de más es el lado SEGURO (deja la mención sin
# cobertura → sigue contando como fuga).
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


def _mencion_negada(text: str, start: int, end: int) -> bool:
    """¿La cita en [start, end) va acompañada de una negación explícita en SU MISMA oración?
    (N-1: mención ≠ uso). Pura y determinista."""
    oracion = verification._normalize(_oracion_de(text, start, end))
    return any(p in oracion for p in _NEGATION_NORM)


def jurisdiction_leak_signal(text: str, extra_patterns: Any = None) -> dict:
    """¿El texto USA articulado/norma/providencia CONCRETOS? (fuga bajo jurisdicción
    desconocida). Determinista y puro — mismo escáner que usa el guardián de citas (CP9),
    aplicado a cualquier texto que se le pase (normalmente diagnóstico + borrador del turno).
    NO decide de qué país es la norma citada — eso violaría el agnosticismo que se está
    protegiendo; solo decide si hay una cita concreta USADA, que es la fuga en sí misma.

    N-1: una cita MENCIONADA con negación explícita en su misma oración («la numeración X no
    corresponde a ninguna ley verificable») NO es fuga — es el comportamiento correcto. Se
    reporta aparte en `negadas`/`detalle_negadas`, nunca se esconde.

    Claves: `citas_detectadas` (total, semántica de siempre) · `negadas` · `citas_computadas`
    (las que sí cuentan como fuga) · `leak` (= `citas_computadas > 0`) · `v` (2 desde N-1;
    su ausencia identifica una señal PERSISTIDA con la regla vieja — ver
    `harness.jurisdiction_leak_rate`).
    """
    pats = verification.compile_patterns(
        extra_patterns if isinstance(extra_patterns, list) else None)
    t = text or ""
    citas = verification.scan_citations(t, pats)
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
    }


# ── INDICIOS de sustancia (estructurales, deterministas) ──────────────────────
# QUÉ MIDEN Y QUÉ NO (leer antes de creerle a estos números):
#
# Estas señales miden la FORMA del escrito, no la calidad del argumento. Un regex no sabe si
# un argumento es bueno, y nada de lo que hay aquí lo sabe. Lo único que distinguen es un
# ESQUELETO (títulos y frases sueltas, citas correctas, cero desarrollo — que hoy saca ok:True)
# de un escrito con prosa desarrollada apoyada en el expediente y en normas concretas. Eso es
# un INDICIO de sustancia, no una medida de sustancia. El nombre de cada clave lo dice así a
# propósito: `indicios_*`, `ratio`, `densidad` — nunca "solidez" ni "calidad".
#
# AGNOSTICISMO DE JURISDICCIÓN (regla dura): CERO léxico jurídico. Un título se detecta por su
# FORMA (línea corta sin puntuación terminal), no por decir "PRIMERO" ni "PETITORIO". El anclaje
# usa `[doc n]` (formato interno de Mia, igual en cualquier país) y la fundamentación reusa el
# escáner de citas que ya existe. El mismo escrito con normas españolas o colombianas da el
# mismo resultado estructural.
#
# GAMEABILIDAD (honestidad primero): cada señal por separado ES gameable — el modelo puede
# rellenar párrafos (infla `densidad_desarrollo`), salpicar `[doc 1]` (infla el anclaje) o
# repetir una norma en cada párrafo (infla la fundamentación). Lo que sube el costo de hacer
# trampa es la COMBINACIÓN con los gates que ya existen y que sí son duros: un `[doc n]`
# inventado lo caza el guardián de fantasmas y una cita sin respaldo dispara
# `citas_sin_respaldo` (que sí tumba `ok`). Para gamear las tres a la vez hay que escribir
# párrafos largos, anclados a documentos que existen, con normas que el corpus respalda — que
# es aproximadamente el trabajo que queríamos que hiciera. No es a prueba de balas: es una
# aproximación honesta y hay que leerla como tal.

# SUBSTANTIVE_PARAGRAPH_MIN_CHARS (180) y HEADER_MAX_CHARS (120) viven ahora en
# agents/verification.py (M1) y se reimportan arriba — su valor y su semántica quedan idénticos.

# Pisos de los INDICIOS. Solo alimentan `flags_informativos` (nunca `ok`), así que un falso
# positivo aquí no rompe a nadie; aun así son deliberadamente BAJOS: solo quieren atrapar el
# esqueleto descarado, no arbitrar entre dos escritos buenos.
DEVELOPMENT_DENSITY_FLOOR = 0.5   # <50% del borrador en prosa desarrollada → indicios de esqueleto
ANCHORING_RATIO_FLOOR = 0.34      # <1 de cada 3 párrafos toca el expediente
GROUNDING_RATIO_FLOOR = 0.34      # <1 de cada 3 párrafos trae una norma concreta

# Banderas INFORMATIVAS: describen indicios, NO problemas probados. Viven en
# `flags_informativos`, jamás en `flags` — ver `score_turn`.
INFO_FLAG_SKELETON = "indicios_de_esqueleto"
INFO_FLAG_LOW_ANCHORING = "poco_anclaje_al_expediente"
INFO_FLAG_LOW_GROUNDING = "poca_fundamentacion_normativa"
# F2 · residuo por oración: una tendencia de FORMA (afirmaciones sin cita/ancla/abstención).
# INFORMATIVA por diseño — SESGADA en ambas direcciones (M2/M3/M4), jamás toca `ok` (§4.6).
INFO_FLAG_SENTENCE_RESIDUE = "residuo_afirmativo_por_oracion"


def _split_blocks(draft: str) -> list[str]:
    """Bloques del borrador: por línea en blanco y, si no las hay, por salto simple.
    El fallback importa porque los modelos alternan ambos estilos y sin él un escrito entero
    contaría como UN párrafo (y todo esqueleto pasaría por desarrollado)."""
    blocks = [b.strip() for b in re.split(r"\n\s*\n", draft or "") if b.strip()]
    if len(blocks) <= 1:
        blocks = [b.strip() for b in (draft or "").split("\n") if b.strip()]
    return blocks


# `_is_header` vive ahora en agents/verification.py (M1) y se reimporta arriba (regla 6).


def substance_signal(draft: str, extra_patterns: Any = None) -> dict:
    """INDICIOS ESTRUCTURALES de sustancia de un borrador. Determinista y puro (sin LLM-juez).

    NO dice si el argumento es bueno, si es correcto, ni si convence. Dice si el texto tiene la
    FORMA de un escrito desarrollado en vez de la de un esqueleto:

      · `densidad_desarrollo` — fracción del borrador que vive en párrafos de prosa desarrollada
        (≥ SUBSTANTIVE_PARAGRAPH_MIN_CHARS) en vez de en títulos y frases sueltas. Es la señal
        que de verdad separa el esqueleto del escrito: un índice de títulos con citas correctas
        se desploma aquí, y hoy sacaría ok:True.
      · `anclaje_expediente_ratio` — de esos párrafos, cuántos citan un hecho del expediente
        (`[doc n]`). Se mide por COBERTURA (cuántos párrafos), no por conteo: 20 `[doc 1]` en un
        párrafo y nada en el resto NO es un escrito anclado, y un conteo diría que sí.
      · `fundamentacion_normativa_ratio` — cuántos traen una cita normativa CONCRETA (la que
        detecta el escáner de CP9: norma con número o artículo con su cuerpo normativo). Una
        apelación vaga ("las normas aplicables", "reiterada jurisprudencia") no la detecta el
        escáner y por eso no suma: es justo la diferencia entre traer la fuente y nombrarla.

    Ver el bloque de comentarios de arriba para qué NO mide y por dónde se gamea.
    """
    draft = draft or ""
    blocks = _split_blocks(draft)
    headers = [b for b in blocks if _is_header(b)]
    prose = [b for b in blocks if not _is_header(b)]
    substantive = [b for b in prose if len(b) >= SUBSTANTIVE_PARAGRAPH_MIN_CHARS]

    total_chars = len(draft)
    chars_sub = sum(len(b) for b in substantive)
    densidad = round(chars_sub / total_chars, 4) if total_chars else 0.0

    lens = sorted(len(b) for b in substantive)
    mediana = lens[len(lens) // 2] if lens else 0

    n = len(substantive)
    if n:
        pats = verification.compile_patterns(
            extra_patterns if isinstance(extra_patterns, list) else None)
        con_doc = sum(1 for b in substantive if verification._DOC_REF_RE.search(b))
        con_norma = sum(1 for b in substantive if verification.scan_citations(b, pats))
        anclaje = round(con_doc / n, 4)
        fundamentacion = round(con_norma / n, 4)
    else:
        con_doc = con_norma = 0
        anclaje = fundamentacion = 0.0

    return {
        "bloques": len(blocks),
        "titulos": len(headers),
        "parrafos_sustantivos": n,
        "mediana_parrafo_chars": mediana,
        "densidad_desarrollo": densidad,
        "parrafos_con_anclaje": con_doc,
        "anclaje_expediente_ratio": anclaje,
        "parrafos_con_norma": con_norma,
        "fundamentacion_normativa_ratio": fundamentacion,
    }


def _substance_info_flags(sig: dict) -> list[str]:
    """Banderas INFORMATIVAS de los indicios. Nunca entran en `ok` (ver `score_turn`)."""
    info: list[str] = []
    if sig["parrafos_sustantivos"] == 0 or sig["densidad_desarrollo"] < DEVELOPMENT_DENSITY_FLOOR:
        info.append(INFO_FLAG_SKELETON)
    # Sin párrafos desarrollados los ratios son 0/0: informar "poco anclaje" ahí sería ruido
    # sobre ruido (ya lo dijo `indicios_de_esqueleto`).
    if sig["parrafos_sustantivos"] > 0:
        if sig["anclaje_expediente_ratio"] < ANCHORING_RATIO_FLOOR:
            info.append(INFO_FLAG_LOW_ANCHORING)
        if sig["fundamentacion_normativa_ratio"] < GROUNDING_RATIO_FLOOR:
            info.append(INFO_FLAG_LOW_GROUNDING)
    return info


# ── DISCIPLINA por ORACIÓN (F2 · INFORMATIVA — jamás gate en esta iteración) ──
# Lee el bloque `oraciones` que el guardián por oración (agents/verification.build_sentence_report)
# añade al informe. Es una lente de FORMA sobre la disciplina de citas: cuántas oraciones traen
# una cita LOCALIZADA (no «verificada»), cuántas se omitieron, y el RESIDUO afirmativo.
#
# HONESTIDAD OBLIGATORIA (M2/M3/M4, §4.6): `oraciones_sin_respaldo_afirmativa` NO es «el número
# del hueco (1)». Es un proxy de forma sesgado en AMBAS direcciones (se infla con abstenciones
# honestas parafraseadas; se desinfla con retórica o frases cortas), ciego a la co-ubicación con
# citas y ciego al carve-out del abogado. Su promoción a gate está CONGELADA (§4.6): aquí solo
# alimenta `flags_informativos`, nunca `flags`/`ok`.
#
# `atribuye_sin_material` vive en ESTA capa (no en verification.py, que queda agnóstico): la
# procedencia por oración reutiliza `_PROVENANCE_PHRASES` + el contexto del turno
# (`documents_retrieved`), que solo el scoring conoce — misma señal de `provenance_signal`,
# aplicada oración a oración (verificación cruzada Codex, decisión de alcance M2a).
def sentence_discipline_signal(verification_report: Any = None,
                               documents_retrieved: Optional[int] = None) -> dict:
    """Señal INFORMATIVA por oración a partir de `report["oraciones"]`. Pura. Si el informe no
    trae el bloque (modo clásico, re-escaneo, corrida vieja) devuelve `{"disponible": False}` y
    nada cambia — retrocompatible.

    `documents_retrieved` (opcional): documentos del expediente recuperados en el turno. Con 0
    (o None → se asume sin material), una oración con frase de procedencia atribuye al despacho
    sin material sellado (`atribuye_sin_material`) — misma regla que `provenance_signal`."""
    rep = verification_report if isinstance(verification_report, dict) else {}
    o = rep.get("oraciones")
    if not isinstance(o, dict):
        return {"disponible": False}
    con_loc = int(o.get("con_cita_localizada", 0) or 0)
    residuo = int(o.get("sin_respaldo_afirmativa", 0) or 0)
    con_cita = int(o.get("con_cita", 0) or 0)
    # «afirmaciones» = oraciones que hacen una aseveración jurídica (con cita o residuo sin
    # cita). Ratio informativo e imperfecto (comparte las cegueras del residuo): NO es gate.
    afirmaciones = con_cita + residuo
    # PROCEDENCIA por oración (M2a) — SOLO informativa. Sin material sellado, cada oración cuyo
    # texto trae una frase de procedencia atribuye al despacho lo que este turno no selló.
    sin_material = int(documents_retrieved or 0) <= 0
    idx_atribuye: list[int] = []
    if sin_material:
        for d in (o.get("detalle") or []):
            texto_norm = verification._normalize(str(d.get("texto") or ""))
            if any(verification._normalize(p) in texto_norm for p in _PROVENANCE_PHRASES):
                idx_atribuye.append(int(d.get("idx", -1)))
    return {
        "disponible": True,
        "oraciones": int(o.get("n", 0) or 0),
        "oraciones_con_cita_localizada": con_loc,
        "oraciones_con_omision": int(o.get("con_omision", 0) or 0),
        "oraciones_sin_respaldo_afirmativa": residuo,
        "ratio_afirmaciones_ancladas": (round(con_loc / afirmaciones, 4)
                                        if afirmaciones else 1.0),
        # LÍMITE DECLARADO: se calcula sobre `detalle` (capado a 80 oraciones y con el texto
        # truncado); es una cota inferior informativa de la atribución sin material, no exacta.
        "oraciones_atribuye_sin_material": len(idx_atribuye),
        "idx_atribuye_sin_material": idx_atribuye[:20],
    }


def _sentence_info_flags(disciplina: dict) -> list[str]:
    """Bandera INFORMATIVA del residuo por oración. Nunca entra en `ok` (ver `score_turn`)."""
    if disciplina.get("disponible") and disciplina.get("oraciones_sin_respaldo_afirmativa", 0) > 0:
        return [INFO_FLAG_SENTENCE_RESIDUE]
    return []


def score_turn(
    draft: str,
    diagnosis: str,
    metadata: dict | None = None,
    *,
    sources: Any = None,
    extra_patterns: Any = None,
    verification_report: Any = None,
) -> dict:
    """Señales objetivas de calidad de un turno. Pura y determinista.

    `draft` = borrador final del turno; `diagnosis` = diagnóstico (para el bloque de cierre);
    `metadata` = metadata del grafo (tokens/latencia/etapas); `sources` = fuentes recuperadas
    del corpus en el turno (para el respaldo de citas — las mismas que usó el grafo);
    `verification_report` = informe del verificador del grafo (preferido; ver `_citation_signal`).
    """
    md = metadata or {}
    draft = draft or ""
    draft_chars = len(draft)
    reached_draft = draft_chars > 0
    tiny_draft = 0 < draft_chars < MIN_DRAFT_CHARS

    cites = _citation_signal(draft, sources, extra_patterns, verification_report)
    has_closing = prompt_builder.parse_diagnosis_closing(diagnosis or "") is not None

    # INDICIOS de sustancia. Solo tienen sentido sobre un borrador real: sobre uno vacío o
    # minúsculo el fallo YA lo dicen `sin_borrador`/`borrador_minusculo`, y añadir tres
    # banderas más sería ruido duplicado sobre el mismo hecho.
    substance = substance_signal(draft, extra_patterns)
    info_flags = _substance_info_flags(substance) if (reached_draft and not tiny_draft) else []
    # DISCIPLINA por oración (F2 · INFORMATIVA). Solo aporta si el informe trae el bloque
    # `oraciones`; su bandera va a `flags_informativos`, JAMÁS a `flags`/`ok` (§4.6, regla 47).
    # `retrieved` (documentos del expediente recuperados en el turno) habilita la procedencia
    # por oración (M2a); ausente → None (se asume sin material, dirección conservadora).
    disciplina_oraciones = sentence_discipline_signal(
        verification_report, documents_retrieved=md.get("retrieved"))
    info_flags = info_flags + _sentence_info_flags(disciplina_oraciones)
    # NOTA (B3): el aviso de atribución NO se cuela en `flags_informativos`. Esa lista tiene un
    # contrato propio —son los INDICIOS DE SUSTANCIA— y varias suites afirman sobre ella; meter
    # ahí una señal de otra naturaleza volvería rojas pruebas que nada tienen que ver. El dato
    # viaja en sus dos claves explícitas (`origen_marcas`, `atribucion_marcas_fiable`), que
    # `**cites` ya propaga al resultado, y el panel las lee con la etiqueta
    # `AVISO_ATRIBUCION_MARCAS`.

    flags: list[str] = []
    if not reached_draft:
        flags.append(FLAG_NO_DRAFT)
    elif tiny_draft:
        flags.append(FLAG_TINY_DRAFT)
    if cites["citas_sin_respaldo"] > 0:
        flags.append(FLAG_UNSUPPORTED_CITATIONS)
    if not has_closing:
        flags.append(FLAG_NO_DIAGNOSIS_CLOSING)

    usage = md.get("usage") if isinstance(md.get("usage"), dict) else {}
    return {
        # forma / completitud
        "reached_draft": reached_draft,
        "draft_chars": draft_chars,
        "draft_tokens": estimate_tokens(draft),
        "has_diagnosis_closing": has_closing,
        "stage": str(md.get("stage") or ""),
        # disciplina de citas (lo central)
        **cites,
        # INDICIOS de sustancia (estructurales — NO miden si el argumento es bueno).
        "sustancia": substance,
        # DISCIPLINA por oración (F2 · INFORMATIVA, nunca gate — ver `sentence_discipline_signal`).
        "disciplina_oraciones": disciplina_oraciones,
        # costo / latencia (informativo, no penaliza calidad por sí solo)
        "total_tokens": int(usage.get("total", 0) or 0),
        "latency_ms": round(float(md.get("latency_ms", 0.0) or 0.0), 1),
        # resumen de problemas objetivos detectados
        "flags": flags,
        # TRANSICIÓN (deliberada): los indicios de sustancia son INFORMATIVOS, no bloqueantes.
        # Van en su propia lista y NO entran en `ok`. Motivo: `flags`/`ok` es el contrato vigente
        # del gate y de los casos de oro YA CONFIRMADOS por el despacho fundador; meter aquí una
        # rúbrica nueva volvería rojos de golpe borradores que el abogado ya aprobó, y un examen
        # que se pone rojo sin que nada haya empeorado deja de creerse (y entonces no sirve para
        # nada). Primero se observa la señal contra los casos reales, se calibran los pisos con
        # datos, y solo después se decide si alguna merece bloquear. Mientras tanto: `flags` sigue
        # midiendo lo probado; `flags_informativos` señala dónde mirar.
        "flags_informativos": info_flags,
        "ok": len(flags) == 0,
    }


# ── Calificación SUSTANTIVA (Banco de oro, Fase 1) ────────────────────────────
# score_turn (arriba) mide DISCIPLINA y es PURO. substantive_score mide si la respuesta nueva
# CUBRE las claves que el abogado confirmó (rúbrica). El DETERMINISTA manda pasa/no-pasa; el
# juez LLM es solo ADVISORY (callback opcional, efecto de red fuera de la ruta pura).

FLAG_MISSING_KEY_CITATION = "falta_cita_clave"
FLAG_MISSING_KEY_CONCLUSION = "falta_conclusion_clave"

# Fracción de palabras significativas de una conclusión clave que deben aparecer para darla por
# cubierta (match por conjunto de términos, no exacto: tolera reformulaciones del modelo).
CONCLUSION_KEYWORD_THRESHOLD = 0.7

# Palabras vacías (no aportan a la cobertura de una conclusión): conectores/artículos comunes.
_STOPWORDS = frozenset((
    "de", "la", "el", "los", "las", "un", "una", "unos", "unas", "y", "o", "u", "e", "en",
    "con", "sin", "por", "para", "del", "al", "se", "su", "sus", "que", "como", "es", "son",
    "lo", "le", "les", "ha", "han", "no", "si", "mas", "pero", "the", "a", "ante", "sobre",
))


def _normalize_cita(text: str) -> str:
    """Normaliza una cita para comparar (minúsculas, sin tildes, sin puntuación) y unifica la
    abreviatura 'art.' con 'artículo' — así 'art. 90' casa con 'artículo 90'."""
    s = verification._normalize(text)          # minúsculas · sin tildes · separadores colapsados
    return re.sub(r"\bart\b", "articulo", s)


def _cita_cubierta(cita_clave: str, halladas_norm: list[str]) -> bool:
    """La cita clave está cubierta si casa (inclusión normalizada, en ambos sentidos) con alguna
    de las citas que el escáner detectó en la respuesta nueva."""
    kn = _normalize_cita(cita_clave)
    if not kn:
        return False
    return any(kn in hn or hn in kn for hn in halladas_norm if hn)


def _keywords(text: str) -> list[str]:
    """Palabras significativas de una conclusión (normalizadas, sin stopwords ni de ≤2 letras)."""
    toks = _normalize_cita(text).split()
    return [t for t in toks if len(t) > 2 and t not in _STOPWORDS]


def _conclusion_cubierta(conclusion_clave: str, texto_norm: str) -> bool:
    """La conclusión clave está cubierta si ≥ umbral de sus palabras significativas aparecen en
    la respuesta nueva (diagnóstico + borrador). Conjunto de términos, no coincidencia literal."""
    kws = _keywords(conclusion_clave)
    if not kws:
        return False
    presentes = sum(1 for w in set(kws) if w in texto_norm)
    return (presentes / len(set(kws))) >= CONCLUSION_KEYWORD_THRESHOLD


def substantive_score(
    draft: str,
    diagnosis: str,
    rubric: Optional[dict],
    *,
    judge: Optional[Callable[[str, str, dict], dict]] = None,
) -> dict:
    """Calificación SUSTANTIVA de una respuesta nueva contra la rúbrica confirmada.

    (a) DETERMINISTA — AUTORITATIVO: cobertura de `citas_clave` (match robusto vía scan_citations)
        y de `conclusiones_clave` (umbral de keywords). `ok = len(flags) == 0`.
    (b) JUEZ LLM — ADVISORY (opcional): `judge(draft, diagnosis, rubric)` debe devolver
        {"veredicto": "solido|debilitado", "explicacion_llana": str}. NUNCA bloquea solo: solo
        adjunta señal. Se pasa como CALLBACK (efecto de red) para mantener esta función pura por
        defecto (judge=None → sin red, determinista, testeable). El juez ve SOLO texto anonimizado.
    """
    rubric = rubric or {}
    citas_clave = [str(c) for c in (rubric.get("citas_clave") or []) if str(c).strip()]
    conclusiones_clave = [str(c) for c in (rubric.get("conclusiones_clave") or []) if str(c).strip()]

    # (a) Determinista.
    halladas = verification.scan_citations(draft or "")
    halladas_norm = [_normalize_cita(h["citation"]) for h in halladas]
    citas_cubiertas = [c for c in citas_clave if _cita_cubierta(c, halladas_norm)]
    citas_faltantes = [c for c in citas_clave if c not in citas_cubiertas]

    texto_norm = _normalize_cita((diagnosis or "") + " \n " + (draft or ""))
    concl_cubiertas = [c for c in conclusiones_clave if _conclusion_cubierta(c, texto_norm)]
    concl_faltantes = [c for c in conclusiones_clave if c not in concl_cubiertas]

    flags: list[str] = []
    if citas_faltantes:
        flags.append(FLAG_MISSING_KEY_CITATION)
    if concl_faltantes:
        flags.append(FLAG_MISSING_KEY_CONCLUSION)

    result = {
        "cobertura_citas": round(len(citas_cubiertas) / len(citas_clave), 4) if citas_clave else 1.0,
        "cobertura_conclusiones": (round(len(concl_cubiertas) / len(conclusiones_clave), 4)
                                   if conclusiones_clave else 1.0),
        "citas_cubiertas": citas_cubiertas,
        "citas_faltantes": citas_faltantes,
        "conclusiones_cubiertas": concl_cubiertas,
        "conclusiones_faltantes": concl_faltantes,
        "faltantes": citas_faltantes + concl_faltantes,
        "n_faltantes_clave": len(citas_faltantes) + len(concl_faltantes),
        "flags": flags,
        "ok": len(flags) == 0,
        "judge": None,
        "judge_flags": [],
    }

    # (b) Juez advisory — nunca bloquea; cualquier fallo de red NO tumba la calificación dura.
    if judge is not None:
        try:
            veredicto = judge(draft or "", diagnosis or "", rubric)
            if isinstance(veredicto, dict):
                result["judge"] = {
                    "veredicto": str(veredicto.get("veredicto") or ""),
                    "explicacion_llana": str(veredicto.get("explicacion_llana") or ""),
                }
                if result["judge"]["veredicto"] == "debilitado":
                    result["judge_flags"] = ["juez_señala_debilitado"]
        except Exception:  # noqa: BLE001 — el juez es advisory: su fallo no altera pasa/no-pasa
            result["judge"] = {"veredicto": "", "explicacion_llana": "El juez no pudo opinar."}

    return result


# ── RECUPERACIÓN de fragmentos ENTERRADOS (expediente grande · N-2) ───────────
# Qué prueba y qué NO. Prueba UNA cosa, verificable sin juez: que el turno llegó a leer un
# fragmento que estaba sellado lejos del inicio de un expediente voluminoso, porque el dato
# reaparece literalmente en la respuesta. NO dice que el análisis sea correcto, ni que el dato
# se haya usado bien: eso es criterio jurídico y aquí no se mide. Por eso vive aparte de
# `substantive_score` y NUNCA se agrega con él (ver `cases.GoldenCase.recall_markers`).
#
# El match es por inclusión NORMALIZADA (minúsculas, sin tildes, separadores colapsados), la
# misma normalización que usa la cobertura de citas: así "otrosí 3" casa con "Otrosi 3" y con
# "otrosi  3". No hay umbral difuso ni keywords parciales — un marcador aparece o no aparece.
FLAG_MISSING_BURIED_FACT = "no_leyo_fragmento_enterrado"


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


# ── PROCEDENCIA: no atribuir al despacho lo que no llegó sellado ──────────────
# Con el despacho VACÍO (cero documentos recuperados en el turno) no hay nada que el turno
# haya "manejado antes" en el sentido de expediente o conocimiento propio: cualquier frase
# que atribuya al despacho o al expediente una experiencia o un antecedente concreto es, en
# ese escenario, memoria paramétrica disfrazada de material del despacho — la MISMA clase de
# defecto que `prompt_builder.PROVENANCE_POLICY` le prohíbe al modelo ("no presentes tu
# propia memoria como material del despacho").
#
# Las frases son léxico GENÉRICO de procedencia en español (ningún país, ninguna corporación,
# ninguna sigla de código) — no es vocabulario jurídico de jurisdicción, así que no repite la
# regla dura de agnosticismo (esa protege literales de PAÍS, no la palabra "despacho").
_PROVENANCE_PHRASES: tuple[str, ...] = (
    "el despacho ha manejado", "el despacho ya ha tratado", "la practica del despacho",
    "conforme a la experiencia del despacho", "segun nuestro expediente",
    "el expediente registra", "consta en el expediente", "el despacho cuenta con",
    "conocimiento consolidado del despacho", "como el despacho ha sostenido",
    "segun el criterio consolidado del despacho", "el despacho suele",
    "en casos anteriores del despacho", "segun nuestros antecedentes",
)

FLAG_UNGROUNDED_PROVENANCE = "atribucion_indebida_al_despacho"


def provenance_signal(draft: str, diagnosis: str, documents_retrieved: int) -> dict:
    """¿La respuesta atribuye al despacho/expediente algo que ESTE turno no selló?

    `documents_retrieved` = documentos del expediente recuperados en el turno (la misma
    cuenta que guarda `harness.run_case` bajo esa clave). Con el despacho VACÍO (0), una
    frase de procedencia genérica (`_PROVENANCE_PHRASES`) es sospechosa: no hay material
    sellado del que esa experiencia pueda salir. Con documentos SÍ recuperados, las mismas
    frases son legítimas (el despacho sí trajo algo) y no se marcan — la señal no penaliza
    decir "consta en el expediente" cuando de verdad consta.

    Determinista y puro. NO decide si la atribución es jurídicamente correcta: solo si HAY
    base sellada para hacerla en este turno.
    """
    texto = verification._normalize((diagnosis or "") + " \n " + (draft or ""))
    hallazgos = [p for p in _PROVENANCE_PHRASES if verification._normalize(p) in texto]
    sin_material = int(documents_retrieved or 0) <= 0
    indebida = sin_material and bool(hallazgos)
    return {
        "sin_material_sellado": sin_material,
        "frases_detectadas": hallazgos,
        "atribucion_indebida": indebida,
        "flags": [FLAG_UNGROUNDED_PROVENANCE] if indebida else [],
    }
