"""Mia · onboarding.soul_interview — la entrevista que construye el SOUL.md (Módulo 5).

El SOUL.md es la capa MÁS importante del sistema de prompts: la capa 1 (identidad)
que el prompt_builder antepone a todo (1b) y que el grafo carga como `soul_snapshot`
al iniciar cada turno (Módulo 5). La entrevista lo arma de forma conversacional a
partir de las respuestas del abogado.

DISEÑO (rediseño 2026-07-06, decisión de Pipe): la generación es DETERMINISTA y
OMITE lo vacío — jamás imprime placeholders entre corchetes. Antes el sistema
rellenaba un template fijo de 9 secciones y CONSERVABA `[CORCHETES]` en todo campo
que el wizard no preguntaba (T.P., zona horaria, "los 3 pilares", jurisprudencia…);
el resultado mezclaba respuestas reales con plantilla vacía. Ahora:
- Solo aparecen las secciones y campos que el abogado respondió; lo demás no existe.
- Sin LLM en la generación → cero invención (regla dura de Pipe: nada se inventa) y
  cero riesgo de que un modelo devuelva el molde a medio llenar.
- Se removieron las preguntas de "objetivo del año" y "los 3 pilares" (estrategia de
  negocio, no de redacción; reportadas como confusas) — junto con la sección `mission`.
- 2026-07-09 (decisión de Pipe): se removieron del cuestionario P10 (legal_voice.structure),
  P11 (legal_voice.banned_words), P14 (hard_nos) y P17 (rhythm) — el estilo de escritura se
  aprende de los escritos reales y del flywheel HITL (no se pregunta), los límites se
  construyen con el tiempo, y el ritmo/horario no le sirve a Mia. `build_soul`/`build_summary`
  SIGUEN renderizando esos campos si vienen en respuestas legacy (`responses.json` viejo) —
  solo desaparecieron del cuestionario, no de la generación.
- `build_summary` produce un RESUMEN en lenguaje llano ("Así entendí a tu despacho")
  que es lo que ve el abogado; el SOUL.md técnico queda por debajo.

REDISEÑO 2026-07-20 ("más rico, no más largo" — docs/diseno-soul-onboarding.md):
el perfil capturaba datos censales y CERO criterio. Se pedía el estilo en 3 adjetivos
mientras el resumen decía "tu estilo no te lo pregunto" (se contradecía), y `hard_nos`
se renderizaba sin que ninguna pregunta lo alimentara. Se retiran del cuestionario los
campos que Mia PUEDE INFERIR del trabajo real o que no cambian un borrador — estilo en
adjetivos (p3), sitio web y canales (p4), herramientas (p18: no activan nada, Conexiones
sabe la verdad) y el modo profundo (p19: no implementado, el frontend ya lo ocultaba) —
y se fusionan p6+p7 en un solo paso. En su lugar entran las tres que hacen COMPUTABLE el
criterio: la línea de autonomía (`autonomia.*`), las líneas rojas (`nunca`) y el estándar
de cierre (`terminado`). Mismo número de pasos, otro rendimiento.
`## aprendido` es la sección que crece sola con el uso: no la alimenta ninguna pregunta
— la escribe Mia desde el trabajo real vía `update_soul`. AVISO: ese escritor todavía
NO existe (incremento aparte); hoy la sección solo se RENDERIZA si alguien pone el campo.
Todo lo retirado se SIGUE renderizando si viene en un `responses.json` viejo: un perfil
ya creado no pierde nada ni deja de guardarse (`LEGACY_RENDERED_FIELDS`). Los campos del
cuestionario ORIGINAL de 19 preguntas que hoy no renderiza nadie (`LEGACY_STORED_FIELDS`:
cortes, doctrina, misión…) se reconocen y se conservan igual, aunque no se impriman: un
despacho configurado antes del recorte tiene que poder volver a guardar su perfil.

Helpers de archivo (soul_path / load_soul_text / load_soul_snapshot / soul_status):
puros (solo config + stdlib, sin LLM) para que `agents/state.py` y `agent/core.py`
los importen sin arrastrar el cliente LLM.
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .. import config

logger = logging.getLogger("mia.onboarding.soul")

# RECORTE 2026-08-25 (bitácora de feedback UX 2026-08-19, decisiones de Pipe):
#   · p2 «¿en qué ciudad y país trabajas?» SALE del cuestionario. La ciudad no cambia un
#     borrador (punto 8) y el país ya lo declara el selector múltiple de jurisdicciones, que
#     es el que además enruta los paquetes jurídicos (punto 9/10 · D10). Preguntarlo dos
#     veces era pedirle al abogado que confirmara algo que ya había dicho.
#   · p22 «¿cuándo das un escrito por terminado?» SALE (punto 12). Mismo criterio con el que
#     salieron p3, p4, p18 y p19: el estándar de cierre se aprende del trabajo aprobado, no
#     de una frase escrita antes de que exista un solo documento.
#   · El registro profesional deja de pedirse aquí y vive en Configuración → perfil del
#     despacho (punto 6 · D9): es un dato de la firma, no criterio de redacción.
# `identity.location` y `terminado` pasan a LEGACY_RENDERED_FIELDS: un despacho que los
# respondió antes NO pierde nada — se siguen guardando y se siguen imprimiendo en su SOUL.
#
# ── Las preguntas del onboarding (bloques del Doc 4, menos P8/P9/P12/P13 que el
#    agente aprende del uso, y menos P15/P16 de estrategia — decisión de Pipe 2026-07-06;
#    menos P10/P11/P14/P17 — decisión de Pipe 2026-07-09: la voz de redacción se aprende
#    de los escritos reales y del flywheel HITL (no se pregunta), los límites (hard_nos)
#    se construyen con el tiempo, y el ritmo/horario es irrelevante para Mia).
# Cada pregunta: id · block · field (sección/campo del SOUL que alimenta) · question
# (lo que ve el abogado) · example. Las respuestas del frontend llegan como
# {field: respuesta}; el campo es la llave.
QUESTIONS: list[dict] = [
    # Bloque 1 — Identidad
    {"id": "p1", "block": "identity", "field": "identity.name",
     "question": "¿Cómo se llama tu despacho y cómo firmas tú?",
     "example": "Va impreso en cada escrito que redacte para ti."},
    # Bloque 2 — Jurisdicción y práctica.
    # NOTA (consolidación 2026-07-09, decisión de Pipe): la pregunta descriptiva de país
    # (antes p5, field jurisdiction.base) ya NO se hace — el frontend tiene UN solo
    # selector múltiple de países (el mismo del enrutamiento de paquetes jurídicos) y
    # auto-llena `jurisdiction.base` con los países elegidos al completar.
    # NOTA (rediseño 2026-07-20): p6 y p7 se FUSIONAN en un solo paso. Sigue siendo la
    # pregunta p6 y sigue alimentando `jurisdiction.practice_areas`, pero el frontend
    # recoge en la misma pantalla `jurisdiction.client_type` (a quién defiende). Es el
    # único prior antes de que exista un solo documento; después Mia lo corrige sola
    # leyendo partes y materias de los expedientes.
    {"id": "p6", "block": "jurisdiction", "field": "jurisdiction.practice_areas",
     "question": "¿A quién defiendes y en qué asuntos?",
     "example": "Escribe lo tuyo con tus palabras. Nada de esto queda fijo."},
    # Bloque 3 — Criterio. Aquí está la riqueza (rediseño 2026-07-20): lo que hace
    # COMPUTABLE el juicio del despacho. Antes el perfil capturaba datos censales y cero
    # criterio; `hard_nos` incluso se renderizaba sin que ninguna pregunta lo alimentara.
    {"id": "p20", "block": "criterio", "field": "autonomia.reviso_siempre",
     "question": "¿Qué quieres revisar siempre antes de que salga, y qué puedo resolver sin preguntarte?",
     "example": "Sin esto solo tengo dos modos: pedirte permiso para todo, o excederme."},
    {"id": "p21", "block": "criterio", "field": "nunca",
     "question": "¿Qué no debo hacer nunca?",
     "example": "Una prohibición tuya me dice más que un párrafo sobre tu estilo."},
]

# Orden canónico de los bloques (para el progreso del frontend).
BLOCKS: tuple[str, ...] = ("identity", "jurisdiction", "criterio")

# ── Campos que el generador SABE leer ────────────────────────────────────────
# `build_soul` lee por CAMPO (`identity.name`…), no por id de pregunta. Si llegan llaves
# que no están aquí, el perfil sale vacío y nadie se entera: el API devolvía 200 con un
# SOUL de dos líneas (fallo silencioso comprobado en vivo el 2026-07-20 mandando
# {"p1":…,"p2":…}). Esta lista es el contraste contra el que el endpoint valida antes de
# escribir nada.

# Los que alimenta el cuestionario de hoy (+ `aprendido`, que no pregunta nadie: lo
# escribe Mia desde el trabajo real vía `update_soul`).
CURRENT_FIELDS: frozenset[str] = frozenset({
    "identity.name",
    "jurisdiction.base", "jurisdiction.practice_areas", "jurisdiction.client_type",
    "autonomia.reviso_siempre", "autonomia.decide_solo", "nunca",
    "aprendido",
})

# Campos de entrevistas ANTERIORES que `build_soul`/`build_summary` SIGUEN renderizando
# (voz, canales, estructura, ritmo, herramientas, triad…): salieron del cuestionario, no
# del generador.
LEGACY_RENDERED_FIELDS: frozenset[str] = frozenset({
    "identity.voice", "identity.channels",
    "legal_voice.structure", "legal_voice.banned_words",
    "hard_nos", "rhythm", "memory.tools_that_survived", "triad_mode",
    # Salieron del cuestionario el 2026-08-25 (recorte de arriba) y se siguen imprimiendo:
    # el perfil de un despacho que ya los contestó no puede empobrecerse por un recorte
    # posterior, y «Revisar mi perfil» tiene que poder volver a guardarlos sin un 422.
    "identity.location", "terminado",
})

# Campos del cuestionario ORIGINAL de 19 preguntas (anterior a los recortes del
# 2026-07-06/09) que HOY ya no se renderizan. Se reconocen igual —y se conservan en el
# archivo de respuestas— porque hay despachos configurados de verdad que los traen: sin
# esto, reabrir "Revisar mi perfil" y volver a guardar devolvía 422 y dejaba al abogado
# encerrado fuera de su propio perfil (hallazgo BLOQUEANTE-1, 2026-07-20). Reconocer no es
# renderizar: el dato se guarda y no se imprime, que es la degradación limpia acordada.
LEGACY_STORED_FIELDS: frozenset[str] = frozenset({
    "jurisdiction.courts", "jurisdiction.key_courts",
    "doctrinal_stance.preferred_sources", "doctrinal_stance.discarded_args",
    "doctrinal_stance.key_jurisprudence",
    "mission.headline", "mission.pillars", "mission.not_in_scope",
    "memory.decisions_made", "memory.orbit",
})

KNOWN_FIELDS: frozenset[str] = CURRENT_FIELDS | LEGACY_RENDERED_FIELDS | LEGACY_STORED_FIELDS

# Secciones que el SOUL.md PUEDE contener (solo aparecen si hay respuesta). Sirve al
# gate y a la inspección; ya NO es un template fijo obligatorio.
SOUL_SECTIONS: tuple[str, ...] = (
    "## identity", "## jurisdiction", "## autonomia", "## nunca", "## terminado",
    "## aprendido",
    # legacy: solo aparecen si un responses.json viejo todavía los trae
    "## legal_voice", "## hard_nos", "## rhythm", "## tools", "## triad_mode",
)

# Referencia informativa del formato (ya no se "rellena": se construye omitiendo lo
# vacío). Se conserva por compatibilidad de import.
SOUL_TEMPLATE = (
    "# SOUL.md — <despacho>\n## identity\n## jurisdiction\n## legal_voice\n"
    "## hard_nos\n## rhythm\n## tools\n## triad_mode\n"
)


def _today() -> datetime:
    return datetime.now()


def _safe_tenant(tenant_id: str) -> str:
    """Sanea el tenant_id para usarlo como nombre de archivo (igual que TraceCapture)."""
    s = re.sub(r"[^A-Za-z0-9_-]", "_", str(tenant_id))
    return s or "tenant"


# ── Helpers de archivo (puros: config + stdlib, sin LLM) ────────────────────

def soul_path(tenant_id: str) -> Path:
    """Ruta del SOUL.md del tenant: $MIA_HOME/soul_{tenant_id}.md.

    Lee config.MIA_HOME en cada llamada (no se captura al importar) para que los tests
    puedan apuntarlo a un tempdir reasignando config.MIA_HOME."""
    return Path(config.MIA_HOME) / f"soul_{_safe_tenant(tenant_id)}.md"


def load_soul_text(tenant_id: str) -> Optional[str]:
    """Contenido del SOUL.md del tenant, o None si no existe / está vacío."""
    p = soul_path(tenant_id)
    if not p.exists():
        return None
    text = p.read_text(encoding="utf-8").strip()
    return text or None


def load_soul_snapshot(tenant_id: str) -> Optional[dict]:
    """Snapshot frozen del SOUL.md para `MatterState.soul_snapshot` (Módulo 5).

    Devuelve {"content": <texto>, "path": <str>} o None si el despacho aún no tiene
    SOUL.md (onboarding no completado) → el grafo no antepone identidad (no bloquea)."""
    text = load_soul_text(tenant_id)
    if not text:
        return None
    return {"content": text, "path": str(soul_path(tenant_id))}


def soul_status(tenant_id: str) -> dict:
    """Estado del onboarding: {completed: bool, last_updated: iso|None}."""
    p = soul_path(tenant_id)
    if not p.exists():
        return {"completed": False, "last_updated": None}
    mtime = datetime.fromtimestamp(p.stat().st_mtime)
    return {"completed": True, "last_updated": mtime.isoformat(timespec="seconds")}


def responses_path(tenant_id: str) -> Path:
    """Ruta de las respuestas crudas guardadas (para 'Revisar mi perfil')."""
    return Path(config.MIA_HOME) / f"soul_{_safe_tenant(tenant_id)}.responses.json"


def load_responses(tenant_id: str) -> dict:
    """Respuestas guardadas de la última entrevista, o {} si no hay."""
    p = responses_path(tenant_id)
    if not p.exists():
        return {}
    try:
        data = json.loads(p.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (ValueError, OSError):
        return {}


def _write_soul(tenant_id: str, content: str) -> Path:
    p = soul_path(tenant_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8")
    return p


def _write_responses(tenant_id: str, responses: dict) -> None:
    p = responses_path(tenant_id)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(responses, ensure_ascii=False, indent=2), encoding="utf-8")


# ── Normalización de respuestas (str / list / dict → texto o lista limpia) ───

def _text(value) -> str:
    """Aplana un valor de respuesta a una línea de texto (vacío si no hay dato)."""
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    if isinstance(value, dict):
        return ", ".join(f"{k}: {str(v).strip()}" for k, v in value.items() if str(v).strip())
    return str(value).strip()


# alias público histórico
_plain = _text


def _items(value) -> list[str]:
    """Normaliza a lista de líneas no vacías (chips/tags/checkboxes o texto suelto)."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v).strip() for v in value if str(v).strip()]
    s = str(value).strip()
    return [s] if s else []


