"""
Mia · test_feedback_processor.py — gate del Módulo 3e (Feedback processor · decisión #19).

Trazas sintéticas (v1 y v2) en un dir temporal bajo `.tmp/`; `call_llm(task="curator")`
mockeado. Verifica: migración (2 tablas) + RLS, carga de trazas (v1/v2, watermark, eventos
ignorados), detección de señales (rechazo, edición significativa/menor, sin-resultado), umbral
de 2 ocurrencias, tipos de propuesta (improve/new/flag_gap), persistencia + idempotencia por
watermark, aislamiento por tenant, y compatibilidad del formato 2d.

HALT: si este gate falla, NO se avanza (CLAUDE.md §G). Salida: exit 0 = PASS · exit 1 = FAIL.

    .venv\\Scripts\\python.exe execution\\test_feedback_processor.py
"""
from __future__ import annotations
import asyncio
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

import psycopg
from dotenv import load_dotenv

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")
sys.path.insert(0, str(ROOT / "backend"))
sys.path.insert(0, str(ROOT / "execution"))

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import init_feedback                                # noqa: E402  (runner migración 006)
from mia.agent import llm                           # noqa: E402
from mia.db import pool                             # noqa: E402
from mia.memory.feedback_processor import FeedbackProcessor  # noqa: E402
from mia.memory.trace_capture import (              # noqa: E402
    REQUIRED_FIELDS, TRACE_SCHEMA, TRACE_SCHEMA_V2, TraceCapture)
from mia.cron import build_scheduler                # noqa: E402

_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def _fake_call_llm(messages, *, task=None, model=None, **kw):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content="PROPUESTA_MOCK"))],
        usage=SimpleNamespace(prompt_tokens=5, completion_tokens=10, total_tokens=15))


llm.call_llm = _fake_call_llm

PG = dict(
    host=os.getenv("PG_HOST", "127.0.0.1"), port=os.getenv("PG_PORT", "5432"),
    dbname=os.getenv("PG_DB", "mia"), user="postgres", password=os.getenv("PG_PASSWORD", ""))


def make_tenant(label: str) -> str:
    with psycopg.connect(autocommit=True, **PG) as c:
        return str(c.execute(
            "INSERT INTO tenants(name) VALUES(%s) RETURNING id", (f"FEEDBACK_TEST {label}",)
        ).fetchone()[0])


def drop_test_tenants() -> None:
    with psycopg.connect(autocommit=True, **PG) as c:
        c.execute("DELETE FROM tenants WHERE name LIKE 'FEEDBACK_TEST%'")


def trace_dict(tid, *, outcome=None, orig=None, final=None, docs=None, playbooks=None) -> dict:
    return {"schema": TRACE_SCHEMA_V2, "trace_id": tid, "matter_id": "m",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "hitl_outcome": outcome, "draft_original": orig, "draft_final": final,
            "retrieved_doc_ids": docs, "activated_playbooks": playbooks}


async def count_proposals(tenant: str) -> int:
    async with pool.tenant_connection(tenant) as conn:
        return (await (await conn.execute(
            "SELECT count(*) FROM feedback_proposals")).fetchone())[0]


async def insert_playbook(tenant: str, title: str, *, protected: bool = False,
                          usage: int = 0) -> str:
    async with pool.tenant_connection(tenant) as conn:
        row = await (await conn.execute(
            "INSERT INTO playbooks (tenant_id, title, summary, applies_when, content, "
            "protected, usage_count) "
            "VALUES (%s::uuid, %s, 's', 'w', 'c', %s, %s) RETURNING id",
            (tenant, title, protected, usage))).fetchone()
    return str(row[0])


