"""Streamable-HTTP + SSE transport on stdlib http.server (zero deps).

Endpoints:
  POST /mcp  -> JSON-RPC (single or batch). Returns JSON.
  GET  /mcp  -> SSE stream of server info + tools (simple discovery stream).
  GET  /sse  -> legacy SSE alias.
  GET  /health -> {"ok": true}
Auth: optional Bearer token via app._state['token'] or header check in middleware.
Threaded server -> handles concurrent calls; tool execution bridged via asyncio.
"""
from __future__ import annotations

import asyncio
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse


def serve_http(app, host="127.0.0.1", port=8000, path="/mcp", log_level="warning", token: str | None = None):
    from .. import _json as J
    import logging
    logging.getLogger().setLevel(getattr(logging, log_level.upper(), logging.WARNING))

    # dedicated loop in background thread for tool execution
    loop = asyncio.new_event_loop()
    t = threading.Thread(target=loop.run_forever, daemon=True)
    t.start()

    def dispatch(msg, headers):
        ctx = {"headers": {k.lower(): v for k, v in headers.items()}, "auth": headers.get("Authorization", "")}
        fut = asyncio.run_coroutine_threadsafe(app.handle(msg, ctx), loop)
        return fut.result(timeout=120)

    class H(BaseHTTPRequestHandler):
        server_version = "makemcp/1.0"
        def log_message(self, *a):
            pass

        def _cors(self):
            self.send_header("Access-Control-Allow-Origin", "*")
            self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.end_headers()

        def do_GET(self):
            u = urlparse(self.path)
            if u.path == "/health":
                body = b'{"ok":true}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if u.path in (path, "/sse", "/mcp/sse"):
                # minimal SSE discovery stream
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Connection", "keep-alive")
                self._cors()
                self.end_headers()
                try:
                    info = {"name": app.name, "version": app.version,
                            "tools": [x.to_dict() for x in app._tools.values()]}
                    chunk = f"event: info\ndata: {J.dumps(info).decode()}\n\n".encode()
                    self.wfile.write(chunk)
                    self.wfile.flush()
                except Exception:
                    pass
                return
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            u = urlparse(self.path)
            if u.path not in (path, "/mcp/", "/rpc"):
                self.send_response(404)
                self.end_headers()
                return
            ln = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(ln) if ln else b"{}"
            try:
                msg = J.loads(raw)
            except Exception:
                self.send_response(400)
                self.end_headers()
                return
            try:
                if isinstance(msg, list):
                    out = []
                    for m in msg:
                        r = dispatch(m, dict(self.headers))
                        if r is not None:
                            out.append(r)
                    body = J.dumps(out)
                else:
                    r = dispatch(msg, dict(self.headers))
                    body = J.dumps(r if r is not None else {"jsonrpc": "2.0", "id": msg.get("id"), "result": {}})
            except Exception as e:
                body = J.dumps({"jsonrpc": "2.0", "id": msg.get("id") if isinstance(msg, dict) else None,
                                "error": {"code": -32603, "message": str(e)}})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self._cors()
            self.end_headers()
            self.wfile.write(body)

    srv = ThreadingHTTPServer((host, port), H)
    srv.daemon_threads = True
    print(f"makemcp '{app.name}' serving HTTP on http://{host}:{port}{path}  (POST JSON-RPC, GET SSE)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
