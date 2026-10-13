"""The match preview: what a friend says about the game before it starts.

Where it is played, the time in the listener's own clock, the weather there, how
each side lines up, and who is favoured. Each part is real or absent, never guessed,
and nothing technical (an id) is ever said. Time and weather are pinned here; the
data is the invented fixture in tests/fixtures.
"""

import datetime

from conftest import make_ctx

from sideline import clock, weather
from sideline.providers.base import ProviderUnavailable
from sideline.mcp.errors import ToolError
from sideline.tools import REGISTRY, find_matches

UTC = datetime.timezone.utc
KICKOFF = datetime.datetime(2026, 10, 4, 16, 30, tzinfo=UTC)          # the fixture's kickoff
SUNNY = {"sky": "clear skies", "temperature_c": 12, "wind_kmh": 21, "rain_chance": 5}


def preview(ctx, listener="ann", **args):
    return REGISTRY["get_match_preview"](ctx, args, listener)


def main():
    real_now, real_weather = clock.now, weather.at_ground
    try:
        clock.now = lambda: KICKOFF - datetime.timedelta(hours=11, minutes=16)
        weather.at_ground = lambda city, country, when: SUNNY

        ctx = make_ctx(start_minute=0)
        REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "ann")
        rec = ctx.store.listener("ann")
        rec["tz_offset_minutes"] = 240
        ctx.store.save_listener(rec)

        spoken, s, _ = preview(ctx)
        print("   ", spoken)
        assert spoken.startswith("Arsenal host Tottenham in the Premier League, round 8."), spoken
        assert "It's at Emirates Stadium, in Invented City." in spoken
        assert "Kick-off is today at 8:30 PM, in about 11 hours." in spoken, "the listener's own clock"
        assert "The forecast for the start is clear skies, 12 degrees, and a breeze of 21 kilometres an hour." in spoken
        assert "The line-ups are not out yet." not in spoken, "this fixture has line-ups"
        assert "Arsenal line up in a 4-3-3" in spoken
        assert "1208341" not in spoken and "fixture" not in spoken.lower(), "no ids, ever"
        assert s["missing"] == [] and s["weather"] == SUNNY
        print("ok  a preview names the ground, the time in the listener's zone, weather and formations")

        # With no zone from the page it says UTC, never a silent guess.
        rec = ctx.store.listener("ann"); rec["tz_offset_minutes"] = None; ctx.store.save_listener(rec)
        spoken, _, _ = preview(ctx)
        assert "Kick-off is today at 4:30 PM UTC" in spoken, spoken
        print("ok  no zone known: the time is said in UTC and says so")

        # Whatever is missing is left out, named in `missing`, and nothing is invented.
        weather.at_ground = lambda *a: None
        ctx.provider.lineups = lambda fid: {}
        spoken, s, _ = preview(ctx)
        assert "forecast" not in spoken and "line up in" not in spoken, spoken
        assert "The line-ups are not out yet." in spoken
        assert set(s["missing"]) == {"weather", "formations"}, s["missing"]
        print("ok  weather and formations missing: left out, listed, never guessed")

        def down(fid):
            raise ProviderUnavailable("quota")
        ctx.provider.lineups = down
        spoken, s, _ = preview(ctx)
        assert "formations" in s["missing"] and spoken, "a feed failure on one part does not sink the preview"
        print("ok  a feed failure on the line-ups does not sink the rest of the preview")

        # Under way: the live state replaces the kick-off line, and no id is spoken.
        live = make_ctx(start_minute=40)
        REGISTRY["follow_match"](live, {"team": "Arsenal"}, "bob")
        spoken, _, _ = preview(live, "bob")
        assert "Kick-off" not in spoken and "40 minutes in" in spoken, spoken
        print("ok  a match under way is described live")

        # follow_match itself is short and carries no id either.
        spoken, _, _ = REGISTRY["follow_match"](make_ctx(start_minute=0), {"team": "Arsenal"}, "cy")
        assert "1208341" not in spoken and "fixture" not in spoken.lower(), spoken
        print("ok  following a match never says an id")

        # "What time is Arsenal playing against Lille?" names a match, it does not follow one.
        weather.at_ground = lambda *a: None
        ask = make_ctx(start_minute=0)
        spoken, s, _ = REGISTRY["get_match_preview"](ask, {"team": "Arsenal", "opponent": "Tottenham"}, "dee")
        assert "Kick-off is today at" in spoken and s["home"] == "Arsenal", spoken
        assert ask.store.listener("dee").get("following") in (None, ""), "asking is not following"
        spoken, s, _ = REGISTRY["get_match_preview"](ask, {"team": "Asenal"}, "dee")
        assert s["home"] == "Arsenal", "a name that came through a little off still finds the team"
        for args in ({"team": "Lille"}, {"team": "Zzyzx", "opponent": "Qqq"}):
            try:
                REGISTRY["get_match_preview"](ask, args, "dee")
            except ToolError as e:
                assert "yesterday, today or tomorrow" in e.spoken and e.detail["reason"] == "no_match", e.spoken
                assert "typo" not in e.spoken and "fixture" not in e.spoken.lower(), e.spoken
            else:
                raise AssertionError("a match the feed cannot show must be said plainly: %r" % (args,))
        try:
            REGISTRY["get_match_preview"](ask, {"team": "Arsenal", "opponent": "Lille"}, "dee")
        except ToolError as e:
            assert e.spoken == "I can't find Arsenal against Lille, but I can see Arsenal against Tottenham, today at 4:30 PM UTC.", e.spoken
        else:
            raise AssertionError("the team is on but not against that opponent: say what is on")
        # What the recogniser made of "Arsenal" ("asana") is offered back, never refused or guessed.
        try:
            REGISTRY["get_match_preview"](ask, {"team": "asana"}, "dee")
        except ToolError as e:
            assert e.spoken == "I couldn't find asana. Did you mean Arsenal against Tottenham, today at 4:30 PM UTC?", e.spoken
            assert e.detail["reason"] == "ambiguous" and e.detail["candidates"][0]["home"] == "Arsenal"
        else:
            raise AssertionError("a mis-heard team must become an offer")
        print("ok  a named match is previewed without following it; a near spelling finds it; "
              "an unseen match is 'not yesterday, today or tomorrow', never a typo")

        # Tomorrow is searched when today has nothing, and the first day with a match wins.
        tomorrow = dict(ask.provider.fixture(1208341), home="Arsenal", away="Lille", fixture_id=555, minute=0,
                        status="NS", kickoff="2026-10-05T19:00:00+00:00")
        ask.provider.fixtures_on = lambda off: [tomorrow] if off == 1 else (
            [f for f in ask.provider.fixtures_today()] if off == 0 else [])
        got = find_matches(ask, "Arsenal", "Lille")
        assert [f["fixture_id"] for f in got] == [555], got
        assert [f["fixture_id"] for f in find_matches(ask, "Arsenal")] == [1208341], "today before tomorrow"
        youth = dict(tomorrow, home="Arsenal U19", away="Lille U19", fixture_id=556)
        both = [youth, tomorrow]
        ask.provider.fixtures_on = lambda off: both if off == 0 else []
        assert [f["fixture_id"] for f in find_matches(ask, "Arsenal", "Lille")] == [555], "the exact name beats Arsenal U19"
        assert [f["fixture_id"] for f in find_matches(ask, "Lille")] == [555]
        print("ok  today is searched first, then tomorrow, then yesterday; an exact name beats a longer one")

        # The weather service: placed by country, or left out; words a listener would use.
        weather.at_ground = real_weather
        assert weather.say(SUNNY) == "clear skies, 12 degrees, and a breeze of 21 kilometres an hour"
        assert weather.say({"sky": "rain", "temperature_c": 8, "wind_kmh": 5, "rain_chance": 80}) == "rain and 8 degrees"
        assert weather.say({"sky": "overcast", "temperature_c": 9, "wind_kmh": 5, "rain_chance": 60}) == \
            "overcast, 9 degrees, and a 60 percent chance of rain"
        assert weather.say(None) == ""
        calls = []

        def fake_get(url, **params):
            calls.append(url)
            if url == weather.GEOCODE:
                return {"results": [{"name": "Hartlepool", "country": "United States", "admin1": "Pennsylvania",
                                     "latitude": 1.0, "longitude": 2.0},
                                    {"name": "Hartlepool", "country": "United Kingdom", "admin1": "England",
                                     "latitude": 54.7, "longitude": -1.2}]}
            return {"hourly": {"weather_code": [0], "temperature_2m": [12.2], "wind_speed_10m": [21.2],
                               "precipitation_probability": [0]}}
        real_get = weather._get
        weather._get = fake_get
        weather._cache.clear()
        try:
            weather.os.environ["SIDELINE_WEATHER"] = "on"
            # A UEFA competition names no country: only an unmistakable city is placed.
            def world_get(url, **params):
                if url == weather.GEOCODE:
                    big = {"name": params["name"], "country": "United Kingdom", "admin1": "England",
                           "latitude": 51.5, "longitude": -0.1, "population": 8900000}
                    small = {"name": params["name"], "country": "Canada", "admin1": "Ontario",
                             "latitude": 43.0, "longitude": -81.2, "population": 400000}
                    same = dict(small, population=7000000)
                    return {"results": [big, same] if params["name"] == "Tie" else [big, small]}
                return fake_get(url, **params)
            weather._get = world_get
            weather._cache.clear()
            assert weather.at_ground("London", "World", KICKOFF) is not None, "London UK, not Ontario"
            assert weather.at_ground("Tie", "World", KICKOFF) is None, "two similar places: not guessed"
            weather._get = fake_get
            weather._cache.clear()
            del calls[:]
            os_env = weather.os.environ
            os_env["SIDELINE_WEATHER"] = "on"
            got = weather.at_ground("Hartlepool", "England", KICKOFF)
            assert got == {"sky": "clear skies", "temperature_c": 12, "wind_kmh": 21, "rain_chance": 0}, got
            assert weather.at_ground("Hartlepool", "England", KICKOFF) == got and len(calls) == 2, "cached"
            assert weather.at_ground("Hartlepool", "Scotland", KICKOFF) is None, "wrong country: not placed, not guessed"
            assert weather.at_ground("Hartlepool", None, KICKOFF) is None and weather.at_ground(None, "England", KICKOFF) is None
            os_env["SIDELINE_WEATHER"] = "off"
            weather._cache.clear()
            assert weather.at_ground("Hartlepool", "England", KICKOFF) is None, "switched off"
        finally:
            weather._get = real_get
            weather.os.environ["SIDELINE_WEATHER"] = "off"
        print("ok  weather: placed only when the country matches, cached, and off means off")
    finally:
        clock.now, weather.at_ground = real_now, real_weather
    print("\npreview: all good")


if __name__ == "__main__":
    main()
