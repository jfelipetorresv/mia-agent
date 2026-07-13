"""
Mia · test_gold_cases.py — gate del Banco de oro (gold-set de calidad por-despacho · Fase 1).

Cubre:
  OFFLINE (sin Ollama, sin nube, sin DB — el NER local y el juez van MOCKEADOS):
    (1) ANONIMIZACIÓN: corpus con PII conocida (cédula, NIT, radicado de 23 dígitos, email,
        teléfono, cuenta, URL + nombres/empresas/direcciones vía NER mockeado) → 0 fugas tras las
        dos pasadas + verificación; idempotencia (re-anonimizar no cambia nada); consistencia de
        marcadores (misma entidad → mismo marcador); el mapa en claro NO se persiste (solo su hash);
        degradación limpia cuando el NER local no está disponible.
    (2) substantive_score DETERMINISTA con rúbrica fija (cobertura de citas/conclusiones clave,
        flags, ok) + juez MOCKEADO (advisory, no altera pasa/no-pasa); compare detecta la regresión
        sustantiva (perder una clave que antes se tenía).
    (4) CANDADO de consentimiento (reuso del `allow_eval_real_data`): sin autorización → error.

  DB (requiere PostgreSQL; si está apagado se DECLARA omitido, no cuenta como fallo):
    (3) RLS de `gold_cases`: `mia_app` bajo GUC de un tenant no ve ni toca los casos de otro.

Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_gold_cases.py
"""
from __future__ import annotations
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia.security import anonymize                          # noqa: E402
from mia.eval.scoring import (                              # noqa: E402
    substantive_score, FLAG_MISSING_KEY_CITATION, FLAG_MISSING_KEY_CONCLUSION,
)
from mia.eval.compare import compare_reports               # noqa: E402
from mia.eval.cases import _rows_to_cases                  # noqa: E402
from mia.api.routes.gold_cases import (                     # noqa: E402
    _consent_guard, _propose_rubric, _safe_title, _draft_aviso, TitleWithPII,
)
from mia.eval.harness import EvalConsentError              # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


# ── NER local MOCKEADO (sin Ollama): devuelve las entidades conocidas del corpus ──────────────
_KNOWN_PERSONAS = ["Juan Pérez Gómez", "María Fernanda Ruiz"]
_KNOWN_EMPRESAS = ["Constructora Andina S.A.S."]
_KNOWN_DIRECCIONES = ["Calle 100 No. 15-20"]


def _fake_ner_llm(messages, *, task=None, model=None, temperature=None, **kw):
    # El módulo DEBE pedir el modelo local — si pidiera nube, esto lo delataría.
    assert model == "mia-local", f"el NER debe correr LOCAL, pidió: {model!r}"
    text = messages[-1]["content"]
    data = {
        "personas": [p for p in _KNOWN_PERSONAS if p in text],
        "empresas": [e for e in _KNOWN_EMPRESAS if e in text],
        "direcciones": [d for d in _KNOWN_DIRECCIONES if d in text],
    }
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data, ensure_ascii=False)))])


def _failing_llm(messages, **kw):
    raise RuntimeError("Ollama no disponible (simulado)")


# ── (1) ANONIMIZACIÓN ─────────────────────────────────────────────────────────
_CORPUS_MESSAGE = (
    "El demandante Juan Pérez Gómez, identificado con C.C. 79.484.321, y la sociedad "
    "Constructora Andina S.A.S. (NIT 900.123.456-7) presentaron la demanda con radicado "
    "11001310300320180012300. Contacto: juan.perez@example.com, teléfono +57 310 555 1234. "
    "Notificaciones en la Calle 100 No. 15-20. Consignar en la cuenta de ahorros 1234567890. "
    "Más datos en https://ejemplo.com/expediente."
)
_CORPUS_DOC = {
    "filename": "poder.pdf",
    "chunks": [
        "María Fernanda Ruiz otorga poder. Su cédula 52.111.222 consta en el documento.",
        "El hecho ocurrió el 3 de marzo de 2019 (fecha que se CONSERVA por relevancia procesal).",
    ],
}
_CORPUS_ANSWER = (
    "Con fundamento en el artículo 90 de la Constitución Política y la Ley 1437 de 2011, se "
    "concluye que operó la caducidad de la acción presentada por Juan Pérez Gómez."
)


