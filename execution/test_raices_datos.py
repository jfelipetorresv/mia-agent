"""
Mia · test_raices_datos.py — BARRERA DE RAÍCES DE DATOS (AVISO · portada del harness).

Origen (harness de litigio de Lexia, `scripts/check-raices-datos.py`): una ruta de datos
que vive fuera del repo se mueve, y la barrera que la vigila queda apuntando al vacío.
No falla ruidosamente: pasa a no encontrar nada, que es indistinguible de «todo está
bien». En el harness, la fuente local de normas llevaba tiempo AUSENTE mientras el gate
de citas seguía verde apañándose con lo que encontraba.

La regla: **toda ruta de datos que Mia declare debe existir y no estar vacía**. Con el
matiz obligatorio del encargo: una ruta OPCIONAL no configurada NO es un fallo — el
fallo es la ruta CONFIGURADA que apunta al vacío. La salida distingue tres estados:

    [SANA]   configurada y sana  → existe y tiene contenido
    [ROTA]   configurada y rota  → EL HALLAZGO: declarada y apunta al vacío (exit 1)
    [ --- ]  no configurada      → informativo, no falla

Inventario (cada entrada dice de dónde sale su verdad):
  - config.MIA_HOME (backend/mia/config.py): la carpeta de identidad por despacho.
    Siempre está configurada (tiene default de producto), así que siempre se audita.
  - Variables de RUTA del entorno/.env — solo se usan los NOMBRES y los valores se leen
    en memoria para comprobar el disco; JAMÁS se copian a ningún archivo:
    OBSIDIAN_VAULT_PATH, OBSIDIAN_VAULT_ALLOWLIST (lista separada por ';'),
    MIA_APP_DIR, MIA_BUNDLE_MANIFEST (archivo: existir basta), MIA_HOME.
  - Carpetas locales registradas por el despacho en la DB (`local_folder_sources.path`,
    migraciones 016/025): la allowlist real de lo que Mia indexa del disco.
  - Carpetas de nube (`remote_drive_sources`, migraciones 027/060, OneDrive y Google
    Drive): son IDs remotos, no rutas del disco — se reportan como INFORMATIVO (conteo),
    porque desde aquí no se puede comprobar su existencia sin salir a la red.

Modo AVISO (catálogo `raices-datos`): esta barrera vive en execution/, fuera de la ruta
del turno — nunca puede frenar al abogado. El exit 1 es la señal del gate para quien
construye, no un muro del producto.

    .venv\\Scripts\\python.exe execution\\test_raices_datos.py
    .venv\\Scripts\\python.exe execution\\test_raices_datos.py --selftest

Exit 0 = ninguna ruta configurada está rota; 1 = hay rutas configuradas y rotas.
"""
from __future__ import annotations

import argparse
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

#: Variables de entorno cuyo VALOR es una ruta de datos. Solo nombres aquí (regla dura:
#: nunca copiar valores del .env a un archivo). `archivo=True` = existir basta.
ENV_RUTAS: tuple[tuple[str, bool, bool], ...] = (
    # (nombre, es_lista_por_punto_y_coma, es_archivo)
    ("MIA_HOME", False, False),
    ("OBSIDIAN_VAULT_PATH", True, False),
    ("OBSIDIAN_VAULT_ALLOWLIST", True, False),
    ("MIA_APP_DIR", False, False),
    ("MIA_BUNDLE_MANIFEST", False, True),
)


def _estado(ruta: str, es_archivo: bool) -> str:
    """'sana' | 'rota'. Una carpeta vacía cuenta como rota: para quien la vigila,
    nada que ver es indistinguible de que todo esté bien."""
    p = Path(ruta)
    if es_archivo:
        return "sana" if p.is_file() else "rota"
    if not p.is_dir():
        return "rota"
    try:
        next(p.iterdir())
        return "sana"
    except StopIteration:
        return "rota"
    except OSError:
        return "rota"


def inventario_config() -> list[tuple[str, str | None, bool]]:
    """(descripcion, ruta_o_None_si_no_configurada, es_archivo)."""
    out: list[tuple[str, str | None, bool]] = []
    # config.MIA_HOME resuelve default + relativo→PROJECT_ROOT: es la verdad del producto.
    try:
        from mia import config as mia_config
        out.append(("MIA_HOME (config.py: identidad por despacho)",
                    str(mia_config.MIA_HOME), False))
    except Exception as exc:  # noqa: BLE001 — sin config no hay inventario: se reporta
        out.append((f"MIA_HOME (config.py NO importable: {type(exc).__name__})",
                    "<<config-roto>>", False))
    for nombre, es_lista, es_archivo in ENV_RUTAS:
        raw = (os.getenv(nombre) or "").strip()
        if nombre == "MIA_HOME":
            # Ya cubierta arriba por la resolución real de config (default incluido).
            continue
        if not raw:
            out.append((f"{nombre} (.env)", None, es_archivo))
            continue
        partes = [p.strip() for p in raw.split(";") if p.strip()] if es_lista else [raw]
        for i, parte in enumerate(partes):
            sufijo = f" [{i + 1}/{len(partes)}]" if len(partes) > 1 else ""
            out.append((f"{nombre} (.env){sufijo}", parte, es_archivo))
    return out


