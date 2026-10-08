"""Demo server showing everything makemcp does (like fastmcp example, faster)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from makemcp import MakeMCP

mcp = MakeMCP("Demo 🚀", instructions="demo server")


@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


@mcp.tool(cache_ttl=30)
def greet(name: str, lang: str = "ar") -> str:
    """Greet someone (cached 30s)."""
    return {"ar": f"أهلاً {name} 👋", "en": f"Hello {name} 👋",
            "fr": f"Bonjour {name} 👋"}.get(lang, f"Hello {name}")


@mcp.resource("docs://readme", description="readme text")
def readme() -> str:
    return "# makemcp demo resource"


@mcp.prompt
def review(code: str) -> str:
    """Ask for a code review prompt."""
    return f"Review this code and list bugs:\n{code}"


if __name__ == "__main__":
    import sys
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "http":
        mcp.run("http", port=8000)
    else:
        mcp.run("stdio")
