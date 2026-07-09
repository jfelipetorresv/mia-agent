"""Mia · rag.ingest_corpus — ingesta del corpus base del SAT-Graph (Módulo 3a).

DEPRECADO a favor de `rag/corpus_factory.py` (Data Factory declarativo, que ingiere el
TEXTO OFICIAL real desde portales del Estado). Este módulo queda por compatibilidad: los
tests (`test_sat_graph.py`) todavía lo usan como semilla mínima y su corpus va marcado
`[VERIFICAR]`. No añadir aquí normas nuevas de producción — el catálogo real crece editando
`packs/{jur}/corpus_sources.json`.

Precarga un corpus mínimo y representativo de Colombia (normas + jurisprudencia +
relaciones) en el SAT-Graph compartido. Idempotente (todo es upsert): re-ejecutarlo no
duplica.

VERIFICACIÓN DE CITAS: estos son DATOS SEMILLA para desarrollo, no citas entregadas a un
cliente. Los datos aproximados o provisionales van marcados con `[VERIFICAR]` en `metadata`
para auditoría contra la fuente primaria (SUIN-Juriscol / la corte respectiva) antes de
cualquier uso real.
"""
from __future__ import annotations

from datetime import date

from .sat_graph import SATGraph

# ── Normas (5) ──────────────────────────────────────────────────────────────
_NORMS = [
    {
        "norm_type": "ley", "norm_number": "1581 de 2012",
        "issuing_body": "Congreso de la República",
        "title": "Ley 1581 de 2012 — Régimen general de protección de datos personales",
        "summary": ("Dicta disposiciones generales para la protección de datos personales; "
                    "desarrolla el derecho de hábeas data (art. 15 C.P.) y regula el "
                    "tratamiento de datos personales por entidades públicas y privadas."),
        "full_text": "",
        "effective_date": date(2012, 10, 17),
        "practice_areas": ["datos", "privacidad"],
        "metadata": {"nota": "[VERIFICAR] contra el texto oficial (SUIN-Juriscol)"},
    },
    {
        "norm_type": "ley", "norm_number": "80 de 1993",
        "issuing_body": "Congreso de la República",
        "title": "Ley 80 de 1993 — Estatuto General de Contratación de la Administración Pública",
        "summary": ("Expide el Estatuto General de Contratación de la Administración Pública; "
                    "fija los principios y reglas de los contratos estatales."),
        "full_text": "",
        "effective_date": date(1993, 10, 28),
        "practice_areas": ["contratacion", "fiscal"],
        "metadata": {"nota": "[VERIFICAR] contra el texto oficial (SUIN-Juriscol)"},
    },
    {
        "norm_type": "ley", "norm_number": "610 de 2000",
        "issuing_body": "Congreso de la República",
        "title": "Ley 610 de 2000 — Trámite de los procesos de responsabilidad fiscal",
        "summary": ("Establece el trámite de los procesos de responsabilidad fiscal de "
                    "competencia de las contralorías y define sus elementos (daño patrimonial "
                    "al Estado, conducta dolosa o gravemente culposa, nexo causal)."),
        "full_text": "",
        "effective_date": date(2000, 8, 18),
        "practice_areas": ["fiscal", "contencioso"],
        "metadata": {"nota": "[VERIFICAR] contra el texto oficial (SUIN-Juriscol)"},
    },
    {
        "norm_type": "ley", "norm_number": "1474 de 2011",
        "issuing_body": "Congreso de la República",
        "title": "Ley 1474 de 2011 — Estatuto Anticorrupción",
        "summary": ("Dicta normas para fortalecer la prevención, investigación y sanción de "
                    "actos de corrupción y la efectividad del control de la gestión pública. "
                    "El art. 86 regula el procedimiento administrativo sancionatorio "
                    "contractual (PASC) para imponer multas, sanciones y declaratorias de "
                    "incumplimiento."),
        "full_text": "",
        "effective_date": date(2011, 7, 12),
        "practice_areas": ["fiscal", "contratacion", "sancionatorio"],
        "metadata": {"articulo_clave": "86 (PASC)",
                     "nota": "[VERIFICAR] alcance del art. 86 contra el texto oficial"},
    },
    {
        "norm_type": "decreto", "norm_number": "1082 de 2015",
        "issuing_body": "Presidencia de la República",
        "title": ("Decreto 1082 de 2015 — Decreto Único Reglamentario del Sector "
                  "Administrativo de Planeación Nacional"),
        "summary": ("Compila y reglamenta, entre otras materias, el sistema de compras y "
                    "contratación pública; es el decreto único reglamentario aplicable a la "
                    "contratación estatal."),
        "full_text": "",
        "effective_date": date(2015, 5, 26),
        "practice_areas": ["contratacion"],
        "metadata": {"nota": "[VERIFICAR] contra el texto oficial (Función Pública)"},
    },
]

