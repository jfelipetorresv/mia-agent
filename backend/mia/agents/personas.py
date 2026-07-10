"""Mia · agents.personas — personas jurídicas especializadas y editables por el despacho
(CP-E3, Ola 5).

Ref: ClaudeOS Pantheon (`claudeos-ref/.../skills/personas/SKILL.md`,
`vite.config.ts::PANTHEON_SEEDS`) — llevado al dominio multi-despacho de Mia. ClaudeOS
guarda cada persona como un YAML en `~/.hermes/pantheon/personas/`; Mia NO puede: es
multi-tenant con RLS, así que las personas viven en la tabla `personas` bajo RLS
fail-closed (migración 023), una por despacho, editables por el despacho.

QUÉ ES UNA PERSONA — "QUIÉN HABLA" en un turno:
  Un rol jurídico (litigante, tributarista, revisor de citas…) con su voz (`role_prompt`),
  su tono, sus áreas de énfasis y un nivel de motor. Complementa a los nodos de CP9, que
  son "CÓMO TRABAJA" (hechos → investigación → cruce → borrador → verificación): la persona
  no cambia el método del equipo, cambia la VOZ con la que ese método se ejecuta.

CÓMO SE INVOCA (consent-first — NUNCA se auto-activa):
  El abogado nombra la persona en su propio mensaje mediante una de sus `summon_phrases`
  ("actúa como litigante…", "revisa las citas de…"), o la selecciona explícitamente. Sin
  invocación, el turno es IDÉNTICO a hoy (comportamiento sin cambios; todos los gates
  previos siguen verdes). La detección es fail-open: cualquier error → sin persona.

EL CANDADO DE CONFIDENCIALIDAD (la razón de ser del diseño de motor):
  Una persona JAMÁS elige un modelo crudo (eso evadiría la política de modelo del despacho:
  `resolve_fallback_chain(task, model=X)` devuelve `[X]` saltándose la cadena de la política
  — un despacho 'soberano' podría terminar en la nube). Una persona solo elige un NIVEL:
    · 'estandar' → sin override: la cadena de la política del despacho gobierna (techo = política).
    · 'local'    → fija el ÚLTIMO alias de la cadena de la política (el extremo local/privado,
                   hoy `mia-local` en las 3 políticas): estrictamente MÁS privado y barato que
                   la política, NUNCA menos, y siempre DENTRO de la cadena que la política ya
                   permite. No puede escalar a la nube. Fail-closed por construcción.

LA VOZ NO PUEDE ANULAR LAS REGLAS DURAS:
  `role_prompt` es material autorizado por el despacho (autoridad de estilo, como el SOUL.md),
  pero se inyecta DESPUÉS de L2/L3 (método y citación) y el bloque de voz reitera que el rol
  no contraviene esas reglas: nunca inventar normas/providencias, lo no verificable va con
  [VERIFICAR]. La persona colorea el tono, no relaja la verificación.
"""
from __future__ import annotations

import logging
import re
import uuid
from dataclasses import dataclass, field, replace
from typing import Optional

from ..db import pool

logger = logging.getLogger("mia.agents.personas")

# ── niveles de motor (el ÚNICO control de modelo de una persona) ─────────────
MODEL_TIER_STANDARD = "estandar"
MODEL_TIER_LOCAL = "local"
MODEL_TIERS = (MODEL_TIER_STANDARD, MODEL_TIER_LOCAL)

# Alias del motor LOCAL (Ollama). Es el modelo más privado del gateway y el extremo
# de todas las cadenas de política. `model_tier='local'` fija ESTE alias cuando está en
# la cadena de la política activa; si no estuviera (config atípica), cae al último eslabón
# de la cadena — que por contrato de _POLICY_CHAINS es el fallback local/más conservador.
LOCAL_ALIAS = "mia-local"

