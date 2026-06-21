"""Mia · onboarding.soul_interview — la entrevista que construye el SOUL.md (Módulo 5).

El SOUL.md es la capa MÁS importante del sistema de prompts: la capa 1
(identidad) que el prompt_builder antepone a todo (1b) y que el grafo carga como
`soul_snapshot` al iniciar cada turno (Módulo 5). La entrevista lo arma de forma
conversacional: 15 preguntas en 5 bloques → respuestas → call_llm(task="soul")
genera el SOUL.md en el template de 9 secciones → se guarda en
$MIA_HOME/soul_{tenant_id}.md.

El template y los ejemplos provienen del Doc 4 (SOUL.md Onboarding) — son la fuente
exacta, no se inventan. Originalmente eran 19 preguntas; se suprimieron 4 que el
agente aprende del uso (P8/P9 tribunales y cortes, P12/P13 argumentos y fuentes →
GEPA/uso). La última (triad_mode) es opcional. Los campos del template que esas
preguntas alimentaban quedan como placeholder hasta que emergen con el uso.

Helpers de archivo (soul_path / load_soul_text / load_soul_snapshot / soul_status):
puros (solo config + stdlib, sin LLM) para que `agents/state.py` y `agent/core.py`
los importen sin arrastrar el cliente LLM. La llamada al LLM (run_interview /
update_soul) importa `agent.llm` de forma diferida.
"""
from __future__ import annotations

import asyncio
import json
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from .. import config

# ── Las 15 preguntas del onboarding (5 bloques; del Doc 4, menos P8/P9/P12/P13) ──
# Cada pregunta: id · block · field (sección/campo del template que alimenta) ·
# question (lo que ve el abogado) · example (el ejemplo del Doc 4). Las respuestas
# del frontend llegan como {field: respuesta}; el campo es la llave.
QUESTIONS: list[dict] = [
    # Bloque 1 — Identidad (P1-P4)
    {"id": "p1", "block": "identity", "field": "identity.name",
     "question": "¿Cuál es el nombre completo de tu despacho y tu nombre como abogado principal?",
     "example": "Lexia Abogados S.A.S. · Juan Felipe Torres · T.P. 227.698"},
    {"id": "p2", "block": "identity", "field": "identity.location",
     "question": "¿En qué ciudad y país operas principalmente?",
     "example": "Bogotá, Colombia — UTC-5"},
    {"id": "p3", "block": "identity", "field": "identity.voice",
     "question": "¿Cómo describirías en 3 adjetivos el estilo de escritura de tu despacho?",
     "example": "Técnico, argumentativo, conciso"},
    {"id": "p4", "block": "identity", "field": "identity.channels",
     "question": "¿Tienes sitio web o canales públicos del despacho?",
     "example": "lexia.co — LinkedIn Lexia Abogados"},
    # Bloque 2 — Jurisdicción (P5-P7)
    {"id": "p5", "block": "jurisdiction", "field": "jurisdiction.base",
     "question": "¿En qué jurisdicción trabajas principalmente?",
     "example": "Colombia — también España ocasionalmente"},
    {"id": "p6", "block": "jurisdiction", "field": "jurisdiction.practice_areas",
     "question": "¿Cuáles son las ramas del derecho en que te especializas?",
     "example": "Seguros, responsabilidad fiscal, contencioso-administrativo, contratos públicos"},
    {"id": "p7", "block": "jurisdiction", "field": "jurisdiction.client_type",
     "question": "¿Qué tipo de cliente defiende principalmente tu despacho?",
     "example": "Aseguradoras (HDI, Zurich, SURA, Seguros del Estado)"},
    # P8 (instancias/tribunales) y P9 (cortes que más cita) suprimidas: el agente las
    # aprende del uso (asuntos aprobados, documentos), no del onboarding.
    # Bloque 3 — Voz jurídica (P10, P11, P14)
    {"id": "p10", "block": "legal_voice", "field": "legal_voice.structure",
     "question": "¿Cómo estructuras típicamente tus escritos?",
     "example": "Párrafos narrativos continuos. Sin viñetas en escritos de fondo."},
    {"id": "p11", "block": "legal_voice", "field": "legal_voice.banned_words",
     "question": "¿Hay palabras o expresiones que nunca usas?",
     "example": "Sin latinismos. Sin 'insalvable'. Sin 'en ese orden de ideas'."},
    # P12 (argumentos que no funcionaron) la detecta GEPA; P13 (jurisprudencia preferida)
    # emerge con el uso. Ambas suprimidas del onboarding.
    {"id": "p14", "block": "legal_voice", "field": "hard_nos",
     "question": "¿Qué cosas Mia nunca debe hacer en tu nombre?",
     "example": "Nunca presentar borrador sin revisión. Nunca recomendar allanarse sin análisis."},
    # Bloque 4 — Misión y ritmo (P15-P18)
    {"id": "p15", "block": "mission_rhythm", "field": "mission.headline",
     "question": "¿Cuál es tu objetivo más importante para este año, en una oración?",
     "example": "Consolidar Lexia Intelligence como el primer agente legal cognitivo de LatAm "
                "con 3+ despachos externos de pago."},
    {"id": "p16", "block": "mission_rhythm", "field": "mission.pillars",
     "question": "¿Cuáles son los 3 pilares que sostienen ese objetivo?",
     "example": "1. Excelencia litigios seguros. 2. Construcción de Mia. 3. Primer cliente externo."},
    {"id": "p17", "block": "mission_rhythm", "field": "rhythm",
     "question": "¿Cuándo trabajas mejor? ¿Tienes días sin reuniones?",
     "example": "Mañanas 7am-12pm trabajo profundo. Sin reuniones lunes ni viernes."},
    {"id": "p18", "block": "mission_rhythm", "field": "memory.tools_that_survived",
     "question": "¿Hay herramientas que usas a diario que Mia debe conocer?",
     "example": "Obsidian, Claude Code, Linear, WhatsApp Business."},
    # Bloque 5 — Triad mode (P19, opcional)
    {"id": "p19", "block": "triad_mode", "field": "triad_mode",
     "question": "¿Quieres habilitar el modo de análisis profundo para matters de alta "
                 "complejidad? Tres modelos distintos en ciclo cerrado: más tiempo y costo, "
                 "mayor calidad.",
     "example": "Sí — imputaciones fiscales >$1.000M COP y arbitrajes"},
]

