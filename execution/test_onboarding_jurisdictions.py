"""
Mia · test_onboarding_jurisdictions.py — gate de selección/persistencia de jurisdicción
(Fase 0.C). Verifica:
  1. OPCIONES no hardcodeadas: se derivan de los packs instalados + 'generic' (Decisión #22).
  2. PERSISTENCIA + RESOLVER (round-trip DB): un tenant con jurisdictions en tenant_settings
     resuelve a esos códigos; sin config → ['generic'] (modo genérico, fail-soft).

    .venv\\Scripts\\python.exe execution\\test_onboarding_jurisdictions.py
"""
from __future__ import annotations
import asyncio
import os
import sys
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

from mia.db import pool                                       # noqa: E402
from mia.jurisdiction.pack import GENERIC_CODE, list_packs, load_pack  # noqa: E402
from mia.jurisdiction.resolver import resolve_jurisdictions   # noqa: E402

_results: list[tuple[str, bool]] = []

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)
T_WITH = "aaaaaaaa-0000-4000-8000-00000000ab01"   # tenant con jurisdicciones
T_NONE = "aaaaaaaa-0000-4000-8000-00000000ab02"   # tenant sin config


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def seed() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for t in (T_WITH, T_NONE):
            c.execute("INSERT INTO tenants (id, name) VALUES (%s::uuid, %s) "
                      "ON CONFLICT (id) DO NOTHING", (t, f"jurtest-{t[-4:]}"))
        c.execute("INSERT INTO tenant_settings (tenant_id, config) VALUES (%s::uuid, %s::jsonb) "
                  "ON CONFLICT (tenant_id) DO UPDATE SET config = EXCLUDED.config",
                  (T_WITH, '{"jurisdictions": ["co", "mx"]}'))
        # T_NONE: sin fila en tenant_settings (resolver debe caer a generic)
        c.execute("DELETE FROM tenant_settings WHERE tenant_id = %s::uuid", (T_NONE,))


def cleanup() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for t in (T_WITH, T_NONE):
            c.execute("DELETE FROM tenant_settings WHERE tenant_id = %s::uuid", (t,))
            c.execute("DELETE FROM tenants WHERE id = %s::uuid", (t,))


def _options() -> list[dict]:
    opts = [{"code": c, "name": load_pack(c).name} for c in list_packs()]
    opts.append({"code": GENERIC_CODE, "name": "Otra / modo genérico"})
    return opts


async def run_db() -> None:
    await pool.open_pool()
    try:
        got = await resolve_jurisdictions(T_WITH)
        check("resolver: tenant con config -> ['co','mx']", got == ["co", "mx"])
        none = await resolve_jurisdictions(T_NONE)
        check("resolver: tenant sin config -> ['generic'] (fail-soft)", none == [GENERIC_CODE])
    finally:
        await pool.close_pool()


def main() -> int:
    print("== Fase 0.C · onboarding: opciones y persistencia de jurisdicción ==")
    # 1 · opciones derivadas de packs (offline)
    codes = [o["code"] for o in _options()]
    check("opciones incluyen el pack 'co'", "co" in codes)
    check("opciones incluyen 'generic' (modo genérico)", GENERIC_CODE in codes)
    check("opciones NO hardcodean países sin pack (p. ej. 'ar' no instalado)", "ar" not in codes)

    # 2 · persistencia + resolver (DB)
    seed()
    try:
        asyncio.run(run_db())
    finally:
        cleanup()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Onboarding jurisdicciones OK — opciones + persistencia + resolver verificados.")
        return 0
    print("Onboarding jurisdicciones FAIL.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
