"""The MCP is the `sideline` folder and nothing else.

Copies only that folder to an empty directory (no simulator, scripts, tests or docs next to it), starts the server
there and talks to it over HTTP. If `sideline` ever imports something outside itself, this fails.
"""

import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

PROBE = r'''
import json, threading, urllib.request
from sideline import app
ctx, srv, poller = app.build()
threading.Thread(target=srv.serve_forever, daemon=True).start()
base = "http://127.0.0.1:%d" % srv.server_address[1]

def post(path, body, headers=None):
    req = urllib.request.Request(base + path, json.dumps(body).encode(), dict({"Content-Type": "application/json"}, **(headers or {})))
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None
import urllib.error

health = json.loads(urllib.request.urlopen(base + "/health", timeout=10).read())
H = {"Accept": "application/json, text/event-stream", "MCP-Protocol-Version": "2025-11-25"}
req = urllib.request.Request(base + "/mcp", json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
    "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}}).encode(),
    dict({"Content-Type": "application/json"}, **H))
sid = urllib.request.urlopen(req, timeout=10).headers["Mcp-Session-Id"]
code, tools = post("/mcp", {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, dict(H, **{"Mcp-Session-Id": sid}))
assert tools, "tools/list answered HTTP %s" % code
code2, cap = post("/agent/chat", {"question": "hi"})
try:
    urllib.request.urlopen(base + "/voice/capabilities", timeout=10)
    voice = 200
except urllib.error.HTTPError as e:
    voice = e.code
import sys
print(json.dumps({"tools": len(tools["result"]["tools"]), "health": health["tools"], "agent": code2, "voice": voice,
                  "simulator_loaded": "simulator" in sys.modules}))
srv.shutdown()
'''


def _free_port():
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main():
    tmp = tempfile.mkdtemp(prefix="sideline-alone-")
    try:
        shutil.copytree(os.path.join(ROOT, "sideline"), os.path.join(tmp, "sideline"),
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        env = {k: v for k, v in os.environ.items() if k not in ("PYTHONPATH",)}
        env.update(SIDELINE_LOG_DIR="off", SIDELINE_BEDROCK="off", SIDELINE_STATE="memory", SIDELINE_PORT=str(_free_port()),
                   AWS_ACCESS_KEY_ID="", AWS_SECRET_ACCESS_KEY="")
        r = subprocess.run([sys.executable, "-I", "-c", PROBE], cwd=tmp, env=env, capture_output=True, text=True,
                           timeout=120)
        # -I ignores the working directory, so put the copy on the path explicitly
        if r.returncode != 0 and "No module named 'sideline'" in r.stderr:
            r = subprocess.run([sys.executable, "-c", PROBE], cwd=tmp, env=env, capture_output=True, text=True,
                               timeout=120)
        assert r.returncode == 0, "the sideline folder alone could not start:\n" + r.stderr[-1500:]
        out = json.loads(r.stdout.strip().splitlines()[-1])
        assert out["tools"] == out["health"] and out["tools"] >= 30, out
        assert out["agent"] in (404, 503) and out["voice"] == 404, out
        assert not out["simulator_loaded"], "sideline imported the simulator"
        print("ok  the sideline folder alone starts, lists %d tools over MCP, and answers 404 for the simulator's routes"
              % out["tools"])
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    print("\nstandalone: all good")


if __name__ == "__main__":
    main()