def anon_checks() -> None:
    print("\n-- (1) anonimización: 0 fugas, idempotencia, consistencia, degradación --")

    bundle = anonymize.anonymize_bundle(
        _CORPUS_MESSAGE, [_CORPUS_DOC], _CORPUS_ANSWER, llm=_fake_ner_llm)

    # 0 fugas de PII ESTRUCTURADA en todo el bundle.
    check("anon: 0 fugas estructuradas tras las 2 pasadas",
          len(bundle["spans_pii_restantes"]) == 0)
    check("anon: el NER local corrió (ner_ran=True)", bundle["ner_ran"] is True)

    blob = "\n".join([bundle["message"], bundle["gold_answer"]]
                     + [c for d in bundle["documents"] for c in d["chunks"]])
    # Los datos crudos NO deben aparecer.
    crudos = ["79.484.321", "900.123.456-7", "11001310300320180012300",
              "juan.perez@example.com", "310 555 1234", "Juan Pérez Gómez",
              "Constructora Andina", "Calle 100 No. 15-20", "52.111.222", "1234567890",
              "ejemplo.com"]
    check("anon: ningún dato crudo sobrevive en el texto anonimizado",
          not any(c in blob for c in crudos))
    check("anon: contains_pii sobre el resultado es False", anonymize.contains_pii(blob) is False)

    # Marcadores tipados presentes.
    check("anon: hay marcadores tipados (CEDULA/PERSONA/RADICADO)",
          "[[CEDULA_1]]" in blob and "[[PERSONA_1]]" in blob and "[[RADICADO_1]]" in blob)

    # Consistencia: la misma persona (Juan Pérez Gómez, en message y answer) → mismo marcador.
    persona_juan = None
    for marker, real in bundle["anon_map"].items():
        if real == "Juan Pérez Gómez":
            persona_juan = marker
    check("anon: consistencia — misma persona en 2 textos comparte marcador",
          persona_juan is not None
          and bundle["message"].count(persona_juan) >= 1
          and persona_juan in bundle["gold_answer"])

    # Fechas CONSERVADAS por defecto.
    check("anon: las fechas se conservan (3 de marzo de 2019)",
          "3 de marzo de 2019" in blob)

    # Idempotencia: re-anonimizar el texto ya anonimizado no cambia nada ni genera PII.
    again = anonymize.anonymize_text(bundle["message"], llm=_fake_ner_llm)
    check("anon: idempotencia — re-anonimizar no altera el texto",
          again.text == bundle["message"] and len(again.spans_pii_restantes) == 0)

    # El mapa en claro NO es persistible: solo su hash.
    check("anon: el hash del mapa es estable y con prefijo sha256",
          bundle["anon_map_hash"].startswith("sha256:")
          and bundle["anon_map_hash"] == anonymize.anon_map_hash(bundle["anon_map"]))
    check("anon: el hash NO revela ningún valor real del mapa",
          not any(real in bundle["anon_map_hash"] for real in bundle["anon_map"].values()))

    # Degradación limpia cuando el NER local no está: estructurados sí, nombres quedan + aviso.
    degr = anonymize.anonymize_text(_CORPUS_MESSAGE, llm=_failing_llm)
    check("anon: sin NER local → degrada (ner_ran=False) con aviso claro",
          degr.ner_ran is False and len(degr.warnings) >= 1)
    check("anon: aún sin NER, los estructurados SÍ se ocultaron",
          "79.484.321" not in degr.text and "juan.perez@example.com" not in degr.text)


# ── (2) substantive_score determinista + juez mockeado + compare ──────────────
_RUBRIC = {
    "citas_clave": ["artículo 90 de la Constitución Política", "Ley 1437 de 2011"],
    "conclusiones_clave": ["operó la caducidad de la acción"],
}


