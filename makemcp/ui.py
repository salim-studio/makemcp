"""Browser interface for converting applications into MCP servers.

Run ``python -m makemcp ui --port 8080`` then open http://127.0.0.1:8080.
Three steps: 1) describe the source, 2) analyze & test-call tools,
3) generate a runnable ``server.py``. Stdlib only.
"""
from __future__ import annotations

import asyncio
import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

PAGE = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>makemcp converter — turn any app into MCP</title>
<style>
:root{--bg:#0f172a;--card:#1e293b;--acc:#22d3ee;--acc2:#818cf8;--tx:#e2e8f0}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);
font-family:system-ui,Segoe UI,Roboto,Arial,sans-serif}
.wrap{max-width:960px;margin:0 auto;padding:24px}
h1{font-size:28px;margin:8px 0}h1 .bolt{color:#fbbf24}
.sub{color:#94a3b8;margin-bottom:20px}
.card{background:var(--card);border-radius:12px;padding:18px;margin:14px 0}
.tabs{display:flex;gap:8px;margin-bottom:12px}
.tabs button{background:#0b1220;color:var(--tx);border:1px solid #334155;
border-radius:8px;padding:8px 16px;cursor:pointer}
.tabs button.on{background:linear-gradient(90deg,var(--acc2),var(--acc));color:#0b1220;font-weight:700}
label{display:block;font-size:13px;color:#94a3b8;margin:10px 0 4px}
input,textarea,select{width:100%;background:#0b1220;color:var(--tx);
border:1px solid #334155;border-radius:8px;padding:9px}
textarea{font-family:Consolas,monospace;min-height:90px}
.row{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
button.go{background:linear-gradient(90deg,var(--acc2),var(--acc));border:0;color:#0b1220;
font-weight:700;border-radius:8px;padding:10px 20px;cursor:pointer}
button.ghost{background:transparent;border:1px solid #475569;color:var(--tx);
border-radius:8px;padding:10px 20px;cursor:pointer}
pre{background:#0b1220;border:1px solid #334155;border-radius:8px;padding:12px;
overflow:auto;max-height:340px;font-size:13px;white-space:pre-wrap}
.ok{color:#4ade80}.err{color:#f87171}
.foot{color:#64748b;font-size:12px;margin:20px 0;text-align:center}
</style></head><body><div class="wrap">
<h1><span class="bolt">⚡</span> makemcp converter</h1>
<div class="sub">Turn a Python app, a REST API (OpenAPI) or shell commands into an MCP server.</div>

<div class="card"><div class="tabs">
<button id="t-py" class="on" onclick="tab('py')">Python app</button>
<button id="t-api" onclick="tab('api')">REST / OpenAPI</button>
<button id="t-cmd" onclick="tab('cmd')">Commands</button>
</div>

<div id="p-py">
<label>Python file, module or function (e.g. <code>app.py</code>, <code>app.py:main</code>, <code>mypkg.mod</code>)</label>
<input id="py-target" value="examples/sample_app.py"/>
<label>Tool name prefix (optional)</label><input id="py-prefix" value=""/>
</div>

<div id="p-api" style="display:none">
<label>OpenAPI URL or JSON file path</label>
<input id="api-target" value="https://petstore3.swagger.io/api/v3/openapi.json"/>
<label>Base URL override (optional)</label><input id="api-base" value=""/>
</div>

<div id="p-cmd" style="display:none">
<label>Commands as JSON: [{"name": "...", "cmd": "echo hello {who}", "description": "..."}]</label>
<textarea id="cmd-tools">[{"name": "greet", "cmd": "echo hello {who}", "description": "Greet someone"}]</textarea>
</div>

<label>Server name</label><input id="srv-name" value="my-mcp"/>
<div class="row">
<button class="go" onclick="analyze()">1 · Analyze</button>
<button class="ghost" onclick="gen()">2 · Generate server.py</button>
<button class="ghost" onclick="dl()">Download</button>
</div></div>

<div class="card"><h3>Discovered tools</h3><pre id="out-tools">Press Analyze…</pre>
<div id="testbox" style="display:none">
<label>Test call as JSON: {"tool": "name", "args": {...}}</label>
<input id="test-call" value=""/>
<div class="row"><button class="go" onclick="testcall()">3 · Test call</button></div>
<pre id="out-test"></pre></div></div>

<div class="card"><h3>Generated server.py</h3><pre id="out-code">Press Generate…</pre></div>
<div class="foot">Copyright (c) 2026 salim-slimani · MIT</div>
</div><script>
let KIND='py', LASTCFG=null;
function tab(k){KIND=k;for(const x of['py','api','cmd']){
document.getElementById('t-'+x).className=x===k?'on':'';
document.getElementById('p-'+x).style.display=x===k?'block':'none';}}
function cfg(){const name=document.getElementById('srv-name').value||'my-mcp';
if(KIND==='py')return{name,sources:[{kind:'python',
target:document.getElementById('py-target').value,
prefix:document.getElementById('py-prefix').value}]};
if(KIND==='api'){const s={kind:'openapi',target:document.getElementById('api-target').value};
const b=document.getElementById('api-base').value;if(b)s.base_url=b;return{name,sources:[s]};}
return{name,sources:[{kind:'command',tools:JSON.parse(document.getElementById('cmd-tools').value)}]};}
async function post(p,b){const r=await fetch(p,{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});return r.json();}
async function analyze(){const c=cfg();LASTCFG=c;
const r=await post('/api/analyze',{config:c});
const el=document.getElementById('out-tools');
if(r.error){el.innerHTML='<span class=err>'+esc(r.error)+'</span>';return;}
el.textContent=r.tools.map(t=>'[tool] '+t.name+' :: '+(t.description||'')).join('\\n')
+'\\n\\n'+r.tool_count+' tool(s) in "'+r.name+'"';
if(r.tools.length){document.getElementById('testbox').style.display='block';
document.getElementById('test-call').value=JSON.stringify({tool:r.tools[0].name,args:{}},null,1);}}
async function testcall(){let t;try{t=JSON.parse(document.getElementById('test-call').value);}
catch(e){document.getElementById('out-test').textContent='Bad JSON: '+e;return;}
const r=await post('/api/test',{config:LASTCFG,tool:t.tool,args:t.args||{}});
document.getElementById('out-test').textContent=JSON.stringify(r,null,1);}
async function gen(){const r=await post('/api/generate',{config:cfg()});
const el=document.getElementById('out-code');
if(r.error){el.innerHTML='<span class=err>'+esc(r.error)+'</span>';return;}
el.textContent=r.code;window._code=r.code;}
function dl(){const b=new Blob([window._code||''],{type:'text/x-python'});
const a=document.createElement('a');a.href=URL.createObjectURL(b);
a.download='server_mcp.py';a.click();}
function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;');}
</script></body></html>
"""


def _config_from(payload: dict) -> dict:
    cfg = payload.get("config") or {}
    if not isinstance(cfg, dict) or not cfg.get("sources"):
        raise ValueError("empty configuration: describe a source first")
    return cfg


def serve_ui(host: str = "127.0.0.1", port: int = 8080):
    from . import _json as J
    from .convert import analyze_target, config_to_app, render_server_module

    loop = asyncio.new_event_loop()
    threading.Thread(target=loop.run_forever, daemon=True).start()

    def run(coro):
        return asyncio.run_coroutine_threadsafe(coro, loop).result(timeout=120)

    class H(BaseHTTPRequestHandler):
        server_version = "makemcp-ui/1.1"
        def log_message(self, *a):
            pass

        def _send(self, body: bytes, ctype="application/json"):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if urlparse(self.path).path in ("/", "/index.html"):
                return self._send(PAGE.encode(), "text/html; charset=utf-8")
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            path = urlparse(self.path).path
            try:
                ln = int(self.headers.get("Content-Length") or 0)
            except ValueError:
                ln = 0
            try:
                payload = J.loads(self.rfile.read(ln) if ln else b"{}")
            except Exception:
                return self._send(J.dumps({"error": "invalid JSON"}))
            try:
                if path == "/api/analyze":
                    cfg = _config_from(payload)
                    if len(cfg["sources"]) == 1 and cfg["sources"][0].get("kind") != "command":
                        s = cfg["sources"][0]
                        out = analyze_target(s.get("target", ""),
                                             kind=s.get("kind", "auto"),
                                             **{k: v for k, v in s.items()
                                                if k not in ("kind", "target")})
                        out["name"] = cfg.get("name", out["name"])
                    else:
                        app = config_to_app(cfg)
                        out = {"name": cfg.get("name", app.name),
                               "tool_count": len(app._tools),
                               "tools": [{"name": t.name, "description": t.description,
                                          "inputSchema": t.schema}
                                         for t in app._tools.values()]}
                    return self._send(J.dumps(out))
                if path == "/api/test":
                    app = config_to_app(_config_from(payload))
                    res = run(app.call_tool(payload.get("tool", ""),
                                            payload.get("args") or {}))
                    try:
                        return self._send(J.dumps({"result": res}))
                    except (TypeError, ValueError):
                        return self._send(json.dumps({"result": str(res)}).encode())
                if path == "/api/generate":
                    code = render_server_module(_config_from(payload))
                    return self._send(J.dumps({"code": code}))
                self.send_response(404)
                self.end_headers()
            except Exception as e:
                return self._send(J.dumps({"error": str(e)}))

    srv = ThreadingHTTPServer((host, port), H)
    srv.daemon_threads = True
    print(f"makemcp converter UI on http://{host}:{port}  (Copyright (c) 2026 salim-slimani)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
