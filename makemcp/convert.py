"""App-to-MCP bridge: convert existing applications into MCP servers.

Supported sources:
- Python files / modules / single functions  -> one tool per public function
- OpenAPI (URL, JSON file or dict)            -> one tool per API operation
- Shell command templates                    -> one tool per command
- JSON config files mixing any of the above

Everything is stdlib-only. Converted apps are regular ``MakeMCP`` instances,
so middleware, auth, caching and all transports keep working.
"""
from __future__ import annotations

import inspect
import json
import keyword
import re
import shlex
import string
import urllib.parse
import urllib.error
import urllib.request
from typing import Any

_OPENAPI_PY_TYPES = {
    "string": "str", "integer": "int", "number": "float", "boolean": "bool",
    "array": "list", "object": "dict",
}


def _ident(name: str) -> str:
    """Make a string safe to use as a Python identifier / tool name."""
    s = re.sub(r"[^0-9a-zA-Z_]", "_", str(name)).strip("_")
    if not s:
        s = "tool"
    if s[0].isdigit():
        s = "n_" + s
    if keyword.iskeyword(s):
        s = s + "_"
    return s


def _op_name(method: str, path: str, operation_id: str | None = None) -> str:
    if operation_id:
        return _ident(operation_id)
    name = method.lower() + "_" + path.strip("/")
    name = re.sub(r"\{([^}]+)\}", r"by_\1", name)
    return _ident(name)


# --------------------------------------------------------------------------
# Python sources
# --------------------------------------------------------------------------

