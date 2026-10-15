#!/usr/bin/env python3
"""Baseline numbers for the MCP: what each tool costs, and what the tool list costs the model every turn.

    python3 scripts/bench.py                    # table
    python3 scripts/bench.py --json out.json    # keep a baseline to compare against
    python3 scripts/bench.py --check            # exit 1 if a starting budget is exceeded

Offline: the invented replay fixtures, no network, no AWS. So the timings are OUR overhead (resolve, store, spoiler
guard, wording), not the feed's, and the number that matters most here is how many calls a tool makes to the provider:
on the live feed each one is a network round trip. The correctness set is tests/test_questions.py.

Token counts are an estimate (characters / 4): good for comparing two versions of the tool list, not for billing.
"""

import argparse
import json
import os
import statistics
import sys
import time

ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ.setdefault("SIDELINE_STATE", "memory")
os.environ.setdefault("SIDELINE_LOG_DIR", "off")
os.environ["SIDELINE_BEDROCK"] = "off"                 # templates, so the timing is not a model's

from conftest import FOOTBALL, age_events, make_ctx    # noqa: E402

from sideline.mcp import registry                       # noqa: E402
from sideline.mcp.errors import ToolError               # noqa: E402
from sideline.poller import poll_once                   # noqa: E402
from sideline.tools import REGISTRY                     # noqa: E402

# Starting targets, to be revised after the first baseline. Offline, so they bound our overhead only.
BUDGET = {"p95_ms": 50.0, "provider_calls": 4, "spoken_words": 60}

LISTENER = "bench"
ARGS = {
    "follow_match": {"team": "Arsenal"}, "get_match_state": {}, "get_fixtures": {}, "search": {"query": "Arsenal"},
    "get_competitions": {}, "get_standings": {}, "get_top_scorers": {}, "get_schedule": {"team": "Arsenal"},
    "get_match_stats": {}, "get_player_stats": {"player": "Saka"}, "get_injuries": {},
    "get_team_form": {"team": "Arsenal"}, "get_squad": {"team": "Arsenal"}, "get_team_stats": {"team": "Arsenal"},
    "set_favourites": {"action": "add", "teams": ["Arsenal"]}, "get_my_matches": {},
    "set_preferences": {"detail": "brief"}, "get_capabilities": {}, "get_match_preview": {},
    "get_match_report": {}, "get_lineups": {}, "what_did_i_miss": {}, "get_event_detail": {"kind": "goal"},
    "get_officials": {}, "get_player_context": {"player": "Saka"}, "get_head_to_head": {},
    "sync_broadcast_delay": {"check": True}, "get_player_profile": {"player": "Saka"}, "get_news": {"team": "Arsenal"},
    "get_standouts": {},
}


class CountingProvider(object):
    """Wraps a provider and counts every call made through it."""

    def __init__(self, inner):
        self._inner = inner
        self.calls = 0

    def __getattr__(self, name):
        attr = getattr(self._inner, name)
        if not callable(attr):
            return attr

        def counted(*a, **kw):
            self.calls += 1
            return attr(*a, **kw)
        return counted


def listing():
    """The tool list as a client receives it, sized."""
    rows = []
    for spec in registry.public_tools():
        chars = len(json.dumps(spec, separators=(",", ":")))
        rows.append({"tool": spec["name"], "chars": chars, "tokens": chars // 4})
    core = sum(len(json.dumps(s, separators=(",", ":"))) for s in registry.public_tools(core_only=True))
    return {"tools": len(rows), "tokens": sum(r["tokens"] for r in rows), "core_tokens": core // 4,
            "per_tool": sorted(rows, key=lambda r: -r["tokens"])}


def fresh():
    """A listener following Arsenal at 64', a while after the events were logged."""
    ctx = make_ctx(start_minute=0, replay=FOOTBALL)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, LISTENER)
    ctx.provider.jump_to(64)
    poll_once(ctx)
    age_events(ctx)
    ctx.provider = CountingProvider(ctx.provider)
    return ctx


def measure(tool, runs):
    times, calls, words, status = [], [], 0, "ok"
    for _ in range(runs):
        ctx = fresh()
        start = time.perf_counter()
        try:
            spoken = REGISTRY[tool](ctx, dict(ARGS[tool]), LISTENER)[0]
        except ToolError as e:
            spoken, status = e.spoken, "declined"
        times.append((time.perf_counter() - start) * 1000.0)
        calls.append(ctx.provider.calls)
        words = len((spoken or "").split())
    times.sort()
    return {"tool": tool, "status": status, "p50_ms": statistics.median(times),
            "p95_ms": times[min(len(times) - 1, int(len(times) * 0.95))], "provider_calls": max(calls),
            "spoken_words": words}


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--runs", type=int, default=30, help="timed runs per tool (default 30)")
    ap.add_argument("--json", metavar="PATH", help="also write the numbers here")
    ap.add_argument("--check", action="store_true", help="exit 1 if a starting budget is exceeded")
    opts = ap.parse_args()

    lst = listing()
    rows = [measure(t["name"], opts.runs) for t in registry.public_tools() if t["name"] in ARGS]
    missing = [t["name"] for t in registry.public_tools() if t["name"] not in ARGS]

    print("tools/list: %d tools, about %d tokens (core set: about %d)" % (lst["tools"], lst["tokens"], lst["core_tokens"]))
    print("largest: " + ", ".join("%s %d" % (r["tool"], r["tokens"]) for r in lst["per_tool"][:5]))
    print()
    print("%-22s %8s %8s %6s %6s  %s" % ("tool", "p50 ms", "p95 ms", "calls", "words", "status"))
    over = []
    for r in rows:
        flags = []
        if r["p95_ms"] > BUDGET["p95_ms"]:
            flags.append("slow")
        if r["provider_calls"] > BUDGET["provider_calls"]:
            flags.append("calls")
        if r["spoken_words"] > BUDGET["spoken_words"]:
            flags.append("long")
        if flags:
            over.append((r["tool"], flags))
        print("%-22s %8.2f %8.2f %6d %6d  %s%s" % (r["tool"], r["p50_ms"], r["p95_ms"], r["provider_calls"],
                                                   r["spoken_words"], r["status"], ("  OVER: " + ",".join(flags)) if flags else ""))
    if missing:
        print("\nno benchmark arguments for: " + ", ".join(missing))
    print("\nstarting budgets (offline): p95 %.0f ms, %d provider calls, %d spoken words"
          % (BUDGET["p95_ms"], BUDGET["provider_calls"], BUDGET["spoken_words"]))

    if opts.json:
        with open(opts.json, "w") as fh:
            json.dump({"listing": lst, "tools": rows, "budget": BUDGET}, fh, indent=2)
        print("wrote " + opts.json)
    if opts.check and (over or missing):
        print("budget check failed: %s" % ", ".join("%s (%s)" % (t, "/".join(f)) for t, f in over) or "missing args")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
