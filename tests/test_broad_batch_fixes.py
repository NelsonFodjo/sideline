"""Fixes from the 50-question batch (tests/conversations/batch-03-broad.json): real situations that read wrong.

Roma 3-4 Real Madrid told only six goals and left out the 90th-minute winner; "Bodo/Glimt" took 42 requests; the NBA
table said "-2 points"; "yesterday" could not find last night's US game; line-ups not yet out read "in a standard shape".
"""

import datetime

from conftest import make_ctx

from sideline import clock, finder
from sideline.mcp.errors import ToolError
from sideline.providers.espn import EspnProvider
from sideline.state.store import Event
from sideline.tools import REGISTRY, no_team

L = "u"


def match(ctx, status="FT", minute=90):
    fx = {"fixture_id": "77", "home": "AS Roma", "away": "Real Madrid", "status": status, "minute": minute,
          "score": {"home": 3, "away": 4}, "sport": "football", "kickoff": "2026-10-14T19:00Z"}
    ctx.provider.fixture = lambda f: dict(fx)
    rec = ctx.store.listener(L)
    rec["discussed"] = {"fixture_id": "77", "at": __import__("time").time()}
    ctx.store.save_listener(rec)
    return fx


def main():
    # every goal of a football match, the winner last, with the penalty where it happened
    ctx = make_ctx()
    match(ctx)
    scorers = [(20, "de Roon", "AS Roma"), (25, "Mbappé", "Real Madrid"), (51, "Malen", "AS Roma"), (57, "Malen", "AS Roma"),
               (83, "Espí", "Real Madrid"), (85, "Endrick", "Real Madrid"), (90, "Rüdiger", "Real Madrid")]
    events = [Event.make("77", m, "goal", player=p, team=t) for m, p, t in scorers]
    events.append(Event.make("77", 87, "penalty", outcome="awarded", player="Soulé", team="AS Roma", conceded_by="Valverde"))
    for e in events:
        ctx.store.append_event(e)
    spoken = REGISTRY["get_match_report"](ctx, {"fixture_id": "77"}, L)[0]
    assert "Rüdiger scored on 90" in spoken and "more" not in spoken.replace("Ask for any", ""), spoken
    assert spoken.index("Endrick scored on 85") < spoken.index("awarded a penalty on 87") < spoken.index("Rüdiger scored on 90"), spoken
    print("ok  all seven goals, and the penalty in its place, before the 90th-minute winner")

    from sideline.sports import football
    pen_goal = {"kind": "goal", "minute": 68, "player": "Ross Barkley", "detail": "penalty", "stoppage": 0}
    assert football.Football().say_event(pen_goal) == "Ross Barkley scored a penalty on 68"
    print("ok  'scored a penalty on 68'")

    # a name with a slash must reach the search as words
    p = EspnProvider()
    urls = []
    p._fetch_json = lambda url, ttl=None, strict=False: urls.append(url) or {"results": []}
    p._find_team("bodo/glimt")
    assert "query=bodo%20glimt" in urls[0] and "%2F" not in urls[0], urls[0]
    print("ok  'Bodo/Glimt' is searched as 'bodo glimt'")

    # the NBA: a record and a seed, never 'points'
    nba = [{"group": "Eastern Conference", "position": 1, "team": "Boston Celtics", "points": None, "record": "4-0"},
           {"group": "Eastern Conference", "position": 15, "team": "New York Knicks", "points": None, "record": "0-4"},
           {"group": "Western Conference", "position": 1, "team": "Sacramento Kings", "points": None, "record": "3-1"}]
    ctx.provider.standings = lambda competition: [dict(r) for r in nba]
    spoken = REGISTRY["get_standings"](ctx, {"competition": "NBA", "team": "Knicks"}, L)[0]
    assert spoken == "In NBA, Eastern Conference, New York Knicks are 15th in the group at 0-4. Boston Celtics lead the group at 4-0.", spoken
    spoken = REGISTRY["get_standings"](ctx, {"competition": "NBA"}, L)[0]
    assert "Eastern Conference, Boston Celtics, 4-0" in spoken and "points" not in spoken, spoken
    print("ok  NBA standings are records and seeds: " + spoken[:100])

    # last night's US game is "yesterday" to a listener in Europe, though the calendar calls it today
    now = datetime.datetime(2026, 10, 15, 10, 0, tzinfo=datetime.timezone.utc)
    game = {"fixture_id": "5", "home": "Denver Nuggets", "away": "LA Clippers", "status": "FT", "minute": 48,
            "kickoff": "2026-10-15T02:00Z", "score": {"home": 110, "away": 122}, "sport": "basketball"}
    ref = finder.Reference({"team": "LA Clippers", "when": "yesterday"})
    scored = finder.score_all([game], ref, None, 0, now=now)
    assert scored and scored[0][1]["fixture_id"] == "5", scored
    earlier = dict(game, fixture_id="6", kickoff="2026-10-15T07:00Z")          # 7 am: this morning, not last night
    assert not finder.score_all([earlier], ref, None, 0, now=now), "a match at 7 am is not last night"
    print("ok  'yesterday' finds last night's 2 am-UTC game, and not this morning's")

    # line-ups and referee before they are out
    ctx = make_ctx(start_minute=0)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, L)
    ctx.provider.lineups = lambda f: {"Crystal Palace": {"formation": None, "xi": [], "bench": []}}
    assert REGISTRY["get_lineups"](ctx, {}, L)[0].startswith("The line-ups aren't out yet."), "not 'in a standard shape'"
    ctx.provider.officials = lambda f: {"referee": None}
    assert REGISTRY["get_officials"](ctx, {}, L)[0] == "The referee hasn't been named yet.", "no 'no cards so far' before kick-off"
    print("ok  before kick-off: line-ups 'aren't out yet', referee 'hasn't been named yet'")

    # basketball: the score and the scorers, never every basket read out
    bb = make_ctx()
    fx = {"fixture_id": "88", "home": "Denver Nuggets", "away": "LA Clippers", "status": "FT", "minute": 48,
          "score": {"home": 110, "away": 122}, "sport": "basketball", "kickoff": "2026-10-15T02:00Z"}
    bb.provider.fixture = lambda f: dict(fx)
    rec = bb.store.listener(L)
    rec["discussed"] = {"fixture_id": "88", "at": __import__("time").time()}
    bb.store.save_listener(rec)
    for minute, who, pts, note in [(2, "Aaron Gordon", 2, "Aaron Gordon makes 1-foot dunk (Cameron Johnson assists)"), (5, "Jamal Murray", 3, None),
                                   (9, "Aaron Gordon", 2, None), (14, "Aaron Gordon", 2, "dunk")]:
        bb.store.append_event(Event.make("88", minute, "basket", player=who, points=pts, team="x", detail=note))
    spoken = REGISTRY["get_match_report"](bb, {"fixture_id": "88"}, L)[0]
    assert spoken.endswith("Leading scorers: Aaron Gordon with 6, Jamal Murray with 3."), spoken
    assert "makes" not in spoken and "dunk" not in spoken, "no basket-by-basket reading: " + spoken
    from sideline.sports import basketball
    said = basketball.Basketball().say_event({"kind": "basket", "minute": 2, "points": 2, "player": "Aaron Gordon",
                                              "detail": "Aaron Gordon makes 1-foot dunk (Cameron Johnson assists)"})
    assert said == "Aaron Gordon scored two with 10 minutes left in the first quarter", said
    print("ok  a basketball match: the score and the leading scorers, not 120 baskets")

    # an unknown team does not cost a scan of five days
    scans = []
    q = EspnProvider()
    q._find_team = lambda want: None
    q.fixtures_on = lambda offset_days=0, sport=None: scans.append(offset_days) or []
    assert q.team_matches("Zzyzx Rovers") is None and scans == [0], scans
    print("ok  a team the search cannot find: one look at today's list, not five days")

    # words
    ctx.provider.head_to_head = lambda fid, limit=5: [{"home": "Crystal Palace", "away": "Lyon", "score": {"home": 2, "away": 0}}]
    assert REGISTRY["get_head_to_head"](ctx, {}, L)[0] == "Their last meeting: Crystal Palace 2, Lyon 0."
    ctx.provider.competitions = lambda country=None: [{"name": "Premier League", "country": "England"}, {"name": "FA Cup", "country": "England"}]
    assert REGISTRY["get_competitions"](ctx, {"country": "England"}, L)[0] == "I can cover 2 competitions in England: Premier League, FA Cup."
    ctx.provider.competitions = lambda country=None: [{"name": "L%d" % i, "country": "X"} for i in range(30)]
    e = no_team(ctx, "Zzyzx Rovers")
    assert e.spoken == "I can't find Zzyzx Rovers. Try the full name, or tell me which league they play in.", e.spoken
    print("ok  one meeting is 'their last meeting'; no repeated country; an unknown team is not met with twenty leagues")


if __name__ == "__main__":
    main()
    print("\nbroad batch fixes: all good")
