"""Fixes found by talking to the tools during a live AFC Champions League Two match (conversation batch 2).

Each is something a listener would have heard wrong: a live match called "not started", the referee left out without
a word, a group table read as one table, "my game" answered about another, and 76 requests to follow one match.
"""

from conftest import make_ctx

from sideline.mcp.errors import ToolError
from sideline.sports import football
from sideline.status import has_started, is_live
from sideline.tools import REGISTRY, resolve_fixture

L = "listener"


def main():
    # a match is live by its status, not by a minute that may still say 0
    assert is_live({"status": "1H", "minute": 0}) and is_live({"status": "live", "minute": 0})
    assert not is_live({"status": "NS", "minute": 0}) and not is_live({"status": "FT", "minute": 90})
    assert has_started({"status": "2H", "minute": 0}) and has_started({"status": "FT"}) and not has_started({"status": "NS"})
    fx = {"home": "Gangwon FC", "away": "Phnom Penh Crown", "score": {"home": 0, "away": 0}, "status": "1H", "minute": 0}
    assert football.Football().say_match_state(fx) == "Gangwon FC and Phnom Penh Crown, still goalless, just under way."
    print("ok  a match in play is never 'not started yet', whatever its minute says")

    # the referee: said to be unnamed, with the tense of the match
    ctx = make_ctx(start_minute=64)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, L)
    ctx.provider.officials = lambda fid: {"referee": None}
    spoken = REGISTRY["get_officials"](ctx, {}, L)[0]
    assert spoken.startswith("The feed doesn't name the referee for this match."), spoken
    assert "so far" in spoken, spoken
    ctx.provider.jump_to(90)
    spoken = REGISTRY["get_officials"](ctx, {}, L)[0]
    assert "in the match" in spoken and "so far" not in spoken, spoken
    ctx.provider.officials = lambda fid: {"referee": "Michael Oliver"}
    assert REGISTRY["get_officials"](ctx, {}, L)[0].startswith("Michael Oliver refereed."), "past tense once it is over"
    print("ok  an unnamed referee is said, and 'so far' becomes 'in the match' at full time")

    # a competition in groups
    table = [{"group": "Group H", "position": 1, "team": "Phnom Penh Crown", "points": 3, "played": 1},
             {"group": "Group H", "position": 2, "team": "Gangwon FC", "points": 1, "played": 1},
             {"group": "Group A", "position": 1, "team": "Al-Wahda", "points": 6, "played": 2}]
    ctx = make_ctx()
    ctx.provider.standings = lambda competition: [dict(r) for r in table]
    spoken = REGISTRY["get_standings"](ctx, {"competition": "AFC Champions League Two", "team": "Gangwon FC"}, L)[0]
    assert spoken == ("In AFC Champions League Two, Group H, Gangwon FC are second in the group with 1 point from 1 game. "
                      "Phnom Penh Crown lead the group with 3 points."), spoken
    spoken = REGISTRY["get_standings"](ctx, {"competition": "AFC Champions League Two"}, L)[0]
    assert spoken.startswith("AFC Champions League Two is played in 2 groups. The leaders: Group A, Al-Wahda, 6 points.")
    assert "Ask about a team for its group." in spoken and "First, Al-Wahda" not in spoken, spoken
    ctx.provider.standings = lambda competition: [{"position": 1, "team": "Arsenal", "points": 20, "played": 8}]
    assert REGISTRY["get_standings"](ctx, {"competition": "Ligue 1"}, L)[0].startswith("Ligue 1 table:"), "no 'the Ligue 1'"
    assert REGISTRY["get_standings"](ctx, {"competition": "English Premier League"}, L)[0].startswith("The English Premier League table:")
    print("ok  groups are read as groups, not as several teams all 'first'; 'the' only where people say it")

    # 'my game' is the one followed, not the one just asked about
    ctx = make_ctx(start_minute=40)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, L)
    rec = ctx.store.listener(L)
    rec["discussed"] = {"fixture_id": 999, "at": __import__("time").time()}          # they just asked about some other match
    ctx.store.save_listener(rec)
    mine = resolve_fixture(ctx, {}, L, followed_first=True)
    assert mine["fixture_id"] == rec["following"], mine
    print("ok  'what did I miss' is about the match they follow, not one they just asked in passing")

    # following costs a few requests: the team's schedule, not a scoreboard per sport per day
    class Schedules(object):
        calls = []

        def team_matches(self, team):
            self.calls.append("team_matches")
            return {"team": team, "team_id": "1", "recent": [], "upcoming": [
                {"fixture_id": "7", "home": "Gangwon FC", "away": "Phnom Penh Crown", "status": "1H", "minute": 5,
                 "kickoff": "2026-10-15T10:00Z", "score": {"home": 0, "away": 0}, "sport": "football"}]}

        def fixtures_on(self, offset_days=0, sport=None):
            self.calls.append("fixtures_on")
            return []
    from sideline.tools import matches_from_schedule
    prov = Schedules()
    ctx = make_ctx()
    ctx.provider = prov
    got = matches_from_schedule(ctx, "Gangwon", None, tz=0)
    assert got is not None and got[0]["fixture_id"] == "7" and prov.calls == ["team_matches"], (got, prov.calls)
    prov.team_matches = lambda team: None
    assert matches_from_schedule(ctx, "Nobody", None, tz=0) is None, "a team the feed does not know: the caller scans"
    print("ok  following a match reads one schedule, and falls back to the scan only for an unknown team")


if __name__ == "__main__":
    main()
    print("\nlive batch fixes: all good")
