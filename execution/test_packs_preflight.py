"""Gate: packs verificados y preflight fail-closed del draft."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.agents import packs  # noqa: E402

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

FAILED: list[str] = []


def check(name: str, ok: bool) -> None:
    print(f"  [{'OK' if ok else 'FAIL'}] {name}")
    if not ok:
        FAILED.append(name)


def main() -> int:
    blob = (
        "Hechos.\n===FACT_PACK===\n"
        '{"hechos": [{"texto": "El accidente.", "locator": "[doc 1]"}], '
        '"conteo_declarado": 1}\n===END===\n'
    )
    pack = packs.parse_fact_pack(blob, num_documents=2)
    check("fact-pack válido cierra", pack.conteo_declarado == 1 and pack.hechos[0].locator == "[doc 1]")

    try:
        packs.parse_fact_pack("prosa sin locators ni JSON", num_documents=1)
        raised = False
    except packs.PackError:
        raised = True
    check("prosa sin pack: PackError (no se traga)", raised)

    try:
        packs.parse_fact_pack(
            '===FACT_PACK===\n{"hechos": [{"texto": "x", "locator": "[doc 1]"}], '
            '"conteo_declarado": 9}\n===END===',
            num_documents=1)
        mismatch = False
    except packs.PackError:
        mismatch = True
    check("conteo declarado distinto del real: PackError", mismatch)

    src = packs.source_pack_from_research(
        [{"referencia": "Ley 1", "pasaje": "art. 1", "tipo": "norma"}])
    check("source-pack sale de las fichas, no del LLM",
          src.conteo_declarado == 1 and len(src.fuentes[0].chunk_hash) == 64)

    strategy_blob = (
        "===STRATEGY_PACK===\n"
        '{"argumentos": [{"id": "A1", "tesis": "Hay caducidad", '
        '"fuente_refs": ["Ley 1"], "seleccionado": true, "contraparte": "", '
        '"prueba": "[doc 1]"}], "descartes": [{"tesis": "Culpa", "motivo": "No consta"}]}\n'
        "===END===\n"
    )
    strat = packs.parse_strategy_pack(strategy_blob, source_pack=src)
    check("strategy-pack exige cita del pack de fuentes", strat.argumentos[0].seleccionado)

    try:
        packs.parse_strategy_pack(
            '===STRATEGY_PACK===\n{"argumentos": [{"id": "A1", "tesis": "x", '
            '"fuente_refs": ["Norma inventada"], "seleccionado": true}], "descartes": []}\n'
            "===END===",
            source_pack=src)
        cited = False
    except packs.PackError:
        cited = True
    check("tesis sin fuente del pack: PackError", cited)

    try:
        packs.preflight_draft(fact_pack=None, source_pack=src, strategy_pack=strat)
        pre = False
    except packs.PackError:
        pre = True
    check("preflight sin fact-pack aborta", pre)

    packs.preflight_draft(fact_pack=pack, source_pack=src, strategy_pack=strat)
    check("preflight con los tres packs cierra", True)

    md = packs.example_metadata_packs()
    check("example_metadata_packs alimenta tests de nodos posteriores",
          md["facts_pack_ok"] is True and md["strategy_pack_ok"] is True)

    if FAILED:
        print("FAIL:", ", ".join(FAILED))
        return 1
    print("PASS: packs y preflight fail-closed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
