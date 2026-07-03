"""Mia · observability — trazabilidad read-only de las acciones (CP-E1, Ola 5).

Capa de OBSERVADOR (patrón hermes.observer.v1): registra QUÉ pasó, sin alterar el
flujo. Es la contraparte pasiva de `policy/` (control activo). El registro vive en
la tabla `audit_logs` (append-only, RLS por tenant, migración 011).
"""
from . import audit  # noqa: F401
