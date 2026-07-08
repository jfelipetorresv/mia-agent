"""
Mia · test_onboarding_draft.py — gate del borrador persistido del onboarding (Fase 2).

El wizard guarda el avance parcial de la entrevista en tenant_settings
(config.onboarding.draft) para que recargar o cerrar el navegador no pierda
lo contestado. Verifica:
  1. ROUND-TRIP: guardar → leer devuelve responses + idx.
  2. SOBRESCRITURA: un guardado nuevo pisa el anterior (autosave).
  3. LIMPIEZA: completar la entrevista borra el borrador (None).
  4. DEFENSIVO: config con basura en 'onboarding' → load devuelve None, no explota.
  5. AISLAMIENTO RLS: el borrador del despacho A no es visible desde el B.
  6. CONTRATO: el endpoint /onboarding/draft existe con tope de tamaño y clamp
     del índice, el status expone 'draft' y complete limpia el borrador.

    .venv\\Scripts\\python.exe execution\\test_onboarding_draft.py
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

from mia.api.routes.ux import (  # noqa: E402
    MAX_ONBOARDING_DRAFT_CHARS,
    _load_onboarding_draft,
    _save_onboarding_draft,
)
from mia.db import pool  # noqa: E402

_results: list[tuple[str, bool]] = []

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)
T_A = "aaaaaaaa-0000-4000-8000-00000000db01"   # despacho A (con borrador)
T_B = "aaaaaaaa-0000-4000-8000-00000000db02"   # despacho B (aislamiento)


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def seed() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for t in (T_A, T_B):
            c.execute("INSERT INTO tenants (id, name) VALUES (%s::uuid, %s) "
                      "ON CONFLICT (id) DO NOTHING", (t, f"drafttest-{t[-4:]}"))
            c.execute("DELETE FROM tenant_settings WHERE tenant_id = %s::uuid", (t,))


def cleanup() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for t in (T_A, T_B):
            c.execute("DELETE FROM tenant_settings WHERE tenant_id = %s::uuid", (t,))


async def run_checks() -> None:
    await pool.open_pool()
    # 1 · round-trip
    draft = {"responses": {"p1": "Despacho Prueba / Dra. Prueba", "_jurisdicciones": ["co"]}, "idx": 3}
    await _save_onboarding_draft(T_A, draft)
    loaded = await _load_onboarding_draft(T_A)
    check("round-trip: responses vuelve intacto",
          loaded is not None and loaded.get("responses", {}).get("p1") == "Despacho Prueba / Dra. Prueba")
    check("round-trip: idx vuelve intacto", loaded is not None and loaded.get("idx") == 3)
    check("round-trip: clave reservada _jurisdicciones persiste",
          loaded is not None and loaded.get("responses", {}).get("_jurisdicciones") == ["co"])

    # 2 · sobrescritura (autosave pisa lo anterior)
    await _save_onboarding_draft(T_A, {"responses": {"p1": "v2"}, "idx": 5})
    loaded = await _load_onboarding_draft(T_A)
    check("autosave sobrescribe el borrador anterior",
          loaded is not None and loaded.get("idx") == 5 and loaded["responses"].get("p1") == "v2"
          and "_jurisdicciones" not in loaded["responses"])

    # 2b · el guardado NO pisa otras claves del config del tenant
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("UPDATE tenant_settings SET config = jsonb_set(config, '{jurisdictions}', "
                  "'[\"co\"]'::jsonb, true) WHERE tenant_id = %s::uuid", (T_A,))
    await _save_onboarding_draft(T_A, {"responses": {"p1": "v3"}, "idx": 1})
    with psycopg.connect(autocommit=True, **PG) as c:
        row = c.execute("SELECT config->'jurisdictions' FROM tenant_settings "
                        "WHERE tenant_id = %s::uuid", (T_A,)).fetchone()
    check("guardar borrador conserva otras claves del config (jurisdictions)",
          row is not None and row[0] == ["co"])

    # 3 · limpieza al completar
    await _save_onboarding_draft(T_A, None)
    check("completar limpia el borrador (load → None)",
          await _load_onboarding_draft(T_A) is None)

    # 4 · defensivo: basura en config.onboarding no explota ni devuelve basura
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("UPDATE tenant_settings SET config = jsonb_set(config, '{onboarding}', "
                  "'\"basura\"'::jsonb, true) WHERE tenant_id = %s::uuid", (T_A,))
    check("config malformado → load devuelve None (fail-soft)",
          await _load_onboarding_draft(T_A) is None)
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("UPDATE tenant_settings SET config = jsonb_set(config, '{onboarding}', "
                  "'{\"draft\": {\"responses\": \"no-es-dict\", \"idx\": 1}}'::jsonb, true) "
                  "WHERE tenant_id = %s::uuid", (T_A,))
    check("draft con responses no-dict → load devuelve None (fail-soft)",
          await _load_onboarding_draft(T_A) is None)

    # 5 · aislamiento entre despachos (RLS vía tenant_connection)
    await _save_onboarding_draft(T_A, {"responses": {"p1": "solo-de-A"}, "idx": 2})
    loaded_b = await _load_onboarding_draft(T_B)
    check("aislamiento: B no ve el borrador de A", loaded_b is None)
    loaded_a = await _load_onboarding_draft(T_A)
    check("aislamiento: A sigue viendo el suyo",
          loaded_a is not None and loaded_a["responses"].get("p1") == "solo-de-A")

    # 6 · contrato en el código de las rutas (endpoint, tope, clamp, status, complete)
    ux_src = (ROOT / "backend" / "mia" / "api" / "routes" / "ux.py").read_text(encoding="utf-8")
    check("endpoint POST /onboarding/draft existe", '"/onboarding/draft"' in ux_src)
    check("tope de tamaño del borrador definido y usado",
          MAX_ONBOARDING_DRAFT_CHARS > 0 and "MAX_ONBOARDING_DRAFT_CHARS" in ux_src)
    check("índice clampado en el endpoint", "min(int(body.idx), 200)" in ux_src)
    check("status expone el borrador", '"draft": draft' in ux_src)
    check("complete limpia el borrador (fail-open con log)",
          "_save_onboarding_draft(tid, None)" in ux_src)

    await pool.close_pool()


def main() -> int:
    print("== Borrador persistido del onboarding (Fase 2) ==")
    seed()
    try:
        asyncio.run(run_checks())
    finally:
        cleanup()
    failed = [n for n, ok in _results if not ok]
    print(f"\nRESULT: {len(_results) - len(failed)}/{len(_results)} checks PASS")
    if failed:
        print("FALLARON: " + "; ".join(failed))
        return 1
    print("Borrador de onboarding OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
