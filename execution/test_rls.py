"""
Mia · test_rls.py — TEST CRÍTICO DE AISLAMIENTO MULTI-TENANT (Módulo 0).

Verifica que el rol de aplicación `mia_app` (NOSUPERUSER, NOBYPASSRLS) NO pueda
ver ni modificar datos de otro tenant. La visibilidad la gobierna el GUC
`app.tenant_id` (fail-closed).

HALT: si este test falla, NO se avanza con el Módulo 0 (ver CLAUDE.md §G).
Salida: exit 0 = PASS · exit 1 = FAIL.

Se ejecuta con el python de mia/.venv:
    .venv\\Scripts\\python.exe execution\\test_rls.py
"""
from __future__ import annotations
import os
import sys
from pathlib import Path

import psycopg
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

HOST = os.getenv("PG_HOST", "127.0.0.1")
PORT = os.getenv("PG_PORT", "5432")
DB = os.getenv("PG_DB", "mia")
SUPER_PW = os.getenv("PG_PASSWORD", "")
APP_PW = os.getenv("PG_APP_PASSWORD", "")

def _kw(user: str, password: str, dbname: str = DB) -> dict:
    # Parámetros por keyword: psycopg escapa los valores (el password de
    # postgres trae caracteres especiales que romperían una URL).
    return dict(host=HOST, port=PORT, dbname=dbname, user=user, password=password)

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def seed() -> dict:
    """Inserta 2 tenants con datos, como superusuario (RLS no aplica)."""
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as s:
        s.execute("DELETE FROM tenants WHERE name IN ('RLS_TEST_A','RLS_TEST_B')")
        a = s.execute("INSERT INTO tenants(name) VALUES ('RLS_TEST_A') RETURNING id").fetchone()[0]
        b = s.execute("INSERT INTO tenants(name) VALUES ('RLS_TEST_B') RETURNING id").fetchone()[0]
        ma = s.execute("INSERT INTO matters(tenant_id,title) VALUES (%s,'Asunto A') RETURNING id", (a,)).fetchone()[0]
        mb = s.execute("INSERT INTO matters(tenant_id,title) VALUES (%s,'Asunto B') RETURNING id", (b,)).fetchone()[0]
        da = s.execute("INSERT INTO documents(tenant_id,matter_id,filename) VALUES (%s,%s,'a.txt') RETURNING id", (a, ma)).fetchone()[0]
        db_ = s.execute("INSERT INTO documents(tenant_id,matter_id,filename) VALUES (%s,%s,'b.txt') RETURNING id", (b, mb)).fetchone()[0]
        s.execute("INSERT INTO chunks(tenant_id,document_id,ord,content) VALUES (%s,%s,0,'contenido A')", (a, da))
        s.execute("INSERT INTO chunks(tenant_id,document_id,ord,content) VALUES (%s,%s,0,'contenido B')", (b, db_))
        # Sala de estrategia (033_warroom_results): un dictamen persistido por asunto — misma
        # RLS fail-closed por tenant que el resto de tablas por-despacho.
        wa = s.execute("INSERT INTO warroom_results(tenant_id,matter_id,result) VALUES (%s,%s,'{}'::jsonb) RETURNING id", (a, ma)).fetchone()[0]
        wb = s.execute("INSERT INTO warroom_results(tenant_id,matter_id,result) VALUES (%s,%s,'{}'::jsonb) RETURNING id", (b, mb)).fetchone()[0]
    return {"a": a, "b": b, "ma": ma, "mb": mb, "db_": db_, "wa": wa, "wb": wb}


def cleanup() -> None:
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as s:
        s.execute("DELETE FROM tenants WHERE name IN ('RLS_TEST_A','RLS_TEST_B')")