# ── Jurisprudencia (3) ──────────────────────────────────────────────────────
_JURIS = [
    {
        "court": "Corte Constitucional", "sala": "Sala de Revisión",
        "decision_number": "T-323/2024", "radicado": None,
        "magistrado_ponente": None,
        "decision_date": date(2024, 1, 1),   # fecha aproximada — ver metadata
        "topic": "Uso de IA en la Rama Judicial",
        "ratio_decidendi": ("[VERIFICAR] Reglas sobre el uso de herramientas de inteligencia "
                            "artificial por los jueces, que no sustituyen el razonamiento "
                            "judicial ni el debido proceso."),
        "obiter_dicta": None,
        "keywords": ["inteligencia artificial", "rama judicial", "debido proceso"],
        "metadata": {"fecha_aproximada": True,
                     "nota": "[VERIFICAR] fecha exacta y ratio contra la Corte Constitucional"},
    },
    {
        "court": "Corte Suprema de Justicia", "sala": "Sala de Casación Civil",
        "decision_number": "SC1983-2025",
        "radicado": "08001-31-53-012-2022-00046-01",
        "magistrado_ponente": "Octavio Augusto Tejeiro Duque",
        "decision_date": date(2025, 11, 7),
        "topic": "Seguros de cumplimiento",
        "ratio_decidendi": ("[VERIFICAR] Tesis sobre el contrato de seguro de cumplimiento y "
                            "la configuración del siniestro."),
        "obiter_dicta": None,
        "keywords": ["seguro de cumplimiento", "contrato de seguro", "siniestro"],
        "metadata": {"nota": "[VERIFICAR] contra la providencia oficial (CSJ)"},
    },
    {
        "court": "Consejo de Estado", "sala": "Sección Tercera",
        "decision_number": "CE-S3-2019-00123", "radicado": None,
        "magistrado_ponente": None,
        "decision_date": date(2019, 6, 15),
        "topic": "Responsabilidad fiscal — elementos constitutivos",
        "ratio_decidendi": ("[VERIFICAR] Elementos constitutivos de la responsabilidad fiscal: "
                            "daño patrimonial al Estado, conducta y nexo causal."),
        "obiter_dicta": None,
        "keywords": ["responsabilidad fiscal", "daño patrimonial", "nexo causal"],
        "metadata": {"placeholder": True,
                     "nota": "[VERIFICAR] identificador y datos PROVISIONALES (sin referencia "
                             "en el corpus de Hermes)"},
    },
]

# ── Relaciones (2): (source_norm_number, target_norm_number, relation_type) ──
_RELATIONS = [
    ("1474 de 2011", "80 de 1993", "modifica_a"),
    ("1082 de 2015", "80 de 1993", "complementa_a"),
]


async def ingest_baseline_corpus(pool=None) -> dict:
    """Precarga el corpus base en el SAT-Graph (upsert idempotente). Devuelve un resumen
    {norms, jurisprudence, relations}.

    `pool`: el pool global `db.pool` ya abierto (lo gestiona el caller); SATGraph accede al
    corpus compartido a través de él. Se acepta por contrato del Módulo 3a; si es None se usa
    el módulo global de todos modos.
    """
    sat = SATGraph()
    ids: dict[str, object] = {}
    for n in _NORMS:
        ids[n["norm_number"]] = await sat.add_norm(n)
    for j in _JURIS:
        await sat.add_jurisprudence(j)
    rel = 0
    for src, tgt, rtype in _RELATIONS:
        await sat.add_relation(ids[src], ids[tgt], rtype)
        rel += 1
    return {"norms": len(_NORMS), "jurisprudence": len(_JURIS), "relations": rel}


async def _run() -> None:
    """Abre el pool global, ingesta el corpus base y cierra. Entry point del runner."""
    from ..db import pool
    await pool.open_pool()
    try:
        summary = await ingest_baseline_corpus(pool)
        print(f"[OK] corpus base ingestado (idempotente): {summary}")
    finally:
        await pool.close_pool()


if __name__ == "__main__":
    # Ejecutar como módulo (imports relativos):  python -m mia.rag.ingest_corpus
    import asyncio
    import sys

    # psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    asyncio.run(_run())
