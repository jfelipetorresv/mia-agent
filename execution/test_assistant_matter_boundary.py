"""Gate offline del límite entre chat general y trabajo jurídico por asunto."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from mia.api.routes.assistant import requires_legal_matter  # noqa: E402


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
    source = (ROOT / "backend/mia/api/routes/assistant.py").read_text(encoding="utf-8")
    assert source.index("requires_legal_matter(body.message)") < source.index("enforce_budget(tid)")
    print("assistant matter boundary OK — trabajo jurídico sustantivo se redirige sin gastar")


if __name__ == "__main__":
    main()
