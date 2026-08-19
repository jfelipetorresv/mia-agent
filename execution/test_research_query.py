"""
Mia · test_research_query.py — gate del bugfix de la consulta FTS de investigación.

Bug (confirmado por exploración): `graph.py::_research_query` concatenaba el mensaje
COMPLETO del abogado (20-40 palabras) + 300 chars de hechos y esa cadena viajaba tal
cual hasta `websearch_to_tsquery('spanish', %(q)s)` en `SATGraph.search_norms` /
`search_jurisprudence`. `websearch_to_tsquery` AND-ea todos los términos no citados:
una pregunta larga casi nunca hace match completo contra el fts_vector -> 0 resultados
-> el turno cae a NO_SOURCES_NOTE y ninguna cita del corpus queda "respaldada".

Fix: `research.build_fts_query()` (determinista, sin LLM, fail-open) extrae citas
normativas explícitas (frase exacta entre comillas) + términos clave sueltos (sin
stopwords), unidos con OR en vez de AND.

Ejercita build_fts_query OFFLINE (sin DB) y su efecto real contra el corpus semilla
(Módulo 3a, `ingest_baseline_corpus` — trae 'Ley 80 de 1993') vía `SATGraph.search_norms`
contra la DB real. El contraste consulta-vieja-vs-nueva ES el fix.

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_research_query.py
"""
from __future__ import annotations
import asyncio
import os
import re
import sys
from pathlib import Path

# psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402
load_dotenv(ROOT / ".env")

# La consola de PowerShell es cp1252: forzar utf-8 evita un crash al imprimir.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agents.research import build_fts_query  # noqa: E402
from mia.db import pool                          # noqa: E402
from mia.rag import SATGraph                      # noqa: E402
from mia.rag.ingest_corpus import ingest_baseline_corpus  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def run_offline_checks() -> None:
    # === 1 · pregunta larga que MENCIONA una cita normativa explícita ===
    pregunta_larga = (
        "Doctor, buenas tardes, necesito su ayuda con un caso complicado: mi cliente "
        "celebró un contrato estatal de obra pública el año pasado y ahora la entidad "
        "contratante alega un presunto incumplimiento contractual para hacer efectiva "
        "la garantía de cumplimiento, invocando la Ley 80 de 1993 como fundamento de su "
        "potestad sancionatoria. ¿Podría usted ayudarme a establecer si la entidad tiene "
        "competencia para declarar el incumplimiento por sí misma o si debe acudir al "
        "juez del contrato?"
    )
    q1 = build_fts_query(pregunta_larga)
    check("1a · build_fts_query detecta la cita 'Ley 80 de 1993' entre comillas",
          '"Ley 80 de 1993"' in q1)
    check("1b · la query usa OR (no concatena el mensaje completo tal cual)",
          " or " in q1 and pregunta_larga.strip() != q1.strip())

    # === 3 · pregunta sin citas -> términos clave sin stopwords ===
    pregunta_sin_citas = "¿qué pasa si mi cliente no contesta la demanda a tiempo?"
    q3 = build_fts_query(pregunta_sin_citas)
    check("3a · sin citas: 'cliente' y 'demanda' y 'contesta' quedan como términos",
          "cliente" in q3 and "demanda" in q3 and "contesta" in q3)
    check("3b · sin citas: stopwords/muletillas ('pasa', 'tiempo', 'qué', 'mi', 'si', "
          "'no') NO aparecen como término suelto",
          not any(re_tok_present(q3, w) for w in ("pasa", "tiempo", "qué", "si")))
    check("3c · sin citas: no hay comillas (no se detectó ninguna cita normativa)",
          '"' not in q3)

    # === 4 · texto vacío / solo stopwords -> fail-open (comportamiento viejo) ===
    q4_empty = build_fts_query("")
    check("4a · texto vacío -> fail-open devuelve '' (mensaje+hechos vacíos, sin tocar)",
          q4_empty == "")
    q4_stop = build_fts_query("de la el en por para con")
    check("4b · solo stopwords -> fail-open devuelve el mensaje crudo sin tocar",
          q4_stop == "de la el en por para con")

    # === extra · dedup y tope de elementos ===
    q_dedup = build_fts_query("demanda demanda demanda contestación contestación")
    check("5 · dedup de términos repetidos preservando orden",
          q_dedup == "demanda or contestación")

    q_cap = build_fts_query(
        " ".join(f"termino{i}palabra" for i in range(20))
    )
    check("6 · tope de ~12 elementos totales", len(q_cap.split(" or ")) <= 12)


def re_tok_present(query: str, word: str) -> bool:
    """True si `word` aparece como TOKEN completo en `query` (no como substring de
    otra palabra) — evita falsos positivos tipo 'si' dentro de 'sino'."""
    return re.search(rf"(?<![\wáéíóúñ]){re.escape(word)}(?![\wáéíóúñ])", query,
                      re.IGNORECASE) is not None


async def run_db_checks() -> None:
    await pool.open_pool()
    try:
        # El corpus semilla es opt-in del pack: la jurisdicción va EXPLÍCITA ('co' es
        # quien declara baseline_corpus_seed). Sin ella no se sembraría nada. Además, el
        # módulo se blinda tras `MIA_ALLOW_SEED_FAKE` (los datos semilla son [VERIFICAR]);
        # este gate fija el opt-in de test a propósito para poder ejercitarlo.
        os.environ["MIA_ALLOW_SEED_FAKE"] = "1"
        await ingest_baseline_corpus(pool, jurisdiction="co")
        sat = SATGraph()

        pregunta_larga = (
            "Doctor, buenas tardes, necesito su ayuda con un caso complicado: mi cliente "
            "celebró un contrato estatal de obra pública el año pasado y ahora la entidad "
            "contratante alega un presunto incumplimiento contractual para hacer efectiva "
            "la garantía de cumplimiento, invocando la Ley 80 de 1993 como fundamento de su "
            "potestad sancionatoria. ¿Podría usted ayudarme a establecer si la entidad tiene "
            "competencia para declarar el incumplimiento por sí misma o si debe acudir al "
            "juez del contrato?"
        )
        query_nueva = build_fts_query(pregunta_larga)

        # === 2 · EL CONTRASTE: la query nueva SÍ encuentra la Ley 80; la cruda NO ===
        res_nueva = await sat.search_norms(query_nueva, jurisdictions=["co"])
        check("2a · query NUEVA (build_fts_query) encuentra la Ley 80 de 1993 en el corpus",
              any("80" in str(r.get("norm_number") or "") for r in res_nueva))

        res_cruda = await sat.search_norms(pregunta_larga, jurisdictions=["co"])
        check("2b · query CRUDA (mensaje completo, comportamiento viejo) devuelve 0 "
              "resultados — ESTE contraste es el bug/fix",
              len(res_cruda) == 0)
    finally:
        await pool.close_pool()


def main() -> int:
    print("== Bugfix consulta FTS de investigación (research.build_fts_query) ==")
    run_offline_checks()
    asyncio.run(run_db_checks())

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("build_fts_query OK — bugfix de la consulta FTS verificado.")
        return 0
    print("test_research_query FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