# ── topes defensivos (anti-abuso; una persona es config del despacho) ────────
MAX_PERSONAS = 24            # personas por despacho
MAX_NAME_LEN = 64
MAX_TITLE_LEN = 120
MAX_TONE_LEN = 160
MAX_DESCRIPTION_LEN = 2000
MAX_ROLE_PROMPT_LEN = 6000   # la voz/método; acotada para no ahogar el prompt del turno
MAX_FOCUS_AREAS = 12
MAX_FOCUS_LEN = 80
MAX_SUMMON_PHRASES = 12
MAX_SUMMON_LEN = 80
# Cuántas guías del despacho puede priorizar UN agente (tope defensivo; el prompt del
# turno no debe ahogarse en material de referencia). En la UI se llama "guía", no playbook.
MAX_LINKED_PLAYBOOKS = 8
# Una frase de invocación demasiado corta ("de", "el") casaría con casi todo mensaje:
# se exige un mínimo para no secuestrar turnos por accidente.
MIN_SUMMON_LEN = 3

# Marca en tenant_settings para sembrar las personas canónicas UNA sola vez por
# despacho (respeta que el despacho luego borre las que no quiera: no se re-siembran).
_SEEDED_FLAG = "personas_seeded"


class PersonaError(Exception):
    """Error de validación de una persona. `str(e)` es apto para el abogado (llano)."""


@dataclass(frozen=True)
class Persona:
    """Una persona jurídica del despacho (fila de `personas`, ya validada)."""

    id: str
    name: str
    title: str
    role_prompt: str
    tone: str
    focus_areas: tuple[str, ...]
    model_tier: str
    summon_phrases: tuple[str, ...]
    description: str
    enabled: bool
    # Guías del despacho que este agente prioriza (ids de `playbooks`), en el orden elegido
    # por el abogado. Se cargan aparte (tabla persona_playbooks) — fail-open: vacío si falla.
    playbook_ids: tuple[str, ...] = ()

    def to_public(self) -> dict:
        """Vista para la API/UI (sin jerga técnica de motor: el nivel se traduce)."""
        return {
            "id": self.id,
            "name": self.name,
            "title": self.title,
            "role_prompt": self.role_prompt,
            "tone": self.tone,
            "focus_areas": list(self.focus_areas),
            "model_tier": self.model_tier,
            "summon_phrases": list(self.summon_phrases),
            "description": self.description,
            "enabled": self.enabled,
            "playbook_ids": list(self.playbook_ids),
        }

    def turn_context(self) -> dict:
        """Lo que viaja al turno (grafo/asistente): nombre, voz pre-renderizada, el
        alias de motor YA acotado por la política activa y las guías priorizadas.
        JSON-serializable (viaja en el checkpoint del asunto)."""
        return {
            "name": self.name,
            "voice": render_persona_voice(self),
            "alias": resolve_persona_alias(self.model_tier),
            "playbook_ids": list(self.playbook_ids),
        }


# ── resolución de motor (fail-closed por construcción) ───────────────────────

def resolve_persona_alias(model_tier: str) -> Optional[str]:
    """Alias de modelo que impone la persona, o None para no imponer ninguno.

    Lee la cadena de la POLÍTICA ACTIVA del despacho (ContextVar, fijado por el
    middleware por request / `tenant_model_policy` en cron) para `task='main'`:
      · 'estandar' → None: sin override, la cadena de la política gobierna (techo = política).
      · 'local'    → el alias del motor LOCAL (`LOCAL_ALIAS`). Forzar el motor local es
                     estrictamente MÁS privado que cualquier política, NUNCA menos: es el
                     extremo de todas las cadenas de _POLICY_CHAINS y jamás sale del servidor.
    Cualquier otro valor se trata como 'estandar' (sin override) — fail-safe.

    Fail-closed por CONSTRUCCIÓN, no por posición: se devuelve `LOCAL_ALIAS` directamente
    (no `chain[-1]`), así que un futuro reordenamiento de _POLICY_CHAINS que dejara la
    cadena terminando en un alias de NUBE NO podría filtrar el trabajo del despacho — 'local'
    siempre significa el motor local. (Si el despliegue renombrara el alias local, la
    constante LOCAL_ALIAS es el único punto a actualizar; el peor caso es un turno que falla
    cerrado por falta del modelo, jamás una fuga a la nube.)
    """
    if model_tier != MODEL_TIER_LOCAL:
        return None
    return LOCAL_ALIAS