# Orden canónico de los 5 bloques (para el progreso del frontend).
BLOCKS: tuple[str, ...] = ("identity", "jurisdiction", "legal_voice", "mission_rhythm", "triad_mode")

# ── Template del SOUL.md — 9 secciones EXACTAS del Doc 4 ─────────────────────
# Es el esqueleto que el LLM rellena con las respuestas. Los campos sin respuesta
# se conservan como placeholders entre corchetes (no se inventan datos).
SOUL_TEMPLATE = """# SOUL.md — [NOMBRE DEL DESPACHO]
# Generado: [FECHA] · Próxima revisión: [FECHA + 3 meses]

## identity
- name: [NOMBRE DESPACHO]
- lawyer: [NOMBRE] · T.P. [NÚMERO]
- location: [CIUDAD, PAÍS] · [TIMEZONE]
- channels: [WEB, LINKEDIN, etc.]
- voice: [3 ADJETIVOS DE ESTILO]

## jurisdiction
- base: [COLOMBIA / ESPAÑA / MÉXICO / ARGENTINA / PERÚ / CHILE]
- practice_areas: [SEGUROS, FISCAL, CIVIL, PENAL, LABORAL, etc.]
- client_type: [ASEGURADORAS / EMPRESAS / PERSONAS / SECTOR PÚBLICO]
- courts: [CONSEJO DE ESTADO, CORTE CONSTITUCIONAL, CSJ, ARBITRAJE]
- process_types: [CONTENCIOSO-ADM, ORDINARIO, FISCAL, PASC, ARBITRAL]

## mission
- headline: [UNA ORACIÓN. Si se logra este año, el año fue exitoso.]
- pillars:
  - [PILAR 1]
  - [PILAR 2]
  - [PILAR 3]
- not_in_scope: [LO QUE NO HACEMOS ESTE AÑO]

## legal_voice
- register: [FORMAL-TÉCNICO / CONCISO / ARGUMENTATIVO]
- structure: [PÁRRAFOS CONTINUOS — sin viñetas en escritos de fondo]
- banned_words: [SIN LATINISMOS. SIN "insalvable". SIN "en ese orden de ideas"]
- argument_style: [DEDUCTIVO DESDE NORMA / DESDE HECHOS / DESDE JURISPRUDENCIA]

## hard_nos
- [NUNCA citar sentencias no verificadas en el corpus]
- [NUNCA recomendar allanarse sin análisis de riesgo previo]
- [NUNCA usar latinismos en escritos procesales]
- [NUNCA presentar como final un escrito sin HITL]

## doctrinal_stance
- preferred_sources: [CONSEJO DE ESTADO ANTES QUE DOCTRINA FORÁNEA]
- key_jurisprudence:
  - [T-323/2024 — IA en la Rama Judicial]
  - [SC1983-2025 — seguros cumplimiento]
- discarded_args: [ARGS QUE PROBAMOS Y NO FUNCIONARON]

## memory
- decisions_made:
  - "[INTENTÉ X, no funcionó porque Y. No sugerir.]"
- orbit:
  - "[NOMBRE]: [ROL] · [ÚLTIMA INTERACCIÓN] · [QUÉ SE LE DEBE]"
- tools_that_survived: [OBSIDIAN · CLAUDE CODE · LINEAR · WHATSAPP BUSINESS]

## rhythm
- deep_work: [07:00–12:00]
- no_meetings: [LUNES Y VIERNES]
- weekend: [SOLO URGENCIAS REALES]
- energy_curve: [MAÑANA: producción jurídica. TARDE: reuniones. NOCHE: lectura]

## triad_mode
- enabled: [true / false]
- trigger: [IMPUTACIÓN >$1.000M COP / ARBITRAJES / SEGÚN CRITERIO]
"""

