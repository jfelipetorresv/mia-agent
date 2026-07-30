"""
Mia · test_seed_despacho_demo.py — gate del despacho de prueba para verificación visual.

Qué custodia: que `seed_despacho_demo.py` deje la máquina EN EL ESTADO que hace falta para
mirar la interfaz, y no solo filas en una tabla. Un seed que "corre bien" pero deja el
onboarding sin completar, o un asunto sin borrador, no sirve para capturar nada — y eso no
se nota hasta que alguien pierde veinte minutos.

Se verifica, sobre el despacho recién sembrado:

  1. El onboarding queda COMPLETO (si no, la app redirige a la entrevista y no hay captura).
  2. Hay un asunto con borrador ESPERANDO REVISIÓN, con su informe de verificación.
  3. Ese borrador trae las tres cosas que había que poder mirar: una cita sin respaldo, una
     afirmación negativa y una parte de otro expediente.
  4. El borrado deja la máquina limpia — en la base Y en los archivos del despacho. Un
     borrado a medias es peor que ninguno: la corrida siguiente hereda el perfil anterior.

Sin red y sin cuota (el seed mockea modelo y embeddings). Necesita la DB portable.
Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_seed_despacho_demo.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import seed_despacho_demo as seed  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    _results.append((nombre, bool(ok)))
    linea = ("  [OK]   " if ok else "  [FAIL] ") + nombre
    if not ok and detalle:
        linea += f" — {detalle}"
    print(linea)


def main() -> int:  # noqa: C901
    from fastapi.testclient import TestClient

    from mia import config
    from mia.api.main import app

    print("== gate: despacho de prueba para verificación visual ==")
    datos = seed.sembrar()
    seed._instalar_dobles()
    auth = {"Authorization": f"Bearer {datos['token']}"}
    tid = datos["tenant_id"]

    try:
        with TestClient(app) as client:
            print("\n1 · la app abre en el escritorio, no en la entrevista")
            st = client.get("/api/onboarding/status", headers=auth).json()
            check("el onboarding queda completo", st.get("completed") is True, str(st))
            check("el SOUL.md del despacho existe de verdad",
                  (Path(config.MIA_HOME) / f"soul_{tid}.md").exists())

            print("\n2 · hay un borrador esperando revisión")
            r = client.get(f"/api/matters/{datos['asunto_con_borrador']}/draft", headers=auth)
            check("GET draft -> 200", r.status_code == 200, str(r.status_code))
            cuerpo = r.json() if r.status_code == 200 else {}
            check("el asunto está esperando la revisión del abogado",
                  cuerpo.get("awaiting_review") is True)
            borrador = cuerpo.get("draft") or ""
            check("el borrador se anuncia como material de prueba",
                  "PRUEBA" in borrador.upper(), borrador[:80])

            print("\n3 · el borrador da material a las tres pantallas de aviso")
            informe = cuerpo.get("verification") or {}
            detalle = informe.get("detalle") or []
            check("el guardián detectó al menos una cita",
                  int(informe.get("citas") or 0) >= 1, str(sorted(informe)))
            # Estado ≠ "respaldada" es lo que habilita el botón «esta cita no existe o no
            # dice eso» en la pantalla de revisión: sin una cita así, no hay qué capturar.
            check("hay una cita SIN respaldo (para el botón «esta cita no existe»)",
                  any(c.get("estado") != "respaldada" for c in detalle), str(detalle))

            neg = informe.get("afirmaciones_negativas") or {}
            check("el guardián de afirmaciones negativas corrió",
                  int(neg.get("n_afirmaciones") or 0) >= 1, str(neg))
            check("y hay al menos una para revisar (el aviso se pinta)",
                  int(neg.get("n_a_revisar") or 0) >= 1, str(neg))

            cont = informe.get("contaminacion_expediente") or {}
            check("hay una parte de OTRO expediente nombrada",
                  int(cont.get("n_partes_ajenas") or 0) >= 1, str(cont))

            print("\n4 · las demás pantallas tienen su estado")
            for etiqueta, mid in (("asunto vacío", datos["asunto_vacio"]),
                                  ("proyecto", datos["proyecto"])):
                rr = client.get(f"/api/matters/{mid}", headers=auth)
                check(f"el {etiqueta} existe", rr.status_code == 200, str(rr.status_code))
    finally:
        print("\n5 · el borrado deja la máquina limpia")
        seed.borrar_demo(verboso=False)

    print("\n6 · el resumen de citas no puede mentir en su primera línea")
    # Defecto encontrado MIRANDO la pantalla que este seed hace posible: con una única cita
    # OMITIDA, el resumen decía «todas con respaldo en sus fuentes». La cuenta solo tenía dos
    # casillas (respaldadas y por verificar) y las citas RETIRADAS del texto no caían en
    # ninguna. Este check es estructural —mira el fuente, no ejecuta el componente— y por eso
    # se declara como lo que es: impide que la frase vuelva a colgar de una condición que no
    # exige que TODAS estén respaldadas.
    rev = (ROOT / "frontend" / "app" / "_components" / "CitationReview.tsx").read_text(
        encoding="utf-8")
    i = rev.find("todas con respaldo en sus fuentes")
    contexto = rev[max(0, i - 300):i] if i > 0 else ""
    check("«todas con respaldo» exige que todas lo estén",
          "v.respaldadas === v.citas" in contexto, contexto[-120:])
    check("el resumen contempla las citas retiradas del texto",
          "retirada del texto" in rev and "v.omitidas" in rev)
    proy = (ROOT / "frontend" / "app" / "proyectos" / "[id]" / "page.tsx").read_text(
        encoding="utf-8")
    check("y la respuesta de un proyecto no pierde los avisos al normalizar el informe",
          "afirmaciones_negativas" in proy and "contaminacion_expediente" in proy)

    check("no queda ningún despacho demo en la base", not seed._tenants_demo())
    # Lo que más duele si se olvida: los archivos. Sobreviven a un DELETE de la tabla y la
    # corrida siguiente heredaría el perfil de la anterior sin que nadie lo note.
    sobrantes = list(Path(config.MIA_HOME).glob(f"soul_{tid}*"))
    check("tampoco quedan el SOUL.md ni las respuestas del despacho borrado",
          not sobrantes, str(sobrantes))

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
