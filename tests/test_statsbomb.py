"""Regressions found by replaying a real match (Spurs 2-2 Arsenal,
2016-03-05, StatsBomb Open Data). A hand-made fixture hid all three:

  * a second yellow card was reported as a yellow, so the listener never
    heard that a player had been sent off
  * a booking filed under "Bad Behaviour" instead of "Foul Committed"
    was dropped
  * the starting XI came out in file order, so the spoken line-up put a
    forward in goal
"""

import json
import os
import tempfile

from conftest import make_ctx  # noqa: F401  (puts the repo root on sys.path)

from sideline.providers.statsbomb import StatsBombProvider


def _write(doc):
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False)
    json.dump(doc, f)
    f.close()
    return f.name


def _ev(minute, **extra):
    base = {"period": 1 if minute <= 45 else 2, "minute": minute, "team": {"name": "Arsenal"},
            "player": {"name": "Francis Coquelin"}}
    base.update(extra)
    return base


def main():
    events = [
        _ev(28, type={"id": 22}, foul_committed={"card": {"name": "Yellow Card"}}),
        _ev(54, type={"id": 22}, foul_committed={"card": {"name": "Second Yellow"}}),
        _ev(65, type={"id": 24, "name": "Bad Behaviour"},
            bad_behaviour={"card": {"name": "Yellow Card"}}),
        _ev(70, type={"id": 22}, foul_committed={"card": {"name": "Red Card"}}),
        _ev(75, type={"id": 16}, shot={"outcome": {"name": "Goal"},
                                       "body_part": {"name": "Right Foot"}}),
    ]
    lineups = [{"team_name": "Arsenal", "lineup": [
        {"player_name": "Striker", "jersey_number": 9,
         "positions": [{"position_id": 23, "start_reason": "Starting XI"}]},
        {"player_name": "Keeper", "jersey_number": 1,
         "positions": [{"position_id": 1, "start_reason": "Starting XI"}]},
        {"player_name": "Fullback", "jersey_number": 2,
         "positions": [{"position_id": 2, "start_reason": "Starting XI"}]},
        {"player_name": "Unused sub", "jersey_number": 18, "positions": []},
        {"player_name": "Came on", "jersey_number": 14,
         "positions": [{"position_id": 23, "start_reason": "Substitution - On"}]},
    ]}]
    ep, lp = _write(events), _write(lineups)
    try:
        p = StatsBombProvider(ep, lp)
        cards = [(e["minute"], e["colour"]) for e in p.to_events(1) if e["kind"] == "card"]
        assert cards == [(28, "yellow"), (54, "red"), (65, "yellow"), (70, "red")], cards
        print("ok  second yellow -> red; a Bad Behaviour booking is kept")

        goal = [e for e in p.to_events(1) if e["kind"] == "goal"][0]
        assert goal["detail"] == "right foot", goal["detail"]
        print("ok  body part is spoken lower-case: 'right foot'")

        lu = p.lineups(1)["Arsenal"]
        assert lu["xi"] == ["Keeper", "Fullback", "Striker"], lu["xi"]
        assert lu["bench"] == ["Unused sub", "Came on"], lu["bench"]
        print("ok  starting XI is goalkeeper first, back to front")
    finally:
        os.unlink(ep)
        os.unlink(lp)

    # The bundled replay is the genuine match, and says so.
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    with open(os.path.join(root, "data", "replay", "spurs-arsenal-2016.json")) as fh:
        doc = json.load(fh)
    assert "StatsBomb" in doc["_attribution"]
    assert doc["fixture"]["home"] == "Tottenham Hotspur"
    reds = [e for e in doc["events"] if e["kind"] == "card" and e["colour"] == "red"]
    assert [e["player"] for e in reds] == ["Francis Joseph Coquelin"]
    print("ok  the real-match replay carries attribution and Coquelin's red")

    print("\nstatsbomb: all good")


if __name__ == "__main__":
    main()
