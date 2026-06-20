"""Windows-safe launcher for the Mia API."""
from __future__ import annotations

import asyncio
import os
import sys

import uvicorn


def main() -> None:
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

    uvicorn.run(
        "mia.api.main:app",
        host=os.getenv("MIA_API_HOST", "127.0.0.1"),
        port=int(os.getenv("MIA_API_PORT", "8000")),
        reload=os.getenv("MIA_API_RELOAD", "0") == "1",
    )


if __name__ == "__main__":
    main()
