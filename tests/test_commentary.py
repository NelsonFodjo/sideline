"""The match's running commentary is available, newest lines first-class, and never ahead of a delayed listener's screen."""

import json
import os

from conftest import make_ctx

from sideline.mcp.errors import ToolError
from sideline.providers.espn import EspnProvider
from sideline.tools import REGISTRY

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def main():
    summary = json.load(open(os.path.join(ROOT, "tests", "fixtures", "espn-psg-city-summary.json")))
    lines = EspnProvider._commentary_lines(summary)
    assert [l["minute"] for l in lines] == [87, 87, 90] and all(l["text"] for l in lines)
    assert EspnProvider._commentary_lines({}) == [] and EspnProvider._commentary_lines({"commentary": [{"text": " "}]}) == []
    print("ok  the feed's commentary is read oldest first, empty lines dropped")

    ctx = make_ctx(start_minute=40)
    REGISTRY["follow_match"](ctx, {"team": "Arsenal"}, "ann")
    try:
        REGISTRY["get_match_report"](ctx, {"part": "commentary"}, "ann")
        raise AssertionError("a provider with no commentary must say so")
    except ToolError as e:
        assert e.detail["reason"] == "no_commentary" and "commentary" in e.spoken
    print("ok  a feed with no commentary says so instead of making any up")

    ctx.provider.commentary = lambda fid: [
        {"minute": 10, "stoppage": 0, "text": "Kick off"}, {"minute": 30, "stoppage": 0, "text": "Shot wide"},
        {"minute": 45, "stoppage": 2, "text": "Half time"}, {"minute": 62, "stoppage": 0, "text": "Goal"}]
    spoken, structured, _ = REGISTRY["get_match_report"](ctx, {"part": "commentary"}, "ann")
    assert spoken.startswith("The latest from the commentary") and "On 30, Shot wide." in spoken, spoken
    assert "Half time" not in spoken, "the listener's screen is at minute 40: nothing later is said"
    open_ctx = make_ctx(start_minute=70)
    open_ctx.provider.commentary = ctx.provider.commentary
    REGISTRY["follow_match"](open_ctx, {"team": "Arsenal"}, "bob")
    rec = open_ctx.store.listener("bob"); rec["broadcast_offset"] = 0; open_ctx.store.save_listener(rec)
    spoken, structured, _ = REGISTRY["get_match_report"](open_ctx, {"part": "commentary"}, "bob")
    assert "On 45 plus 2, Half time." in spoken and structured["commentary"][-1]["text"] == "Goal", spoken
    print("ok  the latest commentary is spoken with its minutes, stoppage time said as 'plus', and held to the listener's minute")

    rec = ctx.store.listener("ann")
    rec["broadcast_offset"] = 60.0                      # the listener's picture is a minute behind
    ctx.store.save_listener(rec)
    fx = {"fixture_id": 1, "home": "A", "away": "B", "minute": 31, "broadcast_offset": 60.0}
    from sideline.tools import get_match_report as mod
    spoken, structured, _ = mod._commentary(ctx, fx, None)
    assert "Goal" not in spoken and "Half time" not in spoken and "Shot wide" in spoken, spoken
    print("ok  a delayed listener hears no commentary beyond the minute their screen has reached")
    # Reading the match out as it goes: a cursor, only the lines after it, never ahead of the listener's picture.
    rec = open_ctx.store.listener("bob"); rec["broadcast_offset"] = 0; open_ctx.store.save_listener(rec)
    run = REGISTRY["get_match_report"]
    spoken, st, _ = run(open_ctx, {"part": "commentary", "since_line": -1}, "bob")
    assert st["commentary"] == [] and st["cursor"] == 4 and spoken == "Nothing new in the commentary.", (spoken, st)
    spoken, st, _ = run(open_ctx, {"part": "commentary", "since_line": 2}, "bob")
    assert [l["text"] for l in st["commentary"]] == ["Half time", "Goal"] and st["cursor"] == 4, st
    assert spoken == "On 45 plus 2, Half time. On 62, Goal.", spoken
    spoken, st, _ = run(open_ctx, {"part": "commentary", "since_line": 4}, "bob")
    assert st["commentary"] == [] and st["cursor"] == 4, "nothing new is not an error"
    open_ctx.provider.commentary = lambda fid: [{"minute": m, "stoppage": 0, "text": "Line %d" % m} for m in range(1, 9)]
    spoken, st, _ = run(open_ctx, {"part": "commentary", "since_line": 0}, "bob")
    assert len(st["commentary"]) == 3 and st["skipped"] == 5 and st["commentary"][-1]["text"] == "Line 8", st
    spoken, st, _ = run(ctx, {"part": "commentary", "since_line": -1}, "ann")
    assert st["cursor"] == 2, "ann's screen is at minute 40 with a delay: the cursor stays inside what she has seen: %s" % st
    open_ctx.provider.commentary = lambda fid: [
        {"minute": 5, "stoppage": 0, "text": "Throw-in for City."}, {"minute": 6, "stoppage": 0, "text": "Goal kick, PSG."},
        {"minute": 7, "stoppage": 0, "text": "Goal! Haaland scores from close range."},
        {"minute": 8, "stoppage": 0, "text": "Yellow card for Vitinha."}, {"minute": 9, "stoppage": 0, "text": "A pass out of play."}]
    spoken, st, _ = run(open_ctx, {"part": "commentary", "since_line": 0, "key_only": True}, "bob")
    assert [l["text"] for l in st["commentary"]] == ["Goal! Haaland scores from close range.", "Yellow card for Vitinha."], st
    assert st["cursor"] == 5, "the cursor still moves past the routine lines it left out"
    print("ok  key moments only: goals, cards and the like are read, throw-ins are not, and nothing is repeated")
    print("ok  commentary can be read out as it goes: a cursor, only what is new, at most three lines, never ahead of the picture")

    print("\ncommentary: all good")


if __name__ == "__main__":
    main()
