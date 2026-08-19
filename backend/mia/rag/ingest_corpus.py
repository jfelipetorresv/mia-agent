"""Mia · rag.ingest_corpus — ingesta del corpus base del SAT-Graph (Módulo 3a).

DEPRECADO a favor de `rag/corpus_factory.py` (Data Factory declarativo, que ingiere el
TEXTO OFICIAL real desde portales del Estado). Este módulo queda por compatibilidad: los
tests (`test_sat_graph.py`) todavía lo usan como semilla mínima y su corpus va marcado
`[VERIFICAR]`. No añadir aquí normas nuevas de producción — el catálogo real crece editando
`packs/{jur}/corpus_sources.json`.

Precarga un corpus mínimo y representativo de Colombia (normas + jurisprudencia +
relaciones) en el SAT-Graph compartido. Idempotente (todo es upsert): re-ejecutarlo no
duplica.

OPT-IN DEL PACK: este corpus es COLOMBIANO, así que NO se siembra solo. `ingest_baseline_corpus`
exige un `jurisdiction` cuyo pack declare `baseline_corpus_seed: true` en `meta.json` (hoy: solo
`co`). Un despacho español o mexicano no recibe estas normas sembradas.

VERIFICACIÓN DE CITAS: estos son DATOS SEMILLA para desarrollo, no citas entregadas a un
cliente. Los datos aproximados o provisionales van marcados con `[VERIFICAR]` en `metadata`
para auditoría contra la fuente primaria (SUIN-Juriscol / la corte respectiva) antes de
cualquier uso real.

BLINDAJE (auditoría 2026-07-17): como el corpus semilla trae jurisprudencia [VERIFICAR] y
fechas aproximadas, `ingest_baseline_corpus` SE NIEGA a correr salvo que la env var
`MIA_ALLOW_SEED_FAKE=1` esté fijada (opt-in explícito de test). Así ningún uso a mano en
producción siembra datos sin confirmar en el SAT-Graph compartido; los tests que lo ejercitan
fijan la env var a propósito.
"""
from __future__ import annotations

import logging
import os
from datetime import date

from ..jurisdiction.pack import load_pack
from .sat_graph import SATGraph

logger = logging.getLogger("mia.rag.ingest_corpus")

# Opt-in EXPLÍCITO de test para sembrar el corpus semilla provisional (ver
# `ingest_baseline_corpus`). Sin esta env var fijada a "1", la función se niega a correr: un
# uso a mano en producción no puede sembrar citas [VERIFICAR] en el SAT-Graph compartido.
SEED_FAKE_ENV = "MIA_ALLOW_SEED_FAKE"

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
    # NOTA (hallazgo de auditoría 2026-07-17): aquí vivía una tercera providencia con
    # `decision_number: "CE-S3-2019-00123"` marcada `placeholder: True` — un identificador de
    # jurisprudencia INVENTADO, sin referencia en fuente alguna. Se ELIMINÓ: un producto legal
    # ("ningún hecho sin fuente; ninguna cita sin verificación") no puede sembrar una cita
    # fabricada ni siquiera como semilla de desarrollo. Las dos providencias restantes son
    # reales (identificadores verificables) y van marcadas [VERIFICAR] pendientes de contraste
    # contra la fuente primaria; el corpus de producción se construye con `corpus_factory.py`
    # (texto oficial real). NO reintroducir identificadores inventados.
]

# ── Relaciones (2): (source_norm_number, target_norm_number, relation_type) ──
_RELATIONS = [
    ("1474 de 2011", "80 de 1993", "modifica_a"),
    ("1082 de 2015", "80 de 1993", "complementa_a"),
]


