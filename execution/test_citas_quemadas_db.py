# -*- coding: utf-8 -*-
"""Mia · test_citas_quemadas_db.py — el MURO de citas quemadas contra la DB REAL.

Complemento de `test_citas_quemadas.py` (que es puro). Prueba lo que ninguna suite pura puede:
que la tabla de la migración 047 existe, que el RLS por tenant la aísla de verdad, que el ciclo
quemar/leer/desquemar funciona sobre la base, y que con el banco LEÍDO de la base el muro retira
la cita del borrador.

Por qué el RLS importa aquí y no es ceremonia: el banco de un despacho es la lista de errores
que encontró en SU ordenamiento y en SUS expedientes. Filtrarlo a otro despacho sería una fuga
de información sobre su trabajo.

Requiere DB (usa DATABASE_URL y PG_PASSWORD del .env). Crea dos tenants de prueba y los BORRA
al final (ON DELETE CASCADE se lleva sus filas).

Salida: exit 0 = PASS · exit 1 = FAIL.
"""
import os
import sys
import uuid

import psycopg
from dotenv import load_dotenv

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
load_dotenv(os.path.join(ROOT, ".env"))
from mia.agents import verification as V

CITA = "Sentencia C-832 de 2002"
URL = os.getenv("DATABASE_URL")
# Crear/borrar tenants exige el rol postgres: mia_app no puede insertar en `tenants` (RLS).
SUPER = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
             dbname=os.getenv("PG_DB", "mia"), user="postgres",
             password=os.getenv("PG_PASSWORD", ""))
fallos = []


def ok(nombre, cond):
    print(f"  [{'OK' if cond else 'XX'}]   {nombre}")
    if not cond:
        fallos.append(nombre)


def main():
    t1 = str(uuid.uuid4())
    t2 = str(uuid.uuid4())
    with psycopg.connect(autocommit=True, **SUPER) as c:
        cols = [r[0] for r in c.execute(
            "SELECT column_name FROM information_schema.columns WHERE table_name='tenants'"
        ).fetchall()]
        print("columnas de tenants:", cols)
        # nombre mínimo obligatorio si existe la columna
        if "name" in cols:
            c.execute("INSERT INTO tenants (id, name) VALUES (%s,%s),(%s,%s)",
                      (t1, "PRUEBA muro citas quemadas A", t2, "PRUEBA muro B"))
        else:
            c.execute("INSERT INTO tenants (id) VALUES (%s),(%s)", (t1, t2))
    try:
        with psycopg.connect(URL) as c:
            # ── despacho A quema la cita ──
            with c.transaction():
                c.execute("SELECT set_config('app.tenant_id', %s, true)", (t1,))
                c.execute(
                    "INSERT INTO burned_citations (tenant_id, citation, citation_norm, reason,"
                    " burned_by) VALUES (app_current_tenant(), %s, %s, %s, 'abogado')",
                    (CITA, V._normalize(CITA), "el pasaje atribuido es fabricado"))
                banco_a = c.execute(
                    "SELECT citation, citation_norm, reason FROM burned_citations").fetchall()
            ok("A · la cita queda en el banco del despacho que la quemó", len(banco_a) == 1)

            # ── el despacho B NO ve el banco de A (RLS real, no promesa) ──
            with c.transaction():
                c.execute("SELECT set_config('app.tenant_id', %s, true)", (t2,))
                banco_b = c.execute("SELECT count(*) FROM burned_citations").fetchone()[0]
            ok("B · RLS: otro despacho NO ve el banco (0 filas) — el banco es información "
               "sobre los expedientes de A", banco_b == 0)

            # ── sin contexto de tenant: fail-closed ──
            with c.transaction():
                c.execute("SELECT set_config('app.tenant_id', '', true)")
                try:
                    sin_ctx = c.execute("SELECT count(*) FROM burned_citations").fetchone()[0]
                except Exception:
                    sin_ctx = "error"
            ok("C · sin contexto de tenant no se lee nada (fail-closed)",
               sin_ctx in (0, "error"))

            # ── el muro, con el banco leído de la base ──
            banco = [{"citation": r[0], "citation_norm": r[1], "reason": r[2]}
                     for r in banco_a]
            borrador = f"Segun la {CITA}, procede la excepcion planteada."
            texto, informe = V.annotate_draft(borrador, burned=banco)
            print("      texto emitido:", texto)
            ok("D · con el banco REAL de la base, el muro retira la cita del borrador",
               "C-832" not in texto and informe.get("quemadas") == 1)

            # ── idempotencia del índice único ──
            with c.transaction():
                c.execute("SELECT set_config('app.tenant_id', %s, true)", (t1,))
                c.execute(
                    "INSERT INTO burned_citations (tenant_id, citation, citation_norm, reason,"
                    " burned_by) VALUES (app_current_tenant(), %s, %s, %s, 'abogado') "
                    "ON CONFLICT (tenant_id, citation_norm) DO UPDATE SET reason=excluded.reason",
                    (CITA.lower(), V._normalize(CITA.lower()), "segundo motivo, con la fuente"))
                n, motivo = c.execute(
                    "SELECT count(*), max(reason) FROM burned_citations").fetchone()
            ok("E · quemar la MISMA cita otra vez no duplica la entrada", n == 1)
            ok("F · y actualiza el motivo (la segunda vez se quema con la fuente en la mano)",
               motivo == "segundo motivo, con la fuente")

            # ── desquemar ──
            with c.transaction():
                c.execute("SELECT set_config('app.tenant_id', %s, true)", (t1,))
                cur = c.execute("DELETE FROM burned_citations WHERE citation_norm=%s",
                                (V._normalize(CITA),))
                borradas = cur.rowcount
                quedan = c.execute("SELECT count(*) FROM burned_citations").fetchone()[0]
            texto2, _ = V.annotate_draft(borrador, burned=[])
            ok("G · desquemar devuelve la cita al texto (el muro es reversible por quien lo puso)",
               borradas == 1 and quedan == 0 and "C-832" in texto2)
    finally:
        with psycopg.connect(autocommit=True, **SUPER) as c:
            c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([t1, t2],))
        print("      (tenants de prueba borrados)")

    print(f"\n{'TODO OK' if not fallos else 'FALLAN: ' + str(fallos)}")
    return 1 if fallos else 0


raise SystemExit(main())
