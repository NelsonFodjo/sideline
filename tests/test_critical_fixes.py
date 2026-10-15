"""Regression tests for the three critical bugs in docs/BUGS.md: ST-01, TL-01, ESPN-01."""

import time

from conftest import age_events, make_ctx

from sideline.mcp.errors import ToolError
from sideline import clock
from sideline.poller import poll_once
from sideline.state.store import Event, backdate
from sideline.providers import espn
from sideline.tools import REGISTRY, events_for, resolve_fixture

L = "listener-1"


def main():
    # ST-01: a delay under a minute still holds back the current minute
    assert clock.delay_minutes(0) == 0 and clock.delay_minutes(None) == 0
    assert clock.delay_minutes(1) == 1 and clock.delay_minutes(45) == 1
    assert clock.delay_minutes(60) == 1 and clock.delay_minutes(61) == 2 and clock.delay_minutes(119) == 2
    print("ok  delay rounds up to whole minutes")

    ctx = make_ctx(start_minute=0)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, L)
    ctx.provider.jump_to(58)
    poll_once(ctx)
    rec = ctx.store.listener(L)
    assert rec.get("broadcast_offset"), "following sets a default delay, never zero"
    fid = rec["following"]
    assert any(e["minute"] == 58 for e in ctx.store.events(fid)), "the 58' goal is in the log"

    gap, _, _ = ctx.store.gap_for(L, fid)
    assert all(e["minute"] <= 57 for e in gap), [e["minute"] for e in gap]
    print("ok  catch-up holds back the minute the listener's picture has not reached")

    # TL-01: tools that read events see the listener's minute, not the feed's
    fx = resolve_fixture(ctx, {}, L)
    assert fx["minute"] == 57 and fx["real_minute"] == 58, (fx["minute"], fx.get("real_minute"))
    assert all(e["minute"] <= 57 for e in events_for(ctx, fx))
    spoken, _, _ = REGISTRY["get_match_report"](ctx, {}, L)
    assert "58" not in spoken, spoken
    print("ok  events_for and the match report do not spoil the 58' goal")

    rec["broadcast_offset"] = 0
    ctx.store.save_listener(rec)
    fx0 = resolve_fixture(ctx, {}, L)
    assert any(e["minute"] == 58 for e in events_for(ctx, fx0)), "no delay, no hiding"
    print("ok  with no delay nothing is hidden")

    # The guard runs on the clock, not on whole minutes: it lifts the moment the delay has passed
    ctx = make_ctx(start_minute=0)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, L)
    ctx.provider.jump_to(58)
    poll_once(ctx)
    fid = ctx.store.listener(L)["following"]
    goal = next(e for e in ctx.store.events(fid) if e["minute"] == 58)
    offset = ctx.store.listener(L)["broadcast_offset"]
    goal["at"] = time.time() - (offset - 5)                       # seen 40 s ago: 5 s still to go
    assert goal["id"] not in [e["id"] for e in ctx.store.gap_for(L, fid)[0]], "held back until the delay has passed"
    goal["at"] = time.time() - (offset + 1)                       # now it has
    assert goal["id"] in [e["id"] for e in ctx.store.gap_for(L, fid)[0]], "shown as soon as the delay has passed"
    fx = resolve_fixture(ctx, {}, L)
    assert any(e["minute"] == 58 for e in events_for(ctx, fx))
    print("ok  the guard lifts when the delay has passed, not a minute later")

    # the score is what the screen has shown, never the feed's number while events are held
    ctx = make_ctx(start_minute=0)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, L)
    ctx.provider.jump_to(58)
    poll_once(ctx)
    age_events(ctx)
    fid = ctx.store.listener(L)["following"]
    shown_all = resolve_fixture(ctx, {}, L)["score"]
    for e in ctx.store.events(fid):
        e["at"] = time.time()                                     # everything seen a moment ago: nothing on screen yet
        e.pop("happened_by", None)
    assert resolve_fixture(ctx, {}, L)["score"] == {"home": 0, "away": 0}, "no events on screen means 0-0, not the feed"
    assert shown_all != {"home": 0, "away": 0}, "the aged log does show goals"
    print("ok  score comes from what has reached the screen")

    # events read late (followed at 60', or a restart) are not all held back for the whole delay
    old = Event.make(fid, 10, "goal", player="X", team="Arsenal")
    backdate(old, 60)
    assert time.time() - old["happened_by"] > 45 * 60, "a minute 10 event read at 60' happened long ago"
    fresh = backdate(Event.make(fid, 59, "goal", player="Y", team="Arsenal"), 60)
    assert "happened_by" not in fresh, "an event from the minute just played may have happened a moment ago"
    print("ok  late-read events are back-dated, fresh ones are not")

    # the marker never moves past an event still to reach the screen
    ctx = make_ctx(start_minute=0)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, L)
    ctx.provider.jump_to(58)
    poll_once(ctx)
    age_events(ctx)
    fid = ctx.store.listener(L)["following"]
    late = Event.make(fid, 55, "card", player="Z", team="Arsenal")       # logged just now, minute 55
    ctx.store.append_event(late)
    events, frm, to = ctx.store.gap_for(L, fid)
    assert late["id"] not in [e["id"] for e in events] and to < 55, (to, [e["minute"] for e in events])
    print("ok  the told marker stops short of an event still to reach their screen")

    # tools that read the feed's LIVE totals do not run ahead of a delayed picture
    live = make_ctx(start_minute=0)
    REGISTRY["follow_match"](live, {"team": "Arsenal"}, L)
    live.provider.jump_to(60)
    for nm, args in (("get_standouts", {}),):
        try:
            REGISTRY[nm](live, args, L)
            raise AssertionError(nm + " must not give live totals to a delayed listener")
        except ToolError as e:
            assert e.detail["reason"] == "spoiler_guard", e.detail
    spoken = REGISTRY["get_match_stats"](live, {}, L)[0]
    assert spoken.startswith("These are live numbers, a moment ahead of your picture."), spoken
    print("ok  live totals (standouts, match numbers) do not run ahead of a delayed listener")

    # ESPN-01: NFL summary URLs use ESPN's own sport name
    assert espn._espn_sport("american_football") == "football"
    assert espn._espn_sport("football") == "soccer"
    assert espn._espn_sport("basketball") == "basketball" and espn._espn_sport("hockey") == "hockey"
    p = espn.EspnProvider()
    seen = []
    p._fetch_json = lambda url, **kw: seen.append(url) or {}
    raw = {"id": "401", "competitions": [{"competitors": [
        {"homeAway": "home", "team": {"displayName": "A", "id": "1"}, "score": "0"},
        {"homeAway": "away", "team": {"displayName": "B", "id": "2"}, "score": "0"}]}],
        "date": "2026-10-15T00:00Z", "status": {"type": {"name": "STATUS_IN_PROGRESS", "state": "in"}}}
    p._norm_fixture(raw, "american_football", "nfl")
    assert p._event_meta["401"][0] == "football"
    p._fetch_summary(*p._event_meta["401"][0:1], "nfl", "401")
    assert "/sports/football/nfl/summary" in seen[-1], seen[-1]
    print("ok  NFL summary requests go to /sports/football/nfl/")


if __name__ == "__main__":
    main()
    print("\ncritical fixes: all good")
