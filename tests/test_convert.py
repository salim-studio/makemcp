"""Tests for makemcp.convert (app-to-MCP bridge). Stdlib only."""
import asyncio
import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

sys.path.insert(0, ".")

from makemcp.convert import (
    analyze_target,
    commands_to_app,
    config_to_app,
    openapi_to_app,
    python_to_app,
    render_server_module,
)

SAMPLE = "examples/sample_app.py"

# 1) Python source -----------------------------------------------------------
app = python_to_app(SAMPLE, name="sample")
names = sorted(app._tools)
assert names == ["add", "fetch_title", "shout"], names
assert app._tools["add"].schema["required"] == ["a", "b"]
assert app._tools["shout"].schema["properties"]["times"].get("default") == 1


async def _call(a, tool, args):
    return await a.call_tool(tool, args)


assert asyncio.run(_call(app, "add", {"a": 2, "b": 3})) == 5
assert asyncio.run(_call(app, "shout", {"text": "hi", "times": 2})) == "HI HI"

info = analyze_target(SAMPLE)
assert info["tool_count"] == 3 and info["name"].startswith("py:"), info
print("1) python source OK:", names)

# 2) Shell commands ----------------------------------------------------------
exe = sys.executable
cmd_app = commands_to_app([
    {"name": "greet", "cmd": f'"{exe}" -c "print(\'hi \' + \'{{who}}\')"',
     "description": "Greet someone"},
])
res = asyncio.run(_call(cmd_app, "greet", {"who": "Ada"}))
assert res["returncode"] == 0 and "hi Ada" in res["stdout"], res
print("2) command source OK:", res["stdout"].strip())

# 3) OpenAPI source (against a local stub) -----------------------------------
SPEC = {
    "openapi": "3.0.0",
    "info": {"title": "Stub"},
    "servers": [{"url": "http://127.0.0.1:8971"}],
    "paths": {
        "/users/{uid}": {
            "get": {
                "operationId": "getUser",
                "summary": "Get a user",
                "parameters": [
                    {"name": "uid", "in": "path", "required": True,
                     "schema": {"type": "string"}},
                    {"name": "verbose", "in": "query",
                     "schema": {"type": "boolean"}},
                ],
            }
        },
        "/users": {
            "post": {
                "summary": "Create a user",
                "requestBody": {"content": {"application/json": {"schema": {
                    "type": "object",
                    "required": ["name"],
                    "properties": {"name": {"type": "string"},
                                   "age": {"type": "integer"}},
                }}}},
            }
        },
    },
}

seen = {}


class Stub(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _ok(self, payload):
        body = json.dumps(payload).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        seen["get"] = self.path
        self._ok({"path": self.path})

    def do_POST(self):
        ln = int(self.headers.get("Content-Length") or 0)
        seen["post_body"] = json.loads(self.rfile.read(ln) or b"{}")
        seen["post_path"] = self.path
        self._ok({"created": True})


srv = ThreadingHTTPServer(("127.0.0.1", 8971), Stub)
threading.Thread(target=srv.serve_forever, daemon=True).start()

api = openapi_to_app(SPEC)
assert sorted(api._tools) == ["getUser", "post_users"], sorted(api._tools)
r1 = asyncio.run(_call(api, "getUser", {"uid": "u7", "verbose": True}))
assert r1["status"] == 200, r1
assert seen["get"] == "/users/u7?verbose=True", seen
r2 = asyncio.run(_call(api, "post_users", {"name": "Ada", "age": 36}))
assert r2["status"] == 200 and seen["post_body"] == {"name": "Ada", "age": 36}, (r2, seen)
srv.shutdown()
print("3) openapi source OK: path/query/body mapping verified")

# 4) Config + codegen ---------------------------------------------------------
cfg = {"name": "mixed", "sources": [
    {"kind": "python", "target": SAMPLE},
    {"kind": "command",
     "tools": [{"name": "pingit", "cmd": f'"{exe}" -c "print(1)"'}]},
]}
mixed = config_to_app(cfg)
assert len(mixed._tools) == 4, sorted(mixed._tools)

code = render_server_module(cfg)
assert "config_to_app" in code and '"mixed"' in code
ns: dict = {}
exec(compile(code, "<generated>", "exec"), ns)
assert sorted(ns["mcp"]._tools) == sorted(mixed._tools)
print("4) config + codegen OK:", sorted(mixed._tools))

print("ALL CONVERT TESTS PASSED")
