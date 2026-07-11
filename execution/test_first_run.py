"""
Mia · test_first_run.py — gate REAL del bootstrap de primer arranque (F2 · sesión 43-44).

Corre `mia.setup.first_run.main()` de punta a punta contra un Postgres portable
REAL (el mismo `pg_bin` de desktop/orchestration.json, dev), con `--app-dir` y
`--pg-data` temporales y un puerto efímero libre. Verifica el Contrato 1
completo: .env semilla (escritura atómica), initdb endurecido, rol/DB/
extensiones/schema, migraciones 003→030, checkpointer, marcador
`.mia-setup-complete`, apagado limpio de Postgres, idempotencia (2a corrida),
reparación (marcador borrado), desajuste cluster/.env, initdb interrumpido, y
fallo limpio con pg-bin inválido. Limpieza total en finally (incluye red de
seguridad: detener cualquier postgres que haya quedado vivo antes de rmtree).

Es un SCRIPT, no pytest (mismo patrón que los demás execution/test_*.py):
    .venv\\Scripts\\python.exe execution\\test_first_run.py
Salida: exit 0 = PASS, 1 = FAIL.
"""
from __future__ import annotations

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
from pathlib import Path

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
PYTHON = ROOT / ".venv" / "Scripts" / "python.exe"
ORCH = ROOT / "desktop" / "orchestration.json"
MARKER_NAME = ".mia-setup-complete"

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    _results.append((name, bool(ok)))
    suffix = f" — {detail}" if detail and not ok else ""
    print(("  [OK]   " if ok else "  [FAIL] ") + name + suffix)


def free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def run_first_run(app_dir: Path, pg_bin: Path, pg_data: Path, pg_port: int) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONPATH"] = str(BACKEND)
    return subprocess.run(
        [str(PYTHON), "-m", "mia.setup.first_run",
         "--pg-bin", str(pg_bin), "--pg-data", str(pg_data),
         "--pg-port", str(pg_port), "--app-dir", str(app_dir)],
        cwd=str(ROOT), env=env, capture_output=True, text=True, timeout=600,
    )


def pg_isready(pg_bin: Path, port: int) -> bool:
    r = subprocess.run(
        [str(pg_bin / "pg_isready.exe"), "-h", "127.0.0.1", "-p", str(port)],
        capture_output=True, text=True,
    )
    return r.returncode == 0


def force_stop_pg(pg_bin: Path, pg_data: Path) -> None:
    """Red de seguridad de limpieza (sub-tarea 7g): si por cualquier razón
    (bug en first_run, bug en el propio test) quedó un postgres corriendo
    sobre este pg_data, lo detiene INCONDICIONALMENTE antes de que el caller
    borre la carpeta con rmtree. No falla si ya estaba detenido o si el
    cluster nunca llegó a inicializarse (PG_VERSION ausente)."""
    if not (pg_data / "PG_VERSION").is_file():
        return
    try:
        subprocess.run(
            [str(pg_bin / "pg_ctl.exe"), "-D", str(pg_data), "-m", "fast", "stop"],
            capture_output=True, text=True,
        )
    except OSError:
        pass


