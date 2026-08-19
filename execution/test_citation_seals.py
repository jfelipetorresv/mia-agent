"""
Mia · test_citation_seals.py — F2 del plan de eficiencia: el SELLO de verificación.

Qué prueba (con mutación, regla de APRENDIZAJES #1-2):
  1 · PURO: una cita sellada se resuelve como "sellada" (sin [VERIFICAR]) y una NO
      sellada sigue anotada (la mutación del check anterior).
  2 · QUEMADA GANA: la misma cita quemada Y sellada sale retirada, nunca sellada.
  3 · DB (RLS real): sellar desde un informe aprobado escribe; las respaldadas entran,
      las anotadas no; re-sellar es idempotente; el sello de OTRO tenant no se ve.
  4 · REVOCACIÓN: quemar la cita borra su sello (incluso con complementos de forma).
  5 · SALTO DEL GATE: la mecánica del veredicto — sin citas nuevas ni avisos, no hay
      nada que auditar (se comprueba sobre el informe, la condición exacta del nodo).

Script directo (no pytest): [OK]/[FAIL], exit 1 si falla. Necesita la DB portable.
"""
from __future__ import annotations

import asyncio
import os
import sys
import uuid
from pathlib import Path

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


CITA = "Ley 599 de 2000, artículo 32"
CITA_CON_COMPLEMENTO = "Ley 599 de 2000, artículo 32, numeral 7"
OTRA = "Sentencia T-406 de 1992"
BORRADOR = f"1. Conforme a la {CITA}, procede la exención.\n2. Según la {OTRA}, el juez pondera.\n"


def parte_pura() -> None:
    from mia.agents import verification as v

    print("1 · puro: sellada se resuelve; no sellada sigue anotada (mutación)")
    # El sello se guarda con la forma que capturó el ESCÁNER (seal_from_approved_report
    # toma e["cita"] del informe), no con el texto completo del borrador. Desde el fix
    # del cotejo por piezas (P0 2026-08-14), un sello con complementos de más
    # («…, artículo 32») ya NO respalda la forma corta — dirección segura: el fixture
    # sella lo que producción sella.
    CITA_SELLADA = "Ley 599 de 2000"
    sellos = [{"citation": CITA_SELLADA, "citation_norm": v._normalize(CITA_SELLADA),
               "fuente_tipo": "corpus", "fuente_ref": "N-TEST-001", "fuente_titulo": "Ficha"}]
    texto, report = v.annotate_draft(BORRADOR, sealed=sellos)
    estados = {e["cita"]: e["estado"] for e in report["detalle"]}

    def estado_de(cita: str) -> str:
        for k, s in estados.items():
            if k in cita or cita in k:
                return s
        return "(no encontrada)"

    check("la cita sellada queda estado=sellada", estado_de(CITA) == "sellada", str(estados))
    check("y NO lleva [VERIFICAR]", "[VERIFICAR]" not in texto.split("\n")[0], texto.split("\n")[0])
    check("la NO sellada sigue anotada (mutación)", estado_de(OTRA) == "anotada", str(estados))
    check("el informe cuenta selladas=1 y banco_sellos=1",
          report.get("selladas") == 1 and report.get("banco_sellos") == 1, str(report))
    check("la fuente del sello viaja al detalle",
          any(e.get("fuente", {}).get("referencia") == "N-TEST-001"
              for e in report["detalle"] if e["estado"] == "sellada"))

    print("1-bis · el sello coteja por PIEZAS, no por substring (P0 2026-08-14)")
    # Con el cotejo substring, un sello de «Ley 80» respaldaba «Ley 800 de 1993»:
    # una cita inventada salía como sellada-verificada. La regla es la misma del
    # cotejo cita↔fuente: piezas completas, contiguas, con conectores tolerados.
    sello_corto = {"ley 80": {"citation": "Ley 80", "fuente_ref": "N-TEST-080"}}
    check("«Ley 800 de 1993» NO coteja un sello de «Ley 80»",
          v._sealed_entry("Ley 800 de 1993", sello_corto) is None)
    check("«Ley 80 de 1993» SÍ coteja el sello de «Ley 80» (legítimo conservado)",
          v._sealed_entry("Ley 80 de 1993", sello_corto) is not None)
    check("«artículo 3 de la Ley 80» SÍ coteja (cita con complementos)",
          v._sealed_entry("artículo 3 de la Ley 80", sello_corto) is not None)
    check("«Decreto Ley 80» NO coteja (cambia el tipo de norma)",
          v._sealed_entry("Decreto Ley 80", sello_corto) is None)
    # Quemada-gana sigue teniendo sentido: el banco laxo ve todo lo que el sello ve.
    check("toda cita que el sello acepta también la ve el banco de quemadas",
          all(v._is_burned(c, frozenset({"ley 80"}))
              for c in ("Ley 80 de 1993", "artículo 3 de la Ley 80")))

    print("2 · quemada GANA al sello")
    quemadas = [{"citation": CITA, "citation_norm": v._normalize(CITA), "reason": "falsa"}]
    _texto2, report2 = v.annotate_draft(BORRADOR, sealed=sellos, burned=quemadas)
    estados2 = {e["cita"]: e["estado"] for e in report2["detalle"]}
    quemada_ok = any((k in CITA or CITA in k) and s == "quemada" for k, s in estados2.items())
    check("la cita quemada+sellada sale QUEMADA", quemada_ok, str(estados2))
    check("y selladas=0", (report2.get("selladas") or 0) == 0, str(report2.get("selladas")))

    print("5 · condición de salto del gate (la del nodo, sobre el informe)")
    _t3, r3 = v.annotate_draft(f"Conforme a la {CITA}, procede.", sealed=sellos)
    citas = int(r3.get("citas") or 0)
    pendientes = citas - int(r3.get("selladas") or 0)
    sin_avisos = not any((r3.get("marcadas"), r3.get("anotadas"), r3.get("omitidas"),
                          r3.get("quemadas")))
    check("todo sellado y sin avisos → el gate no tiene nada que auditar",
          citas > 0 and pendientes <= 0 and sin_avisos, str(r3))
    _t4, r4 = v.annotate_draft(BORRADOR, sealed=sellos)
    pendientes4 = int(r4.get("citas") or 0) - int(r4.get("selladas") or 0)
    check("con una cita nueva, el gate SÍ audita (mutación)", pendientes4 > 0, str(r4))


