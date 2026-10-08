"""Tests for the Vercel ASGI entrypoint (api/index.py). Stdlib only.

Covers both routing styles: browser URL paths ("/mcp") and function mount
paths ("/api/index/mcp"), since serverless platforms differ here.
"""
import asyncio
import importlib.util
import json
import sys

sys.path.insert(0, ".")

spec = importlib.util.spec_from_file_location(
    "vercel_entry", "api/index.py")
entry = importlib.util.module_from_spec(spec)
spec.loader.exec_module(entry)


async def _call(method, path, body=None, root_path=""):
    msgs = []
    state = {"sent": False}
    body_b = json.dumps(body).encode() if body is not None else b""

    async def receive():
        if not state["sent"]:
            state["sent"] = True
            return {"type": "http.request", "body": body_b, "more_body": False}
        await asyncio.sleep(3600)  # pragma: no cover

    async def send(m):
        msgs.append(m)

    await entry.app({"type": "http", "method": method, "path": path,
                     "root_path": root_path}, receive, send)
    start = next(m for m in msgs if m["type"] == "http.response.start")
    data = b"".join(m.get("body", b"")
                    for m in msgs if m["type"] == "http.response.body")
    return start["status"], data


async def main():
    # UI page via browser path and via function mount path
    for p in ("/", "/api/index", "/api/index/"):
        s, d = await _call("GET", p)
        assert s == 200 and "makemcp converter" in d.decode(), (p, s, d[:80])
    print("UI routes OK")

    # MCP discovery + call via both styles
    s, d = await _call("GET", "/mcp")
    assert [t["name"] for t in json.loads(d)["tools"]] == ["add", "fetch_title", "shout"]
    s, d = await _call("GET", "/api/index/mcp")
    assert json.loads(d)["tool_count"] if "tool_count" in json.loads(d) else True
    assert "tools" in json.loads(d), d[:80]
    print("discovery routes OK")

    rpc = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": "add", "arguments": {"a": 20, "b": 22}}}
    for p in ("/mcp", "/api/index/mcp"):
        s, d = await _call("POST", p, rpc)
        assert json.loads(d)["result"]["content"][0]["text"] == "42", (p, d[:120])
    print("RPC routes OK")

    # root_path style (some servers split mount point into root_path)
    s, d = await _call("GET", "/", root_path="/api/index")
    assert s == 200 and "makemcp converter" in d.decode()
    print("root_path style OK")

    s, d = await _call("GET", "/nope")
    assert s == 404 and json.loads(d) == {"error": "not found"}
    print("unknown routes still 404")

    # converter backend still reachable through the mount path
    cfg = {"config": {"name": "t", "sources": [
        {"kind": "python", "target": "examples/sample_app.py"}]}}
    s, d = await _call("POST", "/api/index/api/analyze", cfg)
    assert json.loads(d)["tool_count"] == 3, d[:120]
    print("API routes OK")

asyncio.run(main())
print("ALL VERCEL TESTS PASSED")
