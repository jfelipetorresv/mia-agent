# -*- coding: utf-8 -*-
"""Mia · test_atajos_editables.py — barrera de los ATAJOS EDITABLES (bloque D7).

QUÉ DEFIENDE. Los atajos de la conversación vacía se DERIVAN solos de las guías activas y de
los agentes del despacho. El bloque D7 añade encima una capa de preferencias (migración 062,
tabla `shortcut_prefs`) para fijar, ocultar, renombrar y agregar atajos propios. Dos cosas
pueden romperse en silencio y esta barrera existe para que no lo hagan:

  1 · que la capa nueva TAPE la derivación (si el despacho no toca nada, el resultado tiene
      que ser exactamente el de antes: los atajos siguen apareciendo solos);
  2 · que las preferencias de un despacho se vean o se toquen desde otro. Los atajos nombran
      sus guías, sus ayudantes y su forma de trabajar: son información sobre su trabajo.

Y una tercera que es una promesa hecha al abogado EN PANTALLA: **lo fijado nunca se descarta**.
Si fija más atajos de los que caben, se muestran todos y no entra ningún automático — la
pantalla se lo dice con el número exacto, así que el número tiene que ser cierto.

Estructura: primero las comprobaciones PURAS del reparto (`componer_atajos`, sin DB), luego el
ciclo completo contra la DB REAL con dos despachos de prueba que se borran al final.

Requiere DB (DATABASE_URL y PG_PASSWORD del .env) y la migración 062 aplicada
(`python execution/init_shortcut_prefs.py`).

Salida: exit 0 = PASS · exit 1 = FAIL.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid

import psycopg
from dotenv import load_dotenv

# Windows: sin la política Selector, el pool async de psycopg no consigue conexión y el gate
# se cae con PoolTimeout aunque la base esté perfectamente arriba (mismo arranque que
# test_agent_hub.py y el resto de suites con DB).
if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
sys.path.insert(0, os.path.join(ROOT, "backend"))
load_dotenv(os.path.join(ROOT, ".env"))

from mia.db import pool  # noqa: E402
from mia.memory import atajos as A  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

SUPER = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
             dbname=os.getenv("PG_DB", "mia"), user="postgres",
             password=os.getenv("PG_PASSWORD", ""))

fallos: list[str] = []
_hechos: list[str] = []


def ok(nombre: str, cond) -> None:
    _hechos.append(nombre)
    print(f"  [{'OK' if cond else 'XX'}]   {nombre}")
    if not cond:
        fallos.append(nombre)


# ── 1 · el reparto del cupo, sin DB ─────────────────────────────────────────
def _at(kind: str, n: int, **extra) -> dict:
    base = {"clave": f"{kind}:{n}", "kind": kind, "id": str(n), "label": f"{kind} {n}",
            "texto": f"texto {n}", "oculto": False, "fijado": False, "orden": 0, "desde": ""}
    base.update(extra)
    return base


def puro() -> None:
    print("\n-- 1 · el reparto del cupo (puro, sin base de datos) --")

    # Sin ninguna preferencia: el comportamiento histórico, intacto. Con 8 guías y 3 agentes,
    # los agentes conservan sus 2 cupos reservados y las guías se quedan con 4.
    guias = [_at("guia", i) for i in range(8)]
    agentes = [_at("agente", i) for i in range(3)]
    salida = A.componer_atajos(guias, agentes, [], A.MAX_SHORTCUTS)
    ok("1a · sin preferencias, el reparto histórico no cambia (6 atajos, 2 de ellos agentes)",
       len(salida) == 6 and sum(1 for s in salida if s["kind"] == "agente") == 2)

    # Fijar una guía que estaba fuera del corte la mete SIEMPRE.
    guias_f = [_at("guia", i, fijado=(i == 7)) for i in range(8)]
    salida = A.componer_atajos(guias_f, agentes, [], A.MAX_SHORTCUTS)
    ok("1b · una guía fijada entra aunque el reparto automático la dejara fuera",
       salida[0]["clave"] == "guia:7" and len(salida) == 6)

    # Ocultar: quien oculta ya no aparece (el filtro lo hace el llamador; aquí se comprueba
    # que ocultar no reduce la lista a menos de lo que hay disponible).
    salida = A.componer_atajos([g for g in guias if g["id"] != "0"], agentes, [],
                               A.MAX_SHORTCUTS)
    ok("1c · ocultar un atajo NO deja un hueco: entra el siguiente",
       len(salida) == 6 and all(s["clave"] != "guia:0" for s in salida))

    # Lo fijado nunca se descarta: 8 fijados → se muestran los 8 y ningún automático.
    fijados = [_at("guia", i, fijado=True) for i in range(8)]
    salida = A.componer_atajos(fijados, agentes, [], A.MAX_SHORTCUTS)
    ok("1d · con más fijados de los que caben se muestran TODOS (nada se descarta en silencio)",
       len(salida) == 8 and all(s["fijado"] for s in salida))
    ok("1e · y mientras haya tantos fijados no entra ningún automático",
       not any(s["kind"] == "agente" for s in salida))

    # Los propios van primero: existen porque alguien los escribió.
    salida = A.componer_atajos(guias, agentes, [_at("propio", 1, fijado=True)], A.MAX_SHORTCUTS)
    ok("1f · un atajo propio encabeza la fila", salida[0]["kind"] == "propio")

    # Determinismo: dos llamadas idénticas dan exactamente lo mismo.
    ok("1g · el reparto es determinista (mismo estado → misma lista, byte a byte)",
       A.componer_atajos(guias, agentes, [], 6) == A.componer_atajos(guias, agentes, [], 6))

    # Claves mal formadas: no se cuelan.
    for malo in ("", "guia:", "otro:123", "123"):
        try:
            A.partir_clave(malo)
            ok(f"1h · clave inválida rechazada ({malo!r})", False)
        except A.AtajoError:
            pass
    ok("1h · toda clave inválida se rechaza con un mensaje para el abogado", True)


# ── 2 · el ciclo completo contra la DB real ─────────────────────────────────
def _sembrar() -> tuple[str, str, str, str]:
    """Dos despachos, cada uno con una guía activa propia. Devuelve (t1, t2, guia1, guia2)."""
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    with psycopg.connect(autocommit=True, **SUPER) as c:
        c.execute("INSERT INTO tenants (id, name) VALUES (%s,%s),(%s,%s)",
                  (t1, "PRUEBA atajos A", t2, "PRUEBA atajos B"))
        g1 = c.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, content, applies_when, status) "
            "VALUES (%s, 'Guía de A', 'resumen A', 'contenido A', 'cuando pasa algo en A', 'active') "
            "RETURNING id",
            (t1,)).fetchone()[0]
        g2 = c.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, content, applies_when, status) "
            "VALUES (%s, 'Guía de B', 'resumen B', 'contenido B', 'cuando pasa algo en B', 'active') "
            "RETURNING id",
            (t2,)).fetchone()[0]
    return t1, t2, str(g1), str(g2)


def _limpiar(t1: str, t2: str) -> None:
    with psycopg.connect(autocommit=True, **SUPER) as c:
        c.execute("DELETE FROM tenants WHERE id = ANY(%s)", ([t1, t2],))
    print("      (despachos de prueba borrados)")


async def con_db(t1: str, t2: str, g1: str, g2: str) -> None:
    await pool.open_pool()
    try:
        print("\n-- 2 · la derivación automática sigue intacta --")
        base = await A.list_shortcuts(t1)
        ok("2a · sin tocar nada, la guía activa aparece sola como atajo",
           any(x["clave"] == f"guia:{g1}" for x in base))
        ok("2b · y su texto sigue siendo el derivado, palabra por palabra",
           any(x["texto"] == A.build_playbook_shortcut(
               {"title": "Guía de A", "applies_when": "cuando pasa algo en A"})
               for x in base))

        print("\n-- 3 · fijar, renombrar, ocultar y restablecer --")
        await A.guardar_preferencia(t1, f"guia:{g1}", label="Mi atajo de siempre", fijado=True)
        estado = await A.estado_atajos(t1)
        fila = next(x for x in estado["atajos"] if x["clave"] == f"guia:{g1}")
        ok("3a · renombrar cambia el nombre VISIBLE", fila["label"] == "Mi atajo de siempre")
        ok("3b · y no toca lo que se le pide a Mia al pulsarlo",
           fila["texto"] == A.build_playbook_shortcut(
               {"title": "Guía de A", "applies_when": "cuando pasa algo en A"}))
        ok("3c · fijar queda registrado y el conteo del cupo lo refleja",
           fila["fijado"] and estado["cupo"]["fijados"] == 1)

        await A.guardar_preferencia(t1, f"guia:{g1}", oculto=True)
        visibles = await A.list_shortcuts(t1)
        estado = await A.estado_atajos(t1)
        fila = next(x for x in estado["atajos"] if x["clave"] == f"guia:{g1}")
        ok("3d · ocultar lo saca de la conversación",
           all(x["clave"] != f"guia:{g1}" for x in visibles))
        ok("3e · ocultar desfija (nunca queda 'fijado' algo que no se ve)",
           fila["oculto"] and not fila["fijado"])
        ok("3f · pero el atajo sigue en la pantalla de atajos, para poder encenderlo de nuevo",
           any(x["clave"] == f"guia:{g1}" for x in estado["atajos"]))

        await A.eliminar(t1, f"guia:{g1}")
        estado = await A.estado_atajos(t1)
        fila = next(x for x in estado["atajos"] if x["clave"] == f"guia:{g1}")
        ok("3g · restablecer lo devuelve a como Mia lo propone (nombre original, sin marcas)",
           fila["label"] == "Guía de A" and not fila["fijado"] and not fila["oculto"])

        print("\n-- 4 · atajos propios (crear, editar, borrar) --")
        creado = await A.crear_propio(t1, "Revisión rápida", "Revisa lo que te mando y dime qué falta.")
        visibles = await A.list_shortcuts(t1)
        ok("4a · un atajo propio aparece en la conversación en cuanto se crea",
           any(x["clave"] == creado["clave"] for x in visibles))
        ok("4b · y nace fijado (existe porque el abogado lo quiso)",
           next(x for x in visibles if x["clave"] == creado["clave"])["fijado"])

        _, ident = A.partir_clave(creado["clave"])
        await A.actualizar_propio(t1, ident, "Revisión a fondo", "Revísalo entero y sé duro.")
        visibles = await A.list_shortcuts(t1)
        fila = next(x for x in visibles if x["clave"] == creado["clave"])
        ok("4c · editarlo cambia nombre y texto",
           fila["label"] == "Revisión a fondo" and fila["texto"] == "Revísalo entero y sé duro.")

        try:
            await A.crear_propio(t1, "", "algo")
            ok("4d · un atajo sin nombre se rechaza", False)
        except A.AtajoError as e:
            ok("4d · un atajo sin nombre se rechaza con un mensaje en llano, sin jerga",
               "atajo" in str(e).lower() and "endpoint" not in str(e).lower())

        await A.eliminar(t1, creado["clave"])
        visibles = await A.list_shortcuts(t1)
        ok("4e · borrarlo lo quita de la conversación",
           all(x["clave"] != creado["clave"] for x in visibles))

        print("\n-- 5 · aislamiento entre despachos (RLS) --")
        propio_a = await A.crear_propio(t1, "Solo de A", "Esto es de A.")
        await A.guardar_preferencia(t1, f"guia:{g1}", fijado=True)

        vistos_b = await A.list_shortcuts(t2)
        ok("5a · el despacho B NO ve los atajos propios de A",
           all(x["clave"] != propio_a["clave"] for x in vistos_b))
        ok("5b · ni la guía de A (que ni siquiera es suya)",
           all(x["clave"] != f"guia:{g1}" for x in vistos_b))
        ok("5c · B sigue viendo lo suyo (el aislamiento no lo deja a oscuras)",
           any(x["clave"] == f"guia:{g2}" for x in vistos_b))

        estado_b = await A.estado_atajos(t2)
        ok("5d · el catálogo de B tampoco los trae",
           all(x["clave"] != propio_a["clave"] for x in estado_b["atajos"]))
        ok("5e · y su conteo de fijados no cuenta los de A",
           estado_b["cupo"]["fijados"] == 0)

        # B intenta tocar el atajo propio de A por su identificador: no existe PARA B.
        try:
            await A.actualizar_propio(t2, A.partir_clave(propio_a["clave"])[1], "Robado", "x")
            ok("5f · B NO puede editar un atajo de A", False)
        except A.AtajoError:
            ok("5f · B NO puede editar un atajo de A (para B ese atajo no existe)", True)

        try:
            await A.eliminar(t2, propio_a["clave"])
            ok("5g · B NO puede borrar un atajo de A", False)
        except A.AtajoError:
            ok("5g · B NO puede borrar un atajo de A", True)

        sigue = await A.list_shortcuts(t1)
        ok("5h · y tras los dos intentos, el atajo de A sigue igual",
           any(x["clave"] == propio_a["clave"] and x["label"] == "Solo de A" for x in sigue))

        # B fija SU guía: cada despacho manda sobre lo suyo sin pisar al otro.
        await A.guardar_preferencia(t2, f"guia:{g2}", label="Lo de B", fijado=True)
        estado_a = await A.estado_atajos(t1)
        fila_a = next(x for x in estado_a["atajos"] if x["clave"] == f"guia:{g1}")
        ok("5i · lo que B renombra no cambia nada en A", fila_a["label"] == "Guía de A")

        print("\n-- 6 · fail-closed sin contexto de despacho --")
        async with pool.connection() as conn:
            n = (await (await conn.execute(
                "SELECT count(*) FROM shortcut_prefs")).fetchone())[0]
        ok("6a · sin contexto de despacho no se lee ninguna preferencia (0 filas)", n == 0)
    finally:
        await pool.close_pool()


def main() -> int:
    puro()
    t1, t2, g1, g2 = _sembrar()
    try:
        asyncio.run(con_db(t1, t2, g1, g2))
    finally:
        _limpiar(t1, t2)

    total = len(fallos)
    print(f"\n{len(_hechos) - total}/{len(_hechos)} checks PASS")
    if total:
        print("FALLAN: " + str(fallos))
    return 1 if total else 0


if __name__ == "__main__":
    raise SystemExit(main())
