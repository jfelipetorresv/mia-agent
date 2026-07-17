"""
Mia · test_sat_graph.py — gate del Módulo 3a (SAT-Graph · corpus jurídico COMPARTIDO).

Ejercita `mia.rag.SATGraph` contra la DB real (Módulo 0 + migración 003_sat_graph.sql),
sin red (el SAT-Graph no llama al LLM). El corpus es COMPARTIDO entre tenants (decisión
#16): no lleva `tenant_id`, RLS con política abierta `USING(true)`.

Cubre: existencia de tablas · RLS (mia_app SELECT · dos tenants ven el mismo corpus) ·
curaduría (add_norm/add_jurisprudence/add_relation + upsert idempotente) · vigencia
temporal (get_norm_at_date antes/durante/expirada) · relaciones (get_related_norms +
filtro) · cadena recursiva (get_norm_chain simple/hoja/ciclo) · FTS español (acentos) ·
corpus semilla (ingest_corpus).

HALT: si este gate falla, NO se avanza al Módulo 3b/3c (CLAUDE.md §G).
Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_sat_graph.py
"""
from __future__ import annotations
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv

# psycopg async no corre sobre ProactorEventLoop (Windows nativo, Modo B).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

# La consola de PowerShell es cp1252: forzar utf-8 evita un crash al imprimir.
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.db import pool                              # noqa: E402
from mia.rag import SATGraph                         # noqa: E402
from mia.rag.ingest_corpus import ingest_baseline_corpus, _NORMS, _RELATIONS  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── conexión admin (postgres) para limpiar marcadores de prueba ─────────────
PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)

# Marcadores: todas las normas de prueba llevan issuing_body 'SAT_TEST' y la
# jurisprudencia de prueba court 'SAT_TEST_COURT'. La FK de norm_relations es
# ON DELETE CASCADE, así que borrar las normas de prueba arrastra sus relaciones.
ISSUING_TEST = "SAT_TEST"
COURT_TEST = "SAT_TEST_COURT"


def clean_markers() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM jurisprudence WHERE court LIKE 'SAT_TEST%'")
        c.execute("DELETE FROM legal_norms WHERE issuing_body LIKE 'SAT_TEST%'")


def _norm(num: str, *, eff: date, exp: date | None = None, title: str = "") -> dict:
    return {
        "norm_type": "ley", "norm_number": num, "issuing_body": ISSUING_TEST,
        "title": title or f"Norma de prueba {num}", "summary": "", "full_text": "",
        "effective_date": eff, "expiry_date": exp, "practice_areas": ["prueba"],
        "metadata": {"test": True},
    }


