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

## Convert any app into MCP

Already have an application? Turn it into an MCP server without rewriting it:

```bash
# Python file / module / function -> MCP tools
makemcp convert app.py --name my-mcp -o server_mcp.py --run

# REST API described by OpenAPI -> one tool per endpoint
makemcp convert https://api.example.com/openapi.json --base-url https://api.example.com

# GitHub repo -> one tool per public function (cached locally, no git needed)
makemcp convert psf/requests --name req-mcp -o server_mcp.py
makemcp convert https://github.com/pallets/click/tree/main/src --ref main

# Mixed sources via a JSON config file
makemcp convert config.json --kind config -o server_mcp.py
```

`config.json` example:

```json
{
  "name": "mixed",
  "sources": [
    {"kind": "python", "target": "app.py"},
    {"kind": "openapi", "target": "https://api.example.com/openapi.json"},
    {"kind": "command", "tools": [
      {"name": "disk", "cmd": "df -h {path}", "description": "Show disk usage"}
    ]}
  ]
}
```

Or use the browser interface — analyze sources, test-call tools, and download
a runnable `server.py`, all visually:

```bash
makemcp ui --port 8080   # then open http://127.0.0.1:8080
```

The same converters are available in Python:

```python
from makemcp import python_to_app, openapi_to_app, commands_to_app, github_to_app

app = python_to_app("app.py")                 # functions -> tools
api = openapi_to_app("openapi.json")          # endpoints -> tools
cli = commands_to_app([{"name": "disk", "cmd": "df -h"}])
hub = github_to_app("psf/requests", subdir="src")  # repo -> tools
```

> GitHub repos are downloaded as tarballs (no `git` required) and cached under
> `~/.cache/makemcp` (override with `MAKEMCP_CACHE`, `--refresh` re-downloads).
> Test files are skipped by default (`--include-tests` to keep them).
> Only convert repositories you trust — Python sources are imported locally.
>
> Dependency-resilient extraction: files needing uninstalled third-party
> packages are still converted (missing packages are stubbed at import time),
> and every affected tool reports its requirements — shown in Analyze output
> (`pip install ...`) and in the generated `server.py` header. Repos without
> any Python code are refused with a message describing what was found.

## Project layout

```
makemcp/            core package (server, client, schema, transports, middleware, auth, cache, CLI)
makemcp/convert.py  app-to-MCP bridge (python / openapi / command / config sources)
makemcp/ui.py       browser-based converter interface
assets/logo.svg     brand logo
examples/           demo server + sample convertible app
tests/              smoke + performance + conversion tests
```

## Deploy on Vercel

The repo ships with a dependency-free ASGI entrypoint (`api/index.py`), so it
deploys as-is — no adapter or extra service needed:

```bash
vercel --prod
```

What you get on your `*.vercel.app` domain:

| Route | Purpose |
|-------|---------|
| `GET /` | converter web UI (analyze → test → generate `server.py`) |
| `GET /health` | health check |
| `POST /mcp` | JSON-RPC 2.0 to the bundled demo MCP server (single or batch) |
| `GET /mcp` | server info + tool list |
| `POST /api/analyze|test|generate` | converter backend |

```bash
curl -X POST https://YOUR-APP.vercel.app/mcp \
  -H 'Content-Type: application/json' \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/call",
       "params":{"name":"add","arguments":{"a":20,"b":22}}}'
```

> Note: serverless functions are stateless and short-lived — ideal for the
> converter UI and request/response MCP calls. Long-lived transports
> (stdio, persistent SSE streams) still need a regular server
> (`mcp.run("http")` on any VPS/container).

## License

MIT — Copyright (c) 2026 salim-slimani. See [LICENSE](LICENSE).