def load_python_target(target: str):
    """Load ``file.py[:attr]`` or ``package.module[:attr]``.

    Returns ``(module, obj)`` where *obj* is the attribute when given,
    otherwise the module itself.
    """
    import importlib.util

    import os
    # Split "target[:attr]" on the LAST colon so Windows paths (C:\...)
    # are not cut at the drive letter.
    if os.path.isfile(target):
        name, attr = target, ""
    elif ":" in target:
        name, attr = target.rsplit(":", 1)
    else:
        name, attr = target, ""
    if name.endswith(".py"):
        import os
        path = os.path.abspath(name)
        mod_name = "_mkconv_" + re.sub(r"\W", "_", os.path.basename(path))
        spec = importlib.util.spec_from_file_location(mod_name, path)
        if spec is None or spec.loader is None:
            raise ValueError(f"cannot load python file: {target}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    else:
        import importlib
        mod = importlib.import_module(name)
    if attr:
        try:
            return mod, getattr(mod, attr)
        except AttributeError:
            raise ValueError(f"{target}: attribute '{attr}' not found")
    return mod, mod


def iter_python_functions(obj, include_imported: bool = False,
                          include_private: bool = False):
    """Yield ``(name, fn)`` for public functions found on a module/object."""
    mod_name = getattr(obj, "__name__", None)
    seen = set()
    for name in dir(obj):
        if not include_private and name.startswith("_"):
            continue
        try:
            fn = getattr(obj, name)
        except Exception:
            continue
        if not callable(fn) or isinstance(fn, type):
            continue
        if inspect.isclass(fn):
            continue
        try:
            inspect.signature(fn)
        except (TypeError, ValueError):
            continue
        if not include_imported and inspect.isfunction(fn):
            if mod_name and getattr(fn, "__module__", None) not in (None, mod_name):
                continue
        if id(fn) in seen:
            continue
        seen.add(id(fn))
        yield name, fn


def python_to_app(target: str, name: str | None = None,
                  include_imported: bool = False,
                  include_private: bool = False,
                  prefix: str = ""):
    """Convert a Python file/module/function into a ``MakeMCP`` app."""
    from .server import MakeMCP

    mod, obj = load_python_target(target)
    app = MakeMCP(name or f"py:{target}")
    if callable(obj) and not inspect.ismodule(obj) and not inspect.isclass(obj):
        app.tool(obj, name=f"{prefix}{getattr(obj, '__name__', 'run')}")
        return app
    count = 0
    for fname, fn in iter_python_functions(obj, include_imported, include_private):
        app.tool(fn, name=f"{prefix}{fname}")
        count += 1
    if count == 0:
        raise ValueError(f"no convertible functions found in: {target}")
    return app


# --------------------------------------------------------------------------
# OpenAPI sources
# --------------------------------------------------------------------------

def load_openapi(target) -> dict:
    """Load an OpenAPI spec from a URL, a JSON file path, or a dict."""
    if isinstance(target, dict):
        return target
    if isinstance(target, str) and re.match(r"^https?://", target):
        with urllib.request.urlopen(target, timeout=30) as r:
            text = r.read().decode("utf-8", "replace")
        return json.loads(text)
    with open(target, encoding="utf-8") as f:
        text = f.read()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        try:
            import yaml  # optional
            return yaml.safe_load(text)
        except ImportError:
            raise ValueError("YAML OpenAPI files need PyYAML: pip install pyyaml")


def _openapi_params(operation: dict) -> list[dict]:
    """Flatten path/query/body inputs of one operation into tool params."""
    params: list[dict] = []
    for p in operation.get("parameters", []):
        schema = p.get("schema", {}) or {}
        params.append({
            "name": _ident(p["name"]), "raw": p["name"],
            "in": p.get("in", "query"),
            "required": bool(p.get("required", p.get("in") == "path")),
            "pytype": _OPENAPI_PY_TYPES.get(schema.get("type", "string"), "str"),
            "default": schema.get("default"),
        })
    body = (operation.get("requestBody") or {}).get("content", {}).get("application/json", {})
    bschema = body.get("schema", {}) or {}
    required_body = set(bschema.get("required", []) or [])
    for pname, pschema in (bschema.get("properties", {}) or {}).items():
        params.append({
            "name": _ident(pname), "raw": pname, "in": "body",
            "required": pname in required_body,
            "pytype": _OPENAPI_PY_TYPES.get((pschema or {}).get("type", "string"), "str"),
            "default": (pschema or {}).get("default"),
        })
    # de-duplicate, keeping first occurrence
    seen, out = set(), []
    for pr in params:
        if pr["name"] not in seen:
            seen.add(pr["name"])
            out.append(pr)
    return out


def _build_executor(base_url: str, method: str, path_tpl: str,
                    params: list[dict], headers: dict, timeout: float):
    path_names = {p["raw"] for p in params if p["in"] == "path"}
    query_names = {p["raw"] for p in params if p["in"] == "query"}
    body_names = {p["raw"] for p in params if p["in"] == "body"}
    by_name = {p["name"]: p for p in params}

    def _execute(passed: dict) -> dict:
        raw = {by_name[k]["raw"]: v for k, v in passed.items() if k in by_name}
        url = base_url.rstrip("/") + path_tpl
        for pname in path_names:
            url = url.replace("{" + pname + "}",
                              urllib.parse.quote(str(raw.get(pname, "")), safe=""))
        qs = {k: v for k, v in raw.items()
              if k in query_names and v is not None}
        if qs:
            url += ("&" if "?" in url else "?") + urllib.parse.urlencode(qs, doseq=True)
        data = None
        if body_names:
            payload = {k: v for k, v in raw.items()
                       if k in body_names and v is not None}
            data = json.dumps(payload).encode()
        req_headers = dict(headers)
        if data is not None:
            req_headers.setdefault("Content-Type", "application/json")
        req = urllib.request.Request(url, data=data, headers=req_headers, method=method.upper())
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                raw_body = r.read().decode("utf-8", "replace")
                try:
                    return {"status": r.status, "data": json.loads(raw_body)}
                except json.JSONDecodeError:
                    return {"status": r.status, "data": raw_body}
        except Exception as e:
            body = ""
            try:
                if isinstance(e, urllib.error.HTTPError):
                    body = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            return {"status": getattr(e, "code", 0), "error": str(e), "data": body}

    return _execute


def openapi_to_app(target, name: str | None = None, base_url: str | None = None,
                   headers: dict | None = None, timeout: float = 30.0,
                   prefix: str = ""):
    """Convert an OpenAPI spec into a ``MakeMCP`` app (one tool per operation)."""
    from .server import MakeMCP

    spec = load_openapi(target)
    servers = spec.get("servers", []) or []
    base = (base_url or (servers[0].get("url") if servers else "") or "").rstrip("/")
    if not base:
        raise ValueError("no base URL: pass base_url= or add servers: to the spec")
    app = MakeMCP(name or spec.get("info", {}).get("title", "api"))
    count = 0
    for path, item in (spec.get("paths", {}) or {}).items():
        for method in ("get", "post", "put", "patch", "delete"):
            op = (item or {}).get(method)
            if not isinstance(op, dict):
                continue
            tool_name = f"{prefix}{_op_name(method, path, op.get('operationId'))}"
            params = _openapi_params(op)
            desc = (op.get("summary") or op.get("description") or
                    f"{method.upper()} {path}").strip()
            execute = _build_executor(base, method, path, params, dict(headers or {}), timeout)
            # Build a real function so signature-based schema generation works.
            sig_parts, defaults = [], {}
            ns = {"_execute": execute}
            for pr in params:
                ns[pr["pytype"]] = {"str": str, "int": int, "float": float,
                                    "bool": bool, "list": list, "dict": dict}[pr["pytype"]]
                if pr["required"]:
                    sig_parts.append(f"{pr['name']}: {pr['pytype']}")
                else:
                    dflt = pr["default"]
                    if dflt is None:
                        dflt = {"str": "", "int": 0, "float": 0.0,
                                "bool": False, "list": None, "dict": None}[pr["pytype"]]
                    defaults[pr["name"]] = dflt
                    sig_parts.append(f"{pr['name']}: {pr['pytype']} = _d_{pr['name']}")
                    ns[f"_d_{pr['name']}"] = dflt
            fn_src = (f"def {tool_name}({', '.join(sig_parts)}):\n"
                      f"    return _execute({{k: v for k, v in locals().items()}})\n")
            glb: dict = dict(ns)
            exec(compile(fn_src, f"<openapi:{tool_name}>", "exec"), glb)
            fn = glb[tool_name]
            fn.__doc__ = desc
            app.tool(fn, name=tool_name, description=desc)
            count += 1
    if count == 0:
        raise ValueError("no operations found in OpenAPI spec")
    return app


# --------------------------------------------------------------------------
# Shell-command sources
# --------------------------------------------------------------------------

def command_placeholders(cmd: str) -> list[str]:
    """Extract ``{placeholders}`` from a command template."""
    out = []
    for _, field, _, _ in string.Formatter().parse(cmd):
        if field and field not in out and not field[0].isdigit():
            out.append(_ident(field))
    return out


def command_to_app_entry(name: str, cmd: str, description: str = "",
                         timeout: float = 60.0, cwd: str | None = None):
    """Build a tool function that runs a shell command template.

    Example: ``command_to_app_entry("disk", "df -h {path}")`` creates a tool
    with a ``path`` argument. Only use with commands you trust.
    """
    import subprocess

    params = command_placeholders(cmd)
    sig = ", ".join(f"{p}: str = ''" for p in params) or ""
    src = (f"def {name}({sig}):\n"
           f"    return _run({{k: v for k, v in locals().items()}})\n")

    def _run(args: dict) -> dict:
        try:
            rendered = cmd.format(**{k: args.get(k, "") for k in params})
        except KeyError as e:
            return {"returncode": 2, "stdout": "", "stderr": f"missing argument: {e}"}
        try:
            import os as _os
            if _os.name == "nt":
                # Windows parses quoted strings itself; shlex would keep quotes.
                argv: Any = rendered
            else:
                argv = shlex.split(rendered)
        except ValueError as e:
            return {"returncode": 2, "stdout": "", "stderr": f"bad command: {e}"}
        try:
            done = subprocess.run(argv, capture_output=True, text=True,
                                  timeout=timeout, cwd=cwd, shell=False)
            return {"returncode": done.returncode, "stdout": done.stdout[-4000:],
                    "stderr": done.stderr[-4000:]}
        except subprocess.TimeoutExpired:
            return {"returncode": 124, "stdout": "", "stderr": "timed out"}
        except Exception as e:
            return {"returncode": 1, "stdout": "", "stderr": str(e)}

    glb = {"_run": _run, "str": str}
    exec(compile(src, f"<command:{name}>", "exec"), glb)
    fn = glb[name]
    fn.__doc__ = description or f"Run: {cmd}"
    return fn


def commands_to_app(tools: list[dict], name: str = "commands",
                    prefix: str = ""):
    """Convert ``[{name, cmd, description?, timeout?}]`` into a ``MakeMCP`` app."""
    from .server import MakeMCP

    app = MakeMCP(name)
    if not tools:
        raise ValueError("no command tools given")
    for t in tools:
        tname = f"{prefix}{_ident(t['name'])}"
        fn = command_to_app_entry(tname, t["cmd"], t.get("description", ""),
                                  float(t.get("timeout", 60.0)), t.get("cwd"))
        app.tool(fn, name=tname, description=t.get("description") or f"Run: {t['cmd']}")
    return app


# --------------------------------------------------------------------------
# Config + auto-detect + codegen
# --------------------------------------------------------------------------

def config_to_app(config: dict):
    """Build an app from a config dict::

        {"name": "MyMCP", "sources": [
            {"kind": "python", "target": "app.py"},
            {"kind": "openapi", "target": "https://.../openapi.json"},
            {"kind": "command", "tools": [{"name": "disk", "cmd": "df -h"}]},
        ]}
    """
    from .server import MakeMCP

    combined = MakeMCP(config.get("name", "converted"))
    sources = config.get("sources", [])
    if not sources:
        raise ValueError("config has no sources")
    for src in sources:
        kind = src.get("kind", "auto")
        opts = {k: v for k, v in src.items() if k not in ("kind", "target", "prefix")}
        sub = convert_target(src.get("target", ""), kind=kind, **opts)
        combined.mount(sub, prefix=src.get("prefix", ""))
    # keep the requested display name
    combined.name = config.get("name", "converted")
    return combined


def detect_kind(target: str) -> str:
    t = (target or "").strip()
    if t.endswith(".json") or re.match(r"^https?://", t):
        return "openapi"
    if t.endswith(".py") or ":" in t or re.match(r"^[a-zA-Z_]\w*(\.\w+)+$", t):
        return "python"
    return "unknown"


def convert_target(target: str, kind: str = "auto", **opts):
    """Convert *target* (auto-detected unless *kind* is given) into an app."""
    if kind == "auto":
        kind = detect_kind(target)
    if kind == "python":
        return python_to_app(target, **opts)
    if kind == "openapi":
        return openapi_to_app(target, **opts)
    if kind == "command":
        return commands_to_app(opts.get("tools", []),
                               name=opts.get("name", "commands"),
                               prefix=opts.get("prefix", ""))
    raise ValueError(f"cannot convert {target!r} (kind={kind}); "
                     "use kind='python', 'openapi' or 'command'")


def analyze_target(target: str, kind: str = "auto", **opts) -> dict:
    """Convert and return a JSON-serializable summary (for UIs)."""
    app = convert_target(target, kind=kind, **opts) if kind != "config" \
        else config_to_app(json.loads(open(target, encoding="utf-8").read())
                           if isinstance(target, str) else target)
    return {
        "name": app.name,
        "tool_count": len(app._tools),
        "tools": [{"name": t.name, "description": t.description,
                   "inputSchema": t.schema} for t in app._tools.values()],
    }


def render_server_module(config: dict) -> str:
    """Render a standalone ``server.py`` that rebuilds the converted app."""
    payload = json.dumps(config, indent=2, ensure_ascii=False)
    return f'''"""MCP server generated by makemcp convert.

Run with:
    python server.py           # stdio transport
    python server.py http 8000  # HTTP transport on port 8000
"""
from makemcp.convert import config_to_app

CONFIG = {payload}

mcp = config_to_app(CONFIG)

if __name__ == "__main__":
    import sys
    mode = sys.argv[1] if len(sys.argv) > 1 else "stdio"
    if mode == "http":
        port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
        mcp.run("http", port=port)
    else:
        mcp.run("stdio")
'''
