"""Mia · memory.profile_manager — perfiles del abogado y del despacho (2a).

Dos perfiles de texto que personalizan a Mia:
  · PERFIL_ABOGADO  (≤600 tokens) — el abogado individual: estilo, especialidad,
    preferencias de redacción.
  · PERFIL_DESPACHO (≤900 tokens) — el despacho: metodología, posiciones estándar.

FROZEN SNAPSHOT AL INICIO DEL ASUNTO. Cuando arranca un asunto (`start_matter`),
el manager congela los perfiles vigentes en un `ProfileSnapshot` inmutable. Editar
los perfiles después NO afecta el asunto en curso: el cambio se ve en el SIGUIENTE
asunto (el próximo snapshot). Así un asunto razona con un perfil estable de punta a
punta, sin que un cambio a mitad de camino le cambie las reglas.

Presupuesto de tokens: estimación heurística OFFLINE (`estimate_tokens`, ~4
caracteres/token). Es un guardarraíl local; el conteo exacto lo da el gateway. Un
perfil que excede su presupuesto se RECHAZA con ValueError (no se trunca en
silencio: el dueño del perfil debe recortarlo a conciencia).
"""
from __future__ import annotations

from dataclasses import dataclass

# Estimador de tokens compartido por el subsistema de memoria (re-exportado para
# compatibilidad: `from mia.memory.profile_manager import estimate_tokens`).
from .tokens import estimate_tokens

PERFIL_ABOGADO_MAX_TOKENS = 600
PERFIL_DESPACHO_MAX_TOKENS = 900


@dataclass(frozen=True)
class ProfileSnapshot:
    """Perfiles congelados para un asunto. Inmutable: capturar los strings por
    valor basta para que un cambio posterior en el manager no lo afecte."""

    matter_id: str
    abogado: str
    despacho: str

    @property
    def abogado_tokens(self) -> int:
        return estimate_tokens(self.abogado)

    @property
    def despacho_tokens(self) -> int:
        return estimate_tokens(self.despacho)

    def render(self) -> str:
        """Bloque de texto de los perfiles para inyectar en el prompt (costura L9).
        Omite los perfiles vacíos."""
        parts = []
        if self.abogado.strip():
            parts.append("## Perfil del abogado\n" + self.abogado.strip())
        if self.despacho.strip():
            parts.append("## Perfil del despacho\n" + self.despacho.strip())
        return "\n\n".join(parts)


