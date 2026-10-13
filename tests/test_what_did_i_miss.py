"""The behaviour the whole product rests on.

If any of these break, the submission is not worth filming.
"""

from conftest import make_ctx

from sideline.tools import REGISTRY

L = "listener-1"


def _run(ctx, name, **args):
    return REGISTRY[name](ctx, args, L)


def main():
    # ---------------------------------------------------------------
    # The gap is the listener's own, not a fixed window
    # ---------------------------------------------------------------
    ctx = make_ctx(start_minute=0)
    _run(ctx, "follow_match", team="Arsenal")

    ctx.provider.jump_to(12)
    from sideline.poller import poll_once
    poll_once(ctx)
    _run(ctx, "get_lineups")                 # marks told at 12'
    assert ctx.store.listener(L)["last_told_at"] == 12
    print("ok  answering a question moves the marker to 12'")

    # listener leaves; match runs on
    ctx.provider.jump_to(64)
    poll_once(ctx)
    assert ctx.store.listener(L)["last_told_at"] == 12, "marker must not move on its own"
    print("ok  marker stays frozen while nobody asks")

    spoken, structured, _ = _run(ctx, "what_did_i_miss")
    minutes = [e["minute"] for e in structured["events"]]
    assert structured["window"]["from_minute"] == 12
    assert 34 in minutes and 58 in minutes and 62 in minutes
    assert 12 not in minutes, "already-told events must not repeat"
    print("ok  catch-up covers exactly 12' -> 64':", minutes)

    # ---------------------------------------------------------------
    # 52 minutes away is too long to read back in full
    # ---------------------------------------------------------------
    assert structured["mode"] == "milestones", structured["mode"]
    assert structured["minutes_away"] == 52
    assert "scored" in spoken.lower() and "Want the rest" in spoken
    assert "booked" not in spoken.lower(), "milestones must not list cards"
    print("ok  long absence -> headlines plus an offer:", spoken)

    # ...and the detail it did NOT read back is still owed to them
    spoken2, structured2, _ = _run(ctx, "what_did_i_miss", full=True)
    kinds = sorted({e["kind"] for e in structured2["events"]})
    assert structured2["mode"] == "full"
    assert "card" in kinds and "substitution" in kinds
    assert not any(e["kind"] == "goal" for e in structured2["events"]), \
        "goals were already told in the headlines"
    print("ok  'the rest' returns what the headlines skipped:", kinds)

    # ---------------------------------------------------------------
    # Now there is genuinely nothing left
    # ---------------------------------------------------------------
    spoken3, structured3, _ = _run(ctx, "what_did_i_miss")
    assert structured3["event_count"] == 0, structured3
    assert "nothing" in spoken3.lower()
    print("ok  third ask returns nothing new")

    # ---------------------------------------------------------------
    # A short gap is read back in full, not as headlines
    # ---------------------------------------------------------------
    ctxS = make_ctx(start_minute=30)
    _run(ctxS, "follow_match", team="Arsenal")
    _run(ctxS, "get_match_state")
    ctxS.store.mark_told(L, 30)
    ctxS.provider.jump_to(36)
    poll_once(ctxS)
    _, sS, _ = _run(ctxS, "what_did_i_miss")
    assert sS["mode"] == "full", sS["mode"]
    print("ok  short gap read back in full")

    # ---------------------------------------------------------------
    # The marker never moves backwards
    # ---------------------------------------------------------------
    before = ctx.store.listener(L)["last_told_at"]
    ctx.store.mark_told(L, 5)
    assert ctx.store.listener(L)["last_told_at"] == before
    print("ok  marker never goes backwards")

    # ---------------------------------------------------------------
    # The score is NOT the same as being told what happened
    # ---------------------------------------------------------------
    ctx2 = make_ctx(start_minute=0)
    _run(ctx2, "follow_match", team="Arsenal")
    ctx2.provider.jump_to(40)
    poll_once(ctx2)
    _run(ctx2, "get_match_state")
    assert ctx2.store.listener(L)["last_told_at"] is None, \
        "asking the score must not consume the catch-up"
    _, s, _ = _run(ctx2, "what_did_i_miss")
    assert any(e["minute"] == 34 for e in s["events"])
    print("ok  asking the score does not swallow the goal")

    # ---------------------------------------------------------------
    # Switching match resets the gap
    # ---------------------------------------------------------------
    ctx3 = make_ctx(start_minute=50)
    _run(ctx3, "follow_match", team="Arsenal")
    poll_once(ctx3)
    _run(ctx3, "what_did_i_miss")
    assert ctx3.store.listener(L)["last_told_at"] is not None
    _run(ctx3, "follow_match", team="Tottenham")   # same fixture, no reset
    print("ok  same fixture does not reset")

    # ---------------------------------------------------------------
    # A listener who never asked anything gets the whole match
    # ---------------------------------------------------------------
    ctx4 = make_ctx(start_minute=0)
    _run(ctx4, "follow_match", team="Arsenal")
    ctx4.provider.jump_to(75)
    poll_once(ctx4)
    _, s4, _ = _run(ctx4, "what_did_i_miss")
    assert s4["event_count"] >= 5, s4["event_count"]
    print("ok  first-ever ask returns the whole match so far:",
          s4["event_count"], "events")

    # With a language model on, an empty gap is still just a fact: "nothing since you last asked", never
    # "the language model said: no events were supplied" (found on a real finished match).
    from sideline.language import bedrock
    real = bedrock.available
    quiet = make_ctx(start_minute=40)
    REGISTRY["follow_match"](quiet, {"team": "Arsenal"}, "q")
    REGISTRY["what_did_i_miss"](quiet, {}, "q")                  # hears everything so far (templates)
    bedrock.available = lambda: True
    try:
        spoken, s, _ = REGISTRY["what_did_i_miss"](quiet, {}, "q")
        assert spoken.startswith("Nothing since you last asked."), spoken
        assert s["generated_by"] == "template" and s["event_count"] == 0
    finally:
        bedrock.available = real
    print("ok  an empty gap with the language model on is 'nothing since you last asked', not an error")

    print("\nwhat_did_i_miss: all good")


if __name__ == "__main__":
    main()