# Las 9 secciones (para validación/inspección y para el gate E2E).
SOUL_SECTIONS: tuple[str, ...] = (
    "## identity", "## jurisdiction", "## mission", "## legal_voice", "## hard_nos",
    "## doctrinal_stance", "## memory", "## rhythm", "## triad_mode",
)

# Modelo de la tarea (decisión: sonnet — la identidad del agente es importante).
SOUL_TASK = "soul"

_GEN_SYSTEM = (
    "Eres un asistente que redacta el archivo SOUL.md de un despacho de abogados del "
    "Civil Law hispanoamericano. El SOUL.md define la identidad, la voz y los límites "
    "del agente legal. Recibes (a) un TEMPLATE con 9 secciones y (b) las RESPUESTAS del "
    "abogado a la entrevista de onboarding. Tu tarea: rellenar el template con las "
    "respuestas, respetando EXACTAMENTE los encabezados de sección (## identity, "
    "## jurisdiction, ## mission, ## legal_voice, ## hard_nos, ## doctrinal_stance, "
    "## memory, ## rhythm, ## triad_mode) y el formato de viñetas. Reglas: "
    "(1) Usa SOLO la información de las respuestas; no inventes datos jurídicos, "
    "nombres, normas ni sentencias. "
    "(2) Si una respuesta no cubre un campo, CONSERVA el placeholder original entre "
    "corchetes — no lo borres ni lo inventes. "
    "(3) Mantén el encabezado del archivo con la fecha de generación y la próxima "
    "revisión que se te indican. "
    "(4) Devuelve ÚNICAMENTE el contenido del SOUL.md en Markdown, sin comentarios."
)


def _today() -> datetime:
    return datetime.now()


def _safe_tenant(tenant_id: str) -> str:
    """Sanea el tenant_id para usarlo como nombre de archivo (mismo criterio que TraceCapture)."""
    s = re.sub(r"[^A-Za-z0-9_-]", "_", str(tenant_id))
    return s or "tenant"


# ── Helpers de archivo (puros: config + stdlib, sin LLM) ────────────────────

