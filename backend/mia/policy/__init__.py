"""Mia · policy — capa de POLÍTICAS por despacho (CP-E1, Ola 5).

Control ACTIVO por tenant (patrón hermes.middleware.v1): a diferencia del
observador (observability/, read-only), esta capa puede BLOQUEAR o modificar una
acción según las reglas del despacho. v1 entrega el tope de gasto de IA
(policy/budget.py) — turn_usage MEDÍA el gasto (CP-V1) pero nada lo LIMITABA. Es
el hogar donde enchufar futuras reglas por cliente (redacción extra, routing de
modelo, límites de uso) sin tocar el core.
"""
from . import budget  # noqa: F401
