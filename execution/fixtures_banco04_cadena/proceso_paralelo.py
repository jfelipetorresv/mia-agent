"""Proceso hijo de E2E-13 y E2E-15: una etapa de la cadena desde su `main`, con BARRERAS en el doble.

El doble ES la invocación al proveedor: bloquearlo cae exactamente entre el compromiso irrevocable
(`seq_envio`, escrito bajo el cerrojo) y la invocación real (§4.2, paso 4). Las barreras son
archivos en `barreras/`: el hijo crea `<nombre>` para avisar y espera `<nombre>` para seguir.

    python -X utf8 proceso_paralelo.py <config.json>

config: {"modo": "aprobar" | "juzgar", "escenario": {...}, "version": "nuevo",
         "barreras": "<carpeta>", "reanudar": null | "REF"}
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

AQUI = Path(__file__).resolve().parent
sys.path.insert(0, str(AQUI.parent))

from fixtures_banco04_cadena import entorno  # noqa: E402

entorno.preparar_proceso()

from fixtures_banco04_cadena import dobles, escenario  # noqa: E402

ESPERA_MAX = 300.0


def esperar(carpeta: Path, nombre: str) -> None:
    t0 = time.monotonic()
    while not (carpeta / nombre).exists():
        if time.monotonic() - t0 > ESPERA_MAX:
            raise TimeoutError(f"barrera {nombre} no llegó")
        time.sleep(0.05)


def avisar(carpeta: Path, nombre: str) -> None:
    (carpeta / nombre).write_text(str(os.getpid()), encoding="utf-8")


def reconstruir(d: dict) -> escenario.Escenario:
    e = object.__new__(escenario.Escenario)
    for k, v in d.items():
        setattr(e, k, Path(v) if k in escenario.CAMPOS_RUTA else v)
    e.cus = None
    e.versiones = tuple(e.versiones)
    return e


class ClaudeBloqueante(dobles.ClaudeCLIDoble):
    """En la llamada `aprendizaje` de la aprobación: avisa `A_en_invocacion`, espera `A_suelta` y
    responde SIN `output_tokens` (evento desconocido sin cota)."""

    carpeta: Path = Path(".")

    def __call__(self, cmd, *a, input=None, **kw):  # noqa: A002
        texto = input or ""
        if "nodo=aprendizaje" in texto and not getattr(self, "_hecho", False):
            self._hecho = True
            avisar(self.carpeta, "A_en_invocacion")
            esperar(self.carpeta, "A_suelta")
            r = super().__call__(cmd, *a, input=input, **kw)
            data = json.loads(r.stdout)
            data["usage"].pop("output_tokens", None)
            r.stdout = json.dumps(data, ensure_ascii=False)
            return r
        return super().__call__(cmd, *a, input=input, **kw)


def main() -> int:
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    e = reconstruir(cfg["escenario"])
    barreras = Path(cfg["barreras"])
    if cfg["modo"] == "aprobar":
        cl = ClaudeBloqueante()
        cl.carpeta = barreras
        code = e.aprobar(cfg["version"], proveedores=dobles.proveedores(claude=cl),
                         casos=cfg.get("casos"), solo_piloto=True, custodiados=False)
        avisar(barreras, f"A_fin_{code}")
        return 0
    if cfg["modo"] == "juzgar":
        def barrera(indice: int, nombre: str) -> None:
            if indice == 0:
                avisar(barreras, "B_comprometida")
                esperar(barreras, "B_sigue")
        rn = dobles.runners(cli_claude=e.cli_claude, cli_codex=e.cli_codex,
                            opus_kw={"barrera": barrera})
        code = e.juzgar(rn, reanudar=cfg.get("reanudar"))
        avisar(barreras, f"B_fin_{code}")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
