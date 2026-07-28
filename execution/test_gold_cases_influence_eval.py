"""
Mia · test_gold_cases_influence_eval.py — gate de META C (Banco de oro conectado al examen).

Hoy `load_tenant_gold_cases()` (eval/cases.py) tenía 0 llamadores: el abogado confirmaba casos
de oro pero `run_suite` (harness.py) solo corría los 3 casos SINTÉTICOS canónicos. Este gate
prueba que `run_full_suite` (harness.py) y el endpoint `POST /api/gold-cases:evaluate`
(routes/gold_cases.py) de verdad conectan el Banco de oro confirmado al examen.

Cubre:
  DB directa (sin HTTP), grafo real con LLM/embeddings stubbeados:
    (a) una fila `gold_cases` status='confirmed' → `run_full_suite` la corre ADEMÁS de los 3
        casos sintéticos canónicos (n==4) y el `case_id` del confirmado aparece en el reporte;
    (b) una fila status='draft' → NO aparece en el reporte (solo los CONFIRMADOS entran).

  HTTP (`POST /api/gold-cases:evaluate`):
    (c) sin `allow_eval_real_data` → 403 en llano (mismo candado que `:draft`);
    (d) con el flag concedido → 200 y el reporte trae el caso confirmado.

Requiere PostgreSQL encendido (el harness siembra asuntos bajo RLS). Si la DB no responde,
este gate se reporta como bloqueo de entorno, no como verde inventado.

    .venv\\Scripts\\python.exe execution\\test_gold_cases_influence_eval.py
"""
from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv
from psycopg.types.json import Json

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from mia import config, embeddings                        # noqa: E402
from mia.agent import llm                                 # noqa: E402
from mia.agent.prompt_builder import (                    # noqa: E402
    DIAGNOSIS_CLOSING_FOOTER,
    DIAGNOSIS_CLOSING_HEADER,
)
from mia.agents.state import thread_id_for                # noqa: E402
from mia.db import pool                                   # noqa: E402
from mia.eval import cases, harness                       # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""),
)

_CLOSING = (f"{DIAGNOSIS_CLOSING_HEADER}\nProblema jurídico: la caducidad de la acción.\n"
            f"Normas y fuentes: Ley 1437 de 2011 [VERIFICAR]\n"
            f"Riesgo y recomendación: proponer la excepción.\n{DIAGNOSIS_CLOSING_FOOTER}")


# ── mocks (sin red) — el grafo real con LLM/embeddings stubbeados ─────────────
def _fake_embed(texts):
    return [[0.0] * config.EMBED_DIM for _ in texts]


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    sysmsg = messages[0]["content"] if messages and isinstance(messages[0], dict) else ""
    if "BORRADOR" in sysmsg or "Redacta el borrador" in sysmsg:
        content = ("BORRADOR: contestación de la demanda. Con fundamento en la Ley 1437 de 2011 "
                   "y en reiterada jurisprudencia, se propone la excepción de caducidad. " * 6)
    elif "CRUCE" in sysmsg or "diagnóstico" in sysmsg.lower():
        content = "DIAGNÓSTICO: el eje es la caducidad.\n\n" + _CLOSING
    else:
        content = "Análisis del especialista para el turno de prueba."
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
        usage=SimpleNamespace(prompt_tokens=12, completion_tokens=20, total_tokens=32),
    )


# ── helpers de DB (siembra directa, sin pasar por :draft) ─────────────────────
def _make_tenant(name: str = "[eval] test meta-c") -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (name,)).fetchone()[0])


def _set_eval_flag(tenant_id: str, value: bool) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute(
            "INSERT INTO tenant_settings (tenant_id, config) "
            "VALUES (%s::uuid, jsonb_build_object('eval', jsonb_build_object('allow_eval_real_data', %s::bool))) "
            "ON CONFLICT (tenant_id) DO UPDATE SET config = "
            "  jsonb_set(COALESCE(tenant_settings.config,'{}'::jsonb), '{eval}', "
            "  jsonb_build_object('allow_eval_real_data', %s::bool), true)",
            (tenant_id, value, value))


def _insert_gold_case(tenant_id: str, *, status: str, title: str) -> str:
    """Siembra una fila `gold_cases` YA anonimizada (como si el abogado ya la hubiera guardado y,
    en su caso, confirmado). `synthetic=True` en la tabla es solo metadato de auditoría; lo que
    importa para el candado del harness es que `_rows_to_cases` hidrata TODO gold_case como
    `GoldenCase(synthetic=True)`."""
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO gold_cases(tenant_id, title, message, documents, gold_answer, rubric, "
            "status, synthetic) VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, true) RETURNING id",
            (tenant_id, title,
             "Analiza si operó la caducidad de la acción y prepara la defensa de la entidad.",
             Json([{"filename": "demanda.txt",
                   "chunks": ["El daño se consolidó el 3 de marzo de 2019 y la demanda se "
                              "presentó el 10 de septiembre de 2021."]}]),
             "Operó la caducidad conforme a la Ley 1437 de 2011.",
             Json({"citas_clave": ["Ley 1437 de 2011"], "conclusiones_clave": []}),
             status),
        ).fetchone()[0])


