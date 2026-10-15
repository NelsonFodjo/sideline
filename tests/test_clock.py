"""The current time, and when a fixture starts.

A listener who asks about a match that has not started should hear when it does,
not just "not started yet". These pin the helper and the places that use it. Time
is pinned by replacing clock.now, so nothing here depends on the real clock.
"""

import datetime

from conftest import make_ctx

from sideline import clock, sports
from sideline.tools import REGISTRY

UTC = datetime.timezone.utc
KICKOFF = datetime.datetime(2026, 10, 13, 7, 45, tzinfo=UTC)
FX = {"home": "Newcastle Jets", "away": "Gamba Osaka", "kickoff": "2026-10-13T07:45:00+00:00"}


def at(delta):
    """Pin 'now' to a point relative to kickoff."""
    clock.now = lambda: KICKOFF + delta


def main():
    real_now = clock.now
    try:
        # ------------------------------------------------------ the helper
        assert abs((clock.now() - datetime.datetime.now(UTC)).total_seconds()) < 5
        assert clock.now().tzinfo is not None, "now() is timezone-aware"
        print("ok  now() is the current moment, timezone-aware")
    finally:
        pass

    try:
        assert clock.parse("2026-10-13T07:45:00+00:00") == KICKOFF
        assert clock.parse("2026-10-13T07:45:00Z") == KICKOFF, "a trailing Z (Python 3.8 cannot read it natively)"
        assert clock.parse("2026-10-13T10:45:00+03:00") == KICKOFF, "any offset is normalised"
        assert clock.parse("2026-10-13T07:45:00") == KICKOFF, "no zone is taken as UTC"
        for bad in (None, "", "soon", "13/10/2026", 12345):
            assert clock.parse(bad) is None, bad
        assert clock.kickoff({"kickoff": None}) is None and clock.kickoff(None) is None
        print("ok  parse(): Z, offsets and naive times; garbage and missing are None, never an error")

        sec = datetime.timedelta
        for delta, said in ((sec(seconds=20), "less than a minute"), (sec(seconds=89), "1 minute"),
                            (sec(minutes=45), "45 minutes"), (sec(hours=1), "1 hour"),
                            (sec(hours=2, minutes=15), "2 hours 15 minutes"),
                            (sec(hours=26, minutes=12), "1 day 2 hours"),
                            (sec(days=3), "3 days"), (-sec(minutes=10), "10 minutes")):
            assert clock.say_duration(delta) == said, (delta, clock.say_duration(delta), said)
        print("ok  durations are said as people say them, and rounded to the hour past a day")

        # ------------------------------------------------ the kickoff sentence
        local = "7:45 AM UTC"          # no zone known: UTC, and it says so
        at(-datetime.timedelta(hours=2, minutes=15))
        assert clock.until_kickoff(FX) == datetime.timedelta(hours=2, minutes=15)
        assert clock.say_kickoff(FX) == "Kick-off is today at %s, in about 2 hours." % local
        assert clock.say_kickoff(FX, "tip-off") == "Tip-off is today at %s, in about 2 hours." % local
        # the listener's own clock, when the page told us its offset (Mauritius, +04:00)
        assert clock.say_kickoff(FX, tz_minutes=240) == "Kick-off is today at 11:45 AM, in about 2 hours."
        assert clock.say_kickoff(FX, tz_minutes=-300) == "Kick-off is today at 2:45 AM, in about 2 hours."
        far = {"kickoff": "2026-10-14T18:00:00+00:00"}
        assert clock.say_kickoff(far, at=KICKOFF, tz_minutes=240) == \
            "Kick-off is tomorrow at 10 PM, in about 34 hours."
        assert clock.say_kickoff({"kickoff": "2026-10-13T18:00:00+00:00"}, at=KICKOFF.replace(hour=6, minute=44),
                                 tz_minutes=240) == "Kick-off is today at 10 PM, in about 11 hours."
        assert clock.say_time_of_day(KICKOFF.replace(hour=0, minute=0), 0) == "12 AM"
        assert clock.say_time_of_day(KICKOFF.replace(hour=12, minute=5), 0) == "12:05 PM"
        assert clock.say_time_of_day(KICKOFF) == "7:45 AM UTC", "no known zone: UTC, said so"
        # The zone is named the way people name it.
        for name, said in (("Indian/Mauritius", "Mauritius time"), ("Asia/Kolkata", "India time"),
                           ("America/New_York", "US Eastern time"), ("America/Los_Angeles", "US Pacific time"),
                           ("America/Indiana/Indianapolis", "US Eastern time"), ("Europe/London", "UK time"),
                           ("Africa/Lagos", "Lagos time"), ("America/Argentina/Buenos_Aires", "Buenos Aires time"),
                           ("Etc/UTC", "UTC")):
            assert clock.zone_label(name) == said, (name, clock.zone_label(name))
        assert clock.zone_label(None) == "" and clock.zone_label("") == ""
        mu = clock.Zone(240, "Indian/Mauritius")
        assert mu == 240 and int(mu) == 240, "a Zone is an int too"
        assert clock.say_time_of_day(KICKOFF, mu) == "11:45 AM Mauritius time"
        assert clock.say_time_of_day(KICKOFF, mu, with_zone=False) == "11:45 AM"
        assert clock.say_time_of_day(KICKOFF, clock.Zone(-240, "America/New_York")) == "3:45 AM US Eastern time"
        assert clock.say_time_of_day(KICKOFF, clock.Zone(240)) == "11:45 AM", "an offset with no name: no label"
        assert clock.zone_phrase(mu) == "Mauritius time" and clock.zone_phrase(None) == "UTC" and clock.zone_phrase(clock.Zone(240)) == ""
        assert clock.zone_from({"tz_offset_minutes": 330, "tz_name": "Asia/Kolkata"}).name == "Asia/Kolkata"
        assert clock.zone_from({}) is None
        at(-datetime.timedelta(hours=2, minutes=15))
        assert clock.say_kickoff(FX, tz_minutes=mu) == "Kick-off is today at 11:45 AM Mauritius time, in about 2 hours."
        assert clock.say_zone(330) == "UTC plus 5:30" and clock.say_zone(-570) == "UTC minus 9:30" and clock.say_zone(None) == "UTC"
        assert clock.say_roughly(datetime.timedelta(minutes=89)) == "89 minutes"
        assert clock.say_roughly(datetime.timedelta(days=3)) == "about 3 days"
        at(datetime.timedelta(seconds=5))
        assert clock.say_kickoff(FX) == "Kick-off is about to happen."
        at(datetime.timedelta(minutes=10))
        assert clock.say_kickoff(FX) == "Kick-off was due 10 minutes ago."
        assert clock.until_kickoff(FX) < datetime.timedelta(0)
        assert clock.say_kickoff({"home": "A", "away": "B"}) == ""
        assert clock.say_kickoff({"kickoff": "nonsense"}) == ""
        print("ok  'Kick-off is today at 10 PM, in about 11 hours.' in the listener's own zone, no label; UTC, said so, when unknown, UTC when unknown; past and unknown forms")

        at(-datetime.timedelta(minutes=135))
        snap = clock.snapshot(FX)
        assert snap["minutes_to_kickoff"] == 135 and snap["kickoff"] == KICKOFF.isoformat()
        assert snap["now"] == (KICKOFF - datetime.timedelta(minutes=135)).isoformat()
        assert clock.snapshot({})["minutes_to_kickoff"] is None
        print("ok  snapshot(): the time now, the kickoff, and minutes between, for tool results")

        # ----------------------------- where a listener hears it: the tools
        fb = sports.get("football")
        assert fb.not_started(FX) == ("Newcastle Jets against Gamba Osaka, not started yet. "
                                      "Kick-off is today at %s, in about 2 hours." % local)
        no_time = {"home": "A", "away": "B"}
        assert fb.not_started(no_time) == "A against B, not started yet.", "no kickoff: no stray space"
        bb = sports.get("basketball")
        assert bb.not_started(dict(FX, home="Hawks", away="Rockets")).startswith(
            "Hawks against Rockets, waiting for tip-off. Tip-off is today at")
        print("ok  the football and basketball 'not started' lines carry the start time")

        ctx = make_ctx(start_minute=0)
        provider_fixture = ctx.provider.fixture
        ctx.provider.fixture = lambda fid: dict(provider_fixture(fid), kickoff=FX["kickoff"], minute=0,
                                                status="NS", score={"home": 0, "away": 0})
        spoken, structured, _ = REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "ann")
        assert "Not started yet. Kick-off is today at 7:45 AM UTC, in about 2 hours" in spoken, spoken
        spoken, structured, _ = REGISTRY["get_match_state"](ctx, {}, "ann")
        assert "Kick-off is today at 7:45 AM UTC, in about 2 hours" in spoken, spoken
        assert structured["clock"]["minutes_to_kickoff"] == 135, structured["clock"]
        print("ok  follow_match and get_match_state tell a listener when it starts:", spoken[:80])

        # once it is under way the clock plays no part in the answer
        ctx2 = make_ctx(start_minute=40)
        REGISTRY["follow_match"](ctx2, {"team": "Arsenal"}, "bob")
        spoken, structured, _ = REGISTRY["get_match_state"](ctx2, {}, "bob")
        # a follower has the default 45 s delay, so their picture is a minute behind the feed's 40'
        assert "Kick-off" not in spoken and "39 minutes in" in spoken, spoken
        print("ok  a match under way is answered as before")
    finally:
        clock.now = real_now
    print("\nclock: all good")


if __name__ == "__main__":
    main()
