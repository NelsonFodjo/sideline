"""Protocol conformance.

These are the tests that stop us shipping something that looks right in
our own simulator and then fails the moment a real MCP client connects.
Each one maps to a line in the 2025-11-25 spec.
"""

import json
import threading
import time
import urllib.error
import urllib.request

from conftest import make_ctx

from sideline.mcp import server as mcp_server
from sideline.mcp.registry import public_tools
from sideline.tools import REGISTRY

PORT = 8791
BASE = "http://127.0.0.1:%d" % PORT


def _start():
    ctx = make_ctx(start_minute=40)

    def run_tool(name, args, listener):
        return REGISTRY[name](ctx, args, listener)

    srv = mcp_server.serve("127.0.0.1", PORT, run_tool,
                           lambda h: "test-listener", ["*"])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.2)
    return srv


def _post(payload, headers=None):
    req = urllib.request.Request(
        BASE + "/mcp", data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=5) as r:
            body = r.read().decode() or "null"
            return r.status, json.loads(body), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, None, dict(e.headers)


def main():
    srv = _start()
    try:
        # --- initialize issues a session id -------------------------
        code, doc, hdr = _post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                "params": {"protocolVersion": "2025-11-25"}})
        assert code == 200, code
        assert doc["result"]["protocolVersion"] == "2025-11-25"
        sid = hdr.get("Mcp-Session-Id")
        assert sid, "initialize must issue Mcp-Session-Id"
        assert hdr.get("MCP-Protocol-Version") == "2025-11-25"
        print("ok  initialize + session id")

        # --- notification gets 202 and no body ----------------------
        code, doc, _ = _post({"jsonrpc": "2.0", "method": "notifications/initialized"},
                             {"Mcp-Session-Id": sid})
        assert code == 202, code
        print("ok  notification -> 202 no body")

        # --- tools/list ---------------------------------------------
        code, doc, _ = _post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                             {"Mcp-Session-Id": sid})
        names = [t["name"] for t in doc["result"]["tools"]]
        assert len(names) == len(public_tools()) == 30, names
        assert "what_did_i_miss" in names
        assert "sync_broadcast_delay" in names
        for t in doc["result"]["tools"]:
            assert t["description"], t["name"]
            assert t["inputSchema"]["type"] == "object"
        print("ok  tools/list ->", len(names), "tools, all described")
        by = {t["name"]: t["annotations"] for t in doc["result"]["tools"]}
        assert all(a["destructiveHint"] is False for a in by.values()), "nothing here deletes anything"
        assert {n for n, a in by.items() if not a["readOnlyHint"]} == {
            "follow_match", "sync_broadcast_delay", "set_favourites", "set_preferences", "what_did_i_miss", "get_lineups"}
        assert by["get_match_state"]["readOnlyHint"] and by["get_match_state"]["openWorldHint"]
        assert by["set_favourites"]["openWorldHint"] is False and by["what_did_i_miss"]["idempotentHint"] is False
        print("ok  every tool declares read-only / idempotent / open-world hints; the six that change listener state say so")

        # --- tools/call ---------------------------------------------
        code, doc, _ = _post({"jsonrpc": "2.0", "id": 3, "method": "tools/call",
                              "params": {"name": "follow_match",
                                         "arguments": {"team": "Arsenal"}}},
                             {"Mcp-Session-Id": sid})
        assert doc["result"]["content"][0]["type"] == "text"
        assert doc["result"]["structuredContent"]["fixture_id"] == 1208341
        print("ok  tools/call follow_match")

        # --- schema rejection ---------------------------------------
        code, doc, _ = _post({"jsonrpc": "2.0", "id": 4, "method": "tools/call",
                              "params": {"name": "get_event_detail",
                                         "arguments": {"minute": "thirty"}}},
                             {"Mcp-Session-Id": sid})
        assert "error" not in doc and doc["result"]["isError"], doc          # MCP-09: a tool error the model can correct
        assert doc["result"]["structuredContent"]["reason"] == "invalid_arguments", doc
        print("ok  bad argument type -> isError result (not a protocol error)")

        # --- unknown method -----------------------------------------
        code, doc, _ = _post({"jsonrpc": "2.0", "id": 5, "method": "nope"},
                             {"Mcp-Session-Id": sid})
        assert doc["error"]["code"] == -32601
        print("ok  unknown method -> MethodNotFound")

        # --- unknown session ----------------------------------------
        code, doc, _ = _post({"jsonrpc": "2.0", "id": 6, "method": "tools/list"},
                             {"Mcp-Session-Id": "deadbeef"})
        assert code == 404, code
        print("ok  unknown session -> 404")

        # --- batch: removed from MCP in 2025-06-18, so refused -------
        code, doc, _ = _post([{"jsonrpc": "2.0", "id": 7, "method": "ping"},
                              {"jsonrpc": "2.0", "id": 8, "method": "tools/list"}],
                             {"Mcp-Session-Id": sid})
        assert code == 400, code
        print("ok  batch request -> 400 (not part of MCP 2025-11-25)")

        # --- DELETE ends the session --------------------------------
        req = urllib.request.Request(BASE + "/mcp", method="DELETE",
                                     headers={"Mcp-Session-Id": sid})
        with urllib.request.urlopen(req, timeout=5) as r:
            assert r.status == 204
        code, doc, _ = _post({"jsonrpc": "2.0", "id": 9, "method": "ping"},
                             {"Mcp-Session-Id": sid})
        assert code == 404
        print("ok  DELETE terminates session")

        print("\nprotocol: all good")
    finally:
        srv.shutdown()


if __name__ == "__main__":
    main()