# ── render de la voz de la persona (bloque inyectado en el prompt) ───────────

_VOICE_GUARDRAIL = (
    "Mantén este rol SIN contravenir las reglas de método jurídico y de citación ya "
    "establecidas: no inventes ni afirmes normas, artículos ni providencias sin respaldo; "
    "lo que no puedas verificar va marcado con [VERIFICAR]. El rol colorea tu tono y tu "
    "énfasis, no relaja la verificación."
)


def render_persona_voice(persona: Persona) -> str:
    """Bloque de "voz" que se inyecta en el prompt del turno (tier CONTEXT, no cacheado:
    la persona cambia por turno y no debe envenenar el prefijo estable). No lleva jerga
    técnica ni nombres de modelo (§G)."""
    header = f"## Rol para este turno: {persona.name}"
    if persona.title:
        header += f" — {persona.title}"
    parts = [header, persona.role_prompt.strip()]
    if persona.tone:
        parts.append(f"Tono: {persona.tone.strip()}")
    if persona.focus_areas:
        parts.append("Áreas de énfasis: " + ", ".join(persona.focus_areas) + ".")
    parts.append(_VOICE_GUARDRAIL)
    return "\n\n".join(p for p in parts if p and p.strip())


# ── detección por frases de invocación (pura, testeable sin DB) ──────────────

def detect_persona(message: str, personas: list[Persona]) -> Optional[Persona]:
    """La persona invocada en `message` por una de sus `summon_phrases`, o None.

    Solo considera personas HABILITADAS. Casa por límite de palabra e insensible a
    mayúsculas. Si varias casan, gana la FRASE más larga (la más específica); a igual
    longitud, el primer resultado estable. Pura: no toca la DB (la resolución con DB
    vive en PersonaService.resolve_for_turn)."""
    text = message or ""
    if not text.strip():
        return None
    best: Optional[Persona] = None
    best_len = 0
    for p in personas:
        if not p.enabled:
            continue
        for phrase in p.summon_phrases:
            phrase = (phrase or "").strip()
            if len(phrase) < MIN_SUMMON_LEN:
                continue
            # \b…\b insensible a mayúsculas; la frase se escapa (no es un patrón).
            if re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE):
                if len(phrase) > best_len:
                    best, best_len = p, len(phrase)
    return best


# ── validación / normalización de entrada (CRUD del despacho) ────────────────

def _clean_str(value: object, *, max_len: int, field_name: str, required: bool = False) -> str:
    s = ("" if value is None else str(value)).strip()
    if required and not s:
        raise PersonaError(f"El campo '{field_name}' es obligatorio.")
    if len(s) > max_len:
        raise PersonaError(f"El campo '{field_name}' es demasiado largo (máx. {max_len}).")
    return s


def _clean_list(value: object, *, max_items: int, max_len: int, min_len: int,
                field_name: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, (list, tuple)):
        raise PersonaError(f"El campo '{field_name}' debe ser una lista.")
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        s = str(item or "").strip()
        if not s:
            continue
        if len(s) > max_len:
            raise PersonaError(
                f"Un valor de '{field_name}' es demasiado largo (máx. {max_len}).")
        if len(s) < min_len:
            # Silencioso: se descarta un valor demasiado corto en vez de romper (p. ej.
            # una frase de invocación de 1-2 letras que secuestraría turnos).
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
        if len(out) >= max_items:
            break
    return tuple(out)


