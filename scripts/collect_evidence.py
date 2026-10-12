#!/usr/bin/env python3
"""Measure the claims this project makes, and write docs/EVIDENCE.md.

    python3 scripts/collect_evidence.py            # measure, rewrite docs/EVIDENCE.md
    python3 scripts/collect_evidence.py --print    # measure, print only

Everything in the output is something this script measured on this
machine, now. Nothing is typed in by hand. It deliberately does NOT touch
AWS or a live football feed; those sections say what has not been
verified and which command verifies it.
"""

import json
import os
import platform
import statistics
import subprocess
import sys
import threading
import time
import urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))

PORT = 8794
BASE = "http://127.0.0.1:%d" % PORT


def sh(*cmd):
    return subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True).stdout.strip()


def pct(xs, p):
    xs = sorted(xs)
    return xs[min(len(xs) - 1, int(len(xs) * p))]


class Client:
    """A minimal MCP client over HTTP, counting every byte it moves."""

    def __init__(self):
        self.sid = None
        self.n = 0
        self.bytes_body = 0
        self.bytes_wire = 0

    def rpc(self, method, params=None):
        self.n += 1
        payload = {"jsonrpc": "2.0", "id": self.n, "method": method}
        if params is not None:
            payload["params"] = params
        data = json.dumps(payload).encode()
        h = {"Content-Type": "application/json"}
        if self.sid:
            h["Mcp-Session-Id"] = self.sid
        req = urllib.request.Request(BASE + "/mcp", data, h)
        t0 = time.perf_counter()
        with urllib.request.urlopen(req, timeout=10) as r:
            body = r.read()
            ms = (time.perf_counter() - t0) * 1000
            if r.headers.get("Mcp-Session-Id"):
                self.sid = r.headers["Mcp-Session-Id"]
            head = sum(len(k) + len(v) + 4 for k, v in r.headers.items()) + 17
        req_wire = len(data) + sum(len(k) + len(v) + 4 for k, v in h.items()) + 120
        self.bytes_body += len(body)
        self.bytes_wire += len(body) + head + req_wire
        return (json.loads(body) if body else None), ms


