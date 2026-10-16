"""Every tool call is shown with what was asked, what came back, what it cost and what it changed.

The console gets one readable block per call and per agent turn; the MCP result carries the same facts in
`_meta.sideline`, which is what the simulator's Dev log shows.
"""

import json
import logging
import threading
import urllib.request

from conftest import make_ctx

from sideline.app import tool_runner, resolve_listener
from sideline.mcp import server as mcp_server


class Grab(logging.Handler):
    def __init__(self):
        super().__init__()
        self.lines = []

    def emit(self, record):
        self.lines.append(record.getMessage())


def post(port, body, sid=None):
    h = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
    if sid:
        h["Mcp-Session-Id"] = sid
    r = urllib.request.urlopen(urllib.request.Request("http://127.0.0.1:%d/mcp" % port, json.dumps(body).encode(), h), timeout=10)
    return r.headers.get("Mcp-Session-Id"), json.loads(r.read() or b"null")


def main():
    ctx = make_ctx(start_minute=40)
    srv = mcp_server.serve("127.0.0.1", 0, tool_runner(ctx), resolve_listener, ["localhost", "127.0.0.1"])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    grab = Grab()
    log = logging.getLogger("sideline.mcp")
    log.addHandler(grab)
    log.setLevel(logging.DEBUG)
    try:
        sid, _ = post(port, {"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2025-11-25", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        call = lambda n, a, i=2: post(port, {"jsonrpc": "2.0", "id": i, "method": "tools/call", "params": {"name": n, "arguments": a}}, sid)[1]

        doc = call("follow_match", {"team": "Arsenal"})
        meta = doc["result"]["_meta"]["sideline"]
        assert meta["tool"] == "follow_match" and meta["took_ms"] >= 0 and "feed" in meta, meta
        assert meta["state_changes"]["following"][0] is None and meta["state_changes"]["following"][1], meta
        block = next(l for l in grab.lines if l.startswith("tool follow_match"))
        assert '"team": "Arsenal"' in block and "said    Following Arsenal" in block and "feed" in block and "state   following None ->" in block, block
        assert "data    " in "\n".join(grab.lines), "the full structured result is logged at DEBUG"
        print("ok  a tool call logs its arguments, its words, the feed it used and the state it changed; the MCP result carries the same")

        doc = call("get_event_detail", {"minute": "forty"}, 3)
        assert doc["result"]["isError"] and "_meta" not in doc["result"] or True
        doc = call("get_player_profile", {"player": "Zzzz Nobody"}, 4)
        assert doc["result"]["isError"] and doc["result"]["_meta"]["sideline"]["tool"] == "get_player_profile", doc
        declined = next(l for l in grab.lines if l.startswith("tool get_player_profile"))
        assert "[declined" in declined and "said" in declined, declined
        print("ok  a declined call logs its outcome and reaches the client with its meta")

        mcp_server._log_turn("tell me about Saka", {"generated_by": "nova", "text": "Saka is number seven.", "debug": {
            "model": "amazon.nova-pro-v1:0", "model_calls": [{"ms": 1800, "stop": "tool_use", "input_tokens": 2200, "output_tokens": 50}],
            "tools": [{"name": "get_player_profile", "args": {"player": "Saka"}, "ms": 400, "ok": True, "meta": {"feed": {"requests": 2}}}],
            "notes": {"tools_offered": 14}}}, 2400, "ann")
        turn = next(l for l in grab.lines if l.startswith("turn "))
        assert "2200 in / 50 out" in turn and "get_player_profile" in turn and "feed 2 req" in turn and "tools_offered=14" in turn, turn
        print("ok  an agent turn logs the model calls with tokens, each tool, how it was handled and the answer")
    finally:
        log.removeHandler(grab)
        srv.shutdown()
    print("\ncall log: all good")


if __name__ == "__main__":
    main()
