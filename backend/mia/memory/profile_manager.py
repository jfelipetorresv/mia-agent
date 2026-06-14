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

    def __init__(self, *, abogado: str = "", despacho: str = "") -> None:
        self._abogado = ""
        self._despacho = ""
        self.set_abogado(abogado)
        self.set_despacho(despacho)

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
