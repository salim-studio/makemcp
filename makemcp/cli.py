"""makemcp CLI: run / inspect / convert / ui / version (zero deps, argparse only)."""
from __future__ import annotations
import argparse
import importlib.util
import sys

from .banner import COPYRIGHT


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
    p = argparse.ArgumentParser(
        "makemcp",
        description="MakeMCP: build MCP servers & clients.",
        epilog=f"{COPYRIGHT} · MIT",
    )
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

    c = sub.add_parser("convert", help="convert an app into an MCP server")
    c.add_argument("target", help="app.py[:func], module, OpenAPI URL/JSON file, or config.json")
    c.add_argument("--kind", default="auto",
                   choices=["auto", "python", "openapi", "config"],
                   help="source kind (auto-detected by default)")
    c.add_argument("--name", default=None, help="MCP server name")
    c.add_argument("--prefix", default="", help="prefix for converted tool names")
    c.add_argument("--base-url", default=None, help="OpenAPI base URL override")
    c.add_argument("-o", "--output", default=None,
                   help="write a standalone server.py to this path")
    c.add_argument("--run", action="store_true", help="run the converted server")
    c.add_argument("--transport", default="stdio", choices=["stdio", "http", "sse"])
    c.add_argument("--port", type=int, default=8000)

    u = sub.add_parser("ui", help="open the browser-based app-to-MCP converter")
    u.add_argument("--host", default="127.0.0.1")
    u.add_argument("--port", type=int, default=8080)

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
    if a.cmd == "ui":
        from .ui import serve_ui
        serve_ui(host=a.host, port=a.port)
        return
    if a.cmd == "convert":
        from .convert import analyze_target, config_to_app, convert_target
        import json as _json
        import os as _os
        kw: dict = {}
        if a.name:
            kw["name"] = a.name
        if a.prefix:
            kw["prefix"] = a.prefix
        if a.base_url and a.kind in ("auto", "openapi"):
            kw["base_url"] = a.base_url
        if a.kind == "config":
            with open(a.target, encoding="utf-8") as f:
                cfg = _json.load(f)
            if a.name:
                cfg["name"] = a.name
            app = config_to_app(cfg)
            summary = {"name": app.name, "tool_count": len(app._tools),
                       "tools": sorted(app._tools)}
        else:
            app = convert_target(a.target, kind=a.kind, **kw)
            summary = analyze_target(a.target, kind=a.kind, **kw)
        print(f"Converted '{summary['name']}': {summary['tool_count']} tool(s)")
        for t in summary["tools"]:
            print(f"  [tool] {t['name'] if isinstance(t, dict) else t}")
        if a.output:
            if a.kind == "config":
                with open(a.target, encoding="utf-8") as f:
                    cfg = _json.load(f)
            else:
                src = {"kind": a.kind if a.kind != "auto" else "auto",
                       "target": a.target, **kw}
                cfg = {"name": summary["name"], "sources": [src]}
            from .convert import render_server_module
            with open(a.output, "w", encoding="utf-8") as f:
                f.write(render_server_module(cfg))
            print(f"Wrote {_os.path.abspath(a.output)}")
        if a.run:
            app.run(transport=a.transport, port=a.port)
        return


if __name__ == "__main__":
    main()
