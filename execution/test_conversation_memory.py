"""Memoria larga: PostgreSQL temporal real, resumidor sintético, cero proveedores."""
from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
import hashlib
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch, AsyncMock
from types import SimpleNamespace
import uuid

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))
from test_assistant_chat_requests import ChatRequestTests
from mia.assistant import conversation_memory as memory
from mia.assistant.core import AssistantService


class ConversationMemoryTests(ChatRequestTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        try:
            with psycopg.connect(**{**cls.admin, "dbname": cls.dbname}, autocommit=True) as conn:
                migration = (ROOT / "backend/mia/db/migrations/066_assistant_conversation_memory.sql").read_text(encoding="utf-8")
                conn.execute(migration)
                conn.execute(migration)
        except BaseException:
            cls.tearDownClass()
            raise

    async def asyncSetUp(self):
        await super().asyncSetUp()
        self.conv = str(uuid.uuid4())
        self.rows = []
        async with self.connection(self.tid) as conn:
            await conn.execute("INSERT INTO assistant_conversations(id,tenant_id,user_id,title) VALUES(%s,%s,%s,'memoria sintética')",
                               (self.conv,self.tid,self.uid))
            base = uuid.uuid4().int & ~65535
            for i in range(450):
                marker = " INICIO_UNICO" if i == 0 else " MEDIO_UNICO" if i == 150 else " [VERIFICAR] pendiente original exacto" if i == 50 else ""
                content = f"mensaje-{i:04d}{marker}: " + "detalle verificable " * 20
                row = (uuid.UUID(int=base+i), datetime(2025,1,1,tzinfo=timezone.utc)+timedelta(seconds=i//2),
                       "user" if i%2==0 else "assistant", content)
                self.rows.append(row)
            async with conn.cursor() as cursor:
                await cursor.executemany("INSERT INTO assistant_messages(id,tenant_id,conversation_id,role,content,created_at) "
                                         "VALUES(%s,%s,%s,%s,%s,%s)",
                                         [(r[0],self.tid,self.conv,r[2],r[3],r[1]) for r in self.rows])
        self.calls = []
        calls = self.calls
        class Summarizer:
            def summarize_segment(self, turns, *, previous_summary, model_context_window):
                calls.append((turns,previous_summary))
                text = previous_summary + " ".join(m["content"] for m in turns)
                return "Resumen sintético. " + ("MEDIO_UNICO" if "MEDIO_UNICO" in text else "")
        self.factory = Summarizer
        self.window = 16000

    async def assemble(self, **kwargs):
        return await memory.assemble(self.tid,self.conv,self.window,
                                     compressor_factory=kwargs.get("factory",self.factory))

    async def checkpoint(self):
        async with self.connection(self.tid) as conn:
            return await (await conn.execute("SELECT revision,summary,cursor_id,covered_hash FROM assistant_conversation_memory "
                                              "WHERE conversation_id=%s",(self.conv,))).fetchone()

    async def test_450_paging_reuse_originals_and_pending(self):
        shifted = [(r[0],r[1].astimezone(timezone(timedelta(hours=-5))),r[2],r[3]) for r in self.rows]
        self.assertEqual(memory._hash(self.rows),memory._hash(shifted))
        history = await self.assemble()
        text = "\n".join(m["content"] for m in history)
        self.assertIn("INICIO_UNICO",text)
        self.assertIn("MEDIO_UNICO",text)
        self.assertIn(self.rows[50][3],text)
        self.assertEqual(history[:5],[memory._message(r) for r in self.rows[:5]])
        self.assertEqual(history[-30:],[memory._message(r) for r in self.rows[-30:]])
        submitted = [m["content"] for turns,_ in self.calls for m in turns]
        rendered = [m["content"] for m in history]
        self.assertTrue(all(r[3] in submitted or r[3] in rendered for r in self.rows))
        self.assertEqual(len(submitted),len(set(submitted)))
        count = len(self.calls)
        self.assertGreater(count,0)
        self.assertEqual(await self.assemble(),history)
        self.assertEqual(len(self.calls),count)
        async with self.connection(self.tid) as conn:
            originals = await (await conn.execute("SELECT id,created_at,role,content FROM assistant_messages WHERE conversation_id=%s "
                                                  "ORDER BY created_at,id",(self.conv,))).fetchall()
        self.assertEqual(originals,self.rows)

    async def test_failed_or_ineffective_never_advances_and_failed_can_retry(self):
        class Broken:
            def summarize_segment(self,*args,**kwargs):
                raise RuntimeError("fallo conocido sintético")
        with self.assertRaises(memory.MemoryUnavailable):
            await self.assemble(factory=Broken)
        self.assertEqual((await self.checkpoint())[:3],(0,"",None))
        class NoSaving:
            def summarize_segment(self,turns,**kwargs):
                return " ".join(m["content"] for m in turns) * 2
        with self.assertRaises(memory.MemoryUnavailable):
            await self.assemble(factory=NoSaving)
        self.assertEqual((await self.checkpoint())[:3],(0,"",None))
        # Nuevo material elegible reactiva un intento ineficaz; el mismo no se repaga.
        calls = []
        class Spy(self.factory):
            def summarize_segment(self,*args,**kwargs):
                calls.append(1)
                return super().summarize_segment(*args,**kwargs)
        with self.assertRaises(memory.MemoryUnavailable):
            await self.assemble(factory=Spy)
        self.assertEqual(calls,[])
        async with self.connection(self.tid) as conn:
            await conn.execute("INSERT INTO assistant_messages(tenant_id,conversation_id,role,content) VALUES(%s,%s,'user','nuevo material elegible')",
                               (self.tid,self.conv))
        await self.assemble(factory=Spy)
        self.assertGreater(len(calls),0)

    async def test_edit_and_retroactive_insert_invalidate_covered_prefix(self):
        await self.assemble()
        prior = await self.checkpoint()
        async with self.connection(self.tid) as conn:
            await conn.execute("UPDATE assistant_messages SET content='CORRECCION_UNICA' WHERE id=%s",(self.rows[10][0],))
            await conn.execute("INSERT INTO assistant_messages(tenant_id,conversation_id,role,content,created_at) "
                               "VALUES(%s,%s,'user','RETROACTIVO_UNICO',%s)",
                               (self.tid,self.conv,self.rows[10][1]))
        self.calls.clear()
        await self.assemble()
        submitted = " ".join(m["content"] for turns,_ in self.calls for m in turns)
        self.assertIn("CORRECCION_UNICA",submitted)
        self.assertTrue("RETROACTIVO_UNICO" in submitted, "retroinserción debe reprocesarse")
        self.assertEqual(self.calls[0][1],"")
        self.assertGreater((await self.checkpoint())[0],prior[0])
        # Al borrar cola, los últimos30 actuales pueden entrar en el viejo resumen.
        # Deben volver a estar verbatim, no quedarse detrás de su cursor anterior.
        before_delete = await self.checkpoint()
        calls_before_delete = len(self.calls)
        async with self.connection(self.tid) as conn:
            originals = await (await conn.execute("SELECT id,created_at,role,content FROM assistant_messages "
                                                  "WHERE conversation_id=%s ORDER BY created_at,id",(self.conv,))).fetchall()
            cursor_index = next(i for i,r in enumerate(originals) if r[0] == before_delete[2])
            keep = originals[:cursor_index+11]
            self.assertGreater(memory.ContextCompressor._count([memory._message(r) for r in keep]),self.window*0.8)
            await conn.execute("DELETE FROM assistant_messages WHERE id=ANY(%s::uuid[])",
                               ([r[0] for r in originals[cursor_index+11:]],))
            tail = await (await conn.execute("SELECT id,created_at,role,content FROM assistant_messages "
                                             "WHERE conversation_id=%s ORDER BY created_at DESC,id DESC LIMIT 30",
                                             (self.conv,))).fetchall()
        rebuilt = await self.assemble()
        self.assertEqual(rebuilt[-30:],[memory._message(r) for r in reversed(tail)])
        self.assertGreater(len(self.calls),calls_before_delete)

    async def test_concurrent_summary_and_edit_during_publish(self):
        entered, release = threading.Event(), threading.Event()
        outer = self
        class Slow(self.factory):
            def summarize_segment(self,*args,**kwargs):
                entered.set()
                release.wait(10)
                return super().summarize_segment(*args,**kwargs)
        first = asyncio.create_task(self.assemble(factory=Slow))
        self.assertTrue(await asyncio.to_thread(entered.wait,10))
        with self.assertRaises(memory.MemoryUnavailable):
            await self.assemble(factory=Slow)
        release.set()
        await first
        hashes = [hashlib.sha256(str(turns).encode()).hexdigest() for turns,_ in self.calls]
        self.assertEqual(len(hashes),len(set(hashes)))
        # CAS sobre el snapshot: una edición durante el proveedor no se sella.
        async with self.connection(self.tid) as conn:
            await conn.execute("UPDATE assistant_messages SET content=content || ' nuevo' WHERE id=%s",(self.rows[10][0],))
        self.calls.clear()
        class Mutating(self.factory):
            def summarize_segment(self,*args,**kwargs):
                with psycopg.connect(**{**outer.admin,"dbname":outer.dbname},autocommit=True) as conn:
                    conn.execute("UPDATE assistant_messages SET content=content || ' cambió durante resumen' WHERE id=%s",(outer.rows[10][0],))
                return super().summarize_segment(*args,**kwargs)
        with self.assertRaises(memory.MemoryUnavailable):
            await self.assemble(factory=Mutating)
        self.assertEqual((await self.checkpoint())[1],"")

    async def test_rls_cross_reference_and_pending_overflow(self):
        await self.assemble()
        async with self.connection(self.other_tid) as conn:
            rows = await (await conn.execute("SELECT * FROM assistant_conversation_memory WHERE conversation_id=%s",(self.conv,))).fetchall()
            self.assertEqual(rows,[])
            with self.assertRaises(psycopg.errors.ForeignKeyViolation):
                await conn.execute("INSERT INTO assistant_conversation_memory(tenant_id,conversation_id) VALUES(%s,%s)",
                                   (self.other_tid,self.conv))
        with self.assertRaises(memory.MemoryUnavailable):
            await memory.assemble(self.other_tid,self.conv,self.window,compressor_factory=self.factory)
        async with self.connection(self.tid) as conn:
            await conn.execute("UPDATE assistant_messages SET content='[VERIFICAR] ' || repeat('pendiente ',3000) "
                               "WHERE conversation_id=%s",(self.conv,))
        self.calls.clear()
        with self.assertRaises(memory.MemoryUnavailable):
            await self.assemble()
        self.assertEqual(self.calls,[])
        with self.assertRaises(memory.MemoryUnavailable):
            memory.guard_final_context([{"role":"user","content":"[VERIFICAR] "*20000}],self.window)

    async def test_core_guard_and_ephemeral_never_enter_summary(self):
        from mia.assistant import core
        service = AssistantService()
        provider = AsyncMock(side_effect=AssertionError("main no debe ejecutarse"))
        with patch.object(core,"ContextCompressor",self.factory), patch.object(core.config,"MIA_CONTEXT_WINDOW",self.window), \
             patch.object(core.llm,"call_llm",provider), patch.object(core,"build_assistant_system",lambda *args:"SISTEMA "*30000), \
             patch.object(core.persona_service,"resolve_for_turn",AsyncMock(return_value=None)):
            cid,reply = await service.chat(self.tid,self.uid,self.conv,"TURNO_EFIMERO_UNICO")
        self.assertEqual(cid,self.conv)
        self.assertIn("No respondí",reply)
        provider.assert_not_called()
        self.assertNotIn("TURNO_EFIMERO_UNICO",str(self.calls))

    async def test_full_original_fallback_and_summary_input_guard(self):
        self.window = int(memory.ContextCompressor._count([memory._message(r) for r in self.rows]) / 0.65)
        calls = []
        class NoSaving:
            def summarize_segment(self, turns, **kwargs):
                calls.append(1)
                return " ".join(m["content"] for m in turns) * 2
        expected = [memory._message(r) for r in self.rows]
        self.assertEqual(await self.assemble(factory=NoSaving),expected)
        self.assertEqual(await self.assemble(factory=NoSaving),expected)
        self.assertEqual(calls,[1])
        self.assertEqual((await self.checkpoint())[:3],(0,"",None))
        from mia.agent import context_compressor
        with patch.object(context_compressor.llm,"call_llm",side_effect=AssertionError("No debe pagar")) as provider:
            with self.assertRaises(ValueError):
                context_compressor.ContextCompressor().summarize_segment(
                    [{"role":"user","content":"gigante "*10000}],previous_summary="",model_context_window=1000)
            provider.assert_not_called()

    async def test_core_main_receives_complete_memory_not_recent_window_only(self):
        from mia.assistant import core
        service = AssistantService()
        received = []
        def main(messages, **kwargs):
            received.append(messages)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="Respuesta sintética verificada por fixture"))])
        with patch.object(core,"ContextCompressor",self.factory), patch.object(core.config,"MIA_CONTEXT_WINDOW",self.window), \
             patch.object(core.llm,"call_llm",main), patch.object(core,"build_assistant_system",lambda *args:"Sistema sintético"), \
             patch.object(core.persona_service,"resolve_for_turn",AsyncMock(return_value=None)):
            await service.chat(self.tid,self.uid,self.conv,"TURNO_EFIMERO_UNICO")
        self.assertEqual(len(received),1)
        text = "\n".join(m["content"] for m in received[0])
        for marker in ("INICIO_UNICO","MEDIO_UNICO",self.rows[50][3],"TURNO_EFIMERO_UNICO"):
            self.assertTrue(marker in text)
        self.assertNotIn("TURNO_EFIMERO_UNICO",str(self.calls))

    async def test_antithrashing_persists_and_new_eligible_material_reactivates(self):
        history = await self.assemble()
        basis = memory._hash(self.rows[5:-30])
        async with self.connection(self.tid) as conn:
            await conn.execute("UPDATE assistant_conversation_memory SET ineffective_count=2,eligible_basis=%s "
                               "WHERE conversation_id=%s",(basis,self.conv))
        self.calls.clear()
        self.window = int(memory.ContextCompressor._count(history) / 0.9)
        with self.assertRaises(memory.MemoryUnavailable):
            await self.assemble()
        self.assertEqual(self.calls,[])
        async with self.connection(self.tid) as conn:
            await conn.execute("INSERT INTO assistant_messages(tenant_id,conversation_id,role,content) "
                               "VALUES(%s,%s,'user','nuevo material para evaluar')",(self.tid,self.conv))
        try:
            await self.assemble()
        except memory.MemoryUnavailable:
            pass  # Una ventana menor todavía puede no alcanzar; debe intentar con material nuevo.
        self.assertGreater(len(self.calls),0)


def load_tests(loader, tests, pattern):
    # Reusar solo el fixture DB, no repetir las siete suites de idempotencia heredadas.
    return unittest.TestSuite(ConversationMemoryTests(name) for name in ConversationMemoryTests.__dict__ if name.startswith("test_"))


if __name__ == "__main__":
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    unittest.main()
