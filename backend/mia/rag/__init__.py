"""Mia · rag — recuperación sobre el corpus jurídico compartido (SAT-Graph, Módulo 3a).

`SATGraph` da acceso de lectura (y curaduría) al corpus COMPARTIDO entre tenants
(`legal_norms`, `norm_relations`, `jurisprudence`). NO es dato por-tenant (decisión #16):
las normas y sentencias de Colombia son públicas. Ver architecture/rls_isolation.md.
"""
from .sat_graph import SATGraph

__all__ = ["SATGraph"]
