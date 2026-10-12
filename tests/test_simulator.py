"""The simulator has to be able to reach the server it demos.

It once could not: opened from disk it sends `Origin: null`, which the
Origin allow-list (correctly) refuses, so its first call, `initialize`,
got a 403. Now the server serves the page and the page is same-origin.
"""

import json
import threading
import time
import urllib.error
import urllib.request

from conftest import make_ctx

from sideline.mcp import server as mcp_server
from sideline.tools import REGISTRY

PORT = 8795
BASE = "http://127.0.0.1:%d" % PORT


def main():
    ctx = make_ctx(start_minute=40)
    srv = mcp_server.serve("127.0.0.1", PORT,
                           lambda n, a, l: REGISTRY[n](ctx, a, l),
                           lambda h: "sim-listener", ["localhost", "127.0.0.1"])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)

    with urllib.request.urlopen(BASE + "/") as r:
        page = r.read().decode("utf-8")
        assert r.status == 200 and "text/html" in r.headers["Content-Type"]
    assert "tools/call" in page and "Mcp-Session-Id" in page
    assert '"/agent/chat"' in page and "LIVE_MODE" in page
    assert "webkitSpeechRecognition" in page and "startBrowserRecognition" in page
    assert "server speech recognition unavailable; switching to browser" in page
    assert "Please repeat." in page
    print("ok  GET / serves the simulator, and it is an MCP client (initialize/tools/list/tools/call)")

    with urllib.request.urlopen(BASE + "/?preview=what%20did%20I%20miss&pace=900") as r:
        assert r.status == 200 and "text/html" in r.headers["Content-Type"]
    print("ok  a query string (?preview=...) does not change the route")

    with urllib.request.urlopen(BASE + "/voice/capabilities") as r:
        caps = json.loads(r.read())
    assert not any(k.endswith("_hint") for k in caps), caps
    assert "aws configure" not in page and "GROQ_API_KEY" not in page
    print("ok  no setup hints reach the page: not in the capabilities JSON, not in the page")

    def post(origin, payload):
        h = {"Content-Type": "application/json"}
        if origin:
            h["Origin"] = origin
        req = urllib.request.Request(BASE + "/mcp", json.dumps(payload).encode(), h)
        try:
            with urllib.request.urlopen(req, timeout=3) as r:
                return r.status, dict(r.headers), json.loads(r.read() or b"null")
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), None

    init = {"jsonrpc": "2.0", "id": 1, "method": "initialize",
            "params": {"protocolVersion": "2025-11-25", "capabilities": {},
                       "clientInfo": {"name": "sim", "version": "1"}}}

    code, headers, doc = post(BASE, init)          # what the served page sends
    assert code == 200 and headers.get("Mcp-Session-Id"), (code, headers)
    assert doc["result"]["protocolVersion"] == "2025-11-25"
    print("ok  the page's own origin can initialize and gets a session")

    assert post("null", init)[0] == 403
    assert post("https://evil.example", init)[0] == 403
    print("ok  Origin: null and foreign origins are still refused (the allow-list stays strict)")

    srv.shutdown()
    print("\nsimulator: all good")


if __name__ == "__main__":
    main()