def _validate_tier(value: object) -> str:
    s = ("" if value is None else str(value)).strip().lower()
    if not s:
        return MODEL_TIER_STANDARD
    if s not in MODEL_TIERS:
        raise PersonaError(
            "El nivel de motor no es válido. Usa 'estandar' (el motor del despacho) o "
            "'local' (siempre el motor local).")
    return s


def _normalize_input(data: dict) -> dict:
    """Valida y normaliza el payload de crear/actualizar una persona. Lanza
    PersonaError (en llano) ante datos inválidos."""
    name = _clean_str(data.get("name"), max_len=MAX_NAME_LEN, field_name="name", required=True)
    role_prompt = _clean_str(data.get("role_prompt"), max_len=MAX_ROLE_PROMPT_LEN,
                             field_name="role_prompt", required=True)
    return {
        "name": name,
        "title": _clean_str(data.get("title"), max_len=MAX_TITLE_LEN, field_name="title"),
        "role_prompt": role_prompt,
        "tone": _clean_str(data.get("tone"), max_len=MAX_TONE_LEN, field_name="tone"),
        "focus_areas": _clean_list(data.get("focus_areas"), max_items=MAX_FOCUS_AREAS,
                                   max_len=MAX_FOCUS_LEN, min_len=1, field_name="focus_areas"),
        "model_tier": _validate_tier(data.get("model_tier")),
        "summon_phrases": _clean_list(data.get("summon_phrases"), max_items=MAX_SUMMON_PHRASES,
                                      max_len=MAX_SUMMON_LEN, min_len=MIN_SUMMON_LEN,
                                      field_name="summon_phrases"),
        "description": _clean_str(data.get("description"), max_len=MAX_DESCRIPTION_LEN,
                                  field_name="description"),
        "enabled": bool(data.get("enabled", True)),
    }


def _row_to_persona(row: tuple) -> Persona:
    return Persona(
        id=str(row[0]),
        name=row[1],
        title=row[2] or "",
        role_prompt=row[3] or "",
        tone=row[4] or "",
        focus_areas=tuple(row[5] or ()),
        model_tier=row[6] or MODEL_TIER_STANDARD,
        summon_phrases=tuple(row[7] or ()),
        description=row[8] or "",
        enabled=bool(row[9]),
    )


_SELECT_COLS = ("id, name, title, role_prompt, tone, focus_areas, model_tier, "
                "summon_phrases, description, enabled")


def _require_uuid(value: str) -> str:
    """Valida que `value` sea un UUID (evita que un id malformado toque la DB)."""
    try:
        return str(uuid.UUID(str(value)))
    except (ValueError, AttributeError, TypeError):
        raise PersonaError("Identificador de persona inválido.")