def _firm_lawyer(value) -> tuple[str, str]:
    """identity.name: {firm, lawyer} (onboarding nuevo) o string (legacy)."""
    if isinstance(value, dict):
        return str(value.get("firm", "")).strip(), str(value.get("lawyer", "")).strip()
    if isinstance(value, str):
        # legacy: "Despacho · Abogado · T.P. X" → despacho y (si viene) el RESTO como
        # abogado, preservando la T.P. u otros datos (hallazgo capa 2 MN1: no perderlos).
        parts = [p.strip() for p in re.split(r"·|\|", value) if p.strip()]
        return (parts[0] if parts else ""), (" · ".join(parts[1:]) if len(parts) > 1 else "")
    return "", ""


def _location(value) -> str:
    """identity.location: {country, city} o string → 'Ciudad, País'."""
    if isinstance(value, dict):
        city = str(value.get("city", "")).strip()
        country = str(value.get("country", "")).strip()
        return ", ".join(p for p in (city, country) if p)
    return str(value or "").strip()


def _rhythm(value) -> tuple[str, str]:
    """rhythm: {no_meetings:[...], hours:""} o string → (deep_work, dias_sin_reuniones)."""
    if isinstance(value, dict):
        deep = str(value.get("hours", "")).strip()
        days = ", ".join(str(d).strip() for d in value.get("no_meetings", []) if str(d).strip())
        return deep, days
    return str(value or "").strip(), ""


