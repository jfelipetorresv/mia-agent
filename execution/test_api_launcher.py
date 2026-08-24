"""
Mia · test_api_launcher.py — GATE del lanzador canónico del API.

═══ POR QUÉ EXISTE ═══════════════════════════════════════════════════════════
`python -m mia.api.run` es el camino de `scripts/start_api.ps1` (Modo B) y de la
cáscara de escritorio, y NINGÚN gate lo ejecutaba: todas las suites montan la app
por otra vía (TestClient/uvicorn directo). El 2026-08-15 se encontró que llevaba
roto en Windows un tiempo indeterminado — una local `config = uvicorn.Config(...)`
sombreaba el módulo `config` y el arranque moría con UnboundLocalError — sin que
nada se pusiera rojo (regla 79 de APRENDIZAJES.md: «el lanzador que ningún gate
ejecuta está roto hasta que se demuestre lo contrario»).

═══ QUÉ HACE ═════════════════════════════════════════════════════════════════
Arranca el lanzador DE VERDAD (subproceso, cwd=backend/ — lanzado desde la raíz
el pool muere con ProactorEventLoop, regla 62), espera GET /health == 200 en un
puerto libre elegido al azar, y lo apaga. Si el proceso muere antes del health,
imprime su stderr: el UnboundLocalError de 2026-08-15 se habría visto aquí.

Necesita la base de datos del .env encendida (el lifespan abre el pool). Sin DB
el gate NO se declara verde: falla con PRECHECK explícito.

Exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_api_launcher.py
"""
from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def _db_reachable() -> bool:
    """Sonda de socket (regla 13: nada de Test-NetConnection/psql interactivo)."""
    from dotenv import load_dotenv

    load_dotenv(ROOT / ".env")
    host = os.getenv("PG_HOST", "127.0.0.1")
    port = int(os.getenv("PG_PORT", "5432"))
    try:
        with socket.create_connection((host, port), timeout=3):
            return True
    except OSError:
        return False


def _health_status(port: int) -> int | None:
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/health", timeout=2
        ) as resp:
            return resp.status
    except Exception:  # noqa: BLE001 — aún no arriba; se sigue sondeando
        return None


def run() -> None:
    print("== GATE · lanzador canónico `python -m mia.api.run` hasta /health 200 ==")

    if not _db_reachable():
        # Un gate que se salta la prueba en silencio es un gate ciego (regla 1).
        check("PRECHECK · la base de datos del .env responde (requisito del lifespan)", False)
        return

    port = _free_port()
    env = dict(os.environ)
    env.update(
        MIA_API_PORT=str(port),
        MIA_API_RELOAD="0",
        PYTHONPATH=str(ROOT / "backend"),
        PYTHONUTF8="1",
        PYTHONIOENCODING="utf-8",
    )
    # El puente de Telegram no debe arrancar en un gate aunque el .env traiga token.
    env.pop("TELEGRAM_BOT_TOKEN", None)

    proc = subprocess.Popen(
        [sys.executable, "-m", "mia.api.run"],
        cwd=str(ROOT / "backend"),  # regla 62: desde la raíz el pool muere (Proactor)
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        # Sin ventana de consola: en Windows este gate le sacaba una terminal negra al
        # abogado en pleno trabajo (orden de Pipe 2026-08-24). En otros SO el flag es 0.
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )
    check("el subproceso del lanzador se creó", proc.poll() is None)

    budget_s = float(os.getenv("MIA_LAUNCHER_GATE_BUDGET_S", "120"))
    deadline = time.monotonic() + budget_s
    status: int | None = None
    died_early = False
    t0 = time.monotonic()
    while time.monotonic() < deadline:
        if proc.poll() is not None:
            died_early = True
            break
        status = _health_status(port)
        if status is not None:
            break
        time.sleep(0.5)
    elapsed = time.monotonic() - t0

    if died_early:
        out = (proc.stdout.read() if proc.stdout else "") or ""
        print(f"\n  el lanzador MURIÓ antes del health (exit {proc.returncode}). Salida:")
        print("  " + "\n  ".join(out.strip().splitlines()[-30:]))
    check(f"el lanzador no murió durante el arranque (esperó {elapsed:.1f}s)",
          not died_early)
    check(f"GET /health respondió 200 dentro de {budget_s:.0f}s "
          f"(respondió: {status})", status == 200)

    # Apagado: el lanzador es UN proceso (uvicorn single-process, reload=0).
    if proc.poll() is None:
        proc.kill()
        try:
            proc.wait(timeout=15)
        except subprocess.TimeoutExpired:
            pass
    check("el proceso del lanzador quedó terminado", proc.poll() is not None)


def main() -> int:
    run()
    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("lanzador OK — `python -m mia.api.run` arranca hasta /health 200 (regla 79 cubierta).")
        return 0
    print("lanzador FAIL — el camino de start_api.ps1 no llega a /health 200.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
