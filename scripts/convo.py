#!/usr/bin/env python3
"""Run a conversation against the MCP tools, live, as one listener, and show what they would hear and what it cost.

    python3 scripts/convo.py tests/conversations/batch-01.json

Each turn is {"say": what the listener says, "tool": the tool a model should pick, "args": its arguments}. There is no
model here: the file is the model's choice, so a wrong pick is a finding about tool names and descriptions, and a
weak answer is a finding about the tool. The turns run in order in one session, so "they" and "that" have to work.
"""

import json
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ask   # noqa: E402  (same folder; sets the offline-safe environment)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    with open(sys.argv[1]) as fh:
        turns = json.load(fh)
    session = ask.Session(replay=False)
    total = time.time()
    for i, t in enumerate(turns, 1):
        print("\n" + "=" * 78)
        print("%d. LISTENER: %s" % (i, t["say"]))
        print("   [%s %s]" % (t["tool"], json.dumps(t.get("args") or {}, ensure_ascii=False)))
        session.ask("%s %s" % (t["tool"], json.dumps(t.get("args") or {})))
    print("=" * 78 + "\n%d turns in %.1f s" % (len(turns), time.time() - total))
    return 0


if __name__ == "__main__":
    sys.exit(main())