def main():
    out = []
    w = out.append
    stamp = time.strftime("%Y-%m-%d %H:%M %Z")
    commit = sh("git", "rev-parse", "--short", "HEAD") or "(not a git checkout)"
    dirty = "yes" if sh("git", "status", "--porcelain") else "no"

    w("# Evidence\n")
    w("Every number below was **measured by `scripts/collect_evidence.py`**, not")
    w("typed in. Re-run it (`make evidence`) and this file is rewritten. Where")
    w("something has *not* been verified, it says so and gives the command that")
    w("would verify it. If another document disagrees with this one, this one")
    w("is right and the other is stale.\n")
    w("| | |\n|---|---|")
    w("| Measured | %s |" % stamp)
    w("| Git commit | `%s` (uncommitted changes: %s) |" % (commit, dirty))
    w("| Python | %s on %s |" % (platform.python_version(), platform.platform()))
    w("| Replay used | `data/replay/spurs-arsenal-2016.json` (the default) |\n")

    # ---- server on the real match
    from sideline import language
    from sideline.app import Context
    from sideline.config import CONFIG
    from sideline.mcp import server as mcp_server
    from sideline.providers.replay import ReplayProvider
    from sideline.state import MemoryStore
    from sideline.tools import REGISTRY

    provider = ReplayProvider(CONFIG.replay_path, speed=10000.0, start_minute=0)
    ctx = Context(provider, MemoryStore(), language)
    srv = mcp_server.serve("127.0.0.1", PORT,
                           lambda n, a, l: REGISTRY[n](ctx, a, l),
                           lambda h: "evidence", ["localhost", "127.0.0.1"])
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    time.sleep(0.3)

    # ---- the match
    doc = json.load(open(CONFIG.replay_path, encoding="utf-8"))
    kinds = {}
    for e in doc["events"]:
        kinds[e["kind"]] = kinds.get(e["kind"], 0) + 1
    w("## The bundled match\n")
    w("| | |\n|---|---|")
    fx = doc["fixture"]
    w("| Fixture | %s v %s, %s |" % (fx["home"], fx["away"], fx.get("venue", "")))
    w("| Events | %d (%s) |" % (len(doc["events"]),
                                ", ".join("%d %s" % (v, k) for k, v in sorted(kinds.items()))))
    w("| Referee | %s |" % doc["officials"].get("referee"))
    w("| Line-ups | %s |" % "; ".join("%s: %d starters" % (t, len(v["xi"]))
                                      for t, v in doc["lineups"].items()))
    w("| Attribution in file | %s |\n" % ("yes" if doc.get("_attribution") else "NO"))

    # ---- protocol
    c = Client()
    init, _ = c.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                                   "clientInfo": {"name": "evidence", "version": "1"}})
    c.rpc("notifications/initialized")
    tl, _ = c.rpc("tools/list")
    tools = [t["name"] for t in tl["result"]["tools"]]
    w("## Protocol\n")
    w("| | |\n|---|---|")
    w("| Protocol version negotiated | %s |" % init["result"]["protocolVersion"])
    w("| Tools exposed | %d: %s |\n" % (len(tools), ", ".join(tools)))

    # ---- latency over HTTP, in-process server, replay data
    def call(name, args=None):
        return c.rpc("tools/call", {"name": name, "arguments": args or {}})

    call("follow_match", {"team": "Arsenal"})
    provider.jump_to(70)
    from sideline.poller import poll_once
    poll_once(ctx)
    cases = [("get_match_state", {}), ("get_lineups", {"team": "Arsenal"}),
             ("get_officials", {}), ("get_event_detail", {"kind": "goal"}),
             ("get_player_context", {"player": "Kane"}), ("get_head_to_head", {}),
             ("sync_broadcast_delay", {})]
    w("## Response time (HTTP, in-process server, templates only)\n")
    w("200 calls per tool through a real HTTP client. Server and client share")
    w("one machine, so this is **server time plus loopback**: it shows the")
    w("server is not the slow part, **not** what a listener on a network or")
    w("through Alexa+ would see. Bedrock is off here.\n")
    w("| Tool | p50 ms | p95 ms | max ms |\n|---|---|---|---|")
    for name, args in cases:
        xs = [call(name, args)[1] for _ in range(200)]
        w("| `%s` | %.1f | %.1f | %.1f |" % (name, statistics.median(xs), pct(xs, 0.95), max(xs)))
    xs = []
    for _ in range(200):
        ctx.store.listener("evidence")          # keep the gap non-empty is not needed
        xs.append(call("what_did_i_miss")[1])
    w("| `what_did_i_miss` (template) | %.1f | %.1f | %.1f |\n" % (
        statistics.median(xs), pct(xs, 0.95), max(xs)))

    # ---- precomputed summaries, mechanism only (a SIMULATED model)
    from sideline import summaries
    from sideline.language import bedrock as _bd
    from sideline.poller import poll_once as _poll
    saved = (_bd._converse, _bd.ENABLED, _bd.HAVE_BOTO3, summaries.MODE)
    SIM_MS = 800

    def slow_model(system, user_text, max_tokens=160):
        if not _bd.ENABLED:
            return None
        time.sleep(SIM_MS / 1000.0)
        return "Arsenal went ahead and Tottenham answered; that is where it stands."

    _bd._converse, _bd.ENABLED, _bd.HAVE_BOTO3 = slow_model, True, True
    rows = []
    try:
        for mode in ("live", "cached"):
            summaries.MODE = mode
            summaries.CACHE.clear()
            c2 = Context(ReplayProvider(CONFIG.replay_path, speed=0.0001, start_minute=0),
                         MemoryStore(), language)
            REGISTRY["follow_match"](c2, {"team": "Arsenal"}, "e")
            c2.provider.jump_to(60)
            _poll(c2)
            deadline = time.time() + 5
            while mode == "cached" and time.time() < deadline and not len(summaries.CACHE):
                time.sleep(0.02)
            t0 = time.perf_counter()
            _, st, _ = REGISTRY["what_did_i_miss"](c2, {}, "e")
            rows.append((mode, st["summary_source"], (time.perf_counter() - t0) * 1000))
    finally:
        _bd._converse, _bd.ENABLED, _bd.HAVE_BOTO3, summaries.MODE = saved
    w("## Precomputed catch-up (mechanism only)\n")
    w("**The model here is a stand-in that sleeps %d ms. This is not Bedrock and says" % SIM_MS)
    w("nothing about Bedrock's real latency, which has not been measured.** It shows")
    w("only where that wait lands: on the listener, or in the background.\n")
    w("| `SIDELINE_CATCHUP_MODE` | `summary_source` | `what_did_i_miss` time |\n|---|---|---|")
    for mode, src, ms in rows:
        w("| %s | %s | %.1f ms |" % (mode, src, ms))
    w("")

    # ---- telemetry
    t = Client()
    t.rpc("initialize", {"protocolVersion": "2025-11-25", "capabilities": {},
                         "clientInfo": {"name": "t", "version": "1"}})
    t.bytes_body = t.bytes_wire = 0
    ticks = 0
    for minute in range(0, 91):
        for _ in range(4):                       # one snapshot every 15 s
            provider.jump_to(minute)
            t.rpc("tools/call", {"name": "get_match_state", "arguments": {}})
            ticks += 1
    w("## Data volume\n")
    w("One `get_match_state` call per 15 s across a 90-minute match "
      "(%d calls):\n" % ticks)
    w("| | |\n|---|---|")
    w("| Response bodies only | %.0f KB (%d bytes per call) |" % (
        t.bytes_body / 1024.0, t.bytes_body // ticks))
    w("| Estimated on the wire, both directions, incl. HTTP headers | %.0f KB |" % (
        t.bytes_wire / 1024.0))
    w("| Not included | the spoken audio Alexa+ would stream to the listener |\n")
    srv.shutdown()

    # ---- repo facts
    w("## Repository facts\n")
    py = sh("git", "ls-files", "*.py").split()
    loc = sum(len(open(os.path.join(ROOT, p), encoding="utf-8").read().splitlines()) for p in py)
    tests = sorted(f for f in os.listdir(os.path.join(ROOT, "tests")) if f.startswith("test_"))
    w("| | |\n|---|---|")
    w("| Tracked Python files | %d (%d lines) |" % (len(py), loc))
    w("| Test suites | %d (`make test`) |" % len(tests))
    w("| First commit | %s |" % (sh("git", "log", "--reverse", "--format=%ad", "--date=short").splitlines() or ["?"])[0])
    w("| Third-party imports in the server | boto3 and cryptography, both optional; the rest is the standard library |\n")

    # ---- what is NOT verified
    have_aws = bool(os.environ.get("AWS_ACCESS_KEY_ID") and os.environ.get("AWS_SECRET_ACCESS_KEY"))
    have_feed = bool(os.environ.get("SIDELINE_FOOTBALL_KEY"))
    w("## Not verified yet\n")
    w("These need credentials this script does not use. Until the command has")
    w("been run and its output kept, treat each as **unverified**.\n")
    w("| Claim | Status | Verify with |\n|---|---|---|")
    w("| Bedrock catch-up works and its latency | not measured | `make aws-check` |")
    w("| The default Bedrock model id is available | not checked | `make aws-check` |")
    w("| Precomputed summaries with the real model (hit rate, latency) | tested with a simulated model only | `make aws-check`, then ask after a poll and read `summary_source` |")
    w("| DynamoDB state, incl. conditional-put dedupe | not run against DynamoDB or DynamoDB Local | `make create-table` then `make run` |")
    w("| Polly speech and word marks, Transcribe streaming | not run | `make aws-check`, then the simulator |")
    w("| Live football feed (API-Football) | tested against canned responses only | `make verify-data` |")
    w("| CloudFormation stack deploys | passes `cfn-lint`; never deployed | `make deploy` (costs money; tear down after) |")
    w("| Python 3.8 compatibility | not run locally (this machine: %s); CI is configured for 3.8 and 3.12 and has not run | push and read the CI result |" % platform.python_version())
    w("| Any real Alexa+ device or account link | **impossible**: the tooling is partner-only (Devpost FAQ) | n/a |")
    w("| Use by a blind or low-vision person | no one has tested it | a session with a real person |")
    w("\nCredentials detected in this environment when this ran: AWS keys: %s; football key: %s.\n" % (
        "present" if have_aws else "absent", "present" if have_feed else "absent"))

    text = "\n".join(out) + "\n"
    if "--print" in sys.argv:
        print(text)
    else:
        with open(os.path.join(ROOT, "docs", "EVIDENCE.md"), "w", encoding="utf-8") as fh:
            fh.write(text)
        print("wrote docs/EVIDENCE.md")


if __name__ == "__main__":
    main()