def _triad(value) -> tuple[bool, str]:
    """triad_mode: {enabled, trigger} o string → (enabled, trigger)."""
    if isinstance(value, dict):
        return bool(value.get("enabled")), str(value.get("trigger", "")).strip()
    s = str(value or "").strip()
    on = s.lower().startswith(("si", "sí", "true", "yes")) if s else False
    # legacy string "Sí — para arbitrajes": el trigger es lo que sigue al "sí" (MN4).
    trigger = re.sub(r"^\s*(sí|si|yes|true)\b[\s,.:;—-]*", "", s, flags=re.IGNORECASE).strip() if on else s
    return on, trigger


# ── Generación DETERMINISTA del SOUL.md (omite lo vacío; sin corchetes) ──────

def _section(header: str, lines: list[str]) -> str:
    """Devuelve la sección con su encabezado SOLO si trae al menos una línea."""
    real = [ln for ln in lines if ln]
    if not real:
        return ""
    return header + "\n" + "\n".join(real) + "\n"


def build_soul(responses: dict, *, dates: Optional[tuple[str, str]] = None) -> str:
    """Construye el SOUL.md desde las respuestas, OMITIENDO todo campo/sección sin
    dato. Determinista (sin LLM), sin invención, sin placeholders entre corchetes."""
    r = responses or {}
    gen_date, review_date = dates or _dates_now()

    firm, lawyer = _firm_lawyer(r.get("identity.name"))
    voice = _text(r.get("identity.voice"))
    channels = _text(r.get("identity.channels"))
    location = _location(r.get("identity.location"))

    base = _text(r.get("jurisdiction.base"))
    areas = _text(r.get("jurisdiction.practice_areas"))
    client = _text(r.get("jurisdiction.client_type"))

    # Criterio (rediseño 2026-07-20): lo que hace computable el juicio del despacho.
    reviso = _items(r.get("autonomia.reviso_siempre"))
    decide = _items(r.get("autonomia.decide_solo"))
    nunca = _items(r.get("nunca"))
    terminado = _text(r.get("terminado"))
    # `aprendido`: lo escribe Mia desde el trabajo real (no se pregunta). Cada línea llega
    # ya redactada con su marca [inferido], su fecha y su fuente — aquí solo se imprime.
    aprendido = _items(r.get("aprendido"))

    structure = _text(r.get("legal_voice.structure"))
    banned = _text(r.get("legal_voice.banned_words"))
    hard_nos = _items(r.get("hard_nos"))

    deep_work, no_meetings = _rhythm(r.get("rhythm"))
    tools = _items(r.get("memory.tools_that_survived"))
    triad_on, triad_trigger = _triad(r.get("triad_mode"))

    def line(label: str, value: str) -> str:
        return f"- {label}: {value}" if value else ""

    header = (f"# SOUL.md — {firm or 'Despacho'}\n"
              f"# Generado: {gen_date} · Próxima revisión: {review_date}\n")

    parts = [
        header,
        _section("## identity", [
            line("name", firm), line("lawyer", lawyer),
            line("location", location), line("channels", channels), line("voice", voice)]),
        _section("## jurisdiction", [
            line("base", base), line("practice_areas", areas), line("client_type", client)]),
        _section("## autonomia", [
            line("reviso_siempre", ", ".join(reviso)),
            line("decide_solo", ", ".join(decide))]),
        _section("## nunca", [f"- {n}" for n in nunca]),
        _section("## terminado", [f"- {terminado}" if terminado else ""]),
        # ── legacy: solo si un responses.json viejo todavía trae estos campos ──
        _section("## legal_voice", [
            line("structure", structure), line("banned_words", banned)]),
        _section("## hard_nos", [f"- {h}" for h in hard_nos]),
        _section("## rhythm", [
            line("deep_work", deep_work), line("no_meetings", no_meetings)]),
        _section("## tools", [f"- {t}" for t in tools]),
        # triad_mode solo aparece si el despacho lo activó (opt-in)
        _section("## triad_mode", [
            "- enabled: true", line("trigger", triad_trigger)]) if triad_on else "",
        # Va al final: es lo que crece con el uso, debajo de lo que el abogado declaró.
        _section("## aprendido", [f"- {a}" for a in aprendido]),
    ]
    return "\n".join(p for p in parts if p).rstrip() + "\n"


