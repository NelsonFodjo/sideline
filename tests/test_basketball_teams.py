"""A basket is credited to the right team: the feed names a play's team by id only, so the name comes from the game's header.

It was found by asking a catch-up on a real game (Knicks 122, Raptors 120): every basketball event had no team, and the answer put
a Raptors player on the Knicks.
"""

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ["SIDELINE_STATE"] = "memory"

from sideline.providers.espn import EspnProvider   # noqa: E402


def main():
    summary = {
        "header": {"competitions": [{"competitors": [
            {"team": {"id": "18", "displayName": "New York Knicks"}}, {"team": {"id": "28", "displayName": "Toronto Raptors"}}]}]},
        "plays": [
            {"period": {"number": 1}, "clock": {"displayValue": "10:30"}, "scoringPlay": True, "scoreValue": 2,
             "team": {"id": "28"}, "text": "RJ Barrett makes driving layup"},
            {"period": {"number": 1}, "clock": {"displayValue": "10:00"}, "scoringPlay": True, "scoreValue": 3,
             "team": {"id": "18"}, "text": "Jalen Brunson makes 26-foot three point jumper"},
            {"period": {"number": 1}, "clock": {"displayValue": "9:40"}, "scoringPlay": True, "scoreValue": 1,
             "team": {"displayName": "Toronto Raptors"}, "text": "Scottie Barnes makes free throw 1 of 1"},
        ],
    }
    events = EspnProvider()._basketball_events("1", summary, -1)
    assert [e["team"] for e in events] == ["Toronto Raptors", "New York Knicks", "Toronto Raptors"], [e["team"] for e in events]
    assert [e["player"] for e in events] == ["RJ Barrett", "Jalen Brunson", "Scottie Barnes"]
    print("ok  a basket is credited to the team the header names for the play's id")
    print("\nbasketball teams: all good")


if __name__ == "__main__":
    main()
