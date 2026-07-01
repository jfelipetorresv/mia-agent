"""Windows-safe launcher for the Mia API."""
from __future__ import annotations

import asyncio
import os
import sys

import uvicorn


def main() -> None:
    host = os.getenv("MIA_API_HOST", "127.0.0.1")
    port = int(os.getenv("MIA_API_PORT", "8000"))
    reload = os.getenv("MIA_API_RELOAD", "0") == "1"

    if sys.platform == "win32" and not reload:
        # psycopg async NO corre sobre ProactorEventLoop. uvicorn >=0.36 fuerza
        # ProactorEventLoop en Windows via su loop_factory (ignora la event loop
        # policy), asi que en el arranque single-process montamos el servidor sobre
        # un SelectorEventLoop propio. (Con --reload uvicorn usa subprocess, cuyo
        # loop_factory ya devuelve SelectorEventLoop, por eso ese camino no aplica.)
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        config = uvicorn.Config(
            "mia.api.main:app", host=host, port=port, reload=False, loop="none"
        )
        server = uvicorn.Server(config)
        asyncio.run(server.serve())
        return

    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    uvicorn.run("mia.api.main:app", host=host, port=port, reload=reload)


if __name__ == "__main__":
    main()
