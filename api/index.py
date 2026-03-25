"""
Vercel serverless ASGI entry — export a native ASGI ``app`` (no Mangum).

Client calls ``/api/health``; we strip a leading ``/api`` when present so
``phase7_ui.api`` routes (``/health``, …) match local ``uvicorn`` behavior.
"""

from __future__ import annotations

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from fastapi.middleware.cors import CORSMiddleware

from phase7_ui.api import app as pulse_app

pulse_app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class _StripApiPrefix:
    """ASGI wrapper: /api/foo -> /foo."""

    __slots__ = ("_app", "_prefix")

    def __init__(self, app, prefix: str = "/api") -> None:
        self._app = app
        self._prefix = prefix.rstrip("/") or "/api"

    async def __call__(self, scope, receive, send):  # type: ignore[no-untyped-def]
        if scope.get("type") == "http":
            path = scope.get("path") or ""
            p = self._prefix
            if path == p or path.startswith(p + "/"):
                scope = dict(scope)
                rest = path[len(p) :] or "/"
                scope["path"] = rest if rest.startswith("/") else "/" + rest
        return await self._app(scope, receive, send)


app = _StripApiPrefix(pulse_app)
