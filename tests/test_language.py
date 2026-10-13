"""Phrasing and the Bedrock guard.

The guard test is the important one: a model that invents a scoreline
would destroy the product's only claim, so we check the discard path.
"""

from conftest import make_ctx

from sideline.language import bedrock, templates
from sideline.poller import poll_once
from sideline.tools import REGISTRY

L = "listener-3"


def main():
    ctx = make_ctx(start_minute=80)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, L)
    poll_once(ctx)
    fx = ctx.provider.fixture(1208341)

    assert templates.say_score(fx) == "Arsenal 2, Tottenham 1", templates.say_score(fx)
    print("ok  score           :", templates.say_score(fx))

    assert templates.ordinal_minute(45, 2) == ("just before half time", False)
    assert templates.ordinal_minute(90, 4) == ("deep into stoppage time", False)
    assert templates.ordinal_minute(34) == ("34", True)
    # The preposition is the point: "on 34" works, "on just before half
    # time" does not. when() is what callers should use.
    assert templates.when(34) == "on 34"
    assert templates.when(45, 2) == "just before half time"
    print("ok  stoppage time said the way people say it")

    events = ctx.store.events(1208341)
    goal = next(e for e in events if e["kind"] == "goal")
    line = templates.say_event(goal)
    assert "34" in line and "Saka" in line
    print("ok  event           :", line)

    out, how = bedrock.catchup(events, fx, 0, 80)
    assert how == "template", "bedrock is off by default in this repo"
    assert out.strip().endswith("."), out
    # Goals must come before cards even though a card happened first.
    assert out.index("scored") < out.index("booked"), out
    print("ok  catch-up leads with the goal:", out[:90], "...")

    # ------------------------------------------------- the guard
    assert bedrock._score_consistent("It's 2-1 to Arsenal.", fx) is True
    assert bedrock._score_consistent("It's 4-0.", fx) is False
    print("ok  invented scoreline would be discarded")

    empty, how = bedrock.catchup([], fx, 80, 80)
    assert "nothing" in empty.lower()
    print("ok  empty gap       :", empty)

    # One rule: Bedrock on means a failure is reported; off means the template.
    saved = bedrock._converse, bedrock.available
    try:
        bedrock.available = lambda: True
        bedrock._converse = lambda *args, **kwargs: "Nova reports no headline event."
        out, how = bedrock.milestones(
            [{"kind": "substitution", "minute": 50, "player": "Player"}], fx, 40)
        assert out == "Nova reports no headline event." and how == "bedrock"
        for call in (lambda: bedrock.milestones([], fx, 40),
                     lambda: bedrock.catchup([], fx, 0, 80)):
            try:
                call()
            except bedrock.BedrockUnavailable:
                pass
            else:
                raise AssertionError("with Bedrock on, no event data must fail, not fall back")
        print("ok  Bedrock on: milestones and catch-up never use a template for missing events")

        calls = []

        def twice(*a, **k):
            calls.append(1)
            return "It finished 4-0." if len(calls) == 1 else "Arsenal 2, Tottenham 1."
        bedrock._converse = twice                       # wrong once, then right
        text, how = bedrock.catchup(events, fx, 0, 80)
        assert how == "bedrock" and len(calls) == 2, (how, calls)
        print("ok  a refused answer (wrong score) is retried once, and a good second answer is used")

        calls[:] = []
        bedrock._converse = lambda *a, **k: calls.append(1) or "It finished 4-0."   # contradicts 2-1
        try:
            bedrock.catchup(events, fx, 0, 80)
        except bedrock.BedrockUnavailable:
            assert len(calls) == 2, "one retry, no more"
        else:
            raise AssertionError("an invented scoreline must be refused, not repaired")
        bedrock._converse = lambda *a, **k: ""
        try:
            bedrock.catchup(events, fx, 0, 80)
        except bedrock.BedrockUnavailable:
            pass
        else:
            raise AssertionError("an empty answer must be refused")

        attempts = []

        def boom(*a, **k):
            attempts.append(1)
            raise bedrock.BedrockUnavailable("throttled")
        bedrock._converse = boom
        try:
            bedrock.milestones(events, fx, 60)
        except bedrock.BedrockUnavailable:
            assert len(attempts) == 1, "a failed request is not retried: that costs another timeout"
        else:
            raise AssertionError("a Bedrock failure must reach the caller")
        print("ok  Bedrock on: a wrong score, an empty answer, or an error is reported")

        bedrock.available = lambda: False
        text, how = bedrock.catchup(events, fx, 0, 80)
        assert how == "template" and text
        assert bedrock.translate("hello", "fr") == ("hello", "template")
        print("ok  Bedrock off: the deterministic template, labelled as such")
    finally:
        bedrock._converse, bedrock.available = saved

    # the tool turns a Bedrock failure into a spoken decline, not a crash
    from sideline.mcp.errors import ToolError
    ctx_f = make_ctx(start_minute=60)
    REGISTRY["follow_match"](ctx_f, {"team": "Arsenal"}, "fail")
    poll_once(ctx_f)
    saved = bedrock._converse, bedrock.available
    try:
        bedrock.available = lambda: True
        bedrock._converse = boom
        try:
            REGISTRY["what_did_i_miss"](ctx_f, {}, "fail")
        except ToolError as e:
            assert e.detail["reason"] == "language_unavailable"
        else:
            raise AssertionError("expected a spoken decline")
        # nothing was marked as told: the listener can ask again and still get it
        bedrock._converse = lambda *a, **k: "A goal and a booking since you last asked."
        spoken, st, _ = REGISTRY["what_did_i_miss"](ctx_f, {}, "fail")
        assert st["event_count"] > 0 and st["generated_by"] == "bedrock", st
    finally:
        bedrock._converse, bedrock.available = saved
    print("ok  a Bedrock failure is a spoken decline, and the listener's gap is kept for next time")

    # Found on a live match: more headlines than the template reads out must
    # not be marked as told. Five goals, three named, and the second ask
    # said "Nothing major": the other two were simply gone.
    from sideline.state.store import Event
    ctx = make_ctx(start_minute=0)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "many-goals")
    fid = ctx.provider.fixtures_today()[0]["fixture_id"]
    for i in range(8):
        ctx.store.append_event(Event.make(fid, 3 + i, "goal", player="Extra %d" % i,
                                          team="Arsenal"))
    ctx.provider.jump_to(80)
    poll_once(ctx)
    first, st, _ = REGISTRY["what_did_i_miss"](ctx, {}, "many-goals")
    assert st["mode"] == "milestones"
    spoken_goals = sum(1 for i in range(8) if "Extra %d" % i in first)
    assert spoken_goals == 6, (spoken_goals, first)       # the cap, no more
    second, st2, _ = REGISTRY["what_did_i_miss"](ctx, {}, "many-goals")
    assert "Nothing major" not in second, second          # the rest is still owed
    assert "Extra 6" in second or "Extra 7" in second, second
    print("ok  headlines beyond the cap are not marked as told")

    print("\nlanguage: all good")


if __name__ == "__main__":
    main()
