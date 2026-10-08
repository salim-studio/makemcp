# makemcp ⚡

**أسرع، أخف، وأكمل بديل عربي-عملي لـ `fastmcp`** — ابنِ خوادم وعملاء MCP في بايثون بدون أي اعتماديات إجبارية.

> مثل fastmcp تماماً: `@mcp.tool` / `@mcp.resource` / `@mcp.prompt` + `mcp.run()` — لكن:
> - **صفر اعتماديات** (stdlib فقط) → تثبيت فوري، صور Docker صغيرة
> - **أسرع**: دوال sync تعمل مباشرة بدون hop، schemas محسوبة مسبقاً، JSON عبر `orjson` إن وُجد، `uvloop` إن وُجد
> - **متكامل**: server + client + transports (stdio / HTTP streamable / SSE) + middleware + auth + cache + rate-limit + mount + CLI + فحص

## تثبيت

```bash
pip install makemcp
# للسرعة القصوى (اختياري):
pip install "makemcp[speed]"  # orjson + uvloop
```

## أسرع مثال (مثل fastmcp)

```python
from makemcp import MakeMCP

mcp = MakeMCP("Demo 🚀")

@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b

if __name__ == "__main__":
    mcp.run()  # stdio (لـ Claude Desktop / أي عميل MCP)
```

```bash
python server.py              # stdio
python -m makemcp run server.py --transport http --port 8000   # HTTP
python -m makemcp inspect server.py
```

## كل المزايا في مثال واحد

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
    return f"Review this:\n{code}"

# middleware / auth / limits
mcp.add_middleware(LoggingMiddleware())
mcp.add_middleware(RateLimitMiddleware(max_calls=60, window=60.0))
# mcp.add_middleware(bearer_auth("SECRET"))

# دمج سيرفرات (composition مثل fastmcp.mount)
# mcp.mount(other, prefix="other_")

mcp.run("http", host="127.0.0.1", port=8000)  # POST /mcp + GET /mcp (SSE) + GET /health
```

## العميل

```python
import asyncio
from makemcp import MakeMCPClient

async def main():
    c = MakeMCPClient()
    await c.connect_http("http://127.0.0.1:8000/mcp")
    # أو: await c.connect_stdio(["python", "server.py"])
    # أو داخل نفس العملية (الأسرع): await c.connect_direct(mcp)
    print(await c.list_tools())
    print(await c.call_tool("add", {"a": 2, "b": 3}))
    print(await c.read_resource("docs://readme"))
    print(await c.get_prompt("review", {"code": "x=1"}))

asyncio.run(main())
```

## النقل (Transports)

| النقل | السيرفر | العميل |
|------|---------|--------|
| stdio | `mcp.run()` | `connect_stdio([...])` |
| Streamable HTTP | `mcp.run("http", port=8000)` → `POST /mcp` | `connect_http(url)` |
| SSE | `GET /mcp` / `GET /sse` | أي عميل SSE |
| مباشر | — | `connect_direct(app)` (بدون تسلسل، للاختبارات والسرعة) |

## لماذا أسرع من fastmcp؟

1. لا pydantic/startup ثقيل — توليد schema بـ `typing` فقط + cache.
2. الدوال المتزامنة تُنفَّذ inline بدون threadpool.
3. `orjson`/`uvloop` تُستخدم تلقائياً إن وُجدت.
4. TTL cache اختياري لكل أداة (`cache_ttl=`).
5. عميل HTTP بـ `urllib` + `asyncio.to_thread` بدون جلسات ثقيلة.

## CLI

```bash
makemcp run server.py --transport stdio
makemcp run server.py --transport http --port 8000
makemcp inspect server.py
makemcp version
```

## الترخيص

MIT
