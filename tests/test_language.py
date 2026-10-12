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

    saved = bedrock._converse, bedrock.STRICT_LIVE
    try:
        bedrock._converse = lambda *args, **kwargs: "Nova reports no headline event."
        bedrock.STRICT_LIVE = True
        out, how = bedrock.milestones(
            [{"kind": "substitution", "minute": 50, "player": "Player"}],
            fx, 40)
        assert out == "Nova reports no headline event." and how == "bedrock"
        try:
            bedrock.milestones([], fx, 40)
        except bedrock.BedrockUnavailable:
            pass
        else:
            raise AssertionError("live milestones with no event data must fail")
    finally:
        bedrock._converse, bedrock.STRICT_LIVE = saved
    print("ok  live milestones never use a template for missing headlines")

    print("\nlanguage: all good")


if __name__ == "__main__":
    main()
