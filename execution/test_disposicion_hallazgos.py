"""
Mia · test_disposicion_hallazgos.py — DISPOSICIÓN DE HALLAZGOS (AVISO ESTRICTO · harness).

Origen (harness de litigio, `check-disposicion-hallazgos.py`, caso real 2026-08-19): un
gate dejó una nota, nadie la cerró —ni corrigiéndola ni descartándola con razón— y el
escrito se radicó así. La regla del harness: todo hallazgo se cierra con «corregido» +
evidencia o «descartado» + quién.

La versión de Mia es AVISO ESTRICTO (regla de implantación: toda barrera nueva nace
como aviso): al aprobar en el checkpoint de revisión, el recibo del ledger
(gate="human_approval") registra QUÉ hallazgos del informe de verificación quedaron sin
disposición. Sin bloquear jamás el botón de aprobar, sin diálogos nuevos.

Este gate prueba las tres piezas:
  1. EXTRACCIÓN — memory/hallazgos.py saca los hallazgos abiertos de un informe real
     (citas marcadas/anotadas/omitidas/quemadas, remanente fuera del detalle, [doc n]
     fantasma, afirmaciones negativas confrontadas, contaminación, gate LLM).
  2. DISPOSICIÓN — «corregido» sin evidencia o «descartado» sin quién NO cierran nada;
     con respaldo sí. Cualquier otro verbo no es disposición (regla del harness).
  3. NO-BLOQUEO + CABLEADO — la función jamás lanza (informe malformado → []), el nodo
     HITL la registra sin tocar la decisión, y el recibo de finalize la lleva como
     evidencia (verificación estructural sobre el código real del grafo).

    .venv\\Scripts\\python.exe execution\\test_disposicion_hallazgos.py

Exit 0 = PASS · 1 = FAIL.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.memory import hallazgos as H  # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(f"  [{'OK' if ok else 'FAIL'}] {name}")


INFORME = {
    "citas": 6, "marcadas": 3, "respaldadas": 2, "anotadas": 0, "omitidas": 1,
    "detalle": [
        {"cita": "Ley 80 de 1993, artículo 5", "estado": "marcada"},
        {"cita": "Decreto 1082 de 2015", "estado": "marcada"},
        {"cita": "Código Civil, artículo 1602", "estado": "respaldada"},
        {"cita": "Ley 1437 de 2011, artículo 3", "estado": "omitida"},
    ],
    "docs_fantasma": {"refs_doc": 3, "fantasmas": 1, "documentos_disponibles": 2,
                      "detalle": [{"cita": "[doc 7]", "numeros": [7], "fuera_de_rango": [7]}]},
    "afirmaciones_negativas": {"n_afirmaciones": 2, "n_a_revisar": 1,
                               "revisar": [{"oracion": "El informe no menciona al garante.",
                                            "doc": 1, "archivo": "memorando.pdf"}]},
    "gate_llm": {"veredicto": "hallazgos", "detalle": "la cita X no corresponde"},
}


def main() -> int:
    print("== 1 · extracción de hallazgos abiertos ==")
    abiertos = H.hallazgos_del_informe(INFORME)
    tipos = sorted({h["tipo"] for h in abiertos})
    # 2 marcadas del detalle + 1 marcada remanente (contador 3 > 2 vistas) + 1 omitida
    # + 1 doc fantasma + 1 negativa confrontada + 1 gate LLM = 7
    check(f"extrae los hallazgos abiertos del informe (7 esperados, {len(abiertos)} extraídos)",
          len(abiertos) == 7)
    check("cubre citas marcadas, omitidas, remanente, fantasma, negativa y gate LLM",
          tipos == sorted({"cita_marcada", "cita_omitida", "doc_fantasma",
                           "afirmacion_negativa", "gate_llm"}))
    check("lo respaldado NO es hallazgo",
          not any("1602" in h["hallazgo"] for h in abiertos))
    check("cada hallazgo lleva clave estable citable",
          all(h.get("clave") and ":" in h["clave"] for h in abiertos))
    check("informe limpio → sin hallazgos",
          H.hallazgos_del_informe({"citas": 2, "marcadas": 0, "respaldadas": 2,
                                   "detalle": [], "gate_llm": {"veredicto": "apto"}}) == [])
    check("informe ausente/malformado → [] sin lanzar",
          H.hallazgos_del_informe(None) == [] and H.pendientes_de_disposicion("x") == [])

    print("== 2 · qué cuenta como disposición ==")
    clave = next(h["clave"] for h in abiertos if h["tipo"] == "cita_marcada")
    sin = H.pendientes_de_disposicion(INFORME, None)
    check(f"sin disposiciones, TODO queda registrado como sin disposición ({len(sin)})",
          len(sin) == 7)
    ok_corr = H.pendientes_de_disposicion(
        INFORME, {clave: {"disposicion": "corregido", "evidencia": "v2, línea 118"}})
    check("«corregido» + evidencia cierra ESE hallazgo (7→6)", len(ok_corr) == 6)
    ok_desc = H.pendientes_de_disposicion(
        INFORME, {clave: {"disposicion": "descartado", "quien": "el abogado, 2026-08-24"}})
    check("«descartado» + quién cierra ESE hallazgo (7→6)", len(ok_desc) == 6)
    mal1 = H.pendientes_de_disposicion(INFORME, {clave: {"disposicion": "corregido"}})
    check("«corregido» SIN evidencia no cierra nada", len(mal1) == 7)
    mal2 = H.pendientes_de_disposicion(
        INFORME, {clave: {"disposicion": "visto", "evidencia": "ok"}})
    check("otro verbo («visto») no es disposición", len(mal2) == 7)
    fantasma = H.pendientes_de_disposicion(
        INFORME, {"cita_marcada:no existe tal hallazgo": {
            "disposicion": "corregido", "evidencia": "x"}})
    check("una disposición sobre un hallazgo inexistente no descuenta nada",
          len(fantasma) == 7)

    print("== 3 · aviso estricto: registra, no bloquea ==")
    from mia.agents.graph import MatterGraphBuilder
    src_hitl = inspect.getsource(MatterGraphBuilder.hitl_checkpoint_node)
    src_fin = inspect.getsource(MatterGraphBuilder.finalize_node)
    check("hitl_checkpoint_node calcula los hallazgos sin disposición al aprobar",
          "pendientes_de_disposicion" in src_hitl
          and "hallazgos_sin_disposicion" in src_hitl)
    check("finalize_node lleva la lista al recibo del ledger (evidence de human_approval)",
          '"hallazgos_sin_disposicion"' in src_fin
          and "record_gate" in src_fin)
    # No-bloqueo estructural: en el nodo HITL, ninguna línea que calcule la disposición
    # reasigna la decisión ni el status.
    lineas = [ln.strip() for ln in src_hitl.splitlines()
              if "pendientes_de_disposicion" in ln or "hallazgos_sin_disposicion" in ln]
    check("el registro no toca la decisión (ninguna línea reasigna dec/status/decision)",
          bool(lineas) and not any(ln.startswith(("dec ", "dec=", "status", "decision"))
                                   for ln in lineas))
    check("verification_passes NO depende de la disposición (aviso, no muro)",
          "hallazgos_sin_disposicion" not in inspect.getsource(
              __import__("mia.memory.legal_ledger", fromlist=["x"]).verification_passes))

    print("== 4 · el abogado lo VE antes de aprobar (no solo en el recibo) ==")
    # El recibo del ledger deja constancia DESPUÉS de aprobar. Quien firma tiene que poder
    # ver la lista EN el momento de firmar, o la constancia llega tarde para servirle.
    src_verif = inspect.getsource(MatterGraphBuilder.verificador_citas_node)
    check("el nodo de verificación deja los hallazgos abiertos DENTRO del informe",
          "hallazgos_del_informe" in src_verif
          and '"hallazgos_abiertos"' in src_verif
          and '"hallazgos_abiertos_total"' in src_verif)
    # Y sigue siendo aviso: la lista se calcula, no decide nada.
    lineas_v = [ln.strip() for ln in src_verif.splitlines() if "hallazgos_abiertos" in ln]
    check("listar los hallazgos abiertos no toca el borrador ni la decisión",
          bool(lineas_v) and not any(ln.startswith(("dec ", "dec=", "status", "annotated"))
                                     for ln in lineas_v))
    # La pantalla PINTA lo que el backend extrae; no reimplementa el criterio (si lo
    # reimplementara, el frontend y el recibo podrían decir cosas distintas del mismo caso).
    revision = (ROOT / "frontend" / "app" / "_components" / "CitationReview.tsx").read_text(
        encoding="utf-8")
    check("la pantalla de revisión pinta los hallazgos abiertos",
          "hallazgos_abiertos" in revision and "HALLAZGO_ROTULO" in revision)
    check("la pantalla NO reimplementa el criterio de hallazgo abierto",
          "ESTADOS_ABIERTOS" not in revision and "_disposicion_valida" not in revision)
    check("la pantalla dice que aprobar con puntos abiertos deja constancia",
          "deja" in revision and "constancia" in revision)
    # Y el panel deja de esconderse cuando no hay citas: un [doc n] fantasma o una parte de
    # otro expediente son hallazgos aunque el borrador no cite una sola norma.
    caso = (ROOT / "frontend" / "app" / "casos" / "[id]" / "CasoConBorrador.tsx").read_text(
        encoding="utf-8")
    check("el panel de revisión se muestra también sin citas cuando hay puntos abiertos",
          "hallazgos_abiertos_total" in caso)

    failed = [n for n, ok in _results if not ok]
    print(f"\n{len(_results) - len(failed)}/{len(_results)} checks OK")
    if failed:
        print("FAIL:", "; ".join(failed))
        return 1
    print("PASS: todo hallazgo aprobado sin disposición queda registrado, y nada bloquea.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
