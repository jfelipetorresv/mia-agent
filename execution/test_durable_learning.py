"""Gate enfocado: aprendizaje recuperable, referencias mínimas y aplicación real."""
from __future__ import annotations

import asyncio
import hashlib
import sys
import tempfile
import uuid
from pathlib import Path

if sys.platform == "win32":
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia import config  # noqa: E402
from mia.jobs import durable  # noqa: E402
from mia.memory import aprendido  # noqa: E402
from mia.memory.trace_capture import TraceCapture  # noqa: E402


async def main() -> None:
    required = {
        "wiki_approved_artifact", "learn_approved_artifact",
        "skill_improvement", "harvest_lessons",
    }
    assert required.issubset(durable.HANDLERS)

    tenant, matter = str(uuid.uuid4()), str(uuid.uuid4())
    text = "Versión exacta aprobada por el abogado."
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with tempfile.TemporaryDirectory() as tmp:
        previous_home = config.MIA_HOME
        config.MIA_HOME = Path(tmp)
        try:
            trace = TraceCapture().capture(
                tenant_id=tenant, matter_id=matter, input="consulta", output=text,
                model="test", tokens=1, latency_ms=1, hitl_outcome="approved",
                draft_final=text,
            )
            trace_id = f"{tenant}:{matter}:{trace.timestamp}"
            loaded = await durable._load_trace(tenant, matter, trace_id, digest)
            assert loaded["output"] == text
            try:
                await durable._load_trace(tenant, matter, trace_id, "0" * 64)
                raise AssertionError("una huella ajena aceptó la traza")
            except ValueError:
                pass
        finally:
            config.MIA_HOME = previous_home

    try:
        durable._artifact_ref({"matter_id": matter, "artifact_hash": "x" * 64,
                               "trace_id": "trace"})
        raise AssertionError("hash no hexadecimal aceptado")
    except ValueError:
        pass

    # Fallo posterior a inferir: el manifiesto conserva las mismas líneas; el
    # reintento aplica una vez y una tercera entrega no vuelve a inferir/escribir.
    with tempfile.TemporaryDirectory() as tmp:
        previous_home = config.MIA_HOME
        old_infer = aprendido.infer_learnings
        old_load = aprendido._load_existing_aprendido
        config.MIA_HOME = Path(tmp)
        existing: list[str] = []
        infer_calls = 0

        def fake_infer(_text: str, *, strict: bool = False) -> list[str]:
            nonlocal infer_calls
            infer_calls += 1
            return ["Lección: verificar la fuente antes de citar."]

        class FlakyInterview:
            calls = 0

            async def update_soul(self, _tenant: str, updates: dict) -> None:
                self.calls += 1
                if self.calls == 1:
                    raise OSError("caída simulada antes de persistir")
                existing[:] = list(updates["aprendido"])

        interview = FlakyInterview()
        aprendido.infer_learnings = fake_infer
        aprendido._load_existing_aprendido = lambda _tenant: list(existing)
        try:
            try:
                await aprendido.learn_from_approved_draft(
                    tenant, text, strict=True, idempotency_key=digest,
                    interview=interview,
                )
                raise AssertionError("el fallo de escritura fue absorbido")
            except OSError:
                pass
            result = await aprendido.learn_from_approved_draft(
                tenant, text, strict=True, idempotency_key=digest,
                interview=interview,
            )
            replay = await aprendido.learn_from_approved_draft(
                tenant, text, strict=True, idempotency_key=digest,
                interview=interview,
            )
            assert result == replay == {"added": 1, "dropped": 0}
            assert len(existing) == 1 and infer_calls == 1 and interview.calls == 2
        finally:
            aprendido.infer_learnings = old_infer
            aprendido._load_existing_aprendido = old_load
            config.MIA_HOME = previous_home

    graph_src = (ROOT / "backend/mia/agents/graph.py").read_text(encoding="utf-8")
    hitl_src = (ROOT / "backend/mia/api/routes/hitl.py").read_text(encoding="utf-8")
    ux_src = (ROOT / "backend/mia/api/routes/ux.py").read_text(encoding="utf-8")
    migration = (ROOT / "backend/mia/db/migrations/056_durable_learning_once.sql").read_text(
        encoding="utf-8")
    assert "enqueue_learning_job" in graph_src
    assert "asyncio.create_task(self._harvest_background" not in graph_src
    assert "asyncio.create_task(_wiki_update())" not in hitl_src
    assert "decision_saved=True" in hitl_src and "learning=learning" in hitl_src
    assert 'p["proposal_type"] in ("new_playbook", "harvest_lessons")' in ux_src
    assert "ON CONFLICT (tenant_id, title) DO NOTHING RETURNING id" in ux_src
    assert "await asyncio.to_thread(" in ux_src and "embeddings.embed_texts" in ux_src
    apply_start = ux_src.index("async def apply_proposal")
    pre_embed = ux_src.index("vec_new = (await asyncio.to_thread(", apply_start)
    write_lock = ux_src.index("status = 'pending' FOR UPDATE", apply_start)
    assert pre_embed < write_lock
    assert "uq_durable_learning_once" in migration

    # Reencolado de fallidos (auditoría 2026-08-14): una señal agotada (failed×max)
    # vuelve a la cola al re-encolarse la MISMA señal; succeeded conserva el coalescing.
    class _FakeConn:
        def __init__(self, rows):
            self.rows = list(rows)
            self.sql: list[str] = []

        async def execute(self, sql, params=None):
            self.sql.append(sql)
            row = self.rows.pop(0) if self.rows else None

            class _Cur:
                async def fetchone(_self):
                    return row
            return _Cur()

    from contextlib import asynccontextmanager
    from mia.db import pool as pool_mod
    old_tc = pool_mod.tenant_connection
    payload = {"matter_id": matter, "artifact_hash": digest, "trace_id": "t"}

    failed_conn = _FakeConn([("job-1", "failed"), ("job-1",)])

    @asynccontextmanager
    async def _fake_tc(_tid):
        yield failed_conn
    pool_mod.tenant_connection = _fake_tc
    try:
        rid, created, st = await durable.enqueue_learning_job(
            tenant, "harvest_lessons", payload, dedupe_key="harvest_lessons:k")
        assert (rid, created, st) == ("job-1", True, "queued"), (rid, created, st)
        assert any("status='queued'" in s and "status='failed'" in s for s in failed_conn.sql)

        ok_conn = _FakeConn([("job-2", "succeeded")])

        @asynccontextmanager
        async def _fake_tc2(_tid):
            yield ok_conn
        pool_mod.tenant_connection = _fake_tc2
        rid2, created2, st2 = await durable.enqueue_learning_job(
            tenant, "harvest_lessons", payload, dedupe_key="harvest_lessons:k")
        assert (rid2, created2, st2) == ("job-2", False, "succeeded"), (rid2, created2, st2)
    finally:
        pool_mod.tenant_connection = old_tc
    print("PASS: una señal fallida agotada se reencola; una completada no se duplica")

    print("PASS: los cuatro aprendizajes usan handlers durables allowlisted")
    print("PASS: la traza queda ligada a la huella exacta del artefacto")
    print("PASS: HITL informa decisión guardada y aprendizaje separado")
    print("PASS: harvest solo se aplica si nació una guía real")
    print("PASS: embedding no bloquea el event loop")
    print("PASS: caída y reintento reutilizan una inferencia y no duplican aprendizaje")


asyncio.run(main())
