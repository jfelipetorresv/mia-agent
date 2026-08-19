"""
Mia · test_embed_cache.py — F1.4 del plan de eficiencia: caché de embeddings de consulta.

Prueba (con mutación):
  1. Dos llamadas con el MISMO texto de consulta → el proveedor se llama UNA vez.
  2. Texto distinto → el proveedor se llama de nuevo (la caché no inventa vectores).
  3. Un lote grande (ingesta) NO pasa por la caché ni la contamina.
  4. El vector devuelto por caché es igual al original y es una COPIA (mutarlo no
     envenena la caché).

Script directo (no pytest): [OK]/[FAIL], exit 1 si algo falla. Sin red: el proveedor
se dobla inyectando un módulo litellm falso en sys.modules ANTES del import diferido.
"""
from __future__ import annotations

import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FALLOS: list[str] = []
TOTAL = 0


def check(nombre: str, ok: bool, detalle: str = "") -> None:
    global TOTAL
    TOTAL += 1
    print(f"  [{'OK' if ok else 'FAIL'}]   {nombre}" + (f" — {detalle}" if detalle and not ok else ""))
    if not ok:
        FALLOS.append(nombre)


def main() -> int:
    llamadas = {"n": 0, "textos": []}

    from mia import config

    def _embedding(model=None, input=None, **kw):
        llamadas["n"] += 1
        llamadas["textos"].append(list(input))
        return SimpleNamespace(data=[
            {"embedding": [float(len(t))] + [0.0] * (config.EMBED_DIM - 1)} for t in input
        ])

    sys.modules["litellm"] = SimpleNamespace(embedding=_embedding)

    from mia import embeddings

    embeddings._query_cache.clear()
    if not config.VOYAGE_API_KEY:
        # El doble no necesita la llave real, pero embed_texts la exige: una de mentira.
        config.VOYAGE_API_KEY = "test-key"

    print("1 · misma consulta dos veces → una sola llamada al proveedor")
    v1 = embeddings.embed_texts(["¿cuál es el plazo de entrega?"])
    v2 = embeddings.embed_texts(["¿cuál es el plazo de entrega?"])
    check("el proveedor se llamó una vez", llamadas["n"] == 1, str(llamadas["n"]))
    check("el vector cacheado es igual al original", v1 == v2)

    print("2 · consulta distinta → llamada nueva (mutación del check 1)")
    embeddings.embed_texts(["otra pregunta distinta"])
    check("el proveedor se llamó de nuevo", llamadas["n"] == 2, str(llamadas["n"]))

    print("3 · un lote de ingesta no pasa por la caché")
    lote = [f"fragmento {i}" for i in range(20)]
    antes = len(embeddings._query_cache)
    embeddings.embed_texts(lote)
    embeddings.embed_texts(lote)
    check("la ingesta llama al proveedor cada vez", llamadas["n"] == 4, str(llamadas["n"]))
    check("y no contamina la caché de consultas", len(embeddings._query_cache) == antes,
          f"{antes} → {len(embeddings._query_cache)}")

    print("4 · el vector devuelto es una copia")
    v3 = embeddings.embed_texts(["¿cuál es el plazo de entrega?"])
    v3[0][0] = -999.0
    v4 = embeddings.embed_texts(["¿cuál es el plazo de entrega?"])
    check("mutar el resultado no envenena la caché", v4[0][0] != -999.0, str(v4[0][0]))
    check("y sigue sin llamar al proveedor", llamadas["n"] == 4, str(llamadas["n"]))

    ok = TOTAL - len(FALLOS)
    print(f"\nRESULT: {ok}/{TOTAL} checks PASS")
    if FALLOS:
        print("caché de embeddings FALLA:", ", ".join(FALLOS))
        return 1
    print("caché de embeddings OK — la consulta repetida no vuelve a pagar a Voyage.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
