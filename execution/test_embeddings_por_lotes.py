"""
Mia · test_embeddings_por_lotes.py — gate: un expediente grande se puede indexar.

POR QUÉ EXISTE (sesión 52 · defecto encontrado con un expediente REAL). `embeddings.embed_texts`
mandaba TODOS los textos en una sola llamada y el proveedor rechaza el lote que pasa de su tope
de tokens. Al indexar un arbitraje de 174 páginas la llamada llegó con 127.058 tokens contra un
tope de 120.000 y la operación falló entera (TOO_MANY_TOKENS_IN_BATCH). En el producto pasa lo
mismo: `routes/ux.py::upload_document` pasa de golpe todos los fragmentos del documento, así que
al abogado le reventaba la subida de un documento grande. Sin barrera, vuelve.

Qué se verifica, sin red (el cliente del proveedor se sustituye por un doble):

  1. Un solo lote cuando cabe: nada cambia para el caso pequeño de siempre.
  2. Varios lotes cuando no cabe, y NINGUNO pasa del tope de tokens.
  3. EL ORDEN SE PRESERVA. Es la parte peligrosa: quien llama empareja vectors[i] con texts[i],
     así que devolver los vectores desordenados guardaría cada fragmento con el embedding de
     otro — un fallo SILENCIOSO que envenenaría la búsqueda del expediente sin delatarse.
  4. El tope de ITEMS por lote también se respeta (con textos cortos se alcanza antes que el de
     tokens).
  5. Si el proveedor devuelve menos vectores que textos, REVIENTA en vez de guardar un
     emparejamiento torcido.
  6. El caso real que lo destapó: 174 páginas / ~598.000 caracteres se trocean en varios lotes,
     todos bajo el tope.
  7. `upload_document` sigue pasando por esta función (si alguien la puentea, el arreglo no
     protege al abogado).

Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_embeddings_por_lotes.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia import config, embeddings  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    _results.append((nombre, ok))
    marca = "[OK]  " if ok else "[FAIL]"
    linea = f"  {marca} {nombre}"
    if not ok and detalle:
        linea += f" — {detalle}"
    print(linea)


class _LiteLLMDoble:
    """Doble del cliente: registra cada lote y devuelve un vector reconocible por texto, para
    poder comprobar el ORDEN de la salida."""

    def __init__(self, *, devolver_de_menos: bool = False) -> None:
        self.lotes: list[list[str]] = []
        self.devolver_de_menos = devolver_de_menos

    def embedding(self, *, model, input, api_key, timeout, num_retries):  # noqa: A002
        self.lotes.append(list(input))
        datos = [{"embedding": [float(len(t))] * config.EMBED_DIM} for t in input]
        if self.devolver_de_menos and len(datos) > 1:
            datos = datos[:-1]
        return SimpleNamespace(data=datos)


def _con_doble(textos: list[str], **kw):
    doble = _LiteLLMDoble(**kw)
    real_import = __builtins__["__import__"] if isinstance(__builtins__, dict) else __import__

    def _fake_import(name, *args, **kwargs):
        if name == "litellm":
            return doble
        return real_import(name, *args, **kwargs)

    if isinstance(__builtins__, dict):
        __builtins__["__import__"] = _fake_import
    else:
        __builtins__.__import__ = _fake_import
    try:
        vectores = embeddings.embed_texts(textos)
    finally:
        if isinstance(__builtins__, dict):
            __builtins__["__import__"] = real_import
        else:
            __builtins__.__import__ = real_import
    return doble, vectores


def _tokens(lote: list[str]) -> float:
    return sum(len(t) for t in lote) / embeddings._CHARS_PER_TOKEN


def main() -> int:  # noqa: C901
    print("== gate: indexar un expediente grande (embeddings por lotes) ==")

    # La clave no se usa (el cliente es un doble) pero la función la exige antes de nada.
    original_key = config.VOYAGE_API_KEY
    config.VOYAGE_API_KEY = original_key or "clave-de-prueba-no-usada"
    tope = embeddings._BATCH_TOKEN_LIMIT

    try:
        print("\n1 · el caso pequeño de siempre: un solo lote")
        doble, vs = _con_doble(["hola", "mundo", "tercero"])
        check("una sola llamada al proveedor", len(doble.lotes) == 1, f"{len(doble.lotes)}")
        check("devuelve un vector por texto", len(vs) == 3, f"{len(vs)}")
        check("lista vacía → sin llamadas y sin vectores", embeddings.embed_texts([]) == [])

        print("\n2 · lo que no cabe se trocea, y ningún lote pasa del tope")
        # Cada texto ~ tope/4 tokens → hacen falta varios lotes.
        chars_por_texto = int(tope * embeddings._CHARS_PER_TOKEN / 4)
        textos = [f"{i:04d}" + "x" * chars_por_texto for i in range(12)]
        doble, vs = _con_doble(textos)
        check("hizo varias llamadas", len(doble.lotes) > 1, f"{len(doble.lotes)}")
        check("NINGÚN lote pasa del tope de tokens",
              all(_tokens(l) <= tope for l in doble.lotes),
              f"máximo {max(_tokens(l) for l in doble.lotes):.0f} > {tope}")
        check("no se pierde ni se duplica ningún texto",
              [t for l in doble.lotes for t in l] == textos)

        print("\n3 · el orden se preserva (el fallo silencioso peligroso)")
        check("un vector por texto, en el mismo orden",
              len(vs) == len(textos)
              and all(vs[i][0] == float(len(textos[i])) for i in range(len(textos))))
        # Con longitudes distintas el vector identifica su texto sin ambigüedad.
        variados = ["a" * 10, "b" * 20, "c" * 30, "d" * 40]
        _, vv = _con_doble(variados)
        check("con longitudes distintas, cada vector sigue casando con SU texto",
              [v[0] for v in vv] == [10.0, 20.0, 30.0, 40.0], f"{[v[0] for v in vv]}")

        print("\n4 · el tope de items por lote también se respeta")
        cortos = ["x"] * (embeddings._BATCH_ITEM_LIMIT * 2 + 5)
        doble, vs = _con_doble(cortos)
        check("ningún lote pasa del tope de items",
              all(len(l) <= embeddings._BATCH_ITEM_LIMIT for l in doble.lotes),
              f"máximo {max(len(l) for l in doble.lotes)}")
        check("y siguen saliendo todos los vectores", len(vs) == len(cortos))

        print("\n5 · si el proveedor devuelve de menos, revienta (no guarda torcido)")
        fallo = False
        try:
            _con_doble(["uno", "dos", "tres"], devolver_de_menos=True)
        except RuntimeError as exc:
            fallo = "no se puede emparejar" in str(exc) or "no es fiable" in str(exc)
        check("levanta RuntimeError explicando el riesgo de emparejamiento", fallo)

        print("\n6 · el expediente real que destapó el defecto")
        # 174 páginas ≈ 598.000 caracteres, troceados como los trocea la ingesta (1200/150).
        total_chars = 598_000
        n_frag = total_chars // 1050  # ~570 fragmentos con solape
        expediente = ["y" * 1050 for _ in range(n_frag)]
        doble, vs = _con_doble(expediente)
        check(f"los ~{n_frag} fragmentos del expediente se indexan", len(vs) == n_frag)
        check("en varios lotes, todos bajo el tope",
              len(doble.lotes) > 1 and all(_tokens(l) <= tope for l in doble.lotes),
              f"{len(doble.lotes)} lotes")
        # Antes del arreglo esto habría sido UNA llamada de ~170.000 tokens: rechazada.
        check("un solo lote habría pasado del tope (el defecto era real)",
              total_chars / embeddings._CHARS_PER_TOKEN > tope)

        print("\n7 · la subida del abogado pasa por aquí")
        ux = (ROOT / "backend" / "mia" / "api" / "routes" / "ux.py").read_text(encoding="utf-8")
        check("upload_document usa embeddings.embed_texts (no puentea el arreglo)",
              "embeddings.embed_texts" in ux)
        check("el módulo documenta el defecto que originó el troceo",
              "TOO_MANY_TOKENS_IN_BATCH" in (ROOT / "backend" / "mia" / "embeddings.py")
              .read_text(encoding="utf-8"))
    finally:
        config.VOYAGE_API_KEY = original_key

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\nRESULT: {passed}/{total} checks PASS")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
