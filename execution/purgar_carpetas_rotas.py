"""
Mia · purgar_carpetas_rotas.py — retira de la base el registro de las carpetas cuya ruta ya
no existe, que es parte de lo que `test_raices_datos.py` reporta como ROTA en cada corrida.

POR QUÉ EXISTE. Una carpeta registrada que apunta a una ruta inexistente deja de indexarse EN
SILENCIO: el vigilante sigue corriendo, no encuentra nada, y «no encontrar nada» es
indistinguible de «todo está bien». `test_raices_datos.py` denuncia la situación pero no la
arregla, y hasta hoy la única salida documentada era «reapúntala o retírala desde la pantalla
de conexiones» — a mano, una por una. Este comando es la salida automatizable de la segunda
opción.

QUÉ BORRA Y QUÉ NO. Borra FILAS de `local_folder_sources`; jamás toca un archivo ni una carpeta
del disco. Una carpeta que existe nunca se toca, aunque esté deshabilitada (`enabled=false` es
una decisión del abogado, no una avería) y aunque esté vacía.

QUÉ CUENTA COMO ROTA — y por qué el criterio es MÁS ESTRECHO que el del gate. El gate avisa de
dos cosas distintas: que la ruta no exista y que exista vacía. Este comando BORRA, así que solo
actúa sobre la primera, y ni siquiera sobre toda ella:

  · Una carpeta VACÍA no es rota aquí. Es el caso del abogado que registra la carpeta del caso
    nuevo antes de meter los documentos; retirarle el registro por eso convierte una espera de
    cinco minutos en una carpeta que no se indexa nunca.
  · Una ruta INALCANZABLE hoy tampoco. Un recurso de red con el servidor caído, o con la VPN
    sin levantar, o una unidad sin mapear, se comportan igual que una carpeta borrada: la
    consulta dice que no existe y no lanza ningún error. Borrarla ahí sería retirar el
    expediente vivo del despacho porque el abogado abrió el portátil fuera de la oficina. Se
    listan como SIN ALCANCE y no se tocan.
  · Un error de acceso tampoco es una ausencia.

La diferencia entre avisar y borrar es toda la diferencia de criterio: un aviso de más cuesta
una línea en un informe; un borrado de más cuesta el registro de dónde vivía el expediente.

USO
    # Ver qué se retiraría, sin tocar nada (por defecto)
    .venv\Scripts\python.exe execution\purgar_carpetas_rotas.py

    # Acotado a un solo despacho (recomendado en una máquina con varios)
    .venv\Scripts\python.exe execution\purgar_carpetas_rotas.py --despacho <id>

    # Retirarlas de verdad
    .venv\Scripts\python.exe execution\purgar_carpetas_rotas.py --aplicar

Exit 0 siempre que la operación se pueda hacer (haya o no rotas); exit 2 si la base no responde.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import psycopg  # noqa: E402


def _pg_kwargs() -> dict:
    """Superusuario local, con las MISMAS variables PG_* que usan los init_* y el gate."""
    return dict(
        host=os.getenv("PG_HOST", "127.0.0.1"),
        port=os.getenv("PG_PORT", "5432"),
        dbname=os.getenv("PG_DB", "mia"),
        user="postgres",
        password=os.getenv("PG_PASSWORD", ""),
    )


def inalcanzable(ruta: str) -> bool:
    """¿La ruta está en un sitio al que HOY no se puede llegar?

    Una carpeta en un recurso de red, con el servidor caído o la VPN sin levantar, o en una
    unidad que no está mapeada, se comporta EXACTAMENTE igual que una borrada: `exists()`
    devuelve False sin lanzar nada. Tratarlas igual sería retirar el registro de la carpeta
    viva del despacho —justo el expediente que está en el servidor de la oficina— mientras
    el abogado trabaja desde casa, y dejarlo sin ni siquiera el apunte de a dónde apuntaba.

    Se reconoce por la FORMA de la ruta, no por el resultado de mirarla: una ruta UNC
    (`\\\\servidor\\recurso`) o una letra de unidad que no existe en este equipo.
    """
    p = str(ruta or "")
    if p.startswith("\\\\") or p.startswith("//"):
        return True
    unidad = os.path.splitdrive(p)[0]
    if unidad and not os.path.isdir(unidad + os.sep):
        return True
    return False


def esta_rota(ruta: str) -> bool:
    """True SOLO si la ruta no existe estando su sitio accesible.

    Deliberadamente NO se considera rota una carpeta que existe y está vacía: es el caso del
    abogado que registra la carpeta del caso nuevo antes de meter los documentos, y retirarle
    el registro por eso convierte una espera de cinco minutos en una carpeta que nunca se
    indexa. Que esté vacía lo sigue denunciando `test_raices_datos.py` como aviso; lo que no
    hace este comando es BORRAR por ello.

    Un error de acceso tampoco es una ausencia, ni lo es una ruta inalcanzable hoy.
    """
    if inalcanzable(ruta):
        return False
    p = Path(ruta)
    try:
        return not p.exists()
    except OSError:
        return False


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--aplicar", action="store_true",
                    help="retira de verdad las filas rotas (por defecto solo las lista)")
    ap.add_argument("--despacho", default="",
                    help="acota la operación a UN despacho (su id). Sin esto se opera sobre "
                         "todos, que es lo que casi nunca se quiere en una máquina con "
                         "varios.")
    args = ap.parse_args()

    try:
        conn = psycopg.connect(autocommit=True, connect_timeout=5, **_pg_kwargs())
    except Exception as e:  # noqa: BLE001
        print(f"ERROR: la base no responde ({e.__class__.__name__}). Nada que hacer.")
        return 2

    with conn as c:
        if not c.execute("SELECT to_regclass('public.local_folder_sources')").fetchone()[0]:
            print("local_folder_sources no existe en esta base (migración 016 sin aplicar).")
            return 0
        # Se lee como superusuario (RLS fuera), así que la consulta abarca TODOS los
        # despachos: el nombre de cada uno viaja en la salida para que quien decide
        # `--aplicar` sepa a quién le está retirando qué. Sin eso, el listado es una lista
        # de rutas sin dueño y la decisión se toma a ciegas.
        if args.despacho:
            filas = c.execute(
                "SELECT f.id, f.path, f.label, f.kind, f.enabled, t.name "
                "FROM local_folder_sources f JOIN tenants t ON t.id = f.tenant_id "
                "WHERE f.tenant_id = %s::uuid ORDER BY f.kind, f.path",
                (args.despacho,)).fetchall()
        else:
            filas = c.execute(
                "SELECT f.id, f.path, f.label, f.kind, f.enabled, t.name "
                "FROM local_folder_sources f JOIN tenants t ON t.id = f.tenant_id "
                "ORDER BY t.name, f.kind, f.path").fetchall()

        rotas = [f for f in filas if esta_rota(f[1])]
        inaccesibles = [f for f in filas if inalcanzable(f[1])]
        print(f"Carpetas registradas: {len(filas)} · rotas: {len(rotas)}")
        for _id, path, label, kind, enabled, despacho in rotas:
            estado = "activa" if enabled else "desactivada"
            print(f"  [ROTA] [{despacho}] ({kind}, {estado}) {label} -> {path}")
        for _id, path, label, kind, _en, despacho in inaccesibles:
            # Se nombran, y NO se tocan: hoy no se puede saber si existen.
            print(f"  [SIN ALCANCE] [{despacho}] ({kind}) {label} -> {path}"
                  "  (no se retira: el sitio no está accesible ahora)")

        if not rotas:
            print("Nada que retirar.")
            return 0
        if not args.aplicar:
            print("\nSimulacion: no se tocó nada. Repite con --aplicar para retirarlas.")
            return 0

        ids = [f[0] for f in rotas]
        c.execute("DELETE FROM local_folder_sources WHERE id = ANY(%s)", (ids,))
        # El recuento final cubre el MISMO alcance que la operación: con `--despacho`, el de
        # ese despacho. Un total global tras una operación acotada es un número que no
        # corresponde a lo que se acaba de hacer, y quien lo lee saca la conclusión contraria.
        if args.despacho:
            restantes = c.execute(
                "SELECT count(*) FROM local_folder_sources WHERE tenant_id = %s::uuid",
                (args.despacho,)).fetchone()[0]
            ambito = "de este despacho"
        else:
            restantes = c.execute("SELECT count(*) FROM local_folder_sources").fetchone()[0]
            ambito = "en total"
        print(f"\nRetiradas {len(ids)} fila(s). Quedan {restantes} carpeta(s) "
              f"registrada(s) {ambito}.")
        print("No se borró ningún archivo ni carpeta del disco.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
