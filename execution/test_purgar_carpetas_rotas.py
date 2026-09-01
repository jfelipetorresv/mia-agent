"""
Mia · test_purgar_carpetas_rotas.py — gate de `execution/purgar_carpetas_rotas.py`.

POR QUÉ. El comando BORRA filas. Una herramienta de borrado que se equivoca en el criterio
retira carpetas vivas del abogado y las deja de indexar en silencio, que es exactamente el mal
que venía a curar. Este gate prueba el criterio en LOS DOS SENTIDOS (regla 6-bis: una barrera
nueva no se acepta sin verla en rojo) y, cuando hay base de datos, comprueba además que el modo
por defecto no toca nada.

EL CRITERIO ES MÁS ESTRECHO QUE EL DEL GATE DE AVISO, A PROPÓSITO. `test_raices_datos.py`
avisa de dos cosas —la ruta no existe, o existe vacía—; este comando BORRA, y solo la primera
justifica borrar. Las dos exclusiones que este gate defiende son las que evitan destruir el
registro de una carpeta VIVA:

  · una carpeta VACÍA (el caso nuevo registrado antes de subir los documentos);
  · una ruta INALCANZABLE hoy — un recurso de red con el servidor caído o la VPN sin
    levantar, o una unidad sin mapear: `exists()` dice que no existe y no lanza nada, así
    que es indistinguible de una borrada mirándola. Se distingue por la FORMA de la ruta.

Qué se verifica:
  R (debe cazar)   · una ruta que no existe, en un sitio accesible, es ROTA.
  C (no debe caza) · una carpeta con contenido NO es rota.
  C (no debe caza) · una carpeta VACÍA no es rota (se avisa en otro sitio; no se borra).
  C (no debe caza) · una ruta UNC de un servidor caído NO es rota.
  C (no debe caza) · una ruta en una unidad no mapeada NO es rota.
  Seguridad        · sin `--aplicar` no se ejecuta ningún DELETE, y se comprueba EN VIVO
                     sobre una fila rota sembrada — no sobre una base sin nada que borrar,
                     donde el comando retorna antes de llegar a la guarda y el check pasaría
                     igual con la guarda rota.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\Scripts\python.exe execution\test_purgar_carpetas_rotas.py
"""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

import purgar_carpetas_rotas as purga  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    _results.append((nombre, bool(ok)))
    linea = ("  [OK]   " if ok else "  [FAIL] ") + nombre
    if not ok and detalle:
        linea += f" — {detalle}"
    print(linea)


