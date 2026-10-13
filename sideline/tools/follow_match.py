"""Bind a listener to a match.

Everything else depends on this: once a fixture is bound, the listener
never has to name it again. That is not a convenience, it is the whole
interaction model - a blind listener asking "what did I miss" in the
78th minute should not have to say which game.

Side effect that matters: following a match is what tells the poller to
start watching it. See poller.py.
"""

from .. import clock, sports, sync
from ..status import FINISHED
from ..mcp.errors import ToolError


def run(ctx, args, listener_id):
    from . import find_matches, not_found
    tz0 = clock.zone_from(ctx.store.listener(listener_id))
    team = (args.get("team") or "").strip()
    fixture_id = args.get("fixture_id")

    fx = None
    if fixture_id:
        fx = ctx.provider.fixture(fixture_id)
    else:
        matches = find_matches(ctx, team, args.get("opponent"), tz=tz0) if team else []
        if len(matches) == 1:
            fx = matches[0]
        elif len(matches) > 1:
            # Ambiguity is the listener's to resolve, not ours to guess.
            raise ToolError(
                "I can see more than one %s match today. Which one - %s?" % (
                    team, ", or ".join(clock.say_fixture(m, tz0) for m in matches[:3])),
                {"reason": "ambiguous", "candidates": matches[:3]})

    if not fx:
        raise not_found(ctx, team, args.get("opponent"), tz0)

    rec = ctx.store.listener(listener_id)

    # Arm the spoiler guard NOW, before the listener can ask anything.
    # Alexa+ gives us the device locale at no cost, and it is a better
    # starting guess than a global constant. Uncalibrated must never
    # mean zero - see sideline/sync.py, "Failing safe".
    if args.get("locale"):
        rec["locale"] = args["locale"]
    if rec.get("broadcast_offset") is None:
        offset, source = sync.prior_for(rec.get("locale"))
        rec["broadcast_offset"] = offset
        rec["offset_source"] = source
        rec["offset_calibrated"] = False

    switching = rec.get("following") and rec["following"] != fx["fixture_id"]
    rec["following"] = fx["fixture_id"]
    rec["supports"] = team or rec.get("supports")
    if switching:
        # New match, new gap. Carrying the old marker across would make
        # the first "what did I miss" read out the wrong game.
        rec["last_told_at"] = None
        rec["told_event_ids"] = []
        # A new match is a new stream: the measured delay does not carry
        # over. Back to the prior, armed but uncalibrated.
        rec["broadcast_offset"], rec["offset_source"] = sync.prior_for(rec.get("locale"))
        rec["offset_calibrated"] = False
    ctx.store.save_listener(rec)
    ctx.store.save_fixture({"fixture_id": fx["fixture_id"], **fx})

    # Backfill the event log now rather than waiting for the next poll
    # cycle. Someone who joins on the hour mark and immediately asks what
    # they missed should get the match so far, not silence for fifteen
    # seconds. The poller takes over from here.
    from ..poller import poll_once
    poll_once(ctx)

    minute = fx.get("minute") or 0
    sp = sports.for_fixture(fx)
    tz = clock.zone_from(rec)
    if fx.get("status") in FINISHED:
        spoken = "That %s has finished. %s." % (sp.game, sp.say_score(fx))
    elif minute <= 0:
        spoken = ("Following %s against %s. Not started yet. %s"
                  % (fx["home"], fx["away"], clock.say_kickoff(fx, sp.start_word, tz_minutes=tz))).strip()
    else:
        spoken = "Following %s against %s. %s" % (
            fx["home"], fx["away"], sp.say_match_state(fx))
    if not rec.get("offset_calibrated") and fx.get("status") not in FINISHED:
        # Say it once, here, so the listener knows the anchor exists.
        # Repeating it on every answer would be nagging.
        spoken += (" Tell me when you hear %s and I'll make sure I never "
                   "get ahead of your picture." % sp.start_word)

    structured = {"fixture_id": fx["fixture_id"], "home": fx["home"],
                  "away": fx["away"], "minute": minute, "status": fx.get("status"),
                  "score": fx.get("score"),
                  "switched": bool(switching),
                  "broadcast_offset": rec["broadcast_offset"],
                  "offset_source": rec["offset_source"],
                  "offset_calibrated": bool(rec.get("offset_calibrated"))}
    return spoken, structured, None