def build_summary(responses: dict) -> str:
    """Resumen en LENGUAJE LLANO de lo que Mia entendió del despacho — lo que ve el
    abogado al terminar el onboarding (el SOUL.md técnico queda por debajo). Markdown
    simple; solo incluye los datos que el abogado respondió."""
    r = responses or {}
    firm, lawyer = _firm_lawyer(r.get("identity.name"))
    location = _location(r.get("identity.location"))
    voice = _text(r.get("identity.voice"))
    base = _text(r.get("jurisdiction.base"))
    areas = _text(r.get("jurisdiction.practice_areas"))
    client = _text(r.get("jurisdiction.client_type"))
    reviso = _items(r.get("autonomia.reviso_siempre"))
    decide = _items(r.get("autonomia.decide_solo"))
    nunca = _items(r.get("nunca"))
    terminado = _text(r.get("terminado"))
    aprendido = _items(r.get("aprendido"))
    structure = _text(r.get("legal_voice.structure"))
    banned = _text(r.get("legal_voice.banned_words"))
    hard_nos = _items(r.get("hard_nos"))
    deep_work, no_meetings = _rhythm(r.get("rhythm"))
    tools = _items(r.get("memory.tools_that_survived"))

    despacho = " — ".join(p for p in (firm, lawyer) if p)
    ritmo_bits = []
    if deep_work:
        ritmo_bits.append(f"trabajo profundo {deep_work}")
    if no_meetings:
        ritmo_bits.append(f"sin reuniones {no_meetings}")

    bullets = [
        ("Despacho", despacho),
        ("Dónde trabajas", location),
        ("Jurisdicción", base),
        ("Áreas de práctica", areas),
        ("A quién defiendes", client),
        ("Lo que reviso siempre contigo", ", ".join(reviso)),
        ("Lo que resuelvo sin preguntarte", ", ".join(decide)),
        ("Un escrito está listo cuando", terminado),
        # legacy: solo aparecen si el perfil viene de una entrevista anterior
        ("Estilo de escritura", voice),
        ("Estructura de tus escritos", structure),
        ("Palabras que evitas", banned),
        ("Herramientas que conozco", ", ".join(tools)),
        ("Tu ritmo", "; ".join(ritmo_bits)),
    ]
    lines = ["### Así entendí a tu despacho", ""]
    for label, value in bullets:
        if value:
            lines.append(f"- **{label}:** {value}")
    # Las líneas rojas van en su propia lista: son prohibiciones, no un dato más.
    for titulo, reglas in (("Lo que nunca debo hacer", nunca),
                           ("Reglas que nunca debo romper", hard_nos)):
        if reglas:
            lines.append(f"- **{titulo}:**")
            lines.extend(f"  - {x}" for x in reglas)
    if aprendido:
        lines.append("- **Lo que he ido aprendiendo de tu trabajo:**")
        lines.extend(f"  - {a}" for a in aprendido)
    lines.append("")
    lines.append(
        "Tu estilo de redacción no te lo pregunto: Mia lo aprende de tus propios escritos "
        "y de las correcciones que hagas a sus borradores."
    )
    lines.append("")
    lines.append("Puedes ajustar cualquiera de estos datos cuando quieras desde “Mi despacho”.")
    return "\n".join(lines)


