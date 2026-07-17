"""Mia · security.anonymize — anonimización de asuntos reales para el Banco de oro (Fase 1).

Lo CRÍTICO por confidencialidad: antes de guardar un asunto REAL como caso de oro, se le quita
TODO dato identificable. A diferencia de `security/redact.py` (que enmascara CREDENCIALES en
logs, siempre activo e irreversible), aquí el objetivo es distinto: sustituir PII de personas y
del expediente por marcadores CONSISTENTES y TIPADOS (`CEDULA_1`, `PERSONA_1`…) que preservan el
sentido jurídico (misma entidad → mismo marcador) para que el caso siga siendo un examen útil.

AGNÓSTICO DE JURISDICCIÓN: los formatos de identificación PROPIOS DE UN PAÍS (cédula, NIT,
radicado, teléfono local) NO viven en este código — viven en `jurisdiction/packs/{code}/
id_formats.json`. Mia no es de ningún país: el conocimiento de país está en los datos.

DECISIÓN DE PRODUCTO — "ENMASCARAR TODO, SIEMPRE" (y por qué):
Este módulo NO conoce la jurisdicción del despacho y NO acepta que se la digan. Compone SIEMPRE
la MISMA tabla: base universal + los `id_formats` de TODOS los packs instalados + los respaldos
por rol. Un despacho español enmascara un NIT y un radicado colombianos; uno colombiano enmascara
un DNI español.
  · Por qué: el anonimizador es el GATE DE CONFIDENCIALIDAD — enmascara datos del cliente antes de
    que salgan hacia una IA externa. El secreto profesional MANDA sobre la precisión del análisis.
    Un despacho español atiende clientes colombianos; un dato no deja de ser del cliente por ser
    de otro país.
  · Qué se paga: SOBRE-ENMASCARADO — algún número inocuo (una cuantía, un código interno) queda
    oculto tras un marcador. Coste aceptado y explícito: es barato y reversible en sesión.
    Filtrar una cédula no lo es.
  · Qué se cierra: acoplar la tabla a la configuración la volvía frágil — bastaba un typo de
    `role` en el JSON de un pack, o una jurisdicción mal resuelta, para desactivar un respaldo
    entero y dejar salir documentos en crudo. Sin perilla no hay perilla que fallar.

REGLA DE SEGURIDAD (fail-closed, innegociable): la cobertura NUNCA cae por debajo de
`_BASELINE_FORMATS` + `_ROLE_FALLBACKS`. Sé preciso con lo que esto promete y lo que no:
  1. `_BASELINE_FORMATS` (URL, email, cuenta) se aplica SIEMPRE, desde el código.
  2. `_ROLE_FALLBACKS` (documento/teléfono pan-hispanos) se aplica SIEMPRE también — ya NO se
     suprime porque "algún pack cubra ese rol". Ese `covered` era la fuga: un pack con un regex
     válido pero estrecho que declaraba `role: "document"` apagaba el respaldo pan-hispano entero.
  3. Todo fallo (pack ausente/ilegible, regex inválido, cargador roto) se registra y se DEGRADA
     a las capas 1+2; jamás propaga una excepción ni deja pasar el texto crudo.
Lo que un pack corrupto SÍ pierde son SUS PROPIOS patrones (un `id_formats.json` ilegible no
aporta cédula/NIT/radicado). Eso es correcto por diseño: no hay forma de adivinar un regex que no
se pudo leer, y las capas 1+2 siguen cubriendo. Lo que un pack NO puede hacer nunca es RESTAR
cobertura a las capas 1+2 ni a los patrones de otro pack.
Corolario de caché: una degradación TRANSITORIA (I/O, arranque a medias) NO se cachea — si la
carga de packs señaló fallo, la tabla se reconstruye en la siguiente llamada. Un hipo no puede
dejar a un despacho colombiano operando la sesión entera sin RADICADO/NIT.

Dos pasadas + dos redes de verificación:

  · Pasada 1 — REGEX determinista (estructurados, alta precisión): documentos de identidad, NIT,
    radicado, email, teléfono, cuentas, URLs — el juego exacto lo fija el pack del despacho + la
    base universal. Sin red, sin costo, idempotente.
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

import functools
import hashlib
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Callable, Optional

logger = logging.getLogger("mia.security.anonymize")

# Marcador tipado y consistente. Forma `[[TIPO_N]]`: deliberadamente NO coincide con ningún
# patrón de PII (no trae puntos, arrobas ni corridas largas de dígitos), así el segundo pase de
# verificación no lo vuelve a marcar y la anonimización es IDEMPOTENTE (re-correr no cambia nada).
_MARKER_RE = re.compile(r"\[\[[A-ZÁÉÍÓÚÑ]+_\d+\]\]")


def _marker(tipo: str, n: int) -> str:
    return f"[[{tipo}_{n}]]"


# Valor "PELADO": solo dígitos y separadores/adornos de número, SIN palabra clave que lo tipifique
# (`79484321`, `615 55 12 34`, `+34 612 345 678`). Lo contrario de `cuenta de ahorros 12345678` o
# `DNI 12345678Z`, que se identifican a sí mismos. Ver `AnonSession.existing_marker_for`.
_PELADO_RE = re.compile(r"[\d\s.\-()+]+")


# ── Pasada 1 · patrones de estructurados (orden IMPORTA: lo más específico primero) ───────────
# Los formatos PROPIOS DE UN PAÍS (cédula, NIT, radicado, teléfono local) NO viven aquí: viven en
# `jurisdiction/packs/{code}/id_formats.json` y los carga el pack del despacho. Aquí queda solo la
# RED FAIL-CLOSED del código, que se aplica SIEMPRE — con pack, sin pack o con el pack roto.
#
# Cada entrada se aplica EN ORDEN (`order` ascendente); cada match se reemplaza por su marcador,
# así un patrón posterior nunca ve los dígitos que ya consumió uno anterior (p. ej. el radicado de
# 23 dígitos se retira antes de que el patrón de teléfono pueda morder un tramo de 10).

# BASE UNIVERSAL — cierta en CUALQUIER jurisdicción. Se aplica siempre y un pack NO puede quitarla
# (solo añadir): la cobertura nunca puede reducirse por configuración.
_BASELINE_FORMATS: dict[str, dict] = {
    # URL (http/https/www) — antes que email/números para no partir el host.
    "url": {"marker": "URL", "role": "url", "order": 10, "flags": "i",
            "regex": r"\bhttps?://[^\s<>\"')]+|\bwww\.[^\s<>\"')]+"},
    # Email.
    "email": {"marker": "EMAIL", "role": "email", "order": 20,
              "regex": r"\b[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}\b"},
    # Cuenta bancaria (por palabra clave, para no morder cualquier número).
    "cuenta": {"marker": "CUENTA", "role": "account", "order": 60, "flags": "i",
               "regex": (r"\b(?:cuenta|cta)\.?\s*(?:de\s+ahorros|corriente|no\.?|n[°º]\.?)?"
                         r"\s*:?\s*\d[\d\-]{6,}\d\b")},
}

# RESPALDO POR ROL — se aplica SIEMPRE, pase lo que pase con los packs. NO se suprime porque un
# pack "cubra" el rol: ese era el agujero (un pack con `role: "document"` y un regex estrecho pero
# válido apagaba el respaldo pan-hispano entero y dejaba salir cédulas y DNIs en crudo). Ahora el
# pack de país SUMA precisión sobre esta red, nunca la sustituye. Consecuencia asumida: doble
# cobertura del mismo rol — inofensiva, porque cada match se sustituye por un marcador y el patrón
# siguiente ya no ve los dígitos (y `AnonSession` da el mismo marcador al mismo valor).
# Duplica a propósito lo que `jurisdiction.pack.generic_pack()` declara como dato: esta copia en
# código es la garantía de que ni un fallo del cargador de packs deja pasar texto crudo.
_ROLE_FALLBACKS: dict[str, dict] = {
    # Documento de identidad por PALABRA CLAVE (DNI/NIE/RUT/CURP/RFC/cédula/pasaporte): por
    # palabra clave y no por forma, porque cada país numera distinto.
    "document": {"marker": "DOCUMENTO", "role": "document", "order": 55, "flags": "i",
                 "regex": (r"\b(?:c\.?\s?c\.?|c[eé]dula|documento\s+de\s+identidad|"
                           r"identificaci[oó]n|D\.?N\.?I\.?|N\.?I\.?E\.?|R\.?U\.?T\.?|"
                           r"C\.?U\.?R\.?P\.?|R\.?F\.?C\.?|pasaporte)\s*"
                           r"(?:n[o°º]\.?\s*)?:?\s*[\dA-Z][\dA-Z.\-]{5,}\b")},
    # Teléfono internacional. Tres formas, en orden:
    #   1. prefijo `+` (`+34 612 345 678`, `+57 (1) 555-1234`);
    #   2. corrida PELADA de 7-15 dígitos (`6125551234`);
    #   3. AGRUPADO con separadores (`615 55 12 34`, `615-55-12-34`, `91.123.45.67`) — la forma
    #      NORMAL de escribir un teléfono en España y en medio mundo, que las dos anteriores NO
    #      cubrían: se filtraban enteros.
    # La forma 3 es la laxa, así que va acotada por tres guardas (ver `_PHONE_FALLBACK_RE`).
    "phone": {"marker": "TELEFONO", "role": "phone", "order": 80,
              "regex": None},   # se inyecta abajo (_PHONE_FALLBACK_RE); ver nota
}

# Regex del respaldo de teléfono. Vive aparte por lo delicado del equilibrio fuga/ruido.
#
# La alternativa 3 (agrupada) es LAXA por naturaleza y en texto jurídico hay números por todas
# partes. Tres guardas la contienen, y hay que entenderlas antes de tocarla:
#   · `(?!...fecha...)` ×2 — NO se come fechas. Las fechas se CONSERVAN a propósito (caducidad y
#     prescripción se calculan con ellas): un caso de oro sin fechas no sirve de examen. Se
#     descartan las dos formas con separador `. - espacio`: `16-07-2026` (d-m-a) y `2026-07-16`
#     (ISO). Con `/` no hace falta: `/` no está en la clase de separadores.
#   · `(?=(?:\d[\s.\-]?){7,15}(?!\d))` — exige 7-15 DÍGITOS en total, el rango real de un teléfono
#     con indicativo. Sin esto, `15-20` de una dirección ("Calle 100 No. 15-20") o `12 34` de
#     cualquier tabla se enmascararían como teléfono.
#   · grupos de 2-4 dígitos, entre 2 y 5 grupos — descarta `Ley 1437 de 2011` (el separador es la
#     palabra "de", no un signo) y `1.077` (4 dígitos < 7).
# Ruido residual ACEPTADO y conocido: un rango de artículos con guion y 7+ dígitos
# (`artículos 1494-1495`) o una cuantía agrupada (`12.345.678`) pueden quedar enmascarados. Es el
# coste de la decisión "enmascarar todo, siempre": sobre-enmascarar es barato, filtrar no.
_PHONE_FALLBACK_RE = (
    r"\+\d[\d\s().-]{6,}\d"                                   # 1 · con prefijo internacional
    r"|(?<!\d)\d{7,15}(?!\d)"                                 # 2 · corrida pelada
    r"|(?<!\d)"                                               # 3 · agrupado con separadores
    r"(?![0-3]?\d[\s.\-][01]?\d[\s.\-]\d{4}(?!\d))"           #     …no es `16-07-2026`
    r"(?!(?:19|20)\d{2}[\s.\-][01]?\d[\s.\-][0-3]?\d(?!\d))"  #     …no es `2026-07-16`
    r"(?=(?:\d[\s.\-]?){7,15}(?!\d))"                         #     …7-15 dígitos en total
    r"\d{2,4}(?:[\s.\-]\d{2,4}){1,4}(?!\d)"
)
_ROLE_FALLBACKS["phone"]["regex"] = _PHONE_FALLBACK_RE


def _compile_format(key: str, fmt: dict) -> Optional[tuple[int, str, str, re.Pattern]]:
    """Compila UNA entrada de `id_formats`. Devuelve (order, marker, role, patrón) o None si la
    entrada es inservible. FAIL-SOFT POR ENTRADA: un regex mal escrito en el JSON de un pack se
    DESCARTA con log y no tumba al anonimizador — el resto de la cobertura (incluida la base
    universal) sigue en pie. Nunca propaga la excepción: reventar aquí sería dejar el texto crudo."""
    if not isinstance(fmt, dict):
        return None
    regex = fmt.get("regex")
    if not regex or not isinstance(regex, str):
        return None
    flags = re.IGNORECASE if "i" in str(fmt.get("flags") or "").lower() else 0
    try:
        pat = re.compile(regex, flags)
    except (re.error, TypeError, RecursionError):
        logger.exception("anonymize: formato de ID inválido en el pack (%s); se descarta esa "
                         "entrada y se conserva el resto de la cobertura", key)
        return None
    marker = str(fmt.get("marker") or key).strip().upper() or key.upper()
    role = str(fmt.get("role") or "").strip().lower()
    try:
        order = int(fmt.get("order", 100))
    except (TypeError, ValueError):
        order = 100
    return (order, marker, role, pat)


def _cached_unless_degraded(build: Callable[[], tuple]) -> Callable[[], object]:
    """Memoiza `build()` SOLO si NO señaló degradación.

    `build` devuelve `(valor, degraded)`. Si `degraded` es True (los packs no se pudieron listar o
    leer), el valor se DEVUELVE pero NO se cachea: la siguiente llamada reintenta.

    Por qué existe (fuga de disponibilidad): con un `lru_cache` normal, un hipo transitorio de I/O
    durante el arranque congelaba la tabla DEGRADADA para toda la vida del proceso — un despacho
    colombiano habría operado la sesión entera sin RADICADO ni NIT por un parpadeo del disco. El
    caché es una optimización; jamás puede fijar una pérdida de cobertura.

    `.cache_clear()` conserva el contrato de `lru_cache` (los tests reubican `PACKS_DIR`)."""
    box: dict = {}

    @functools.wraps(build)
    def wrapper():
        if "v" in box:
            return box["v"]
        value, degraded = build()
        if not degraded:
            box["v"] = value
        return value

    wrapper.cache_clear = box.clear   # type: ignore[attr-defined]
    return wrapper


def _pack_formats() -> tuple[dict, bool]:
    """`id_formats` de TODOS los packs instalados + si la carga se DEGRADÓ.

    No recibe jurisdicción a propósito (decisión "enmascarar todo, siempre"): el juego de patrones
    no depende de la configuración del despacho. Import diferido y todo en try/except: si la capa
    de jurisdicción falla entera se devuelve vacío + `degraded=True` y el llamador se queda con la
    base universal + los respaldos, sin cachear el bajón."""
    degraded = False
    try:
        from ..jurisdiction.pack import list_packs, load_pack   # import diferido (evita ciclos)
    except Exception:  # noqa: BLE001 — sin capa de jurisdicción → solo base universal + respaldos
        logger.exception("anonymize: no se pudo cargar la capa de jurisdicción; se anonimiza con "
                         "la base universal + los respaldos por rol")
        return {}, True
    try:
        codes = tuple(list_packs())
    except Exception:  # noqa: BLE001
        logger.exception("anonymize: no se pudieron listar los packs; base universal + respaldos")
        return {}, True
    out: dict[str, dict] = {}
    for code in codes:
        try:
            formats = load_pack(code).id_formats or {}
        except Exception:  # noqa: BLE001 — un pack roto no puede tumbar la anonimización
            logger.exception("anonymize: pack '%s' ilegible; se ignora y se conserva la base", code)
            degraded = True
            continue
        for key, fmt in formats.items():
            if isinstance(fmt, dict):        # descarta claves de documentación ("_note": "...")
                out[f"{code}:{key}"] = fmt
    return out, degraded


def _build_structured_patterns() -> tuple[tuple[tuple[str, re.Pattern], ...], bool]:
    """Tabla (TIPO, patrón) ORDENADA. La MISMA para todo el mundo, siempre.

    Composición (decisión "enmascarar todo, siempre" — ver la cabecera del módulo):
      1. `_BASELINE_FORMATS` — SIEMPRE.
      2. Los `id_formats` de TODOS los packs INSTALADOS — sin filtrar por jurisdicción del
         despacho: un cliente colombiano de un bufete español conserva su cobertura de NIT.
      3. `_ROLE_FALLBACKS` — SIEMPRE también (ya no hay supresión por `role` "cubierto").
    Ordenada por `order` (lo específico antes que lo laxo, para que un patrón laxo no muerda los
    dígitos de uno preciso) y deduplicada por (marcador, patrón, flags)."""
    pack_formats, degraded = _pack_formats()

    entries: list[tuple[int, str, str, re.Pattern]] = []
    for source in (_BASELINE_FORMATS, pack_formats, _ROLE_FALLBACKS):
        prefix = "fallback:" if source is _ROLE_FALLBACKS else ""
        for key, fmt in source.items():
            c = _compile_format(f"{prefix}{key}", fmt)
            if c:
                entries.append(c)

    entries.sort(key=lambda e: (e[0], e[1]))
    seen: set[tuple[str, str, int]] = set()
    table: list[tuple[str, re.Pattern]] = []
    for _order, marker, _role, pat in entries:
        sig = (marker, pat.pattern, pat.flags)
        if sig in seen:
            continue
        seen.add(sig)
        table.append((marker, pat))
    return tuple(table), degraded


_structured_patterns = _cached_unless_degraded(_build_structured_patterns)

# ── Heurística de SOSPECHA (FIX 3+4) · candidatos que el NER local pudo OMITIR ─────────────────
# NO oculta nada: solo MARCA para que la revisión humana (Fase 2) resalte. Tipos distintos de la
# PII confirmada (`sospecha_*`), para no dar falsa sensación de "todo limpio".
_CAP_WORD = r"[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+"

# Palabras Capitalizadas genéricas del lenguaje jurídico: si TODA la secuencia cae aquí, no es un
# nombre propio (evita falsos positivos tipo "Constitución Política", "Corte Suprema"). Base
# PAN-HISPANA; el pack del despacho AÑADE las suyas ("colombia", "bogotá"…) vía `pii_hints.json`.
# Un pack solo puede AÑADIR: quitar una stop-word aumentaría el ruido, nunca la fuga.
_STOP_CAP_BASE = {
    "constitución", "política", "ley", "corte", "suprema", "justicia", "consejo", "estado",
    "república", "código", "civil", "penal", "comercial", "laboral", "sala", "tribunal",
    "superior", "juzgado", "ministerio", "nación", "procuraduría", "fiscalía",
    "general", "nacional", "departamento", "municipio", "distrito", "sentencia", "auto",
    "decreto", "resolución", "artículo", "capítulo", "título", "libro",
    "administrativo", "contencioso", "procedimiento", "comercio", "sustantivo", "trabajo",
    "única", "único", "unificada",
}

# Prefijos de vía PAN-HISPANOS. El pack añade los locales ("Carrera", "Kra", "Diagonal"…).
_ADDRESS_PREFIXES_BASE = ("Calle", "Cll", "Avenida", "Av", "Autopista", "Carretera",
                          "Plaza", "Paseo", "Camino")

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

def _pack_hints() -> tuple[tuple[tuple[str, ...], frozenset], bool]:
    """Pistas de sospecha de TODOS los packs instalados (prefijos de vía + stop-words) + si la
    carga se degradó. Mismo contrato que `_pack_formats`: sin jurisdicción (la sospecha también
    se marca "toda, siempre" — una dirección colombiana en un despacho español debe resaltarse) y
    fail-soft (si la capa de jurisdicción falla, queda la base pan-hispana, sin cachear el bajón)."""
    try:
        from ..jurisdiction.pack import list_packs, load_pack   # import diferido (evita ciclos)
    except Exception:  # noqa: BLE001
        return ((), frozenset()), True
    try:
        codes = tuple(list_packs())
    except Exception:  # noqa: BLE001
        logger.exception("anonymize: no se pudieron listar los packs para las pistas de sospecha")
        return ((), frozenset()), True
    degraded = False
    prefixes: list[str] = []
    stops: set[str] = set()
    for code in codes:
        try:
            hints = load_pack(code).pii_hints or {}
        except Exception:  # noqa: BLE001 — pack roto → se ignoran sus pistas, no se revienta
            logger.exception("anonymize: no se pudieron leer las pistas del pack '%s'", code)
            degraded = True
            continue
        for p in hints.get("address_prefixes") or []:
            if isinstance(p, str) and p.strip():
                prefixes.append(p.strip())
        for s in hints.get("stop_capitalized") or []:
            if isinstance(s, str) and s.strip():
                stops.add(s.strip().lower())
    return (tuple(prefixes), frozenset(stops)), degraded


def _build_direccion_re() -> tuple[re.Pattern, bool]:
    """Dirección física (`Calle 100 No. 15-20`, `Carrera 7 # 12-34`, ...). Los prefijos de vía
    LOCALES los aportan los packs (todos); la base pan-hispana está siempre."""
    (pack_prefixes, _stops), degraded = _pack_hints()
    prefixes = list(dict.fromkeys([*_ADDRESS_PREFIXES_BASE, *pack_prefixes]))
    alt = "|".join(re.escape(p) for p in prefixes)
    return re.compile(
        rf"\b(?:{alt})\.?\s*"
        r"\d{1,3}[A-Za-z]?\s*"
        r"(?:#|No\.?|N[°º]\.?|Nro\.?)?\s*"
        r"\d{1,3}[A-Za-z]?(?:\s*-\s*\d{1,3}[A-Za-z]?)?",
        re.IGNORECASE), degraded


def _build_stop_cap() -> tuple[frozenset, bool]:
    """Stop-words Capitalizadas: base pan-hispana + las de todos los packs (unión, nunca resta)."""
    (_prefixes, pack_stops), degraded = _pack_hints()
    return frozenset(_STOP_CAP_BASE | set(pack_stops)), degraded


_direccion_re = _cached_unless_degraded(_build_direccion_re)
_stop_cap = _cached_unless_degraded(_build_stop_cap)

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
    _by_digits: dict[str, str] = field(default_factory=dict)    # dígitos (≥6) → marcador

    @staticmethod
    def _norm(value: str) -> str:
        """Clave de identidad: minúsculas sin separadores, para que '79.123.456' y '79123456'
        (o 'Juan  Pérez' y 'juan pérez') mapeen al mismo marcador."""
        return re.sub(r"[\s.\-]+", "", str(value or "").strip().lower())

    @staticmethod
    def _digits(value: str) -> str:
        """Dígitos del valor, sin nada más. '' para emails/URLs (sus dígitos son ruido: dos
        correos distintos no son la misma entidad por compartir un '2')."""
        s = str(value or "")
        if "@" in s or "://" in s:
            return ""
        return re.sub(r"\D", "", s)

    def marker_for(self, tipo: str, value: str) -> str:
        key = (tipo, self._norm(value))
        marker = self._reverse.get(key)
        if marker is None:
            self._counters[tipo] = self._counters.get(tipo, 0) + 1
            marker = _marker(tipo, self._counters[tipo])
            self._reverse[key] = marker
            self.map[marker] = str(value)
        digits = self._digits(value)
        if len(digits) >= 6:
            self._by_digits.setdefault(digits, marker)   # el PRIMER tipo que lo vio manda
        return marker

    def existing_marker_for(self, value: str) -> Optional[str]:
        """Marcador YA asignado en la sesión a este MISMO número PELADO. `None` si es nuevo o si
        el valor no es "pelado".

        Por qué (consistencia de marcadores): con "enmascarar todo, siempre" conviven varios
        patrones sobre el mismo texto — el preciso del pack y el respaldo laxo. Sin esto, una
        cédula escrita `79.484.321` (→ `[[CEDULA_1]]`) y repetida PELADA más abajo como `79484321`
        recibiría `[[TELEFONO_1]]` del respaldo: la misma entidad con dos marcadores distintos, y
        el caso de oro deja de ser ilegible como examen. Es la misma regla de la pasada 3, aplicada
        ya en la pasada 1 para que gane el patrón MÁS ESPECÍFICO (que corre primero, por `order`).

        Solo para valores PELADOS (dígitos y separadores, sin palabra clave) y con coincidencia
        EXACTA de dígitos (≥6). Ese acotamiento importa: un valor CON palabra clave se identifica
        a sí mismo (`cuenta de ahorros 12345678` es una cuenta, dígalo quien lo diga) y debe
        conservar SU tipo aunque otro dato de la sesión comparta los mismos dígitos por
        coincidencia. Solo el número pelado es ambiguo, y solo él adopta el marcador previo."""
        raw = str(value or "").strip()
        if not raw or not _PELADO_RE.fullmatch(raw):
            return None
        digits = self._digits(raw)
        if len(digits) < 6:
            return None
        return self._by_digits.get(digits)


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
    """Pasada 1. Los patrones corren por `order`: primero los del pack de país (precisos), después
    los respaldos (laxos). Si un patrón posterior vuelve a encontrar un número que otro YA
    enmascaró, reusa SU marcador en vez de acuñar uno nuevo de otro tipo — así la misma entidad
    conserva un solo marcador aunque la cubran dos patrones (ver `AnonSession.existing_marker_for`)."""
    out = text or ""
    for tipo, pat in _structured_patterns():
        def _repl(m: re.Match, _tipo=tipo) -> str:
            raw = m.group(0)
            previo = session.existing_marker_for(raw)
            return previo if previo is not None else session.marker_for(_tipo, raw)
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
    [{"tipo", "valor", "start", "end"}]. Base de `contains_pii` y de `spans_pii_restantes`.

    Sin parámetro de jurisdicción, a propósito: la tabla es la misma para todo despacho (base
    universal + TODOS los packs instalados + respaldos). Ver la cabecera del módulo."""
    spans: list[dict] = []
    s = text or ""
    for tipo, pat in _structured_patterns():
        for m in pat.finditer(s):
            spans.append({"tipo": tipo, "valor": m.group(0), "start": m.start(), "end": m.end()})
    spans.sort(key=lambda x: x["start"])
    return spans


