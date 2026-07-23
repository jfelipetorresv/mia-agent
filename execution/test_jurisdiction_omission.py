# -*- coding: utf-8 -*-
"""
Mia · test_jurisdiction_omission.py — gate del endurecimiento F2: bajo jurisdicción
DESCONOCIDA, ninguna cita sin respaldo se emite — se OMITE del texto (control
determinista), no se deja pasar con una marca que el prompt ya demostró no bastar
(F1 midió 40% de fuga en el caso de citas con la sola instrucción al modelo).

Cubre:
  P · retrocompatibilidad: con omit_unbacked=False (default), annotate_draft es
      idéntico byte a byte al comportamiento clásico (marca, no omite; informe sin
      la clave nueva).
  O · mecánica de la omisión: sin respaldo → span sustituido por OMIT_MARK y estado
      "omitida" en el informe; respaldo por corpus o por ancla → intacta; una marca
      [VERIFICAR] del modelo no autoriza nada; el guardián de [doc n] fantasma sigue
      corriendo después.
  C · cableado real vía graph._verify_draft: jurisdictions=["generic"] o ausente →
      omite (fail-safe); jurisdicción configurada → comportamiento clásico INTACTO;
      report_key separa el informe del diagnóstico del informe del borrador.
  M · mutación: el mismo texto SIN el modo omisión conserva la cita — el aserto de
      este gate discrimina de verdad (no está verde por accidente).

Sin DB obligatoria (fail-soft de citation_patterns_for) y sin LLM.
Salida: exit 0 = PASS · exit 1 = FAIL.
    .venv\\Scripts\\python.exe execution\\test_jurisdiction_omission.py
"""
from __future__ import annotations
import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.agents import verification  # noqa: E402
from mia.agents.graph import MatterGraphBuilder  # noqa: E402

OK = "  [OK]  "
FAIL = "  [FAIL]"
failures: list[str] = []


def check(cond: bool, label: str) -> None:
    print(f"{OK if cond else FAIL} {label}")
    if not cond:
        failures.append(label)


# Una cita que el escáner base detecta (cuerpo normativo + número) y un texto anfitrión.
CITA = "Ley 100 de 1993"
TEXTO = f"El régimen aplicable surge de la {CITA}, como se explicó arriba."
FUENTE_RESPALDO = [{"tipo": "norma", "referencia": CITA, "titulo": "Norma de prueba",
                    "texto": f"Texto íntegro de la {CITA} para el cotejo."}]

print("== P · retrocompatibilidad (omit_unbacked=False es el clásico byte a byte) ==")

t_default, r_default = verification.annotate_draft(TEXTO)
t_false, r_false = verification.annotate_draft(TEXTO, omit_unbacked=False)
check(t_default == t_false and r_default == r_false,
      "p1 · default y omit_unbacked=False producen exactamente lo mismo")
check(CITA in t_default and verification.VERIFY_MARK in t_default,
      "p2 · clásico: la cita sin respaldo se conserva y se MARCA (no se omite)")
check("omitidas" not in r_default,
      "p3 · clásico: el informe no gana claves nuevas (retrocompatible)")

print("== O · mecánica de la omisión (omit_unbacked=True) ==")

t1, r1 = verification.annotate_draft(TEXTO, omit_unbacked=True)
check(CITA not in t1, "o1 · la cita sin respaldo DESAPARECE del texto emitido")
check(verification.OMIT_MARK in t1, "o2 · en su lugar queda la marca de omisión visible")
check(r1.get("omitidas") == 1 and r1.get("anotadas") == 0,
      "o3 · informe: omitidas=1, anotadas=0 (nada queda 'anotado' bajo omisión)")
check(any(d.get("estado") == "omitida" and CITA in d.get("cita", "")
          for d in r1.get("detalle", [])),
      "o4 · el texto original de la cita queda en el informe (trazabilidad)")

t2, r2 = verification.annotate_draft(TEXTO, sources=FUENTE_RESPALDO, omit_unbacked=True)
check(CITA in t2 and r2.get("respaldadas") == 1 and r2.get("omitidas") == 0,
      "o5 · cita respaldada por el corpus del turno: intacta (no se omite)")

