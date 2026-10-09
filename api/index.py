"""Vercel serverless entrypoint: ``app`` is a dependency-free ASGI application.

Routes:
    GET  /            -> converter web UI
    GET  /health      -> {"ok": true}
    GET  /api/debug   -> request-scope diagnostics (method/path/headers)
    POST /api/analyze /api/test /api/generate -> converter backend
    POST /mcp         -> JSON-RPC 2.0 to the bundled demo MCP server
    GET  /mcp         -> server info + tool list (discovery)
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from makemcp.ui import api_analyze, api_generate, api_test, page_html  # noqa: E402

_DEMO = None


def _demo_app():
    global _DEMO
    if _DEMO is None:
        from makemcp.convert import python_to_app

        root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        _DEMO = python_to_app(os.path.join(root, "examples", "sample_app.py"),
                              name="makemcp-demo")
    return _DEMO


def _json_body(obj) -> bytes:
    try:
        return json.dumps(obj, ensure_ascii=False).encode()
    except (TypeError, ValueError):
        return json.dumps({"result": str(obj)}).encode()


async def app(scope, receive, send):
    if scope.get("type") != "http":
        return
    method = scope.get("method", "GET").upper()
    # Vercel may hand us the browser URL path ("/mcp") or the function
    # mount path ("/api/index", "/api/index/mcp"). Normalize both to the
    # browser-style path so routing works either way.
    # NOTE: only the full "/api/index" mount prefix is stripped — never a
    # bare "/api", because the converter backend really lives there
    # ("/api/analyze", "/api/test", "/api/generate").
    full = (scope.get("root_path") or "") + (scope.get("path") or "/")
    path = full
    if path == "/api/index" or path.startswith("/api/index/"):
        path = path[len("/api/index"):] or "/"
    path = path.rstrip("/") or "/"

    body = b""
    while True:
        event = await receive()
        body += event.get("body", b"")
        if not event.get("more_body"):
            break

    async def respond(status: int, payload: bytes, ctype: str):
        await send({"type": "http.response.start",
                    "status": status,
                    "headers": [(b"content-type", ctype.encode()),
                                (b"content-length", str(len(payload)).encode()),
                                (b"access-control-allow-origin", b"*")]})
        await send({"type": "http.response.body", "body": payload})

    ok = lambda obj: respond(200, _json_body(obj), "application/json")  # noqa: E731
    err = lambda msg: respond(200, _json_body({"error": str(msg)}),  # noqa: E731
                              "application/json")

    try:
        if method == "GET" and path in ("/", "/index.html"):
            return await respond(200, page_html().encode(),
                                 "text/html; charset=utf-8")
        if method == "GET" and path == "/health":
            return await ok({"ok": True})
        if method == "GET" and path == "/api/debug":
            headers = {k.decode(errors="replace"): v.decode(errors="replace")
                       for k, v in scope.get("headers", [])}
            try:
                from makemcp import __version__ as _v
            except Exception:
                _v = "dev"
            return await ok({
                "makemcp": _v,
                "method": method,
                "path": scope.get("path"),
                "root_path": scope.get("root_path"),
                "query": (scope.get("query_string") or b"").decode(),
                "headers": {k: v for k, v in headers.items()
                            if k.lower().startswith(
                                ("x-vercel", "x-matched", "x-forwarded",
                                 "forwarded", "host"))},
            })
        if method == "GET" and path == "/mcp":
            demo = _demo_app()
            return await ok({"name": demo.name, "version": demo.version,
                             "tools": [t.to_dict() for t in demo._tools.values()]})
        if method == "POST" and path in ("/api/analyze", "/api/test",
                                         "/api/generate", "/mcp"):
            try:
                payload = json.loads(body.decode("utf-8") or "{}")
            except json.JSONDecodeError:
                return await err("invalid JSON")
            if path == "/api/analyze":
                return await ok(api_analyze(payload.get("config") or {}))
            if path == "/api/generate":
                return await ok(api_generate(payload.get("config") or {}))
            if path == "/api/test":
                res = await api_test(payload.get("config") or {},
                                     payload.get("tool", ""),
                                     payload.get("args") or {})
                return await respond(200, _json_body({"result": res}),
                                     "application/json")
            # POST /mcp -> JSON-RPC dispatch
            demo = _demo_app()
            if isinstance(payload, list):
                out = [await demo.handle(m) for m in payload]
                return await ok([o for o in out if o is not None])
            resp = await demo.handle(payload)
            return await ok(resp if resp is not None else {})
        return await respond(404, _json_body({"error": "not found"}),
                             "application/json")
    except Exception as e:
        return await err(e)