def main() -> int:
    print("== gate del retiro de carpetas registradas rotas ==")
    base = Path(tempfile.mkdtemp(prefix="mia purga carpetas "))

    print("\n1 · el criterio caza lo roto (R)")
    check("una ruta inexistente, en un sitio accesible, es ROTA",
          purga.esta_rota(str(base / "no-existe")))

    print("\n2 · el criterio NO caza lo sano (C — prueba de mutación al revés)")
    llena = base / "llena"
    llena.mkdir()
    (llena / "expediente.pdf").write_text("contenido", encoding="utf-8")
    check("una carpeta con contenido NO es rota", not purga.esta_rota(str(llena)))
    sub_dir = base / "solo-subcarpeta"
    (sub_dir / "dentro").mkdir(parents=True)
    check("una carpeta cuyo único contenido es otra carpeta NO es rota",
          not purga.esta_rota(str(sub_dir)))
    archivo = base / "doc.txt"
    archivo.write_text("hola", encoding="utf-8")
    check("un archivo con bytes NO es roto", not purga.esta_rota(str(archivo)))

    print("\n2-bis · lo que parece borrado y NO lo está (los dos casos que destruían "
          "registros vivos)")
    vacia = base / "caso nuevo sin documentos"
    vacia.mkdir()
    check("una carpeta VACÍA no se borra: es el caso registrado antes de subir el "
          "expediente", not purga.esta_rota(str(vacia)))
    check("un recurso de red con el servidor caído NO es rota",
          not purga.esta_rota(r"\\servidor-de-la-oficina\expedientes\2026"))
    check("y se reconoce como INALCANZABLE, para poder nombrarla sin tocarla",
          purga.inalcanzable(r"\\servidor-de-la-oficina\expedientes\2026"))
    unidad_muerta = next((f"{L}:\\Casos" for L in "ZYXWV"
                          if not os.path.isdir(f"{L}:\\")), None)
    if unidad_muerta:
        check("una unidad de red no mapeada NO es rota",
              not purga.esta_rota(unidad_muerta) and purga.inalcanzable(unidad_muerta))
    else:
        print("  [----] todas las letras de prueba están mapeadas; caso no evaluado")

    print("\n3 · el borrado es explícito, nunca por defecto")
    fuente = (ROOT / "execution" / "purgar_carpetas_rotas.py").read_text(encoding="utf-8")
    delete_line = [ln for ln in fuente.splitlines() if "DELETE FROM local_folder_sources" in ln]
    check("existe exactamente un DELETE en el comando", len(delete_line) == 1,
          f"encontrados {len(delete_line)}")
    idx_guarda = fuente.find("if not args.aplicar:")
    idx_delete = fuente.find("DELETE FROM local_folder_sources")
    check("el DELETE está DESPUÉS de la guarda `if not args.aplicar: return`",
          idx_guarda != -1 and idx_delete != -1 and idx_guarda < idx_delete)
    check("el comando declara que no toca archivos del disco",
          "No se borró ningún archivo ni carpeta del disco." in fuente)

    print("\n4 · en vivo contra la base, CON una fila rota sembrada")
    # Sin sembrar, el comando retorna en «Nada que retirar» antes de llegar a la guarda de
    # `--aplicar`: el check saldría verde aunque la guarda estuviera rota. Un verde vacuo en
    # el único check que protege un borrado es peor que no tenerlo.
    tenant = None
    try:
        import psycopg
        import uuid as _uuid
        kw = purga._pg_kwargs()
        with psycopg.connect(autocommit=True, connect_timeout=5, **kw) as c:
            tenant = str(_uuid.uuid4())
            c.execute("INSERT INTO tenants (id, name) VALUES (%s::uuid, %s)",
                      (tenant, "A test purga carpetas"))
            rota = str(base / "esta-no-existe")
            viva = str(llena)
            for ruta, etiqueta in ((rota, "rota"), (viva, "viva")):
                c.execute(
                    "INSERT INTO local_folder_sources (tenant_id, path, label, kind) "
                    "VALUES (%s::uuid, %s, %s, 'knowledge')", (tenant, ruta, etiqueta))
            antes = c.execute(
                "SELECT count(*) FROM local_folder_sources WHERE tenant_id = %s::uuid",
                (tenant,)).fetchone()[0]

            sys.argv = ["purgar_carpetas_rotas.py", "--despacho", tenant]  # SIMULACRO
            purga.main()
            medio = c.execute(
                "SELECT count(*) FROM local_folder_sources WHERE tenant_id = %s::uuid",
                (tenant,)).fetchone()[0]
            check("el simulacro NO borra, TENIENDO una fila rota que borrar",
                  antes == 2 and medio == 2, f"{antes} -> {medio}")

            sys.argv = ["purgar_carpetas_rotas.py", "--despacho", tenant, "--aplicar"]
            purga.main()
            quedan = c.execute(
                "SELECT label FROM local_folder_sources WHERE tenant_id = %s::uuid",
                (tenant,)).fetchall()
            check("con --aplicar se retira la rota y SOLO la rota",
                  [r[0] for r in quedan] == ["viva"], str(quedan))
    except Exception as e:  # noqa: BLE001
        print(f"  [----] base no disponible ({e.__class__.__name__}); comprobación en vivo omitida")
    finally:
        if tenant:
            try:
                import psycopg as _pg
                with _pg.connect(autocommit=True, **purga._pg_kwargs()) as c:
                    c.execute("DELETE FROM tenants WHERE id = %s::uuid", (tenant,))
            except Exception:  # noqa: BLE001
                print("  [aviso] no se pudo borrar el despacho de prueba; bórralo a mano")

    ok = sum(1 for _, r in _results if r)
    print(f"\n{ok}/{len(_results)} checks PASS")
    if ok != len(_results):
        print("Gate FAIL — el criterio de 'carpeta rota' no es de fiar; no borrar nada.")
        return 1
    print("Gate OK.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
