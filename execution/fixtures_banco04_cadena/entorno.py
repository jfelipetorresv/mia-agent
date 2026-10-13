"""Proceso hermético para las pruebas de la cadena (banco04-cadena/v5).

`preparar_proceso()` se llama ANTES de importar nada de `mia`:

  · escribe un `MIA_TEST_ENV_FILE` SINTÉTICO fuera del repo (puerto 55448, nunca 55432) y vuelca
    sus valores al proceso, como hace `run_banco04.aplicar_entorno`. `mia.config` se importa una
    sola vez por proceso: todos los escenarios comparten este MIA_HOME y esta DATABASE_URL;
  · neutraliza `dotenv.load_dotenv` SOLO para el `.env` del repositorio: el proceso de pruebas
    nunca carga la instalación (ni claves de API ni rutas);
  · deja el proceso SIN sesión de CLI ni claves: `CLAUDE_CONFIG_DIR` y `CODEX_HOME` vacíos, claves
    de API vacías y `LITELLM_BASE_URL` a un puerto local cerrado. Si una implementación ignorase los
    dobles, la llamada real fallaría sin sesión en vez de gastar cuota (defensa en profundidad);
  · `LOCALAPPDATA` y `MIA_BANCO04_CUSTODIA` apuntan a carpetas temporales: nada toca el registro de
    uso real ni la custodia real.
"""
from __future__ import annotations

import atexit
import contextlib
import hashlib
import json
import os
import shutil
import socket
import sys
import tempfile
from pathlib import Path
from typing import Iterator, Optional

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
EXEC = ROOT / "execution"
FIXTURES = Path(__file__).resolve().parent
DIR_INSTANTANEAS = BACKEND / "mia" / "eval" / "banco04" / "telemetria_acreditada"
PUERTO_AISLADO = "55448"
PUERTO_PROHIBIDO = "55432"

# Lo que había en el entorno ANTES de aislar el proceso (solo se usa para la precondición del
# clúster aislado de E2E-1: el `MIA_TEST_ENV_FILE` que provea el implementador).
ENTORNO_ORIGINAL: dict[str, str] = dict(os.environ)

_ESTADO: dict = {"preparado": False, "raiz": None, "instantaneas_creadas": []}

CLAVES_A_VACIAR = ("ANTHROPIC_API_KEY", "OPENAI_API_KEY", "OPENROUTER_API_KEY", "GEMINI_API_KEY",
                   "GOOGLE_API_KEY", "MINIMAX_API_KEY", "PINECONE_API_KEY", "MISTRAL_API_KEY",
                   "DEEPSEEK_API_KEY", "TELEGRAM_BOT_TOKEN", "CLAUDE_CODE_OAUTH_TOKEN",
                   "VOYAGE_API_KEY", "AZURE_API_KEY", "COHERE_API_KEY")


def rutas_python() -> None:
    for p in (str(BACKEND), str(EXEC), str(FIXTURES.parent)):
        if p not in sys.path:
            sys.path.insert(0, p)


def raiz() -> Path:
    if _ESTADO["raiz"] is None:
        raise RuntimeError("preparar_proceso() no se llamó")
    return _ESTADO["raiz"]


def nueva_carpeta(nombre: str) -> Path:
    """Carpeta temporal nueva (fuera del repo) bajo la raíz del proceso."""
    p = Path(tempfile.mkdtemp(prefix=f"{nombre}-", dir=str(raiz())))
    return p


def _guardar_dotenv() -> None:
    try:
        import dotenv  # noqa: WPS433
    except ImportError:
        return
    original = dotenv.load_dotenv
    env_repo = (ROOT / ".env").resolve()

    def load_dotenv(dotenv_path=None, *a, **kw):  # noqa: ANN001
        try:
            if dotenv_path is not None and Path(dotenv_path).resolve() == env_repo:
                return False                    # nunca la instalación en el proceso de pruebas
        except (OSError, TypeError, ValueError):
            pass
        return original(dotenv_path, *a, **kw)

    load_dotenv.__wrapped__ = original           # type: ignore[attr-defined]
    dotenv.load_dotenv = load_dotenv