def _fake_judge(draft, diagnosis, rubric):
    # El juez ve SOLO el texto que se le pasa (anonimizado en producción) — aquí es un mock.
    return {"veredicto": "solido", "explicacion_llana": "La respuesta cubre las claves."}


def scoring_checks() -> None:
    print("\n-- (2) substantive_score determinista + juez advisory + compare --")

    draft_ok = ("Con fundamento en el artículo 90 de la Constitución Política y en la Ley 1437 "
                "de 2011, se concluye que operó la caducidad de la acción y se propone la excepción.")
    s_ok = substantive_score(draft_ok, "", _RUBRIC, judge=_fake_judge)
    check("score: respuesta completa → sin faltantes y ok=True",
          s_ok["ok"] is True and s_ok["n_faltantes_clave"] == 0)
    check("score: cobertura de citas y conclusiones = 1.0",
          s_ok["cobertura_citas"] == 1.0 and s_ok["cobertura_conclusiones"] == 1.0)
    check("score: el juez advisory adjunta veredicto sin alterar ok",
          s_ok["judge"]["veredicto"] == "solido")

    # Determinismo: dos corridas idénticas dan el mismo resultado (sin el juez).
    a = substantive_score(draft_ok, "", _RUBRIC)
    b = substantive_score(draft_ok, "", _RUBRIC)
    check("score: determinista (misma entrada → misma salida)",
          a["citas_cubiertas"] == b["citas_cubiertas"]
          and a["conclusiones_cubiertas"] == b["conclusiones_cubiertas"])

    draft_falta = "Solo menciono la Ley 1437 de 2011, sin más."
    s_falta = substantive_score(draft_falta, "", _RUBRIC)
    check("score: falta una cita clave → flag y no ok",
          FLAG_MISSING_KEY_CITATION in s_falta["flags"] and s_falta["ok"] is False)
    check("score: falta la conclusión clave → flag",
          FLAG_MISSING_KEY_CONCLUSION in s_falta["flags"])

    # Juez que falla NO tumba la calificación dura (advisory).
    def _bad_judge(*a, **k):
        raise RuntimeError("juez caído")
    s_j = substantive_score(draft_ok, "", _RUBRIC, judge=_bad_judge)
    check("score: un juez caído no altera pasa/no-pasa (ok sigue True)", s_j["ok"] is True)

    # compare: perder una clave que antes se tenía → regresión sustantiva (fail-safe).
    before = {"cases": [{"case_id": "g1", "score": {"reached_draft": True, "draft_chars": 500,
                                                    "has_diagnosis_closing": True},
                         "substantive": s_ok}]}
    after = {"cases": [{"case_id": "g1", "score": {"reached_draft": True, "draft_chars": 500,
                                                   "has_diagnosis_closing": True},
                        "substantive": s_falta}]}
    cmp = compare_reports(before, after)
    check("compare: perder cobertura de una clave → regresión",
          cmp["overall"] == "regresion" and cmp["n_regresiones"] == 1)

    # proponer rúbrica desde material anonimizado (citas del borrador + conclusiones del cierre).
    prop = _propose_rubric(draft_ok, "")
    check("propose_rubric: extrae las citas clave del borrador",
          any("1437" in c for c in prop["citas_clave"])
          and any("90" in c for c in prop["citas_clave"]))

    # loader puro: filas → GoldenCase con rúbrica.
    casos = _rows_to_cases([("id-1", "Caso", "mensaje", [{"filename": "d.txt", "chunks": ["c"]}],
                             "respuesta", _RUBRIC)])
    check("loader: hidrata GoldenCase con rúbrica y documentos, marcado sintético",
          len(casos) == 1 and casos[0].rubric == _RUBRIC and casos[0].synthetic is True
          and casos[0].documents[0].filename == "d.txt")


# ── (4) candado de consentimiento ─────────────────────────────────────────────
def consent_checks() -> None:
    print("\n-- (4) candado de consentimiento (reuso allow_eval_real_data) --")
    blocked = False
    try:
        _consent_guard(False)
    except EvalConsentError:
        blocked = True
    check("candado: sin autorización de datos reales → EvalConsentError", blocked)
    ok = True
    try:
        _consent_guard(True)
    except EvalConsentError:
        ok = False
    check("candado: con autorización → deja continuar", ok)


