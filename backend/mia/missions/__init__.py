"""Mia · missions — tablero de misión por expediente (CP-E5, Ola 5).

Descompone un objetivo grande del expediente ("preparar la contestación") en HITOS
visibles que el abogado ve, edita y avanza a mano (consent-first). `decompose` propone los
hitos (LLM auxiliar barato + guardas jurídicas duras); `service` los persiste y gobierna bajo
RLS por despacho. Nada se auto-ejecuta: el tablero es planeación visible, no un ejecutor.
"""
from . import decompose, service  # noqa: F401

mission_service = service.mission_service  # instancia compartida (re-export)
