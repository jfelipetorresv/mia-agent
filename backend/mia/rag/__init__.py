"""Mia · rag — recuperación sobre el corpus jurídico compartido (SAT-Graph, Módulo 3a).

`SATGraph` da acceso de lectura (y curaduría) al corpus COMPARTIDO entre tenants
(`legal_norms`, `norm_relations`, `jurisprudence`). NO es dato por-tenant (decisión #16):
las normas y las providencias son derecho público, sea cual sea la jurisdicción del
despacho. Lo que separa el corpus de un despacho del de otro NO es el tenant sino la
JURISDICCIÓN (decisión #25): toda búsqueda va acotada a la(s) del despacho, y toda
escritura queda marcada con una jurisdicción explícita o neutra ('generic') — nunca con un
país supuesto. Ver architecture/rls_isolation.md.
"""
from .sat_graph import SATGraph

__all__ = ["SATGraph"]