class ProfileManager:
    """Mantiene los perfiles VIGENTES (editables) y los congela por asunto.

    Editar un perfil valida el presupuesto y reemplaza el valor vigente, pero NO
    toca los snapshots ya entregados. `start_matter` devuelve un snapshot con el
    estado vigente en ese instante.
    """

    def __init__(self, *, abogado: str = "", despacho: str = "",
                 pool=None, tenant_id: str | None = None) -> None:
        self._abogado = ""
        self._despacho = ""
        self.set_abogado(abogado)
        self.set_despacho(despacho)
        # Backend de persistencia del perfil ESTRUCTURADO del despacho (Fase 3, decisión #20).
        # Distinto de los perfiles de TEXTO de arriba (abogado/despacho, costura L9). Con
        # pool=None el manager es in-memory puro (el gate 2a no cambia).
        self._pool = pool
        self._tenant_id = tenant_id

    @staticmethod
    def _check_budget(kind: str, text: str, budget: int) -> None:
        n = estimate_tokens(text)
        if n > budget:
            raise ValueError(
                f"PERFIL_{kind.upper()} excede el presupuesto: {n} > {budget} tokens "
                f"(~{len(text)} caracteres). Recórtalo."
            )

    def set_abogado(self, text: str) -> None:
        """Reemplaza el perfil VIGENTE del abogado (valida ≤600 tokens)."""
        self._check_budget("abogado", text, PERFIL_ABOGADO_MAX_TOKENS)
        self._abogado = text

    def set_despacho(self, text: str) -> None:
        """Reemplaza el perfil VIGENTE del despacho (valida ≤900 tokens)."""
        self._check_budget("despacho", text, PERFIL_DESPACHO_MAX_TOKENS)
        self._despacho = text

    @property
    def abogado(self) -> str:
        return self._abogado

    @property
    def despacho(self) -> str:
        return self._despacho

    def start_matter(self, matter_id: str) -> ProfileSnapshot:
        """Congela los perfiles vigentes para `matter_id`. Los cambios posteriores
        a los perfiles NO afectan este snapshot (se verán en el próximo asunto)."""
        return ProfileSnapshot(
            matter_id=matter_id,
            abogado=self._abogado,
            despacho=self._despacho,
        )

    # ── perfil estructurado del despacho en DB (Fase 3, decisión #20) ──────────
    # Tabla firm_profiles, una fila por tenant. Bajo RLS (tenant_connection).
    _FIRM_FIELDS = (
        "name", "lawyer_name", "tp_number", "jurisdiction", "practice_areas",
        "voice_adjectives", "banned_words", "preferred_sources", "hard_nos", "tools",
    )

    async def get_firm_profile(self, tenant_id: str | None = None) -> dict | None:
        """Perfil estructurado del despacho (dict) o None si no se ha creado."""
        tid = tenant_id or self._tenant_id
        if self._pool is None or tid is None:
            return None
        from psycopg.rows import dict_row
        async with self._pool.tenant_connection(tid) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "SELECT name, lawyer_name, tp_number, jurisdiction, practice_areas, "
                    "voice_adjectives, banned_words, preferred_sources, hard_nos, rhythm, tools, "
                    "updated_at FROM firm_profiles WHERE tenant_id = %s::uuid", (tid,))
                return await cur.fetchone()

    async def upsert_firm_profile(self, tenant_id: str, data: dict) -> dict:
        """Crea/actualiza el perfil estructurado del despacho (upsert por tenant). Devuelve el
        perfil resultante."""
        from psycopg.types.json import Json
        from psycopg.rows import dict_row
        rhythm = Json(data.get("rhythm") or {})
        vals = {f: data.get(f) for f in self._FIRM_FIELDS}
        async with self._pool.tenant_connection(tenant_id) as conn:
            async with conn.cursor(row_factory=dict_row) as cur:
                await cur.execute(
                    "INSERT INTO firm_profiles "
                    "  (tenant_id, name, lawyer_name, tp_number, jurisdiction, practice_areas, "
                    "   voice_adjectives, banned_words, preferred_sources, hard_nos, rhythm, tools) "
                    "VALUES (%(t)s::uuid, %(name)s, %(lawyer_name)s, %(tp_number)s, "
                    "  COALESCE(%(jurisdiction)s,'colombia'), %(practice_areas)s, "
                    "  %(voice_adjectives)s, %(banned_words)s, %(preferred_sources)s, "
                    "  %(hard_nos)s, %(rhythm)s, %(tools)s) "
                    "ON CONFLICT (tenant_id) DO UPDATE SET "
                    "  name=EXCLUDED.name, lawyer_name=EXCLUDED.lawyer_name, "
                    "  tp_number=EXCLUDED.tp_number, jurisdiction=EXCLUDED.jurisdiction, "
                    "  practice_areas=EXCLUDED.practice_areas, voice_adjectives=EXCLUDED.voice_adjectives, "
                    "  banned_words=EXCLUDED.banned_words, preferred_sources=EXCLUDED.preferred_sources, "
                    "  hard_nos=EXCLUDED.hard_nos, rhythm=EXCLUDED.rhythm, tools=EXCLUDED.tools, "
                    "  updated_at=now() "
                    "RETURNING name, lawyer_name, tp_number, jurisdiction, practice_areas, "
                    "  voice_adjectives, banned_words, preferred_sources, hard_nos, rhythm, tools, "
                    "  updated_at",
                    {"t": tenant_id, "rhythm": rhythm, **vals})
                return await cur.fetchone()