def main() -> int:
    print("== first_run: bootstrap de primer arranque (F2 · gate REAL) ==")

    orch = json.loads(ORCH.read_text(encoding="utf-8"))
    pg_bin = Path(orch["db"]["pg_bin"])
    check("pg_bin de desktop/orchestration.json existe", pg_bin.is_dir(), str(pg_bin))
    check("python del .venv existe", PYTHON.is_file(), str(PYTHON))
    if not pg_bin.is_dir() or not PYTHON.is_file():
        passed = sum(1 for _, ok in _results if ok)
        print(f"\nRESULT: {passed}/{len(_results)} checks PASS (no se puede continuar)")
        return 1

    workdir = Path(tempfile.mkdtemp(prefix="mia-test-first-run-"))
    app_dir = workdir / "app"
    pg_data = workdir / "pgdata"
    pg_port = free_port()
    bad_workdir: Path | None = None
    partial_workdir: Path | None = None

    pg_started_for_checks = False

    def stop_check_pg() -> None:
        nonlocal pg_started_for_checks
        if pg_started_for_checks:
            subprocess.run(
                [str(pg_bin / "pg_ctl.exe"), "-D", str(pg_data), "-m", "fast", "stop"],
                capture_output=True, text=True,
            )
            pg_started_for_checks = False

    try:
        # ---- 1a corrida (initdb real #1) ----
        proc = run_first_run(app_dir, pg_bin, pg_data, pg_port)
        check("1a corrida: exit 0", proc.returncode == 0,
              f"stdout: ...{proc.stdout[-800:]}\nstderr: ...{proc.stderr[-800:]}")
        check("1a corrida: imprime progreso MIA-SETUP:", "MIA-SETUP:" in proc.stdout)

        env_path = app_dir / ".env"
        check(".env creado", env_path.is_file())
        env_text_1 = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""

        from dotenv import dotenv_values
        env_values = dotenv_values(env_path) if env_path.is_file() else {}

        check("JWT_SECRET >= 32 caracteres", len(env_values.get("JWT_SECRET") or "") >= 32)
        for key in ("PG_HOST", "PG_PORT", "PG_DB", "PG_PASSWORD", "PG_APP_PASSWORD",
                    "DATABASE_URL", "LITELLM_BASE_URL", "LITELLM_API_KEY",
                    "LITELLM_MASTER_KEY", "MIA_CORS_ORIGINS", "MIA_ENV"):
            check(f".env trae {key}", bool(env_values.get(key)))
        check(".env: VOYAGE_API_KEY presente (vacío por defecto)", "VOYAGE_API_KEY" in env_values)
        check("LITELLM_MASTER_KEY == LITELLM_API_KEY",
              env_values.get("LITELLM_MASTER_KEY") == env_values.get("LITELLM_API_KEY"))
        check("MIA_ENV=prod", env_values.get("MIA_ENV") == "prod")
        check("PG_PORT coincide con el puerto efímero pedido", env_values.get("PG_PORT") == str(pg_port))
        check("DATABASE_URL usa PG_APP_PASSWORD y el puerto pedido",
              (env_values.get("PG_APP_PASSWORD") or "?") in (env_values.get("DATABASE_URL") or "")
              and f":{pg_port}/" in (env_values.get("DATABASE_URL") or ""))

        marker_path = app_dir / MARKER_NAME
        check("marcador .mia-setup-complete existe tras la 1a corrida", marker_path.is_file())
        check("marcador: sin restos de .tmp en app_dir", not (app_dir / (MARKER_NAME + ".tmp")).exists())
        check(".env: sin restos de .env.tmp en app_dir", not (app_dir / ".env.tmp").exists())
        setup_tmp_dir = app_dir / ".setup-tmp"
        check("carpeta privada .setup-tmp fue limpiada al terminar", not setup_tmp_dir.exists())

        check("PG_VERSION existe (initdb corrió)", (pg_data / "PG_VERSION").is_file())
        conf_path = pg_data / "postgresql.conf"
        conf_text = conf_path.read_text(encoding="utf-8") if conf_path.is_file() else ""
        check("postgresql.conf fija listen_addresses = '127.0.0.1'",
              "listen_addresses = '127.0.0.1'" in conf_text)
        check(f"postgresql.conf fija port = {pg_port}", f"port = {pg_port}" in conf_text)

        check("Postgres quedó DETENIDO al terminar first_run", not pg_isready(pg_bin, pg_port))

        # ---- levantamos Postgres SOLO para verificar contenido; lo apagamos después ----
        # Sin capture_output: pg_ctl deja los pipes heredados al demonio postgres.exe
        # y leerlos hasta EOF cuelga este proceso (misma lección que en first_run.py).
        start = subprocess.run(
            [str(pg_bin / "pg_ctl.exe"), "-D", str(pg_data), "-w",
             "-l", str(workdir / "pg-check.log"), "-o", f"-p {pg_port}", "start"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pg_started_for_checks = start.returncode == 0
        check("Postgres arranca para poder verificar su contenido", pg_started_for_checks)

        if pg_started_for_checks:
            import psycopg
            super_pw = env_values.get("PG_PASSWORD") or ""
            kw = dict(host="127.0.0.1", port=pg_port, dbname="mia", user="postgres", password=super_pw)
            with psycopg.connect(autocommit=True, **kw) as c:
                role = c.execute(
                    "SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname='mia_app'"
                ).fetchone()
                check("rol mia_app existe", role is not None)
                if role is not None:
                    check("rol mia_app sin SUPERUSER", role[0] is False)
                    check("rol mia_app sin BYPASSRLS", role[1] is False)

                exts = {r[0] for r in c.execute(
                    "SELECT extname FROM pg_extension WHERE extname IN ('vector','pgcrypto')"
                ).fetchall()}
                check("extensión vector instalada", "vector" in exts)
                check("extensión pgcrypto instalada", "pgcrypto" in exts)

                core_tables = {r[0] for r in c.execute(
                    "SELECT table_name FROM information_schema.tables WHERE table_schema='public' "
                    "AND table_name IN ('tenants','matters','documents','chunks','tenant_settings')"
                ).fetchall()}
                check("tablas núcleo de schema.sql presentes", core_tables == {
                    "tenants", "matters", "documents", "chunks", "tenant_settings"
                }, str(core_tables))

                late = c.execute(
                    "SELECT 1 FROM information_schema.tables WHERE table_schema='public' "
                    "AND table_name='persona_playbooks'"
                ).fetchone()
                check("tabla de migración tardía persona_playbooks presente (030 aplicada)",
                      late is not None)

                ckpt_tables = [r[0] for r in c.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname='public' "
                    "AND tablename LIKE 'checkpoint%'"
                ).fetchall()]
                check("tablas checkpoint* presentes", len(ckpt_tables) > 0, str(ckpt_tables))

                if ckpt_tables:
                    priv_ok = True
                    priv_detail = []
                    for t in ckpt_tables:
                        row = c.execute(
                            "SELECT has_table_privilege('mia_app', %s, 'SELECT'), "
                            "has_table_privilege('mia_app', %s, 'INSERT'), "
                            "has_table_privilege('mia_app', %s, 'UPDATE'), "
                            "has_table_privilege('mia_app', %s, 'DELETE')",
                            (t, t, t, t),
                        ).fetchone()
                        ok_row = bool(row) and all(row)
                        priv_ok = priv_ok and ok_row
                        if not ok_row:
                            priv_detail.append(t)
                    check("mia_app tiene SELECT/INSERT/UPDATE/DELETE en tablas checkpoint*",
                          priv_ok, str(priv_detail))

            # (a) login REAL como mia_app vía DATABASE_URL del .env generado.
            database_url = env_values.get("DATABASE_URL") or ""
            try:
                with psycopg.connect(database_url, autocommit=True) as mc:
                    row = mc.execute("SELECT 1").fetchone()
                check("login real como mia_app (DATABASE_URL) + SELECT 1", row == (1,))
            except Exception as exc:  # noqa: BLE001
                check("login real como mia_app (DATABASE_URL) + SELECT 1", False, repr(exc))

        stop_check_pg()
        check("Postgres re-detenido tras la verificación", not pg_isready(pg_bin, pg_port))

        # ---- 2a corrida: idempotencia ----
        proc2 = run_first_run(app_dir, pg_bin, pg_data, pg_port)
        check("2a corrida: exit 0", proc2.returncode == 0,
              f"stdout: ...{proc2.stdout[-800:]}\nstderr: ...{proc2.stderr[-800:]}")
        env_text_2 = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
        check(".env intacto BYTE A BYTE tras la 2a corrida (secretos nunca regenerados)",
              env_text_1 == env_text_2)
        check("2a corrida: Postgres también queda detenido", not pg_isready(pg_bin, pg_port))
        check("2a corrida: marcador existe", marker_path.is_file())

        # ---- (c) escenario de reparación: borrar SOLO el marcador y re-correr ----
        marker_path.unlink(missing_ok=True)
        check("reparación: marcador borrado antes de re-correr", not marker_path.is_file())
        proc_repair = run_first_run(app_dir, pg_bin, pg_data, pg_port)
        check("reparación (marcador borrado): exit 0", proc_repair.returncode == 0,
              f"stdout: ...{proc_repair.stdout[-800:]}\nstderr: ...{proc_repair.stderr[-800:]}")
        env_text_repair = env_path.read_text(encoding="utf-8") if env_path.is_file() else ""
        check("reparación (marcador borrado): .env byte-idéntico", env_text_1 == env_text_repair)
        check("reparación (marcador borrado): marcador quedó recreado", marker_path.is_file())
        check("reparación (marcador borrado): Postgres queda detenido", not pg_isready(pg_bin, pg_port))

        # (sub-tarea 6) en una corrida de reparación, ensure_app_role_and_database
        # toma la rama ALTER (el rol mia_app ya existe) — confirmamos que la
        # contraseña re-aplicada SIGUE calzando con DATABASE_URL levantando
        # Postgres una vez más y haciendo login real como mia_app.
        start_repair = subprocess.run(
            [str(pg_bin / "pg_ctl.exe"), "-D", str(pg_data), "-w",
             "-l", str(workdir / "pg-check-repair.log"), "-o", f"-p {pg_port}", "start"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        pg_started_for_checks = start_repair.returncode == 0
        check("reparación: Postgres arranca para verificar login post-ALTER", pg_started_for_checks)
        if pg_started_for_checks:
            import psycopg
            try:
                with psycopg.connect(env_values.get("DATABASE_URL") or "", autocommit=True) as mc:
                    row = mc.execute("SELECT 1").fetchone()
                check("login mia_app tras rama ALTER (reparación): contraseña sigue calzando",
                      row == (1,))
            except Exception as exc:  # noqa: BLE001
                check("login mia_app tras rama ALTER (reparación): contraseña sigue calzando",
                      False, repr(exc))
        stop_check_pg()

        # ---- (d) escenario de desajuste: borrar SOLO el .env, dejando el cluster ----
        env_path.unlink(missing_ok=True)
        check("desajuste: .env borrado antes de re-correr (cluster intacto)", not env_path.is_file())
        proc_mismatch = run_first_run(app_dir, pg_bin, pg_data, pg_port)
        check("desajuste (.env borrado): exit != 0", proc_mismatch.returncode != 0)
        mismatch_lines = [ln for ln in proc_mismatch.stdout.splitlines() if ln.strip()]
        mismatch_last = mismatch_lines[-1] if mismatch_lines else ""
        check("desajuste (.env borrado): última línea en llano describe el problema",
              mismatch_last.startswith("MIA-SETUP:")
              and "base de datos previa" in mismatch_last
              and "configuración" in mismatch_last,
              repr(mismatch_last))
        check("desajuste (.env borrado): NO se regeneró un .env nuevo", not env_path.is_file())
        check("desajuste (.env borrado): cluster intacto (PG_VERSION sigue ahí)",
              (pg_data / "PG_VERSION").is_file())
        check("desajuste (.env borrado): Postgres no quedó corriendo", not pg_isready(pg_bin, pg_port))

        # ---- fallo limpio con pg-bin inválido ----
        bad_workdir = Path(tempfile.mkdtemp(prefix="mia-test-first-run-badbin-"))
        bad_pg_bin = bad_workdir / "no-hay-postgres-aqui"
        bad_pg_bin.mkdir(parents=True, exist_ok=True)  # carpeta real, pero SIN los .exe de Postgres
        bad_app_dir = bad_workdir / "app"
        bad_pg_data = bad_workdir / "pgdata"
        bad_port = free_port()
        proc3 = run_first_run(bad_app_dir, bad_pg_bin, bad_pg_data, bad_port)
        check("pg-bin inválido: exit != 0", proc3.returncode != 0)
        stdout_lines = [ln for ln in proc3.stdout.splitlines() if ln.strip()]
        last_line = stdout_lines[-1] if stdout_lines else ""
        check("pg-bin inválido: última línea de stdout es un mensaje en llano, sin stacktrace",
              last_line.startswith("MIA-SETUP:") and "No se pudo preparar Mia" in last_line,
              repr(last_line))
        check("pg-bin inválido: el stacktrace (si lo hay) NO quedó en stdout",
              "Traceback" not in proc3.stdout)

        # ---- (e) escenario de initdb a medias: pg_data no vacío, sin PG_VERSION ----
        # Simula un initdb interrumpido de una corrida anterior (p. ej. corte de
        # energía a mitad de camino). first_run debe limpiar el CONTENIDO de
        # pg_data y reintentar, no fallar ni tocar nada fuera de pg_data.
        partial_workdir = Path(tempfile.mkdtemp(prefix="mia-test-first-run-partial-"))
        partial_app_dir = partial_workdir / "app"
        partial_pg_data = partial_workdir / "pgdata"
        partial_pg_data.mkdir(parents=True, exist_ok=True)
        garbage_file = partial_pg_data / "garbage-de-initdb-interrumpido.txt"
        garbage_file.write_text("basura de un initdb que no terminó", encoding="utf-8")
        garbage_subdir = partial_pg_data / "base"
        garbage_subdir.mkdir(parents=True, exist_ok=True)
        (garbage_subdir / "algo.tmp").write_text("mas basura", encoding="utf-8")
        partial_port = free_port()

        proc_partial = run_first_run(partial_app_dir, pg_bin, partial_pg_data, partial_port)
        check("initdb a medias: exit 0", proc_partial.returncode == 0,
              f"stdout: ...{proc_partial.stdout[-800:]}\nstderr: ...{proc_partial.stderr[-800:]}")
        check("initdb a medias: menciona la limpieza en el progreso",
              "incompleto" in proc_partial.stdout or "limpia" in proc_partial.stdout)
        check("initdb a medias: PG_VERSION existe tras limpiar y reintentar",
              (partial_pg_data / "PG_VERSION").is_file())
        check("initdb a medias: la basura previa fue eliminada", not garbage_file.exists())
        check("initdb a medias: Postgres quedó detenido al terminar",
              not pg_isready(pg_bin, partial_port))
        check("initdb a medias: carpeta padre (workdir) sigue intacta", partial_workdir.is_dir())

    except Exception as exc:  # noqa: BLE001 - cualquier falla inesperada del gate se reporta, no revienta
        check("el gate corrió sin excepciones inesperadas", False, repr(exc))
    finally:
        stop_check_pg()
        # (g) red de seguridad: si algo dejó un postgres vivo sobre estos
        # pg_data, se detiene incondicionalmente ANTES del rmtree.
        force_stop_pg(pg_bin, pg_data)
        shutil.rmtree(workdir, ignore_errors=True)
        if bad_workdir is not None:
            shutil.rmtree(bad_workdir, ignore_errors=True)
        if partial_workdir is not None:
            force_stop_pg(pg_bin, partial_workdir / "pgdata")
            shutil.rmtree(partial_workdir, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
