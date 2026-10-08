"""Sample application used to demonstrate app-to-MCP conversion.

Convert it with:
    python -m makemcp convert examples/sample_app.py --run
"""


def add(a: int, b: int) -> int:
    """Add two numbers"""
    return a + b


def shout(text: str, times: int = 1) -> str:
    """Repeat text in uppercase."""
    return " ".join([text.upper()] * max(1, times))


async def fetch_title(url: str) -> str:
    """Pretend to fetch a page title (async example)."""
    return f"Title of {url}"


def _helper():
    return "not converted (private)"