def derive_firm_profile(responses: dict) -> dict:
    """Deriva el subconjunto de `firm_profiles` (Fase 3, tabla estructurada) A PARTIR de las
    respuestas de la entrevista — la fuente canónica sigue siendo el archivo de respuestas
    en disco (C2, decisión de Pipe: `firm_profiles` pasa a ser DERIVADO, no fuente).

    Pura y determinista (misma entrada → misma salida). Mapea SOLO los campos derivables:
    `name`/`lawyer_name` (identity.name), `jurisdiction` (jurisdiction.base),
    `practice_areas` (jurisdiction.practice_areas) y `tools` (memory.tools_that_survived).
    Omite toda clave sin valor — NUNCA pisa con '' o [] (el llamador hace merge encima de
    lo que ya había en `firm_profiles`). NO deriva ni toca `tp_number`, `preferred_sources`,
    `voice_adjectives`, `banned_words`, `hard_nos` ni `rhythm` (extras/legacy, fuera del
    cuestionario actual — los edita el abogado aparte, como "extras")."""
    r = responses or {}
    out: dict = {}

    firm, lawyer = _firm_lawyer(r.get("identity.name"))
    if firm:
        out["name"] = firm
    if lawyer:
        out["lawyer_name"] = lawyer

    base = _text(r.get("jurisdiction.base"))
    if base:
        out["jurisdiction"] = base

    # practice_areas: si viene string (respuesta legacy en texto libre), se separa por
    # comas ("Civil, comercial, laboral" -> 3 áreas); si viene lista, tal cual.
    raw_areas = r.get("jurisdiction.practice_areas")
    if isinstance(raw_areas, list):
        areas = [str(a).strip() for a in raw_areas if str(a).strip()]
    else:
        areas = [a.strip() for a in _text(raw_areas).split(",") if a.strip()]
    if areas:
        out["practice_areas"] = areas

    tools = _items(r.get("memory.tools_that_survived"))
    if tools:
        out["tools"] = tools

    return out