# ── personas canónicas sembradas por despacho (editables después) ────────────
# Ref PANTHEON_SEEDS de ClaudeOS, traducido al oficio jurídico del Civil Law. Son un
# PUNTO DE PARTIDA: el despacho las edita, deshabilita o borra a gusto. El revisor de
# citas usa el motor LOCAL a propósito (tarea mecánica y barata; más privado).
DEFAULT_PERSONAS: tuple[dict, ...] = (
    {
        "name": "Litigante",
        "title": "Estratega procesal",
        "role_prompt": (
            "Actúas como litigante estratega al servicio del cliente del despacho. Piensas "
            "en clave de defensa: identificas la teoría del caso más favorable, las "
            "excepciones y defensas disponibles, las cargas probatorias de cada parte y los "
            "riesgos procesales. Eres persuasivo pero riguroso: cada afirmación se ancla en "
            "el expediente o en la norma, y distingues lo que está probado de lo que falta "
            "por acreditar. Priorizas la posición del cliente sin exagerar la fuerza del caso."
        ),
        "tone": "firme, persuasivo, orientado a la defensa",
        "focus_areas": ["excepciones y defensas", "cargas probatorias", "estrategia procesal"],
        "model_tier": MODEL_TIER_STANDARD,
        "summon_phrases": ["litigante", "como litigante", "en modo litigante", "modo litigante"],
        "description": (
            "Voz de litigante estratega: piensa la defensa del cliente, las excepciones y la "
            "carga probatoria. Úsala cuando quieras enfocar un asunto desde la estrategia procesal."
        ),
    },
    {
        "name": "Tributarista",
        "title": "Especialista en derecho tributario y fiscal",
        "role_prompt": (
            "Actúas como tributarista prudente. Analizas los problemas desde el derecho "
            "tributario y fiscal: obligaciones formales y sustanciales, procedimientos ante "
            "la autoridad tributaria, prescripción, sanciones y recursos. Eres técnico y "
            "conservador: prefieres la interpretación defendible ante la autoridad y señalas "
            "expresamente los riesgos y las zonas grises. No afirmas un criterio fiscal sin "
            "respaldo normativo verificable."
        ),
        "tone": "técnico, prudente, conservador",
        "focus_areas": ["derecho tributario", "procedimiento fiscal", "sanciones y recursos"],
        "model_tier": MODEL_TIER_STANDARD,
        "summon_phrases": ["tributarista", "como tributarista", "perspectiva tributaria",
                           "en materia tributaria"],
        "description": (
            "Voz de tributarista: enfoca el asunto desde el derecho tributario y fiscal, con "
            "prudencia técnica. Úsala para temas de impuestos, sanciones o procedimiento fiscal."
        ),
    },
    {
        "name": "Revisor de citas",
        "title": "Verificador de exactitud normativa",
        "role_prompt": (
            "Actúas como revisor meticuloso de las citas jurídicas de un texto. Tu único "
            "oficio es la EXACTITUD: revisas cada norma, artículo y providencia mencionada y "
            "señalas cuáles están respaldadas y cuáles no. Todo lo que no puedas confirmar "
            "contra su fuente lo marcas con [VERIFICAR] y lo dices con claridad. No redactas "
            "argumentos nuevos ni cambias la estrategia: solo verificas y adviertes. Prefieres "
            "un 'no lo puedo confirmar' honesto antes que dar por cierta una cita plausible."
        ),
        "tone": "meticuloso, literal, verificador",
        "focus_areas": ["exactitud de citas", "verificación normativa", "control de calidad"],
        "model_tier": MODEL_TIER_LOCAL,
        "summon_phrases": ["revisor de citas", "revisa las citas", "verifica las citas",
                           "como revisor de citas"],
        "description": (
            "Voz de revisor de citas: verifica la exactitud de cada norma y providencia y marca "
            "con [VERIFICAR] lo que no tenga respaldo. Úsala como control de calidad de un escrito."
        ),
    },
)