async def ingest_baseline_corpus(pool=None, jurisdiction: str | None = None) -> dict:
    """Precarga el corpus semilla en el SAT-Graph (upsert idempotente). Devuelve un resumen
    {norms, jurisprudence, relations} — o {..., "skipped": <motivo>} si no se sembró nada.

    OPT-IN EXPLÍCITO DEL PACK (regla de agnosticismo): este corpus es COLOMBIANO. Solo se
    siembra si `jurisdiction` apunta a un pack que declara `baseline_corpus_seed: true` en su
    `meta.json`. Sin `jurisdiction`, con un pack que no lo declare (p. ej. España) o en modo
    genérico → NO se siembra nada: un despacho no recibe el corpus de otro país. El sesgo aquí
    es el contrario al del anonimizador: ante la duda NO se siembra (sembrar derecho ajeno
    desinforma; no sembrar solo deja el corpus vacío).

    `pool`: el pool global `db.pool` ya abierto (lo gestiona el caller); SATGraph accede al
    corpus compartido a través de él. Se acepta por contrato del Módulo 3a; si es None se usa
    el módulo global de todos modos.
    """
    vacio = {"norms": 0, "jurisprudence": 0, "relations": 0}
    if not jurisdiction:
        return {**vacio, "skipped": "sin jurisdicción declarada (el corpus semilla es opt-in)"}
    try:
        pack = load_pack(jurisdiction)
    except Exception:  # noqa: BLE001 — un pack ilegible NO puede terminar sembrando corpus ajeno
        logger.exception("ingest_corpus: pack '%s' ilegible; no se siembra corpus", jurisdiction)
        return {**vacio, "skipped": f"pack '{jurisdiction}' ilegible"}
    if not pack.baseline_corpus_seed:
        return {**vacio,
                "skipped": (f"el pack '{jurisdiction}' no declara baseline_corpus_seed; "
                            "este corpus semilla es de Colombia y no se siembra en otra "
                            "jurisdicción")}

    # BLINDAJE (hallazgo de auditoría 2026-07-17): el corpus semilla contiene DATOS
    # PROVISIONALES — jurisprudencia marcada [VERIFICAR] y fechas aproximadas (no citas
    # verificadas). Correr este módulo a mano (`python -m mia.rag.ingest_corpus co`)
    # sembraría esos datos sin confirmar en el SAT-Graph COMPARTIDO por TODOS los tenants.
    # Por eso solo se permite bajo un opt-in EXPLÍCITO de test (`MIA_ALLOW_SEED_FAKE=1`), que
    # los gates fijan a propósito; cualquier uso a mano en producción falla aquí con un mensaje
    # claro. El corpus real de producción se construye con `rag/corpus_factory.py` (texto
    # oficial descargado, sin [VERIFICAR]).
    if os.getenv(SEED_FAKE_ENV) != "1":
        raise RuntimeError(
            "ingest_baseline_corpus está DESHABILITADO fuera de tests: su corpus semilla "
            "contiene datos provisionales ([VERIFICAR], fechas aproximadas) que NO deben "
            "sembrarse en el SAT-Graph compartido de producción. Usa rag/corpus_factory.py "
            f"(texto oficial real). Los tests que lo necesitan fijan {SEED_FAKE_ENV}=1."
        )

    # La jurisdicción va EXPLÍCITA en cada fila: antes estos dicts no la traían y quedaban
    # marcados por el `COALESCE(..., 'co')` del INSERT. Ese default ya no existe (sat_graph
    # marca 'generic' cuando no se dice), así que sembrar sin decirlo dejaría el corpus
    # semilla sin adscripción — y además duplicaría las filas 'co' ya cargadas, porque la
    # jurisdicción es parte de la clave del upsert.
    sat = SATGraph()
    ids: dict[str, object] = {}
    for n in _NORMS:
        ids[n["norm_number"]] = await sat.add_norm({**n, "jurisdiction": pack.code})
    for j in _JURIS:
        await sat.add_jurisprudence({**j, "jurisdiction": pack.code})
    rel = 0
    for src, tgt, rtype in _RELATIONS:
        await sat.add_relation(ids[src], ids[tgt], rtype)
        rel += 1
    return {"norms": len(_NORMS), "jurisprudence": len(_JURIS), "relations": rel}


async def _run(jurisdiction: str) -> None:
    """Abre el pool global, ingesta el corpus semilla de `jurisdiction` y cierra. Entry point
    del runner. La jurisdicción es EXPLÍCITA: sembrar corpus de un país es una decisión, no un
    efecto colateral de ejecutar un script."""
    from ..db import pool
    await pool.open_pool()
    try:
        summary = await ingest_baseline_corpus(pool, jurisdiction=jurisdiction)
        if summary.get("skipped"):
            print(f"[--] no se sembró nada: {summary['skipped']}")
        else:
            print(f"[OK] corpus semilla ingestado (idempotente): {summary}")
    finally:
        await pool.close_pool()


if __name__ == "__main__":
    # Ejecutar como módulo (imports relativos):
    #   python -m mia.rag.ingest_corpus co
    import asyncio
    import sys

    # psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass
    if len(sys.argv) < 2:
        print("Uso: python -m mia.rag.ingest_corpus <jurisdiccion>   (p. ej. 'co')\n"
              "El corpus semilla es opt-in del pack: hay que decir de qué país se siembra.")
        raise SystemExit(2)
    asyncio.run(_run(sys.argv[1]))