texto_ancla = f"Como indica la {CITA} [doc 1], el plazo corre."
# El contenido termina la cita con puntuación: el cotejo por piezas rechaza (a propósito)
# un documento que CONTINÚE el identificador ("Ley 100 de 1993 bis").
docs_ancla = [{"filename": "memo.txt", "content": f"El memo invoca la {CITA}."}]
t3, r3 = verification.annotate_draft(texto_ancla, documents=docs_ancla, omit_unbacked=True)
check(CITA in t3 and r3.get("respaldadas") == 1 and r3.get("omitidas") == 0,
      "o6 · cita anclada al expediente [doc n]: intacta (el input del abogado manda)")

texto_marcado = f"La {CITA} {verification.VERIFY_MARK} regula la materia."
t4, r4 = verification.annotate_draft(texto_marcado, omit_unbacked=True)
check(CITA not in t4 and r4.get("omitidas") == 1,
      "o7 · una marca [VERIFICAR] del modelo NO autoriza la cita: también se omite")

t5, r5 = verification.annotate_draft(texto_marcado, sources=FUENTE_RESPALDO,
                                     omit_unbacked=True)
check(CITA in t5 and r5.get("respaldadas") == 1 and r5.get("omitidas") == 0,
      "o8 · marcada PERO con respaldo real: se conserva como respaldada")

texto_mixto = (f"Primero, la {CITA} regula la materia. "
               f"Segundo, el Decreto 999 de 2001 no aparece en fuente alguna. "
               f"El resto del párrafo debe quedar intacto.")
t6, r6 = verification.annotate_draft(texto_mixto, sources=FUENTE_RESPALDO,
                                     omit_unbacked=True)
check(CITA in t6 and "Decreto 999" not in t6
      and "El resto del párrafo debe quedar intacto." in t6,
      "o9 · mixto: solo la cita sin respaldo desaparece; el texto vecino queda intacto")
check(r6.get("respaldadas") == 1 and r6.get("omitidas") == 1,
      "o10 · informe del mixto: 1 respaldada + 1 omitida")

texto_fantasma = f"La {CITA} aplica según [doc 9]."
t7, r7 = verification.annotate_draft(texto_fantasma, num_documents=1, omit_unbacked=True)
check("docs_fantasma" in r7 and "[doc 9]" in t7 and verification.VERIFY_MARK in t7,
      "o11 · el guardián de [doc n] fantasma sigue corriendo tras la omisión")

print("== C · cableado real vía graph._verify_draft ==")


def _verify(jurisdictions, text, report_key="verification"):
    state = {"tenant_id": "00000000-0000-0000-0000-000000000000",
             "jurisdictions": jurisdictions, "documents": [], "messages": []}
    md: dict = {}
    out = asyncio.run(MatterGraphBuilder._verify_draft(
        SimpleNamespace(), state, md, text, report_key=report_key))
    return out, md


out_gen, md_gen = _verify(["generic"], TEXTO)
check(CITA not in out_gen and verification.OMIT_MARK in out_gen,
      "c1 · jurisdictions=['generic'] → la cita sin respaldo se OMITE")
out_none, _ = _verify(None, TEXTO)
check(CITA not in out_none,
      "c2 · sin dato de jurisdicción → fail-safe hacia desconocida (también omite)")
out_co, md_co = _verify(["co"], TEXTO)
check(CITA in out_co and verification.VERIFY_MARK in out_co,
      "c3 · jurisdicción configurada → comportamiento clásico INTACTO (marca, no omite)")
check("omitidas" not in (md_co.get("verification") or {}),
      "c4 · bajo configurada el informe tampoco cambia de forma")
_, md_diag = _verify(["generic"], TEXTO, report_key="verification_diagnosis")
check("verification_diagnosis" in md_diag and "verification" not in md_diag,
      "c5 · report_key separa el informe del diagnóstico del informe del borrador")

print("== M · mutación: el gate sabe reprobar ==")

t_mut, _ = verification.annotate_draft(TEXTO, omit_unbacked=False)
check(CITA in t_mut,
      "m1 · SIN el modo omisión la cita sobrevive — el aserto o1 discrimina de verdad")

print()
total = 3 + 11 + 5 + 1
if failures:
    print(f"{len(failures)}/{total} checks FAIL:")
    for f in failures:
        print(f"   - {f}")
    sys.exit(1)
print(f"{total}/{total} checks PASS")
print("omisión de citas bajo jurisdicción desconocida OK — la regla del prompt ya es control.")
