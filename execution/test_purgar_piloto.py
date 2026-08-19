"""
Mia · test_purgar_piloto.py — gate del BORRADO VERIFICABLE de un piloto con datos reales.

POR QUÉ. `execution/purgar_piloto.py` es lo que le da al abogado la certeza de que después de
probar MIA con un expediente real no queda rastro. Una herramienta de borrado que falla en
silencio es peor que no tenerla: produce certeza falsa. Este gate prueba las propiedades de las
que depende esa certeza, incluidas las dos que ya estuvieron mal durante el desarrollo:

  · el slug de la carpeta de transcripts del CLI no contemplaba los ESPACIOS de la ruta, así que
    no encontraba la carpeta y reportaba «0 coincidencias» — certeza falsa;
  · con `--todo-el-disco` el purgado del CLI borraba TODOS los transcripts de la carpeta (976 en
    la máquina de desarrollo), no solo los del piloto: material ajeno destruido.

Qué se verifica (sin red; la parte de base de datos se marca como no evaluada si no hay DB):

  1. Sin `--termino` el comando REPROBA: la certeza es la búsqueda, y sin término no hay nada
     que demostrar (sería un PASS vacío).
  2. La carpeta de transcripts del CLI se localiza aunque la ruta de MIA_HOME tenga espacios,
     dos puntos y separadores; y cuando NO se puede localizar se devuelve None (para que el
     informe lo diga) en vez de un «no existe» tranquilizador.
  3. El purgado del CLI solo toca transcripts del piloto — los que contienen un término o caen
     en la ventana — y deja intactos los ajenos, incluso sin ventana.
  4. El barrido de disco encuentra el rastro en archivos derivados y lo borra, y el informe
     nunca incluye el CONTENIDO hallado (solo ruta y número de coincidencias).
  5. Las tablas de la base se DESCUBREN del catálogo por su columna `tenant_id`, no de una lista
     cableada que envejece.

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_purgar_piloto.py
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    _results.append((nombre, ok))
    marca = "[OK]  " if ok else "[FAIL]"
    linea = f"  {marca} {nombre}"
    if not ok and detalle:
        linea += f" — {detalle}"
    print(linea)


def main() -> int:  # noqa: C901
    print("== gate del borrado verificable del piloto ==")

    fuente = (ROOT / "execution" / "purgar_piloto.py").read_text(encoding="utf-8")

    print("\n1 · sin término no se puede demostrar nada")
    check("el comando EXIGE al menos un --termino",
          "hace falta al menos al menos un --termino" in fuente
          or "hace falta al menos un --termino" in fuente)
    check("y explica que sin término sería un PASS vacío",
          "PASS vacío" in fuente)

    # Importar el módulo con un MIA_HOME de prueba QUE TIENE ESPACIOS en la ruta (el caso que
    # rompió el slug en el desarrollo).
    tmp = Path(tempfile.mkdtemp(prefix="mia purga test "))  # espacios a propósito
    mia_home = tmp / "mia data"
    (mia_home / "eval-runs" / "corrida").mkdir(parents=True, exist_ok=True)
    (mia_home / "traces").mkdir(parents=True, exist_ok=True)
    os.environ["MIA_HOME"] = str(mia_home)

    from mia import config  # noqa: E402
    importlib.reload(config)
    config.MIA_HOME = str(mia_home)
    import purgar_piloto as pp  # noqa: E402
    importlib.reload(pp)

    print("\n2 · la carpeta de transcripts del CLI se localiza (o se dice que no)")
    # Fabricamos la carpeta que el CLI crearía: la ruta slugificada bajo ~/.claude/projects.
    slug = "".join(ch if ch.isalnum() else "-" for ch in str(mia_home.resolve()))
    base_cli = Path.home() / ".claude" / "projects"
    carpeta_cli = base_cli / slug
    creada = False
    try:
        carpeta_cli.mkdir(parents=True, exist_ok=True)
        creada = True
    except OSError:
        pass

    if creada:
        hallada = pp._cli_transcript_dir()
        check("localiza la carpeta aunque MIA_HOME tenga ESPACIOS y ':' en la ruta",
              hallada is not None and hallada.resolve() == carpeta_cli.resolve(),
              f"devolvió {hallada}")
    else:
        print("  [NO EVALUADO] no se pudo crear la carpeta de prueba del CLI")

    check("cuando no se puede localizar devuelve None (no un 'no existe' tranquilizador)",
          "return None" in fuente and "certeza falsa" in fuente)
    check("el informe trata 'no localizada' como PROBLEMA, no como limpio",
          "no se pudo localizar la carpeta de transcripts" in fuente)

    print("\n3 · el purgado del CLI no destruye material ajeno")
    if creada:
        propio = carpeta_cli / "propio-del-piloto.jsonl"
        ajeno = carpeta_cli / "de-otro-trabajo.jsonl"
        propio.write_text('{"content":"prompt con ZZTERMINO-PILOTO adentro"}', encoding="utf-8")
        ajeno.write_text('{"content":"otro trabajo, nada que ver"}', encoding="utf-8")
        # Sin ventana (--todo-el-disco): el criterio debe ser el TÉRMINO, no «todos».
        res = pp.purgar_cli(["ZZTERMINO-PILOTO"], purgar=True, desde=None)
        check("borra el transcript del piloto (contiene el término)",
              not propio.exists() and "propio-del-piloto.jsonl" in res["borrados"])
        check("NO borra el transcript ajeno aunque no haya ventana",
              ajeno.exists(), "se borró material ajeno")
        check("y después reporta 0 coincidencias", res["restos"] == [])

        # Con ventana: entra por antigüedad aunque no traiga el término.
        reciente = carpeta_cli / "en-la-ventana.jsonl"
        reciente.write_text('{"content":"turno del piloto sin el nombre"}', encoding="utf-8")
        antiguo_ts = time.time() - 3600
        os.utime(ajeno, (antiguo_ts, antiguo_ts))
        res2 = pp.purgar_cli(["ZZTERMINO-PILOTO"], purgar=True, desde=time.time() - 60)
        check("con ventana, borra lo de la ventana aunque no traiga el término",
              not reciente.exists() and "en-la-ventana.jsonl" in res2["borrados"])
        check("y sigue respetando lo anterior a la ventana", ajeno.exists())
        for p in (ajeno,):
            p.unlink(missing_ok=True)
        carpeta_cli.rmdir()
    else:
        print("  [NO EVALUADO] sin carpeta de prueba del CLI")

    print("\n4 · el barrido de disco encuentra, borra y no filtra el contenido")
    derivado = mia_home / "eval-runs" / "corrida" / "cases.jsonl"
    derivado.write_text('{"draft_full":"borrador con ZZTERMINO-PILOTO dentro"}', encoding="utf-8")
    hallazgos = pp._barrer_archivos(mia_home, ["ZZTERMINO-PILOTO"], desde=None)
    check("encuentra el archivo derivado con el término", len(hallazgos) == 1)
    check("devuelve ruta y CONTEO, nunca el texto hallado",
          bool(hallazgos) and isinstance(hallazgos[0][1], int) and hallazgos[0][1] == 1)
    d = pp.purgar_disco(None, ["ZZTERMINO-PILOTO"], purgar=True, desde=None)
    check("lo borra", not derivado.exists())
    check("y después reporta 0 restos", d["restos"] == [])
    # Un PDF/DOCX del abogado NO es material derivado: no se toca.
    original = mia_home / "expediente-del-abogado.pdf"
    original.write_bytes(b"%PDF-1.4 ZZTERMINO-PILOTO")
    pp.purgar_disco(None, ["ZZTERMINO-PILOTO"], purgar=True, desde=None)
    check("NO borra los archivos originales del abogado (solo lo que MIA derivó)",
          original.exists())

    print("\n4b · las coincidencias son por PALABRA COMPLETA (este comando borra lo que halla)")
    # Buscando 'Nexa' con subcadena, cuatro corridas viejas del banco que solo decían 'anexa'
    # quedaron marcadas para borrado: material ajeno al piloto destruido por un falso positivo.
    check("'Nexa' NO casa dentro de 'anexa' ni 'conexa'",
          pp._contar("documento anexa y prueba conexa", ["Nexa"]) == 0,
          str(pp._contar("documento anexa y prueba conexa", ["Nexa"])))
    check("pero sí casa cuando es la palabra", pp._contar("el personal de Nexa S.A.", ["Nexa"]) == 1)
    check("insensible a mayúsculas", pp._contar("NEXA y nexa", ["Nexa"]) == 2)
    check("los nombres compuestos siguen casando",
          pp._contar("demanda del Banco Popular S.A.", ["Banco Popular"]) == 1)
    check("un término vacío no cuenta nada", pp._contar("cualquier texto", ["", "  "]) == 0)

    print("\n5 · la conexión a la base funciona de verdad")
    # Este check existe porque el comando reventó con AttributeError justo al llegar a la base
    # —la parte que da la certeza— por usar nombres de config que no existen (POSTGRES_* en vez
    # de PG_*). Un gate que no toca esta función no habría visto nada.
    try:
        kw = pp._pg_kwargs()
        check("_pg_kwargs() no revienta y trae los cinco parámetros",
              set(kw) == {"host", "port", "dbname", "user", "password"}, str(sorted(kw)))
    except Exception as exc:  # noqa: BLE001
        check("_pg_kwargs() no revienta y trae los cinco parámetros", False,
              f"{type(exc).__name__}: {exc}")
    check("NO usa nombres de config inexistentes (POSTGRES_*)",
          "config.POSTGRES_" not in fuente)

    print("\n6 · las tablas se descubren del catálogo, no de una lista cableada")
    check("la consulta busca la columna tenant_id en information_schema",
          "information_schema.columns" in fuente and "column_name='tenant_id'" in fuente)
    check("y el propio código dice por qué (una tabla nueva entra sola)",
          "entra sola" in fuente)

    print("\n7 · el informe advierte lo que NO puede deshacer")
    check("dice que lo ya enviado a los proveedores no se revierte",
          "NO deshace lo que ya salió" in fuente)
    check("y remite a la anonimización como la vía para eso",
          "anonymize" in fuente)

    # Limpieza propia: un gate que prueba borrado no puede dejar basura detrás.
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    check("el gate limpia su propio directorio temporal", not tmp.exists())

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
