"""Mia · security.anonymize — anonimización de asuntos reales para el Banco de oro (Fase 1).

Lo CRÍTICO por confidencialidad: antes de guardar un asunto REAL como caso de oro, se le quita
TODO dato identificable. A diferencia de `security/redact.py` (que enmascara CREDENCIALES en
logs, siempre activo e irreversible), aquí el objetivo es distinto: sustituir PII de personas y
del expediente por marcadores CONSISTENTES y TIPADOS (`CEDULA_1`, `PERSONA_1`…) que preservan el
sentido jurídico (misma entidad → mismo marcador) para que el caso siga siendo un examen útil.

Dos pasadas + dos redes de verificación:

  · Pasada 1 — REGEX determinista (estructurados, alta precisión): cédula, NIT, radicado de 23
    dígitos (CSJ), email, teléfono (+57/celular), cuentas, URLs. Sin red, sin costo, idempotente.
  · Pasada 2 — NER LOCAL para nombres/entidades (personas, empresas, direcciones): vía `call_llm`
    con el modelo LOCAL (`mia-local`, Ollama), temp 0. DEBE correr LOCAL — opera sobre texto AÚN
    identificable; mandarlo a un modelo en nube sería la fuga que esto previene. Si el modelo
    local NO está → se DEGRADA limpio: solo estructurados + aviso claro de que faltó el NER, para
    que la revisión humana cargue el peso de los nombres. Fechas: se CONSERVAN por defecto
    (relevantes para caducidad/prescripción).
  · Pasada 3 — REIDENTIFICACIÓN: cierra la grieta del número PELADO — una corrida de dígitos sin
    separadores que normaliza a un valor YA enmascarado en la sesión recibe el MISMO marcador (una
    "cuantía" no revive la cédula).
  · Verificación: re-escanea el texto YA anonimizado con TODOS los patrones estructurados y AÑADE
    una heurística de SOSPECHA (nombres/empresas/direcciones/IDs que el NER pudo omitir), que
    devuelve como spans `sospecha_*` en `spans_pii_restantes[]`. `contains_pii(text)` es la puerta
    reutilizable. OJO: `spans_pii_restantes` vacío = "nada que YO detecte", NO "garantizado limpio".

RIESGO RESIDUAL (honesto): ninguna anonimización automática es perfecta — apodos, hechos únicos
que reidentifican por contexto, OCR sucio, nombres que el NER local no vea. La REVISIÓN HUMANA es
la única red real: `status='confirmed'` solo lo pone el abogado tras revisar los spans resaltados.

El `anon_map` (marcador→valor real) se devuelve para uso EN SESIÓN (la pantalla de revisión); NO
se persiste en claro NUNCA — a la DB solo va su HASH (`anon_map_hash`), para auditar que la
anonimización fue reproducible sin poder reidentificar desde la base.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

logger = logging.getLogger("mia.security.anonymize")

# Marcador tipado y consistente. Forma `[[TIPO_N]]`: deliberadamente NO coincide con ningún
# patrón de PII (no trae puntos, arrobas ni corridas largas de dígitos), así el segundo pase de
# verificación no lo vuelve a marcar y la anonimización es IDEMPOTENTE (re-correr no cambia nada).
_MARKER_RE = re.compile(r"\[\[[A-ZÁÉÍÓÚÑ]+_\d+\]\]")


def _marker(tipo: str, n: int) -> str:
    return f"[[{tipo}_{n}]]"


# ── Pasada 1 · patrones de estructurados (orden IMPORTA: lo más específico primero) ───────────
# Cada entrada: (TIPO, patrón). Se aplican EN ORDEN; cada match se reemplaza por su marcador, así
# un patrón posterior nunca ve los dígitos que ya consumió uno anterior (p. ej. el radicado de 23
# dígitos se retira antes de que el patrón de teléfono pueda morder un tramo de 10).
_STRUCTURED_PATTERNS: tuple[tuple[str, re.Pattern], ...] = (
    # URL (http/https/www) — antes que email/números para no partir el host.
    ("URL", re.compile(r"\bhttps?://[^\s<>\"')]+|\bwww\.[^\s<>\"')]+", re.IGNORECASE)),
    # Email.
    ("EMAIL", re.compile(r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b")),
    # Radicado CSJ de 23 dígitos (con o sin separadores). Muy específico → primero entre números.
    ("RADICADO", re.compile(r"\b\d(?:[\s.\-]?\d){22}\b")),
    # NIT: por palabra clave, o formato 900.123.456-7.
    ("NIT", re.compile(
        r"\bNIT\.?\s*:?\s*\d[\d.\-]{6,}\d\b"
        r"|\b\d{3}\.\d{3}\.\d{3}\-\d\b", re.IGNORECASE)),
    # Cédula: por palabra clave (C.C. / cédula), o número con separador de miles (79.123.456).
    # El número "pelado" de 8-10 dígitos NO se toma aquí a propósito: es demasiado ambiguo
    # (se confunde con teléfonos/cuantías) — riesgo residual que cubre la revisión humana.
    ("CEDULA", re.compile(
        r"\b(?:c\.?\s?c\.?|c[eé]dula|documento\s+de\s+identidad|identificaci[oó]n)\s*"
        r"(?:n[o°º]\.?\s*)?:?\s*\d[\d.\-]{5,}\d\b"
        r"|\b\d{1,3}(?:\.\d{3}){2,3}\b", re.IGNORECASE)),
    # Cuenta bancaria (por palabra clave, para no morder cualquier número).
    ("CUENTA", re.compile(
        r"\b(?:cuenta|cta)\.?\s*(?:de\s+ahorros|corriente|no\.?|n[°º]\.?)?\s*:?\s*\d[\d\-]{6,}\d\b",
        re.IGNORECASE)),
    # Teléfono colombiano: celular = 10 dígitos que empiezan en 3, con o sin indicativo +57 y
    # con CUALQUIER separación —espacios, puntos, guiones o paréntesis— o pegado (p. ej.
    # `(315)5551234`, `+57 300 555 12 34`, `310 555 1234`); o fijo con indicativo +57. Normaliza
    # de facto tolerando separadores arbitrarios entre dígitos. Va DESPUÉS de radicado/NIT/cédula/
    # cuenta (todos más específicos) para no morderles dígitos y evitar mascar cuantías legítimas.
    ("TELEFONO", re.compile(
        r"(?<!\d)(?:\+?57[\s.\-]?)?\(?3\d{2}\)?(?:[\s.\-]?\d){7}(?!\d)"
        r"|(?<!\d)\+57[\s.\-]?\d{7,10}(?!\d)")),
)

# ── Heurística de SOSPECHA (FIX 3+4) · candidatos que el NER local pudo OMITIR ─────────────────
# NO oculta nada: solo MARCA para que la revisión humana (Fase 2) resalte. Tipos distintos de la
# PII confirmada (`sospecha_*`), para no dar falsa sensación de "todo limpio".
_CAP_WORD = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"

# Palabras Capitalizadas genéricas del lenguaje jurídico: si TODA la secuencia cae aquí, no es un
# nombre propio (evita falsos positivos tipo "Constitución Política", "Corte Suprema").
_STOP_CAP = {
    "constitución", "política", "ley", "corte", "suprema", "justicia", "consejo", "estado",
    "república", "código", "civil", "penal", "comercial", "laboral", "sala", "tribunal",
    "superior", "juzgado", "ministerio", "nación", "procuraduría", "fiscalía", "contraloría",
    "general", "nacional", "departamento", "municipio", "distrito", "sentencia", "auto",
    "decreto", "resolución", "artículo", "capítulo", "título", "libro", "colombia", "bogotá",
    "administrativo", "contencioso", "procedimiento", "comercio", "sustantivo", "trabajo",
    "única", "único", "unificada",
}

# Nombre propio probable: 2+ palabras Capitalizadas consecutivas (`Pérez Gómez`). Excluye tokens
# de marcador (`[[PERSONA_1]]`, en MAYÚSCULAS sin minúsculas → no casa con _CAP_WORD).
_NOMBRE_RE = re.compile(rf"\b{_CAP_WORD}(?:\s+{_CAP_WORD}){{1,4}}\b")

# Razón social por sufijo societario (`... S.A.S.`, `... Ltda`, `... & Asociados`) o por vocablo
# institucional inicial (`Fundación X`, `Corporación Y`).
_SUFIJO_SOC_RE = re.compile(
    rf"{_CAP_WORD}(?:\s+(?:{_CAP_WORD}|&|y|de|del|la|los|las))*\s+"
    r"(?:S\.?A\.?S\.?|S\.?A\.?|Ltda\.?|S\.?\s?en\s?C\.?|&\s?Asociados)")
_INSTITUC_RE = re.compile(
    rf"\b(?:Fundación|Corporación|Asociación|Cooperativa)\s+{_CAP_WORD}(?:\s+{_CAP_WORD})*")

# Dirección física (`Calle 100 No. 15-20`, `Carrera 7 # 12-34`, ...).
_DIRECCION_RE = re.compile(
    r"\b(?:Calle|Cll|Carrera|Cra|Kra|Kr|Avenida|Av|Autopista|Transversal|Diagonal|Circular)\.?\s*"
    r"\d{1,3}[A-Za-z]?\s*"
    r"(?:#|No\.?|N[°º]\.?|Nro\.?)?\s*"
    r"\d{1,3}[A-Za-z]?(?:\s*-\s*\d{1,3}[A-Za-z]?)?",
    re.IGNORECASE)

# IDs "pelados" sospechosos (OCR sucio): cédula de 10 díg. o radicado de 21-23 díg. SIN separadores
# que NO quedaron mapeados. Se reportan como sospecha (no se enmascaran sin match exacto).
_ID_PELADO_RE = re.compile(r"(?<!\d)(?:\d{10}|\d{21,23})(?!\d)")


@dataclass
class AnonSession:
    """Diccionario de sesión que da consistencia a los marcadores ENTRE varios textos (la
    pregunta, cada documento y el borrador de un mismo asunto comparten una sola sesión, así una
    misma persona/cédula recibe el MISMO marcador en todos). No se persiste en claro."""

    map: dict[str, str] = field(default_factory=dict)          # marcador → valor real
    _reverse: dict[tuple[str, str], str] = field(default_factory=dict)  # (tipo, valor_norm) → marcador
    _counters: dict[str, int] = field(default_factory=dict)

    @staticmethod
    def _norm(value: str) -> str:
        """Clave de identidad: minúsculas sin separadores, para que '79.123.456' y '79123456'
        (o 'Juan  Pérez' y 'juan pérez') mapeen al mismo marcador."""
        return re.sub(r"[\s.\-]+", "", str(value or "").strip().lower())

    def marker_for(self, tipo: str, value: str) -> str:
        key = (tipo, self._norm(value))
        marker = self._reverse.get(key)
        if marker is None:
            self._counters[tipo] = self._counters.get(tipo, 0) + 1
            marker = _marker(tipo, self._counters[tipo])
            self._reverse[key] = marker
            self.map[marker] = str(value)
        return marker


@dataclass
class AnonResult:
    """Resultado de anonimizar un texto. `anon_map` es SOLO para la sesión/pantalla; a la DB va
    únicamente su hash (`anon_map_hash`).

    `spans_pii_restantes` mezcla PII CONFIRMADA que sobrevivió (tipos estructurados) con SOSPECHAS
    (`sospecha_nombre` / `sospecha_direccion` / `sospecha_id`) de lo que el NER pudo omitir. Una
    lista vacía significa "nada que YO detecte", NO "garantizado limpio": la revisión humana es la
    única red real."""

    text: str
    anon_map: dict[str, str]
    spans_pii_restantes: list[dict]
    ner_ran: bool
    warnings: list[str] = field(default_factory=list)


# ── Pasada 1 · estructurados ──────────────────────────────────────────────────────────────────
def _apply_structured(text: str, session: AnonSession) -> str:
    out = text or ""
    for tipo, pat in _STRUCTURED_PATTERNS:
        def _repl(m: re.Match, _tipo=tipo) -> str:
            return session.marker_for(_tipo, m.group(0))
        out = pat.sub(_repl, out)
    return out


# ── Pasada 2 · NER local (nombres/empresas/direcciones) ───────────────────────────────────────
_NER_SYSTEM = (
    "Eres un extractor de entidades para anonimizar un texto jurídico colombiano. Devuelve "
    "EXCLUSIVAMENTE un objeto JSON con tres listas de cadenas EXACTAS tal como aparecen en el "
    "texto, sin explicaciones: {\"personas\": [...], \"empresas\": [...], \"direcciones\": [...]}. "
    "personas = nombres de personas naturales. empresas = razones sociales de personas jurídicas. "
    "direcciones = direcciones físicas (calles, carreras, etc.). NO incluyas normas, artículos, "
    "sentencias, entidades públicas genéricas ni fechas. Si no hay de un tipo, usa lista vacía."
)
_NER_TIPO = {"personas": "PERSONA", "empresas": "EMPRESA", "direcciones": "DIRECCION"}


def _parse_ner_json(content: str) -> Optional[dict]:
    """Extrae el objeto JSON de la respuesta del modelo. None si no hay JSON legible."""
    if not content:
        return None
    m = re.search(r"\{.*\}", content, re.DOTALL)
    if not m:
        return None
    try:
        data = json.loads(m.group(0))
        return data if isinstance(data, dict) else None
    except (ValueError, TypeError):
        return None


def _run_ner(text: str, llm: Optional[Callable]) -> Optional[list[tuple[str, str]]]:
    """Llama al modelo LOCAL para extraer entidades. Devuelve [(TIPO, valor)] o None si el NER
    no pudo correr (Ollama ausente, error de red, respuesta ilegible) → el llamador DEGRADA.

    NUNCA usa un modelo en nube: `model='mia-local'` fuerza la cadena de un solo alias local
    (resolve_fallback_chain); el texto de entrada AÚN es identificable."""
    if not (text or "").strip():
        return []
    call = llm
    if call is None:
        try:
            from ..agent.llm import call_llm as call  # import diferido (evita ciclos en el import)
        except Exception:  # noqa: BLE001 — sin gateway disponible → degradar
            logger.exception("anonymize: no se pudo importar call_llm; se degrada a solo estructurados")
            return None
    try:
        resp = call(
            [{"role": "system", "content": _NER_SYSTEM},
             {"role": "user", "content": text}],
            task="anonymize_ner", model="mia-local", temperature=0,
        )
        content = resp.choices[0].message.content
    except Exception:  # noqa: BLE001 — modelo local no disponible / falló → degradar limpio
        logger.exception("anonymize: el NER local no está disponible; se degrada a solo estructurados")
        return None

    data = _parse_ner_json(content or "")
    if data is None:
        logger.warning("anonymize: el NER local no devolvió JSON legible; se degrada")
        return None

    entities: list[tuple[str, str]] = []
    for llave, tipo in _NER_TIPO.items():
        for val in data.get(llave, []) or []:
            s = str(val).strip()
            if s:
                entities.append((tipo, s))
    return entities


def _apply_ner(text: str, entities: list[tuple[str, str]], session: AnonSession) -> str:
    """Reemplaza las entidades (literal, sin distinguir mayúsculas) por su marcador consistente.
    Las más largas primero, para que un nombre no parta a otro que lo contiene."""
    out = text or ""
    for tipo, value in sorted(entities, key=lambda e: len(e[1]), reverse=True):
        if not value.strip():
            continue
        marker = session.marker_for(tipo, value)
        out = re.sub(re.escape(value), lambda _m, _mk=marker: _mk, out, flags=re.IGNORECASE)
    return out


# ── Pasada 3 · reidentificación por número "pelado" (FIX 5) ────────────────────────────────────
def _apply_reidentification(text: str, session: AnonSession) -> str:
    """Cierra la grieta del número PELADO: si una corrida de dígitos SIN separadores normaliza al
    mismo valor que YA quedó enmascarado en la sesión (p. ej. `79484321` cuando `79.484.321` ya es
    `[[CEDULA_1]]`), la enmascara con el MISMO marcador — así una "cuantía" no revive el dato. Solo
    reemplaza en coincidencia EXACTA contra el mapa (no toca números no relacionados)."""
    out = text or ""
    # dígitos del valor (≥6) → marcador, para los valores numéricos ya mapeados en la sesión.
    # Se extraen los dígitos aunque el valor traiga palabra clave o separadores (p. ej.
    # "cédula 79.484.321" → "79484321"); se omiten emails/URLs (dígitos dispersos, sin sentido).
    digit_map: dict[str, str] = {}
    for marker, value in session.map.items():
        if "@" in value or "://" in value:
            continue
        digits = re.sub(r"\D", "", value)
        if len(digits) >= 6:
            digit_map.setdefault(digits, marker)
    if not digit_map:
        return out

    def _repl(m: re.Match) -> str:
        return digit_map.get(m.group(0), m.group(0))

    return re.sub(r"(?<!\d)\d{6,}(?!\d)", _repl, out)


# ── Verificación (segundo pase) ───────────────────────────────────────────────────────────────
def scan_pii(text: str) -> list[dict]:
    """Escanea el texto con TODOS los patrones estructurados y devuelve los spans hallados:
    [{"tipo", "valor", "start", "end"}]. Base de `contains_pii` y de `spans_pii_restantes`."""
    spans: list[dict] = []
    s = text or ""
    for tipo, pat in _STRUCTURED_PATTERNS:
        for m in pat.finditer(s):
            spans.append({"tipo": tipo, "valor": m.group(0), "start": m.start(), "end": m.end()})
    spans.sort(key=lambda x: x["start"])
    return spans


def contains_pii(text: str) -> bool:
    """True si el texto trae PII ESTRUCTURADA identificable (cédula, NIT, radicado, email,
    teléfono, cuenta, URL). Puerta reutilizable: el PATCH del caso la usa para rechazar un texto
    que el abogado haya reeditado y vuelto a ensuciar. No cubre nombres (eso es NER + revisión)."""
    s = text or ""
    return any(pat.search(s) for _tipo, pat in _STRUCTURED_PATTERNS)


def scan_suspects(text: str) -> list[dict]:
    """Heurística de SOSPECHA (FIX 3+4): candidatos que el NER local pudo OMITIR y que `scan_pii`
    (solo estructurados) nunca surfacearía — nombres propios multi-palabra, razones sociales por
    sufijo societario, direcciones e IDs "pelados" de OCR sucio. Devuelve spans con `tipo`
    `sospecha_nombre` / `sospecha_direccion` / `sospecha_id` (distinto de la PII CONFIRMADA) para
    que la Fase 2 los resalte. NO oculta nada: solo alerta. Una lista vacía significa "nada que YO
    detecte", NO "garantizado limpio"."""
    s = text or ""
    spans: list[dict] = []

    def _add(tipo: str, m: re.Match) -> None:
        spans.append({"tipo": tipo, "valor": m.group(0), "start": m.start(), "end": m.end()})

    for m in _DIRECCION_RE.finditer(s):
        _add("sospecha_direccion", m)
    for rx in (_SUFIJO_SOC_RE, _INSTITUC_RE):
        for m in rx.finditer(s):
            _add("sospecha_nombre", m)
    for m in _NOMBRE_RE.finditer(s):
        palabras = re.findall(_CAP_WORD, m.group(0))
        if palabras and all(p.lower() in _STOP_CAP for p in palabras):
            continue  # secuencia genérica (p. ej. "Constitución Política") → no es nombre propio
        _add("sospecha_nombre", m)
    for m in _ID_PELADO_RE.finditer(s):
        _add("sospecha_id", m)

    spans.sort(key=lambda x: x["start"])
    return spans


