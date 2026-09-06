"""Gate offline del límite entre chat general y trabajo jurídico por asunto."""
from __future__ import annotations

import sys
import asyncio
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.api.routes.assistant import requires_legal_matter  # noqa: E402
from mia.api.routes import assistant  # noqa: E402


async def check_endpoints() -> None:
    request = SimpleNamespace(state=SimpleNamespace(tenant_id="synthetic"))
    body = assistant.ChatBody(message="Redacta una demanda con estos hechos")
    with patch.object(assistant, "_prepare_chat", AsyncMock(side_effect=AssertionError("No debe gastar"))) as prepare:
        try:
            await assistant.assistant_chat(body, request)
        except assistant.HTTPException as error:
            assert error.status_code == 409
        else:
            raise AssertionError("El JSON no bloqueó el trabajo jurídico")
        response = await assistant.assistant_chat_stream(body, request)
        events = [event async for event in response.body_iterator]
        assert events[0]["event"] == "matter_required"
        prepare.assert_not_awaited()


def main() -> None:
    blocked = (
        "Redacta una demanda con estos hechos",
        "Analiza este caso y prepara la estrategia jurídica",
        "Revisa la cláusula del contrato que te copio",
        "Prepara el recurso contra la sentencia",
    )
    allowed = (
        "Recuérdame llamar a Ana mañana",
        "¿Qué asuntos tengo pendientes?",
        "Organiza mis tareas de esta semana",
        "¿Qué significa contrato?",
    )
    assert all(requires_legal_matter(text) for text in blocked)
    assert not any(requires_legal_matter(text) for text in allowed)
    asyncio.run(check_endpoints())
    source = (ROOT / "backend/mia/api/routes/assistant.py").read_text(encoding="utf-8")
    for endpoint, next_endpoint in (("async def assistant_chat(", '@router.post("/chat/stream")'),
                                    ("async def assistant_chat_stream(", '@router.get("/conversations")')):
        body = source.split(endpoint, 1)[1].split(next_endpoint, 1)[0]
        assert body.index("requires_legal_matter(body.message)") < body.index("_prepare_chat(body")
    print("assistant matter boundary OK — trabajo jurídico sustantivo se redirige sin gastar")


if __name__ == "__main__":
    main()
