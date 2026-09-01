# -*- coding: utf-8 -*-
"""
Mia · test_persona_capacidades.py — barrera de las CAPACIDADES de un agente (bloque D8).

QUÉ DEFIENDE. Pipe, bitácora 2026-08-19 (punto 23 · decisión D8): el diseñador de agentes
debía dejar decir «qué puede hacer», no solo el encargo en prosa. Dos cosas pueden romperse
en silencio aquí, y las dos convierten el control en una etiqueta decorativa:

  1 · que lo marcado NO llegue al turno. Si la capacidad se guarda y no entra en la voz del
      agente, marcarla no cambia una sola palabra de lo que Mia hace — y el abogado creería
      haber concedido algo que nadie aplica.
  2 · que se acepte una capacidad que el producto no tiene. El vocabulario es cerrado a
      propósito: cada valor tiene detrás una capacidad real. Un valor desconocido REPRUEBA
      en vez de guardarse y quedar ahí, sin efecto y sin aviso.

Y una tercera que es una promesa hecha en pantalla: **conceder no es poder**. El catálogo
distingue lo que el abogado marca de lo que esta instalación puede cumplir, y dice la razón
cuando no puede. Un catálogo que mintiera ahí prometería lectura óptica en un equipo que no
la tiene instalada.

Estructura: comprobaciones PURAS (sin DB) del vocabulario y de la voz, más el contrato del
endpoint leído del código. Añade el ciclo con DB solo si la base responde.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_persona_capacidades.py
"""
from __future__ import annotations

import asyncio
import inspect
import os
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

from mia.agents import personas as P  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    _results.append((nombre, bool(ok)))
    linea = ("  [OK]   " if ok else "  [FAIL] ") + nombre
    if not ok and detalle:
        linea += f" — {detalle}"
    print(linea)


def _persona(caps: tuple[str, ...]) -> P.Persona:
    return P.Persona(
        id="00000000-0000-0000-0000-000000000000",
        name="Agente de prueba", title="", role_prompt="Trabaja el caso.", tone="",
        focus_areas=(), model_tier=P.MODEL_TIER_STANDARD, summon_phrases=(),
        description="", enabled=True, capabilities=caps,
    )


