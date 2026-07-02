"""Mia · cron.blueprints — catálogo de plantillas de automatización (CP-P2, Ola 2).

Una *plantilla* (blueprint) es la definición ÚNICA de una automatización que el abogado
rellena SIN jerga: cada plantilla tiene campos con etiquetas en español ("¿cuántos días
antes?") y produce una automatización concreta. Es la única fuente de verdad — el
frontend la pinta como formulario, el gate la valida, y `fill_blueprint` la convierte en
el `spec` que guarda AutomationService (no hay un segundo motor de automatización).

REGLA DURA (regla 5 del propietario): una plantilla que toca un PLAZO PROCESAL
(`is_procedural=True`) jamás se auto-activa ni calcula un término. Solo se ofrece como
SUGERENCIA que el abogado acepta a mano (consent-first, suggestions.py), y al ejecutarse
solo superficie fechas que él ya fijó, con [VERIFICAR] (igual que la vigilancia de CP-P1).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Tipos de campo que el formulario entiende (sin jerga técnica hacia el abogado).
SLOT_TYPES = frozenset({"entero", "texto", "opcion"})


class BlueprintFillError(ValueError):
    """Los valores dados para una plantilla no pasan la validación."""


@dataclass(frozen=True)
class BlueprintSlot:
    """Un campo rellenable de una plantilla."""
    name: str
    type: str
    label: str                       # etiqueta en español para el abogado
    default: Any = None
    options: tuple = ()              # para type="opcion": valores permitidos
    min: Optional[int] = None        # para type="entero"
    max: Optional[int] = None
    help: str = ""


@dataclass(frozen=True)
class Blueprint:
    """Una plantilla de automatización parametrizable."""
    key: str
    kind: str                        # tipo de automatización que produce
    display_name: str                # nombre en español (§G, sin jerga)
    description: str
    is_procedural: bool              # ¿toca un plazo procesal? → consent-first obligatorio
    slots: tuple[BlueprintSlot, ...] = ()


# ── el catálogo ──────────────────────────────────────────────────────────────
# Cada plantilla se ata a una capacidad REAL (una vigilancia que la lee); nada aquí es
# decorativo. Las procesales llevan is_procedural=True.
CATALOG: dict[str, Blueprint] = {
    "deadline_heads_up": Blueprint(
        key="deadline_heads_up",
        kind="deadline_heads_up",
        display_name="Avísame antes de un vencimiento",
        description=("Mia te avisa con anticipación de los plazos que TÚ ya fijaste en tus "
                     "recordatorios. No calcula términos: solo te recuerda lo que registraste, "
                     "y el aviso siempre lleva [VERIFICAR]."),
        is_procedural=True,
        slots=(
            BlueprintSlot("dias_antes", "entero", "¿Cuántos días antes quieres el aviso?",
                          default=3, min=1, max=30,
                          help="Entre 1 y 30 días. Por defecto, 3."),
        ),
    ),
    "calendar_heads_up": Blueprint(
        key="calendar_heads_up",
        kind="calendar_heads_up",
        display_name="Anticipación de avisos del calendario",
        description=("Elige con cuánta anticipación quieres que Mia te avise de los eventos "
                     "próximos de tu calendario (audiencias, reuniones). No toca plazos ni "
                     "calcula nada: solo ajusta cuánto se adelanta el aviso."),
        is_procedural=False,
        slots=(
            BlueprintSlot("dias_antes", "entero", "¿Con cuántos días de anticipación te aviso?",
                          default=2, min=1, max=14,
                          help="Entre 1 y 14 días. Por defecto, 2."),
        ),
    ),
}


def get_blueprint(key: str) -> Optional[Blueprint]:
    return CATALOG.get(key)


def catalog_entries() -> list[dict]:
    """Catálogo para el frontend: cada plantilla con sus campos (etiquetas en español)."""
    out = []
    for bp in CATALOG.values():
        out.append({
            "key": bp.key,
            "nombre": bp.display_name,
            "descripcion": bp.description,
            "toca_plazo_procesal": bp.is_procedural,
            "campos": [
                {"name": s.name, "tipo": s.type, "etiqueta": s.label, "default": s.default,
                 "opciones": list(s.options), "min": s.min, "max": s.max, "ayuda": s.help}
                for s in bp.slots
            ],
        })
    return out


def _validate_slot(slot: BlueprintSlot, raw: Any) -> Any:
    """Valida y normaliza UN valor contra su campo. Lanza BlueprintFillError si no cuadra."""
    if raw is None:
        if slot.default is not None:
            return slot.default
        raise BlueprintFillError(f"Falta un valor para «{slot.label}».")
    if slot.type == "entero":
        try:
            val = int(raw)
        except (TypeError, ValueError):
            raise BlueprintFillError(f"«{slot.label}» debe ser un número entero.")
        if slot.min is not None and val < slot.min:
            raise BlueprintFillError(f"«{slot.label}» no puede ser menor que {slot.min}.")
        if slot.max is not None and val > slot.max:
            raise BlueprintFillError(f"«{slot.label}» no puede ser mayor que {slot.max}.")
        return val
    if slot.type == "opcion":
        if slot.options and str(raw) not in [str(o) for o in slot.options]:
            raise BlueprintFillError(f"«{slot.label}»: opción no válida.")
        return str(raw)
    return str(raw)  # texto


def fill_blueprint(key: str, values: Optional[dict]) -> dict:
    """Valida los valores dados y devuelve el `spec` de la automatización.

    Devuelve {"blueprint_key", "kind", "is_procedural", "params"}. Lanza
    BlueprintFillError si algún campo no valida. NO ejecuta ni agenda nada — solo
    construye el spec que AutomationService.create persistirá (consent-first: el que
    crea la automatización es un acto humano explícito, nunca este módulo)."""
    bp = CATALOG.get(key)
    if bp is None:
        raise BlueprintFillError(f"Plantilla desconocida: {key}")
    values = dict(values or {})
    params = {slot.name: _validate_slot(slot, values.get(slot.name)) for slot in bp.slots}
    return {"blueprint_key": bp.key, "kind": bp.kind,
            "is_procedural": bp.is_procedural, "params": params}
