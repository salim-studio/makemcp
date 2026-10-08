"""Middleware + Auth (minimal overhead chain)."""
from __future__ import annotations

from typing import Any, Awaitable, Callable


class Middleware:
    """Base: override async on_call / on_request. Return None to continue."""

    async def on_call(self, ctx: dict, tool: str, args: dict) -> Any | None:
        return None

    async def on_request(self, ctx: dict, method: str, params: Any) -> Any | None:
        return None


class LoggingMiddleware(Middleware):
    def __init__(self, logger=None):
        import logging
        self.log = logger or logging.getLogger("makemcp")

    async def on_call(self, ctx, tool, args):
        self.log.info("tool=%s args=%s", tool, args)
        return None


class RateLimitMiddleware(Middleware):
    """Simple token-bucket per key (default per tool)."""

    def __init__(self, max_calls: int = 60, window: float = 60.0):
        import time
        self.max_calls = max_calls
        self.window = window
        self._hits: dict = {}
        self._time = time.monotonic

    async def on_call(self, ctx, tool, args):
        now = self._time()
        lst = self._hits.get(tool)
        if lst is None:
            lst = []
            self._hits[tool] = lst
        cutoff = now - self.window
        while lst and lst[0] < cutoff:
            lst.pop(0)
        if len(lst) >= self.max_calls:
            from .exceptions import MakeMCPError
            raise MakeMCPError(f"Rate limit exceeded for '{tool}'", code=-32000)
        lst.append(now)
        return None


def bearer_auth(token: str, header: str | None = None):
    """Factory returning a Middleware enforcing `Authorization: Bearer <token>`."""
    from .exceptions import AuthError

    class _Auth(Middleware):
        async def on_request(self, ctx, method, params):
            got = (ctx.get("auth") or ctx.get("authorization") or header or "")
            if isinstance(ctx.get("headers"), dict):
                h = ctx["headers"]
                got = h.get("authorization", h.get("Authorization", got))
            if got.startswith("Bearer "):
                got = got[7:]
            if got != token:
                raise AuthError("Unauthorized")
            return None

    return _Auth()
