"""Demo server showcasing makemcp tools, resources and prompts."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from makemcp import MakeMCP

mcp = MakeMCP("Demo", instructions="demo server")


@mcp.tool
def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


@mcp.tool(cache_ttl=30)
def greet(name: str, greeting: str = "Hello") -> str:
    """Greet someone (result cached for 30s)."""
    return f"{greeting}, {name}!"


@mcp.resource("docs://readme", description="readme text")
def readme() -> str:
    return "# makemcp demo resource"


@mcp.prompt
def review(code: str) -> str:
    """Build a code-review prompt."""
    return f"Review this code and list any bugs:\n{code}"


if __name__ == "__main__":
    transport = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if transport == "http":
        mcp.run("http", port=8000)
    else:
        mcp.run("stdio")