# ── API pública ───────────────────────────────────────────────────────────────────────────────
def anonymize_text(
    text: str,
    *,
    session: Optional[AnonSession] = None,
    run_ner: bool = True,
    llm: Optional[Callable] = None,
) -> AnonResult:
    """Anonimiza UN texto (2 pasadas + verificación). Pasa una `session` compartida para dar
    marcadores consistentes entre varios textos del mismo asunto. `llm` inyectable (tests);
    por defecto usa el `call_llm` real forzando el modelo local."""
    session = session if session is not None else AnonSession()
    warnings: list[str] = []

    out = _apply_structured(text or "", session)

    ner_ran = False
    if run_ner:
        entities = _run_ner(out, llm)
        if entities is None:
            warnings.append(
                "No se pudo revisar nombres y empresas automáticamente (falta el motor local). "
                "Revisa a mano que no queden nombres reales antes de confirmar.")
        else:
            out = _apply_ner(out, entities, session)
            ner_ran = True

    # Pasada 3: reidentificación de números pelados ya mapeados (FIX 5).
    out = _apply_reidentification(out, session)

    # Verificación: estructurados que sobrevivieron + heurística de sospecha (FIX 3+4).
    restantes = scan_pii(out) + scan_suspects(out)
    restantes.sort(key=lambda x: x["start"])
    return AnonResult(text=out, anon_map=dict(session.map),
                      spans_pii_restantes=restantes, ner_ran=ner_ran, warnings=warnings)


