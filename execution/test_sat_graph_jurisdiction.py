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
  5. DEFAULT DE ESCRITURA NEUTRO (migración 036): escribir sin jurisdicción explícita NO
     marca 'co'. Un despacho español que ingiere queda 'es'; sin despacho ni jurisdicción
     queda 'generic'; el DEFAULT de la columna en la DB ya no es un país. Y el despacho
     colombiano no sufre regresión: sigue marcando 'co' y su material sigue encontrándose.

HALT junto a test_rls.py (aislamiento). Salida: exit 0 = PASS.
    .venv\\Scripts\\python.exe execution\\test_sat_graph_jurisdiction.py
"""
from __future__ import annotations
import asyncio
import os
import sys
from datetime import date
from pathlib import Path
from uuid import uuid4

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
TENANT_TEST = "JURTEST_TENANT"          # marcador de tenants de prueba
MIGRATION_036 = (ROOT / "backend" / "mia" / "db" / "migrations"
                 / "036_jurisdiction_neutral_defaults.sql")


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def clean_markers() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM jurisprudence WHERE court IN ('JURTEST_COURT', 'JURTEST_COURT_ES')")
        c.execute("DELETE FROM legal_norms WHERE issuing_body = %s", (ISSUING_TEST,))
        # tenant_settings cae por FK ON DELETE CASCADE del tenant.
        c.execute("DELETE FROM tenants WHERE name LIKE %s", (TENANT_TEST + "%",))


def make_tenant(label: str, jurisdictions: list[str] | None) -> str:
    """Crea un despacho de prueba con sus jurisdicciones en tenant_settings.
    `jurisdictions=None` → sin config (el resolver cae a ['generic'])."""
    import json
    with psycopg.connect(autocommit=True, **PG) as c:
        tid = c.execute("INSERT INTO tenants(name) VALUES(%s) RETURNING id",
                        (f"{TENANT_TEST} {label}",)).fetchone()[0]
        cfg = {} if jurisdictions is None else {"jurisdictions": jurisdictions}
        c.execute("INSERT INTO tenant_settings(tenant_id, config) VALUES(%s, %s::jsonb)",
                  (tid, json.dumps(cfg)))
    return str(tid)


def jurisdiction_of(norm_id) -> str | None:
    with psycopg.connect(**PG) as c:
        row = c.execute("SELECT jurisdiction FROM legal_norms WHERE id = %s::uuid",
                        (str(norm_id),)).fetchone()
    return row[0] if row else None


def jurisdiction_of_ruling(jid) -> str | None:
    with psycopg.connect(**PG) as c:
        row = c.execute("SELECT jurisdiction FROM jurisprudence WHERE id = %s::uuid",
                        (str(jid),)).fetchone()
    return row[0] if row else None


def column_default(table: str) -> str:
    with psycopg.connect(**PG) as c:
        row = c.execute(
            "SELECT column_default FROM information_schema.columns "
            "WHERE table_schema='public' AND table_name=%s AND column_name='jurisdiction'",
            (table,)).fetchone()
    return (row[0] or "") if row else ""


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

        # === 5 · DEFAULT DE ESCRITURA NEUTRO (migración 036) =================
        # El defecto: `COALESCE(%(jurisdiction)s,'co')` + `DEFAULT 'co'` marcaban COLOMBIANO
        # todo lo que se guardara sin decir la jurisdicción.
        def _sin_jurisdiccion(num: str) -> dict:
            # El título lleva KW para que la búsqueda FTS pueda encontrarla (es lo que se
            # verifica: que el material del despacho aparezca en SU jurisdicción).
            return {"norm_type": "ley", "norm_number": num, "issuing_body": ISSUING_TEST,
                    "title": f"Norma sin jurisdicción {KW} {num}", "summary": "", "full_text": "",
                    "effective_date": date(2020, 1, 1), "expiry_date": None,
                    "practice_areas": [], "metadata": {"test": True}}

        # 5a · el despacho ESPAÑOL ingiere sin jurisdicción explícita → 'es', jamás 'co'.
        t_es = make_tenant("es", ["es"])
        es_id = await sat.add_norm(_sin_jurisdiccion("JUR-DEF-ES"), tenant_id=t_es)
        es_jur = jurisdiction_of(es_id)
        check("despacho español ingiere sin jurisdicción explícita -> NO queda 'co'",
              es_jur != "co")
        check("despacho español ingiere sin jurisdicción explícita -> queda 'es' (su pack)",
              es_jur == "es")

        es_jid = await sat.add_jurisprudence(
            {"norm_id": None, "court": "JURTEST_COURT_ES", "sala": None,
             "decision_number": "JUR-DEF-ES-1", "radicado": None, "magistrado_ponente": None,
             "decision_date": date(2024, 1, 1), "topic": f"Sentencia {KW}",
             "ratio_decidendi": "", "obiter_dicta": None, "keywords": [],
             "metadata": {"test": True}},
            tenant_id=t_es)
        es_rjur = jurisdiction_of_ruling(es_jid)
        check("jurisprudencia del despacho español sin jurisdicción -> NO queda 'co'",
              es_rjur != "co")
        check("jurisprudencia del despacho español sin jurisdicción -> queda 'es'",
              es_rjur == "es")

        # La consecuencia que importaba: su material aparece en SUS búsquedas y no en las
        # del despacho colombiano.
        es_res = await sat.search_norms(KW, jurisdictions=["es"])
        co_res2 = await sat.search_norms(KW, jurisdictions=["co"])
        check("el material del despacho español se encuentra buscando en 'es'",
              any(str(r["id"]) == str(es_id) for r in es_res))
        check("el material del despacho español NO contamina las búsquedas 'co'",
              all(str(r["id"]) != str(es_id) for r in co_res2))

        # 5b · sin despacho y sin jurisdicción → neutro 'generic' (nunca un país supuesto).
        anon_id = await sat.add_norm(_sin_jurisdiccion("JUR-DEF-ANON"))
        anon_jur = jurisdiction_of(anon_id)
        check("sin tenant y sin jurisdicción explícita -> NO queda 'co'", anon_jur != "co")
        check("sin tenant y sin jurisdicción explícita -> queda 'generic' (neutro)",
              anon_jur == "generic")

        # 5c · despacho SIN jurisdicciones configuradas → 'generic', no 'co'.
        t_none = make_tenant("sinconfig", None)
        none_id = await sat.add_norm(_sin_jurisdiccion("JUR-DEF-NONE"), tenant_id=t_none)
        check("despacho sin jurisdicciones configuradas -> 'generic', nunca 'co'",
              jurisdiction_of(none_id) == "generic")

        # 5d · CERO REGRESIÓN del despacho fundador (colombiano).
        t_co = make_tenant("co", ["co"])
        co_def_id = await sat.add_norm(_sin_jurisdiccion("JUR-DEF-CO"), tenant_id=t_co)
        check("despacho colombiano ingiere sin jurisdicción explícita -> sigue quedando 'co'",
              jurisdiction_of(co_def_id) == "co")
        check("la jurisdicción explícita sigue mandando sobre el pack del despacho",
              jurisdiction_of(await sat.add_norm(
                  {**_sin_jurisdiccion("JUR-DEF-MX"), "jurisdiction": "mx"},
                  tenant_id=t_co)) == "mx")
        # El material colombiano preexistente (sembrado arriba con 'co') se sigue encontrando.
        co_res3 = await sat.search_norms(KW, jurisdictions=["co"])
        check("cero regresión: el material 'co' preexistente se sigue encontrando en 'co'",
              any(str(r["id"]) == str(co_id) for r in co_res3))

        # 5e · el DEFAULT de la columna en la DB ya no es un país: un INSERT que omita la
        # columna (fuera del código de sat_graph) cae en 'generic', no en 'co'.
        raw_id = uuid4()
        with psycopg.connect(autocommit=True, **PG) as c:
            c.execute(
                "INSERT INTO legal_norms(id, norm_type, norm_number, issuing_body, title, "
                "effective_date) VALUES(%s::uuid, 'ley', 'JUR-DEF-RAW', %s, 'Raw', %s)",
                (str(raw_id), ISSUING_TEST, date(2020, 1, 1)))
        check("DEFAULT de legal_norms.jurisdiction ya no es un país (INSERT crudo -> generic)",
              jurisdiction_of(raw_id) == "generic")
        check("DEFAULT declarado de legal_norms/jurisprudence/firm_profiles = 'generic'",
              all("generic" in column_default(t) and "'co'" not in column_default(t)
                  for t in ("legal_norms", "jurisprudence", "firm_profiles")))

        # 5f · la migración 036 es idempotente (SET DEFAULT es declarativo).
        idem_ok = True
        try:
            sql_036 = MIGRATION_036.read_text(encoding="utf-8")
            for _ in range(2):
                with psycopg.connect(autocommit=True, **PG) as c:
                    c.execute(sql_036)
        except Exception:  # noqa: BLE001
            idem_ok = False
        check("migración 036 es idempotente (dos corridas seguidas, mismo estado)",
              idem_ok and column_default("legal_norms").startswith("'generic'"))
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
