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
     "question": "¿Cuál es el nombre completo de tu despacho y tu nombre como abogado principal?",
     "example": "Fajardo & Asociados · María Fajardo"},
    {"id": "p2", "block": "identity", "field": "identity.location",
     "question": "¿En qué ciudad y país operas principalmente?",
     # El ejemplo enseña el FORMATO, no una plaza: MIA no es de ningún país.
     "example": "Ciudad, País"},
    {"id": "p3", "block": "identity", "field": "identity.voice",
     "question": "¿Cómo describirías en 3 adjetivos el estilo de escritura de tu despacho?",
     "example": "Técnico, argumentativo, conciso"},
    {"id": "p4", "block": "identity", "field": "identity.channels",
     "question": "¿Tienes sitio web o canales públicos del despacho?",
     "example": "fajardoasociados.co — LinkedIn Fajardo & Asociados"},
    # Bloque 2 — Jurisdicción. NOTA (consolidación 2026-07-09, decisión de Pipe): la
    # pregunta descriptiva de país (antes p5, field jurisdiction.base) ya NO se hace —
    # el frontend tiene UN solo selector múltiple de países (el mismo del enrutamiento
    # de paquetes jurídicos) y auto-llena `jurisdiction.base` con los países elegidos
    # al completar. build_soul/build_summary siguen renderizando ese campo.
    {"id": "p6", "block": "jurisdiction", "field": "jurisdiction.practice_areas",
     "question": "¿Cuáles son las ramas del derecho en que te especializas?",
     "example": "Civil, comercial, laboral, seguros"},
    {"id": "p7", "block": "jurisdiction", "field": "jurisdiction.client_type",
     "question": "¿Qué tipo de cliente defiende principalmente tu despacho?",
     "example": "Aseguradoras (HDI, Zurich, SURA, Seguros del Estado)"},
    # Bloque 3 — Herramientas
    {"id": "p18", "block": "tools", "field": "memory.tools_that_survived",
     "question": "¿Hay herramientas que usas a diario que Mia debe conocer?",
     "example": "Correo, gestor documental, calendario, mensajería."},
    # Bloque 4 — Modo profundo (opcional; el frontend puede ocultarlo hasta implementarse)
    {"id": "p19", "block": "triad_mode", "field": "triad_mode",
     "question": "¿Quieres habilitar el modo de análisis profundo para asuntos de alta "
                 "complejidad? Tres modelos distintos en ciclo cerrado: más tiempo y costo, "
                 "mayor calidad.",
     "example": "Sí — casos de alta cuantía y arbitrajes"},
]

# Orden canónico de los bloques (para el progreso del frontend).
BLOCKS: tuple[str, ...] = ("identity", "jurisdiction", "tools", "triad_mode")

# Secciones que el SOUL.md PUEDE contener (solo aparecen si hay respuesta). Sirve al
# gate y a la inspección; ya NO es un template fijo obligatorio.
SOUL_SECTIONS: tuple[str, ...] = (
    "## identity", "## jurisdiction", "## legal_voice", "## hard_nos",
    "## rhythm", "## tools", "## triad_mode",
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
        _section("## legal_voice", [
            line("structure", structure), line("banned_words", banned)]),
        _section("## hard_nos", [f"- {h}" for h in hard_nos]),
        _section("## rhythm", [
            line("deep_work", deep_work), line("no_meetings", no_meetings)]),
        _section("## tools", [f"- {t}" for t in tools]),
        # triad_mode solo aparece si el despacho lo activó (opt-in)
        _section("## triad_mode", [
            "- enabled: true", line("trigger", triad_trigger)]) if triad_on else "",
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
        ("Tipo de cliente", client),
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
    if hard_nos:
        lines.append("- **Reglas que nunca debo romper:**")
        lines.extend(f"  - {h}" for h in hard_nos)
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
