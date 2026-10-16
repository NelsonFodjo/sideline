"""Fixes found by asking a hundred questions across basketball, American football, hockey and baseball (16 October 2026)."""

import os
import sys
from types import SimpleNamespace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests"))
os.environ["SIDELINE_STATE"] = "memory"

from simulator import agent                         # noqa: E402
from sideline import resolve                        # noqa: E402
from sideline.providers.espn import EspnProvider    # noqa: E402
from sideline.tools import get_squad, get_team_stats  # noqa: E402


def main():
    # a person is not a misheard team
    items = list(resolve.items_from_names(["Aston Villa", "Bukayo Saka", "Arsenal"]))
    assert resolve.fix_names("goals for Auston Matthews", items) == "goals for Auston Matthews"
    assert resolve.fix_names("Bukaiyo Saka scored", items) == "Bukayo Saka scored"
    assert resolve.fix_names("what about Arsenl", items) == "what about Arsenal"
    print("ok  'Auston Matthews' is no longer turned into 'Aston', while 'Bukaiyo Saka' and 'Arsenl' are still repaired")

    # a season line in each sport's own words
    line = EspnProvider._season_line
    split = lambda **kw: [{"displayName": "Regular Season", "stats": list(kw.values())}]       # noqa: E731
    assert line("basketball", ["gamesPlayed", "avgPoints", "avgRebounds", "avgAssists"], split(a="64", b="25.0", c="11.5", d="3.1")) == \
        "regular season, 64 games: 25 points, 11.5 rebounds and 3.1 assists a game"
    assert line("hockey", ["games", "goals", "assists", "points"], split(a="7", b="4", c="14", d="18")) == \
        "regular season, 7 games: 4 goals, 14 assists and 18 points"
    assert line("baseball", ["gamesPlayed", "hits", "homeRuns", "RBIs"], split(a="135", b="144", c="30", d="81")) == \
        "regular season, 135 games: 144 hits, 30 home runs and 81 runs batted in"
    assert line("football", ["passingYards", "passingTouchdowns", "interceptions"], split(a="1,037", b="9", c="2")) == \
        "regular season: 1037 passing yards, 9 touchdown passes and 2 interceptions"
    assert line("basketball", ["gamesPlayed"], [{"displayName": "Projected", "stats": ["82"]}]) is None
    print("ok  a player's season figures are said in basketball, hockey, baseball and football words, only from what the feed lists")

    # a team's record: no draws, no goals, in basketball
    feed = SimpleNamespace(team_stats=lambda team: {"team": "Los Angeles Lakers", "played": 0, "won": 2, "drawn": 0, "lost": 2,
                                                    "goals_for": 428, "goals_against": 438, "sport": "basketball", "record": "2-2"})
    spoken, _, _ = get_team_stats.run(SimpleNamespace(provider=feed), {"team": "Lakers"}, "x")
    assert spoken == "Los Angeles Lakers this season: won 2, lost 2.", spoken
    print("ok  a basketball record is 'won 2, lost 2', not '0 games, drew 0, 428 goals scored'")

    # one player's game, from a box score
    gl = EspnProvider._game_line
    assert gl("basketball", "", {"points": "20", "rebounds": "3", "assists": "7", "minutes": "29"}) == "20 points, 3 rebounds and 7 assists in 29 minutes"
    assert gl("hockey", "forwards", {"goals": "0", "assists": "1", "shotsTotal": "2", "timeOnIce": "25:52"}) == "0 goals, 1 assist and 2 shots in 25:52 on the ice"
    assert gl("baseball", "batting", {"hits-atBats": "1-4", "hits": "1", "homeRuns": "1", "RBIs": "3", "runs": "1"}) == \
        "batted 1-4, with 1 home run, 3 runs batted in and 1 run"
    assert gl("baseball", "pitching", {"fullInnings.partInnings": "4.1", "hits": "3", "runs": "2", "strikeouts": "5"}) == \
        "pitched 4.1 innings, 3 hits, 2 runs and 5 strikeouts"
    assert gl("american_football", "passing", {"passingYards": "225", "passingTouchdowns": "2", "interceptions": "0"}) == \
        "225 passing yards, 2 touchdowns and 0 interceptions"
    print("ok  a player's night is read from the box score in each sport's words")

    # a playoff series, with the teams' names
    comp = {"series": [{"summary": "MIL wins series 4-0"}]}
    home = {"team": {"abbreviation": "LAD", "displayName": "Los Angeles Dodgers"}}
    away = {"team": {"abbreviation": "MIL", "displayName": "Milwaukee Brewers"}}
    assert EspnProvider._series_text(comp, home, away) == "Milwaukee Brewers wins series 4-0"
    assert EspnProvider._series_text({"series": {"summary": "Series tied 2-2"}}, home, away) == "Series tied 2-2"
    assert EspnProvider._series_text({}, home, away) is None
    print("ok  a playoff series is said with the teams' names")

    # league leaders outside football
    class Fake(EspnProvider):
        def _fetch_json(self, url, **kw):
            leader = lambda n, t, v: {"athlete": {"displayName": n}, "team": {"displayName": t}, "displayValue": v, "value": float(v)}   # noqa: E731
            return {"requestedSeason": {"displayName": "2025-26", "type": {"name": "Regular Season"}},
                    "leaders": {"categories": [{"name": "pointsPerGame", "displayName": "Points Per Game",
                                                "leaders": [leader("Luka Doncic", "Los Angeles Lakers", "33.5")]},
                                               {"name": "reboundsPerGame", "displayName": "Rebounds Per Game",
                                                "leaders": [leader("Nikola Jokic", "Denver Nuggets", "12.9")]}]}}
    rows = Fake()._leaders("basketball", "nba", "rebounds")
    assert rows[0]["player"] == "Nikola Jokic" and rows[0]["value"] == "12.9" and rows[0]["season"] == "2025-26 regular season", rows
    assert Fake()._leaders("basketball", "nba", None)[0]["player"] == "Luka Doncic"
    print("ok  league leaders outside football come with the stat and the season they are from")

    # a squad outside football: positions in that sport's words
    squad = {"team": "Denver Broncos", "coach": "Sean Payton", "sport": "american_football",
             "players": [{"name": "Bo Nix", "number": "10", "position": "quarterback"},
                         {"name": "Sam Ehlinger", "number": "4", "position": "quarterback"},
                         {"name": "Courtland Sutton", "number": "14", "position": "wide receiver"}]}
    spoken, _, _ = get_squad._other_sport(squad, squad["players"], "quarterback")
    assert spoken == "Denver Broncos' quarterbacks: Bo Nix, number 10, Sam Ehlinger, number 4.", spoken
    spoken, _, _ = get_squad._other_sport(squad, squad["players"], "")
    assert spoken.startswith("Denver Broncos have 3 players. The feed lists Sean Payton as head coach"), spoken
    print("ok  a squad outside football lists quarterbacks, goalies or pitchers, and says the coach may be out of date")
    print("\nother sports: all good")


if __name__ == "__main__":
    main()
