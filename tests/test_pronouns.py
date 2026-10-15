"""Resolving "who is he?" with no camera feed.

A sighted viewer looks at the screen. We cannot, so we resolve from
recency - and refuse rather than guess when recency gives us nothing.
"""

from conftest import age_events, make_ctx

from sideline.mcp.errors import ToolError
from sideline.poller import poll_once
from sideline.tools import REGISTRY

L = "listener-pron"


def _run(ctx, name, **args):
    return REGISTRY[name](ctx, args, L)


def main():
    # 35' - Saka scored on 34. "Who is he?" means Saka.
    ctx = make_ctx(start_minute=35)
    _run(ctx, "follow_match", team="Arsenal")
    poll_once(ctx)
    age_events(ctx)

    spoken, s, _ = _run(ctx, "get_player_context", player="he")
    assert s["resolved_from_pronoun"] is True
    assert s["player"]["name"] == "Saka", s["player"]
    assert "just scored" in spoken
    print("ok  'he' right after a goal -> the scorer:", spoken[:70], "...")

    # 52' - Bissouma was booked on 51. Now "he" means Bissouma.
    ctx2 = make_ctx(start_minute=52)
    _run(ctx2, "follow_match", team="Arsenal")
    poll_once(ctx2)
    age_events(ctx2)
    spoken2, s2, _ = _run(ctx2, "get_player_context", player="that player")
    assert s2["player"]["name"] == "Bissouma", s2["player"]
    assert "just booked" in spoken2
    print("ok  'that player' after a booking -> the booked player")

    # 80' - nothing has happened for eighteen minutes (seventeen on the listener's own screen, a minute behind). Refuse.
    ctx3 = make_ctx(start_minute=80)
    _run(ctx3, "follow_match", team="Arsenal")
    poll_once(ctx3)
    age_events(ctx3)
    try:
        _run(ctx3, "get_player_context", player="he")
        raise AssertionError("should have raised")
    except ToolError as e:
        assert e.detail["reason"] == "pronoun_unresolved"
        assert "can\'t see the screen" in e.spoken
        print("ok  nothing recent -> admits it rather than guessing:", e.spoken)

    # A real name still works exactly as before.
    _, s4, _ = _run(ctx3, "get_player_context", player="martinelli")
    assert s4["resolved_from_pronoun"] is False
    assert s4["player"]["name"] == "Martinelli"
    print("ok  a named player is unaffected")

    print("\npronouns: all good")


if __name__ == "__main__":
    main()