def contains_pii(text: str) -> bool:
    """True si el texto trae PII ESTRUCTURADA identificable (documento, NIT, radicado, email,
    teléfono, cuenta, URL — base universal + TODOS los packs instalados + respaldos). Puerta
    reutilizable: el PATCH del caso la usa para rechazar un texto que el abogado haya reeditado y
    vuelto a ensuciar. No cubre nombres (eso es NER + revisión)."""
    s = text or ""
    return any(pat.search(s) for _tipo, pat in _structured_patterns())


def scan_suspects(text: str) -> list[dict]:
    """Heurística de SOSPECHA (FIX 3+4): candidatos que el NER local pudo OMITIR y que `scan_pii`
    (solo estructurados) nunca surfacearía — nombres propios multi-palabra, razones sociales por
    sufijo societario, direcciones e IDs "pelados" de OCR sucio. Devuelve spans con `tipo`
    `sospecha_nombre` / `sospecha_direccion` / `sospecha_id` (distinto de la PII CONFIRMADA) para
    que la Fase 2 los resalte. NO oculta nada: solo alerta. Una lista vacía significa "nada que YO
    detecte", NO "garantizado limpio"."""
    stop_cap = _stop_cap()
    s = text or ""
    spans: list[dict] = []

    def _add(tipo: str, m: re.Match) -> None:
        spans.append({"tipo": tipo, "valor": m.group(0), "start": m.start(), "end": m.end()})

    for m in _direccion_re().finditer(s):
        _add("sospecha_direccion", m)
    for rx in (_SUFIJO_SOC_RE, _INSTITUC_RE):
        for m in rx.finditer(s):
            _add("sospecha_nombre", m)
    for m in _NOMBRE_RE.finditer(s):
        palabras = re.findall(_CAP_WORD, m.group(0))
        if palabras and all(p.lower() in stop_cap for p in palabras):
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
    por defecto usa el `call_llm` real forzando el modelo local.

    NO recibe jurisdicción: enmascara con TODO lo instalado, siempre (ver la cabecera)."""
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
    NO recibe jurisdicción: enmascara con TODO lo instalado, siempre (ver la cabecera).
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
