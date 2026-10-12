"""The spoiler guard.

A companion that tells a blind listener about a goal their television
has not shown yet is worse than no companion.

This feature must not ask the listener to read the clock on their screen.
They cannot see it - that is the whole premise of the product. These tests
exist so that design error cannot come back.
"""

import time

from conftest import make_ctx

from sideline import sync
from sideline.mcp.errors import ToolError
from sideline.poller import poll_once
from sideline.tools import REGISTRY

L = "listener-sync"


def _run(ctx, name, **args):
    return REGISTRY[name](ctx, args, L)


def main():
    # ---------------------------------------------------------------
    # It is armed before the listener says anything
    # ---------------------------------------------------------------
    ctx = make_ctx(start_minute=36)
    _, s, _ = _run(ctx, "follow_match", team="Arsenal", locale="en-KE")
    assert s["broadcast_offset"] > 0, "uncalibrated must never mean zero"
    assert s["offset_source"] == "locale:KE"
    assert s["offset_calibrated"] is False
    print("ok  armed from locale before any anchor: %ds (%s)"
          % (s["broadcast_offset"], s["offset_source"]))

    _, s2, _ = _run(make_ctx(start_minute=36), "follow_match",
                    team="Arsenal", locale="en-GB")
    assert s2["broadcast_offset"] != s["broadcast_offset"], \
        "the prior should vary by region, not be one global number"
    print("ok  the prior varies by region: KE %ds vs GB %ds"
          % (s["broadcast_offset"], s2["broadcast_offset"]))

    assert sync.prior_for(None)[1] == "default"
    assert sync.prior_for("en-ZZ")[1] == "default"
    print("ok  unknown locale falls back to the conservative default")

    # ---------------------------------------------------------------
    # The audio anchor - the path that needs no sight and no help
    # ---------------------------------------------------------------
    poll_once(ctx)
    for e in ctx.store.events(1208341):
        if e["kind"] == "goal":
            e["at"] -= 40          # we logged it 40 seconds ago

    spoken, s3, _ = _run(ctx, "sync_broadcast_delay", heard="goal")
    assert s3["precision"] == "wall_clock", s3
    assert 35 <= s3["measured"] <= 40, s3["measured"]
    assert s3["calibrated"] is True
    print("ok  'they've just scored' measures on the wall clock: %ds"
          % s3["measured"])

    # ...and that beats the minute bucket, which is the bug that caught us
    assert sync.MINUTE_BUCKET_SECONDS < 60
    print("ok  period anchors no longer stack a whole bucket of conservatism")

    # ---------------------------------------------------------------
    # The point of all of it: do not spoil
    # ---------------------------------------------------------------
    ctx2 = make_ctx(start_minute=34)
    _run(ctx2, "follow_match", team="Arsenal", locale="en-KE")
    poll_once(ctx2)
    _run(ctx2, "sync_broadcast_delay", offset_seconds=180)
    ctx2.store.mark_told(L, 30)

    _, s4, _ = _run(ctx2, "what_did_i_miss")
    assert not any(e["minute"] == 34 for e in s4["events"]), \
        "told the listener about a goal their screen has not reached"
    print("ok  catch-up withholds a goal the picture has not reached")

    _, ms, _ = _run(ctx2, "get_match_state")
    assert ms["score"] == {"home": 0, "away": 0}, ms["score"]
    print("ok  the score reported is the score on their screen")

    # ---------------------------------------------------------------
    # The sighted companion, as a fallback and not the only way in
    # ---------------------------------------------------------------
    ctx3 = make_ctx(start_minute=36)
    _run(ctx3, "follow_match", team="Arsenal", locale="en-GB")
    sp, s5, _ = _run(ctx3, "sync_broadcast_delay", their_minute=35)
    assert s5["source"] == "companion" and s5["broadcast_offset"] == 60
    print("ok  someone nearby reads the clock out:", sp)

    # ---------------------------------------------------------------
    # Near-live is in sync, not an error
    # ---------------------------------------------------------------
    ctx4 = make_ctx(start_minute=36)
    _run(ctx4, "follow_match", team="Arsenal", locale="en-GB")
    poll_once(ctx4)
    sp, s6, _ = _run(ctx4, "sync_broadcast_delay", heard="goal")
    assert s6["measured"] == 0, s6
    assert "right with the live feed" in sp
    print("ok  a listener close to live is told they are in sync")

    # ---------------------------------------------------------------
    # Refusals, and what the listener hears
    # ---------------------------------------------------------------
    ctx5 = make_ctx(start_minute=5)
    _run(ctx5, "follow_match", team="Arsenal", locale="en-GB")
    try:
        _run(ctx5, "sync_broadcast_delay", heard="goal")
        raise AssertionError("should have raised")
    except ToolError as e:
        assert e.detail["reason"] == "anchor_not_in_data"
        print("ok  anchoring on a goal that has not happened -> asks for another")

    try:
        _run(ctx5, "sync_broadcast_delay")
        raise AssertionError("should have raised")
    except ToolError as e:
        assert e.detail["reason"] == "need_anchor"
        assert "kick-off" in e.spoken and str(e.detail["broadcast_offset"]) in e.spoken
        assert "clock" not in e.spoken.lower(), \
            "never ask a blind listener to read a clock"
        print("ok  with nothing to go on it asks for a SOUND, not a screen:")
        print("    ", e.spoken)

    ctx6 = make_ctx(start_minute=80)
    _run(ctx6, "follow_match", team="Arsenal", locale="en-GB")
    try:
        _run(ctx6, "sync_broadcast_delay", their_minute=20)
        raise AssertionError("should have raised")
    except ToolError as e:
        assert e.detail["reason"] == "offset_too_large"
        print("ok  implausible offset -> asks again rather than obeying")

    # ---------------------------------------------------------------
    # Reading back, and clearing only on request
    # ---------------------------------------------------------------
    sp, s7, _ = _run(ctx3, "sync_broadcast_delay", check=True)
    assert s7["calibrated"] and s7["broadcast_offset"] == 60
    print("ok  can report how far behind it is holding")

    _, s8, _ = _run(ctx3, "sync_broadcast_delay", clear=True)
    assert s8["broadcast_offset"] == 0
    print("ok  goes live only when explicitly told to")

    print("\nbroadcast sync: all good")


if __name__ == "__main__":
    main()
