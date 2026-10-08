"""makemcp CLI: run / inspect / dev (zero deps, argparse only)."""
from __future__ import annotations
import argparse
import importlib.util
import sys


def _load(target: str):
    """target: file.py[:app] or module[:app]"""
    name, _, attr = target.partition(":")
    attr = attr or "mcp"
    if name.endswith(".py"):
        spec = importlib.util.spec_from_file_location("_mkcli", name)
        mod = importlib.util.module_from_spec(spec)
        sys.modules["_mkcli"] = mod
        spec.loader.exec_module(mod)
    else:
        mod = importlib.import_module(name)
    app = getattr(mod, attr, None) or getattr(mod, "app", None) or getattr(mod, "mcp", None)
    if app is None:
        raise SystemExit(f"no app '{attr}' found in {name} (tried {attr}/app/mcp)")
    return app


def main(argv=None):
    p = argparse.ArgumentParser("makemcp", description="MakeMCP: fast MCP servers & clients")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run a server file")
    r.add_argument("target", help="server.py[:app]")
    r.add_argument("--transport", default="stdio", choices=["stdio", "http", "sse"])
    r.add_argument("--host", default="127.0.0.1")
    r.add_argument("--port", type=int, default=8000)
    r.add_argument("--path", default="/mcp")

    i = sub.add_parser("inspect", help="list tools/resources/prompts")
    i.add_argument("target", help="server.py[:app]")

    v = sub.add_parser("version", help="print version")

    a = p.parse_args(argv)
    if a.cmd == "version":
        from . import __version__
        print(__version__)
        return
    if a.cmd == "inspect":
        import asyncio
        app = _load(a.target)
        async def go():
            print(f"== {app.name} v{app.version} ==")
            for t in app._tools.values():
                print(f"[tool] {t.name}: {t.description} schema={t.schema}")
            for u, res in app._resources.items():
                print(f"[resource] {u}: {res.description}")
            for n, pr in app._prompts.items():
                print(f"[prompt] {n}: {pr.description} args={pr.arguments}")
        asyncio.run(go())
        return
    if a.cmd == "run":
        app = _load(a.target)
        app.run(transport=a.transport, host=a.host, port=a.port, path=a.path)
        return


if __name__ == "__main__":
    main()