# ── (5) grietas de fuga de PII que el gate NO cubría (revisión adversarial) ────
def _partial_ner_llm(messages, *, task=None, model=None, temperature=None, **kw):
    """NER que devuelve SOLO 1 de varias entidades (fuga parcial silenciosa)."""
    assert model == "mia-local", f"el NER debe correr LOCAL, pidió: {model!r}"
    text = messages[-1]["content"]
    data = {  # reconoce a Juan; OMITE la empresa, la dirección y a María Fernanda.
        "personas": [p for p in ["Juan Pérez Gómez"] if p in text],
        "empresas": [], "direcciones": [],
    }
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(data, ensure_ascii=False)))])


def pii_gate_checks() -> None:
    print("\n-- (5) grietas de fuga de PII (NER parcial, teléfono, título, número pelado) --")

    # (5.1) NER PARCIAL: 1 de varias entidades → sospecha para las omitidas + aviso cauteloso.
    r = anonymize.anonymize_text(_CORPUS_MESSAGE, llm=_partial_ner_llm)
    tipos = {str(s["tipo"]) for s in r.spans_pii_restantes}
    check("ner parcial: NER corrió pero omitió entidades (ner_ran=True)", r.ner_ran is True)
    check("ner parcial: marca spans de SOSPECHA para lo omitido (empresa/dirección)",
          any(t.startswith("sospecha") for t in tipos))
    aviso = _draft_aviso(r.ner_ran, r.spans_pii_restantes)
    check("ner parcial: el aviso es CAUTELOSO, no 'todo limpio'",
          "con cuidado" in aviso.lower() and "limpio" not in aviso.lower().split("cuidado")[0])
    # Juan (el que SÍ reconoció el NER) quedó enmascarado; la empresa cruda sigue viva → por eso alerta.
    check("ner parcial: la entidad reconocida se ocultó pero la omitida sobrevive cruda",
          "Juan Pérez Gómez" not in r.text and "Constructora Andina" in r.text)

    # (5.2) TELÉFONO con () y agrupación 2-2 → oculto / contains_pii=True.
    for tel in ["(315)5551234", "+57 300 555 12 34"]:
        rr = anonymize.anonymize_text(f"Comunicarse al {tel} en horario laboral.", run_ner=False)
        check(f"tel: '{tel}' queda OCULTO y sin PII residual",
              tel not in rr.text and anonymize.contains_pii(rr.text) is False)
        check(f"tel: contains_pii detecta '{tel}' en crudo",
              anonymize.contains_pii(f"tel {tel} fin") is True)

    # (5.3) FUGA POR TÍTULO: defecto sale del mensaje ANONIMIZADO; título explícito con PII se rechaza.
    anon_msg = anonymize.anonymize_bundle(_CORPUS_MESSAGE, [], "", llm=_fake_ner_llm)["message"]
    t_def = _safe_title(None, anon_msg)
    check("titulo: el defecto NO contiene PII estructurada ni datos crudos",
          not anonymize.contains_pii(t_def)
          and "79.484.321" not in t_def and "juan.perez@example.com" not in t_def)
    rechazado = False
    try:
        _safe_title("Caso de Juan, C.C. 79.484.321", anon_msg)
    except TitleWithPII:
        rechazado = True
    check("titulo: título explícito con PII → rechazado (TitleWithPII)", rechazado)
    check("titulo: título explícito limpio → se conserva",
          _safe_title("Caducidad en acción de reparación", anon_msg)
          == "Caducidad en acción de reparación")

    # (5.4) REVERSIÓN pelado↔valor mapeado: cédula con puntos + la misma pelada → mismo marcador.
    txt = "La cédula 79.484.321 aparece; más abajo el número 79484321 se repite como cuantía."
    rp = anonymize.anonymize_text(txt, run_ner=False)
    check("reid: la cédula con puntos se enmascaró", "79.484.321" not in rp.text)
    check("reid: la MISMA pelada 79484321 quedó con el MISMO marcador ([[CEDULA_1]] x2)",
          "79484321" not in rp.text and rp.text.count("[[CEDULA_1]]") == 2)


