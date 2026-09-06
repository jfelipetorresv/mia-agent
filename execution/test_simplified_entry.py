"""Mia · gate del alta y creación simplificadas.

Comprueba el comportamiento, sin base de datos ni modelo: el alta no exige entrevista
ni inventa identidad, y aun un cliente legado que envíe `kind='proyecto'` crea un caso
de borrador sujeto a aprobación.

    .venv\Scripts\python.exe execution\test_simplified_entry.py
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.api.routes import ux  # noqa: E402
from mia.onboarding.soul_interview import SoulInterview, build_soul  # noqa: E402


def check(name: str, ok: bool) -> None:
    print(("  [OK]   " if ok else "  [FAIL] ") + name)
    if not ok:
        raise AssertionError(name)


class _Result:
    def __init__(self, row):
        self.row = row

    async def fetchone(self):
        return self.row


class _Connection:
    def __init__(self):
        self.params = None

    async def execute(self, sql, params):
        self.params = params
        if "SELECT name FROM tenants" in sql:
            return _Result(("Firma registrada",))
        return _Result(("11111111-1111-4111-8111-111111111111", "active", "2026-09-06"))


class _ConnectionContext:
    def __init__(self, connection):
        self.connection = connection

    async def __aenter__(self):
        return self.connection

    async def __aexit__(self, *_exc):
        return False


class _Pool:
    def __init__(self, connection):
        self.connection = connection

    def tenant_connection(self, _tenant):
        return _ConnectionContext(self.connection)


async def main() -> None:
    check("la entrevista inicial no contiene preguntas", await SoulInterview().get_questions() == [])
    blank = build_soul({})
    check("un perfil vacío no inventa identidad", "Perfil en aprendizaje" in blank and "Lexia" not in blank)

    original_tenant = ux._tenant
    original_pool = ux.pool
    original_jurisdictions = ux._matter_jurisdictions
    original_threadpool = ux.run_in_threadpool
    original_interview = ux.SoulInterview
    original_save_draft = ux._save_onboarding_draft
    original_soul_status = ux.soul_status
    original_load_responses = ux.load_responses
    original_load_soul_text = ux.load_soul_text
    try:
        connection = _Connection()
        ux._tenant = lambda _request: "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        ux.pool = _Pool(connection)

        async def jurisdictions(_tenant, requested):
            return requested or []

        async def no_threadpool(*_args, **_kwargs):
            return None

        ux._matter_jurisdictions = jurisdictions
        ux.run_in_threadpool = no_threadpool
        created = await ux.create_matter(
            object(), ux.MatterCreate(name="  Caso de prueba  ", kind="proyecto"),
        )
        check("un cliente legado no puede crear respuesta directa", created["kind"] == "asunto")
        check("la base recibe siempre el modo con aprobación", connection.params[3] == "asunto")
        check("el nombre del caso se guarda y devuelve sin espacios exteriores",
              connection.params[1] == "Caso de prueba" and created["name"] == "Caso de prueba")
        try:
            await ux.create_matter(object(), ux.MatterCreate(name="Caso inválido", kind="ajeno"))
        except Exception as exc:
            check("un modo inválido sigue rechazado", getattr(exc, "status_code", None) == 422)
        else:
            check("un modo inválido sigue rechazado", False)
        connection.params = None
        try:
            await ux.create_matter(object(), ux.MatterCreate(name="   "))
        except Exception as exc:
            check("un caso sin nombre se rechaza antes de escribir", 
                  getattr(exc, "status_code", None) == 422 and connection.params is None)
        else:
            check("un caso sin nombre se rechaza antes de escribir", False)

        captured = {}

        class _Interview:
            async def run_interview(self, tenant, responses):
                captured["tenant"] = tenant
                captured["responses"] = responses
                return "# SOUL.md — Perfil en aprendizaje\n"

            def summary(self, _responses):
                return "### Perfil en aprendizaje"

        async def no_save_draft(*_args, **_kwargs):
            return None

        ux.SoulInterview = _Interview
        ux._save_onboarding_draft = no_save_draft
        ux.soul_status = lambda _tenant: {"completed": False}
        completed = await ux.onboarding_complete(object(), ux.OnboardingComplete(responses={}))
        check("el alta vacía se completa", completed["generated_by"] == "deterministic")
        check("el alta vacía usa solo la firma registrada", captured["responses"] == {
            "identity.name": {"firm": "Firma registrada"}})

        captured.clear()
        ux.soul_status = lambda _tenant: {"completed": True}
        ux.load_responses = lambda _tenant: {"identity.name": {"firm": "Guardada", "lawyer": "Ana"}}
        ux.load_soul_text = lambda _tenant: "# SOUL.md — Guardada\n"
        retried = await ux.onboarding_complete(object(), ux.OnboardingComplete(responses={}))
        check("un reintento vacío conserva el perfil existente", retried["soul_content"] == "# SOUL.md — Guardada\n")
        check("un reintento vacío no vuelve a escribir el perfil", captured == {})
    finally:
        ux._tenant = original_tenant
        ux.pool = original_pool
        ux._matter_jurisdictions = original_jurisdictions
        ux.run_in_threadpool = original_threadpool
        ux.SoulInterview = original_interview
        ux._save_onboarding_draft = original_save_draft
        ux.soul_status = original_soul_status
        ux.load_responses = original_load_responses
        ux.load_soul_text = original_load_soul_text


if __name__ == "__main__":
    asyncio.run(main())
