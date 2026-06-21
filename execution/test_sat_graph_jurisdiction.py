"""
Mia · test_sat_graph_jurisdiction.py — gate de partición por jurisdicción + versionado
temporal del SAT-Graph (Fase 0.C · Decisión #25, migración 011).

Verifica contra la DB real:
  1. AISLAMIENTO: search_norms/search_jurisprudence con jurisdictions=['co'] encuentran la
     norma 'co' pero NO la 'mx' (y viceversa) → no hay fuga cross-jurisdicción en la salida.
  2. ENFORCEMENT: búsqueda sin jurisdictions y sin admin → ValueError (Decisión #25).
  3. ADMIN: búsqueda con admin=True (curaduría) ve el corpus completo.
  4. VERSIONADO TEMPORAL: add_norm con misma (jurisdiction, norm_number, issuing_body) pero
     distinta effective_date INSERTA una versión nueva (antes el upsert la sobrescribía);
     get_norm_at_date resuelve la vigente a cada fecha.

HALT junto a test_rls.py (aislamiento). Salida: exit 0 = PASS.
    .venv\\Scripts\\python.exe execution\\test_sat_graph_jurisdiction.py
"""
from __future__ import annotations
import asyncio
import os
import sys
from datetime import date
from pathlib import Path

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.db import pool                 # noqa: E402
from mia.rag import SATGraph            # noqa: E402

_results: list[tuple[str, bool]] = []

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)
ISSUING_TEST = "JURTEST_BODY"           # marcador para limpieza
KW = "JURTESTUNICO"                     # palabra clave única para FTS


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def clean_markers() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM jurisprudence WHERE court = 'JURTEST_COURT'")
        c.execute("DELETE FROM legal_norms WHERE issuing_body = %s", (ISSUING_TEST,))


def _raises_valueerror(coro_factory) -> bool:
    try:
        asyncio.get_event_loop().run_until_complete(coro_factory())
        return False
    except ValueError:
        return True
    except Exception:
        return False


async def run_gate() -> None:
    await pool.open_pool()
    try:
        sat = SATGraph()

        # Sembrar la MISMA palabra clave en una norma 'co' y otra 'mx'.
        co_id = await sat.add_norm({
            "norm_type": "ley", "norm_number": "JUR-CO-1", "issuing_body": ISSUING_TEST,
            "title": f"Norma colombiana {KW}", "summary": "", "full_text": "",
            "effective_date": date(2020, 1, 1), "expiry_date": None,
            "jurisdiction": "co", "practice_areas": ["prueba"], "metadata": {"test": True},
        })
        mx_id = await sat.add_norm({
            "norm_type": "ley", "norm_number": "JUR-MX-1", "issuing_body": ISSUING_TEST,
            "title": f"Norma mexicana {KW}", "summary": "", "full_text": "",
            "effective_date": date(2020, 1, 1), "expiry_date": None,
            "jurisdiction": "mx", "practice_areas": ["prueba"], "metadata": {"test": True},
        })
        check("seed: norma 'co' y 'mx' creadas", co_id is not None and mx_id is not None)

        # 1 · AISLAMIENTO en search_norms
        co_res = await sat.search_norms(KW, jurisdictions=["co"])
        co_titles = [r["title"] for r in co_res]
        check("search jurisdictions=['co'] encuentra la norma 'co'",
              any("colombiana" in (t or "") for t in co_titles))
        check("search jurisdictions=['co'] NO devuelve la norma 'mx'",
              all(r["jurisdiction"] == "co" for r in co_res))

        mx_res = await sat.search_norms(KW, jurisdictions=["mx"])
        check("search jurisdictions=['mx'] NO devuelve la norma 'co'",
              all(r["jurisdiction"] == "mx" for r in mx_res)
              and any("mexicana" in (r["title"] or "") for r in mx_res))

        # 2 · ENFORCEMENT: sin jurisdictions y sin admin → ValueError
        raised = False
        try:
            await sat.search_norms(KW)
        except ValueError:
            raised = True
        check("search sin jurisdictions y sin admin -> ValueError", raised)

        raised_j = False
        try:
            await sat.search_jurisprudence(KW)
        except ValueError:
            raised_j = True
        check("search_jurisprudence sin jurisdictions y sin admin -> ValueError", raised_j)

        # 3 · ADMIN: corpus completo (ve ambas)
        admin_res = await sat.search_norms(KW, admin=True)
        jurs = {r["jurisdiction"] for r in admin_res}
        check("search admin=True ve 'co' y 'mx'", {"co", "mx"} <= jurs)

        # 4 · VERSIONADO TEMPORAL: misma clave, distinta effective_date → versión nueva
        v1 = await sat.add_norm({
            "norm_type": "ley", "norm_number": "JUR-VER", "issuing_body": ISSUING_TEST,
            "title": "Norma v1", "summary": "", "full_text": "",
            "effective_date": date(2018, 1, 1), "expiry_date": date(2021, 1, 1),
            "jurisdiction": "co", "practice_areas": [], "metadata": {},
        })
        v2 = await sat.add_norm({
            "norm_type": "ley", "norm_number": "JUR-VER", "issuing_body": ISSUING_TEST,
            "title": "Norma v2", "summary": "", "full_text": "",
            "effective_date": date(2021, 1, 1), "expiry_date": None,
            "jurisdiction": "co", "practice_areas": [], "metadata": {},
        })
        check("versionado: dos effective_date distintas -> dos filas (ids distintos)",
              str(v1) != str(v2))
        async with pool.connection() as conn:
            cnt = (await (await conn.execute(
                "SELECT count(*) FROM legal_norms WHERE norm_number='JUR-VER' AND issuing_body=%s",
                (ISSUING_TEST,))).fetchone())[0]
        check("versionado: la norma conserva 2 versiones (no se sobrescribió)", cnt == 2)

        at_2019 = await sat.get_norm_at_date(v1, date(2019, 6, 1))
        at_2022 = await sat.get_norm_at_date(v2, date(2022, 6, 1))
        check("vigencia: v1 vigente en 2019", at_2019 is not None and at_2019["title"] == "Norma v1")
        check("vigencia: v2 vigente en 2022", at_2022 is not None and at_2022["title"] == "Norma v2")
    finally:
        await pool.close_pool()


def main() -> int:
    print("== Fase 0.C · SAT-Graph partición por jurisdicción + versionado temporal ==")
    clean_markers()
    try:
        asyncio.run(run_gate())
    finally:
        clean_markers()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("SAT-Graph jurisdicción OK — aislamiento + versionado temporal verificados.")
        return 0
    print("SAT-Graph jurisdicción FAIL — HALT (aislamiento cross-jurisdicción).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
