"""MakeMCPClient: connect to any MCP server over STDIO or HTTP.

- stdio: spawns `command` subprocess speaking JSON-RPC lines.
- http: POST JSON-RPC to url (urllib, keep-alive via single opener).
- direct: wrap a MakeMCP instance in-process (fastest, no serialization).
"""
from __future__ import annotations

import asyncio
import subprocess
import threading
import urllib.request
import urllib.error
from typing import Any

from . import _json as J

_NEXT_ID = iter(range(1, 10 ** 9))


def _nid():
    return next(_NEXT_ID)


class MakeMCPClient:
    def __init__(self, headers: dict | None = None, timeout: float = 30.0):
        self.headers = dict(headers or {})
        self.timeout = timeout
        self._proc: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._url: str | None = None
        self._app = None  # direct mode
        self._opener = urllib.request.build_opener()

    # ----- transports -----
    async def connect_direct(self, app) -> "MakeMCPClient":
        self._app = app
        await app.handle({"jsonrpc": "2.0", "id": _nid(), "method": "initialize", "params": {}})
        return self

    async def connect_http(self, url: str) -> "MakeMCPClient":
        self._url = url.rstrip("/")
        await self._rpc("initialize", {})
        return self

    async def connect_stdio(self, command: list[str]) -> "MakeMCPClient":
        import os
        env = dict(os.environ)
        cwd = os.getcwd()
        env["PYTHONPATH"] = cwd + os.pathsep + env.get("PYTHONPATH", "")
        self._proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                      stderr=subprocess.DEVNULL, bufsize=0, env=env, cwd=cwd)
        await self._rpc("initialize", {})
        return self

    def _post_http(self, payload: bytes, url: str) -> bytes:
        req = urllib.request.Request(url, data=payload,
                                     headers={"Content-Type": "application/json", **self.headers})
        try:
            with self._opener.open(req, timeout=self.timeout) as r:
                return r.read()
        except urllib.error.HTTPError as e:
            return e.read()

    async def _rpc(self, method: str, params: Any) -> Any:
        if self._app is not None:
            resp = await self._app.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params})
            if resp and "error" in resp:
                raise RuntimeError(resp["error"])
            return (resp or {}).get("result")
        msg = {"jsonrpc": "2.0", "id": _nid(), "method": method, "params": params}
        if self._proc is not None:
            with self._lock:
                assert self._proc.stdin and self._proc.stdout
                self._proc.stdin.write(J.dumps(msg) + b"\n")
                self._proc.stdin.flush()
                line = self._proc.stdout.readline()
            resp = J.loads(line)
            if "error" in resp:
                raise RuntimeError(resp["error"])
            return resp.get("result")
        if self._url is not None:
            raw = await asyncio.to_thread(self._post_http, J.dumps(msg), self._url)
            resp = J.loads(raw)
            if isinstance(resp, dict) and "error" in resp:
                raise RuntimeError(resp["error"])
            return resp.get("result") if isinstance(resp, dict) else resp
        raise RuntimeError("not connected: call connect_direct/http/stdio first")

    # ----- high-level API (mirrors fastmcp client) -----
    async def ping(self):
        return await self._rpc("ping", {})

    async def list_tools(self):
        r = await self._rpc("tools/list", {})
        return (r or {}).get("tools", [])

    async def call_tool(self, name: str, args: dict | None = None):
        r = await self._rpc("tools/call", {"name": name, "arguments": args or {}})
        return (r or {}).get("content", r)

    async def list_resources(self):
        r = await self._rpc("resources/list", {})
        return (r or {}).get("resources", [])

    async def read_resource(self, uri: str):
        r = await self._rpc("resources/read", {"uri": uri})
        return (r or {}).get("contents", r)

    async def list_prompts(self):
        r = await self._rpc("prompts/list", {})
        return (r or {}).get("prompts", [])

    async def get_prompt(self, name: str, args: dict | None = None):
        return await self._rpc("prompts/get", {"name": name, "arguments": args or {}})

    async def close(self):
        if self._proc is not None:
            try:
                self._proc.terminate()
            except Exception:
                pass
            self._proc = None


Client = MakeMCPClient