def anonymize_bundle(
    message: str,
    documents: list[dict],
    gold_answer: str,
    *,
    run_ner: bool = True,
    llm: Optional[Callable] = None,
) -> dict:
    """Anonimiza el asunto completo (pregunta + documentos + borrador aprobado) con UNA sola
    sesión, así una misma entidad recibe el mismo marcador en todo el caso. Devuelve el bundle
    ya anonimizado + el mapa (para la pantalla) + su hash (lo persistible) + los spans restantes.

    `documents`: [{"filename": str, "chunks": [str, ...]}]. Estructura conservada, texto anonimizado.
    """
    session = AnonSession()
    warnings: list[str] = []
    ner_ok = True

    def _anon(t: str) -> str:
        nonlocal ner_ok
        r = anonymize_text(t, session=session, run_ner=run_ner, llm=llm)
        if run_ner and not r.ner_ran:
            ner_ok = False
        for w in r.warnings:
            if w not in warnings:
                warnings.append(w)
        return r.text

    message_anon = _anon(message or "")
    gold_answer_anon = _anon(gold_answer or "")
    documents_anon: list[dict] = []
    for doc in documents or []:
        if not isinstance(doc, dict):
            continue
        chunks = [_anon(str(c)) for c in (doc.get("chunks") or [])]
        documents_anon.append({"filename": str(doc.get("filename") or ""), "chunks": chunks})

    # Verificación global sobre TODO lo que quedó (pregunta + borrador + chunks).
    todo = "\n".join([message_anon, gold_answer_anon]
                     + [c for d in documents_anon for c in d["chunks"]])
    restantes = scan_pii(todo) + scan_suspects(todo)
    restantes.sort(key=lambda x: x["start"])

    return {
        "message": message_anon,
        "documents": documents_anon,
        "gold_answer": gold_answer_anon,
        "anon_map": dict(session.map),
        "anon_map_hash": anon_map_hash(session.map),
        "spans_pii_restantes": restantes,
        "ner_ran": ner_ok,
        "warnings": warnings,
    }


def anon_map_hash(anon_map: dict[str, str]) -> str:
    """HASH sha256 estable del mapa marcador→valor real. Es lo ÚNICO persistible del mapa: no
    permite reidentificar (no es reversible), solo auditar que la anonimización fue reproducible.
    Determinista (claves ordenadas). '' para un mapa vacío."""
    if not anon_map:
        return ""
    payload = json.dumps(anon_map, ensure_ascii=False, sort_keys=True)
    return "sha256:" + hashlib.sha256(payload.encode("utf-8")).hexdigest()