# ── (3) RLS de gold_cases (requiere DB) ───────────────────────────────────────
def _pg(user: str, password: str) -> dict:
    return dict(host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
                dbname=os.getenv("PG_DB", "mia"), user=user, password=password)


def rls_checks() -> bool:
    """Devuelve True si corrió (DB disponible), False si se omitió por falta de DB."""
    print("\n-- (3) RLS de gold_cases (requiere DB) --")
    super_pw = os.getenv("PG_PASSWORD", "")
    app_pw = os.getenv("PG_APP_PASSWORD", "")
    try:
        conn = psycopg.connect(autocommit=True, connect_timeout=3, **_pg("postgres", super_pw))
    except Exception as e:  # noqa: BLE001 — DB apagada: se OMITE, no es fallo del código
        print(f"  [SKIP] DB no disponible ({type(e).__name__}); RLS de gold_cases no verificada.")
        return False

    ids = {}
    try:
        with conn:
            conn.execute("DELETE FROM tenants WHERE name IN ('GC_RLS_A','GC_RLS_B')")
            a = conn.execute("INSERT INTO tenants(name) VALUES('GC_RLS_A') RETURNING id").fetchone()[0]
            b = conn.execute("INSERT INTO tenants(name) VALUES('GC_RLS_B') RETURNING id").fetchone()[0]
            ga = conn.execute(
                "INSERT INTO gold_cases(tenant_id,title,message,gold_answer,status) "
                "VALUES(%s,'A','msg A','ans A','confirmed') RETURNING id", (a,)).fetchone()[0]
            gb = conn.execute(
                "INSERT INTO gold_cases(tenant_id,title,message,gold_answer,status) "
                "VALUES(%s,'B','msg B','ans B','confirmed') RETURNING id", (b,)).fetchone()[0]
            ids = {"a": a, "b": b, "ga": ga, "gb": gb}

        with psycopg.connect(**_pg("mia_app", app_pw)) as app:
            with app.transaction(force_rollback=True):
                n = app.execute("SELECT count(*) FROM gold_cases").fetchone()[0]
                check("rls: sin GUC (fail-closed) no ve ningún caso de oro", n == 0)
            with app.transaction(force_rollback=True):
                app.execute("SELECT set_config('app.tenant_id', %s, true)", (str(ids["a"]),))
                check("rls: A ve exactamente sus casos (count==1)",
                      app.execute("SELECT count(*) FROM gold_cases").fetchone()[0] == 1)
                check("rls: A no ve el caso de B por id (0)",
                      app.execute("SELECT count(*) FROM gold_cases WHERE id=%s",
                                  (ids["gb"],)).fetchone()[0] == 0)
                check("rls: DELETE del caso de B afecta 0 filas",
                      app.execute("DELETE FROM gold_cases WHERE id=%s", (ids["gb"],)).rowcount == 0)
                violated = False
                try:
                    with app.transaction():
                        app.execute(
                            "INSERT INTO gold_cases(tenant_id,title,message) VALUES(%s,'intruso','x')",
                            (ids["b"],))
                except psycopg.Error:
                    violated = True
                check("rls: INSERT con tenant_id=B bajo GUC=A es rechazado (WITH CHECK)", violated)
    finally:
        try:
            with psycopg.connect(autocommit=True, **_pg("postgres", super_pw)) as c:
                c.execute("DELETE FROM tenants WHERE name IN ('GC_RLS_A','GC_RLS_B')")
        except Exception:
            pass
    return True


def main() -> int:
    anon_checks()
    scoring_checks()
    consent_checks()
    pii_gate_checks()
    db_ran = rls_checks()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS" + ("" if db_ran else "  (RLS OMITIDO: DB apagada)"))
    if passed == total:
        print("Banco de oro OK — Fase 1 verificada"
              + ("." if db_ran else " en su parte offline (falta correr RLS con DB encendida)."))
        return 0
    print("Banco de oro FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