def soul_path(tenant_id: str) -> Path:
    """Ruta del SOUL.md del tenant: $MIA_HOME/soul_{tenant_id}.md.

    Lee config.MIA_HOME en cada llamada (no se captura al importar) para que los tests
    puedan apuntarlo a un tempdir reasignando config.MIA_HOME.
    """
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
    SOUL.md (onboarding no completado) → el grafo no antepone identidad (no bloquea).
    """
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


def _render_responses(responses: dict) -> str:
    """Mapea field → respuesta a un bloque legible para el prompt de generación."""
    by_field = {q["field"]: q for q in QUESTIONS}
    lines = []
    for field, answer in responses.items():
        if answer is None or str(answer).strip() == "":
            continue
        label = by_field.get(field, {}).get("question", field)
        lines.append(f"- [{field}] {label}\n  → {str(answer).strip()}")
    return "\n".join(lines) or "(el abogado no respondió ninguna pregunta)"


def _plain(value) -> str:
    """Renderiza un valor de respuesta (str / list / dict) a texto plano legible.

    El frontend envía strings, listas (chips/tags/checkboxes) y dicts
    ({firm,lawyer} / {country,city} / {pillars} / {no_meetings,hours} /
    {enabled,trigger}). Aquí se aplanan a una línea para el SOUL.md sin LLM.
    """
    if value is None:
        return ""
    if isinstance(value, list):
        return ", ".join(str(v).strip() for v in value if str(v).strip())
    if isinstance(value, dict):
        return ", ".join(f"{k}: {str(v).strip()}" for k, v in value.items() if str(v).strip())
    return str(value).strip()


# ── La entrevista ───────────────────────────────────────────────────────────

class SoulInterview:
    """Conduce el onboarding del SOUL.md y mantiene el archivo por tenant."""

    async def get_questions(self) -> list[dict]:
        """Las 15 preguntas (con id/block/field/question/example) para el frontend."""
        return [dict(q) for q in QUESTIONS]

    async def run_interview(self, tenant_id: str, responses: dict) -> str:
        """Genera el SOUL.md a partir de las respuestas, lo guarda y lo devuelve.

        `responses` es {field: respuesta del abogado}. Usa call_llm(task="soul") para
        rellenar el template de 9 secciones; los campos sin respuesta quedan como
        placeholder. Escribe en $MIA_HOME/soul_{tenant_id}.md.
        """
        content = await self._generate(self._build_messages(responses))
        _write_soul(tenant_id, content)
        _write_responses(tenant_id, responses)   # para 'Revisar mi perfil' / revisión trimestral
        return content

    async def update_soul(self, tenant_id: str, updates: dict) -> str:
        """Actualiza campos puntuales del SOUL.md existente (revisión trimestral).

        `updates` es {field: nuevo valor}. Reescribe el SOUL.md aplicando los cambios
        sobre el contenido actual, conservando lo demás. Si no hay SOUL.md previo,
        equivale a una entrevista nueva con esos campos.
        """
        current = load_soul_text(tenant_id)
        if not current:
            return await self.run_interview(tenant_id, updates)
        messages = [
            {"role": "system", "content": _GEN_SYSTEM},
            {"role": "user", "content": (
                "Actualiza el siguiente SOUL.md aplicando SOLO los cambios indicados y "
                "conservando intacto todo lo demás (incluida la sección no afectada). "
                "Mantén los 9 encabezados de sección.\n\n"
                f"Fecha de revisión: {self._dates()[0]} · Próxima revisión: {self._dates()[1]}\n\n"
                f"=== SOUL.md actual ===\n{current}\n\n"
                f"=== Cambios a aplicar (field → nuevo valor) ===\n{_render_responses(updates)}\n\n"
                "Devuelve el SOUL.md completo y actualizado."
            )},
        ]
        content = await self._generate(messages)
        _write_soul(tenant_id, content)
        merged = {**load_responses(tenant_id), **updates}   # respuestas previas + cambios
        _write_responses(tenant_id, merged)
        return content

    # ── Fallback sin LLM (timeout / fallo del gateway) ───────────────────────
    def generate_without_llm(self, responses: dict) -> str:
        """Construye el SOUL.md directamente desde las respuestas, SIN llamar al LLM.

        Fallback determinista para cuando call_llm(task='soul') hace timeout o falla.
        Mapea cada respuesta a su campo del template de 9 secciones; los campos sin
        respuesta quedan como placeholder entre corchetes (no se inventan datos). El
        abogado puede refinar este perfil base luego desde la pantalla 'Mi despacho'.
        """
        r = responses or {}
        gen_date, review_date = self._dates()

        # identity.name: {firm, lawyer} (onboarding nuevo) o string (legacy).
        name = r.get("identity.name")
        firm = lawyer = ""
        if isinstance(name, dict):
            firm = str(name.get("firm", "")).strip()
            lawyer = str(name.get("lawyer", "")).strip()
        elif isinstance(name, str):
            firm = name.strip()

        # identity.location: {country, city} o string.
        loc = r.get("identity.location")
        country = city = ""
        if isinstance(loc, dict):
            country = str(loc.get("country", "")).strip()
            city = str(loc.get("city", "")).strip()
        elif isinstance(loc, str):
            country = loc.strip()
        location = ", ".join(p for p in (city, country) if p)

        # mission.pillars: {pillars:[...]} | list | string.
        pillars_val = r.get("mission.pillars")
        if isinstance(pillars_val, dict):
            pillars = [str(p).strip() for p in pillars_val.get("pillars", []) if str(p).strip()]
        elif isinstance(pillars_val, list):
            pillars = [str(p).strip() for p in pillars_val if str(p).strip()]
        elif isinstance(pillars_val, str) and pillars_val.strip():
            pillars = [pillars_val.strip()]
        else:
            pillars = []

        # rhythm: {no_meetings:[...], hours:""} | string.
        rhythm_val = r.get("rhythm")
        deep_work = no_meetings = ""
        if isinstance(rhythm_val, dict):
            deep_work = str(rhythm_val.get("hours", "")).strip()
            no_meetings = ", ".join(str(d).strip() for d in rhythm_val.get("no_meetings", []) if str(d).strip())
        elif isinstance(rhythm_val, str):
            deep_work = rhythm_val.strip()

        # triad_mode: {enabled, trigger} | string.
        triad_val = r.get("triad_mode")
        triad_enabled, triad_trigger = "false", ""
        if isinstance(triad_val, dict):
            triad_enabled = "true" if triad_val.get("enabled") else "false"
            triad_trigger = str(triad_val.get("trigger", "")).strip()
        elif isinstance(triad_val, str) and triad_val.strip():
            triad_enabled = "true" if triad_val.strip().lower().startswith(("si", "sí", "true", "yes")) else "false"

        # hard_nos: lista de límites | string.
        hard_nos_val = r.get("hard_nos")
        if isinstance(hard_nos_val, list):
            hard_nos = [str(h).strip() for h in hard_nos_val if str(h).strip()]
        elif isinstance(hard_nos_val, str) and hard_nos_val.strip():
            hard_nos = [hard_nos_val.strip()]
        else:
            hard_nos = []

        def ph(value: str, placeholder: str) -> str:
            return value if value else placeholder

        pillars_block = "\n".join(f"  - {p}" for p in pillars) if pillars else (
            "  - [PILAR 1]\n  - [PILAR 2]\n  - [PILAR 3]"
        )
        hard_nos_block = "\n".join(f"- {h}" for h in hard_nos) if hard_nos else (
            "- [NUNCA citar sentencias no verificadas en el corpus]\n"
            "- [NUNCA recomendar allanarse sin análisis de riesgo previo]\n"
            "- [NUNCA presentar como final un escrito sin revisión]"
        )

        return f"""# SOUL.md — {ph(firm, "[NOMBRE DEL DESPACHO]")}