def main() -> int:  # noqa: C901
    print("== barrera de las capacidades de un agente (D8) ==")

    print("\n1 · el vocabulario es cerrado (R: lo desconocido reprueba)")
    check("las tres capacidades de la decisión D8 existen",
          set(P.CAPABILITIES) == {"lectura_visual", "investigacion_viva", "documentos_largos"},
          str(P.CAPABILITIES))
    try:
        P._validate_capabilities(["volar"])
        check("una capacidad inventada se RECHAZA", False)
    except P.PersonaError as e:
        check("una capacidad inventada se RECHAZA con un mensaje en llano, sin jerga",
              "capacidad" in str(e).lower() and "endpoint" not in str(e).lower())
    # Los dos valores «vacíos» NO significan lo mismo, y confundirlos borraba en silencio
    # lo que el abogado había concedido en cualquier guardado parcial:
    #   None       = «este cuerpo no habla de capacidades» → se conserva lo que hubiera
    #   lista []   = «quítalas todas» → es una orden del abogado
    check("un cuerpo que no menciona capacidades NO las toca (None ≠ vaciar)",
          P._validate_capabilities(None) is None)
    check("la lista vacía SÍ es la orden de quitarlas todas",
          P._validate_capabilities([]) == [])
    check("las repetidas se colapsan y el orden es canónico",
          P._validate_capabilities(
              ["documentos_largos", "lectura_visual", "lectura_visual"])
          == ["lectura_visual", "documentos_largos"])

    print("\n2 · lo concedido LLEGA al turno (si no, la casilla no controla nada)")
    # La disponibilidad se FUERZA en los dos sentidos: medirla contra la máquina real haría
    # que el veredicto del gate dependiera de qué haya instalado en ella, y un gate cuyo
    # resultado cambia con el equipo no prueba nada de forma repetible.
    _real = P.capability_available
    P.capability_available = lambda c: True
    try:
        voz_sin = P.render_persona_voice(_persona(()))
        voz_con = P.render_persona_voice(_persona(("lectura_visual",)))
        check("sin capacidades, la voz del agente no menciona ninguna",
              "Lo que puedes hacer" not in voz_sin)
        check("con una capacidad DISPONIBLE, la voz la enuncia",
              "Lo que puedes hacer" in voz_con
              and P.CAPABILITY_VOICE["lectura_visual"] in voz_con)
        voz_tres = P.render_persona_voice(_persona(tuple(P.CAPABILITIES)))
        check("las tres capacidades llegan enteras al turno",
              all(P.CAPABILITY_VOICE[c] in voz_tres for c in P.CAPABILITIES))
    finally:
        P.capability_available = _real

    print("\n2-bis · conceder NO es poder, TAMPOCO en el prompt")
    # El defecto que esto impide: el abogado marca «leer escaneados» en un equipo sin lectura
    # óptica, la pantalla se lo advierte, y el turno le dice al modelo que SÍ puede. En un
    # producto cuyo absoluto es cero afirmaciones sin respaldo, afirmarle al modelo una
    # capacidad inexistente es la premisa falsa que produce el invento.
    P.capability_available = lambda c: False
    try:
        voz_falsa = P.render_persona_voice(_persona(("lectura_visual",)))
        check("una capacidad concedida pero AUSENTE no se le afirma al modelo",
              P.CAPABILITY_VOICE["lectura_visual"] not in voz_falsa)
        check("y se le dice explícitamente que hoy NO puede hacerlo",
              "NO tiene hoy" in voz_falsa
              and P.CAPABILITY_UNAVAILABLE["lectura_visual"] in voz_falsa)
        check("el aviso de ausencia le pide DECIRLO en vez de suponer",
              "dilo" in P.CAPABILITY_UNAVAILABLE["lectura_visual"].lower())
    finally:
        P.capability_available = _real
    fuente_cap = inspect.getsource(P.capability_available)
    check("la medición es fail-closed: cualquier fallo de detección deja la capacidad fuera",
          "except Exception" in fuente_cap and fuente_cap.rstrip().endswith("return False"))
    # C · conceder capacidades NO relaja la regla de verificación: el guardrail sigue.
    check("conceder capacidades NO relaja la verificación (el guardrail sigue en la voz)",
          "[VERIFICAR]" in voz_tres and "no relaja la verificación" in voz_tres)
    check("la capacidad de investigación en vivo dice que lo traído entra por verificar",
          "por verificar" in P.CAPABILITY_VOICE["investigacion_viva"])

    print("\n3 · viaja al estado del turno y a la pantalla")
    p = _persona(("documentos_largos",))
    check("turn_context lleva las capacidades al grafo",
          p.turn_context().get("capabilities") == ["documentos_largos"])
    check("to_public las expone a la pantalla",
          p.to_public().get("capabilities") == ["documentos_largos"])

    print("\n4 · conceder NO es poder: el catálogo lo distingue")
    ruta = (ROOT / "backend" / "mia" / "api" / "routes" / "personas.py").read_text(
        encoding="utf-8")
    check("el catálogo de capacidades expone `disponible` y su `razon`",
          '"disponible"' in ruta and '"razon"' in ruta)
    check("la pantalla y el prompt miden la disponibilidad con la MISMA función (si "
          "divergieran, dirían cosas distintas del mismo equipo)",
          "capability_available" in ruta)
    fuente_mod = inspect.getsource(P)
    check("y esa función MIDE (lectura óptica del equipo, ayudantes del hub), no afirma",
          "optional_capabilities" in fuente_mod and "list_available" in fuente_mod)
    check("una capacidad no disponible viaja SIEMPRE con su razón concreta",
          'razon_de(' in ruta and ruta.count("disponible") >= 3)
    pantalla = (ROOT / "frontend" / "app" / "personas" / "page.tsx").read_text(
        encoding="utf-8")
    check("la pantalla pinta la razón cuando la capacidad no está disponible",
          "CapacidadesField" in pantalla and "!c.disponible" in pantalla)
    check("la pantalla manda las capacidades al guardar",
          "capabilities: form.capabilities" in pantalla)

    print("\n5 · la columna nace aditiva y con su vocabulario acotado")
    mig = (ROOT / "backend" / "mia" / "db" / "migrations"
           / "064_persona_capabilities.sql").read_text(encoding="utf-8")
    check("la migración es aditiva e idempotente",
          "ADD COLUMN IF NOT EXISTS capabilities" in mig)
    check("y acota el vocabulario también en la base",
          "ck_personas_capabilities" in mig
          and all(c in mig for c in P.CAPABILITIES))

    print("\n6 · en vivo contra la base (si está encendida)")
    asyncio.run(_con_db())

    ok = sum(1 for _, r in _results if r)
    print(f"\n{ok}/{len(_results)} checks PASS")
    if ok != len(_results):
        print("Gate FAIL — el control de capacidades no está haciendo lo que promete.")
        return 1
    print("PASS: lo que el abogado concede llega al turno, y lo que no existe no se promete.")
    return 0


