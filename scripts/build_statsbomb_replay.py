#!/usr/bin/env python3
"""Turn a StatsBomb Open Data match into a replay file.

    git clone --depth 1 https://github.com/statsbomb/open-data
    python scripts/build_statsbomb_replay.py \
        --events  open-data/data/events/<match_id>.json \
        --lineups open-data/data/lineups/<match_id>.json \
        --home "Team A" --away "Team B" --out data/replay/match.json

Produces the same shape providers/replay.py already reads, so nothing
downstream changes. Real data, deterministic playback, no API key, no
rate limit.

StatsBomb's licence requires attribution. It is written into the output
file and surfaced in the README and the video description.
"""

import argparse
import json
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sideline.providers.statsbomb import ATTRIBUTION, StatsBombProvider  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events", required=True)
    ap.add_argument("--lineups")
    ap.add_argument("--home", required=True)
    ap.add_argument("--away", required=True)
    ap.add_argument("--fixture-id", type=int, default=1)
    ap.add_argument("--venue", default="")
    ap.add_argument("--referee", default="",
                    help="from the matches file; the events file does not carry it")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    p = StatsBombProvider(a.events, a.lineups)
    events = p.to_events(a.fixture_id)

    rows = []
    for e in events:
        rows.append({k: v for k, v in e.items()
                     if k in ("minute", "stoppage", "kind", "player",
                              "player_off", "team", "assist", "detail",
                              "colour", "reason", "decision")
                     and v not in (None, "")})

    officials = p.officials(a.fixture_id)
    if a.referee:
        officials = dict(officials, referee=a.referee)
        officials.pop("note", None)

    doc = {
        "_comment": "Built from StatsBomb Open Data. Real match, real events.",
        "_attribution": ATTRIBUTION,
        "fixture": {"fixture_id": a.fixture_id, "home": a.home, "away": a.away,
                    "home_id": 1, "away_id": 2, "venue": a.venue, "kickoff": None},
        "events": rows,
        "lineups": p.lineups(a.fixture_id),
        "officials": officials,
        "head_to_head": [],
    }
    with open(a.out, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, indent=2, ensure_ascii=False)
    print("wrote %s - %d events" % (a.out, len(rows)))
    print(ATTRIBUTION)


if __name__ == "__main__":
    main()
