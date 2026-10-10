"""MakeMCP server: tools/resources/prompts + JSON-RPC dispatch + transports.

Design principles:
- zero mandatory dependencies (stdlib only)
- sync functions run inline (no event-loop hop), async awaited directly
- precomputed schemas, dict lookups, optional result caching
- single dispatch coroutine handling all MCP methods
"""
from __future__ import annotations

import asyncio
import inspect
import time
import traceback
import typing
from typing import Any, Callable

from . import _json as J
from .cache import TTLCache
from .exceptions import MakeMCPError, ToolError, ResourceError, PromptError
from .schema import func_schema, coerce
from .types import Tool, Resource, Prompt, TextContent

PROTOCOL_VERSION = "2024-11-05"


def _is_async(fn) -> bool:
    return inspect.iscoroutinefunction(fn)


def _json_safe(obj: Any) -> Any:
    """Recursively coerce *obj* into JSON-serializable data (str fallback).

    Guarantees the transport layer can always serialize a response —
    converted tools may return exotic objects (e.g. dependency stubs).
    """
    try:
        J.dumps(obj)
        return obj
    except Exception:
        pass
    if isinstance(obj, dict):
        return {str(k): _json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_json_safe(v) for v in obj]
    return str(obj)


def _coerce_item(r: Any) -> dict:
    if isinstance(r, dict) and isinstance(r.get("type"), str):
        return _json_safe(r)
    if hasattr(r, "to_dict"):
        try:
            d = r.to_dict()
            return _json_safe(d) if isinstance(d, dict) \
                else {"type": "text", "text": str(d)}
        except Exception:
            pass
    return {"type": "text", "text": r if isinstance(r, str) else str(r)}


def _result_to_content(res: Any) -> list[dict]:
    if res is None:
        return [{"type": "text", "text": ""}]
    if isinstance(res, TextContent):
        return [_json_safe(res.to_dict())]
    if isinstance(res, dict) and res.get("type") in ("text", "image", "resource"):
        return [_json_safe(res)]
    if isinstance(res, (str, int, float, bool)):
        return [{"type": "text", "text": str(res)}]
    if isinstance(res, (list, tuple)):
        out: list[dict] = [_coerce_item(r) for r in res]
        return out or [{"type": "text", "text": ""}]
    if hasattr(res, "to_dict"):
        try:
            d = res.to_dict()
            return [_json_safe(d) if isinstance(d, dict)
                    else {"type": "text", "text": str(d)}]
        except Exception:
            pass
    # structured: return as text JSON (fast dumps)
    try:
        return [{"type": "text", "text": _json_safe(J.dumps(res).decode())}]
    except Exception:
        return [{"type": "text", "text": str(res)}]