async def _con_db() -> None:
    """Ciclo real: crear con capacidades, leerlas, cambiarlas y rechazar una inventada."""
    from mia.db import pool
    import psycopg
    import uuid

    sup = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
               dbname=os.getenv("PG_DB", "mia"), user="postgres",
               password=os.getenv("PG_PASSWORD", ""))
    tenant = str(uuid.uuid4())
    try:
        with psycopg.connect(autocommit=True, connect_timeout=5, **sup) as c:
            c.execute("INSERT INTO tenants (id, name) VALUES (%s::uuid, %s)",
                      (tenant, "A test capacidades"))
    except Exception as e:  # noqa: BLE001
        print(f"  [----] base no disponible ({e.__class__.__name__}); ciclo en vivo omitido")
        return

    try:
        await pool.open_pool()
        creada = await P.persona_service.create_persona(tenant, {
            "name": "Perito visual",
            "role_prompt": "Lee los escaneados del expediente y extrae los hechos.",
            "capabilities": ["lectura_visual"],
        })
        check("en vivo · se crea un agente con su capacidad",
              creada.capabilities == ("lectura_visual",), str(creada.capabilities))

        cambiada = await P.persona_service.update_persona(tenant, creada.id, {
            "name": "Perito visual",
            "role_prompt": "Lee los escaneados del expediente y extrae los hechos.",
            "capabilities": ["documentos_largos", "lectura_visual"],
        })
        check("en vivo · se pueden cambiar",
              cambiada.capabilities == ("lectura_visual", "documentos_largos"),
              str(cambiada.capabilities))

        quitadas = await P.persona_service.update_persona(tenant, creada.id, {
            "name": "Perito visual",
            "role_prompt": "Lee los escaneados del expediente y extrae los hechos.",
            "capabilities": [],
        })
        check("en vivo · y se pueden quitar todas", quitadas.capabilities == ())

        try:
            await P.persona_service.update_persona(tenant, creada.id, {
                "name": "Perito visual", "role_prompt": "x", "capabilities": ["volar"]})
            check("en vivo · una capacidad inventada no se guarda", False)
        except P.PersonaError:
            check("en vivo · una capacidad inventada no se guarda", True)

        # R · un guardado PARCIAL (sin el campo) no puede borrar lo concedido. Es el camino
        # que hoy nadie recorre y que mañana recorre el primer interruptor suelto.
        await P.persona_service.update_persona(tenant, creada.id, {
            "name": "Perito visual",
            "role_prompt": "Lee los escaneados del expediente y extrae los hechos.",
            "capabilities": ["lectura_visual", "documentos_largos"]})
        parcial = await P.persona_service.update_persona(tenant, creada.id, {
            "name": "Perito visual",
            "role_prompt": "Lee los escaneados del expediente y extrae los hechos.",
            "enabled": True})  # sin mencionar capabilities
        check("en vivo · un guardado que no menciona capacidades NO borra las concedidas",
              parcial.capabilities == ("lectura_visual", "documentos_largos"),
              str(parcial.capabilities))
    finally:
        await pool.close_pool()
        try:
            with psycopg.connect(autocommit=True, **sup) as c:
                c.execute("DELETE FROM tenants WHERE id = %s::uuid", (tenant,))
        except Exception:  # noqa: BLE001
            print("  [aviso] no se pudo borrar el despacho de prueba; bórralo a mano")


if __name__ == "__main__":
    raise SystemExit(main())
