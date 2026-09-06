"""Idempotencia contra PostgreSQL real en una base temporal, sin datos ni IA reales."""
from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch
import uuid

from dotenv import dotenv_values
import psycopg
from psycopg import sql

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from mia.assistant import chat_requests as cr  # noqa: E402
from mia.assistant.core import AssistantService  # noqa: E402
from mia.api.routes import assistant as api  # noqa: E402


class ChatRequestTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        env = dotenv_values(ROOT / ".env")
        cls.dbname = "mia_idempotency_test_" + uuid.uuid4().hex
        cls.admin = dict(host=env.get("PG_HOST", "127.0.0.1"),
                         port=env.get("PG_PORT", "5432"), dbname="postgres",
                         user="postgres", password=env.get("PG_PASSWORD", ""), connect_timeout=5)
        cls.app = {**cls.admin, "dbname": cls.dbname, "user": "mia_app",
                   "password": env.get("PG_APP_PASSWORD", "")}
        cls.tid, cls.other_tid, cls.uid, cls.other_uid = [str(uuid.uuid4()) for _ in range(4)]
        with psycopg.connect(**cls.admin, autocommit=True) as conn:
            role = conn.execute("SELECT rolsuper, rolbypassrls FROM pg_roles WHERE rolname='mia_app'").fetchone()
            if role != (False, False):
                raise AssertionError("El test exige mia_app sin privilegios para saltar RLS")
            conn.execute(sql.SQL("CREATE DATABASE {} WITH TEMPLATE template0").format(sql.Identifier(cls.dbname)))
        try:
            with psycopg.connect(**{**cls.admin, "dbname": cls.dbname}, autocommit=True) as conn:
                conn.execute("CREATE TABLE tenants(id uuid PRIMARY KEY)")
                conn.execute("CREATE TABLE users(id uuid PRIMARY KEY, tenant_id uuid, email text)")
                conn.execute("CREATE FUNCTION app_current_tenant() RETURNS uuid LANGUAGE sql STABLE AS "
                             "$$ SELECT nullif(current_setting('app.tenant_id', true), '')::uuid $$")
                conn.execute("ALTER TABLE users ENABLE ROW LEVEL SECURITY; ALTER TABLE users FORCE ROW LEVEL SECURITY")
                conn.execute("CREATE POLICY p_users ON users USING (tenant_id=app_current_tenant()) "
                             "WITH CHECK (tenant_id=app_current_tenant())")
                conn.execute("GRANT SELECT ON users TO mia_app")
                conn.execute((ROOT / "backend/mia/db/migrations/015_assistant.sql").read_text(encoding="utf-8"))
                migration = (ROOT / "backend/mia/db/migrations/065_assistant_chat_requests.sql").read_text(encoding="utf-8")
                conn.execute(migration)
                conn.execute(migration)  # migración repetible
                conn.execute("INSERT INTO tenants VALUES (%s),(%s)", (cls.tid, cls.other_tid))
                conn.execute("INSERT INTO users VALUES (%s,%s,'synthetic@example.test'),(%s,%s,'synthetic@example.test')",
                             (cls.uid, cls.tid, cls.other_uid, cls.other_tid))
        except BaseException:
            cls.tearDownClass()
            raise

    @classmethod
    def tearDownClass(cls):
        # Solo la base aleatoria que este test creó; jamás se toca la base de Mia.
        if not cls.dbname.startswith("mia_idempotency_test_"):
            raise AssertionError("Destino de limpieza inválido")
        with psycopg.connect(**cls.admin, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(cls.dbname)))

    async def asyncSetUp(self):
        @asynccontextmanager
        async def tenant_connection(tid):
            async with await psycopg.AsyncConnection.connect(**self.app) as conn:
                async with conn.transaction():
                    await conn.execute("SELECT set_config('app.tenant_id', %s, true)", (tid,))
                    yield conn
        self.connection = tenant_connection
        self.pool_patch = patch.object(cr.pool, "tenant_connection", tenant_connection)
        self.pool_patch.start()
        self.addCleanup(self.pool_patch.stop)
        self.service = AssistantService()
        self.provider = AsyncMock(return_value="respuesta sintética")

        async def chat(tid, uid, conversation_id, message):
            reply = await self.provider(message)
            if conversation_id is None:
                async with tenant_connection(tid) as conn:
                    row = await (await conn.execute(
                        "INSERT INTO assistant_conversations(tenant_id,user_id,title) VALUES(%s,%s,'sintético') RETURNING id",
                        (tid, uid))).fetchone()
                conversation_id = str(row[0])
            await self.service._persist_turn(tid, conversation_id, message, reply)
            return conversation_id, reply
        self.service.chat = chat

    async def prepare(self, rid, *, tid=None, uid=None, message="hola", conversation_id=None, budget=None):
        return await self.service.prepare_chat(
            tid or self.tid, uid or self.uid, conversation_id, message,
            request_id=rid, before_execute=budget)

    async def test_replay_survives_service_restart_and_budget_limit(self):
        rid = str(uuid.uuid4())
        budget = AsyncMock()
        first = await self.service.chat_prepared(await self.prepare(rid, budget=budget))
        fresh_service = AssistantService()
        fresh_service.chat = AsyncMock(side_effect=AssertionError("No debe llamar proveedor"))
        denied = AsyncMock(side_effect=api.policy_budget.BudgetExceeded("tope sintético"))
        second = await fresh_service.chat_prepared(await fresh_service.prepare_chat(
            self.tid, self.uid, None, "hola", request_id=rid, before_execute=denied))
        self.assertFalse(first["cached"])
        self.assertTrue(second["cached"])
        self.assertEqual(first["reply"], second["reply"])
        self.assertEqual(first["conversation_id"], second["conversation_id"])
        self.provider.assert_awaited_once()
        denied.assert_not_awaited()
        async with self.connection(self.tid) as conn:
            count = await (await conn.execute("SELECT count(*) FROM assistant_messages WHERE conversation_id=%s",
                                              (first["conversation_id"],))).fetchone()
        self.assertEqual(count[0], 2)

    async def test_concurrent_claims_call_provider_once(self):
        rid = str(uuid.uuid4())
        entered, release = asyncio.Event(), asyncio.Event()
        async def slow(message):
            entered.set()
            await release.wait()
            return "respuesta concurrente"
        self.provider.side_effect = slow
        async def run():
            try:
                return await self.service.chat_prepared(await self.prepare(rid))
            except cr.ChatRequestConflict:
                return "blocked"
        tasks = [asyncio.create_task(run()) for _ in range(6)]
        await asyncio.wait_for(entered.wait(), 10)
        release.set()
        results = await asyncio.wait_for(asyncio.gather(*tasks), 10)
        self.assertEqual(sum(isinstance(r, dict) and not r["cached"] for r in results), 1)
        self.provider.assert_awaited_once()

    async def test_payload_conflicts_and_user_scope(self):
        rid = str(uuid.uuid4())
        await self.service.chat_prepared(await self.prepare(rid))
        for change in ({"message": "distinto"}, {"conversation_id": str(uuid.uuid4())}):
            with self.assertRaises(cr.ChatRequestConflict):
                await self.prepare(rid, **change)
        # Mismo UUID en otro despacho: otra reserva, no recupera datos del primero.
        other = await self.prepare(rid, tid=self.other_tid, uid=self.other_uid)
        self.assertIsNone(other.cached)
        # Otro usuario de la misma firma también tiene namespace independiente.
        user2 = str(uuid.uuid4())
        with psycopg.connect(**{**self.admin, "dbname": self.dbname}, autocommit=True) as conn:
            conn.execute("INSERT INTO users VALUES(%s,%s,'other@example.test')", (user2, self.tid))
        self.assertIsNone((await self.prepare(rid, uid=user2)).cached)
        async with self.connection(self.other_tid) as conn:
            count = await (await conn.execute("SELECT count(*) FROM assistant_chat_requests WHERE tenant_id=%s",
                                              (self.tid,))).fetchone()
            self.assertEqual(count[0], 0)
            with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                await conn.execute("INSERT INTO assistant_chat_requests(tenant_id,user_id,request_id,payload_hash) "
                                   "VALUES(%s,%s,%s,%s)", (self.tid,self.uid,str(uuid.uuid4()),"a"*64))
        async with await psycopg.AsyncConnection.connect(**self.app) as conn:
            count = await (await conn.execute("SELECT count(*) FROM assistant_chat_requests")).fetchone()
            self.assertEqual(count[0], 0)

    async def test_failure_and_cancellation_never_reexecute(self):
        for error in (RuntimeError("sintético"), asyncio.CancelledError()):
            rid = str(uuid.uuid4())
            self.provider.side_effect = error
            with self.assertRaises(type(error)):
                await self.service.chat_prepared(await self.prepare(rid))
            self.provider.side_effect = None
            with self.assertRaises(cr.ChatRequestConflict):
                await self.prepare(rid)
        self.assertEqual(self.provider.await_count, 2)

    async def test_receipt_failure_after_persisted_turn_blocks_retry(self):
        rid = str(uuid.uuid4())
        with patch.object(cr, "complete", AsyncMock(side_effect=RuntimeError("receipt caído"))):
            with self.assertRaises(RuntimeError):
                await self.service.chat_prepared(await self.prepare(rid))
        with self.assertRaises(cr.ChatRequestConflict):
            await self.prepare(rid)
        self.provider.assert_awaited_once()

    async def test_json_and_sse_cached_resolve_user_and_preserve_new_402(self):
        request = SimpleNamespace(state=SimpleNamespace(tenant_id=self.tid, email="synthetic@example.test"))
        body = api.ChatBody(message="hola", request_id=uuid.uuid4())
        with patch.object(api, "_service", self.service), patch.object(api.policy_budget, "enforce_budget", AsyncMock()):
            first = await api.assistant_chat(body, request)
        denied = AsyncMock(side_effect=api.policy_budget.BudgetExceeded("tope sintético"))
        with patch.object(api, "_service", self.service), patch.object(api.policy_budget, "enforce_budget", denied):
            second = await api.assistant_chat(body, request)
            response = await api.assistant_chat_stream(body, request)
            events = [event async for event in response.body_iterator]
            reply = json.loads(events[-1]["data"])
            self.assertEqual(events[-1]["event"], "reply")
            self.assertEqual(reply["message"], first["reply"])
            self.assertTrue(reply["cached"])
            self.assertTrue(second["cached"])
            denied.assert_not_awaited()
            for endpoint in (api.assistant_chat, api.assistant_chat_stream):
                with self.assertRaises(api.HTTPException) as caught:
                    await endpoint(api.ChatBody(message="hola", request_id=uuid.uuid4()), request)
                self.assertEqual(caught.exception.status_code, 402)
        self.provider.assert_awaited_once()

    async def test_legacy_no_id_and_missing_user(self):
        for _ in range(2):
            result = await self.service.chat_prepared(await self.prepare(None))
            self.assertIsNone(result["request_id"])
        self.assertEqual(self.provider.await_count, 2)
        with self.assertRaises(ValueError):
            await self.service.prepare_chat(self.tid, None, None, "hola", request_id=str(uuid.uuid4()))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    unittest.main()