async def parte_db() -> None:
    import psycopg

    from mia.db import pool
    from mia.memory import burned_citations, citation_seals

    PG = dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
              dbname=os.getenv("PG_DB", "mia"), user="postgres",
              password=os.getenv("PG_PASSWORD", ""))
    t1, t2 = str(uuid.uuid4()), str(uuid.uuid4())
    with psycopg.connect(autocommit=True, **PG) as c:
        for t in (t1, t2):
            c.execute("INSERT INTO tenants (id, name) VALUES (%s, %s)",
                      (t, f"test-sellos-{t[:8]}"))
    await pool.open_pool()
    try:
        print("3 · DB: sellar desde un informe aprobado (RLS real)")
        # Contrato hash-bound (053): sin source_passage_hash + artifact_hash de 64 hex
        # y jurisdicciones, NO nace sello (fail-closed) — se prueba primero la negativa.
        passage_hash = "a" * 64
        artifact_hash = "b" * 64
        report = {"detalle": [
            {"cita": CITA, "estado": "respaldada",
             "fuente": {"tipo": "corpus", "referencia": "N-TEST-001", "titulo": "Ficha",
                        "source_passage_hash": passage_hash}},
            {"cita": OTRA, "estado": "anotada"},
        ]}
        sin_huella = {"detalle": [
            {"cita": CITA, "estado": "respaldada",
             "fuente": {"tipo": "corpus", "referencia": "N-TEST-001", "titulo": "Ficha"}},
        ]}
        n0 = await citation_seals.seal_from_approved_report(
            t1, sin_huella, trace_id="tr-0", artifact_hash=artifact_hash,
            jurisdictions=["generic"])
        check("sin huella de pasaje NO nace sello (fail-closed 053)", n0 == 0, str(n0))
        n = await citation_seals.seal_from_approved_report(
            t1, report, trace_id="tr-1", artifact_hash=artifact_hash,
            jurisdictions=["generic"])
        check("sella exactamente las respaldadas", n == 1, str(n))
        citation_seals.invalidate(t1)
        sellos = await citation_seals.list_seals(t1)
        check("el sello quedó en la DB con su fuente",
              len(sellos) == 1 and sellos[0]["fuente_ref"] == "N-TEST-001", str(sellos))
        n2 = await citation_seals.seal_from_approved_report(
            t1, report, trace_id="tr-2", artifact_hash=artifact_hash,
            jurisdictions=["generic"])
        citation_seals.invalidate(t1)
        check("re-sellar es idempotente (sigue habiendo 1)",
              len(await citation_seals.list_seals(t1)) == 1, str(n2))
        citation_seals.invalidate(t2)
        check("el sello NO se ve desde otro despacho (RLS)",
              await citation_seals.list_seals(t2) == [])

        print("4 · revocación: quemar borra el sello")
        await burned_citations.burn(t1, CITA_CON_COMPLEMENTO, reason="demostrada falsa")
        citation_seals.invalidate(t1)
        check("quemar (aun con complementos) revocó el sello",
              await citation_seals.list_seals(t1) == [])
    finally:
        await pool.close_pool()
        with psycopg.connect(autocommit=True, **PG) as c:
            for t in (t1, t2):
                c.execute("DELETE FROM tenants WHERE id = %s", (t,))


def main() -> int:
    # Gotcha permanente de esta máquina: psycopg async no corre sobre el ProactorEventLoop
    # de Windows (mismo arreglo que el resto de suites con DB).
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    parte_pura()
    asyncio.run(parte_db())
    ok = TOTAL - len(FALLOS)
    print(f"\nRESULT: {ok}/{TOTAL} checks PASS")
    if FALLOS:
        print("sello de verificación FALLA:", ", ".join(FALLOS))
        return 1
    print("sello OK — lo aprobado no se re-audita; lo quemado no revive; lo nuevo se audita siempre.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
