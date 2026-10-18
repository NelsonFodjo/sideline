"""What is on: every match read out with its time.

For a list the time is the point, so no fixture is ever named without one: in the list itself, in
"which one did you mean?", and in "did you mean?". Time is pinned and the data is invented.
"""

import datetime

from conftest import make_ctx

from sideline import clock
from sideline.mcp.errors import ToolError
from sideline.tools import REGISTRY, find_matches

UTC = datetime.timezone.utc
NOW = datetime.datetime(2026, 10, 4, 6, 0, tzinfo=UTC)


def fx(i, home, away, hour, comp="Some League", league_id=999, minute=0, status="NS", day=4):
    return {"fixture_id": i, "home": home, "away": away, "minute": minute, "status": status,
            "competition": comp, "country": "Inventland", "league_id": league_id,
            "kickoff": datetime.datetime(2026, 10, day, hour, 0, tzinfo=UTC).isoformat()}


def main():
    real_now = clock.now
    try:
        clock.now = lambda: NOW
        ctx = make_ctx(start_minute=0)
        rec = ctx.store.listener("ann")
        rec["tz_offset_minutes"] = 240
        ctx.store.save_listener(rec)

        # say_fixture: the time is always there
        assert clock.say_fixture(fx(1, "A", "B", 19), 240) == "A against B, today at 11 PM"
        assert clock.say_fixture(fx(1, "A", "B", 19), 240, with_day=False) == "A against B at 11 PM"
        assert clock.say_fixture(fx(1, "A", "B", 19, day=5), 240) == "A against B, tomorrow at 11 PM"
        assert clock.say_fixture(fx(1, "A", "B", 19), None) == "A against B, today at 7 PM UTC", "no zone: UTC, said so"
        assert clock.say_fixture(fx(1, "A", "B", 8, minute=34, status="1H"), 240) == "A against B, live, 34 minutes in"
        assert clock.say_fixture(fx(1, "A", "B", 8, status="FT"), 240) == "A against B, finished"
        assert clock.say_fixture(fx(1, "A", "B", 6), 240) == "A against B, starting now"
        assert clock.say_fixture(fx(1, "A", "B", 5), 240) == "A against B, was due to start at 9 AM"
        print("ok  a match is never named without its time: today, tomorrow, live, finished, starting, UTC when unknown")

        day = [fx(1, "Lowly", "Minor", 10), fx(2, "Arsenal", "Lille", 19, "UEFA Champions League", 2),
               fx(3, "Live Home", "Live Away", 5, minute=61, status="2H"),
               fx(4, "Spurs", "Chelsea", 13, "Premier League", 39), fx(5, "Late", "Night", 23),
               fx(6, "Early", "Bird", 7), fx(7, "Extra", "Time", 21)]
        ctx.provider.fixtures_on = lambda off: day if off == 0 else [fx(8, "Next", "Day", 15, day=5)] if off == 1 else []

        spoken, s, _ = REGISTRY["get_fixtures"](ctx, {}, "ann")
        print("   ", spoken)
        assert spoken.startswith("Today: Some League: Live Home against Live Away, live, 61 minutes in. "
                                 "Early against Bird at 11 AM. Lowly against Minor at 2 PM. "
                                 "Premier League: Spurs against Chelsea at 5 PM. "
                                 "UEFA Champions League: Arsenal against Lille at 11 PM."), spoken
        assert "more" not in spoken and s["total"] == 5 and len(s["matches"]) == 5
        print("ok  live first, then soonest first, each with its time")

        # The listener's day is not the UTC day: at +4, 21:00 and 23:00 UTC are 1 AM and 3 AM tomorrow.
        assert "Late" not in spoken and "Extra" not in spoken, "after local midnight is tomorrow"
        spoken, s, _ = REGISTRY["get_fixtures"](ctx, {"when": "tomorrow"}, "ann")
        assert "Extra against Time at 1 AM" in spoken and "Late against Night at 3 AM" in spoken, spoken
        print("ok  'today' is the listener's day, not the UTC date: a 1 AM kick-off is tomorrow's")

        spoken, _, _ = REGISTRY["get_fixtures"](ctx, {"competition": "premier league"}, "ann")
        assert spoken == "Today in the premier league: Spurs against Chelsea at 5 PM.", spoken
        spoken, _, _ = REGISTRY["get_fixtures"](ctx, {"live_only": True}, "ann")
        assert spoken == "Live now: Live Home against Live Away, live, 61 minutes in.", spoken
        spoken, _, _ = REGISTRY["get_fixtures"](ctx, {"when": "tomorrow"}, "ann")
        assert spoken == "Tomorrow: Extra against Time at 1 AM. Late against Night at 3 AM. Next against Day at 7 PM.", spoken
        for args, said in (({"competition": "La Liga"}, "I can't see any matches in La Liga today."),
                           ({"when": "yesterday"}, "I can't see any matches yesterday.")):
            try:
                REGISTRY["get_fixtures"](ctx, args, "ann")
            except ToolError as e:
                assert e.spoken == said and e.detail["reason"] == "no_match", e.spoken
            else:
                raise AssertionError("an empty list must be said plainly")
        print("ok  by competition, live only, tomorrow; an empty day is said plainly")

        # A quiet day looks ahead: "the next matches" never ends in "nothing tomorrow".
        later = [fx(20, "Far", "Away", 15, day=7)]
        ctx.provider.fixtures_on = lambda off: later if off == 3 else []
        spoken, s, _ = REGISTRY["get_fixtures"](ctx, {"when": "tomorrow"}, "ann")
        assert spoken == "Nothing tomorrow. The next matches are on Wednesday: Far against Away at 7 PM.", spoken
        assert s["skipped"] == "tomorrow", s
        spoken, s, _ = REGISTRY["get_fixtures"](ctx, {"date": "2026-10-07"}, "ann")
        assert spoken == "On Wednesday: Far against Away at 7 PM.", spoken
        spoken, _, _ = REGISTRY["get_fixtures"](ctx, {"date": "2026-10-05"}, "ann")
        assert spoken.startswith("Nothing tomorrow. The next matches are on Wednesday"), "a quiet named day looks ahead too: " + spoken
        try:
            REGISTRY["get_fixtures"](ctx, {"when": "yesterday"}, "ann")
            raise AssertionError("yesterday does not look ahead")
        except ToolError as e:
            assert e.spoken == "I can't see any matches yesterday.", e.spoken
        ctx.provider.fixtures_on = lambda off: []
        try:
            REGISTRY["get_fixtures"](ctx, {"when": "tomorrow"}, "ann")
            raise AssertionError("nothing in ten days is said plainly")
        except ToolError as e:
            assert e.spoken == "I can't see any matches tomorrow.", e.spoken
        from sideline.tools import possessive
        assert [possessive(n) for n in ("Celtic", "Rangers", "St. Mirren", "Hearts")] == ["Celtic's", "Rangers'", "St. Mirren's", "Hearts'"]
        from sideline.tools.get_fixtures import _matches
        assert _matches({"competition": "Premiership", "country": "Scotland"}, "Scottish Premiership")
        assert _matches({"competition": "Superliga", "country": "Denmark"}, "the Danish Superliga")
        assert not _matches({"competition": "Superliga Play-offs", "country": "Denmark"}, "Danish Superliga")
        assert not _matches({"competition": "Premier League", "country": "England"}, "Scottish Premiership")
        assert not _matches({"competition": "CAF Champions League"}, "Champions League")
        assert _matches({"competition": "CAF Champions League"}, "CAF Champions League")
        assert _matches({"competition": "UEFA Champions League"}, "Champions League")
        print("ok  a quiet day names the next day with matches; names ending in s take the apostrophe alone")

        # A named zone is said once at the top of a list, and after a single match.
        rec = ctx.store.listener("ann"); rec["tz_name"] = "Indian/Mauritius"; ctx.store.save_listener(rec)
        ctx.provider.fixtures_on = lambda off: day if off == 0 else []
        spoken, _, _ = REGISTRY["get_fixtures"](ctx, {"competition": "premier league"}, "ann")
        assert spoken == "Today in the premier league, in Mauritius time: Spurs against Chelsea at 5 PM.", spoken
        two0 = [fx(10, "Arsenal", "Lille", 19)]
        ctx.provider.fixtures_on = lambda off: two0 if off == 0 else []
        try:
            REGISTRY["get_match_preview"](ctx, {"team": "Arsenal", "opponent": "Everton"}, "ann")
        except ToolError as e:
            assert e.spoken.endswith("Arsenal against Lille, today at 11 PM Mauritius time."), e.spoken
        print("ok  the zone is named the way people name it: once at the top of a list, after a single match's time")
        rec = ctx.store.listener("ann"); rec["tz_name"] = None; ctx.store.save_listener(rec)

        # Offers and "which one" carry the time too.
        two = [fx(10, "Arsenal", "Lille", 19), fx(11, "Arsenal U19", "Lille U19", 11)]
        ctx.provider.fixtures_on = lambda off: two if off == 0 else []
        try:
            REGISTRY["get_match_preview"](ctx, {"team": "asana"}, "ann")
        except ToolError as e:
            assert e.spoken == "I couldn't find asana. Did you mean Arsenal against Lille, today at 11 PM?", e.spoken
        try:
            REGISTRY["get_match_preview"](ctx, {"team": "Arsenal", "opponent": "Everton"}, "ann")
        except ToolError as e:
            assert e.spoken.startswith("I can't find Arsenal against Everton, but I can see Arsenal against Lille, today at 11 PM"), e.spoken
        twice = [fx(10, "Arsenal", "Lille", 19), fx(12, "Arsenal", "Everton", 15)]
        ctx.provider.fixtures_on = lambda off: twice if off == 0 else []
        try:
            REGISTRY["get_match_preview"](ctx, {"team": "Arsenal"}, "ann")
        except ToolError as e:
            assert e.spoken == ("I can see more than one Arsenal match. Which one: 1, Arsenal against Everton, today at 7 PM, "
                                "or 2, Arsenal against Lille, today at 11 PM?"), e.spoken
        print("ok  'did you mean', 'but I can see' and 'which one' carry each match's time")

        # Names as people say them: nicknames, and accents that a voice never says.
        mixed = [fx(20, "Tottenham Hotspur", "Chelsea", 19), fx(21, "Sønderjyske Fodbold", "FC København", 15)]
        ctx.provider.fixtures_on = lambda off: mixed if off == 0 else []
        assert [f["fixture_id"] for f in find_matches(ctx, "Spurs")] == [20], "a nickname"
        assert [f["fixture_id"] for f in find_matches(ctx, "Sonderjyske")] == [21], "no ø spoken"
        assert [f["fixture_id"] for f in find_matches(ctx, "Copenhagen")] == [21], "the English name"
        assert [f["fixture_id"] for f in find_matches(ctx, "Spurs", "Chelsea")] == [20]
        print("ok  nicknames and unaccented spellings find the team")
    finally:
        clock.now = real_now
    print("\nfixtures: all good")


if __name__ == "__main__":
    main()
