"""Mia · agent.prompt_builder — system prompt de 10 capas en 3 tiers.

Adaptado de Hermes (agent/system_prompt.py::build_system_prompt_parts). El prompt
se arma una vez por sesión y se cachea en el agente; solo se reconstruye tras una
compresión de contexto. Eso mantiene caliente el prefix cache del gateway
(decisión #3: ~75% de ahorro en matters largos).

Las 10 capas viven en UNA sola tabla ordenada (`LAYERS`): es la fuente única de
verdad del orden, del tier y de la marca de cacheo. Todo lo demás (el prompt
ensamblado, la vista por tiers, la inspección capa-a-capa) se deriva de ahí.

Tres tiers, ordenados cache-friendly:

  STABLE  (capas 1-6) — byte-estable entre turnos → es el PREFIJO cacheado
    (TTL 1h en el gateway, ver STABLE_CACHE_TTL_SECONDS):
    L1 identidad · L2 metodología jurídica · L3 citación/verificación ·
    L4 herramientas · L5 comunicación con el usuario · L6 skills.
  CONTEXT (capas 7-8) — estable por sesión, NO cacheado:
    L7 contexto del asunto · L8 instrucciones de la sesión.
  VOLATILE (capas 9-10) — por turno, NO cacheado:
    L9 memoria/playbook del despacho · L10 metadata de la sesión.

Las capas L4, L6, L7, L9 son COSTURAS: hoy no-op (vacías) hasta que las llenen los
módulos posteriores (tools 1c/1d · skills · matter · memoria 2a/2b). El contrato
de las 10 capas queda fijado aquí; activarlas es rellenar el estado del agente.

Helpers stateless que leen el estado del agente por duck-typing (no importan core
→ sin ciclo).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Callable

# TTL del prefix cache del gateway para el tier STABLE (decisión #3). El builder
# NO fuerza el TTL — lo aplica LiteLLM aguas arriba; aquí se expone para documentar
# la intención y para que el gate pueda verificar la política de cacheo.
STABLE_CACHE_TTL_SECONDS = 3600  # 1 hora

# Nombres de tier (un solo lugar para evitar typos sueltos por el archivo).
TIER_STABLE = "stable"
TIER_CONTEXT = "context"
TIER_VOLATILE = "volatile"

# ── Capas STABLE de texto fijo ─────────────────────────────────────────────

# L2 · Metodología jurídica
METHODOLOGY = (
    "Razonas como un jurista del Civil Law hispanoamericano. Estructuras tu "
    "análisis en: (1) hechos relevantes, (2) problema jurídico, (3) fundamentos "
    "de derecho con sus fuentes, (4) conclusión y recomendación. Distingues entre "
    "norma aplicable, jurisprudencia y doctrina. Eres prudente: nombras tus "
    "supuestos, los riesgos y lo que falta por verificar antes de afirmar una "
    "conclusión."
)

# L3 · Citación y verificación (CLAUDE.md global · "Legal Citation Verification")
CITATION_POLICY = (
    "Nunca inventas normas, artículos ni sentencias. Toda cita legal debe poder "
    "verificarse contra su fuente primaria. Si no puedes verificar una norma o una "
    "providencia, NO la afirmes como cierta: márcala con [VERIFICAR] y dilo "
    "explícitamente. Prefieres decir 'no lo sé con certeza' antes que ofrecer una "
    "cita plausible pero no confirmada. Citas con precisión: norma, artículo y, "
    "cuando aplique, la corporación, el número y la fecha de la providencia."
)

# L5 · Comunicación con el usuario (CLAUDE.md §G)
USER_COMMS = (
    "Tu interlocutor es un abogado sin formación técnica en IA. Nunca usas jerga "
    "del sistema: no menciones 'HITL', 'LangGraph', 'pgvector', 'tenant', "
    "'embeddings' ni nombres de modelos. Hablas en términos del oficio jurídico: "
    "'asunto' (no 'caso' ni 'matter'), 'revisar el borrador', 'estoy investigando "
    "el expediente'. Eres clara, directa y profesional."
)


# ── Helpers por capa (leen el estado del agente) ───────────────────────────

def _identity_layer(agent: Any) -> str:
    """L1 · Identidad de Mia (sustituible por SOUL.md en el Módulo 5)."""
    return str(getattr(agent, "identity", "") or "")


def _methodology_layer(agent: Any) -> str:
    """L2 · Metodología jurídica (texto fijo)."""
    return METHODOLOGY


def _citation_layer(agent: Any) -> str:
    """L3 · Política de citación/verificación (texto fijo)."""
    return CITATION_POLICY


def _tools_layer(agent: Any) -> str:
    """L4 · Guía de herramientas. Costura: vacía hasta que el agente tenga tools (1c/1d)."""
    names = list(getattr(agent, "tool_names", []) or [])
    if not names:
        return ""
    return (
        "Tienes herramientas disponibles: " + ", ".join(names) + ". Úsalas para "
        "actuar de verdad (buscar en el expediente, redactar, verificar) en vez de "
        "describir lo que harías. No afirmes haber hecho algo sin ejecutar la "
        "herramienta correspondiente."
    )


def _user_comms_layer(agent: Any) -> str:
    """L5 · Reglas de comunicación con el usuario (texto fijo, §G)."""
    return USER_COMMS


def _skills_layer(agent: Any) -> str:
    """L6 · Índice de skills. Costura: vacía hasta que exista el sistema de skills."""
    return str(getattr(agent, "skills_index", "") or "")


def _matter_layer(agent: Any) -> str:
    """L7 · Contexto del asunto (matter). Costura: vacía hasta cargar un expediente."""
    ctx = getattr(agent, "matter_context", None)
    if not ctx:
        return ""
    return "## Asunto en curso\n" + str(ctx)


def _session_instructions_layer(agent: Any) -> str:
    """L8 · Instrucciones de la sesión (system_message del caller)."""
    return str(getattr(agent, "system_message", "") or "")


def _memory_layer(agent: Any) -> str:
    """L9 · Memoria / playbook del despacho. Costura: vacía hasta 2a/2b."""
    return str(getattr(agent, "memory_block", "") or "")


def _metadata_layer(agent: Any) -> str:
    """L10 · Metadata de la sesión. Date-only para no invalidar el cache (patrón Hermes).

    No incluye el nombre del modelo a propósito (§G: Mia no revela jerga ni modelos).
    """
    return f"Fecha de la sesión: {datetime.now():%Y-%m-%d}"


# ── Tabla de capas — FUENTE ÚNICA del orden / tier / cacheo ─────────────────

@dataclass(frozen=True)
class LayerSpec:
    """Una de las 10 capas: su posición, su nombre, su tier y cómo se construye."""

    index: int                       # 1..10, orden de ensamblaje
    name: str                        # identificador estable de la capa
    tier: str                        # TIER_STABLE | TIER_CONTEXT | TIER_VOLATILE
    build: Callable[[Any], str]      # (agent) -> texto de la capa ("" si costura vacía)

    @property
    def cached(self) -> bool:
        """True si la capa entra al PREFIJO cacheado (TTL 1h). Solo el tier STABLE
        (capas 1-6) es byte-estable entre turnos, así que solo él se cachea."""
        return self.tier == TIER_STABLE


# El orden de esta tupla ES el contrato de las 10 capas. No reordenar sin
# actualizar architecture/prompt_builder.md y el gate (test_prompt_builder.py).
LAYERS: tuple[LayerSpec, ...] = (
    LayerSpec(1, "identity", TIER_STABLE, _identity_layer),
    LayerSpec(2, "methodology", TIER_STABLE, _methodology_layer),
    LayerSpec(3, "citation", TIER_STABLE, _citation_layer),
    LayerSpec(4, "tools", TIER_STABLE, _tools_layer),
    LayerSpec(5, "user_comms", TIER_STABLE, _user_comms_layer),
    LayerSpec(6, "skills", TIER_STABLE, _skills_layer),
    LayerSpec(7, "matter", TIER_CONTEXT, _matter_layer),
    LayerSpec(8, "session_instructions", TIER_CONTEXT, _session_instructions_layer),
    LayerSpec(9, "memory", TIER_VOLATILE, _memory_layer),
    LayerSpec(10, "metadata", TIER_VOLATILE, _metadata_layer),
)


# ── Ensamblaje ─────────────────────────────────────────────────────────────

def build_layers(agent: Any) -> list[dict]:
    """Las 10 capas en orden, cada una con su metadata y su contenido renderizado.

    Útil para inspección y para el gate: deja ver qué capa entra al prompt, en qué
    tier y si está cacheada. Las costuras vacías aparecen con content="".
    """
    return [
        {
            "index": spec.index,
            "name": spec.name,
            "tier": spec.tier,
            "cached": spec.cached,
            "content": spec.build(agent) or "",
        }
        for spec in LAYERS
    ]


def _join(parts: list[str]) -> str:
    """Une capas no vacías con doble salto (descarta costuras vacías)."""
    return "\n\n".join(p.strip() for p in parts if p and p.strip())


def build_system_prompt_parts(agent: Any) -> dict[str, str]:
    """Arma el prompt como 3 tiers ordenados (stable / context / volatile)."""
    by_tier: dict[str, list[str]] = {TIER_STABLE: [], TIER_CONTEXT: [], TIER_VOLATILE: []}
    for spec in LAYERS:
        by_tier[spec.tier].append(spec.build(agent))
    return {
        "stable": _join(by_tier[TIER_STABLE]),
        "context": _join(by_tier[TIER_CONTEXT]),
        "volatile": _join(by_tier[TIER_VOLATILE]),
    }


def build_system_prompt(agent: Any) -> str:
    """System prompt de sistema completo (stable + context + volatile)."""
    parts = build_system_prompt_parts(agent)
    return "\n\n".join(p for p in (parts["stable"], parts["context"], parts["volatile"]) if p)


def invalidate(agent: Any) -> None:
    """Invalida el prompt cacheado del agente (forzar rebuild tras compresión)."""
    agent._cached_system_prompt = None