def firm_name(responses: dict) -> str:
    """Nombre del despacho tal como quedaría en el SOUL.md ('' si no vino).

    Es el único dato que Mia no puede inferir ni omitir: encabeza el archivo y va impreso
    en cada escrito. El endpoint lo exige explícitamente en vez de deducirlo de que exista
    la sección `## identity` — esa sección aparece con CUALQUIER dato de identidad (una
    ciudad, un canal), así que el guardián decía exigir el nombre y no lo exigía
    (hallazgo MAYOR-3, 2026-07-20). Tolera la forma legacy (string 'Despacho · Abogado')
    y la nueva ({firm, lawyer})."""
    return _firm_lawyer((responses or {}).get("identity.name"))[0]


def validate_soul(content: str) -> list[str]:
    """Defectos del SOUL.md generado. En el diseño DETERMINISTA los placeholders de
    plantilla son imposibles por construcción (build_soul omite lo vacío, jamás
    imprime corchetes), así que la única comprobación real es que exista la sección de
    identidad. Devuelve [] si el SOUL está bien formado.

    Nota (hallazgo capa 2 B1): NO se cazan corchetes en el texto — un abogado puede
    escribir un corchete legítimo en su respuesta (p. ej. 'No usar [sic]') y ese dato
    real no debe marcarse como defecto ni tumbar nada."""
    return [] if "## identity" in (content or "") else ["## identity"]


