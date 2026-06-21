"""Mia · jurisdiction — paquetes de jurisdicción instalables (Eje 1, Decisión #24).

El código es agnóstico de jurisdicción. Los datos de referencia jurisdiccional
(festivos, recesos, formatos de identificación, marcadores documentales, catálogo de
términos, estilo de cita) viven en `packs/{code}/` como datos, no en el código. Un
despacho SELECCIONA su(s) pack(s) en el onboarding; un país sin pack cae a GenericPack
(modo genérico). Distinto del Eje 2 (conocimiento del despacho: SOUL/wiki/playbooks).
"""
from __future__ import annotations

from .pack import GENERIC_CODE, JurisdictionPack, list_packs, load_pack
from .resolver import resolve_jurisdictions

__all__ = [
    "JurisdictionPack",
    "load_pack",
    "list_packs",
    "resolve_jurisdictions",
    "GENERIC_CODE",
]
