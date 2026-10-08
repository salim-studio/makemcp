<p align="center">
  <img src="assets/logo.svg" alt="makemcp logo" width="140" />
</p>

<h1 align="center">makemcp</h1>

<p align="center"><strong>Build MCP servers and clients — dependency-free.</strong></p>

<p align="center">
  <img src="https://img.shields.io/badge/python-%3E%3D3.9-blue" alt="Python >= 3.9" />
  <img src="https://img.shields.io/badge/dependencies-zero-brightgreen" alt="Zero dependencies" />
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="MIT license" />
  <img src="https://img.shields.io/badge/protocol-MCP_2024--11--05-orange" alt="MCP protocol" />
</p>

---

`makemcp` is a minimal Python framework for the [Model Context Protocol (MCP)](https://modelcontextprotocol.io/).
Define tools, resources and prompts as plain Python functions — schemas, validation
and documentation are generated automatically. Serve them over **stdio**,
**streamable HTTP** or **SSE**, and connect to any server with the built-in client.

- **Zero mandatory dependencies** — standard library only. Instant install, tiny images.
- **Async-first, sync-friendly** — plain functions run inline, coroutines are awaited directly.
- **Complete** — server + client + transports + middleware + auth + caching + rate limiting + composition + CLI.

## Install

```bash
pip install makemcp
# Maximum speed (optional C-accelerated JSON / event loop):
pip install "makemcp[speed]"
```

## Quickstart

```python
from makemcp import MakeMCP

mcp = MakeMCP("Demo")

@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

if __name__ == "__main__":
    mcp.run()  # stdio transport (works with any MCP client)
```

```bash
python server.py                                            # stdio
python -m makemcp run server.py --transport http --port 8000  # HTTP
python -m makemcp inspect server.py                           # list capabilities
```

## Everything in one example

```python
from makemcp import MakeMCP
from makemcp.middleware import LoggingMiddleware, RateLimitMiddleware, bearer_auth

mcp = MakeMCP("MyAPI", version="1.0.0", instructions="...")

@mcp.tool(cache_ttl=30, timeout=5.0, tags={"math"})
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

@mcp.resource("docs://readme", description="readme")
def readme() -> str:
    return "# hello"

@mcp.prompt
def review(code: str) -> str:
    return f"Review this code and list any bugs:\n{code}"

# Middleware / auth / limits
mcp.add_middleware(LoggingMiddleware())
mcp.add_middleware(RateLimitMiddleware(max_calls=60, window=60.0))
# mcp.add_middleware(bearer_auth("SECRET"))

# Compose servers by mounting them
# mcp.mount(other, prefix="other_")

mcp.run("http", host="127.0.0.1", port=8000)  # POST /mcp + GET /mcp (SSE) + GET /health
```

## Client

```python
import asyncio
from makemcp import MakeMCPClient

async def main():
    c = MakeMCPClient()
    await c.connect_http("http://127.0.0.1:8000/mcp")
    # or: await c.connect_stdio(["python", "server.py"])
    # or in-process (fastest, no serialization): await c.connect_direct(mcp)
    print(await c.list_tools())
    print(await c.call_tool("add", {"a": 2, "b": 3}))
    print(await c.read_resource("docs://readme"))
    print(await c.get_prompt("review", {"code": "x = 1"}))

asyncio.run(main())
```

## Transports

| Transport | Server | Client |
|-----------|--------|--------|
| stdio | `mcp.run()` | `connect_stdio([...])` |
| Streamable HTTP | `mcp.run("http", port=8000)` → `POST /mcp` | `connect_http(url)` |
| SSE | `GET /mcp` / `GET /sse` | any SSE-capable client |
| In-process | — | `connect_direct(app)` (no serialization; ideal for tests) |

## Why fast?

1. No heavy validation layer — schemas are generated from `typing` hints once and cached.
2. Synchronous functions execute inline, with no threadpool hop.
3. `orjson` / `uvloop` are used automatically when installed.
4. Optional per-tool TTL result cache (`cache_ttl=`).
5. Lightweight HTTP client built on `urllib` — no heavy session objects.

## CLI

```bash
makemcp run server.py --transport stdio
makemcp run server.py --transport http --port 8000
makemcp inspect server.py
makemcp version
```

## Project layout

```
makemcp/            core package (server, client, schema, transports, middleware, auth, cache, CLI)
assets/logo.svg     brand logo
examples/           demo server
tests/              smoke + performance tests
```

## License

MIT — Copyright (c) 2026 salim-slimani. See [LICENSE](LICENSE).