async def db_checks(fp: FeedbackProcessor, tc: TraceCapture, t: dict) -> None:
    await pool.open_pool()
    try:
        # === migración ===
        async with pool.connection() as conn:
            cols = {r[0] for r in await (await conn.execute(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_schema='public' AND table_name='feedback_proposals'")).fetchall()}
            wm = await (await conn.execute(
                "SELECT to_regclass('public.processed_traces_watermark')")).fetchone()
        check("migración: feedback_proposals existe con columnas",
              {"proposal_type", "target_playbook_id", "suggested_content", "status",
               "trace_ids"}.issubset(cols))
        check("migración: processed_traces_watermark existe", wm[0] is not None)

        # === RLS ===
        async with pool.tenant_connection(t["a"]) as conn:
            await conn.execute(
                "INSERT INTO feedback_proposals (tenant_id, proposal_type, suggested_content, "
                "rationale) VALUES (%s::uuid, 'flag_gap', 'x', 'y')", (t["a"],))
            await conn.execute(
                "INSERT INTO processed_traces_watermark (tenant_id, trace_date) "
                "VALUES (%s::uuid, '2020-01-01')", (t["a"],))
        async with pool.tenant_connection(t["b"]) as conn:
            pb = (await (await conn.execute("SELECT count(*) FROM feedback_proposals")).fetchone())[0]
            wb = (await (await conn.execute("SELECT count(*) FROM processed_traces_watermark")).fetchone())[0]
        check("RLS feedback_proposals: B no ve las de A", pb == 0)
        check("RLS processed_traces_watermark: B no ve las de A", wb == 0)

        # === load_traces: v2 + v1 + evento ignorado ===
        tc.capture(tenant_id=t["load"], matter_id="m1", input="i", output="o", model="m",
                   tokens=1, latency_ms=1.0, hitl_outcome="rejected", retrieved_doc_ids=["d1"])
        tc.capture(tenant_id=t["load"], matter_id="m2", input="i", output="o", model="m",
                   tokens=1, latency_ms=1.0, hitl_outcome="approved", retrieved_doc_ids=[])
        tc.capture(tenant_id=t["load"], matter_id="m3", input="i", output="o", model="m",
                   tokens=1, latency_ms=1.0)                       # v1 (sin campos HITL)
        tc.capture_event(tenant_id=t["load"], matter_id="m3", event_type="context_compressed",
                         ratio_compresion=0.4)                     # evento → debe ignorarse
        loaded = await fp.load_traces(t["load"])
        schemas = {r["schema"] for r in loaded}
        check("load_traces carga las trazas v2", any(r["schema"] == TRACE_SCHEMA_V2 for r in loaded))
        check("load_traces carga las trazas v1 (compatibilidad) e ignora eventos",
              TRACE_SCHEMA in schemas and len(loaded) == 3)

        # === load solo nuevas (watermark) ===
        tc.capture(tenant_id=t["solo"], matter_id="m1", input="i", output="o", model="m",
                   tokens=1, latency_ms=1.0, hitl_outcome="rejected", retrieved_doc_ids=["d1"])
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        async with pool.tenant_connection(t["solo"]) as conn:
            await conn.execute(
                "INSERT INTO processed_traces_watermark (tenant_id, trace_date) "
                "VALUES (%s::uuid, %s::date)", (t["solo"], today))
        check("load_traces no recarga trazas ya procesadas (watermark)",
              (await fp.load_traces(t["solo"])) == [])

        # === analyze (puro) ===
        rej = await fp.analyze([trace_dict("r1", outcome="rejected", docs=["d"]),
                                trace_dict("r2", outcome="rejected", docs=["d"])])
        check("analyze: hitl_outcome='rejected' -> HITL_REJECTION", rej["HITL_REJECTION"]["count"] == 2)

        sig = await fp.analyze([trace_dict("e1", outcome="edited", orig="A" * 100,
                                           final="B" * 100, docs=["d"])])
        check("analyze: diff > 20% -> HITL_EDIT", sig["HITL_EDIT"]["count"] == 1)

        minor = await fp.analyze([trace_dict("e2", outcome="edited", orig="A" * 100,
                                             final="A" * 96 + "B" * 4, docs=["d"])])
        check("analyze: diff < 20% -> NO cuenta como HITL_EDIT", minor["HITL_EDIT"]["count"] == 0)

        nores = await fp.analyze([trace_dict("n1", outcome="approved", docs=[])])
        check("analyze: retrieved_doc_ids=[] -> NO_RESULT", nores["NO_RESULT"]["count"] == 1)

        # === propose: umbral + tipos ===
        def analysis(signal, count):
            base = {"HITL_REJECTION": {"count": 0, "trace_ids": []},
                    "HITL_EDIT": {"count": 0, "trace_ids": []},
                    "NO_RESULT": {"count": 0, "trace_ids": []}}
            base[signal] = {"count": count, "trace_ids": [f"x{i}" for i in range(count)]}
            return base

        check("propose: 1 sola ocurrencia -> sin propuesta (umbral 2)",
              (await fp.propose(t["gap"], analysis("NO_RESULT", 1))) == [])

        await insert_playbook(t["improve"], "PB existente")
        imp = await fp.propose(t["improve"], analysis("HITL_REJECTION", 2))
        check("propose: 2+ HITL_REJECTION con playbook -> 'improve_playbook'",
              len(imp) == 1 and imp[0]["type"] == "improve_playbook" and imp[0]["target_playbook_id"])

        nue = await fp.propose(t["nuevo"], analysis("HITL_REJECTION", 2))
        check("propose: 2+ HITL_REJECTION sin playbook -> 'new_playbook'",
              len(nue) == 1 and nue[0]["type"] == "new_playbook" and nue[0]["target_playbook_id"] is None)

        gap = await fp.propose(t["gap"], analysis("NO_RESULT", 2))
        check("propose: 2+ NO_RESULT -> 'flag_gap'",
              len(gap) == 1 and gap[0]["type"] == "flag_gap")

        # === CP-C3 (Riesgo #31): la propuesta apunta al playbook QUE FALLÓ ===
        # analyze() acumula los activated_playbooks de las trazas con señal…
        linked_sig = await fp.analyze([
            trace_dict("l1", outcome="rejected", docs=["d"], playbooks=["pb-culpable"]),
            trace_dict("l2", outcome="rejected", docs=["d"], playbooks=["pb-culpable", "pb-otro"]),
        ])
        check("CP-C3 analyze: la señal acumula los playbooks activados en sus trazas",
              linked_sig["HITL_REJECTION"]["playbooks"] == {"pb-culpable": 2, "pb-otro": 1})

        # …y propose() elige el MÁS activado en esas trazas, no el más usado del tenant.
        popular = await insert_playbook(t["linked"], "PB popular", usage=99)
        culpable = await insert_playbook(t["linked"], "PB culpable", usage=0)
        linked_analysis = analysis("HITL_REJECTION", 2)
        linked_analysis["HITL_REJECTION"]["playbooks"] = {culpable: 2}
        linked = await fp.propose(t["linked"], linked_analysis)
        check("CP-C3 propose: el target es el playbook activado en las trazas con señal",
              len(linked) == 1 and linked[0]["type"] == "improve_playbook"
              and linked[0]["target_playbook_id"] == culpable
              and linked[0]["target_playbook_id"] != popular)
        check("CP-C3 propose: la razón explica el vínculo con las trazas",
              "estaba activo en las trazas" in linked[0]["rationale"])

        # Un playbook PROTEGIDO (H.6) jamás es target: cae al no protegido más usado…
        prot = await insert_playbook(t["prot"], "PB protegido", protected=True, usage=50)
        libre = await insert_playbook(t["prot"], "PB libre", usage=1)
        prot_analysis = analysis("HITL_REJECTION", 2)
        prot_analysis["HITL_REJECTION"]["playbooks"] = {prot: 2}
        prot_props = await fp.propose(t["prot"], prot_analysis)
        check("CP-C3 propose: un playbook protegido NUNCA es target (cae al no protegido)",
              len(prot_props) == 1 and prot_props[0]["target_playbook_id"] == libre)

        # …y si SOLO hay protegidos, la propuesta baja a new_playbook (sin 409 sin salida).
        await insert_playbook(t["soloprot"], "PB único protegido", protected=True)
        sp_analysis = analysis("HITL_REJECTION", 2)
        sp = await fp.propose(t["soloprot"], sp_analysis)
        check("CP-C3 propose: solo playbooks protegidos -> 'new_playbook' (nunca 409)",
              len(sp) == 1 and sp[0]["type"] == "new_playbook"
              and sp[0]["target_playbook_id"] is None)

        # === run completo + idempotencia + watermark ===
        for i in range(2):
            tc.capture(tenant_id=t["run"], matter_id=f"m{i}", input="i", output="o", model="m",
                       tokens=1, latency_ms=1.0, hitl_outcome="rejected", retrieved_doc_ids=["d"])
        await insert_playbook(t["run"], "PB run")
        stats = await fp.run(t["run"])
        check("run(tenant) devuelve traces_analyzed/proposals_created/errors",
              set(stats.keys()) == {"traces_analyzed", "proposals_created", "errors"}
              and stats["traces_analyzed"] == 2 and stats["proposals_created"] >= 1
              and stats["errors"] == 0)
        n_after_first = await count_proposals(t["run"])
        async with pool.tenant_connection(t["run"]) as conn:
            wm_rows = (await (await conn.execute(
                "SELECT count(*) FROM processed_traces_watermark")).fetchone())[0]
        check("run: el watermark se actualiza con las trazas procesadas", wm_rows >= 1)

        stats2 = await fp.run(t["run"])
        check("run idempotente: 2ª corrida no reprocesa ni duplica propuestas",
              stats2["proposals_created"] == 0 and (await count_proposals(t["run"])) == n_after_first)

        # === aislamiento por tenant ===
        await fp.save_proposals(t["a"], [{"type": "flag_gap", "target_playbook_id": None,
                                          "suggested_content": "c", "rationale": "r",
                                          "signal_count": 2, "trace_ids": ["z"]}])
        check("aislamiento: las propuestas de A no son visibles para B",
              (await count_proposals(t["b"])) == 0 and (await count_proposals(t["a"])) >= 1)
    finally:
        await pool.close_pool()


def compat_2d_smoke() -> bool:
    """Smoke: capturar SIN campos v2 da schema v1 + los 8 campos requeridos; CON campos da v2."""
    with tempfile.TemporaryDirectory() as tmp:
        tc = TraceCapture(Path(tmp) / "tr")
        v1 = tc.capture(tenant_id="x", matter_id="m", input="i", output="o", model="mm",
                        tokens=1, latency_ms=1.0)
        v2 = tc.capture(tenant_id="x", matter_id="m", input="i", output="o", model="mm",
                        tokens=1, latency_ms=1.0, hitl_outcome="rejected")
        rec = tc.read("x")
        ok_v1 = v1.schema == TRACE_SCHEMA and set(REQUIRED_FIELDS).issubset(rec[0].keys())
        ok_v2 = v2.schema == TRACE_SCHEMA_V2
        return ok_v1 and ok_v2


def main() -> int:
    print("== Módulo 3e · Feedback processor ==")
    if not os.getenv("PG_PASSWORD"):
        print("  [FAIL] PG_PASSWORD vacío en .env")
        return 1

    init_feedback.apply()

    check('el job "feedback_daily" está registrado en el scheduler',
          any(j["name"] == "feedback_daily" for j in build_scheduler().list_jobs()))
    check("compatibilidad 2d: v1 mantiene schema/campos, v2 sube a mia.trace.v2",
          compat_2d_smoke())

    work = Path(tempfile.mkdtemp(prefix="feedback_", dir=str(ROOT / ".tmp")))
    tc = TraceCapture(work / "traces")
    fp = FeedbackProcessor(traces_dir=work / "traces")
    drop_test_tenants()
    t = {k: make_tenant(k) for k in ("a", "b", "load", "solo", "improve", "nuevo", "gap",
                                     "run", "linked", "prot", "soloprot")}
    try:
        asyncio.run(db_checks(fp, tc, t))
    finally:
        drop_test_tenants()
        shutil.rmtree(work, ignore_errors=True)

    passed = sum(1 for _, ok in _results if ok)
    total = len(_results)
    print(f"\n{passed}/{total} checks PASS")
    if passed == total:
        print("Feedback processor OK — Módulo 3e verificado.")
        return 0
    print("Feedback processor FAIL — HALT: no avanzar (CLAUDE.md §G).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