def valores_aislados(base: Path) -> dict:
    return {"PG_HOST": "127.0.0.1", "PG_PORT": PUERTO_AISLADO, "PG_DB": "mia_banco04_dobles",
            "PG_PASSWORD": "dobles-sin-uso", "PG_APP_PASSWORD": "dobles-sin-uso",
            "DATABASE_URL": f"postgresql://mia_app:dobles-sin-uso@127.0.0.1:{PUERTO_AISLADO}/"
                            "mia_banco04_dobles",
            "MIA_HOME": str(base / "mia-home")}


def preparar_proceso(env_real: Optional[Path] = None) -> Path:
    """Aísla el proceso. Idempotente. Devuelve la raíz temporal (fuera del repo).

    `env_real`: SOLO para el proceso hijo de E2E-1 (esqueleto con base de datos): usa el
    `MIA_TEST_ENV_FILE` del clúster aislado 55448 que provee el implementador, ya validado por
    `cluster_aislado()`. Todo lo demás (sin sesión de CLI, sin claves, sin red) se mantiene."""
    if _ESTADO["preparado"]:
        return _ESTADO["raiz"]
    base = Path(tempfile.mkdtemp(prefix="banco04-cadena-"))
    if ROOT in base.resolve().parents:
        raise RuntimeError("la carpeta temporal cae bajo el repositorio")
    _ESTADO["raiz"] = base
    (base / "mia-home").mkdir()
    if env_real is not None:
        from dotenv import dotenv_values  # noqa: WPS433
        valores = {k: v for k, v in dotenv_values(str(env_real)).items() if v is not None}
        if str(valores.get("PG_PORT")) != PUERTO_AISLADO:
            raise RuntimeError("el entorno real no es el clúster aislado 55448")
        env_file = Path(env_real)
    else:
        valores = valores_aislados(base)
        env_file = base / "entorno-aislado-sintetico.env"
        env_file.write_text("\n".join(f"{k}={v}" for k, v in valores.items()) + "\n", encoding="utf-8")
    for d in ("claude-sin-sesion", "codex-sin-sesion", "localappdata", "sin-custodia-real"):
        (base / d).mkdir()
    os.environ.update(valores)
    os.environ["MIA_TEST_ENV_FILE"] = str(env_file)
    os.environ["MIA_ENV"] = "dev"
    os.environ["CLAUDE_CONFIG_DIR"] = str(base / "claude-sin-sesion")
    os.environ["CODEX_HOME"] = str(base / "codex-sin-sesion")
    os.environ["LOCALAPPDATA"] = str(base / "localappdata")
    # Una carpeta que NO es custodia: abrirla falla cerrado salvo que un escenario la sustituya.
    os.environ["MIA_BANCO04_CUSTODIA"] = str(base / "sin-custodia-real")
    os.environ["LITELLM_BASE_URL"] = "http://127.0.0.1:9"
    os.environ["LITELLM_API_KEY"] = "sk-dobles-sin-red"
    for k in CLAVES_A_VACIAR:
        os.environ[k] = ""
    os.environ.pop("CI", None)
    os.environ.pop("GITHUB_ACTIONS", None)
    _guardar_dotenv()
    rutas_python()
    _ESTADO["preparado"] = True
    atexit.register(limpiar)
    return base


def limpiar() -> None:
    for p in list(_ESTADO["instantaneas_creadas"]):
        with contextlib.suppress(OSError):
            Path(p).unlink()
    _ESTADO["instantaneas_creadas"].clear()
    r = _ESTADO.get("raiz")
    if r is not None and os.environ.get("BANCO04_CADENA_CONSERVAR") != "1":
        shutil.rmtree(r, ignore_errors=True)


@contextlib.contextmanager
def entorno(**cambios: Optional[str]) -> Iterator[None]:
    """Cambia variables de entorno y las restaura al salir."""
    previos = {k: os.environ.get(k) for k in cambios}
    try:
        for k, v in cambios.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        yield
    finally:
        for k, v in previos.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


@contextlib.contextmanager
def manifiesto_custodia(ruta: Path) -> Iterator[None]:
    """La custodia de prueba se abre con su PROPIO manifiesto: `custodia._MANIFEST_PATH` apunta a él
    mientras dura el escenario (el manifiesto del repo describe la custodia real, que nunca se abre).
    Interfaz fijada por las pruebas: la cadena localiza el manifiesto de custodia por
    `custodia.cargar_manifiesto()` / `custodia._MANIFEST_PATH`, consultado en tiempo de llamada."""
    from mia.eval.banco04 import custodia as cus  # noqa: WPS433
    previo = cus._MANIFEST_PATH
    cus._MANIFEST_PATH = Path(ruta)
    try:
        yield
    finally:
        cus._MANIFEST_PATH = previo


