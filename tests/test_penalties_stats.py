"""Penalties and the statistics table, from a real ESPN summary (Manchester City 2, Paris Saint-Germain 4).

In that match PSG won a penalty on 87 (Nuno Mendes fouled by Matheus Nunes) and Ferran Torres' kick was saved by
Gianluigi Donnarumma on 90. The parser used to drop it, so the match report never mentioned it.
"""

import json
import os

from conftest import make_ctx

from sideline.providers.espn import EspnProvider
from sideline.tools import get_match_stats
from sideline.sports import football

HERE = os.path.dirname(os.path.abspath(__file__))


def main():
    with open(os.path.join(HERE, "fixtures", "espn-psg-city-summary.json")) as fh:
        summary = json.load(fh)
    p = EspnProvider()
    events = p._soccer_events("401915407", summary, since_minute=0)
    by_kind = {}
    for e in events:
        by_kind.setdefault(e["kind"], []).append(e)

    pens = sorted(by_kind["penalty"], key=lambda e: e["minute"])
    assert [e["outcome"] for e in pens] == ["awarded", "saved"], pens
    awarded, saved = pens
    assert (awarded["minute"], awarded["player"], awarded["conceded_by"]) == (87, "Nuno Mendes", "Matheus Nunes"), awarded
    assert awarded["team"] == "Paris Saint-Germain", awarded
    assert (saved["minute"], saved["player"], saved["keeper"]) == (90, "Ferran Torres", "Gianluigi Donnarumma"), saved
    print("ok  the penalty on 87 and the save on 90 are both in the events")

    sp = football.Football()
    assert sp.say_event(awarded) == "Paris Saint-Germain were awarded a penalty on 87, after Nuno Mendes was fouled by Matheus Nunes", sp.say_event(awarded)
    assert sp.say_event(saved) == "Ferran Torres's penalty was saved by Gianluigi Donnarumma on 90", sp.say_event(saved)
    print("ok  said as a person would:", sp.say_event(saved))

    goals = by_kind["goal"]
    assert len(goals) == 6 and all(g["team"] for g in goals), [g["team"] for g in goals]
    assert {g["player"]: g["team"] for g in goals}["Erling Haaland"] == "Manchester City"
    assert [g["assist"] for g in goals if g["player"] == "Iliman Ndiaye"] == []
    assert next(g for g in goals if g["minute"] == 53)["assist"] == "Iliman Ndiaye", "no 'with a cross' in the name"
    print("ok  every goal has its team, and an assist is a name")

    subs = {(e["player"], e["player_off"]) for e in by_kind["substitution"]}
    assert ("Nico O'Reilly", "Enzo Fernández") in subs, subs
    print("ok  names with an apostrophe survive: Nico O'Reilly")

    assert p._clock_minute("90'+4'") == (90, 4) and p._clock_minute("45'+2'") == (45, 2) and p._clock_minute("13'") == (13, 0)
    print("ok  stoppage time is read: 90'+4' is minute 90, four added")

    # the statistics: every metric asked for, worked out from the feed's own counts
    p._event_meta["401915407"] = ("soccer", "football", "uefa.champions")
    p._fetch_summary = lambda sport, league, fid: summary
    stats = p.match_stats("401915407")
    city, psg = stats["Manchester City"], stats["Paris Saint-Germain"]
    rows = {r["metric"]: r for r in get_match_stats.table_rows(city, psg)}
    assert rows["Possession (%)"] == {"metric": "Possession (%)", "home": "54%", "away": "46%"}, rows["Possession (%)"]
    assert (rows["Total shots (on target)"]["home"], rows["Total shots (on target)"]["away"]) == ("27 (9)", "15 (10)")
    assert (rows["Pass accuracy (%)"]["home"], rows["Pass accuracy (%)"]["away"]) == ("85% (423/499)", "84% (374/444)")
    assert (rows["Fouls / yellow cards / red cards"]["home"], rows["Fouls / yellow cards / red cards"]["away"]) == ("10 / 1 / 0", "11 / 1 / 0")
    assert (rows["Corners"]["home"], rows["Corners"]["away"]) == ("11", "2")
    assert (rows["Offsides"]["home"], rows["Offsides"]["away"]) == ("2", "0")
    assert (rows["Goalkeeper saves"]["home"], rows["Goalkeeper saves"]["away"]) == ("6", "6")
    assert rows["Expected goals (xG)"]["home"] == "not provided", "an xG the feed does not give is never made up"
    print("ok  the statistics table matches the feed's numbers; xG is said to be missing, not invented")

    spoken = get_match_stats._football_spoken("Manchester City", "Paris Saint-Germain", list(rows.values()), city, psg)
    assert "not provided" not in spoken and "expected goals" in spoken and "Cards: Manchester City 1 yellow, Paris Saint-Germain 1 yellow" in spoken, spoken
    print("ok  and it reads aloud cleanly")


if __name__ == "__main__":
    main()
    print("\npenalties and statistics: all good")
