"""Every tool, once, plus the failure modes that reach the listener."""

from conftest import make_ctx

from sideline.mcp.errors import ToolError
from sideline.poller import poll_once
from sideline.tools import REGISTRY

L = "listener-2"


def _run(ctx, name, **args):
    return REGISTRY[name](ctx, args, L)


def main():
    ctx = make_ctx(start_minute=70)
    _run(ctx, "follow_match", team="Arsenal")
    poll_once(ctx)

    spoken, s, ui = _run(ctx, "get_match_state")
    assert "Arsenal" in spoken and s["generated_by"] == "template"
    assert ui["home_score"] is not None
    print("ok  get_match_state  :", spoken)

    spoken, s, _ = _run(ctx, "get_lineups", team="Arsenal")
    assert "Raya" in spoken and "4-3-3" in spoken
    print("ok  get_lineups      :", spoken[:72], "...")

    spoken, s, _ = _run(ctx, "get_officials")
    assert "Michael Oliver" in spoken
    assert s["officials"]["yellows_shown"] >= 3
    print("ok  get_officials    :", spoken)

    spoken, s, _ = _run(ctx, "get_event_detail", kind="goal")
    assert s["event"]["kind"] == "goal"
    print("ok  get_event_detail :", spoken)

    spoken, s, _ = _run(ctx, "get_player_context", player="saka")
    assert "Arsenal" in spoken and s["player"]["number"] == 7
    print("ok  get_player_context:", spoken[:72], "...")

    spoken, s, _ = _run(ctx, "get_head_to_head", limit=3)
    assert len(s["results"]) == 3
    print("ok  get_head_to_head :", spoken[:72], "...")

    # ------------------------------------------------- failure modes
    try:
        _run(ctx, "get_player_context", player="zzzz")
        raise AssertionError("should have raised")
    except ToolError as e:
        assert "can't find" in e.spoken.lower()
        print("ok  unknown player -> speakable refusal:", e.spoken)

    ctx2 = make_ctx(start_minute=10)
    try:
        _run(ctx2, "get_match_state")
        raise AssertionError("should have raised")
    except ToolError as e:
        assert e.detail["reason"] == "no_fixture"
        print("ok  no match followed -> speakable refusal:", e.spoken)

    try:
        _run(ctx2, "follow_match", team="Barcelona")
        raise AssertionError("should have raised")
    except ToolError as e:
        assert e.detail["reason"] == "no_match"
        print("ok  unknown team -> speakable refusal:", e.spoken)

    print("\ntools: all good")


if __name__ == "__main__":
    main()
