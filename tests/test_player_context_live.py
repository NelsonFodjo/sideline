"""'Tell me about the goalkeeper who saved the penalty' and 'who was the most dangerous player': real PSG v Man City data.

Found in conversation batch 1: the answer was "Gianluigi Donnarumma, Manchester City, started." and "he" after a finished
match was a substitute from its last minute.
"""

import json
import os

from conftest import make_ctx

from sideline.mcp.errors import ToolError
from sideline.providers.espn import EspnProvider
from sideline.tools import get_player_context

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with open(os.path.join(HERE, "fixtures", "espn-psg-city-summary.json")) as fh:
        summary = json.load(fh)
    p = EspnProvider()
    fid = "401915407"
    p._event_meta[fid] = ("soccer", "football", "uefa.champions")
    p._fetch_summary = lambda sport, league, f: summary
    lineups = p.lineups(fid)
    city = lineups["Manchester City"]
    assert city["numbers"]["Gianluigi Donnarumma"] == "1" and city["positions"]["Gianluigi Donnarumma"] == "goalkeeper", city["numbers"]
    assert city["match_stats"]["Gianluigi Donnarumma"] == {"appearances": 1, "goalsConceded": 4, "saves": 6}
    assert city["match_stats"]["Erling Haaland"]["totalGoals"] == 2 and city["match_stats"]["Erling Haaland"]["totalShots"] == 8
    print("ok  the roster gives shirt number, position and what each player did in the match")

    ctx = make_ctx()
    ctx.provider.lineups = p.lineups
    ctx.provider.events = lambda fixture_id, since_minute=0: p._soccer_events(fixture_id, summary, since_minute)
    fx = {"fixture_id": fid, "home": "Manchester City", "away": "Paris Saint-Germain", "status": "FT", "minute": 90,
          "score": {"home": 2, "away": 4}, "sport": "football", "kickoff": "2026-10-14T19:00Z"}
    ctx.provider.fixture = lambda f: dict(fx)
    L = "u"
    rec = ctx.store.listener(L)
    rec["discussed"] = {"fixture_id": fid, "at": __import__("time").time()}
    ctx.store.save_listener(rec)

    spoken, structured, _ = get_player_context.run(ctx, {"player": "Donnarumma", "fixture_id": fid}, L)
    assert spoken.startswith("Gianluigi Donnarumma, Manchester City goalkeeper, number 1, started. In this match: 6 saves and 4 conceded."), spoken
    assert "Ferran Torres's penalty was saved by Gianluigi Donnarumma on 90" in spoken, spoken
    print("ok  the keeper who saved the penalty:\n    " + spoken)

    spoken, _, _ = get_player_context.run(ctx, {"player": "Haaland", "fixture_id": fid}, L)
    assert spoken == ("Erling Haaland, Manchester City forward, number 9, started. "
                      "In this match: 2 goals and 8 shots with 3 on target. Goals on 53 and 75."), spoken
    print("ok  the scorer: " + spoken[:150])

    for pronoun in ("he", "that player"):
        try:
            get_player_context.run(ctx, {"player": pronoun, "fixture_id": fid}, L)
            raise AssertionError("'he' after a finished match must not be guessed")
        except ToolError as e:
            assert e.detail["reason"] == "pronoun_unresolved" and e.detail["match_over"], e.detail
            assert e.spoken.startswith("That match is over, so I can't tell who you mean by that."), e.spoken
    print("ok  'he' after the final whistle is asked about, never a substitute from the 90th minute")

    # who stood out: counted, ranked openly, never a made-up rating
    from sideline.tools import get_standouts
    spoken, structured, _ = get_standouts.run(ctx, {"fixture_id": fid}, L)
    names = [p["name"] for p in structured["standouts"]]
    assert names[0] == "Erling Haaland" and "Gianluigi Donnarumma" in names and len(names) <= 4, names
    assert "no player ratings" in spoken and "Erling Haaland, Manchester City: 2 goals and 8 shots with 3 on target" in spoken, spoken
    assert "man of the match" not in spoken.lower()
    print("ok  who stood out, by what is counted, with the ranking said:\n    " + spoken[:210] + "...")
    ctx.provider.lineups = lambda f: {}
    try:
        get_standouts.run(ctx, {"fixture_id": fid}, L)
        raise AssertionError("no player numbers must be said")
    except ToolError as e:
        assert e.detail["reason"] == "no_player_stats"
    print("ok  with no player numbers from the feed it says so")

    assert get_player_context._did({}) == "" and get_player_context._did({"saves": 1}) == "1 save"
    assert get_player_context._did({"totalGoals": 1, "goalAssists": 2}) == "1 goal and 2 assists"
    print("ok  a player who did nothing measurable is not given an empty sentence")


if __name__ == "__main__":
    main()
    print("\nplayer context (real match): all good")
