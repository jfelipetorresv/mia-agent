"""Mia · memory.tokens — estimación de tokens OFFLINE para presupuestos.

Heurística determinista (~4 caracteres/token). NO iguala el tokenizer de Anthropic
(el conteo exacto lo da el gateway aguas arriba); es un guardarraíl local que
permite hacer cumplir presupuestos y que los gates corran sin red.
"""
from __future__ import annotations

import math


def estimate_tokens(text: str) -> int:
    """Estimación offline y determinista de tokens (~4 caracteres por token)."""
    if not text:
        return 0
    return math.ceil(len(text) / 4)
