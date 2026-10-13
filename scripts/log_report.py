#!/usr/bin/env python3
"""Summarise the call logs: what was used, how fast, what was declined.

    python3 scripts/log_report.py            # every day in logs/
    python3 scripts/log_report.py 2026-10-17 # one day

Reads logs/calls-<date>.jsonl (written by sideline/audit.py). Nothing is sent anywhere.
"""

import collections
import glob
import json
import os
import statistics
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import sideline  # noqa: E402,F401  (loads .env, environment wins)
from sideline.config import CONFIG  # noqa: E402


def load(directory, day=None):
    pattern = os.path.join(directory, "calls-%s.jsonl" % (day or "*"))
    for path in sorted(glob.glob(pattern)):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                try:
                    yield json.loads(line)
                except ValueError:
                    continue


def main():
    directory = os.path.abspath(CONFIG.log_dir if CONFIG.log_dir.lower() != "off" else "logs")
    rows = list(load(directory, sys.argv[1] if len(sys.argv) > 1 else None))
    if not rows:
        print("no call logs in %s yet (run the server first)" % directory)
        return 0
    tools = [r for r in rows if r["kind"] == "tool"]
    agent = [r for r in rows if r["kind"] == "agent"]
    stt = [r for r in rows if r["kind"] == "stt"]
    tokens = [r for r in rows if r["kind"] == "tokens"]
    first, last = rows[0]["time"], rows[-1]["time"]
    print("%d records, %s to %s\n" % (len(rows), first[:16], last[:16]))

    print("TOOL CALLS: %d (%d answered, %d declined or refused)" % (
        len(tools), sum(1 for r in tools if r["ok"]), sum(1 for r in tools if not r["ok"])))
    by = collections.defaultdict(list)
    for r in tools:
        by[r["tool"]].append(r)
    print("  %-22s %5s %6s %9s" % ("tool", "calls", "ok", "median ms"))
    for name, rs in sorted(by.items(), key=lambda kv: -len(kv[1])):
        print("  %-22s %5d %6d %9d" % (name, len(rs), sum(1 for r in rs if r["ok"]),
                                       statistics.median(r.get("ms") or 0 for r in rs)))
    reasons = collections.Counter(r.get("reason") for r in tools if not r["ok"])
    if reasons:
        print("  declined because: " + ", ".join("%s x%d" % (k, v) for k, v in reasons.most_common()))
    feed = [r for r in tools if r.get("reason") == "provider_unavailable"]
    if feed:
        print("  FEED ERRORS: %d, e.g. %s" % (len(feed), feed[-1].get("problem")))

    if agent:
        ok = [r for r in agent if r["ok"]]
        print("\nVOICE AGENT: %d turns (%d failed), median %d ms" % (
            len(agent), len(agent) - len(ok), statistics.median(r.get("ms") or 0 for r in agent)))
        used = collections.Counter(t for r in ok for t in (r.get("tools") or []))
        print("  tools chosen: " + ", ".join("%s x%d" % (k, v) for k, v in used.most_common(8)))
    if tokens:
        print("\nBEDROCK TOKENS (as counted by Bedrock): %d calls" % len(tokens))
        for (source, model), rs in sorted(collections.defaultdict(list, {
                k: [r for r in tokens if (r.get("source"), r.get("model")) == k]
                for k in {(r.get("source"), r.get("model")) for r in tokens}}).items()):
            print("  %-6s %-24s %5d calls, %7d in, %6d out" % (
                source, model, len(rs), sum(r.get("input") or 0 for r in rs), sum(r.get("output") or 0 for r in rs)))
    if stt:
        print("\nSPEECH IN: %d clips; by provider: %s" % (
            len(stt), ", ".join("%s x%d" % kv for kv in collections.Counter(r["provider"] for r in stt).most_common())))
        empty = sum(1 for r in stt if not r.get("heard"))
        if empty:
            print("  %d clips heard nothing (noise, typing or silence)" % empty)
    return 0


if __name__ == "__main__":
    sys.exit(main())
