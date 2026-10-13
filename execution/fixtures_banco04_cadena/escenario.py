"""Recorrido de las etapas de la cadena DESDE SUS `main` (IC-1) y lectura de lo que dejaron en disco.

INTERFAZ FIJADA POR LAS PRUEBAS (el contrato la deja abierta; ver el informe):

  run_banco04.main(argv, *, proveedores=None, mundo=None)
      argv añade a los actuales: --casos a,b (con --permitir-parcial), --solo-piloto,
      --fase extension, --telemetria-acreditada <sha256>, --atribucion-preregistrada <ruta.json>.
      Sin --salida-custodia: los crudos custodiados van a <MIA_BANCO04_CUSTODIA>/salidas (§1.3).
  banco04_validar_jueces.main(argv, *, runners=None, carpeta_local_appdata=None)
      argv añade --telemetria-acreditada <sha256> y --reanudar-aprobado-por-pipe <REF>;
      `carpeta_local_appdata` sustituye SOLO por parámetro la API SHGetKnownFolderPath (R9, K3).
  banco04_juzgar.main(argv, *, runners=None)
      registrar-cadena --base <S/ver> [--nuevo <S/ver>] --custodia <C> --salida <R8> --bloque 0|7
                       [--linea-base]
      juzgar --cadena <R8> --custodia <C> [--reanudar-aprobado-por-pipe REF --etapas juicio
                       --versiones a,b]
  banco04_decidir.main(argv)
      previa    --nuevo --base --custodia --cadena
      veredicto --nuevo --base --custodia --cadena --salida <VEREDICTO.json>
      linea-base --base --custodia --cadena --salida <INFORME_LINEA_BASE.json>
  banco04_medir_codex.main(argv, *, proveedores=None, mundo=None)   (argv de R14, §2)
  puerta.decidir(*, dir_nuevo, dir_base, custodia, cadena, _prueba=None)
  puerta.medir_linea_base(*, dir_base, custodia, cadena, _prueba=None)
  puerta.PruebaPuerta(manifiesto_custodia=<ruta>, desproteger=<fn>)

Toda llamada a un `main` existente pasa SIEMPRE `proveedores=`/`mundo=`/`runners=`: hoy esos
parámetros no existen y la llamada falla en el acto con `TypeError`, antes de tocar ningún CLI
real, la base 55432 o la custodia real.
"""
from __future__ import annotations

import contextlib
import importlib
import json
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from . import custodia_falsa as CF
from . import dobles, entorno, firmas

BLOQUE = 7
CAMPOS_RUTA = ("raiz", "S", "soul", "cadena", "appdata", "custodia", "manifiesto_custodia")
SOUL ="# SOUL de plantilla del banco 0.4 (sintético, idéntico por versión)\n"


class PuntoDeEntradaAusente(RuntimeError):
    """Un `main` o módulo del contrato no existe o no acepta su interfaz."""


def importar(nombre: str):
    try:
        return importlib.import_module(nombre)
    except ImportError as exc:
        raise PuntoDeEntradaAusente(f"no existe el módulo {nombre} ({exc})") from exc


def invocar(fn: Callable, *a, **kw) -> int:
    """Llama a un `main` y devuelve su código de salida (SystemExit incluido)."""
    try:
        r = fn(*a, **kw)
    except SystemExit as exc:
        c = exc.code
        return c if isinstance(c, int) else (0 if c is None else 1)
    except TypeError as exc:
        if "unexpected keyword" in str(exc) or "positional argument" in str(exc):
            raise PuntoDeEntradaAusente(f"{getattr(fn, '__module__', '?')}.{getattr(fn, '__name__', '?')} "
                                        f"no acepta la interfaz del contrato: {exc}") from exc
        raise
    return int(r) if isinstance(r, int) else 0


def head_sha() -> str:
    out = subprocess.run(["git", "-C", str(entorno.ROOT), "rev-parse", "HEAD"], capture_output=True,
                         text=True, encoding="utf-8", errors="replace", timeout=30, check=False)
    return (out.stdout or "").strip()


def versiones_cli() -> tuple[str, str]:
    """La versión del CLI que R1 registra (§9.4) es la REAL (`claude --version`): la instantánea de
    prueba tiene que acreditar esa versión exacta. Codex: `codex --version` o un marcador."""
    import run_banco04 as R
    cl = R.version_cli() or "claude-cli-desconocido"
    try:
        out = subprocess.run(["codex", "--version"], capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=30,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), check=False)
        cx = (out.stdout or "").strip() or "codex-cli-desconocido"
    except (OSError, subprocess.SubprocessError):
        cx = "codex-cli-desconocido"
    return cl, cx


