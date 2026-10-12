#!/usr/bin/env python3
"""Exercise every tool against a running server.

    python -m sideline            # terminal 1
    python scripts/smoke_test.py  # terminal 2

Prints what a listener would actually hear. Useful for checking phrasing
by ear - read the output aloud. If it sounds like a database, it is.
"""

import json
import sys
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8765"
_n = [0]
_sid = [None]


def rpc(method, params=None):
    _n[0] += 1
    body = {"jsonrpc": "2.0", "id": _n[0], "method": method}
    if params:
        body["params"] = params
    headers = {"Content-Type": "application/json"}
    if _sid[0]:
        headers["Mcp-Session-Id"] = _sid[0]
    req = urllib.request.Request(BASE + "/mcp", json.dumps(body).encode(), headers)
    with urllib.request.urlopen(req, timeout=10) as r:
        if r.headers.get("Mcp-Session-Id"):
            _sid[0] = r.headers["Mcp-Session-Id"]
        raw = r.read().decode()
    return json.loads(raw) if raw else None


def call(name, **args):
    doc = rpc("tools/call", {"name": name, "arguments": args})
    res = doc.get("result") or {}
    spoken = (res.get("content") or [{}])[0].get("text", "")
    took = ((res.get("_meta") or {}).get("sideline") or {}).get("took_ms")
    flag = "  [declined]" if res.get("isError") else ""
    print("\n  ask  %s(%s)" % (name, ", ".join("%s=%r" % kv for kv in args.items())))
    print("  hear %s%s" % (spoken, flag))
    if took is not None:
        print("  (%d ms)" % took)
    return res


def main():
    init = rpc("initialize", {"protocolVersion": "2025-11-25",
                              "clientInfo": {"name": "smoke", "version": "1"}})
    print("server :", init["result"]["serverInfo"]["name"],
          init["result"]["serverInfo"]["version"])
    print("protocol:", init["result"]["protocolVersion"])
    rpc("notifications/initialized")

    tools = rpc("tools/list")["result"]["tools"]
    print("tools  :", ", ".join(t["name"] for t in tools))

    print("\n--- a listener follows a match -------------------------------")
    call("follow_match", team="Arsenal")
    call("get_match_state")

    print("\n--- he has just sat down: the whole match so far -------------")
    res = call("what_did_i_miss")
    sc = res.get("structuredContent") or {}
    if sc.get("window"):
        print("  (window %s' -> %s', %d events, via %s)" % (
            sc["window"]["from_minute"], sc["window"]["to_minute"],
            sc.get("event_count", 0), sc.get("generated_by")))

    print("\n--- asking twice should give nothing new ---------------------")
    call("what_did_i_miss")

    print("\n--- the graphic nobody reads out -----------------------------")
    call("get_lineups", team="Arsenal")

    print("\n--- the things nobody reads out ------------------------------")
    call("get_officials")
    call("get_event_detail", kind="goal")
    call("get_player_context", player="kane")
    call("get_head_to_head", limit=3)

    print("\n--- failures the listener can hear ---------------------------")
    call("get_player_context", player="nobody")

    print("\ndone. read the 'hear' lines aloud - that is the product.")


if __name__ == "__main__":
    main()
