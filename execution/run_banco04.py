"""
Mia · run_banco04.py — runner de PRODUCCIÓN del banco de calidad 0.4 (protocolo banco04-v1.2).

Qué hace este archivo (ítem 6 de §10.2) y qué NO:
  · produce las corridas (turno hasta la pantalla de revisión) de los 17 casos × R repeticiones
    y las persiste una por una; NO juzga (eso es `mia.eval.banco04.jueces`) y NO agrega.
  · NO usa `execution/run_eval.py`: ese archivo carga el `.env` del repositorio (`:65`) y conecta
    sin guarda de aislamiento (`:82-83`). Este importa `mia` SOLO después de fijar el entorno
    aislado, porque `mia.config` hace `load_dotenv(<repo>/.env)` al importarse (no sobrescribe
    lo ya presente en el entorno, así que el orden es la defensa).

Piezas puras (todas con su gate en `execution/test_banco04_produccion.py`):
  1. `verificar_aislamiento`  §9.3 — exige `MIA_TEST_ENV_FILE`; rechaza el `.env` del repo, el
     puerto 55432, un host que no sea local y un `MIA_HOME` que sea el de la instalación. Usa
     `isolated_test_env.select`, pero NO confía solo en ella: `select` tiene una salida por CI
     (`CI=true` + `PG_*` en el entorno) que se salta archivo y puerto; aquí se le quita `CI` y
     además se revisa el puerto por cuenta propia.
  2. `politica_fija`          §9.1 — `quality_adaptive` y nada más, comprobada en cada corrida.
  3. `clasificar_fallo`       §9.5 — infraestructura / producto / límite de uso.
  4. `ContadorCuota`          §3.4 + §5.5 — acumulado contra el techo, con la RESERVA del juicio
     apartada y la cota conservadora de los intentos fallidos; sin cota → NO CERTIFICABLE (P10).
  5. `decidir_r`              §3.4 — tanda piloto: la decisión de bajar R se toma SOLO con consumo
     (la firma no admite ningún dato de calidad) y deja escrita la cifra que la disparó.
  6. `elegir_aprobaciones`    §5.5 — submuestra determinista: una repetición por caso.
  7. `ejecutar_banco`         §9.5 — idempotente (un archivo por versión·caso·repetición,
     atómico), un reintento de infraestructura con los dos intentos listados, tramos de menos
     de 10 min y suspensión «incompleto — no certificable» (P11).

Las constantes del protocolo (techos, reserva, R, ids de fuga) NO se duplican aquí: `main()` las
importa de `mia.eval.banco04.protocolo` y falla cerrado si no existe o le falta alguna.

Uso (con el entorno aislado ya levantado por otro encargo: clúster sintético ≠ 55432):

    $env:MIA_TEST_ENV_FILE = 'C:\\ruta\\fuera\\del\\repo\\banco04.env'
    .venv\\Scripts\\python.exe execution\\run_banco04.py --plan  --version 0.4 --sha <sha> ...
    .venv\\Scripts\\python.exe execution\\run_banco04.py --version 0.4 --sha <sha> --bloque 0 \\
        --salida D:\\banco04\\runs --soul-plantilla D:\\banco04\\SOUL.md --max-minutos 9
Códigos de salida: 0 = banco terminado · 10 = tramo agotado, relanzar (idempotente) ·
2 = SUSPENDIDO, «incompleto — no certificable» · 3 = rechazado por aislamiento/configuración.
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Awaitable, Callable, Iterable, Mapping, Optional
from types import SimpleNamespace
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "execution"))   # isolated_test_env

import isolated_test_env  # noqa: E402

# ── constantes que SON del runner (el resto vive en protocolo.py) ────────────
POLITICA_FIJA = "quality_adaptive"          # §9.1: política fija en las dos versiones
PUERTO_INSTALADO = "55432"                  # el clúster de la instalación: prohibido (§9.2/§9.3)
HOSTS_LOCALES = ("127.0.0.1", "localhost", "::1")
TEXTO_INCOMPLETO = "incompleto — no certificable"   # §3.4, literal
ESTADOS_TERMINALES = ("completo", "fallo_producto", "fallo_infraestructura")
MAX_INTENTOS_INFRA = 2                      # un intento + UN reintento (§9.5)
EXIT_OK, EXIT_SUSPENDIDO, EXIT_RECHAZADO, EXIT_TRAMO = 0, 2, 3, 10


class AislamientoError(RuntimeError):
    """El entorno no es el aislado del banco: el runner rechaza arrancar."""


class BancoAbortado(RuntimeError):
    """Una condición de fail-closed (SOUL alterado, caso no sintético…) detiene el banco."""


# ══════════════════════════════════════════════════════════════════════════════
# 1 · Guarda de aislamiento (§9.3)
# ══════════════════════════════════════════════════════════════════════════════
def _resolver(ruta: Any) -> Path:
    return Path(str(ruta)).expanduser().resolve()


def _mismo_o_dentro(a: Path, b: Path) -> bool:
    try:
        a.relative_to(b)
        return True
    except ValueError:
        return False


def homes_instalados(repo_root: Path, read_file: Callable[[str], Mapping] | None = None) -> list[Path]:
    """`MIA_HOME` de la INSTALACIÓN: el default `<repo>/mia-data` y el que declare el `.env` del
    repo (se lee solo la clave MIA_HOME para compararla; no se carga al entorno)."""
    repo_root = _resolver(repo_root)
    homes = [(repo_root / "mia-data").resolve()]
    env_repo = repo_root / ".env"
    if env_repo.is_file():
        try:
            leer = read_file or isolated_test_env.dotenv_values
            declarado = (leer(str(env_repo)) or {}).get("MIA_HOME")
        except Exception:  # noqa: BLE001 — un .env ilegible no autoriza nada
            declarado = None
        if declarado:
            p = Path(str(declarado))
            homes.append((p if p.is_absolute() else repo_root / p).resolve())
    return homes


def verificar_aislamiento(environ: Mapping[str, str], *, repo_root: Path,
                          read_file: Callable[[str], Mapping] | None = None) -> dict:
    """Devuelve los valores del entorno aislado o levanta `AislamientoError`.

    El runner rechaza arrancar si: no hay `MIA_TEST_ENV_FILE`; ese archivo ES el `.env` del repo;
    el puerto es 55432 (o falta); el host no es local; `MIA_HOME` falta o es el de la instalación.
    """
    repo_root = _resolver(repo_root)
    ruta = (environ.get("MIA_TEST_ENV_FILE") or "").strip()
    if not ruta:
        raise AislamientoError("MIA_TEST_ENV_FILE debe apuntar al entorno aislado del banco "
                               "(sin él el runner no arranca).")
    archivo = _resolver(ruta)
    if not archivo.is_file():
        raise AislamientoError(f"MIA_TEST_ENV_FILE no es un archivo: {archivo}")
    env_repo = repo_root / ".env"
    if archivo == env_repo.resolve() or (env_repo.exists() and archivo.samefile(env_repo)):
        raise AislamientoError("MIA_TEST_ENV_FILE apunta al .env del repositorio: eso es la "
                               "instalación, no el entorno aislado.")
    # `select` tiene una salida por CI que se salta archivo y puerto. Aquí no existe ese camino.
    limpio = {k: v for k, v in environ.items() if k not in ("CI", "GITHUB_ACTIONS")}
    try:
        valores = dict(isolated_test_env.select(limpio, read_file or isolated_test_env.dotenv_values))
    except RuntimeError as exc:
        raise AislamientoError(str(exc)) from exc
    puerto = str(valores.get("PG_PORT") or "").strip()
    if not puerto:
        raise AislamientoError("El entorno aislado no declara PG_PORT.")
    if puerto == PUERTO_INSTALADO:
        raise AislamientoError(f"El puerto {PUERTO_INSTALADO} es el clúster de la instalación: "
                               "el banco corre en un clúster sintético distinto.")
    host = str(valores.get("PG_HOST") or "127.0.0.1").strip()
    if host not in HOSTS_LOCALES:
        raise AislamientoError(f"PG_HOST={host!r}: el clúster sintético escucha solo en local.")
    # El pool y el checkpointer de `mia` NO usan PG_*: abren `config.DATABASE_URL`. Si el entorno
    # aislado no la declara, `mia.config` la toma del `.env` del repo (= la instalación, :55432)
    # y las corridas escribirían en la base instalada aunque PG_PORT diga otra cosa.
    url = str(valores.get("DATABASE_URL") or "").strip()
    if not url:
        raise AislamientoError("El entorno aislado debe declarar DATABASE_URL (con ella abre `mia` "
                               "su pool; sin ella la tomaría del .env del repositorio).")
    try:
        partes = urlsplit(url)
        url_puerto, url_host = partes.port, (partes.hostname or "")
    except ValueError as exc:
        raise AislamientoError(f"DATABASE_URL no es una URL válida: {exc}") from exc
    if str(url_puerto) == PUERTO_INSTALADO:
        raise AislamientoError(f"DATABASE_URL apunta al puerto {PUERTO_INSTALADO} (la instalación).")
    if str(url_puerto) != puerto:
        raise AislamientoError(f"DATABASE_URL (puerto {url_puerto}) no coincide con PG_PORT ({puerto}).")
    if url_host not in HOSTS_LOCALES:
        raise AislamientoError(f"DATABASE_URL apunta a {url_host!r}: el clúster sintético es local.")
    home_txt = str(valores.get("MIA_HOME") or environ.get("MIA_HOME") or "").strip()
    if not home_txt:
        raise AislamientoError("El entorno aislado no declara MIA_HOME (un MIA_HOME sintético "
                               "por versión, §9.2).")
    home = _resolver(home_txt)
    for instalado in homes_instalados(repo_root):
        if home == instalado or _mismo_o_dentro(home, instalado):
            raise AislamientoError(f"MIA_HOME={home} es el de la instalación ({instalado}).")
    valores["MIA_HOME"] = str(home)
    return valores


def aplicar_entorno(valores: Mapping[str, Any], environ: dict | None = None) -> None:
    """Vuelca el entorno aislado SOBRE el proceso, ANTES de importar `mia` (así el
    `load_dotenv` de `mia.config` no puede traer los valores del repo: no sobrescribe)."""
    destino = os.environ if environ is None else environ
    for k, v in valores.items():
        if v is not None:
            destino[str(k)] = str(v)
    destino["MIA_ENV"] = "dev"


def verificar_entorno_cargado(valores: Mapping[str, Any], environ: Mapping[str, str],
                              config_home: Any, config_url: Any = None) -> None:
    """Después de importar `mia`: lo que quedó vivo es el entorno aislado, no el del repo.
    `config_url` es `mia.config.DATABASE_URL` (lo que de verdad abre el pool)."""
    if str(environ.get("PG_PORT")) != str(valores.get("PG_PORT")):
        raise AislamientoError("Tras importar mia, PG_PORT no es el del entorno aislado.")
    if str(environ.get("PG_PORT")) == PUERTO_INSTALADO:
        raise AislamientoError(f"Tras importar mia, el puerto es {PUERTO_INSTALADO}.")
    if _resolver(config_home) != _resolver(valores.get("MIA_HOME")):
        raise AislamientoError("Tras importar mia, MIA_HOME no es el del entorno aislado.")
    if config_url is None or str(config_url) != str(valores.get("DATABASE_URL")):
        raise AislamientoError("Tras importar mia, config.DATABASE_URL no es la del entorno "
                               "aislado (el pool abriría otra base).")


def verificar_salida_custodia(destino: Path, *, repo_root: Path, mia_home: Any, salida: Path) -> Path:
    """Carpeta para los crudos de los casos CUSTODIADOS: fuera del repo, fuera de `MIA_HOME` y
    aparte de la salida común (el texto en claro de V1-V4 no puede quedar en ninguno de ellos)."""
    p = verificar_salida_fuera_del_repo(destino, repo_root)
    home, sal = _resolver(mia_home), _resolver(salida)
    if p == home or _mismo_o_dentro(p, home) or _mismo_o_dentro(home, p):
        raise AislamientoError(f"La salida de custodia {p} está bajo MIA_HOME ({home}) o lo "
                               "contiene: el claro descifrado no puede quedar ahí.")
    if p == sal or _mismo_o_dentro(p, sal) or _mismo_o_dentro(sal, p):
        raise AislamientoError("La salida de custodia debe ser una carpeta APARTE de --salida.")
    return p


def verificar_salida_fuera_del_repo(salida: Path, repo_root: Path) -> Path:
    """Las salidas crudas no se escriben bajo el repositorio (custodia, §2.3 y §9.7)."""
    p, repo = _resolver(salida), _resolver(repo_root)
    if p == repo or _mismo_o_dentro(p, repo):
        raise AislamientoError(f"La salida {p} está bajo el repositorio: las salidas crudas "
                               "van fuera (custodia).")
    return p


# ══════════════════════════════════════════════════════════════════════════════
# 2 · Política fija (§9.1)
# ══════════════════════════════════════════════════════════════════════════════
@contextmanager
def politica_fija(llm_mod: Any, politica: str = POLITICA_FIJA):
    """Fija la política SOLO para esta corrida y comprueba que la efectiva es la pedida.

    `run_case_n` vuelve a leer la política del tenant (`model_policy_for`); este runner no lo
    usa, así que lo que gobierna es este contexto y se verifica, no se supone."""
    token = llm_mod.set_model_policy(politica)
    try:
        efectiva = llm_mod.get_model_policy()
        if efectiva != politica:
            raise BancoAbortado(f"Política efectiva {efectiva!r} ≠ {politica!r} (§9.1).")
        yield efectiva
    finally:
        llm_mod.reset_model_policy(token)


# ══════════════════════════════════════════════════════════════════════════════
# 3 · Persistencia atómica e idempotente (§9.5)
# ══════════════════════════════════════════════════════════════════════════════
def escribir_atomico(ruta: Path, objeto: Any) -> None:
    """tmp + `os.replace`: un archivo a medio escribir nunca queda con el nombre final."""
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(objeto, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, ruta)


def leer_json(ruta: Path) -> Optional[dict]:
    try:
        return json.loads(ruta.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def ruta_corrida(salida: Path, version: str, caso_id: str, rep: int) -> Path:
    return salida / version / caso_id / f"rep-{rep:02d}.json"


def ruta_en_curso(salida: Path, version: str, caso_id: str, rep: int) -> Path:
    return salida / version / caso_id / f"rep-{rep:02d}.en_curso.json"


# ══════════════════════════════════════════════════════════════════════════════
# 4 · Clasificación de fallos (§9.5)
# ══════════════════════════════════════════════════════════════════════════════
_RE_LIMITE_USO = re.compile(r"usage limit|rate[ _-]?limit|limit(e)? de uso|cuota agotada|"
                            r"quota|too many requests|429", re.I)
_RE_SESION = re.compile(r"session (has )?expired|sesi[oó]n (ha )?expir|not logged in|"
                        r"please (log ?in|run /login)|login required|unauthorized|401", re.I)


def clasificar_fallo(exc: BaseException, *, llamadas_modelo: int,
                     intentos_fallidos: int = 0) -> str:
    """`limite_de_uso` | `infraestructura` | `producto`.

    · límite de uso del plan → suspensión (§3.4), no se reintenta;
    · infraestructura = el proceso murió ANTES de la primera llamada al modelo
      (`llamadas_modelo == 0`: ni éxito ni intento fallido registrado) o la sesión del CLI expiró;
    · producto = el turno falló DESPUÉS de llamar al modelo: no se reintenta y cuenta.
    El orden importa: un límite de uso nunca se disfraza de fallo de infraestructura.
    """
    texto = f"{type(exc).__name__}: {exc}"
    estado = getattr(exc, "status_code", None)
    if estado == 429 or _RE_LIMITE_USO.search(texto):
        return "limite_de_uso"
    if estado == 401 or _RE_SESION.search(texto):
        return "infraestructura"
    if int(llamadas_modelo) + int(intentos_fallidos) == 0:
        return "infraestructura"
    return "producto"


# ══════════════════════════════════════════════════════════════════════════════
# 5 · Contador de cuota contra el techo, con reserva del juicio (§3.4 · §5.5)
# ══════════════════════════════════════════════════════════════════════════════
def cota_de_fallidos(fallidos: Iterable[Mapping], sin_registro: int = 0) -> tuple[int, bool]:
    """(tokens de la cota superior, ¿calculable?). Cada fallido aporta entrada estimada + cota de
    salida; si UNO no la trae (`None`) o hubo un intento que ni se pudo registrar, NO es
    calculable (P10): jamás se rellena con cero."""
    total, calculable = 0, int(sin_registro or 0) == 0
    for f in fallidos or ():
        cota = f.get("tokens_cota_superior") if isinstance(f, Mapping) else None
        if isinstance(cota, bool) or not isinstance(cota, (int, float)):
            calculable = False
        else:
            total += int(cota)
    return total, calculable


class ContadorCuota:
    """Acumulado de cuota por proveedor contra los techos duros del circuito.

    Del techo se aparta desde el principio la RESERVA del juicio: la producción (rubros
    `produccion` y `aprobacion`) no puede tocarla. Todo se mide con la cota conservadora de los
    intentos fallidos. Idempotente: registrar dos veces la misma clave la reemplaza.
    """
    RUBROS_PRODUCCION = ("produccion", "aprobacion")

    def __init__(self, *, techo_claude: int, techo_codex: int,
                 reserva_juicio_claude: int, reserva_juicio_codex: int) -> None:
        if not (0 <= reserva_juicio_claude < techo_claude and 0 <= reserva_juicio_codex <= techo_codex):
            raise ValueError("Reserva del juicio incompatible con el techo.")
        self.techo_claude, self.techo_codex = int(techo_claude), int(techo_codex)
        self.reserva_claude, self.reserva_codex = int(reserva_juicio_claude), int(reserva_juicio_codex)
        self._filas: dict[str, dict] = {}

    # -- escritura -----------------------------------------------------------------------
    def registrar(self, clave: str, *, rubro: str, claude_conocido: int = 0,
                  claude_fallidos: Iterable[Mapping] = (), codex_conocido: int = 0,
                  codex_fallidos: Iterable[Mapping] = (), sin_registro: int = 0,
                  desconocido: bool = False) -> None:
        cota_cl, ok_cl = cota_de_fallidos(claude_fallidos, sin_registro)
        cota_cx, ok_cx = cota_de_fallidos(codex_fallidos)
        self._filas[str(clave)] = {
            "rubro": rubro, "claude": int(claude_conocido) + cota_cl,
            "codex": int(codex_conocido) + cota_cx,
            "calculable": bool(ok_cl and ok_cx and not desconocido)}

    # -- lectura -------------------------------------------------------------------------
    def _suma(self, proveedor: str, rubros: Iterable[str] | None = None) -> int:
        return sum(f[proveedor] for f in self._filas.values()
                   if rubros is None or f["rubro"] in rubros)

    @property
    def claude_total(self) -> int:
        return self._suma("claude")

    @property
    def codex_total(self) -> int:
        return self._suma("codex")

    @property
    def claude_produccion(self) -> int:
        return self._suma("claude", self.RUBROS_PRODUCCION)

    @property
    def tope_produccion_claude(self) -> int:
        return self.techo_claude - self.reserva_claude

    @property
    def codex_produccion(self) -> int:
        return self._suma("codex", self.RUBROS_PRODUCCION)

    @property
    def cota_calculable(self) -> bool:
        return all(f["calculable"] for f in self._filas.values())

    def advertencias(self) -> list[str]:
        out = []
        if self.codex_produccion > 0 and self.reserva_codex >= self.techo_codex:
            out.append(f"se consumieron {self.codex_produccion} tokens de Codex en PRODUCCIÓN "
                       "(5C) con la totalidad de la cuota Codex reservada para el juicio: el plan "
                       "del Bloque 0 no la preveía")
        return out

    def claves_sin_cota(self) -> list[str]:
        return sorted(k for k, f in self._filas.items() if not f["calculable"])

    @property
    def tope_produccion_codex(self) -> int:
        return self.techo_codex - self.reserva_codex

    def motivo_juicio(self, proveedor: str, cota_tokens: int) -> Optional[str]:
        """Control PREVIO de un intento de juez (Claude o Codex): verifica el techo de AMBOS
        proveedores (si cualquiera ya lo alcanzó, el circuito está suspendido: no se lanza nada) y
        que la cota del intento quepa en el techo del proveedor que llama."""
        for nombre, tot, tec in (("Claude", self.claude_total, self.techo_claude),
                                 ("Codex", self.codex_total, self.techo_codex)):
            if tot >= tec:
                return (f"el acumulado de cuota {nombre} ({tot}) ya alcanzó el techo ({tec}): "
                        "el circuito está suspendido")
        total, techo = ((self.claude_total, self.techo_claude) if proveedor == "claude"
                        else (self.codex_total, self.techo_codex))
        if total + max(0, int(cota_tokens)) > techo:
            return (f"el intento de juez ({proveedor}, cota {int(cota_tokens)}) llevaría el acumulado "
                    f"({total}) por encima del techo ({techo})")
        return None

    def motivo_suspension(self, *, proximo_estimado: int = 0, proximo_codex: int = 0) -> Optional[str]:
        """Texto del motivo si hay que PARAR ya (acumulado en el techo, o la próxima corrida
        invadiría la reserva del juicio); `None` si se puede seguir."""
        if self.claude_total >= self.techo_claude:
            return (f"el acumulado de cuota Claude ({self.claude_total}) alcanzó el techo "
                    f"({self.techo_claude})")
        if self.codex_total >= self.techo_codex:
            return (f"el acumulado de cuota Codex ({self.codex_total}) alcanzó el techo "
                    f"({self.techo_codex})")
        if self.claude_produccion + max(0, int(proximo_estimado)) > self.tope_produccion_claude:
            return (f"la producción ({self.claude_produccion} + {int(proximo_estimado)} de la "
                    f"siguiente corrida) invadiría la reserva del juicio "
                    f"(tope de producción {self.tope_produccion_claude} = techo "
                    f"{self.techo_claude} − reserva {self.reserva_claude})")
        if self.codex_produccion + max(0, int(proximo_codex)) > self.tope_produccion_codex:
            return (f"la producción usa Codex ({self.codex_produccion} + {int(proximo_codex)} de la "
                    f"siguiente corrida) por encima de lo que deja la reserva del juicio "
                    f"(tope de producción Codex {self.tope_produccion_codex} = techo "
                    f"{self.techo_codex} − reserva {self.reserva_codex})")
        return None

    def resumen(self) -> dict:
        return {"claude_total": self.claude_total, "claude_produccion": self.claude_produccion,
                "codex_total": self.codex_total, "codex_produccion": self.codex_produccion,
                "advertencias": self.advertencias(), "techo_claude": self.techo_claude,
                "techo_codex": self.techo_codex, "reserva_juicio_claude": self.reserva_claude,
                "reserva_juicio_codex": self.reserva_codex,
                "tope_produccion_claude": self.tope_produccion_claude,
                "tope_produccion_codex": self.tope_produccion_codex,
                "cota_calculable": self.cota_calculable,
                "claves_sin_cota": self.claves_sin_cota()}


# ══════════════════════════════════════════════════════════════════════════════
# 6 · Plan de repeticiones y tanda piloto (§3.1 · §3.4)
# ══════════════════════════════════════════════════════════════════════════════
@dataclass(frozen=True)
class CasoPlan:
    id: str
    clase: str          # "fuga" | "pequeno" | "voluminoso"
    r: int


def construir_plan(ids_casos: Iterable[str], *, ids_fuga: Iterable[str],
                   ids_voluminosos: Iterable[str], r_fuga: int, r_base: int,
                   r_voluminoso: Optional[int] = None) -> list[CasoPlan]:
    """R por clase. Las constantes llegan por parámetro (viven en protocolo.py)."""
    fuga, volu = set(ids_fuga), set(ids_voluminosos)
    plan = []
    for cid in ids_casos:
        if cid in fuga:
            plan.append(CasoPlan(cid, "fuga", int(r_fuga)))
        elif cid in volu:
            plan.append(CasoPlan(cid, "voluminoso", int(r_base if r_voluminoso is None else r_voluminoso)))
        else:
            plan.append(CasoPlan(cid, "pequeno", int(r_base)))
    return plan


def plan_desde_protocolo(protocolo: Any, ids_casos: Iterable[str],
                         ids_custodiados: Iterable[str] = ()) -> list[CasoPlan]:
    """El plan con las R de `protocolo.repeticiones` (la ÚNICA fuente de R): fuga 10, el resto 5."""
    cust = tuple(ids_custodiados)
    plan = []
    for cid in ids_casos:
        estrato = protocolo.estrato_de(cid, cust)       # un id fuera de la muestra es un error
        clase = ("fuga" if cid in protocolo.CASOS_FUGA_INTERMITENTE
                 else "voluminoso" if estrato in protocolo.ESTRATOS_VOLUMINOSOS else "pequeno")
        plan.append(CasoPlan(cid, clase, int(protocolo.repeticiones(cid, cust))))
    return plan


def proyectar_consumo(consumo_piloto: Mapping[str, int], r_por_caso: Mapping[str, int], *,
                      consumo_aprobaciones: int = 0) -> int:
    """Proyección del circuito de producción: Σ (consumo de la corrida piloto × R del caso) más
    las aprobaciones. SOLO cifras de consumo: la firma no admite ningún dato de calidad."""
    total = int(consumo_aprobaciones)
    for caso, r in r_por_caso.items():
        total += int(consumo_piloto[caso]) * int(r)
    return total


def decidir_r(plan: list[CasoPlan], consumo_piloto: Mapping[str, int], *,
              tope_produccion: int, r_reducido: int, consumo_aprobaciones: int = 0) -> dict:
    """Decisión de R tras la piloto (§3.4), tomada SOLO con el dato de consumo.

    1) proyección con R plena; 2) si supera el tope, R baja al valor reducido SOLO en los
    pequeños sin fuga; 3) si aun así supera, el banco se suspende antes de seguir produciendo.
    Devuelve la decisión con la cifra que la disparó (se escribe tal cual en disco)."""
    plena = {c.id: c.r for c in plan}
    p_plena = proyectar_consumo(consumo_piloto, plena, consumo_aprobaciones=consumo_aprobaciones)
    out = {"tope_produccion": int(tope_produccion), "proyeccion_r_plena": p_plena,
           "consumo_piloto_por_caso": dict(consumo_piloto), "r_por_caso": plena,
           "proyeccion_r_reducida": None, "decision": "r_plena", "cifra_disparadora": None}
    if p_plena <= tope_produccion:
        return out
    reducido = {c.id: (min(c.r, int(r_reducido)) if c.clase == "pequeno" else c.r) for c in plan}
    p_red = proyectar_consumo(consumo_piloto, reducido, consumo_aprobaciones=consumo_aprobaciones)
    out["proyeccion_r_reducida"] = p_red
    out["cifra_disparadora"] = p_plena
    if p_red <= tope_produccion:
        out.update(decision="r_reducida", r_por_caso=reducido)
    else:
        out.update(decision="suspender", cifra_disparadora=p_red)
    return out


def elegir_aprobaciones(completadas: Mapping[str, Iterable[int]], semilla: str) -> list[dict]:
    """Submuestra de aprobaciones (§5.5): UNA repetición COMPLETADA por caso, elegida de forma
    determinista con la semilla (mismo conjunto de entradas → mismas elegidas)."""
    elegidas = []
    for caso in sorted(completadas):
        reps = sorted(int(r) for r in completadas[caso])
        if not reps:
            continue
        mejor = min(reps, key=lambda r: hashlib.sha256(f"{semilla}|{caso}|{r}".encode()).hexdigest())
        elegidas.append({"caso": caso, "rep": mejor})
    return elegidas


# ══════════════════════════════════════════════════════════════════════════════
# 7 · Orquestación idempotente (§9.5)
# ══════════════════════════════════════════════════════════════════════════════
@dataclass
class Deps:
    """Todo lo que toca el mundo (modelo, DB, reloj) entra por aquí, para poder probarlo con
    dobles y para que el runner real solo sea un montaje."""
    producir: Callable[[Any, int], Awaitable[dict]]       # (caso, rep) -> resultado de run_case
    marca: Callable[[], dict]                              # estado del guardián antes de una corrida
    consumo_desde: Callable[[dict], dict]                  # consumo (delta) desde esa marca
    hash_soul: Callable[[], Optional[str]]                 # sha256 del SOUL vivo del despacho
    paradas: tuple = ()                                    # excepciones de parada del guardián
    reloj: Callable[[], float] = time.monotonic


@dataclass
class Contexto:
    salida: Path
    version: str
    sha: str
    semilla: str
    plan: list[CasoPlan]
    casos: Mapping[str, Any]                  # id -> caso (GoldenCase o doble)
    contador: ContadorCuota
    soul_esperado: str
    r_reducido: int
    consumo_aprobaciones: int = 0
    politica: str = POLITICA_FIJA
    cli_version: Optional[str] = None
    max_segundos: Optional[float] = None      # tramo (< 10 min)
    reanudacion_aprobada: Optional[str] = None  # referencia de la aprobación expresa de Pipe
    muestra_completa: bool = True             # ¿están los 17 casos? Si no, nunca certificable
    # Los casos CUSTODIADOS (V1-V4) escriben sus crudos APARTE: el texto en claro que producen no
    # puede quedar bajo el repo ni bajo MIA_HOME (formato de la custodia, §3 último paso; §9.7).
    salida_custodia: Optional[Path] = None
    ids_custodiados: frozenset = frozenset()
    # Versiones cuyo consumo suma contra UN mismo techo (Bloque 7: 0.4 y la re-producción de 0.3.3).
    versiones_contador: tuple = ()
    # I8 (§2.3): cifra `(id, bytes) -> bytes` con la llave de la custodia. Sin él, un caso custodiado
    # NO se corre: nunca se guarda su diagnóstico ni su borrador en claro.
    cifrar: Optional[Callable[[str, bytes], bytes]] = None
    # I10: manifiesto inmutable de la ejecución (SHA real del árbol, SOUL, CLI, política, protocolo).
    manifiesto: Optional[dict] = None

    @property
    def manifiesto_sha256(self) -> Optional[str]:
        return manifiesto_sha256(self.manifiesto) if self.manifiesto is not None else None


def _base_de(ctx: Contexto, caso_id: str) -> Path:
    """Carpeta de salida de un caso. Un caso custodiado SIN carpeta de custodia no se corre."""
    if caso_id in ctx.ids_custodiados:
        if ctx.salida_custodia is None:
            raise BancoAbortado(f"El caso custodiado {caso_id} exige --salida-custodia (fuera del "
                                "repo y de MIA_HOME).")
        return ctx.salida_custodia
    return ctx.salida


def _bases(ctx: Contexto) -> list[Path]:
    return [ctx.salida] + ([ctx.salida_custodia] if ctx.salida_custodia is not None else [])


def _dir_version(ctx: Contexto) -> Path:
    return ctx.salida / ctx.version


def _marcador_suspension(ctx: Contexto) -> Path:
    return _dir_version(ctx) / "SUSPENDIDO.json"


def ruta_intento(base: Path, version: str, caso_id: str, rep: int, n: int) -> Path:
    return base / version / caso_id / f"rep-{rep:02d}.intento-{n}.json"


def _intentos_en_disco(base: Path, version: str, caso_id: str, rep: int) -> list[dict]:
    filas = []
    for ruta in (base / version / caso_id).glob(f"rep-{rep:02d}.intento-*.json"):
        fila = leer_json(ruta)
        if fila and isinstance(fila.get("n"), int):
            filas.append(fila)
    return sorted(filas, key=lambda f: f["n"])


def manifiesto_sha256(m: Mapping) -> str:
    return hashlib.sha256(json.dumps(m, sort_keys=True, ensure_ascii=False,
                                     separators=(",", ":")).encode("utf-8")).hexdigest()


def info_arbol_git(repo_root: Path) -> dict:
    """SHA REAL del árbol que se mide (`git rev-parse HEAD`) y si tiene cambios sin commitear.
    Solo lectura. `--sha` deja de ser una etiqueta libre: debe ser este."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        head = subprocess.run(["git", "-C", str(repo_root), "rev-parse", "HEAD"], capture_output=True,
                              text=True, timeout=30, creationflags=flags, check=False)
        estado = subprocess.run(["git", "-C", str(repo_root), "status", "--porcelain"],
                                capture_output=True, text=True, timeout=60, creationflags=flags,
                                check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        raise BancoAbortado(f"No se pudo leer el SHA real del árbol (git): {exc}") from exc
    sha = (head.stdout or "").strip()
    if head.returncode != 0 or len(sha) < 40:
        raise BancoAbortado("No se pudo leer el SHA real del árbol (git rev-parse HEAD).")
    return {"sha": sha, "arbol_limpio": estado.returncode == 0 and not (estado.stdout or "").strip()}


def verificar_sha_declarado(declarado: str, real: str) -> None:
    d = (declarado or "").strip().lower()
    if len(d) < 7 or not real.lower().startswith(d):
        raise BancoAbortado(f"--sha {declarado!r} no es el SHA real del árbol medido ({real[:12]}…): "
                            "no es una etiqueta libre.")


def construir_manifiesto(*, version: str, sha_arbol: str, arbol_limpio: bool, soul_sha256: str,
                         cli_version: Optional[str], politica: str, protocolo_version: str,
                         protocolo_hash: str, runner_sha256: str) -> dict:
    return {"version": version, "sha_arbol": sha_arbol, "arbol_limpio": bool(arbol_limpio),
            "soul_sha256": soul_sha256, "cli_version": cli_version, "politica": politica,
            "protocolo_version": protocolo_version, "protocolo_hash": protocolo_hash,
            "runner_sha256": runner_sha256}


def _exigir_mismo_manifiesto(ctx: Contexto, registro: Mapping, ruta: Path) -> None:
    if registro.get("manifiesto_sha256") != ctx.manifiesto_sha256:
        raise BancoAbortado(
            f"El registro previo {ruta} se hizo con otro manifiesto de ejecución "
            f"({registro.get('manifiesto_sha256')!r} ≠ {ctx.manifiesto_sha256!r}): no se reutiliza "
            "(SHA del árbol, SOUL, CLI, política o protocolo cambiaron).")


def asegurar_manifiesto(ctx: Contexto) -> None:
    """Crea (una sola vez, exclusivo) `MANIFIESTO.json` de la versión y rechaza una ejecución cuyo
    manifiesto difiera del registrado o registros previos hechos con otro manifiesto."""
    if ctx.manifiesto is None:
        return
    ruta = _dir_version(ctx) / "MANIFIESTO.json"
    if ruta.exists():
        previo = leer_json(ruta)
        if previo != json.loads(json.dumps(ctx.manifiesto)):
            campos = sorted(k for k in set(previo or {}) | set(ctx.manifiesto)
                            if (previo or {}).get(k) != ctx.manifiesto.get(k))
            raise BancoAbortado("El manifiesto de esta ejecución no coincide con el registrado para la "
                                f"versión (difieren: {', '.join(campos) or 'formato'}): se rechaza.")
    else:
        ruta.parent.mkdir(parents=True, exist_ok=True)
        with open(ruta, "x", encoding="utf-8") as f:            # exclusivo: nunca se reescribe
            f.write(json.dumps(ctx.manifiesto, ensure_ascii=False, indent=2, sort_keys=True))
    for base in _bases(ctx):
        for r in sorted((base / ctx.version).glob("*/rep-??.json")):
            fila = leer_json(r) or {}
            if fila.get("manifiesto_sha256") != ctx.manifiesto_sha256:
                _exigir_mismo_manifiesto(ctx, fila, r)


def escribir_bytes_atomico(ruta: Path, datos: bytes) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    tmp = ruta.with_name(ruta.name + f".{os.getpid()}.tmp")
    tmp.write_bytes(datos)
    os.replace(tmp, ruta)


def cifrar_resultado_custodiado(ctx: Contexto, caso_id: str, rep: int, resultado: Any,
                                base: Path) -> dict:
    """Cifra el resultado crudo (diagnóstico, borrador, material) de un caso custodiado con la
    llave de la custodia y deja en el registro SOLO la ficha: archivo cifrado + hashes."""
    if ctx.cifrar is None:
        raise BancoAbortado(f"El caso custodiado {caso_id} no puede persistir su salida en claro "
                            "(§2.3): falta el cifrador de la custodia.")
    claro = json.dumps(resultado, ensure_ascii=False, default=str, sort_keys=True).encode("utf-8")
    id_reg = f"{ctx.version}/{caso_id}/{rep}"
    cif = ctx.cifrar(id_reg, claro)
    archivo = f"rep-{rep:02d}.resultado.enc"
    escribir_bytes_atomico(base / ctx.version / caso_id / archivo, cif)
    return {"cifrado": True, "archivo": archivo, "id_registro": id_reg,
            "algoritmo": "AES-256-GCM (llave de la custodia)", "bytes_claro": len(claro),
            "sha256_claro": hashlib.sha256(claro).hexdigest(),
            "sha256_cifrado": hashlib.sha256(cif).hexdigest()}


def _recuperar_huerfanas(ctx: Contexto) -> None:
    """Convierte cada `.en_curso` que dejó un proceso muerto en un INTENTO duradero: consumo
    DESCONOCIDO, sin cota (§5.5) y clase infraestructura (cuenta para el único reintento).
    Antes el marcador solo vivía hasta el siguiente arranque: tras relanzar se borraba y el banco
    volvía a poder cerrar «terminado» con una corrida de consumo desconocido (P10)."""
    for base in _bases(ctx):
        for ruta in sorted((base / ctx.version).glob("*/rep-*.en_curso.json")):
            marca = leer_json(ruta) or {}
            caso_id, rep, n = marca.get("caso_id"), marca.get("rep"), marca.get("intento")
            if isinstance(rep, int) and isinstance(n, int) and caso_id:
                destino = ruta_intento(base, ctx.version, caso_id, rep, n)
                if not destino.exists():
                    escribir_atomico(destino, {
                        "n": n, "caso_id": caso_id, "rep": rep, "estado": "fallo_infraestructura",
                        "clase": "infraestructura", "huerfano": True,
                        "error": "el proceso murió con la corrida a medias (consumo desconocido)",
                        "consumo": {"desconocido": True, "claude_conocido": 0, "fallidos": [],
                                    "sin_registro": 0, "llamadas": 0}})
            try:
                ruta.unlink()
            except OSError:
                pass


def cargar_contador_desde_disco(ctx: Contexto, recuperar: bool = True) -> None:
    """Reconstruye el contador desde los crudos persistidos (idempotente al relanzar). La fuente
    son los INTENTOS (uno por archivo, duraderos), con clave única `caso/rep/n`. `recuperar=False`
    (lo usa el ledger del juicio) NO convierte marcadores `.en_curso` en intentos huérfanos: la
    producción puede estar viva y su marcador es una corrida en vuelo, no una muerte."""
    if recuperar:
        _recuperar_huerfanas(ctx)
    for version in _versiones(ctx):
        for base in _bases(ctx):
            for patron in ("*/rep-*.intento-*.json", "*/rep-??.json"):
                for ruta in sorted((base / version).glob(patron)):
                    fila = leer_json(ruta)
                    if not fila:
                        continue
                    intentos = fila.get("intentos") if "intentos" in fila else [fila]
                    for it in intentos or []:
                        # la clave lleva la versión solo cuando no es la actual (compatibilidad)
                        pref = "" if version == ctx.version else f"{version}/"
                        registrar_consumo(
                            ctx.contador,
                            f"{pref}{it.get('caso_id') or fila.get('caso_id')}/"
                            f"{it.get('rep') or fila.get('rep')}/{it.get('n')}", "produccion",
                            it.get("consumo") or {})
    _cargar_aprobaciones_y_juicio(ctx)


def registrar_consumo(contador: ContadorCuota, clave: str, rubro: str, consumo: Mapping) -> None:
    """UNA sola puerta para pasar un consumo medido (Claude y Codex por separado) al contador."""
    contador.registrar(
        clave, rubro=rubro,
        claude_conocido=int(consumo.get("claude_conocido") or 0),
        claude_fallidos=consumo.get("fallidos") or (),
        codex_conocido=int(consumo.get("codex_conocido") or 0),
        codex_fallidos=consumo.get("codex_fallidos") or (),
        sin_registro=int(consumo.get("sin_registro") or 0),
        desconocido=bool(consumo.get("desconocido")))


def _resumen_consumo_codex(consumo: Mapping) -> int:
    cota, _ = cota_de_fallidos(consumo.get("codex_fallidos") or ())
    return int(consumo.get("codex_conocido") or 0) + cota


def _resumen_consumo(consumo: Mapping) -> int:
    cota, _ = cota_de_fallidos(consumo.get("fallidos") or (), consumo.get("sin_registro") or 0)
    return int(consumo.get("claude_conocido") or 0) + cota


def _escribir_suspension(ctx: Contexto, motivo: str, extra: Mapping | None = None) -> dict:
    ruta = _marcador_suspension(ctx)
    previo = leer_json(ruta) or {}
    marcador = {
        "estado": TEXTO_INCOMPLETO, "motivo": motivo, "version": ctx.version, "sha": ctx.sha,
        "consumo": ctx.contador.resumen(),
        "regla": "solo se reanuda con una nueva aprobación expresa de Pipe (§3.4); un resultado "
                 "incompleto nunca se certifica: ni para la línea base ni para aprobar 0.4",
        "reanudaciones_previas": previo.get("reanudaciones_previas", []) + (
            [previo["motivo"]] if previo.get("motivo") else [])}
    marcador.update(extra or {})
    escribir_atomico(ruta, marcador)
    return marcador


async def _ejecutar_una(ctx: Contexto, deps: Deps, caso_plan: CasoPlan, rep: int) -> dict:
    """Una (caso, repetición). Devuelve el registro persistido (o el ya existente).

    Cada INTENTO se escribe en su propio archivo (`rep-NN.intento-K.json`) apenas termina, y el
    contador usa la clave `caso/rep/K`: un relanzamiento (por muerte del proceso o por reanudar
    tras un límite de uso) continúa en el intento K+1 sin perder el consumo del anterior ni
    reabrir el tope de dos intentos de infraestructura (§9.5)."""
    base = _base_de(ctx, caso_plan.id)
    ruta = ruta_corrida(base, ctx.version, caso_plan.id, rep)
    previo = leer_json(ruta)
    if previo and previo.get("estado") in ESTADOS_TERMINALES:
        _exigir_mismo_manifiesto(ctx, previo, ruta)
        return previo                                         # idempotencia: ya está hecha
    caso = ctx.casos[caso_plan.id]
    if getattr(caso, "synthetic", False) is not True:
        raise BancoAbortado(f"El caso {caso_plan.id} no es sintético (§9.3).")
    if caso_plan.id in ctx.ids_custodiados and ctx.cifrar is None:
        raise BancoAbortado(f"El caso custodiado {caso_plan.id} exige el cifrador de la custodia "
                            "(§2.3): no se corre para no guardar su salida en claro.")
    hash_previo = deps.hash_soul()
    if hash_previo != ctx.soul_esperado:
        raise BancoAbortado(f"El SOUL del despacho cambió (esperado {ctx.soul_esperado}, "
                            f"ahora {hash_previo}): se detiene antes de la corrida (§9.3).")
    intentos = _intentos_en_disco(base, ctx.version, caso_plan.id, rep)
    n_infra = sum(1 for i in intentos if i.get("clase") == "infraestructura")
    n = max([i["n"] for i in intentos], default=0)
    final: Optional[str] = "fallo_infraestructura" if n_infra >= MAX_INTENTOS_INFRA else None
    resultado: Optional[dict] = None
    while final is None:
        n += 1
        escribir_atomico(ruta_en_curso(base, ctx.version, caso_plan.id, rep),
                         {"caso_id": caso_plan.id, "rep": rep, "intento": n})
        marca = deps.marca()
        t0 = deps.reloj()
        error: Optional[BaseException] = None
        parada: Optional[BaseException] = None
        try:
            resultado = await deps.producir(caso, rep)
        except deps.paradas as exc:                           # parada del guardián de gasto
            error, parada = exc, exc
        except Exception as exc:  # noqa: BLE001 — se clasifica, no se traga
            error = exc
        consumo = deps.consumo_desde(marca)
        intento = {"n": n, "caso_id": caso_plan.id, "rep": rep,
                   "segundos": round(deps.reloj() - t0, 3), "consumo": consumo}
        registrar_consumo(ctx.contador, f"{caso_plan.id}/{rep}/{n}", "produccion", consumo)
        if error is None:
            intento["estado"] = "completo"
            final = "completo"
        else:
            tipo = ("limite_de_uso" if parada is not None else clasificar_fallo(
                error, llamadas_modelo=int(consumo.get("llamadas") or 0),
                intentos_fallidos=len(consumo.get("fallidos") or ())))
            intento.update(estado=f"fallo_{tipo}", clase=tipo,
                           error=f"{type(error).__name__}: {error}")
            resultado = None
            if tipo == "limite_de_uso":
                final = "limite_de_uso"
            elif tipo == "producto":
                final = "fallo_producto"                      # no se reintenta; cuenta (§9.5)
            else:                                             # infraestructura: UN reintento
                n_infra += 1
                if n_infra >= MAX_INTENTOS_INFRA:
                    final = "fallo_infraestructura"
        escribir_atomico(ruta_intento(base, ctx.version, caso_plan.id, rep, n), intento)
        try:                                                  # solo DESPUÉS de dejarlo duradero
            ruta_en_curso(base, ctx.version, caso_plan.id, rep).unlink()
        except OSError:
            pass
        intentos.append(intento)
    registro = {
        "version": ctx.version, "sha": ctx.sha, "caso_id": caso_plan.id, "clase": caso_plan.clase,
        "rep": rep, "estado": final, "politica": ctx.politica, "semilla": ctx.semilla,
        "cli_version": ctx.cli_version, "soul_sha256_previo": hash_previo, "intentos": intentos,
        "manifiesto_sha256": ctx.manifiesto_sha256,
        "resultado": (cifrar_resultado_custodiado(ctx, caso_plan.id, rep, resultado, base)
                      if (caso_plan.id in ctx.ids_custodiados and resultado is not None)
                      else resultado)}
    if final != "limite_de_uso":            # un límite de uso no es un resultado: solo queda el intento
        escribir_atomico(ruta, registro)
    return registro


async def ejecutar_banco(ctx: Contexto, deps: Deps) -> dict:
    """Corre el banco hasta terminar, hasta el techo (suspensión) o hasta agotar el tramo."""
    asegurar_manifiesto(ctx)
    cargar_contador_desde_disco(ctx)
    marcador = leer_json(_marcador_suspension(ctx))
    if marcador and not ctx.reanudacion_aprobada:
        return {"estado": TEXTO_INCOMPLETO, "motivo": marcador.get("motivo"),
                "salida": EXIT_SUSPENDIDO, "marcador": marcador}
    if marcador and ctx.reanudacion_aprobada:
        marcador = dict(marcador, reanudado_con=ctx.reanudacion_aprobada)
        escribir_atomico(_dir_version(ctx) / "SUSPENDIDO.reanudado.json", marcador)
        _marcador_suspension(ctx).unlink()
    t_ini = deps.reloj()
    plan = {c.id: c for c in ctx.plan}
    consumos_piloto: dict[str, int] = {}
    codex_piloto: dict[str, int] = {}

    def agotado() -> bool:
        return ctx.max_segundos is not None and (deps.reloj() - t_ini) >= ctx.max_segundos

    def suspender(motivo: str) -> dict:
        m = _escribir_suspension(ctx, motivo)
        return {"estado": TEXTO_INCOMPLETO, "motivo": motivo, "salida": EXIT_SUSPENDIDO, "marcador": m}

    async def paso(caso_plan: CasoPlan, rep: int, estimado: int, estimado_codex: int = 0) -> Optional[dict]:
        """Corre una repetición; devuelve un dict de salida si hay que parar, o None."""
        if (leer_json(ruta_corrida(_base_de(ctx, caso_plan.id), ctx.version, caso_plan.id, rep))
                or {}).get("estado") in ESTADOS_TERMINALES:
            return None
        motivo = ctx.contador.motivo_suspension(proximo_estimado=estimado,
                                                proximo_codex=estimado_codex)
        if motivo:
            return suspender(motivo)
        if agotado():
            return {"estado": "tramo_agotado", "salida": EXIT_TRAMO}
        reg = await _ejecutar_una(ctx, deps, caso_plan, rep)
        if reg["estado"] == "limite_de_uso":
            return suspender("el plan devolvió límites de uso que impiden terminar")
        motivo = ctx.contador.motivo_suspension()
        if motivo:
            return suspender(motivo)
        return None

    # 1 · tanda piloto: repetición 1 de cada caso (cuenta como repetición 1)
    for c in ctx.plan:
        salida = await paso(c, 1, 0)
        if salida:
            return salida
    for c in ctx.plan:
        reg = leer_json(ruta_corrida(_base_de(ctx, c.id), ctx.version, c.id, 1)) or {}
        consumos_piloto[c.id] = sum(_resumen_consumo(i.get("consumo") or {})
                                    for i in reg.get("intentos", []))
        codex_piloto[c.id] = sum(_resumen_consumo_codex(i.get("consumo") or {})
                                 for i in reg.get("intentos", []))
    # 2 · decisión de R, solo con consumo (se escribe una vez, con la cifra que la disparó)
    ruta_dec = _dir_version(ctx) / "decision_r.json"
    decision = leer_json(ruta_dec)
    if decision is None:
        decision = decidir_r(ctx.plan, consumos_piloto,
                             tope_produccion=ctx.contador.tope_produccion_claude,
                             r_reducido=ctx.r_reducido,
                             consumo_aprobaciones=ctx.consumo_aprobaciones)
        escribir_atomico(ruta_dec, decision)
    if decision["decision"] == "suspender":
        return suspender("la proyección del circuito supera el tope aun con R reducida: "
                         f"{decision['cifra_disparadora']} > {decision['tope_produccion']}")
    r_por_caso = decision["r_por_caso"]
    # 3 · resto de repeticiones, en orden de repetición (reparte el riesgo de cortar a mitad)
    for rep in range(2, max(r_por_caso.values()) + 1):
        for c in ctx.plan:
            if rep > int(r_por_caso[c.id]):
                continue
            salida = await paso(c, rep, consumos_piloto.get(c.id, 0), codex_piloto.get(c.id, 0))
            if salida:
                return salida
    # 4 · terminado: submuestra de aprobaciones + estado
    completadas: dict[str, list[int]] = {}
    for c in ctx.plan:
        for rep in range(1, int(r_por_caso[c.id]) + 1):
            if (leer_json(ruta_corrida(_base_de(ctx, c.id), ctx.version, c.id, rep)) or {}).get(
                    "estado") == "completo":
                completadas.setdefault(c.id, []).append(rep)
    escribir_atomico(_dir_version(ctx) / "aprobaciones_plan.json",
                     {"semilla": ctx.semilla, "elegidas": elegir_aprobaciones(completadas, ctx.semilla),
                      "nota": "cada aprobación corre APARTE en su propio despacho y MIA_HOME (§5.5)"})
    motivos = ([] if ctx.contador.cota_calculable else ["techo sin cota calculable (P10)"]) + (
        [] if ctx.muestra_completa else ["muestra incompleta: faltan casos del protocolo"])
    estado = {"estado": "terminado" if not motivos else "no certificable", "motivos": motivos,
              "consumo": ctx.contador.resumen(), "decision_r": decision["decision"],
              "version": ctx.version, "sha": ctx.sha}
    escribir_atomico(_dir_version(ctx) / "estado_banco.json", estado)
    return {"estado": estado["estado"], "salida": EXIT_OK, "detalle": estado}


# ══════════════════════════════════════════════════════════════════════════════
# 7b · Aprobaciones (§5.5) y ledger del juicio (§3.4)
# ══════════════════════════════════════════════════════════════════════════════
RUBROS_JUICIO = ("juicio", "adjudicacion", "validacion", "estabilidad")
_RE_ID_LEDGER = re.compile(r"^[A-Za-z0-9._-]{1,120}$")


def _versiones(ctx: Contexto) -> tuple:
    """Versiones cuyo consumo suma contra el techo (en el Bloque 7: 0.4 y la re-producción de
    0.3.3 comparten UN techo por bloque)."""
    return tuple(ctx.versiones_contador) or (ctx.version,)


def ruta_ledger(salida: Path, version: str, id_: str) -> Path:
    return salida / version / "ledger" / f"{id_}.json"


def registrar_consumo_externo(salida: Path, version: str, *, id_: str, etapa: str,
                              claude_conocido: int = 0, claude_fallidos: Iterable[Mapping] = (),
                              codex_conocido: int = 0, codex_fallidos: Iterable[Mapping] = (),
                              sin_registro: int = 0, desconocido: bool = False,
                              nota: str = "") -> Path:
    """Puerta del LEDGER para lo que el runner no mide por sí mismo: el consumo del JUICIO, la
    adjudicación, la validación de jueces y la estabilidad (Claude y Codex por separado).

    Cada llamada escribe UN archivo atómico y duradero (`<salida>/<versión>/ledger/<id>.json`);
    el contador lo recoge al arrancar (`cargar_contador_desde_disco`) bajo el rubro `juicio`, que
    cuenta para el techo del circuito pero NO para el tope de producción (§3.4). Idempotente por
    `id_`. Un consumo desconocido o sin cota deja el techo «no certificable» (P10)."""
    if etapa not in RUBROS_JUICIO:
        raise ValueError(f"etapa {etapa!r} no válida; use una de {RUBROS_JUICIO}")
    if not _RE_ID_LEDGER.match(id_):
        raise ValueError("id_ del ledger: solo letras, dígitos, punto, guion y guion bajo")
    ruta = ruta_ledger(Path(salida), version, id_)
    escribir_atomico(ruta, {
        "id": id_, "version": version, "etapa": etapa, "nota": nota,
        "consumo": {"claude_conocido": int(claude_conocido), "fallidos": list(claude_fallidos),
                    "codex_conocido": int(codex_conocido), "codex_fallidos": list(codex_fallidos),
                    "sin_registro": int(sin_registro), "desconocido": bool(desconocido)}})
    return ruta


def _cargar_aprobaciones_y_juicio(ctx: Contexto) -> None:
    for version in _versiones(ctx):
        for base in _bases(ctx):
            for ruta in sorted((base / version).glob("*/aprob.intento-*.json")):
                it = leer_json(ruta)
                if not it:
                    continue
                clave = f"{version}/{it.get('caso_id')}/{it.get('rep')}/aprob{it.get('n')}"
                # el turno reproducido y la aprobación se contabilizan (los dos gastan cuota); la
                # cifra de §5.5/§6.3 para la aprobación es SOLO `consumo_aprobacion`
                registrar_consumo(ctx.contador, clave + "/turno", "aprobacion",
                                  it.get("consumo_turno") or {"desconocido": bool(it.get("huerfano"))})
                registrar_consumo(ctx.contador, clave + "/aprobar", "aprobacion",
                                  it.get("consumo_aprobacion") or {})
        for ruta in sorted((ctx.salida / version / "ledger").glob("*.json")):
            fila = leer_json(ruta)
            if fila and fila.get("estado") == "en_curso":
                campo = "claude_conocido" if fila.get("proveedor") == "claude" else "codex_conocido"
                registrar_consumo(ctx.contador, f"ledger/{version}/{fila.get('id')}", "juicio",
                                  {campo: int(fila.get("cota_reservada") or 0), "desconocido": True})
            elif fila:
                registrar_consumo(ctx.contador, f"ledger/{version}/{fila.get('id')}", "juicio",
                                  fila.get("consumo") or {})


class PresupuestoAgotado(RuntimeError):
    """El intento de juez no cabe en el techo: no se lanza."""


class LedgerJuicio:
    """API del contador COMPARTIDO para el agente de juicio (Opus y Codex).

        ledger = LedgerJuicio(salida, version, nuevo_contador=lambda: contador_desde_protocolo(P, 0),
                              salida_custodia=..., versiones=("0.4",))
        ledger.iniciar(id_="j-opus-p1-0007", etapa="juicio", proveedor="claude", cota_tokens=60_000)
        try:
            ...lanzar al juez...
            ledger.cerrar("j-opus-p1-0007", claude_conocido=51_200)
        except TimeoutError:
            ledger.cerrar("j-opus-p1-0007", timeout=True)      # consumo desconocido: no certificable

    `iniciar` (1) relee del disco TODO lo gastado por producción, aprobaciones y juicio, (2) rechaza
    (`PresupuestoAgotado`) si la cota del intento no cabe en el techo del proveedor, y (3) deja el
    intento escrito de forma atómica y duradera como `en_curso` ANTES de que el juez se lance: un
    proceso que muere o un timeout dejan un intento de consumo DESCONOCIDO (cuenta su cota y el techo
    queda no certificable), nunca un hueco. `cerrar` sustituye la reserva por lo medido."""

    def __init__(self, salida: Path, version: str, *, nuevo_contador: Callable[[], ContadorCuota],
                 salida_custodia: Optional[Path] = None, versiones: tuple = ()) -> None:
        self.salida, self.version = Path(salida), version
        self.nuevo_contador = nuevo_contador
        self.salida_custodia = Path(salida_custodia) if salida_custodia else None
        self.versiones = tuple(versiones)

    def contador(self) -> ContadorCuota:
        c = self.nuevo_contador()
        ctx = SimpleNamespace(salida=self.salida, salida_custodia=self.salida_custodia,
                              version=self.version, versiones_contador=self.versiones, contador=c)
        cargar_contador_desde_disco(ctx, recuperar=False)
        return c

    def iniciar(self, *, id_: str, etapa: str, proveedor: str, cota_tokens: Optional[int]) -> Path:
        if proveedor not in ("claude", "codex"):
            raise ValueError("proveedor: 'claude' o 'codex'")
        if etapa not in RUBROS_JUICIO or not _RE_ID_LEDGER.match(id_):
            raise ValueError("etapa o id_ no válidos")
        if not isinstance(cota_tokens, int) or isinstance(cota_tokens, bool) or cota_tokens <= 0:
            raise ValueError("cota_tokens es obligatoria: el intento se reserva ANTES de lanzarlo")
        if ruta_ledger(self.salida, self.version, id_).exists():
            raise ValueError(f"el id_ {id_!r} ya existe en el ledger")
        motivo = self.contador().motivo_juicio(proveedor, cota_tokens)
        if motivo:
            raise PresupuestoAgotado(motivo)
        ruta = ruta_ledger(self.salida, self.version, id_)
        escribir_atomico(ruta, {"id": id_, "version": self.version, "etapa": etapa,
                                "proveedor": proveedor, "estado": "en_curso",
                                "cota_reservada": cota_tokens, "consumo": {}})
        return ruta

    def cerrar(self, id_: str, *, claude_conocido: int = 0, codex_conocido: int = 0,
               claude_fallidos: Iterable[Mapping] = (), codex_fallidos: Iterable[Mapping] = (),
               sin_registro: int = 0, timeout: bool = False, error: str = "") -> Path:
        ruta = ruta_ledger(self.salida, self.version, id_)
        fila = leer_json(ruta)
        if not fila or fila.get("estado") != "en_curso":
            raise ValueError(f"no hay un intento en curso {id_!r}")
        reservada = int(fila["cota_reservada"])
        campo = "claude_conocido" if fila["proveedor"] == "claude" else "codex_conocido"
        consumo = {"claude_conocido": int(claude_conocido), "codex_conocido": int(codex_conocido),
                   "fallidos": list(claude_fallidos), "codex_fallidos": list(codex_fallidos),
                   "sin_registro": int(sin_registro), "desconocido": bool(timeout)}
        if timeout:                    # no se sabe cuánto gastó: se cuenta su cota y no se certifica
            consumo[campo] = max(consumo[campo], reservada)
        escribir_atomico(ruta, dict(fila, estado="cerrado", consumo=consumo, error=error,
                                    timeout=bool(timeout)))
        return ruta


def contador_desde_protocolo(protocolo: Any, bloque: int) -> ContadorCuota:
    k = constantes_de_protocolo(protocolo, bloque)
    return ContadorCuota(techo_claude=k["techo_claude"], techo_codex=k["techo_codex"],
                         reserva_juicio_claude=k["reserva_claude"],
                         reserva_juicio_codex=k["reserva_codex"])


@dataclass
class DepsAprobacion:
    """Lo que toca el mundo en una aprobación: su PROPIO despacho y su propio `MIA_HOME` (la
    aprobación escribe en el SOUL: no puede hacerlo en el de la producción)."""
    abrir_despacho: Callable[[Any], Awaitable[Any]]                    # (caso) -> handle
    producir_hasta_revision: Callable[[Any, Any], Awaitable[dict]]     # (handle, caso) -> resultado
    aprobar: Callable[[Any, dict], Awaitable[dict]]                    # (handle, resultado) -> {estado,...}
    cerrar_despacho: Callable[[Any], Awaitable[None]]
    marca: Callable[[], dict]
    consumo_desde: Callable[[dict], dict]
    paradas: tuple = ()
    reloj: Callable[[], float] = time.monotonic


def ruta_aprobacion(base: Path, version: str, caso_id: str) -> Path:
    return base / version / caso_id / "aprobacion.json"


def ruta_intento_aprob(base: Path, version: str, caso_id: str, n: int) -> Path:
    return base / version / caso_id / f"aprob.intento-{n}.json"


def ruta_en_curso_aprob(base: Path, version: str, caso_id: str) -> Path:
    return base / version / caso_id / "aprob.en_curso.json"


async def _ejecutar_una_aprobacion(ctx: Contexto, d: DepsAprobacion, caso_id: str, rep: int) -> dict:
    """Aprobación sin cambios de UN caso: turno hasta la revisión en un despacho propio, aprobar,
    esperar los trabajos de aprendizaje. Mismos intentos duraderos que la producción."""
    base = _base_de(ctx, caso_id)
    ruta = ruta_aprobacion(base, ctx.version, caso_id)
    previo = leer_json(ruta)
    if previo and previo.get("estado") in ESTADOS_APROBACION_TERMINALES:
        return previo
    caso = ctx.casos[caso_id]
    if getattr(caso, "synthetic", False) is not True:
        raise BancoAbortado(f"El caso {caso_id} no es sintético (§9.3).")
    intentos = []
    for f in sorted((base / ctx.version / caso_id).glob("aprob.intento-*.json")):
        fila = leer_json(f)
        if fila and isinstance(fila.get("n"), int):
            intentos.append(fila)
    intentos.sort(key=lambda i: i["n"])
    n_infra = sum(1 for i in intentos if i.get("clase") == "infraestructura")
    n = max([i["n"] for i in intentos], default=0)
    final: Optional[str] = "fallo_infraestructura" if n_infra >= MAX_INTENTOS_INFRA else None
    detalle: Optional[dict] = None
    while final is None:
        n += 1
        escribir_atomico(ruta_en_curso_aprob(base, ctx.version, caso_id),
                         {"caso_id": caso_id, "rep": rep, "intento": n})
        t0 = d.reloj()
        handle: Any = None
        m_turno = m_aprob = None
        c_turno: dict = {}
        c_aprob: dict = {}
        error: Optional[BaseException] = None
        parada: Optional[BaseException] = None
        detalle = None
        try:
            handle = await d.abrir_despacho(caso)
            m_turno = d.marca()
            resultado = await d.producir_hasta_revision(handle, caso)
            c_turno = d.consumo_desde(m_turno)
            m_aprob = d.marca()
            detalle = await d.aprobar(handle, resultado)
            c_aprob = d.consumo_desde(m_aprob)
        except d.paradas as exc:
            error, parada = exc, exc
        except Exception as exc:  # noqa: BLE001
            error = exc
        finally:
            try:
                if handle is not None:
                    await d.cerrar_despacho(handle)
            except Exception as exc:  # noqa: BLE001 — limpiar no tumba la medición
                print(f"AVISO: no se pudo cerrar el despacho de la aprobación {caso_id}: {exc}",
                      file=sys.stderr)
        if error is not None:                     # lo consumido hasta el fallo se mide igual
            if m_aprob is not None:
                c_aprob = d.consumo_desde(m_aprob)
            elif m_turno is not None:
                c_turno = d.consumo_desde(m_turno)
        intento = {"n": n, "caso_id": caso_id, "rep": rep, "segundos": round(d.reloj() - t0, 3),
                   "consumo_turno": c_turno, "consumo_aprobacion": c_aprob}
        if error is None:
            ok = bool((detalle or {}).get("aprobada", True))
            intento["estado"] = "completo" if ok else "no_aprobable"
            final = intento["estado"]
        else:
            tipo = ("limite_de_uso" if parada is not None else clasificar_fallo(
                error, llamadas_modelo=int(c_turno.get("llamadas") or 0) + int(
                    c_aprob.get("llamadas") or 0),
                intentos_fallidos=len(c_turno.get("fallidos") or ()) + len(c_aprob.get("fallidos") or ())))
            intento.update(estado=f"fallo_{tipo}", clase=tipo, error=f"{type(error).__name__}: {error}")
            if tipo == "limite_de_uso":
                final = "limite_de_uso"
            elif tipo == "producto":
                final = "fallo_producto"
            else:
                n_infra += 1
                if n_infra >= MAX_INTENTOS_INFRA:
                    final = "fallo_infraestructura"
        clave = f"{ctx.version}/{caso_id}/{rep}/aprob{n}"
        registrar_consumo(ctx.contador, clave + "/turno", "aprobacion", c_turno)
        registrar_consumo(ctx.contador, clave + "/aprobar", "aprobacion", c_aprob)
        escribir_atomico(ruta_intento_aprob(base, ctx.version, caso_id, n), intento)
        try:
            ruta_en_curso_aprob(base, ctx.version, caso_id).unlink()
        except OSError:
            pass
        intentos.append(intento)
    ok_final = [i for i in intentos if i.get("estado") in ("completo", "no_aprobable")]
    registro = {
        "version": ctx.version, "caso_id": caso_id, "rep": rep, "estado": final, "intentos": intentos,
        "aprobacion": detalle if final in ("completo", "no_aprobable") else None,
        # la cifra de §5.5/§6.3 para la aprobación: SOLO el paso de aprobar y sus trabajos
        "consumo_aprobacion": (ok_final[-1]["consumo_aprobacion"] if ok_final else None),
        "consumo_turno_reproducido": (ok_final[-1]["consumo_turno"] if ok_final else None)}
    if final != "limite_de_uso":
        escribir_atomico(ruta, registro)
    return registro


ESTADOS_APROBACION_TERMINALES = ("completo", "no_aprobable", "fallo_producto", "fallo_infraestructura")


async def ejecutar_aprobaciones(ctx: Contexto, d: DepsAprobacion) -> dict:
    """Fase de aprobaciones (§5.5): UNA por caso, la repetición que eligió `elegir_aprobaciones`,
    cada una en su propio despacho y `MIA_HOME`. Se detiene por techo, por la reserva del juicio
    o por un límite de uso igual que la producción; relanzable e idempotente."""
    asegurar_manifiesto(ctx)
    _recuperar_huerfanas_aprob(ctx)
    cargar_contador_desde_disco(ctx)
    marcador = leer_json(_marcador_suspension(ctx))
    if marcador and not ctx.reanudacion_aprobada:
        return {"estado": TEXTO_INCOMPLETO, "motivo": marcador.get("motivo"),
                "salida": EXIT_SUSPENDIDO, "marcador": marcador}
    if marcador and ctx.reanudacion_aprobada:
        escribir_atomico(_dir_version(ctx) / "SUSPENDIDO.reanudado.json",
                         dict(marcador, reanudado_con=ctx.reanudacion_aprobada))
        _marcador_suspension(ctx).unlink()
    plan = leer_json(_dir_version(ctx) / "aprobaciones_plan.json")
    if not plan or not plan.get("elegidas"):
        raise BancoAbortado("No hay aprobaciones_plan.json: termine antes la producción.")
    elegidas = plan["elegidas"]
    por_aprobacion = max(1, int(ctx.consumo_aprobaciones) // max(1, len(elegidas)))
    t_ini = d.reloj()
    for e in elegidas:
        caso_id, rep = e["caso"], int(e["rep"])
        if (leer_json(ruta_aprobacion(_base_de(ctx, caso_id), ctx.version, caso_id)) or {}).get(
                "estado") in ESTADOS_APROBACION_TERMINALES:
            continue
        motivo = ctx.contador.motivo_suspension(proximo_estimado=por_aprobacion)
        if motivo:
            m = _escribir_suspension(ctx, motivo)
            return {"estado": TEXTO_INCOMPLETO, "motivo": motivo, "salida": EXIT_SUSPENDIDO, "marcador": m}
        if ctx.max_segundos is not None and (d.reloj() - t_ini) >= ctx.max_segundos:
            return {"estado": "tramo_agotado", "salida": EXIT_TRAMO}
        reg = await _ejecutar_una_aprobacion(ctx, d, caso_id, rep)
        motivo = ("el plan devolvió límites de uso que impiden terminar"
                  if reg["estado"] == "limite_de_uso" else ctx.contador.motivo_suspension())
        if motivo:
            m = _escribir_suspension(ctx, motivo)
            return {"estado": TEXTO_INCOMPLETO, "motivo": motivo, "salida": EXIT_SUSPENDIDO, "marcador": m}
    estados = {e["caso"]: (leer_json(ruta_aprobacion(_base_de(ctx, e["caso"]), ctx.version, e["caso"]))
                           or {}).get("estado") for e in elegidas}
    motivos = ([] if ctx.contador.cota_calculable else ["techo sin cota calculable (P10)"]) + (
        [] if ctx.muestra_completa else ["muestra incompleta"]) + [
        f"aprobación de {c}: {s}" for c, s in estados.items() if s != "completo"] + [
        f"aprobación de {e['caso']}: trabajos de aprendizaje sin terminar"
        for e in elegidas if ((leer_json(ruta_aprobacion(_base_de(ctx, e['caso']), ctx.version,
                                                          e['caso'])) or {}).get("aprobacion") or {}
                              ).get("trabajos", {}).get("pendientes")]
    resumen = {"estado": "aprobaciones_terminadas" if not motivos else "no certificable",
               "motivos": motivos, "aprobaciones": estados, "consumo": ctx.contador.resumen(),
               "version": ctx.version, "sha": ctx.sha}
    escribir_atomico(_dir_version(ctx) / "aprobaciones_estado.json", resumen)
    return {"estado": resumen["estado"], "salida": EXIT_OK, "detalle": resumen}


def _recuperar_huerfanas_aprob(ctx: Contexto) -> None:
    """Una aprobación que murió a medias: consumo DESCONOCIDO, intento de infraestructura."""
    for base in _bases(ctx):
        for ruta in sorted((base / ctx.version).glob("*/aprob.en_curso.json")):
            marca = leer_json(ruta) or {}
            caso_id, rep, n = marca.get("caso_id"), marca.get("rep"), marca.get("intento")
            if isinstance(n, int) and caso_id:
                destino = ruta_intento_aprob(base, ctx.version, caso_id, n)
                if not destino.exists():
                    escribir_atomico(destino, {
                        "n": n, "caso_id": caso_id, "rep": rep, "estado": "fallo_infraestructura",
                        "clase": "infraestructura", "huerfano": True,
                        "error": "el proceso murió con la aprobación a medias (consumo desconocido)",
                        "consumo_turno": {"desconocido": True}, "consumo_aprobacion": {"desconocido": True}})
            try:
                ruta.unlink()
            except OSError:
                pass


# ══════════════════════════════════════════════════════════════════════════════
# 8 · Montaje real (modelo + DB sintéticos). Requiere el clúster aislado levantado.
# ══════════════════════════════════════════════════════════════════════════════
def es_alias_codex(alias: Any) -> bool:
    """`cli-codex` y `cli-codex-eval`: la cuota de Codex, aparte de la de Claude (§5.5, 5C)."""
    return str(alias or "").startswith("cli-codex")


def consumo_desde_guardian(guard: Any, m: dict) -> dict:
    """Consumo (delta) de una corrida desde la marca, separado en Claude y Codex. Un fallo sin
    alias reconocible se atribuye a Claude (lado conservador del techo de Claude)."""
    todos = list(getattr(guard, "intentos_fallidos", None) or [])[m["fallidos"]:]
    codex = [f for f in todos if es_alias_codex(f.get("alias"))]
    claude = [f for f in todos if not es_alias_codex(f.get("alias"))]
    sin_reg = int(getattr(guard, "intentos_fallidos_sin_registro", 0) or 0) - m["sin_registro"]
    return {"claude_conocido": guard.tokens_llm - m["tokens"],
            "codex_conocido": guard.tokens_codex - m.get("codex_tokens", 0),
            "llamadas": (guard.llamadas_llm - m["calls"]) + (guard.llamadas_codex - m.get("codex_calls", 0)),
            "fallidos": claude, "codex_fallidos": codex, "sin_registro": sin_reg}


def marca_guardian(guard: Any) -> dict:
    return {"calls": guard.llamadas_llm, "tokens": guard.tokens_llm,
            "codex_calls": guard.llamadas_codex, "codex_tokens": guard.tokens_codex,
            "fallidos": len(getattr(guard, "intentos_fallidos", None) or []),
            "sin_registro": int(getattr(guard, "intentos_fallidos_sin_registro", 0) or 0)}


def crear_guardian_banco(spend_guard_mod: Any, **kw: Any) -> Any:
    """`EvalSpendGuard` que separa los tokens de EMBEDDINGS (siembra, Voyage) de los del modelo.

    `note_call` los suma a `total_tokens`/`calls`; con ~10 000 fragmentos sembrados por versión
    inflarían millones de tokens de «cuota Claude» (y la proyección de la piloto, que decide R) y
    una muerte tras sembrar se clasificaría como fallo de producto. Se usa `tokens_llm`/`llamadas_llm`."""
    class GuardBanco(spend_guard_mod.EvalSpendGuard):
        def __init__(self, *a: Any, **k: Any) -> None:
            super().__init__(*a, **k)
            self.tokens_embeddings = 0
            self.llamadas_embeddings = 0
            self.tokens_codex = 0
            self.llamadas_codex = 0

        def note_call(self, *, alias: str, prompt_tokens: int, completion_tokens: int,
                      total_tokens: int, cost_usd: float, seconds: float) -> None:
            super().note_call(alias=alias, prompt_tokens=prompt_tokens,
                              completion_tokens=completion_tokens, total_tokens=total_tokens,
                              cost_usd=cost_usd, seconds=seconds)
            if alias == spend_guard_mod.embed_alias():
                self.tokens_embeddings += int(total_tokens or 0)
                self.llamadas_embeddings += 1
            elif es_alias_codex(alias):            # la segunda IA (5C): su propia cuota
                self.tokens_codex += int(total_tokens or 0)
                self.llamadas_codex += 1

        @property
        def tokens_llm(self) -> int:               # CLAUDE: sin embeddings ni Codex
            return self.total_tokens - self.tokens_embeddings - self.tokens_codex

        @property
        def llamadas_llm(self) -> int:             # llamadas a Claude
            return self.calls - self.llamadas_embeddings - self.llamadas_codex

    return GuardBanco(**kw)


def version_cli() -> Optional[str]:
    """`claude --version`, sin ventana, o None si no se puede obtener."""
    flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        out = subprocess.run(["claude", "--version"], capture_output=True, text=True, timeout=30,
                             creationflags=flags, check=False)
    except (OSError, subprocess.SubprocessError):
        return None
    texto = (out.stdout or "").strip()
    return texto if out.returncode == 0 and texto else None


def cargar_protocolo() -> Any:
    """Importa `protocolo.py`; sin él (o con una constante ausente) el runner no arranca."""
    try:
        from mia.eval.banco04 import protocolo
    except Exception as exc:  # noqa: BLE001
        raise BancoAbortado(f"No se puede importar mia.eval.banco04.protocolo: {exc}") from exc
    return protocolo


# Estimación de las 17 aprobaciones sin cambios (§3.2, tabla del Bloque 0: ≈ 1,0 M). Es una cifra
# de la PROSA del protocolo, no una constante de `protocolo.py`: se declara aquí, con su fuente.
APROBACIONES_EST_TOKENS = 1_000_000


def constantes_de_protocolo(protocolo: Any, bloque: int) -> dict:
    """Techo, reserva y R del bloque (0 ó 7) desde `protocolo.py`. Si falta algo → `BancoAbortado`
    (fail-closed): sin reserva del juicio declarada no se produce, porque la producción podría
    comerse la cuota que hace falta para juzgar (§3.4)."""
    clave = {0: "bloque0", 7: "bloque7"}.get(bloque)
    try:
        techos = protocolo.TECHOS_CIRCUITO[clave]
        reserva = protocolo.RESERVA_JUICIO[clave]      # sin fallback: si falta, fail-closed
        fuente = "protocolo.py"
        techo_claude, techo_codex = int(techos["claude"]), int(techos["codex"])
        reserva_claude = int(reserva["claude"])
        r_codex = reserva["codex"]
        reserva_codex = techo_codex if r_codex == "total" else int(r_codex)
        return {"techo_claude": techo_claude, "techo_codex": techo_codex,
                "reserva_claude": reserva_claude, "reserva_codex": reserva_codex,
                "reserva_fuente": fuente, "r_reducido": int(protocolo.R_CONTINGENCIA_PEQUENOS_SIN_FUGA),
                "rotulo_suspension": str(protocolo.ROTULO_SUSPENSION),
                "n_casos": int(protocolo.N_CASOS_TOTAL)}
    except (AttributeError, KeyError, TypeError, ValueError) as exc:
        raise BancoAbortado(f"protocolo.py no define techo/reserva/R del bloque {bloque}: "
                            f"{type(exc).__name__}: {exc}") from exc


def _montaje_real(args: argparse.Namespace, valores: dict) -> int:
    """Importa `mia` (YA con el entorno aislado aplicado) y corre el banco de verdad."""
    sys.path.insert(0, str(ROOT / "backend"))
    import psycopg  # noqa: WPS433

    from mia import config
    from mia.agent import llm as llm_mod
    from mia.agents.state import thread_id_for
    from mia.db import pool
    from mia.eval import cases as cases_mod
    from mia.eval import harness, holdout, spend_guard
    from mia.metrics import usage as usage_metrics
    from mia.onboarding import soul_interview

    verificar_entorno_cargado(valores, os.environ, config.MIA_HOME, config.DATABASE_URL)
    protocolo = cargar_protocolo()
    k = constantes_de_protocolo(protocolo, args.bloque)
    if k["rotulo_suspension"] != TEXTO_INCOMPLETO:
        raise BancoAbortado("El rótulo de suspensión del runner no coincide con protocolo.py.")
    cli = version_cli()
    if not cli:
        raise BancoAbortado("No se pudo registrar la versión del CLI de Claude (§9.4).")
    os.environ["MIA_EVAL_PERSIST_FULL"] = "1"
    os.environ["MIA_EVAL_CLI_VERSION"] = cli

    casos = list(cases_mod.load_golden_cases()) + list(cases_mod.load_large_cases()) + \
        list(holdout.load_holdout_cases(holdout.HOLDOUT_PURPOSE_MEASURE))
    ids_custodiados: list[str] = []
    jurisdicciones: dict[str, list[str]] = {}
    cust_abierta = None
    if args.incluir_custodiados:
        from mia.eval.banco04 import custodia
        # solo con el propósito de medición. Se mantiene ABIERTA mientras dura la corrida: su llave
        # cifra las salidas crudas de V1-V4 (§2.3); se cierra al terminar (`cerrar_custodia`).
        cust_abierta = custodia.abrir(custodia.PROPOSITO_MEDICION)
        cust = list(cust_abierta.casos())
        jurisdicciones = cust_abierta.jurisdicciones()
        ids_custodiados = [c.id for c in cust]
        casos += cust
    try:
        plan = plan_desde_protocolo(protocolo, [c.id for c in casos], ids_custodiados)
    except KeyError as exc:
        raise BancoAbortado(f"Caso fuera de la muestra del protocolo: {exc}") from exc
    muestra_completa = len(plan) == k["n_casos"]
    if not muestra_completa and not args.permitir_parcial:
        raise BancoAbortado(f"La muestra tiene {len(plan)} de {k['n_casos']} casos (faltan los "
                            "voluminosos custodiados): un banco parcial no es certificable. "
                            "Use --permitir-parcial solo para ensayos.")
    soul_texto = Path(args.soul_plantilla).read_bytes()
    soul_esperado = hashlib.sha256(soul_texto).hexdigest()
    # I10 — manifiesto inmutable: `--sha` debe ser el SHA REAL del árbol medido, y el árbol limpio.
    info = info_arbol_git(ROOT)
    verificar_sha_declarado(args.sha, info["sha"])
    if not info["arbol_limpio"] and not args.permitir_arbol_sucio:
        raise BancoAbortado("El árbol tiene cambios sin commitear: lo medido no sería el SHA declarado. "
                            "Use --permitir-arbol-sucio solo para ensayos (queda en el manifiesto).")
    manifiesto = construir_manifiesto(
        version=args.version, sha_arbol=info["sha"], arbol_limpio=info["arbol_limpio"],
        soul_sha256=soul_esperado, cli_version=cli, politica=POLITICA_FIJA,
        protocolo_version=str(protocolo.VERSION_PROTOCOLO), protocolo_hash=str(protocolo.hash_protocolo()),
        runner_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    pg = dict(host=valores.get("PG_HOST", "127.0.0.1"), port=valores["PG_PORT"],
              dbname=valores.get("PG_DB", "mia"), user="postgres",
              password=valores.get("PG_PASSWORD", ""))
    contador = ContadorCuota(techo_claude=k["techo_claude"], techo_codex=k["techo_codex"],
                             reserva_juicio_claude=k["reserva_claude"],
                             reserva_juicio_codex=k["reserva_codex"])
    guard = crear_guardian_banco(spend_guard, run_limit_usd=args.max_usd, source="cli",
                                 session_id=f"banco04-{args.version}")
    salida = verificar_salida_fuera_del_repo(Path(args.salida), ROOT)
    salida_cust = None
    if args.incluir_custodiados:
        salida_cust = verificar_salida_custodia(Path(args.salida_custodia), repo_root=ROOT,
                                                mia_home=valores["MIA_HOME"], salida=salida)
    holder: dict[str, Any] = {}

    def marca() -> dict:
        return marca_guardian(guard)

    def consumo_desde(m: dict) -> dict:
        return consumo_desde_guardian(guard, m)

    def hash_soul() -> Optional[str]:
        p = soul_interview.soul_path(holder["tenant"])
        return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None

    def fijar_jurisdicciones(codigos: list[str], tenant: Optional[str] = None) -> None:
        """`[]` = despacho sin ordenamiento (`generic`); `["co"]` = el pack co. Se fija en CADA
        corrida (también `[]` en los casos visibles) para que nunca herede el del caso previo."""
        from psycopg.types.json import Json
        with psycopg.connect(autocommit=True, **pg) as c:
            c.execute(
                "INSERT INTO tenant_settings (tenant_id, config) "
                "VALUES (%s::uuid, jsonb_build_object('jurisdictions', %s::jsonb)) "
                "ON CONFLICT (tenant_id) DO UPDATE SET config = "
                "coalesce(tenant_settings.config, '{}'::jsonb) || "
                "jsonb_build_object('jurisdictions', %s::jsonb), updated_at = now()",
                (tenant or holder["tenant"], Json(list(codigos)), Json(list(codigos))))

    async def producir(caso: Any, rep: int) -> dict:
        fijar_jurisdicciones(jurisdicciones.get(caso.id, []))
        res = await harness.run_case(holder["tenant"], caso, tenant_allow_real=False)
        if res.get("matter_id"):
            holder["matters"].append(res["matter_id"])      # para limpiar sus checkpoints
        return res

    def armar_ctx() -> Contexto:
        return Contexto(
            salida=salida, version=args.version, sha=args.sha, semilla=args.semilla, plan=plan,
            casos={c.id: c for c in casos}, contador=contador, soul_esperado=soul_esperado,
            r_reducido=k["r_reducido"], consumo_aprobaciones=APROBACIONES_EST_TOKENS,
            muestra_completa=muestra_completa, cli_version=cli, salida_custodia=salida_cust,
            ids_custodiados=frozenset(ids_custodiados), max_segundos=args.max_minutos * 60.0,
            reanudacion_aprobada=args.reanudar_aprobado_por_pipe,
            versiones_contador=tuple(v for v in (args.versiones_contador or "").split(",") if v),
            cifrar=(cust_abierta.cifrar_registro if cust_abierta is not None else None),
            manifiesto=manifiesto)

    async def esperar_trabajos(tenant: str) -> dict:
        """Espera a que terminen los trabajos de aprendizaje del despacho (§5.5): sin API ni
        programador, el runner levanta el `DurableWorker` y lo detiene al terminar."""
        from mia.jobs.durable import DurableWorker
        worker = DurableWorker()
        tarea = asyncio.create_task(worker.start())
        limite = time.monotonic() + args.espera_trabajos
        pendientes = -1
        try:
            while time.monotonic() < limite:
                with psycopg.connect(autocommit=True, **pg) as c:
                    pendientes = int(c.execute(
                        "SELECT count(*) FROM durable_jobs WHERE tenant_id=%s::uuid "
                        "AND status IN ('queued','running')", (tenant,)).fetchone()[0])
                if pendientes == 0:
                    break
                await asyncio.sleep(2)
        finally:
            await worker.stop(grace_seconds=20)
            tarea.cancel()
            await asyncio.gather(tarea, return_exceptions=True)
        with psycopg.connect(autocommit=True, **pg) as c:
            por_estado = {r[0]: int(r[1]) for r in c.execute(
                "SELECT status, count(*) FROM durable_jobs WHERE tenant_id=%s::uuid GROUP BY 1",
                (tenant,)).fetchall()}
        return {"por_estado": por_estado, "pendientes": max(0, pendientes)}

    async def abrir_despacho_aprob(caso: Any) -> dict:
        with psycopg.connect(autocommit=True, **pg) as c:
            tenant = str(c.execute(
                "INSERT INTO tenants(name) VALUES('[banco04] aprobación') RETURNING id").fetchone()[0])
        home = Path(valores["MIA_HOME"]) / "aprobaciones" / f"{caso.id}-{tenant[:8]}"
        home.mkdir(parents=True, exist_ok=True)
        h = {"tenant": tenant, "home": home, "previo_home": config.MIA_HOME, "matters": []}
        config.MIA_HOME = home                      # su propio MIA_HOME: la aprobación escribe el SOUL
        ruta = soul_interview.soul_path(tenant)
        ruta.parent.mkdir(parents=True, exist_ok=True)
        ruta.write_bytes(soul_texto)
        fijar_jurisdicciones(jurisdicciones.get(caso.id, []), tenant)
        return h

    async def producir_aprob(h: dict, caso: Any) -> dict:
        scope = usage_metrics.set_usage_scope(h["tenant"], source="eval")
        try:
            res = await harness.run_case(h["tenant"], caso, tenant_allow_real=False)
        finally:
            usage_metrics.reset_usage_scope(scope)
        if res.get("matter_id"):
            h["matters"].append(res["matter_id"])
        return res

    async def aprobar_aprob(h: dict, res: dict) -> dict:
        """Aprobación SIN cambios, igual que `POST /matters/{id}/approve` (hitl.py)."""
        from langgraph.types import Command
        from mia.agents.checkpointer import open_checkpointer
        from mia.agents.graph import build_matter_graph
        from mia.memory import legal_ledger
        scope = usage_metrics.set_usage_scope(h["tenant"], res["matter_id"], source="eval")
        try:
            async with open_checkpointer() as cp:
                graph = build_matter_graph(cp)
                cfg = {"configurable": {"thread_id": thread_id_for(h["tenant"], res["matter_id"])}}
                state = await graph.aget_state(cfg)
                vals = (state.values or {}) if state else {}
                if not legal_ledger.verification_passes((vals.get("metadata") or {}).get("verification")):
                    return {"aprobada": False,
                            "motivo": "la revisión independiente no permite emitir como final"}
                orden = {"decision": "approved", "attested": True,
                         "draft_hash": legal_ledger.content_hash(vals.get("draft") or "")}
                async for _ in graph.astream(Command(resume=orden), cfg, stream_mode="updates"):
                    pass
                final = await graph.aget_state(cfg)
                aprendizaje = (((final.values or {}).get("metadata") or {}).get("learning") or {}
                               ).get("status")
        finally:
            usage_metrics.reset_usage_scope(scope)
        try:
            await usage_metrics.flush_pending()
        except Exception:  # noqa: BLE001
            pass
        trabajos = await esperar_trabajos(h["tenant"])
        return {"aprobada": True, "aprendizaje": aprendizaje, "trabajos": trabajos}

    async def cerrar_aprob(h: dict) -> None:
        config.MIA_HOME = h["previo_home"]
        import shutil
        shutil.rmtree(h["home"], ignore_errors=True)
        with psycopg.connect(autocommit=True, **pg) as c:
            for mid in h["matters"]:
                tid = thread_id_for(h["tenant"], mid)
                for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                    try:
                        c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (tid,))
                    except Exception:  # noqa: BLE001
                        pass
            c.execute("DELETE FROM tenants WHERE id = %s", (h["tenant"],))

    async def correr_aprobaciones() -> dict:
        await pool.open_pool()
        try:
            dapr = DepsAprobacion(
                abrir_despacho=abrir_despacho_aprob, producir_hasta_revision=producir_aprob,
                aprobar=aprobar_aprob, cerrar_despacho=cerrar_aprob, marca=marca,
                consumo_desde=consumo_desde, paradas=(spend_guard.SpendGuardHalt,))
            with politica_fija(llm_mod), spend_guard.install(), guard.activate():
                return await ejecutar_aprobaciones(armar_ctx(), dapr)
        finally:
            await pool.close_pool()
            if cust_abierta is not None:
                cust_abierta.cerrar()

    async def correr() -> dict:
        await pool.open_pool()
        with psycopg.connect(autocommit=True, **pg) as c:
            holder["tenant"] = str(c.execute(
                "INSERT INTO tenants(name) VALUES('[banco04] despacho efímero') RETURNING id"
            ).fetchone()[0])
        # SOUL de plantilla idéntica por versión, con su sha256 comprobado antes de cada corrida
        ruta_soul = soul_interview.soul_path(holder["tenant"])
        ruta_soul.parent.mkdir(parents=True, exist_ok=True)
        ruta_soul.write_bytes(soul_texto)
        matters: list[str] = holder.setdefault("matters", [])
        try:
            ctx = armar_ctx()
            deps = Deps(producir=producir, marca=marca, consumo_desde=consumo_desde,
                        hash_soul=hash_soul, paradas=(spend_guard.SpendGuardHalt,))
            scope = usage_metrics.set_usage_scope(holder["tenant"], source="eval")
            try:
                with politica_fija(llm_mod), spend_guard.install(), guard.activate():
                    return await ejecutar_banco(ctx, deps)
            finally:
                usage_metrics.reset_usage_scope(scope)
                try:
                    await usage_metrics.flush_pending()
                    # §9.4: el desglose por nodo se captura ANTES de borrar el despacho efímero
                    # (el borrado se lleva sus filas de turn_usage).
                    por_nodo = await harness.usage_by_node(holder["tenant"])
                    escribir_atomico(salida / args.version / f"usage_by_node.{int(time.time())}.json",
                                     por_nodo)
                except Exception as exc:  # noqa: BLE001 — se declara, no tumba el tramo
                    print(f"AVISO: no se pudo capturar usage_by_node: {exc}", file=sys.stderr)
        finally:
            await pool.close_pool()
            if cust_abierta is not None:
                cust_abierta.cerrar()
            with psycopg.connect(autocommit=True, **pg) as c:
                for mid in matters:
                    tid = thread_id_for(holder["tenant"], mid)
                    for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                        try:
                            c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (tid,))
                        except Exception:  # noqa: BLE001
                            pass
                c.execute("DELETE FROM tenants WHERE id = %s", (holder["tenant"],))

    res = asyncio.run(correr_aprobaciones() if args.fase == "aprobaciones" else correr())
    print(json.dumps({k2: v for k2, v in res.items() if k2 != "marcador"}, ensure_ascii=False,
                     indent=2, default=str))
    return int(res.get("salida", EXIT_OK))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Runner de producción del banco 0.4 (banco04-v1.2)")
    ap.add_argument("--version", required=True, help="etiqueta de la versión (p. ej. 0.4 / 0.3.3)")
    ap.add_argument("--sha", required=True, help="SHA de la versión que se mide")
    ap.add_argument("--bloque", type=int, choices=(0, 7), default=0)
    ap.add_argument("--salida", required=True, help="carpeta de salidas crudas (FUERA del repo)")
    ap.add_argument("--soul-plantilla", required=False, help="SOUL de plantilla idéntico por versión")
    ap.add_argument("--semilla", default="banco04")
    ap.add_argument("--max-minutos", type=float, default=9.0, help="tramo (<10 min por comando)")
    ap.add_argument("--max-usd", type=float, default=2.0, help="tope del guardián de embeddings")
    ap.add_argument("--incluir-custodiados", action="store_true",
                    help="añade los 4 voluminosos custodiados (V1-V4) vía mia.eval.banco04.custodia")
    ap.add_argument("--salida-custodia", default=None,
                    help="carpeta APARTE para los crudos de V1-V4 (fuera del repo y de MIA_HOME); "
                         "obligatoria con --incluir-custodiados")
    ap.add_argument("--permitir-parcial", action="store_true",
                    help="ensayo con menos de 17 casos: el resultado queda «no certificable»")
    ap.add_argument("--reanudar-aprobado-por-pipe", default=None, metavar="REF",
                    help="referencia de la aprobación expresa de Pipe para reanudar un banco suspendido")
    ap.add_argument("--fase", choices=("produccion", "aprobaciones"), default="produccion",
                    help="`aprobaciones`: ejecuta las aprobaciones elegidas (cada una en su propio "
                         "despacho y MIA_HOME) cuando la producción ya terminó")
    ap.add_argument("--espera-trabajos", type=float, default=300.0, metavar="SEG",
                    help="cuánto esperar a que terminen los trabajos de aprendizaje de una aprobación")
    ap.add_argument("--versiones-contador", default="",
                    help="Bloque 7: versiones que suman contra el mismo techo (p. ej. 0.4,0.3.3)")
    ap.add_argument("--permitir-arbol-sucio", action="store_true",
                    help="ensayo: mide un árbol con cambios sin commitear (queda en el manifiesto)")
    ap.add_argument("--plan", action="store_true", help="solo valida el aislamiento y no corre nada")
    args = ap.parse_args(argv)
    try:
        valores = verificar_aislamiento(os.environ, repo_root=ROOT)
        verificar_salida_fuera_del_repo(Path(args.salida), ROOT)
        if args.incluir_custodiados:
            if not args.salida_custodia:
                raise BancoAbortado("--incluir-custodiados exige --salida-custodia.")
            verificar_salida_custodia(Path(args.salida_custodia), repo_root=ROOT,
                                      mia_home=valores["MIA_HOME"], salida=Path(args.salida))
        aplicar_entorno(valores)
        if args.plan:
            print(json.dumps({"aislamiento": "ok", "pg_port": valores.get("PG_PORT"),
                              "mia_home": valores.get("MIA_HOME")}, ensure_ascii=False))
            return EXIT_OK
        if not args.soul_plantilla:
            raise BancoAbortado("--soul-plantilla es obligatorio.")
        return _montaje_real(args, valores)
    except (AislamientoError, BancoAbortado) as exc:
        print(f"RECHAZADO: {exc}", file=sys.stderr)
        return EXIT_RECHAZADO


if __name__ == "__main__":
    raise SystemExit(main())
