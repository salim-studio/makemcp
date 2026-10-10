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
from urllib.parse import parse_qs, urlparse

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
<div class="sub">Turn a Python app, a REST API (OpenAPI), shell commands or a GitHub repo into an MCP server.</div>

<div class="card"><div class="tabs">
<button id="t-py" class="on" onclick="tab('py')">Python app</button>
<button id="t-api" onclick="tab('api')">REST / OpenAPI</button>
<button id="t-cmd" onclick="tab('cmd')">Commands</button>
<button id="t-gh" onclick="tab('gh')">GitHub</button>
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

<div id="p-gh" style="display:none">
<label>GitHub repo URL or shorthand (only convert repos you trust)</label>
<input id="gh-target" value="salim-studio/makemcp"/>
<label>Branch / tag (optional, blank = default branch)</label><input id="gh-ref" value=""/>
<label>Subdirectory (optional)</label><input id="gh-subdir" value="examples"/>
</div>

<label>Server name</label><input id="srv-name" value="my-mcp"/>
<div class="row">
<button class="go" onclick="analyze()">1 · Analyze</button>
<button class="ghost" onclick="gen()">2 · Generate server.py</button>
<button class="ghost" onclick="dl()">Download</button>
<button class="ghost" onclick="example()">Try working example</button>
</div></div>

<div class="card"><h3>Discovered tools</h3><pre id="out-tools">Press Analyze…</pre>
<div id="testbox" style="display:none">
<label>Test call as JSON: {"tool": "name", "args": {...}}</label>
<input id="test-call" value=""/>
<div class="row"><button class="go" onclick="testcall()">3 · Test call</button></div>
<pre id="out-test"></pre></div></div>

<div class="card"><h3>Generated server.py</h3><pre id="out-code">Press Generate…</pre></div>
<div class="foot">Copyright (c) 2026 salim-slimani · MIT · __MAKEMCP_VERSION__</div>
</div><script>
let KIND='py', LASTCFG=null;
function tab(k){KIND=k;for(const x of['py','api','cmd','gh']){
document.getElementById('t-'+x).className=x===k?'on':'';
document.getElementById('p-'+x).style.display=x===k?'block':'none';}}
function cfg(){const name=document.getElementById('srv-name').value||'my-mcp';
if(KIND==='py')return{name,sources:[{kind:'python',
target:document.getElementById('py-target').value,
prefix:document.getElementById('py-prefix').value}]};
if(KIND==='api'){const s={kind:'openapi',target:document.getElementById('api-target').value};
const b=document.getElementById('api-base').value;if(b)s.base_url=b;return{name,sources:[s]};}
if(KIND==='gh'){const s={kind:'github',target:document.getElementById('gh-target').value};
const r=document.getElementById('gh-ref').value;if(r)s.ref=r;
const d=document.getElementById('gh-subdir').value;if(d)s.subdir=d;
return{name,sources:[s]};}
return{name,sources:[{kind:'command',tools:JSON.parse(document.getElementById('cmd-tools').value)}]};}
async function post(p,b){const r=await fetch(p,{method:'POST',
headers:{'Content-Type':'application/json'},body:JSON.stringify(b)});
let j;try{j=await r.json();}catch(e){return{error:'HTTP '+r.status+' at '+p};}
if(!r.ok&&!j.error)j.error='HTTP '+r.status+' at '+p;return j;}
function api(name,body){return post('/api/'+name+'?route=api/'+name,body);}
async function example(){tab('gh');
document.getElementById('gh-target').value='salim-studio/makemcp';
document.getElementById('gh-ref').value='';
document.getElementById('gh-subdir').value='examples';
document.getElementById('srv-name').value='makemcp-self';
document.getElementById('out-tools').textContent='Converting salim-studio/makemcp …';
await analyze();}
async function analyze(){const c=cfg();LASTCFG=c;
const r=await api('analyze',{config:c});
const el=document.getElementById('out-tools');
if(r.error){el.innerHTML='<span class=err>'+esc(r.error)+'</span>';return;}
el.textContent=r.tools.map(t=>'[tool] '+t.name+
(t.requires&&t.requires.length?' [needs: '+t.requires.join(', ')+']':'')+
' :: '+(t.description||'')).join('\\n')
+'\\n\\n'+r.tool_count+' tool(s) in "'+r.name+'"'+
(r.requirements&&r.requirements.length?'\\nInstall: pip install '+r.requirements.join(' '):'');
if(r.tools.length){document.getElementById('testbox').style.display='block';
document.getElementById('test-call').value=JSON.stringify({tool:r.tools[0].name,args:{}},null,1);}}
async function testcall(){let t;try{t=JSON.parse(document.getElementById('test-call').value);}
catch(e){document.getElementById('out-test').textContent='Bad JSON: '+e;return;}
const r=await api('test',{config:LASTCFG,tool:t.tool,args:t.args||{}});
document.getElementById('out-test').textContent=JSON.stringify(r,null,1);}
async function gen(){const r=await api('generate',{config:cfg()});
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


def page_html() -> str:
    """Converter UI page with the running version stamped in the footer."""
    try:
        from . import __version__
    except Exception:
        __version__ = "dev"
    return PAGE.replace("__MAKEMCP_VERSION__", f"v{__version__}")


def api_analyze(config: dict) -> dict:
    """Shared handler: describe the tools a config would produce."""
    from .convert import analyze_target, config_to_app, summarize_app

    if len(config["sources"]) == 1 and config["sources"][0].get("kind") != "command":
        s = config["sources"][0]
        out = analyze_target(s.get("target", ""),
                             kind=s.get("kind", "auto"),
                             **{k: v for k, v in s.items()
                                if k not in ("kind", "target")})
        out["name"] = config.get("name", out["name"])
        return out
    return summarize_app(config_to_app(config), name=config.get("name"))


async def api_test(config: dict, tool: str, args: dict):
    """Shared handler: build the app and call one tool (for testing)."""
    from .convert import config_to_app

    app = config_to_app(config)
    return await app.call_tool(tool, args or {})


def api_generate(config: dict) -> dict:
    """Shared handler: render a standalone server.py for a config."""
    from .convert import render_server_module, config_to_app

    reqs = None
    try:
        reqs = config_to_app(config)._state.get("requirements") or None
    except Exception:
        reqs = None
    return {"code": render_server_module(config, requirements=reqs)}


def serve_ui(host: str = "127.0.0.1", port: int = 8080):
    from . import _json as J

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
                return self._send(page_html().encode(), "text/html; charset=utf-8")
            self.send_response(404)
            self.end_headers()

        def do_POST(self):
            parts = urlparse(self.path)
            path = parts.path
            if parts.query:
                # ?route= survives proxy rewrites that replace the URL path.
                q = parse_qs(parts.query)
                if q.get("route"):
                    path = "/" + q["route"][0].lstrip("/")
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
                    return self._send(J.dumps(api_analyze(_config_from(payload))))
                if path == "/api/test":
                    res = run(api_test(_config_from(payload),
                                       payload.get("tool", ""),
                                       payload.get("args") or {}))
                    try:
                        return self._send(J.dumps({"result": res}))
                    except (TypeError, ValueError):
                        return self._send(json.dumps({"result": str(res)}).encode())
                if path == "/api/generate":
                    return self._send(J.dumps(api_generate(_config_from(payload))))
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