# Generado: {gen_date} · Próxima revisión: {review_date}
# (Perfil base sin IA: generado por timeout del modelo. Refínalo desde "Mi despacho".)

## identity
- name: {ph(firm, "[NOMBRE DESPACHO]")}
- lawyer: {ph(lawyer, "[NOMBRE] · T.P. [NÚMERO]")}
- location: {ph(location, "[CIUDAD, PAÍS] · [TIMEZONE]")}
- channels: {ph(_plain(r.get("identity.channels")), "[WEB, LINKEDIN, etc.]")}
- voice: {ph(_plain(r.get("identity.voice")), "[3 ADJETIVOS DE ESTILO]")}

## jurisdiction
- base: {ph(_plain(r.get("jurisdiction.base")), "[JURISDICCIÓN PRINCIPAL]")}
- practice_areas: {ph(_plain(r.get("jurisdiction.practice_areas")), "[ÁREAS DE PRÁCTICA]")}
- client_type: {ph(_plain(r.get("jurisdiction.client_type")), "[TIPO DE CLIENTE]")}
- courts: {ph(_plain(r.get("jurisdiction.courts")), "[INSTANCIAS Y TRIBUNALES]")}
- key_courts: {ph(_plain(r.get("jurisdiction.key_courts")), "[CORTES MÁS CITADAS]")}