# ── precondición del clúster aislado (solo E2E-1 y las mutaciones del esqueleto con BD) ───────
def cluster_aislado() -> tuple[bool, str, Optional[Path]]:
    """(disponible, motivo, ruta del env). Nunca intenta el 55432."""
    ruta = (ENTORNO_ORIGINAL.get("MIA_TEST_ENV_FILE") or "").strip()
    if not ruta:
        return False, "clúster aislado no disponible: MIA_TEST_ENV_FILE no está definido", None
    p = Path(ruta)
    if not p.is_file():
        return False, f"clúster aislado no disponible: {p} no existe", None
    try:
        if p.resolve() == (ROOT / ".env").resolve() or ROOT in p.resolve().parents:
            return False, "clúster aislado no disponible: el env apunta al repositorio", None
    except OSError:
        return False, "clúster aislado no disponible: ruta ilegible", None
    try:
        from dotenv import dotenv_values  # noqa: WPS433
        vals = dotenv_values(str(p))
    except Exception as exc:  # noqa: BLE001
        return False, f"clúster aislado no disponible: env ilegible ({type(exc).__name__})", None
    puerto = str(vals.get("PG_PORT") or "")
    host = str(vals.get("PG_HOST") or "127.0.0.1")
    if puerto == PUERTO_PROHIBIDO:
        return False, "clúster aislado no disponible: el env declara el 55432 (prohibido)", None
    if puerto != PUERTO_AISLADO:
        return False, f"clúster aislado no disponible: PG_PORT={puerto!r} ≠ 55448", None
    if host not in ("127.0.0.1", "localhost", "::1"):
        return False, f"clúster aislado no disponible: host {host!r} no local", None
    try:
        with socket.create_connection((host, int(PUERTO_AISLADO)), timeout=1.5):
            pass
    except OSError as exc:
        return False, f"clúster aislado no disponible: sin conexión a {host}:55448 ({exc})", None
    return True, "ok", p


# ── instantáneas de acreditación de prueba (§4.4) ─────────────────────────────────────────────
def instalar_instantanea(contenido: dict) -> tuple[str, Path]:
    """Escribe una instantánea de PRUEBA, direccionada por contenido, en el directorio que fija el
    contrato (§4.4: `backend/mia/eval/banco04/telemetria_acreditada/<sha256>.json`).

    El contrato no admite otra ubicación y exige que cada R1 cite una instantánea con TODAS sus
    `firmas_previstas` acreditadas, así que una prueba que corra el runner no puede evitarlo. Se
    escribe solo si el directorio YA existe (lo crea la implementación; si falta, la prueba queda
    en rojo con ese motivo) y se borra al terminar el proceso."""
    if not DIR_INSTANTANEAS.is_dir():
        raise FileNotFoundError(f"no existe el directorio de instantáneas {DIR_INSTANTANEAS} (§4.4)")
    datos = canonico(contenido)
    sha = hashlib.sha256(datos).hexdigest()
    ruta = DIR_INSTANTANEAS / f"{sha}.json"
    if not ruta.exists():
        ruta.write_bytes(datos)
        _ESTADO["instantaneas_creadas"].append(str(ruta))
    return sha, ruta


def instalar_instantanea_corrupta(contenido: dict) -> tuple[str, Path]:
    """I15: una instantánea cuyo NOMBRE ya no es el sha256 de sus bytes (editada en sitio)."""
    sha, ruta = instalar_instantanea(contenido)
    datos = ruta.read_bytes()
    editado = datos.replace(b'"presente_siempre"', b'"omitido_si_cero"', 1)
    if editado == datos:
        editado = datos + b" "
    nombre = hashlib.sha256(datos + b"#i15").hexdigest()
    corrupta = DIR_INSTANTANEAS / f"{nombre}.json"
    corrupta.write_bytes(editado)
    _ESTADO["instantaneas_creadas"].append(str(corrupta))
    return nombre, corrupta


def canonico(obj) -> bytes:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def sha256_archivo(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def copiar_arbol(origen: Path, destino: Path) -> Path:
    shutil.copytree(origen, destino)
    return destino