def run_assertions(ids: dict) -> None:
    a, b, ma, mb, db_ = ids["a"], ids["b"], ids["ma"], ids["mb"], ids["db_"]
    wa, wb = ids["wa"], ids["wb"]
    with psycopg.connect(**_kw("mia_app", APP_PW)) as app:
        # 0) Fail-closed: sin GUC no se ve nada.
        with app.transaction(force_rollback=True):
            n = app.execute("SELECT count(*) FROM matters").fetchone()[0]
            check("Sin GUC (fail-closed) no ve ninguna fila", n == 0)

        # 1) Contexto tenant A.
        with app.transaction(force_rollback=True):
            app.execute("SELECT set_config('app.tenant_id', %s, true)", (str(a),))
            check("A ve exactamente sus matters (count==1)",
                  app.execute("SELECT count(*) FROM matters").fetchone()[0] == 1)
            check("A no ve matters de B filtrando por tenant_id (0)",
                  app.execute("SELECT count(*) FROM matters WHERE tenant_id=%s", (b,)).fetchone()[0] == 0)
            check("A no puede SELECT el matter de B por id (0)",
                  app.execute("SELECT count(*) FROM matters WHERE id=%s", (mb,)).fetchone()[0] == 0)
            check("A no ve documents de B (0)",
                  app.execute("SELECT count(*) FROM documents WHERE id=%s", (db_,)).fetchone()[0] == 0)
            # warroom_results: A ve el suyo, no el de B; no puede modificar ni borrar el de B.
            check("A ve su propio warroom_results (1)",
                  app.execute("SELECT count(*) FROM warroom_results WHERE id=%s", (wa,)).fetchone()[0] == 1)
            check("A no ve warroom_results de B (0)",
                  app.execute("SELECT count(*) FROM warroom_results WHERE id=%s", (wb,)).fetchone()[0] == 0)
            check("UPDATE del warroom_results de B bajo GUC=A afecta 0 filas",
                  app.execute("UPDATE warroom_results SET result=result WHERE id=%s", (wb,)).rowcount == 0)
            check("DELETE del warroom_results de B afecta 0 filas",
                  app.execute("DELETE FROM warroom_results WHERE id=%s", (wb,)).rowcount == 0)
            check("UPDATE masivo (sin WHERE de tenant) solo toca filas de A (rowcount==1)",
                  app.execute("UPDATE matters SET title=title").rowcount == 1)
            check("DELETE del chunk de B afecta 0 filas",
                  app.execute("DELETE FROM chunks WHERE document_id=%s", (db_,)).rowcount == 0)
            # INSERT con tenant ajeno bajo GUC=A => WITH CHECK violation (aislado en savepoint).
            violated = False
            try:
                with app.transaction():
                    app.execute("INSERT INTO matters(tenant_id,title) VALUES (%s,'intruso')", (b,))
            except psycopg.Error:
                violated = True
            check("INSERT con tenant_id=B bajo GUC=A es rechazado (WITH CHECK)", violated)
            # warroom_results: INSERT con tenant ajeno bajo GUC=A => WITH CHECK violation.
            violated_wr = False
            try:
                with app.transaction():
                    app.execute("INSERT INTO warroom_results(tenant_id,matter_id,result) VALUES (%s,%s,'{}'::jsonb)", (b, mb))
            except psycopg.Error:
                violated_wr = True
            check("INSERT en warroom_results con tenant_id=B bajo GUC=A es rechazado (WITH CHECK)",
                  violated_wr)

        # 2) Contexto tenant B: ve lo suyo, no lo de A.
        with app.transaction(force_rollback=True):
            app.execute("SELECT set_config('app.tenant_id', %s, true)", (str(b),))
            check("B ve exactamente sus matters (count==1)",
                  app.execute("SELECT count(*) FROM matters").fetchone()[0] == 1)
            check("B no puede SELECT el matter de A por id (0)",
                  app.execute("SELECT count(*) FROM matters WHERE id=%s", (ma,)).fetchone()[0] == 0)
            check("B ve su propio warroom_results (1)",
                  app.execute("SELECT count(*) FROM warroom_results WHERE id=%s", (wb,)).fetchone()[0] == 1)
            check("B no ve warroom_results de A (0)",
                  app.execute("SELECT count(*) FROM warroom_results WHERE id=%s", (wa,)).fetchone()[0] == 0)


def main() -> int:
    # Garantía: el rol de app NO debe ser superusuario ni bypassrls.
    with psycopg.connect(autocommit=True, **_kw("postgres", SUPER_PW)) as s:
        row = s.execute(
            "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname='mia_app'"
        ).fetchone()
    if row is None:
        print("  [FAIL] el rol mia_app no existe (corre init_db.py primero)")
        return 1
    check("mia_app NO es superusuario", row[0] is False)
    check("mia_app NO tiene BYPASSRLS", row[1] is False)

    ids = seed()
    try:
        run_assertions(ids)
    finally:
        cleanup()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    if passed == total:
        print("RLS OK — aislamiento multi-tenant verificado.")
        return 0
    print("RLS FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