# ════════════════════════════════════════════════════════════════════════════════════════
# Lectura de disco
# ════════════════════════════════════════════════════════════════════════════════════════
def leer(p: Path) -> Optional[dict]:
    try:
        return json.loads(Path(p).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def filas_r4(dir_version: Path) -> list[dict]:
    d = Path(dir_version) / "llamadas"
    out = []
    for f in sorted(d.glob("*.json")) if d.is_dir() else []:
        x = leer(f)
        if isinstance(x, dict):
            x["_ruta"] = str(f)
            out.append(x)
    return out


def archivos(dir_: Path, patron: str) -> list[Path]:
    d = Path(dir_)
    return sorted(d.glob(patron)) if d.is_dir() else []


def codigos(veredicto: Optional[dict]) -> set:
    return {m.get("codigo") for m in (veredicto or {}).get("motivos") or [] if isinstance(m, dict)}


def condiciones(veredicto: Optional[dict], metrica: str) -> list[dict]:
    """Condiciones cuyo `id` contiene el nombre literal de la métrica (interfaz fijada)."""
    return [c for c in (veredicto or {}).get("condiciones") or []
            if isinstance(c, dict) and metrica in str(c.get("id", ""))]


def valores(veredicto: Optional[dict], metrica: str) -> list:
    return [c.get("valor") for c in condiciones(veredicto, metrica)]


# ════════════════════════════════════════════════════════════════════════════════════════
# Escenario: una raíz S, una custodia de prueba, una instantánea
# ════════════════════════════════════════════════════════════════════════════════════════
class Escenario:
    def __init__(self, nombre: str, *, custodia_plantilla: Optional[Path] = None,
                 instantanea: Optional[dict] = None, versiones: tuple = ("base", "nuevo"),
                 bloque: int = BLOQUE) -> None:
        self.nombre = nombre
        self.raiz = entorno.nueva_carpeta(nombre)
        self.S = self.raiz / "S"
        self.S.mkdir()
        self.bloque = bloque
        self.versiones = tuple(versiones)
        self.soul = self.raiz / "soul-plantilla.md"
        self.soul.write_text(SOUL, encoding="utf-8")
        self.cadena = self.S / "cadena" / "MANIFIESTO_CADENA.json"
        self.appdata = self.raiz / "known-folder-localappdata"
        self.appdata.mkdir()
        if custodia_plantilla is None:
            self.cus = CF.CustodiaPrueba(self.raiz / "custodia", casos_visibles=CF.casos_visibles())
            self.custodia = self.cus.carpeta
            self.manifiesto_custodia = self.cus.ruta_manifiesto
        else:
            self.custodia = self.raiz / "custodia"
            shutil.copytree(custodia_plantilla, self.custodia)
            self.manifiesto_custodia = self.raiz / f"manifest-custodia.json"
            shutil.copy2(custodia_plantilla.parent / f"manifest-{custodia_plantilla.name}.json",
                         self.manifiesto_custodia)
            self.cus = None
        self.cli_claude, self.cli_codex = versiones_cli()
        self.instantanea = instantanea or firmas.instantanea(self.cli_claude, self.cli_codex)
        self.sha_instantanea: Optional[str] = None
        self.sha = head_sha()

    # ── contexto común ──────────────────────────────────────────────────────────
    @contextlib.contextmanager
    def contexto(self):
        with entorno.entorno(MIA_BANCO04_CUSTODIA=str(self.custodia)):
            with entorno.manifiesto_custodia(self.manifiesto_custodia):
                yield

    def preparar_instantanea(self) -> str:
        if self.sha_instantanea is None:
            try:
                self.sha_instantanea, _ = entorno.instalar_instantanea(self.instantanea)
            except FileNotFoundError as exc:
                raise PuntoDeEntradaAusente(str(exc)) from exc
        return self.sha_instantanea

    def dir(self, version: str) -> Path:
        return self.S / version

    # ── producir / aprobar (run_banco04.main) ──────────────────────────────────
    def argv_runner(self, version: str, *, fase: str = "produccion", casos: Optional[Iterable[str]] = None,
                    solo_piloto: bool = False, custodiados: bool = True, reanudar: Optional[str] = None,
                    atribucion: Optional[dict] = None, extra: Iterable[str] = (),
                    instantanea_sha: Optional[str] = None) -> list[str]:
        sha_inst = instantanea_sha or self.preparar_instantanea()
        a = ["--version", version, "--sha", self.sha, "--bloque", str(self.bloque),
             "--salida", str(self.S), "--soul-plantilla", str(self.soul), "--semilla", "banco04",
             "--max-minutos", "600", "--fase", fase, "--permitir-arbol-sucio",
             "--telemetria-acreditada", sha_inst]
        if self.bloque == 7:
            a += ["--versiones-contador", ",".join(self.versiones)]
        if custodiados:
            a += ["--incluir-custodiados"]
        if casos is not None:
            a += ["--casos", ",".join(casos), "--permitir-parcial"]
        if solo_piloto:
            a += ["--solo-piloto"]
        if reanudar:
            a += ["--reanudar-aprobado-por-pipe", reanudar]
        if atribucion is not None:
            ruta = self.raiz / f"atribucion-{version}.json"
            ruta.write_text(json.dumps(atribucion, ensure_ascii=False), encoding="utf-8")
            a += ["--atribucion-preregistrada", str(ruta)]
        return a + list(extra)

    def producir(self, version: str, *, proveedores: Optional[dict] = None, mundo=None,
                 guion: Optional[dobles.Guion] = None, sin_mundo: bool = False, **kw) -> int:
        """`sin_mundo`: el esqueleto con base de datos (§6.1, E2E-1) — solo `proveedores`."""
        import run_banco04 as R
        prov = proveedores if proveedores is not None else dobles.proveedores()
        if sin_mundo:
            with self.contexto():
                return invocar(R.main, self.argv_runner(version, **kw), proveedores=prov)
        m = mundo if mundo is not None else dobles.Mundo(self.soul, guion, version=version)
        self.ultimo_mundo = m
        with self.contexto():
            return invocar(R.main, self.argv_runner(version, **kw), proveedores=prov, mundo=m)

    def aprobar(self, version: str, *, proveedores: Optional[dict] = None, mundo=None,
                guion: Optional[dobles.Guion] = None, sin_mundo: bool = False, **kw) -> int:
        return self.producir(version, proveedores=proveedores, mundo=mundo, guion=guion,
                             fase="aprobaciones", sin_mundo=sin_mundo, **kw)

    def producir_y_aprobar(self, version: str, **kw) -> tuple[int, int]:
        guion = kw.pop("guion", None)
        prov = kw.pop("proveedores", None)
        a = self.producir(version, proveedores=prov, guion=guion, **kw)
        kw.pop("atribucion", None)
        b = self.aprobar(version, proveedores=prov, guion=guion, **kw)
        return a, b

    # ── validación reservada (VJ main) ─────────────────────────────────────────
    def validar(self, runners: Optional[dict] = None, *, version: str = "nuevo",
                reanudar: Optional[str] = None, hash_congelado: Optional[str] = None,
                appdata: Optional[Path] = None) -> int:
        import banco04_validar_jueces as VJ
        from mia.eval.banco04 import jueces
        comb = hash_congelado or jueces.hash_evaluador()["combinado"]
        acr = self.raiz / "acreditacion-v13.json"
        if self.cus is not None:
            acr.write_text(json.dumps(self.cus.acreditacion_v13(comb), ensure_ascii=False), encoding="utf-8")
        elif not acr.exists():
            raise RuntimeError("escenario sin custodia propia: la acreditación v1.3 debe copiarse")
        a = ["--conjunto-custodia", "reservado", "--salida", str(self.raiz / "vj-resumen.json"),
             "--hash-congelado", comb, "--salida-banco", str(self.S), "--version", version,
             "--bloque", str(self.bloque), "--salida-custodia", str(self.custodia / "salidas"),
             "--versiones-contador", ",".join(self.versiones), "--acreditacion-v13", str(acr),
             "--telemetria-acreditada", self.preparar_instantanea()]
        if reanudar:
            a += ["--reanudar-aprobado-por-pipe", reanudar]
        carpeta = appdata or self.appdata
        with self.contexto():
            return invocar(VJ.main, a, runners=runners or dobles.runners(cli_claude=self.cli_claude, cli_codex=self.cli_codex),
                           carpeta_local_appdata=lambda: carpeta)

    # ── juzgar ────────────────────────────────────────────────────────────────
    def registrar_cadena(self, *, base: str = "base", nuevo: Optional[str] = "nuevo",
                         linea_base: bool = False) -> int:
        J = importar("banco04_juzgar")
        a = ["registrar-cadena", "--base", str(self.dir(base)), "--custodia", str(self.custodia),
             "--salida", str(self.cadena), "--bloque", str(self.bloque)]
        if nuevo:
            a += ["--nuevo", str(self.dir(nuevo))]
        if linea_base:
            a += ["--linea-base"]
        with self.contexto():
            return invocar(J.main, a)

    def juzgar(self, runners: Optional[dict] = None, *, reanudar: Optional[str] = None,
               etapas: str = "juicio", versiones: Optional[str] = None) -> int:
        J = importar("banco04_juzgar")
        a = ["juzgar", "--cadena", str(self.cadena), "--custodia", str(self.custodia)]
        if reanudar:
            a += ["--reanudar-aprobado-por-pipe", reanudar, "--etapas", etapas,
                  "--versiones", versiones or ",".join(self.versiones)]
        with self.contexto():
            return invocar(J.main, a, runners=runners or dobles.runners(cli_claude=self.cli_claude, cli_codex=self.cli_codex))

    # ── decidir ───────────────────────────────────────────────────────────────
    def prueba_puerta(self):
        puerta = importar("mia.eval.banco04.puerta")
        from mia.eval.banco04 import custodia as cus
        return puerta.PruebaPuerta(manifiesto_custodia=self.manifiesto_custodia,
                                   desproteger=cus.desproteger_dpapi)

    def decidir(self, *, prueba: bool = True, base: str = "base", nuevo: str = "nuevo") -> dict:
        puerta = importar("mia.eval.banco04.puerta")
        with self.contexto():
            return puerta.decidir(dir_nuevo=self.dir(nuevo), dir_base=self.dir(base),
                                  custodia=self.custodia, cadena=self.cadena,
                                  _prueba=self.prueba_puerta() if prueba else None)

    def decidir_cli(self, subcomando: str = "veredicto", *, base: str = "base",
                    nuevo: Optional[str] = "nuevo") -> tuple[int, Optional[dict], Path]:
        D = importar("banco04_decidir")
        salida = self.raiz / ("INFORME_LINEA_BASE.json" if subcomando == "linea-base" else "VEREDICTO.json")
        a = [subcomando, "--base", str(self.dir(base)), "--custodia", str(self.custodia),
             "--cadena", str(self.cadena)]
        if nuevo and subcomando != "linea-base":
            a += ["--nuevo", str(self.dir(nuevo))]
        if subcomando != "previa":
            a += ["--salida", str(salida)]
        with self.contexto():
            code = invocar(D.main, a)
        return code, leer(salida), salida

    def medir_linea_base(self, *, prueba: bool = True) -> dict:
        puerta = importar("mia.eval.banco04.puerta")
        with self.contexto():
            return puerta.medir_linea_base(dir_base=self.dir("base"), custodia=self.custodia,
                                           cadena=self.cadena,
                                           _prueba=self.prueba_puerta() if prueba else None)

    # ── medición previa de Codex (R14) ─────────────────────────────────────────
    def medir_codex(self, version: str, *, proveedores: Optional[dict] = None, guion=None,
                    max_codex: int = 5_000_000, max_claude: int = 5_000_000, k: int = 1) -> int:
        M = importar("banco04_medir_codex")
        a = ["--version", version, "--sha", self.sha, "--bloque", "7", "--salida", str(self.S),
             "--soul-plantilla", str(self.soul), "--max-tokens-codex", str(max_codex),
             "--max-tokens-claude", str(max_claude), "--corridas-por-clase", str(k),
             "--telemetria-acreditada", self.preparar_instantanea(), "--permitir-arbol-sucio",
             "--incluir-custodiados", "--versiones-contador", ",".join(self.versiones)]
        prov = proveedores if proveedores is not None else dobles.proveedores(con_codex=True)
        with self.contexto():
            return invocar(M.main, a, proveedores=prov,
                           mundo=dobles.Mundo(self.soul, guion or dobles.Guion(
                               llamadas=dobles.LLAMADAS_POR_DEFECTO + (("legal_research", "investigacion"),)),
                               version=version))

    # ── utilidades ─────────────────────────────────────────────────────────────
    def serializar(self) -> dict:
        """Lo que necesita un proceso hijo (E2E-13, E2E-15) para operar sobre este escenario."""
        self.preparar_instantanea()
        out = {}
        for k in (*CAMPOS_RUTA, "nombre", "bloque", "versiones", "instantanea", "sha_instantanea",
                  "sha", "cli_claude", "cli_codex"):
            v = getattr(self, k)
            out[k] = str(v) if k in CAMPOS_RUTA else (list(v) if isinstance(v, tuple) else v)
        return out

    def r1(self, version: str) -> Optional[dict]:
        return leer(self.dir(version) / "MANIFIESTO.json")

    def r2(self, version: str, caso: str, rep: int) -> Optional[dict]:
        return leer(self.dir(version) / caso / f"rep-{rep:02d}.json")

    def r4(self, version: str) -> list[dict]:
        return filas_r4(self.dir(version))

    def todas_r4(self) -> list[dict]:
        out = []
        for d in sorted(self.S.iterdir()) if self.S.is_dir() else []:
            if d.is_dir():
                out += filas_r4(d)
        return out


def copiar(origen: Escenario, nombre: str) -> Escenario:
    """Copia COMPLETA de un escenario ya juzgado (familia I: editar en disco sin regenerar)."""
    nuevo = object.__new__(Escenario)
    nuevo.__dict__.update(origen.__dict__)
    nuevo.nombre = nombre
    nuevo.raiz = entorno.nueva_carpeta(nombre)
    for hijo in origen.raiz.iterdir():
        destino = nuevo.raiz / hijo.name
        if hijo.is_dir():
            shutil.copytree(hijo, destino)
        else:
            shutil.copy2(hijo, destino)
    nuevo.S = nuevo.raiz / "S"
    nuevo.cadena = nuevo.S / "cadena" / "MANIFIESTO_CADENA.json"
    nuevo.soul = nuevo.raiz / "soul-plantilla.md"
    nuevo.appdata = nuevo.raiz / "known-folder-localappdata"
    nuevo.custodia = nuevo.raiz / "custodia"
    nuevo.manifiesto_custodia = (nuevo.raiz / origen.manifiesto_custodia.name)
    nuevo.cus = None
    return nuevo


def derivar(origen: Escenario, nombre: str, *, regenerar: Iterable[str] = (), revalidar: bool = False) -> Escenario:
    """Copia para la familia S: borra las versiones a regenerar (y sus crudos custodiados), la cadena
    y TODO el juicio de las dos versiones; con `revalidar`, también la validación reservada. Lo
    demás (producción de la otra versión, contadores de secuencia) queda tal cual."""
    nuevo = copiar(origen, nombre)
    for v in regenerar:
        shutil.rmtree(nuevo.dir(v), ignore_errors=True)
        shutil.rmtree(nuevo.custodia / "salidas" / v, ignore_errors=True)
    shutil.rmtree(nuevo.S / "cadena", ignore_errors=True)
    for f in list(nuevo.S.rglob("*.json")):
        x = leer(f) if f.parent.name == "llamadas" else None
        if isinstance(x, dict) and (str(x.get("fase", "")).startswith("juicio")
                                    or (revalidar and x.get("fase") == "validacion")):
            f.unlink()
    for patron in ("*.juicio.json", "*.juicio.enc", "*.juicio.derivado.json"):
        for f in list(nuevo.S.rglob(patron)) + list((nuevo.custodia / "salidas").rglob(patron)):
            f.unlink()
    for d in list(nuevo.S.rglob("juicio")):
        if d.is_dir():
            shutil.rmtree(d, ignore_errors=True)
    for f in list(nuevo.S.rglob("VEREDICTO.json")) + list(nuevo.S.rglob("EXTENSION.json")):
        f.unlink()
    if revalidar:
        shutil.rmtree(nuevo.custodia / "validacion", ignore_errors=True)
        shutil.rmtree(nuevo.custodia / "registro-uso", ignore_errors=True)
        nuevo.appdata = entorno.nueva_carpeta(f"{nombre}-appdata")
    return nuevo


def instalar(instantanea: dict):
    """Instala una instantánea de prueba; sin el directorio del contrato, punto de entrada ausente."""
    try:
        return entorno.instalar_instantanea(instantanea)
    except FileNotFoundError as exc:
        raise PuntoDeEntradaAusente(str(exc)) from exc
