#!/usr/bin/env python3
"""Capture a real match into the replay format.

    export SIDELINE_FOOTBALL_KEY=...
    python scripts/record_match.py --fixture 1208341 --out data/replay/real.json

Run it live and it polls to full time. Run it after the match and it
captures the finished record in one pass, which is usually what you want
the night before filming.

The output feeds providers/replay.py. See docs/DATA_PROVIDERS.md.
"""

import argparse
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sideline.providers.apifootball import ApiFootballProvider  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fixture", type=int, required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--live", action="store_true",
                    help="poll until full time instead of one pass")
    ap.add_argument("--interval", type=int, default=20)
    args = ap.parse_args()

    p = ApiFootballProvider()
    if not p.api_key:
        sys.exit("set SIDELINE_FOOTBALL_KEY")

    seen = {}
    while True:
        fx = p.fixture(args.fixture)
        if not fx:
            sys.exit("fixture not found")
        for e in p.events(args.fixture):
            key = (e["minute"], e["kind"], e.get("player"))
            seen[key] = e
        print("\r%s %d-%d  %s'  %d events" % (
            fx["home"], fx["score"]["home"], fx["score"]["away"],
            fx["minute"], len(seen)), end="", flush=True)
        if not args.live or fx.get("status") in ("FT", "finished"):
            break
        time.sleep(args.interval)

    events = []
    for e in sorted(seen.values(), key=lambda x: x["minute"]):
        row = {k: v for k, v in e.items()
               if k in ("minute", "stoppage", "kind", "player", "player_off",
                        "team", "assist", "detail", "colour", "reason", "decision")}
        events.append(row)

    doc = {
        "_comment": "Captured with scripts/record_match.py. Real match data.",
        "fixture": {k: fx[k] for k in ("fixture_id", "home", "away",
                                       "home_id", "away_id", "venue", "kickoff")},
        "events": events,
        "lineups": p.lineups(args.fixture),
        "officials": p.officials(args.fixture),
        "head_to_head": p.head_to_head(args.fixture, 5),
    }
    with open(args.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    print("\nwrote %s - %d events" % (args.out, len(events)))


if __name__ == "__main__":
    main()