class PersonaService:
    """CRUD de personas del despacho bajo RLS + resolución de la persona de un turno.

    Sin estado por request (una instancia se reutiliza): cada método abre su propia
    `pool.tenant_connection(tenant_id)` (RLS fail-closed) y no comparte nada entre
    despachos."""

    # ── siembra idempotente de las personas canónicas ────────────────────────
    async def _ensure_seeded(self, tenant_id: str) -> None:
        """Siembra las personas canónicas UNA vez por despacho (marca en
        tenant_settings.config['personas_seeded']). Si el despacho luego borra alguna,
        NO se re-siembra (respeta su autonomía). Idempotente y barato tras la 1ª vez."""
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "SELECT config->>%s FROM tenant_settings WHERE tenant_id = %s::uuid",
                (_SEEDED_FLAG, tenant_id),
            )).fetchone()
            already = bool(row and str(row[0] or "").strip().lower() in ("true", "1", "yes", "on"))
            if already:
                return
            for seed in DEFAULT_PERSONAS:
                data = _normalize_input(seed)
                # ON CONFLICT DO NOTHING: si el despacho ya creó una con ese nombre, se
                # respeta la suya (no la pisa la semilla).
                await conn.execute(
                    "INSERT INTO personas (tenant_id, name, title, role_prompt, tone, "
                    "focus_areas, model_tier, summon_phrases, description, enabled) "
                    "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (tenant_id, name) DO NOTHING",
                    (tenant_id, data["name"], data["title"], data["role_prompt"], data["tone"],
                     list(data["focus_areas"]), data["model_tier"],
                     list(data["summon_phrases"]), data["description"], data["enabled"]),
                )
            # Marca sembrado (merge sobre config, sin pisar otras claves — patrón CP-E1).
            await conn.execute(
                "INSERT INTO tenant_settings (tenant_id, config) "
                "VALUES (%s::uuid, jsonb_build_object(%s::text, to_jsonb(true))) "
                "ON CONFLICT (tenant_id) DO UPDATE SET config = "
                "  COALESCE(tenant_settings.config, '{}'::jsonb) "
                "  || jsonb_build_object(%s::text, to_jsonb(true))",
                (tenant_id, _SEEDED_FLAG, _SEEDED_FLAG),
            )

    # ── vínculos persona → guías (fail-open) ──────────────────────────────────
    async def _load_links(self, tenant_id: str, persona_ids: list[str]) -> dict:
        """Mapa persona_id → tupla de ids de guías vinculadas (por position, created_at),
        en UNA query agregada. FAIL-OPEN: ante cualquier error devuelve {} (las personas
        quedan sin vínculos) y el flujo sigue — vincular guías es una ayuda, no un candado.
        Corre en su PROPIA conexión: un fallo aquí no aborta la transacción de la lectura."""
        if not persona_ids:
            return {}
        try:
            async with pool.tenant_connection(tenant_id) as conn:
                rows = await (await conn.execute(
                    "SELECT persona_id, array_agg(playbook_id ORDER BY position, created_at) "
                    "FROM persona_playbooks WHERE persona_id = ANY(%s::uuid[]) "
                    "GROUP BY persona_id",
                    (persona_ids,),
                )).fetchall()
            return {str(r[0]): tuple(str(x) for x in (r[1] or ())) for r in rows}
        except Exception:  # noqa: BLE001 — CP-E3: los vínculos jamás tumban el turno
            logger.warning("personas: no se pudieron cargar los vínculos de guías (tenant=%s)",
                           tenant_id, exc_info=True)
            return {}

    async def _attach_links(self, tenant_id: str, personas: list[Persona]) -> list[Persona]:
        """Adjunta los ids de guías vinculadas a cada persona (fail-open: sin vínculos si
        la query falla). Persona es frozen → se reconstruye con dataclasses.replace."""
        if not personas:
            return personas
        try:
            links = await self._load_links(tenant_id, [p.id for p in personas])
        except Exception:  # noqa: BLE001 — doble red CP-E3: adjuntar vínculos jamás tumba el turno
            logger.warning("personas: no se pudieron adjuntar los vínculos (tenant=%s)",
                           tenant_id, exc_info=True)
            return personas
        if not links:
            return personas
        return [replace(p, playbook_ids=links[p.id]) if links.get(p.id) else p
                for p in personas]

    async def get_linked_playbook_ids(self, tenant_id: str, persona_id: str) -> list[str]:
        """Ids de las guías vinculadas a un agente, en su orden (position, created_at)."""
        persona_id = _require_uuid(persona_id)
        links = await self._load_links(tenant_id, [persona_id])
        return list(links.get(persona_id, ()))

    async def set_linked_playbooks(
        self, tenant_id: str, persona_id: str, playbook_ids: list[str]
    ) -> None:
        """Reemplaza las guías vinculadas de un agente (DELETE + INSERTs en una transacción).

        Valida: el agente existe; tope MAX_LINKED_PLAYBOOKS; dedupe preservando orden; cada
        id apunta a una guía del despacho (cualquier estado). Un id malformado o inexistente
        → PersonaError en llano (NUNCA un 500 técnico)."""
        persona_id = _require_uuid(persona_id)
        # Dedupe preservando orden + validación de UUID (un id malformado se trata como una
        # guía que "ya no existe", nunca como un error crudo que llegue al ::uuid de la DB).
        clean: list[str] = []
        seen: set[str] = set()
        for pid in (playbook_ids or []):
            try:
                u = str(uuid.UUID(str(pid)))
            except (ValueError, AttributeError, TypeError):
                raise PersonaError("Una de las guías seleccionadas ya no existe.")
            if u in seen:
                continue
            seen.add(u)
            clean.append(u)
        if len(clean) > MAX_LINKED_PLAYBOOKS:
            raise PersonaError(
                f"Un agente puede tener máximo {MAX_LINKED_PLAYBOOKS} guías vinculadas.")
        async with pool.tenant_connection(tenant_id) as conn:
            exists = await (await conn.execute(
                "SELECT 1 FROM personas WHERE id = %s::uuid", (persona_id,),
            )).fetchone()
            if not exists:
                raise PersonaError("Ese agente no existe en este despacho.")
            if clean:
                found = await (await conn.execute(
                    "SELECT id FROM playbooks WHERE id = ANY(%s::uuid[])", (clean,),
                )).fetchall()
                found_ids = {str(r[0]) for r in found}
                if any(pid not in found_ids for pid in clean):
                    raise PersonaError("Una de las guías seleccionadas ya no existe.")
            await conn.execute(
                "DELETE FROM persona_playbooks WHERE persona_id = %s::uuid", (persona_id,))
            for pos, pid in enumerate(clean):
                await conn.execute(
                    "INSERT INTO persona_playbooks (tenant_id, persona_id, playbook_id, position) "
                    "VALUES (%s::uuid, %s::uuid, %s::uuid, %s)",
                    (tenant_id, persona_id, pid, pos))

    # ── lecturas ──────────────────────────────────────────────────────────────
    async def list_personas(self, tenant_id: str) -> list[Persona]:
        """Personas del despacho (habilitadas y no), orden estable por nombre. Siembra
        las canónicas la primera vez."""
        await self._ensure_seeded(tenant_id)
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                f"SELECT {_SELECT_COLS} FROM personas ORDER BY lower(name)"
            )).fetchall()
        return await self._attach_links(tenant_id, [_row_to_persona(r) for r in rows])

    async def get_persona(self, tenant_id: str, persona_id: str) -> Optional[Persona]:
        """Una persona del despacho por id, o None si no existe/es de otro despacho (RLS)."""
        persona_id = _require_uuid(persona_id)
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                f"SELECT {_SELECT_COLS} FROM personas WHERE id = %s::uuid", (persona_id,),
            )).fetchone()
        if not row:
            return None
        attached = await self._attach_links(tenant_id, [_row_to_persona(row)])
        return attached[0]

    async def _enabled_personas(self, tenant_id: str) -> list[Persona]:
        """Solo las habilitadas — para la detección por frases (sin sembrar en el turno
        salvo que haga falta: _ensure_seeded es barato tras la 1ª vez)."""
        await self._ensure_seeded(tenant_id)
        async with pool.tenant_connection(tenant_id) as conn:
            rows = await (await conn.execute(
                f"SELECT {_SELECT_COLS} FROM personas WHERE enabled = true"
            )).fetchall()
        return await self._attach_links(tenant_id, [_row_to_persona(r) for r in rows])

    # ── escrituras ─────────────────────────────────────────────────────────────
    async def create_persona(self, tenant_id: str, data: dict) -> Persona:
        """Crea una persona (acto humano explícito). Nombre duplicado → PersonaError."""
        clean = _normalize_input(data)
        async with pool.tenant_connection(tenant_id) as conn:
            count = await (await conn.execute("SELECT count(*) FROM personas")).fetchone()
            if count and count[0] >= MAX_PERSONAS:
                raise PersonaError(
                    f"El despacho ya tiene el máximo de personas ({MAX_PERSONAS}). "
                    "Elimina o deshabilita alguna para crear otra.")
            dup = await (await conn.execute(
                "SELECT 1 FROM personas WHERE lower(name) = lower(%s)", (clean["name"],),
            )).fetchone()
            if dup:
                raise PersonaError(f"Ya existe una persona llamada '{clean['name']}'.")
            row = await (await conn.execute(
                "INSERT INTO personas (tenant_id, name, title, role_prompt, tone, focus_areas, "
                "model_tier, summon_phrases, description, enabled) "
                "VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                f"RETURNING {_SELECT_COLS}",
                (tenant_id, clean["name"], clean["title"], clean["role_prompt"], clean["tone"],
                 list(clean["focus_areas"]), clean["model_tier"], list(clean["summon_phrases"]),
                 clean["description"], clean["enabled"]),
            )).fetchone()
        return _row_to_persona(row)

    async def update_persona(self, tenant_id: str, persona_id: str, data: dict) -> Persona:
        """Actualiza una persona del despacho. Inexistente/ajena → PersonaError (RLS)."""
        persona_id = _require_uuid(persona_id)
        clean = _normalize_input(data)
        async with pool.tenant_connection(tenant_id) as conn:
            dup = await (await conn.execute(
                "SELECT 1 FROM personas WHERE lower(name) = lower(%s) AND id <> %s::uuid",
                (clean["name"], persona_id),
            )).fetchone()
            if dup:
                raise PersonaError(f"Ya existe otra persona llamada '{clean['name']}'.")
            row = await (await conn.execute(
                "UPDATE personas SET name = %s, title = %s, role_prompt = %s, tone = %s, "
                "focus_areas = %s, model_tier = %s, summon_phrases = %s, description = %s, "
                "enabled = %s, updated_at = now() WHERE id = %s::uuid "
                f"RETURNING {_SELECT_COLS}",
                (clean["name"], clean["title"], clean["role_prompt"], clean["tone"],
                 list(clean["focus_areas"]), clean["model_tier"], list(clean["summon_phrases"]),
                 clean["description"], clean["enabled"], persona_id),
            )).fetchone()
        if not row:
            raise PersonaError("Esa persona no existe en este despacho.")
        return _row_to_persona(row)

    async def delete_persona(self, tenant_id: str, persona_id: str) -> None:
        """Elimina una persona del despacho. Inexistente/ajena → PersonaError (RLS)."""
        persona_id = _require_uuid(persona_id)
        async with pool.tenant_connection(tenant_id) as conn:
            row = await (await conn.execute(
                "DELETE FROM personas WHERE id = %s::uuid RETURNING 1", (persona_id,),
            )).fetchone()
        if not row:
            raise PersonaError("Esa persona no existe en este despacho.")

    # ── resolución de la persona de un turno (fail-open) ──────────────────────
    async def resolve_for_turn(
        self, tenant_id: str, message: str, explicit_id: Optional[str] = None
    ) -> Optional[Persona]:
        """La persona a aplicar en este turno: la seleccionada explícitamente (si está
        habilitada) o la invocada por frase en `message`. None si ninguna aplica.

        FAIL-OPEN: cualquier error (DB caída, dato raro) → None → el turno sigue sin
        persona (comportamiento idéntico a hoy). Aplicar una persona es una ayuda, no
        un candado; nunca tumba el turno."""
        try:
            if explicit_id:
                persona = await self.get_persona(tenant_id, explicit_id)
                return persona if (persona and persona.enabled) else None
            personas = await self._enabled_personas(tenant_id)
            return detect_persona(message, personas)
        except Exception:  # noqa: BLE001 — §G: aplicar una persona jamás tumba el turno
            logger.warning("resolve_for_turn: no se pudo resolver la persona (tenant=%s)",
                           tenant_id, exc_info=True)
            return None


# Instancia compartida (sin estado por request; misma vida que AssistantService).
persona_service = PersonaService()
