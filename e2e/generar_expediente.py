"""Genera el expediente sintético FIJO del E2E de primera vez.

Deriva los tres documentos del caso de oro voluminoso
(`expediente-voluminoso-cruce-disperso`, backend/mia/eval/cases.py) y los
escribe como .txt en e2e/expediente/. El expediente queda versionado como
código determinista, no como binarios en git (convención del repo).

Uso:  .venv\\Scripts\\python.exe e2e\\generar_expediente.py
Salida: e2e/expediente/*.txt + manifiesto con conteo de fragmentos.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "backend"))

from mia.eval.cases import load_large_cases  # noqa: E402

DESTINO = Path(__file__).resolve().parent / "expediente"


def main() -> int:
    caso = next(
        (c for c in load_large_cases() if c.id == "expediente-voluminoso-cruce-disperso"),
        None,
    )
    if caso is None:
        print("ERROR: no existe el caso expediente-voluminoso-cruce-disperso en cases.py")
        return 1

    DESTINO.mkdir(exist_ok=True)
    manifiesto = {"case_id": caso.id, "pregunta": caso.message, "documentos": []}
    for doc in caso.documents:
        nombre = doc.filename
        if not nombre.endswith(".txt"):
            nombre += ".txt"
        cuerpo = "\n\n".join(doc.chunks)
        ruta = DESTINO / nombre
        ruta.write_text(cuerpo, encoding="utf-8")
        manifiesto["documentos"].append({"nombre": nombre, "fragmentos": len(doc.chunks)})
        print(f"  {nombre}: {len(doc.chunks)} fragmentos, {ruta.stat().st_size} bytes")

    (DESTINO / "manifiesto.json").write_text(
        json.dumps(manifiesto, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    total = sum(d["fragmentos"] for d in manifiesto["documentos"])
    print(f"Expediente fijo generado: {len(manifiesto['documentos'])} documentos, {total} fragmentos")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
