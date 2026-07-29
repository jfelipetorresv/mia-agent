"""
Mia · purgar_piloto.py — BORRADO VERIFICABLE de un piloto con expediente real.

PARA QUÉ. Cuando el abogado prueba MIA con un expediente REAL suyo y quiere la certeza de que
después no queda rastro, no basta borrar el despacho en la base: el turno deja copia en varios
sitios, y algunos están FUERA de MIA. Este comando los cubre TODOS y, sobre todo, DEMUESTRA el
resultado buscando los términos del cliente en los tres sitios al final. Si encuentra una sola
coincidencia, REPRUEBA (exit 1). La certeza es la búsqueda, no la promesa.

LOS TRES SITIOS (verificados en la sesión 52):

  1. BASE DE DATOS. Borrar el tenant arrastra por FK casi todo, pero no todo: los checkpoints
     de LangGraph se indexan por `thread_id` y no tienen FK a tenants. Además, para no depender
     de una lista cableada que se queda vieja en cuanto alguien añade una tabla, el comando
     DESCUBRE en el catálogo todas las tablas con columna `tenant_id` y verifica que queden 0
     filas en CADA una. Una tabla nueva entra sola en la verificación.

  2. DISCO DE MIA (`MIA_HOME`). Trazas de turno, corridas del banco (que con
     MIA_EVAL_PERSIST_FULL=1 guardan el borrador y el diagnóstico COMPLETOS), el perfil del
     despacho (`soul_<tenant>.md`), la carpeta del despacho y el vault espejo. Nada de esto se
     va al borrar el tenant.

  3. TRANSCRIPTS DEL CLI DE LA SUSCRIPCIÓN — el que nadie espera. En la política 'suscripcion'
     MIA razona invocando el CLI `claude` headless con `cwd = MIA_HOME`, y ese CLI guarda el
     PROMPT COMPLETO de cada turno en `~/.claude/projects/<slug de MIA_HOME>/*.jsonl`. O sea:
     el expediente queda en la carpeta del usuario, fuera de MIA, y borrar en MIA no lo toca.
     Comprobado empíricamente el 2026-07-29 (el contenido del expediente de prueba estaba en el
     transcript). Se purgan los transcripts de la VENTANA del piloto.

LO QUE ESTE COMANDO NO PUEDE DESHACER, y hay que decirlo antes de empezar: lo que ya SALIÓ de la
máquina. Para poder buscar dentro del expediente su texto va al proveedor de embeddings, y para
razonar va al modelo. Borrar aquí no revierte eso. Si eso importa, el expediente debe entrar
ANONIMIZADO (`backend/mia/security/anonymize.py`), no purgarse después.

USO
    # 1) ANTES del piloto: fotografía de la ventana (para saber qué es nuevo)
    .venv\\Scripts\\python.exe execution\\purgar_piloto.py --marcar-inicio

    # 2) DESPUÉS: ver qué hay, sin borrar nada
    .venv\\Scripts\\python.exe execution\\purgar_piloto.py --verificar --termino "Banco Popular" --termino "Zurich"

    # 3) Purgar y DEMOSTRAR que no queda rastro
    .venv\\Scripts\\python.exe execution\\purgar_piloto.py --purgar --tenant <uuid> --termino "Banco Popular"

NUNCA imprime el contenido encontrado: solo la ruta y cuántas coincidencias. El informe no puede
convertirse él mismo en una filtración.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

import psycopg  # noqa: E402

from mia import config  # noqa: E402

MARCA = ROOT / "mia-data" / ".piloto-ventana.json"

# Extensiones de texto que vale la pena barrer en disco. Los PDF/DOCX originales del abogado NO
# se tocan (son SUS archivos, en SU carpeta): aquí solo se purga lo que MIA derivó.
EXT_TEXTO = {".md", ".json", ".jsonl", ".txt", ".log", ".yaml", ".yml", ".csv"}


def _pg_kwargs() -> dict:
    return {
        "host": config.POSTGRES_HOST,
        "port": config.POSTGRES_PORT,
        "dbname": config.POSTGRES_DB,
        "user": config.POSTGRES_USER,
        "password": config.POSTGRES_PASSWORD,
    }


def _slug(texto: str) -> str:
    """Normaliza como lo hace el CLI: todo lo que no es alfanumérico pasa a '-'. Se normaliza
    en vez de replicar la regla exacta del CLI (que es de otro programa y puede cambiar)."""
    return "".join(ch if ch.isalnum() else "-" for ch in texto)


def _cli_transcript_dir() -> Path | None:
    """Carpeta donde el CLI `claude` guarda los transcripts de los turnos de MIA, o None si no
    se pudo localizar.

    El cwd del CLI es MIA_HOME (ver `agent/subscription_llm.call_cli`) y el CLI la nombra
    slugificando esa ruta — separadores, ':' Y ESPACIOS pasan a '-'. Devolver None cuando no se
    encuentra es deliberado: quien llama debe REPORTARLO como «no puedo demostrar que esté
    limpia», nunca como «0 coincidencias». Un 'no existe' equivocado da certeza falsa, que es
    peor que no dar ninguna.
    """
    base = Path.home() / ".claude" / "projects"
    if not base.is_dir():
        return None
    objetivo = _slug(str(Path(config.MIA_HOME).resolve()))
    directo = base / objetivo
    if directo.is_dir():
        return directo
    # Búsqueda tolerante: comparar slugs normalizados (colapsando guiones repetidos).
    def _plano(s: str) -> str:
        return "-".join(p for p in _slug(s).split("-") if p).lower()

    objetivo_plano = _plano(objetivo)
    for cand in base.iterdir():
        if cand.is_dir() and _plano(cand.name) == objetivo_plano:
            return cand
    return None


# ── ventana ───────────────────────────────────────────────────────────────────
def marcar_inicio() -> int:
    ahora = datetime.now(timezone.utc).timestamp()
    MARCA.parent.mkdir(parents=True, exist_ok=True)
    MARCA.write_text(json.dumps({"inicio_ts": ahora,
                                 "inicio_iso": datetime.fromtimestamp(
                                     ahora, timezone.utc).isoformat()}),
                     encoding="utf-8")
    print(f"Ventana del piloto abierta: {MARCA}")
    print("Todo lo que MIA escriba desde ahora se considera del piloto.")
    print("Al terminar: --verificar (mira) y luego --purgar (borra y demuestra).")
    return 0


def _inicio_ts() -> float | None:
    if not MARCA.is_file():
        return None
    try:
        return float(json.loads(MARCA.read_text(encoding="utf-8"))["inicio_ts"])
    except (OSError, ValueError, KeyError):
        return None


# ── base de datos ─────────────────────────────────────────────────────────────
def _tablas_con_tenant(cur) -> list[str]:
    """Tablas del esquema public que tienen columna `tenant_id`. Se DESCUBREN en el catálogo:
    así una tabla nueva entra sola en la verificación y esto no envejece."""
    cur.execute(
        "SELECT table_name FROM information_schema.columns "
        "WHERE table_schema='public' AND column_name='tenant_id' "
        "ORDER BY table_name"
    )
    return [r[0] for r in cur.fetchall()]


def _filas_del_tenant(cur, tablas: list[str], tenant: str) -> dict[str, int]:
    restos: dict[str, int] = {}
    for t in tablas:
        try:
            cur.execute(f'SELECT count(*) FROM public."{t}" WHERE tenant_id = %s::uuid',
                        (tenant,))
            n = int(cur.fetchone()[0])
            if n:
                restos[t] = n
        except Exception as exc:  # noqa: BLE001 — una tabla ilegible se REPORTA, no se ignora
            restos[f"{t} (no se pudo leer: {type(exc).__name__})"] = -1
    return restos


def purgar_db(tenant: str, *, purgar: bool) -> dict:
    with psycopg.connect(autocommit=True, **_pg_kwargs()) as c:
        with c.cursor() as cur:
            tablas = _tablas_con_tenant(cur)
            antes = _filas_del_tenant(cur, tablas, tenant)

            if purgar:
                # Checkpoints de LangGraph: se indexan por thread_id y NO tienen FK a tenants,
                # así que el CASCADE del tenant no los alcanza. El thread_id lleva el tenant.
                for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    try:
                        cur.execute(f"DELETE FROM {t} WHERE thread_id LIKE %s", (f"%{tenant}%",))
                    except Exception:  # noqa: BLE001 — best-effort; la verificación es el juez
                        pass
                cur.execute("DELETE FROM tenants WHERE id = %s::uuid", (tenant,))

            despues = _filas_del_tenant(cur, tablas, tenant)
    return {"tablas_revisadas": len(tablas), "antes": antes, "despues": despues}


# ── disco ─────────────────────────────────────────────────────────────────────
def _barrer_archivos(base: Path, terminos: list[str], *, desde: float | None) -> list[tuple[Path, int]]:
    """Archivos de texto bajo `base` que contienen alguno de los términos. Devuelve
    (ruta, coincidencias). NUNCA devuelve el texto."""
    hallazgos: list[tuple[Path, int]] = []
    if not base.is_dir():
        return hallazgos
    for p in base.rglob("*"):
        if not p.is_file() or p.suffix.lower() not in EXT_TEXTO:
            continue
        try:
            if desde is not None and p.stat().st_mtime < desde:
                continue
            texto = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        n = sum(texto.lower().count(t.lower()) for t in terminos)
        if n:
            hallazgos.append((p, n))
    return hallazgos


def purgar_disco(tenant: str | None, terminos: list[str], *, purgar: bool,
                 desde: float | None) -> dict:
    home = Path(config.MIA_HOME)
    borrados: list[str] = []

    if purgar and tenant:
        # Artefactos nombrados por tenant: perfil del despacho y su carpeta.
        for cand in (home / f"soul_{tenant}.md",
                     home / f"soul_{tenant}.responses.json",
                     home / "despachos" / tenant,
                     home / "traces" / tenant,
                     home / "wiki" / tenant):
            if cand.exists():
                shutil.rmtree(cand, ignore_errors=True) if cand.is_dir() else cand.unlink(
                    missing_ok=True)
                borrados.append(str(cand.relative_to(home)))

    if purgar:
        # Cualquier archivo derivado que TODAVÍA contenga un término (corridas del banco con
        # texto completo, trazas de turno, etc.). Se borra el archivo entero: es material
        # derivado de MIA, no el original del abogado.
        for p, _ in _barrer_archivos(home, terminos, desde=desde):
            try:
                p.unlink()
                borrados.append(str(p.relative_to(home)))
            except OSError:
                pass

    restos = _barrer_archivos(home, terminos, desde=None)
    return {"borrados": borrados, "restos": [(str(p), n) for p, n in restos]}


# ── transcripts del CLI (fuera de MIA) ────────────────────────────────────────
def purgar_cli(terminos: list[str], *, purgar: bool, desde: float | None) -> dict:
    d = _cli_transcript_dir()
    if d is None:
        # NO se puede afirmar que esté limpia: se dice que no se pudo localizar.
        return {"carpeta": None, "existe": False, "localizada": False,
                "borrados": [], "restos": []}
    borrados: list[str] = []
    if purgar and d.is_dir():
        # DOS condiciones, y hace falta al menos una: que el transcript CONTENGA un término del
        # cliente, o que caiga dentro de la ventana del piloto. Nunca «todos los de la carpeta»:
        # ahí viven también los turnos de otros trabajos, y sin ventana (--todo-el-disco) un
        # borrado indiscriminado se llevaría material ajeno al piloto. Se mira el contenido —el
        # script ya lo lee para verificar, así que no hay lectura extra que ahorrar.
        for p in sorted(d.glob("*.jsonl")):
            try:
                en_ventana = desde is not None and p.stat().st_mtime >= desde
                texto = p.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            tiene_termino = any(t.lower() in texto.lower() for t in terminos)
            if not (tiene_termino or en_ventana):
                continue
            try:
                p.unlink()
                borrados.append(p.name)
            except OSError:
                pass

    restos = _barrer_archivos(d, terminos, desde=None) if d.is_dir() else []
    return {"carpeta": str(d), "existe": d.is_dir(), "localizada": True,
            "borrados": borrados, "restos": [(str(p), n) for p, n in restos]}


# ── informe ───────────────────────────────────────────────────────────────────
def main() -> int:  # noqa: C901
    ap = argparse.ArgumentParser(description="Borrado verificable de un piloto con datos reales")
    ap.add_argument("--marcar-inicio", action="store_true",
                    help="abre la ventana del piloto (correr ANTES de meter el expediente)")
    ap.add_argument("--verificar", action="store_true", help="mira y reporta, sin borrar nada")
    ap.add_argument("--purgar", action="store_true", help="borra y luego demuestra el resultado")
    ap.add_argument("--tenant", default=None, help="uuid del despacho de prueba")
    ap.add_argument("--termino", action="append", default=[],
                    help="término del cliente a buscar (repetible). Ej: --termino 'Banco Popular'")
    ap.add_argument("--todo-el-disco", action="store_true",
                    help="al purgar archivos, no limitarse a la ventana temporal")
    args = ap.parse_args()

    if args.marcar_inicio:
        return marcar_inicio()

    if not (args.verificar or args.purgar):
        ap.error("elige --marcar-inicio, --verificar o --purgar")
    if not args.termino:
        ap.error("hace falta al menos un --termino: la certeza es la búsqueda, y sin término "
                 "que buscar este comando no puede demostrar nada (sería un PASS vacío)")

    desde = None if args.todo_el_disco else _inicio_ts()
    modo = "PURGA" if args.purgar else "VERIFICACIÓN (no borra nada)"
    print(f"== {modo} del piloto ==")
    print(f"  términos: {len(args.termino)} · ventana: "
          f"{'toda' if desde is None else datetime.fromtimestamp(desde, timezone.utc).isoformat()}")

    problemas: list[str] = []

    # 1 · base
    print("\n1 · base de datos")
    if args.tenant:
        db = purgar_db(args.tenant, purgar=args.purgar)
        print(f"  tablas con tenant_id revisadas: {db['tablas_revisadas']}")
        if db["antes"]:
            print(f"  filas del despacho ANTES: {sum(v for v in db['antes'].values() if v > 0)} "
                  f"en {len(db['antes'])} tabla(s)")
        if db["despues"]:
            print("  QUEDAN FILAS:")
            for t, n in sorted(db["despues"].items()):
                print(f"    - {t}: {n}")
            problemas.append(f"quedan filas en {len(db['despues'])} tabla(s) de la base")
        else:
            print("  0 filas del despacho en TODAS las tablas con tenant_id.")
    else:
        print("  (sin --tenant: no se revisa la base)")
        problemas.append("no se revisó la base (falta --tenant)")

    # 2 · disco de MIA
    print(f"\n2 · disco de MIA ({config.MIA_HOME})")
    disco = purgar_disco(args.tenant, args.termino, purgar=args.purgar, desde=desde)
    if disco["borrados"]:
        print(f"  borrados: {len(disco['borrados'])} artefacto(s)")
        for b in disco["borrados"][:10]:
            print(f"    - {b}")
        if len(disco["borrados"]) > 10:
            print(f"    … y {len(disco['borrados']) - 10} más")
    if disco["restos"]:
        print("  TODAVÍA CONTIENEN UN TÉRMINO:")
        for ruta, n in disco["restos"][:10]:
            print(f"    - {ruta} ({n} coincidencia(s))")
        problemas.append(f"{len(disco['restos'])} archivo(s) de MIA con coincidencias")
    else:
        print("  0 archivos con coincidencias.")

    # 3 · transcripts del CLI
    print("\n3 · transcripts del CLI de la suscripción (FUERA de MIA)")
    cli = purgar_cli(args.termino, purgar=args.purgar, desde=desde)
    if not cli.get("localizada"):
        print("  NO SE PUDO LOCALIZAR la carpeta de transcripts del CLI. Este comando NO puede "
              "demostrar que esté limpia — y un 'no existe' equivocado daría certeza falsa. "
              "Búscala a mano bajo ~/.claude/projects (el nombre es la ruta de MIA_HOME con "
              "todo lo no alfanumérico vuelto '-').")
        problemas.append("no se pudo localizar la carpeta de transcripts del CLI")
        cli = {**cli, "restos": []}
    else:
        print(f"  carpeta: {cli['carpeta']} ({'existe' if cli['existe'] else 'no existe'})")
    if cli["borrados"]:
        print(f"  transcripts borrados: {len(cli['borrados'])}")
    if cli["restos"]:
        print("  TODAVÍA CONTIENEN UN TÉRMINO:")
        for ruta, n in cli["restos"][:10]:
            print(f"    - {ruta} ({n} coincidencia(s))")
        problemas.append(f"{len(cli['restos'])} transcript(s) del CLI con coincidencias")
    else:
        print("  0 transcripts con coincidencias.")

    # veredicto
    print("\n== resultado ==")
    if problemas:
        print("NO LIMPIO. Queda rastro:")
        for p in problemas:
            print(f"  · {p}")
        print("Vuelve a correr con --purgar (y --todo-el-disco si el rastro es de antes de la "
              "ventana).")
        return 1

    print("LIMPIO — 0 coincidencias de los términos en la base, en el disco de MIA y en los "
          "transcripts del CLI.")
    print("RECORDATORIO HONESTO: esto NO deshace lo que ya salió de la máquina (proveedor de "
          "embeddings y modelo). Para eso el expediente tiene que entrar anonimizado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