class MakeMCP:
    def __init__(self, name: str = "makemcp", version: str = "1.0.0",
                 instructions: str | None = None, lifespan=None,
                 json_backend: str = "auto"):
        self.name = name
        self.version = version
        self.instructions = instructions
        self.lifespan = lifespan
        self._tools: dict[str, Tool] = {}
        self._resources: dict[str, Resource] = {}
        self._prompts: dict[str, Prompt] = {}
        self._middleware: list = []
        self._result_cache = TTLCache(maxsize=4096, ttl=30.0)
        self._state: dict = {}
        self._on_startup: list[Callable] = []
        self._on_shutdown: list[Callable] = []
        # mount registry: prefix -> MakeMCP
        self._mounts: list[tuple[str, "MakeMCP"]] = []

    # ---------- decorators ----------
    def tool(self, fn=None, *, name: str | None = None, description: str | None = None,
             tags: set | list | None = None, cache_ttl: float | None = None,
             timeout: float | None = None):
        def deco(f):
            tname = name or f.__name__
            is_async = _is_async(f)
            t = Tool(name=tname, fn=f, description=description or (f.__doc__ or "").strip(),
                     schema=func_schema(f), tags=set(tags or ()),
                     cache_ttl=cache_ttl, timeout=timeout, is_async=is_async)
            self._tools[tname] = t
            return f
        return deco(fn) if fn else deco

    def resource(self, uri=None, *, name: str | None = None, description: str | None = None,
                 mime_type: str = "text/plain"):
        def deco(f):
            u = uri or f"resource://{f.__name__}"
            if callable(uri) and isinstance(uri, type(lambda: 0)):
                pass
            r = Resource(uri=u if isinstance(u, str) else f"resource://{f.__name__}",
                         fn=f, name=name or f.__name__,
                         description=description or (f.__doc__ or "").strip(),
                         mimeType=mime_type, is_async=_is_async(f))
            self._resources[r.uri] = r
            return f
        if callable(uri) and not isinstance(uri, str):
            fn = uri
            uri = None
            return deco(fn)
        return deco

    def prompt(self, fn=None, *, name: str | None = None, description: str | None = None):
        def deco(f):
            pname = name or f.__name__
            # build arguments from signature
            sig = inspect.signature(f)
            try:
                hints = typing.get_type_hints(f)
            except Exception:
                hints = {}
            args = []
            for pname2, p in sig.parameters.items():
                if pname2 in ("self", "cls", "ctx", "context"):
                    continue
                if p.kind in (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD):
                    continue
                a = {"name": pname2}
                if p.default is not inspect.Parameter.empty:
                    a["required"] = False
                else:
                    a["required"] = True
                args.append(a)
            pr = Prompt(name=pname, fn=f, description=description or (f.__doc__ or "").strip(),
                        arguments=args, is_async=_is_async(f))
            self._prompts[pname] = pr
            return f
        return deco(fn) if fn else deco

    # ---------- composition ----------
    def mount(self, app: "MakeMCP", prefix: str = "") -> "MakeMCP":
        """Mount another MakeMCP app (tools prefixed, resources/prompts merged)."""
        self._mounts.append((prefix, app))
        for n, t in app._tools.items():
            self._tools[f"{prefix}{n}" if prefix else n] = t
        for u, r in app._resources.items():
            self._resources[u] = r
        for n, p in app._prompts.items():
            self._prompts[f"{prefix}{n}" if prefix else n] = p
        return self

    def add_middleware(self, mw) -> "MakeMCP":
        self._middleware.append(mw)
        return self

    def on_startup(self, fn):
        self._on_startup.append(fn)
        return fn

    def on_shutdown(self, fn):
        self._on_shutdown.append(fn)
        return fn

    def import_server(self, dotted: str, prefix: str = ""):
        """Import tools from 'module:attr' or 'module.attr' path."""
        mod, _, attr = dotted.partition(":")
        if not attr:
            mod, _, attr = dotted.rpartition(".")
        import importlib
        m = importlib.import_module(mod)
        app = getattr(m, attr) if attr else m
        if isinstance(app, MakeMCP):
            return self.mount(app, prefix)
        # collect bare functions marked? just mount callables
        for n in dir(app):
            if n.startswith("_"):
                continue
            f = getattr(app, n)
            if callable(f) and hasattr(f, "__makemcp_tool__"):
                self._tools[n] = f.__makemcp_tool__
        return self

    # ---------- core execution (fast path, no serialization) ----------
    async def call_tool(self, name: str, args: dict | None = None, ctx: dict | None = None):
        ctx = ctx or {}
        t = self._tools.get(name)
        if t is None:
            raise ToolError(f"Unknown tool: {name}", code=-32602)
        args = dict(args or {})
        for mw in self._middleware:
            hook = getattr(mw, "on_call", None)
            if hook:
                r = await hook(ctx, name, args) if _is_async(hook) else hook(ctx, name, args)
                if r is not None:
                    return r
        # cache
        ckey = None
        if t.cache_ttl:
            try:
                ckey = (name, J.dumps(args).decode())
                v, hit = self._result_cache.get(ckey)
                if hit:
                    return v
            except Exception:
                ckey = None
        # bind + coerce
        try:
            sig = inspect.signature(t.fn)
            try:
                hints = typing.get_type_hints(t.fn)
            except Exception:
                hints = {}
            bound = {}
            for k, v in args.items():
                bound[k] = coerce(v, hints.get(k))
            coro = t.fn(**bound)
            if t.is_async:
                res = await asyncio.wait_for(coro, t.timeout) if t.timeout else await coro
            else:
                res = coro
                if inspect.isawaitable(res):
                    res = await res
        except TypeError as e:
            raise ToolError(f"Invalid arguments for '{name}': {e}", code=-32602)
        except MakeMCPError:
            raise
        except Exception as e:
            raise ToolError(f"{name} failed: {e}", data=traceback.format_exc(limit=3))
        if ckey:
            self._result_cache.set(ckey, res, ttl=t.cache_ttl)
        return res

    async def read_resource(self, uri: str, ctx: dict | None = None):
        r = self._resources.get(uri)
        if r is None:
            # prefix match for templated resources {x}
            for key, res in self._resources.items():
                if "{" in key:
                    import re
                    pat = re.sub(r"\{[^}]+\}", r"([^/]+)", key)
                    m = re.fullmatch(pat, uri)
                    if m:
                        r = res
                        break
            if r is None:
                raise ResourceError(f"Unknown resource: {uri}", code=-32602)
        try:
            out = r.fn(uri) if "uri" in inspect.signature(r.fn).parameters else r.fn()
            if r.is_async or inspect.isawaitable(out):
                out = await out
        except MakeMCPError:
            raise
        except Exception as e:
            raise ResourceError(f"resource {uri} failed: {e}")
        if isinstance(out, str):
            return [{"uri": uri, "mimeType": r.mimeType, "text": out}]
        if isinstance(out, dict):
            return [{**{"uri": uri, "mimeType": r.mimeType}, **out}]
        if isinstance(out, list):
            return out
        return [{"uri": uri, "mimeType": r.mimeType, "text": str(out)}]

    async def get_prompt(self, name: str, args: dict | None = None, ctx: dict | None = None):
        p = self._prompts.get(name)
        if p is None:
            raise PromptError(f"Unknown prompt: {name}", code=-32602)
        try:
            out = p.fn(**dict(args or {}))
            if p.is_async or inspect.isawaitable(out):
                out = await out
        except MakeMCPError:
            raise
        except Exception as e:
            raise PromptError(f"prompt {name} failed: {e}")
        if isinstance(out, str):
            return [{"role": "user", "content": {"type": "text", "text": out}}]
        return out if isinstance(out, list) else [{"role": "user", "content": {"type": "text", "text": str(out)}}]

    # ---------- JSON-RPC dispatch ----------
    def _ok(self, _id, result):
        return {"jsonrpc": "2.0", "id": _id, "result": result}

    def _err(self, _id, code, msg, data=None):
        e = {"code": code, "message": msg}
        if data is not None:
            e["data"] = data
        return {"jsonrpc": "2.0", "id": _id, "error": e}

    async def handle(self, msg: dict, ctx: dict | None = None) -> dict | None:
        """Handle one JSON-RPC message. Returns response dict or None (notification)."""
        ctx = ctx or {}
        _id = msg.get("id")
        method = msg.get("method", "")
        params = msg.get("params") or {}
        is_notify = _id is None and method.startswith("notifications/")
        try:
            for mw in self._middleware:
                hook = getattr(mw, "on_request", None)
                if hook:
                    r = await hook(ctx, method, params) if _is_async(hook) else hook(ctx, method, params)
                    if r is not None:
                        return self._ok(_id, r) if _id is not None else None
            if method == "initialize":
                return self._ok(_id, {
                    "protocolVersion": PROTOCOL_VERSION,
                    "capabilities": {"tools": {"listChanged": False},
                                     "resources": {"listChanged": False},
                                     "prompts": {"listChanged": False}},
                    "serverInfo": {"name": self.name, "version": self.version},
                    **({"instructions": self.instructions} if self.instructions else {}),
                })
            if method in ("notifications/initialized", "notifications/cancelled"):
                return None
            if method == "ping":
                return self._ok(_id, {})
            if method == "tools/list":
                return self._ok(_id, {"tools": [t.to_dict() for t in self._tools.values()]})
            if method == "tools/call":
                name = params.get("name", "")
                args = params.get("arguments") or {}
                res = await self.call_tool(name, args, ctx)
                return self._ok(_id, {"content": _result_to_content(res), "isError": False})
            if method == "resources/list":
                return self._ok(_id, {"resources": [r.to_dict() for r in self._resources.values()]})
            if method == "resources/read":
                items = await self.read_resource(params.get("uri", ""), ctx)
                return self._ok(_id, {"contents": _json_safe(items)})
            if method == "prompts/list":
                return self._ok(_id, {"prompts": [p.to_dict() for p in self._prompts.values()]})
            if method == "prompts/get":
                msgs = await self.get_prompt(params.get("name", ""), params.get("arguments") or {}, ctx)
                return self._ok(_id, {"messages": _json_safe(msgs)})
            return self._err(_id, -32601, f"Method not found: {method}")
        except MakeMCPError as e:
            if is_notify or _id is None:
                return None
            return self._err(_id, e.code, str(e), getattr(e, "data", None))
        except Exception as e:
            if is_notify or _id is None:
                return None
            return self._err(_id, -32603, f"Internal error: {e}")

    # ---------- transports ----------
    async def _run_stdio_async(self):
        """Async stdio (Unix fast path). Windows uses sync loop (see run())."""
        import sys
        loop = asyncio.get_running_loop()
        reader = asyncio.StreamReader()
        proto = asyncio.StreamReaderProtocol(reader)
        await loop.connect_read_pipe(lambda: proto, sys.stdin.buffer)
        wtransport, wproto = await loop.connect_write_pipe(asyncio.BaseProtocol, sys.stdout.buffer)
        writer = asyncio.StreamWriter(wtransport, wproto, reader, loop)
        while True:
            line = await reader.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = J.loads(line)
            except Exception:
                continue
            if isinstance(msg, list):
                out = [await self.handle(m) for m in msg]
                out = [o for o in out if o is not None]
                if out:
                    writer.write(J.dumps(out) + b"\n")
                    await writer.drain()
            else:
                resp = await self.handle(msg)
                if resp is not None:
                    writer.write(J.dumps(resp) + b"\n")
                    await writer.drain()

    def _run_stdio_sync(self):
        """Blocking cross-platform stdio loop (works on Windows)."""
        import sys
        stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        while True:
            line = stdin.readline()
            if not line:
                break
            line = line.strip()
            if not line:
                continue
            try:
                msg = J.loads(line)
            except Exception:
                continue
            try:
                if isinstance(msg, list):
                    out = loop.run_until_complete(
                        asyncio.gather(*[self.handle(m) for m in msg]))
                    out = [o for o in out if o is not None]
                    if out:
                        stdout.write(J.dumps(out) + b"\n")
                        stdout.flush()
                else:
                    resp = loop.run_until_complete(self.handle(msg))
                    if resp is not None:
                        stdout.write(J.dumps(resp) + b"\n")
                        stdout.flush()
            except Exception:
                continue

    def run(self, transport: str = "stdio", host: str = "127.0.0.1", port: int = 8000,
            path: str = "/mcp", log_level: str = "warning", **kw):
        """transport: stdio | http | sse  (http = streamable HTTP + SSE on same port)."""
        for f in self._on_startup:
            r = f()
            if inspect.isawaitable(r):
                asyncio.get_event_loop().run_until_complete(r) if not asyncio.get_event_loop().is_running() else None
        if transport == "stdio":
            import os
            if os.name == "nt":
                # Windows: ProactorEventLoop has no pipe support -> sync loop directly
                self._run_stdio_sync()
            else:
                try:
                    import uvloop
                    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
                except ImportError:
                    pass
                asyncio.run(self._run_stdio_async())
        elif transport in ("http", "sse", "streamable-http"):
            from .transports.http import serve_http
            serve_http(self, host=host, port=port, path=path, log_level=log_level, **kw)
        else:
            raise ValueError(f"unknown transport {transport}")

    # convenience alias
    def run_stdio(self):
        return self.run("stdio")