def inventario_db() -> tuple[list[tuple[str, str | None, bool]], list[str]]:
    """Carpetas locales registradas en la DB + notas informativas (nube).

    Se lee como `postgres` (gate local, igual que los init_*). Si la DB no está
    disponible se reporta como informativo — este gate vigila rutas, no la DB.
    """
    entradas: list[tuple[str, str | None, bool]] = []
    notas: list[str] = []
    try:
        import psycopg
        kw = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
                  dbname=os.getenv("PG_DB", "mia"), user="postgres",
                  password=os.getenv("PG_PASSWORD", ""))
        with psycopg.connect(connect_timeout=5, **kw) as c:
            if c.execute("SELECT to_regclass('public.local_folder_sources')").fetchone()[0]:
                rows = c.execute(
                    "SELECT path, kind FROM local_folder_sources ORDER BY path").fetchall()
                for path, kind in rows:
                    entradas.append((f"carpeta registrada en la DB (kind={kind})",
                                     str(path), False))
            else:
                notas.append("local_folder_sources aún no existe en esta DB (migración 016 sin aplicar)")
            if c.execute("SELECT to_regclass('public.remote_drive_sources')").fetchone()[0]:
                n = c.execute("SELECT count(*), count(*) FILTER (WHERE provider='google') "
                              "FROM remote_drive_sources").fetchone()
                notas.append(f"carpetas de nube registradas (027/060): {n[0]} en total, "
                             f"{n[1]} de Google Drive — remotas, no verificables desde el disco")
        return entradas, notas
    except Exception as exc:  # noqa: BLE001 — sin DB, el inventario de disco sigue valiendo
        notas.append(f"DB no disponible para el inventario ({type(exc).__name__}): "
                     "solo se auditan las rutas de config/.env")
        return entradas, notas


def auditar(entradas: list[tuple[str, str | None, bool]]) -> tuple[int, int, int, list[str]]:
    """(sanas, rotas, no_configuradas, hallazgos)."""
    sanas = rotas = nc = 0
    hallazgos: list[str] = []
    for descripcion, ruta, es_archivo in entradas:
        if ruta is None:
            nc += 1
            print(f"  [ --- ] {descripcion}: no configurada (informativo, no es fallo)")
            continue
        estado = _estado(ruta, es_archivo)
        if estado == "sana":
            sanas += 1
            print(f"  [SANA]  {descripcion}")
        else:
            rotas += 1
            hallazgos.append(descripcion)
            print(f"  [ROTA]  {descripcion}: la ruta configurada no existe o está vacía. "
                  f"Lo que la vigila no vigila nada y no falla ruidosamente: no encontrar "
                  f"nada es indistinguible de que todo esté bien. Reapúntala o retírala.")
    return sanas, rotas, nc, hallazgos


def selftest() -> int:
    ok, total = 0, 4
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        llena = base / "llena"
        llena.mkdir()
        (llena / "x.md").write_text("contenido", encoding="utf-8")
        vacia = base / "vacia"
        vacia.mkdir()

        s, r, n, _ = auditar([("carpeta con contenido", str(llena), False)])
        ok += int((s, r, n) == (1, 0, 0))
        print(f"selftest 1/4 {'OK' if s == 1 else 'FALLO'}: configurada y sana")

        s, r, n, h = auditar([("carpeta vacía", str(vacia), False)])
        ok += int(r == 1 and bool(h))
        print(f"selftest 2/4 {'OK' if r == 1 else 'FALLO'}: carpeta vacía = rota (el hallazgo)")

        s, r, n, h = auditar([("carpeta inexistente", str(base / "no-existe"), False)])
        ok += int(r == 1)
        print(f"selftest 3/4 {'OK' if r == 1 else 'FALLO'}: inexistente = rota")

        s, r, n, _ = auditar([("opcional sin configurar", None, False)])
        ok += int((r, n) == (0, 1))
        print(f"selftest 4/4 {'OK' if (r, n) == (0, 1) else 'FALLO'}: "
              "no configurada NO es fallo")
    print(f"SELFTEST raices-datos: {ok}/{total}")
    return 0 if ok == total else 1


def main() -> int:
    ap = argparse.ArgumentParser(description="Barrera de raíces de datos (AVISO)")
    ap.add_argument("--selftest", action="store_true")
    args = ap.parse_args()
    if args.selftest:
        return selftest()

    print("== Raíces de datos declaradas por Mia (config/.env) ==")
    sanas, rotas, nc, hallazgos = auditar(inventario_config())

    # Las carpetas registradas en la DB son declaraciones POR DESPACHO, no del producto:
    # en la DB de desarrollo quedan residuos de tenants de prueba (seeds, tests) cuyas
    # carpetas temporales ya no existen. Se auditan y se DICEN con conteo —ese es el
    # hallazgo que esta barrera existe para no callar— pero solo lo declarado por
    # config/.env decide el exit code (modo AVISO del catálogo: registrar y reportar).
    print("\n== Carpetas registradas por los despachos en la DB (aviso, no decide el exit) ==")
    db_entradas, notas = inventario_db()
    db_sanas, db_rotas, _, _ = auditar(db_entradas)
    for nota in notas:
        print(f"  [INFO]  {nota}")

    print(f"\nRESUMEN config/.env: {sanas} sana(s) · {rotas} ROTA(s) · "
          f"{nc} no configurada(s) [informativo]")
    print(f"RESUMEN DB (aviso): {db_sanas} sana(s) · {db_rotas} rota(s) — una carpeta "
          f"registrada que ya no existe deja de indexarse EN SILENCIO: reapúntala, "
          f"o retírala desde la pantalla de conexiones.")
    if rotas:
        print("FAIL: hay rutas de datos configuradas (config/.env) que apuntan al vacío:")
        for h in hallazgos:
            print(f"  - {h}")
        return 1
    print("PASS: ninguna ruta de datos configurada en config/.env está rota.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
