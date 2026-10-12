"""Tool implementations.

Every tool is a function with the same signature:

    run(ctx, args, listener_id) -> (spoken_text, structured, ui_payload)

`spoken_text` is what Alexa+ will read (it may rephrase). `structured`
is machine-readable detail, which is where a judge or a developer can
see exactly what the server knew. `ui_payload` is the MCP Apps card for
screened devices, or None.

Rule applied throughout: nothing essential may live only in the UI
payload. A listener on a voice-only Echo must get the whole answer in
`spoken_text`. See docs/ACCESSIBILITY.md - this is an accessibility
product and a screen-only fact is a bug, not a feature.
"""

from . import (follow_match, get_event_detail, get_head_to_head, get_lineups,
               get_match_state, get_officials, get_player_context,
               sync_broadcast_delay, what_did_i_miss)

REGISTRY = {
    "follow_match": follow_match.run,
    "get_match_state": get_match_state.run,
    "get_lineups": get_lineups.run,
    "what_did_i_miss": what_did_i_miss.run,
    "get_event_detail": get_event_detail.run,
    "get_officials": get_officials.run,
    "get_player_context": get_player_context.run,
    "get_head_to_head": get_head_to_head.run,
    "sync_broadcast_delay": sync_broadcast_delay.run,
}


def resolve_fixture(ctx, args, listener_id):
    """Fixture the listener means.

    Order: explicit argument, then whatever they are following. If
    neither, that is a ToolError with a spoken line Alexa+ can read -
    not an exception. "Which match?" is a reasonable thing to be asked.
    """
    from ..mcp.errors import ToolError
    fid = args.get("fixture_id")
    if not fid:
        fid = ctx.store.listener(listener_id).get("following")
    if not fid:
        raise ToolError(
            "I'm not following a match yet. Tell me which game to follow.",
            {"reason": "no_fixture"})
    fx = ctx.provider.fixture(fid)
    if not fx:
        raise ToolError("I can't find that match any more.",
                        {"reason": "fixture_not_found", "fixture_id": fid})

    # Apply the broadcast offset HERE, in one place, rather than asking
    # eight tools each to remember to subtract it. Every tool downstream
    # sees the match as the listener's screen is showing it, and none of
    # them needs to know this happened. See sync_broadcast_delay.py.
    offset = ctx.store.listener(listener_id).get("broadcast_offset") or 0
    if offset:
        fx = dict(fx)
        fx["real_minute"] = fx.get("minute") or 0
        fx["minute"] = max(0, (fx.get("minute") or 0) - offset // 60)
        fx["broadcast_offset"] = offset
        fx["score"] = ctx.store.score_at(fid, fx["minute"]) or fx["score"]
    return fx
