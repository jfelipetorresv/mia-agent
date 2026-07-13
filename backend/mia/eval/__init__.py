"""Mia · eval — banco de pruebas de calidad (eval harness, CP-E4, Ola 5).

Corre Mia sobre un set de CASOS DE ORO y mide señales OBJETIVAS de calidad jurídica
(sin LLM-juez: todo determinista), para saber si un cambio la MEJORA o la EMPEORA antes
de mergearlo. Ref Hermes `batch_runner.py` (correr el agente en batch sobre casos) +
`trajectory_compressor.py` (métricas por corrida), traído al grafo de asunto de Mia.

Regla dura (decisión de Pipe, plan de olas): los casos de oro de v1 son SINTÉTICOS
(`cases.py`) — NO datos reales de cliente. Correr el eval sobre expedientes REALES del
despacho exige consentimiento explícito (`allow_eval_real_data`, fail-closed) — ver
`harness.read_eval_policy`.
"""
from .cases import GOLDEN_CASES, GoldenCase, load_golden_cases, load_tenant_gold_cases
from .compare import compare_reports
from .scoring import score_turn, substantive_score

__all__ = [
    "GOLDEN_CASES",
    "GoldenCase",
    "load_golden_cases",
    "load_tenant_gold_cases",
    "compare_reports",
    "score_turn",
    "substantive_score",
]