def _drop_tenant(tenant_id: str, matter_ids: list[str]) -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        for mid in matter_ids:
            tid = thread_id_for(tenant_id, mid)
            for t in ("checkpoint_writes", "checkpoint_blobs", "checkpoints"):
                try:
                    c.execute(f"DELETE FROM {t} WHERE thread_id=%s", (tid,))
                except Exception:
                    pass
        c.execute("DELETE FROM tenants WHERE id=%s", (tenant_id,))


# ── (a) + (b): run_full_suite directo, sin HTTP ───────────────────────────────
async def db_checks() -> None:
    print("\n-- db: run_full_suite conecta el Banco de oro confirmado al examen --")
    await pool.open_pool()
    tenant = _make_tenant()
    matter_ids: list[str] = []
    try:
        gid_confirmed = _insert_gold_case(tenant, status="confirmed", title="Caso confirmado")
        gid_draft = _insert_gold_case(tenant, status="draft", title="Caso aún en borrador")

        report = await harness.run_full_suite(tenant, run_id="test_meta_c")
        matter_ids = [str(c["matter_id"]) for c in report["cases"] if c.get("matter_id")]

        case_ids = {c["case_id"] for c in report["cases"]}
        # El número de casos sintéticos se DERIVA del banco, no se cablea: desde la decisión
        # #47.1 los casos de RIESGO entran por defecto (3 → 9) y un test que fijara "4" se
        # rompería con cada caso nuevo. Lo que esta barrera cuida es la relación —el confirmado
        # se SUMA al examen canónico—, no una constante.
        n_sinteticos = len(cases.load_golden_cases())
        check(f"run_full_suite: corre los {n_sinteticos} sintéticos + el confirmado "
              f"(n=={n_sinteticos + 1})",
              report["summary"]["n_casos"] == n_sinteticos + 1)
        check("run_full_suite: el caso CONFIRMADO aparece en el reporte",
              gid_confirmed in case_ids)
        check("run_full_suite: el caso DRAFT (sin confirmar) NO aparece en el reporte",
              gid_draft not in case_ids)

        confirmed_result = next(c for c in report["cases"] if c["case_id"] == gid_confirmed)
        check("run_full_suite: el caso confirmado llegó a borrador",
              confirmed_result.get("reached_draft") is True)
        check("run_full_suite: el caso confirmado trae calificación sustantiva (rúbrica no vacía)",
              "substantive" in confirmed_result)
    finally:
        await pool.close_pool()
        _drop_tenant(tenant, matter_ids)


# ── (c) + (d): HTTP POST /api/gold-cases:evaluate ─────────────────────────────
def http_checks() -> None:
    print("\n-- http: POST /api/gold-cases:evaluate respeta el candado y devuelve el reporte --")
    import jwt
    from fastapi.testclient import TestClient

    from mia.api.main import app

    tenant = _make_tenant("[eval] test meta-c http")
    matter_ids: list[str] = []
    try:
        gid = _insert_gold_case(tenant, status="confirmed", title="Caso confirmado http")
        token = jwt.encode({"tenant_id": tenant}, config.JWT_SECRET, algorithm=config.JWT_ALG)
        auth = {"Authorization": f"Bearer {token}"}

        with TestClient(app) as client:
            r = client.post("/api/gold-cases:evaluate", headers=auth)
            det = (r.json() or {}).get("detail", "")
            check(":evaluate sin autorización → 403", r.status_code == 403)
            check(":evaluate: el 403 habla en llano (mismo candado que :draft)",
                  isinstance(det, str) and "datos reales" in det and "Configuración" in det)

            r = client.put("/settings/eval-consent", headers=auth, json={"permitido": True})
            check("(preparación) PUT eval-consent concede la autorización", r.status_code == 200)

            r = client.post("/api/gold-cases:evaluate", headers=auth)
            check(":evaluate con autorización → 200", r.status_code == 200)
            report = r.json() or {}
            matter_ids = [str(c["matter_id"]) for c in report.get("cases", []) if c.get("matter_id")]
            case_ids = {c.get("case_id") for c in report.get("cases", [])}
            n_sinteticos = len(cases.load_golden_cases())
            check(f":evaluate: el reporte trae {n_sinteticos + 1} casos ({n_sinteticos} "
                  f"sintéticos + 1 confirmado)",
                  report.get("summary", {}).get("n_casos") == n_sinteticos + 1)
            check(":evaluate: el reporte incluye el caso confirmado del despacho", gid in case_ids)
    finally:
        _drop_tenant(tenant, matter_ids)


def main() -> int:
    if not os.getenv("PG_PASSWORD") or not config.JWT_SECRET:
        print("  [FAIL] PG_PASSWORD o JWT_SECRET vacío en .env")
        return 1
    try:
        with psycopg.connect(autocommit=True, connect_timeout=3, **PG):
            pass
    except Exception as e:  # noqa: BLE001
        print(f"  [BLOQUEO DE ENTORNO] DB no disponible ({type(e).__name__}): "
              "este gate es DB+HTTP, no se puede correr sin PostgreSQL encendido.")
        return 1

    embeddings.embed_texts = _fake_embed
    llm.call_llm = _fake_call_llm

    asyncio.run(db_checks())
    http_checks()

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Banco de oro conectado al examen OK — META C verificada.")
        return 0
    print("META C FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
