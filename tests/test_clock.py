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
        local = KICKOFF.astimezone().strftime("%H:%M")
        at(-datetime.timedelta(hours=2, minutes=15))
        assert clock.until_kickoff(FX) == datetime.timedelta(hours=2, minutes=15)
        assert clock.say_kickoff(FX) == "Kick-off is in 2 hours 15 minutes, at %s." % local
        assert clock.say_kickoff(FX, "tip-off") == "Tip-off is in 2 hours 15 minutes, at %s." % local
        at(datetime.timedelta(seconds=5))
        assert clock.say_kickoff(FX) == "Kick-off is about to happen."
        at(datetime.timedelta(minutes=10))
        assert clock.say_kickoff(FX) == "Kick-off was due 10 minutes ago."
        assert clock.until_kickoff(FX) < datetime.timedelta(0)
        assert clock.say_kickoff({"home": "A", "away": "B"}) == ""
        assert clock.say_kickoff({"kickoff": "nonsense"}) == ""
        print("ok  'Kick-off is in 2 hours 15 minutes, at %s.' and its past and unknown forms" % local)

        at(-datetime.timedelta(minutes=135))
        snap = clock.snapshot(FX)
        assert snap["minutes_to_kickoff"] == 135 and snap["kickoff"] == KICKOFF.isoformat()
        assert snap["now"] == (KICKOFF - datetime.timedelta(minutes=135)).isoformat()
        assert clock.snapshot({})["minutes_to_kickoff"] is None
        print("ok  snapshot(): the time now, the kickoff, and minutes between, for tool results")

        # ----------------------------- where a listener hears it: the tools
        fb = sports.get("football")
        assert fb.not_started(FX) == ("Newcastle Jets against Gamba Osaka, not started yet. "
                                      "Kick-off is in 2 hours 15 minutes, at %s." % local)
        no_time = {"home": "A", "away": "B"}
        assert fb.not_started(no_time) == "A against B, not started yet.", "no kickoff: no stray space"
        bb = sports.get("basketball")
        assert bb.not_started(dict(FX, home="Hawks", away="Rockets")).startswith(
            "Hawks against Rockets, waiting for tip-off. Tip-off is in 2 hours 15 minutes")
        print("ok  the football and basketball 'not started' lines carry the start time")

        ctx = make_ctx(start_minute=0)
        provider_fixture = ctx.provider.fixture
        ctx.provider.fixture = lambda fid: dict(provider_fixture(fid), kickoff=FX["kickoff"], minute=0,
                                                status="NS", score={"home": 0, "away": 0})
        spoken, structured, _ = REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "ann")
        assert "Not started yet. Kick-off is in 2 hours 15 minutes" in spoken, spoken
        spoken, structured, _ = REGISTRY["get_match_state"](ctx, {}, "ann")
        assert "Kick-off is in 2 hours 15 minutes" in spoken, spoken
        assert structured["clock"]["minutes_to_kickoff"] == 135, structured["clock"]
        print("ok  follow_match and get_match_state tell a listener when it starts:", spoken[:80])

        # once it is under way the clock plays no part in the answer
        ctx2 = make_ctx(start_minute=40)
        REGISTRY["follow_match"](ctx2, {"team": "Arsenal"}, "bob")
        spoken, structured, _ = REGISTRY["get_match_state"](ctx2, {}, "bob")
        assert "Kick-off" not in spoken and "40 minutes in" in spoken, spoken
        print("ok  a match under way is answered as before")
    finally:
        clock.now = real_now
    print("\nclock: all good")


if __name__ == "__main__":
    main()
