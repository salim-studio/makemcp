"""Smoke + perf tests for makemcp (stdlib only)."""
import asyncio
import sys
import time

sys.path.insert(0, ".")

from makemcp import MakeMCP, MakeMCPClient


def build():
    mcp = MakeMCP("Test")

    @mcp.tool
    def add(a: int, b: int) -> int:
        """Add"""
        return a + b

    @mcp.resource("data://x")
    def x() -> str:
        return "hello"

    @mcp.prompt
    def p(code: str) -> str:
        return f"rev:{code}"

    return mcp


async def main():
    mcp = build()
    c = MakeMCPClient()
    await c.connect_direct(mcp)
    assert await c.ping() == {}
    tools = await c.list_tools()
    assert any(t["name"] == "add" for t in tools), tools
    out = await c.call_tool("add", {"a": 2, "b": 3})
    assert out[0]["text"] == "5", out
    res = await c.read_resource("data://x")
    assert "hello" in str(res)
    pr = await c.get_prompt("p", {"code": "z"})
    assert "rev:z" in str(pr)

    # raw dispatch perf (in-process, no serialization)
    N = 20000
    t0 = time.perf_counter()
    for _ in range(N):
        await mcp.call_tool("add", {"a": 1, "b": 2})
    dt = time.perf_counter() - t0
    print(f"OK functional. {N} direct calls in {dt:.3f}s = {N/dt:,.0f} calls/s")
    # JSON-RPC dispatch perf
    N2 = 5000
    msg = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
           "params": {"name": "add", "arguments": {"a": 1, "b": 2}}}
    t0 = time.perf_counter()
    for _ in range(N2):
        await mcp.handle(dict(msg))
    dt = time.perf_counter() - t0
    print(f"{N2} handle() in {dt:.3f}s = {N2/dt:,.0f} req/s")
    print("ALL TESTS PASSED")


asyncio.run(main())