## mission
- headline: {ph(_plain(r.get("mission.headline")), "[UNA ORACIÓN. Si se logra este año, el año fue exitoso.]")}
- pillars:
{pillars_block}
- not_in_scope: [LO QUE NO HACEMOS ESTE AÑO]

## legal_voice
- register: [FORMAL-TÉCNICO / CONCISO / ARGUMENTATIVO]
- structure: {ph(_plain(r.get("legal_voice.structure")), "[ESTRUCTURA DE LOS ESCRITOS]")}
- banned_words: {ph(_plain(r.get("legal_voice.banned_words")), "[PALABRAS O EXPRESIONES PROHIBIDAS]")}
- argument_style: [DEDUCTIVO DESDE NORMA / DESDE HECHOS / DESDE JURISPRUDENCIA]

## hard_nos
{hard_nos_block}

## doctrinal_stance
- preferred_sources: {ph(_plain(r.get("doctrinal_stance.preferred_sources")), "[FUENTES PREFERIDAS]")}
- key_jurisprudence:
  - [JURISPRUDENCIA CLAVE]
- discarded_args: {ph(_plain(r.get("doctrinal_stance.discarded_args")), "[ARGS QUE PROBAMOS Y NO FUNCIONARON]")}

## memory
- decisions_made:
  - "[INTENTÉ X, no funcionó porque Y. No sugerir.]"
- orbit:
  - "[NOMBRE]: [ROL] · [ÚLTIMA INTERACCIÓN] · [QUÉ SE LE DEBE]"
- tools_that_survived: {ph(_plain(r.get("memory.tools_that_survived")), "[HERRAMIENTAS DEL DÍA A DÍA]")}

## rhythm
- deep_work: {ph(deep_work, "[HORARIO DE TRABAJO PROFUNDO]")}
- no_meetings: {ph(no_meetings, "[DÍAS SIN REUNIONES]")}
- weekend: [SOLO URGENCIAS REALES]
- energy_curve: [MAÑANA: producción jurídica. TARDE: reuniones. NOCHE: lectura]

## triad_mode
- enabled: {triad_enabled}
- trigger: {ph(triad_trigger, "[CUÁNDO ACTIVARLO]")}
"""

    def save_fallback(self, tenant_id: str, responses: dict) -> str:
        """Genera el SOUL.md SIN LLM, lo guarda y persiste las respuestas; devuelve el contenido.

        Equivalente a run_interview pero por la vía determinista (sin LLM). Marca el
        onboarding como completado (escribe el archivo que soul_status detecta).
        """
        content = self.generate_without_llm(responses)
        _write_soul(tenant_id, content)
        _write_responses(tenant_id, responses)
        return content

    # ── internos ────────────────────────────────────────────────────────────
    def _dates(self) -> tuple[str, str]:
        today = _today()
        review = today + timedelta(days=90)
        return today.strftime("%Y-%m-%d"), review.strftime("%Y-%m-%d")

    def _build_messages(self, responses: dict) -> list[dict]:
        gen_date, review_date = self._dates()
        return [
            {"role": "system", "content": _GEN_SYSTEM},
            {"role": "user", "content": (
                f"Fecha de generación: {gen_date} · Próxima revisión: {review_date}\n\n"
                f"=== TEMPLATE (9 secciones, respétalas) ===\n{SOUL_TEMPLATE}\n\n"
                f"=== RESPUESTAS DE LA ENTREVISTA ===\n{_render_responses(responses)}\n\n"
                "Genera el SOUL.md final."
            )},
        ]

    async def _generate(self, messages: list[dict]) -> str:
        from ..agent import llm  # import diferido: la generación es lo único que toca el LLM
        resp = await asyncio.to_thread(llm.call_llm, messages, task=SOUL_TASK, temperature=0.3)
        return (resp.choices[0].message.content or "").strip()