async def run_gate() -> None:
    await pool.open_pool()
    try:
        sat = SATGraph()

        # Corpus semilla idempotente (el gate es autónomo; upsert no duplica). La
        # jurisdicción va EXPLÍCITA: el corpus semilla es opt-in del pack ('co').
        await ingest_baseline_corpus(pool, jurisdiction="co")

        # === 1 · existencia de tablas ===
        async with pool.connection() as conn:
            rows = await (await conn.execute(
                "SELECT table_name FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name IN "
                "('legal_norms','norm_relations','jurisprudence')"
            )).fetchall()
        tablas = {r[0] for r in rows}
        check("las 3 tablas del SAT-Graph existen en el schema público",
              tablas == {"legal_norms", "norm_relations", "jurisprudence"})

        # === 2 · RLS: mia_app puede SELECT en las 3 tablas (conexión sin GUC) ===
        select_ok = True
        async with pool.connection() as conn:
            for t in ("legal_norms", "norm_relations", "jurisprudence"):
                try:
                    await (await conn.execute(f"SELECT count(*) FROM {t}")).fetchone()
                except Exception:
                    select_ok = False
        check("mia_app puede SELECT en las 3 tablas del corpus", select_ok)

        # === 3 · corpus COMPARTIDO: dos tenants distintos ven las mismas normas ===
        t1 = "11111111-1111-1111-1111-111111111111"
        t2 = "22222222-2222-2222-2222-222222222222"
        async with pool.tenant_connection(t1) as conn:
            n1 = (await (await conn.execute("SELECT count(*) FROM legal_norms")).fetchone())[0]
        async with pool.tenant_connection(t2) as conn:
            n2 = (await (await conn.execute("SELECT count(*) FROM legal_norms")).fetchone())[0]
        check("dos tenant_id distintos ven el mismo corpus (no es por-tenant)",
              n1 == n2 and n1 >= 5)

        # === 4 · add_norm + retrieve por id (vía get_norm_at_date durante vigencia) ===
        temp_id = await sat.add_norm(_norm("SATT-TEMP", eff=date(2020, 1, 1), exp=date(2022, 1, 1)))
        got = await sat.get_norm_at_date(temp_id, date(2021, 1, 1))
        check("add_norm inserta y se recupera por id", got is not None and str(got["id"]) == str(temp_id))

        # === 5 · add_jurisprudence + retrieve (vía FTS más abajo; aquí inserta sin error) ===
        jid = await sat.add_jurisprudence({
            "norm_id": str(temp_id), "court": COURT_TEST, "sala": "Sala de prueba",
            "decision_number": "TEST_J1", "radicado": None, "magistrado_ponente": None,
            "decision_date": date(2024, 5, 1), "topic": "Tema de prueba SATJURISUNICO",
            "ratio_decidendi": "Ratio de prueba.", "obiter_dicta": None,
            "keywords": ["prueba"], "metadata": {"test": True},
        })
        check("add_jurisprudence inserta y devuelve id", jid is not None)

        # === 6 · add_relation entre dos normas ===
        a_id = await sat.add_norm(_norm("SATT-A", eff=date(2010, 1, 1)))
        b_id = await sat.add_norm(_norm("SATT-B", eff=date(2011, 1, 1)))
        rel_id = await sat.add_relation(a_id, b_id, "modifica_a")
        check("add_relation crea una relación tipada", rel_id is not None)

        # === 7-9 · get_norm_at_date antes / durante / expirada ===
        check("get_norm_at_date: fecha anterior a effective_date -> None",
              (await sat.get_norm_at_date(temp_id, date(2019, 1, 1))) is None)
        check("get_norm_at_date: fecha dentro de la vigencia -> norma",
              (await sat.get_norm_at_date(temp_id, date(2021, 1, 1))) is not None)
        check("get_norm_at_date: fecha posterior a expiry_date -> None",
              (await sat.get_norm_at_date(temp_id, date(2023, 1, 1))) is None)

        # === 10-11 · get_related_norms + filtro por relation_type ===
        rel = await sat.get_related_norms(a_id)
        check("get_related_norms devuelve la norma destino de la relación",
              any(str(r["id"]) == str(b_id) and r["relation_type"] == "modifica_a" for r in rel))
        rel_d = await sat.get_related_norms(a_id, "deroga_a")
        check("get_related_norms filtrado por relation_type inexistente -> vacío", rel_d == [])

        # === 12 · search_norms FTS (palabra clave en el título) ===
        await sat.add_norm(_norm("SATT-FTS", eff=date(2015, 1, 1),
                                 title="Norma de prueba SATGRAPHUNICO sobre cosas"))
        res = await sat.search_norms("SATGRAPHUNICO", jurisdictions=["co"])
        check("search_norms (FTS) encuentra por palabra del título",
              any("SATGRAPHUNICO" in (r["title"] or "") for r in res))

        # === 13 · search_jurisprudence FTS (palabra clave en el topic) ===
        jres = await sat.search_jurisprudence("SATJURISUNICO", jurisdictions=["co"])
        check("search_jurisprudence (FTS) encuentra por palabra del topic",
              any("SATJURISUNICO" in (r["topic"] or "") for r in jres))

        # === 14 · norm_chain simple A -> B -> C (modifica_a) ===
        c_id = await sat.add_norm(_norm("SATT-C", eff=date(2012, 1, 1)))
        await sat.add_relation(b_id, c_id, "modifica_a")
        chain = await sat.get_norm_chain(a_id)
        ids_chain = [str(x["id"]) for x in chain]
        check("get_norm_chain sigue A->B->C por modifica_a",
              ids_chain == [str(a_id), str(b_id), str(c_id)])

        # === 15 · norm_chain de una hoja -> solo ella misma ===
        leaf = await sat.get_norm_chain(c_id)
        check("get_norm_chain de un nodo hoja devuelve solo la raíz",
              len(leaf) == 1 and str(leaf[0]["id"]) == str(c_id))

        # === 16 · norm_chain con ciclo CY1 -> CY2 -> CY1 (no loop infinito) ===
        cy1 = await sat.add_norm(_norm("SATT-CY1", eff=date(2013, 1, 1)))
        cy2 = await sat.add_norm(_norm("SATT-CY2", eff=date(2014, 1, 1)))
        await sat.add_relation(cy1, cy2, "modifica_a")
        await sat.add_relation(cy2, cy1, "modifica_a")
        cyc = await asyncio.wait_for(sat.get_norm_chain(cy1), timeout=10)
        check("get_norm_chain con ciclo termina (guardia de ciclos) y no se repite",
              len(cyc) == 2 and len(cyc) == len({str(x["id"]) for x in cyc}))

        # === 17 · upsert idempotente de norma (misma clave -> mismo id, sin duplicar) ===
        d1 = await sat.add_norm(_norm("SATT-DUP", eff=date(2016, 1, 1)))
        d2 = await sat.add_norm(_norm("SATT-DUP", eff=date(2016, 1, 1)))
        async with pool.connection() as conn:
            dup = (await (await conn.execute(
                "SELECT count(*) FROM legal_norms WHERE norm_number=%s AND issuing_body=%s",
                ("SATT-DUP", ISSUING_TEST))).fetchone())[0]
        check("upsert de norma es idempotente (mismo id, no duplica)",
              str(d1) == str(d2) and dup == 1)

        # === 18 · upsert idempotente de jurisprudencia ===
        j2 = await sat.add_jurisprudence({
            "norm_id": None, "court": COURT_TEST, "sala": None,
            "decision_number": "TEST_J1", "radicado": None, "magistrado_ponente": None,
            "decision_date": date(2024, 5, 1), "topic": "Tema de prueba SATJURISUNICO",
            "ratio_decidendi": "Ratio de prueba.", "obiter_dicta": None,
            "keywords": ["prueba"], "metadata": {"test": True},
        })
        async with pool.connection() as conn:
            jdup = (await (await conn.execute(
                "SELECT count(*) FROM jurisprudence WHERE decision_number=%s AND court=%s",
                ("TEST_J1", COURT_TEST))).fetchone())[0]
        check("upsert de jurisprudencia es idempotente (mismo id, no duplica)",
              str(j2) == str(jid) and jdup == 1)

        # === 19 · corpus semilla: las 5 normas de ingest_corpus están en DB ===
        seed_nums = [n["norm_number"] for n in _NORMS]
        async with pool.connection() as conn:
            seed_cnt = (await (await conn.execute(
                "SELECT count(*) FROM legal_norms WHERE norm_number = ANY(%s)", (seed_nums,)
            )).fetchone())[0]
        check("corpus semilla: las 5 normas base están en la DB", seed_cnt == len(_NORMS))

        # === 20 · corpus semilla: las 2 relaciones base están en DB ===
        seed_src = list({src for src, _t, _r in _RELATIONS})
        async with pool.connection() as conn:
            rel_cnt = (await (await conn.execute(
                "SELECT count(*) FROM norm_relations r JOIN legal_norms s ON s.id=r.source_norm_id "
                "WHERE s.norm_number = ANY(%s)", (seed_src,)
            )).fetchone())[0]
        check("corpus semilla: las 2 relaciones base están en la DB", rel_cnt == len(_RELATIONS))

        # === 21 · FTS español: búsqueda con acento ('protección') encuentra norma ===
        acc = await sat.search_norms("protección", jurisdictions=["co"])
        check("FTS español: 'protección' (con acento) encuentra norma del corpus",
              len(acc) >= 1)
    finally:
        await pool.close_pool()


def main() -> int:
    print("== Módulo 3a · SAT-Graph (corpus jurídico compartido) ==")
    clean_markers()
    try:
        asyncio.run(run_gate())
    finally:
        clean_markers()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("SAT-Graph OK — Módulo 3a verificado.")
        return 0
    print("SAT-Graph FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