def _dates_now() -> tuple[str, str]:
    today = _today()
    review = today + timedelta(days=90)
    return today.strftime("%Y-%m-%d"), review.strftime("%Y-%m-%d")


# ── La entrevista ───────────────────────────────────────────────────────────

class SoulInterview:
    """Conduce el onboarding del SOUL.md y mantiene el archivo por tenant."""

    async def get_questions(self) -> list[dict]:
        """Las preguntas (con id/block/field/question/example) para el frontend."""
        return [dict(q) for q in QUESTIONS]

    async def run_interview(self, tenant_id: str, responses: dict) -> str:
        """Genera el SOUL.md desde las respuestas (determinista, sin corchetes), lo
        guarda y lo devuelve. Persiste también las respuestas crudas para 'Revisar mi
        perfil' / la revisión trimestral."""
        content = build_soul(responses)
        _write_soul(tenant_id, content)
        _write_responses(tenant_id, responses)
        return content

    async def update_soul(self, tenant_id: str, updates: dict) -> str:
        """Actualiza el SOUL.md fusionando las respuestas previas con los cambios y
        reconstruyéndolo (determinista). Si no hay perfil previo, equivale a una
        entrevista nueva con esos campos.

        Nota (capa 2 MN2): la reconstrucción usa SOLO los campos que hoy pregunta el
        onboarding; un `responses.json` viejo con campos ya removidos (objetivo/pilares,
        cortes) no los reimprime — es la consecuencia deliberada de haber simplificado."""
        merged = {**load_responses(tenant_id), **(updates or {})}
        content = build_soul(merged)
        _write_soul(tenant_id, content)
        _write_responses(tenant_id, merged)
        return content

    def generate_without_llm(self, responses: dict) -> str:
        """Alias histórico: la generación SIEMPRE es determinista ahora."""
        return build_soul(responses)

    def save_fallback(self, tenant_id: str, responses: dict) -> str:
        """Genera el SOUL.md (determinista), lo guarda y persiste las respuestas."""
        content = build_soul(responses)
        _write_soul(tenant_id, content)
        _write_responses(tenant_id, responses)
        return content

    def summary(self, responses: dict) -> str:
        """Resumen en lenguaje llano para mostrar al abogado."""
        return build_summary(responses)

    def _dates(self) -> tuple[str, str]:
        return _dates_now()
