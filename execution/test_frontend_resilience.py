"""Contratos baratos para que los estados de fallo del frontend no se vuelvan silenciosos.

Son checks de fuente, al estilo de los gates UX existentes. El comportamiento visual se
comprueba con Playwright; aquí se protege el cableado mínimo que evita afirmar que unos datos
vacíos son datos reales o dejar acciones sin salida cuando un servicio no responde.
"""
from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
_results: list[tuple[str, bool]] = []


def check(name: str, ok: bool) -> None:
    _results.append((name, bool(ok)))
    print(("  [OK]   " if ok else "  [FAIL] ") + name)


def main() -> int:
    chat = (ROOT / "frontend/app/chat/page.tsx").read_text(encoding="utf-8")
    memoria = (ROOT / "frontend/app/memoria/page.tsx").read_text(encoding="utf-8")
    ayuda = (ROOT / "frontend/app/ayuda/page.tsx").read_text(encoding="utf-8")
    configurar = (ROOT / "frontend/app/configurar/page.tsx").read_text(encoding="utf-8")
    arnes = (ROOT / "e2e/capturas_cotejo_pack.mjs").read_text(encoding="utf-8")

    check(
        "abrir una conversación conserva el hilo visible si falla la carga",
        "const previousMessages = messages" in chat
        and "setMessages(previousMessages)" in chat
        and "No pude abrir esa conversación" in chat
        and "Reintentar" in chat,
    )
    check(
        "el chat móvil permite crear y recuperar conversaciones",
        'id="chat-mobile-conversation"' in chat
        and 'onClick={newConversation}' in chat
        and "conversations.map" in chat,
    )
    check(
        "el chat anuncia estado y respuesta dinámica al lector de pantalla",
        'role="status"' in chat and 'aria-live="polite"' in chat and "aria-atomic" in chat,
    )
    check(
        "Sugerencias distingue datos vacíos de una carga incompleta",
        "Promise.allSettled" in memoria
        and "loadError" in memoria
        and "No pude actualizar todas las mejoras" in memoria
        and "!loadError" in memoria,
    )
    check(
        "Ayuda ofrece reintento cuando el manual falla",
        "retryKey" in ayuda and "Reintentar" in ayuda and "role=\"alert\"" in ayuda,
    )
    check(
        "Configuración ofrece reintento cuando el estado falla",
        "onClick={load}" in configurar and "role=\"alert\"" in configurar,
    )
    check(
        "el arnés de cotejo conserva detalle de errores sin query strings",
        "detalle_error" in arnes
        and "r.failure()?.errorText" in arnes
        and "u.pathname" in arnes,
    )

    passed = sum(1 for _, ok in _results if ok)
    print(f"\n{passed}/{len(_results)} checks PASS")
    return 0 if passed == len(_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
