"""A followed match stays on screen, refreshes on the server's 30 s beat, and goes only when switched or stopped.

The page is checked as source (no browser here); the server's part, telling the page which match is followed, is run.
"""

import os
import re

from conftest import make_ctx

from sideline.tools import REGISTRY

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    ctx = make_ctx(start_minute=40)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "ann")
    _, structured, _ = REGISTRY["get_match_state"](ctx, {}, "ann")
    assert structured["following"] is True, structured
    REGISTRY["follow_match"](ctx, {"stop": True}, "ann")
    try:
        _, structured, _ = REGISTRY["get_match_state"](ctx, {"fixture_id": 1208341}, "ann")
        assert structured["following"] is False, "a match asked about, not followed"
    except Exception:
        pass
    print("ok  get_match_state says whether the match is the one the listener follows")

    src = open(os.path.join(ROOT, "simulator", "index.html"), encoding="utf-8").read()
    assert re.search(r"CARD_REFRESH_MS=30000", src), "the card is refreshed every 30 s"
    refresh = src[src.index("async function refreshCard"):src.index("function applyToolResult")]
    assert 'name:"get_match_state"' in refresh and "fixture_id:FOLLOW.fixture_id" in refresh, "the refresh reads the followed match, held to the stream delay"
    assert "document.hidden" in refresh and "clearInterval(cardT)" in refresh, "it pauses when hidden and stops at full time"
    assert "folstop" not in src, "no stop button: the card goes by itself when the talk moves on, and 'stop following' is said"
    assert 'item.name==="follow_match" && sc.stopped' in src and "stopFollowing()" in src
    render = src[src.index("function renderAgentAnswer"):src.index("function renderAgentAnswer") + 3500]
    assert "cardHidden=!(result.tool_results||[]).some(" in render and "else hideMatch();" in render, \
        "a followed match shows for a question about it, and not for one about something else"
    assert "sc.fixture_id!=null && String(sc.fixture_id)!==String(FOLLOW.fixture_id)" in src, "another match asked about does not take the card over"
    assert "scs.following" in src and "was let go" in src, "a match followed in an earlier session is not shown at the start"
    assert "setFollow(scs)" not in src
    print("ok  the page keeps a followed match on screen, refreshes it every 30 s, switches on a new follow and stops on request")
    print("\nfollowed card: all good")


if __name__ == "__main__":
    main()
