"""Bind a listener to a match.

Everything else depends on this: once a fixture is bound, the listener
never has to name it again. That is not a convenience, it is the whole
interaction model - a blind listener asking "what did I miss" in the
78th minute should not have to say which game.

Side effect that matters: following a match is what tells the poller to
start watching it. See poller.py.
"""

import time

from .. import clock, sports, sync
from ..status import FINISHED
from ..mcp.errors import ToolError


def run(ctx, args, listener_id):
    from . import find_matches, not_found
    tz0 = clock.zone_from(ctx.store.listener(listener_id))
    team = (args.get("team") or "").strip()
    fixture_id = args.get("fixture_id")

    if args.get("stop"):
        rec = ctx.store.listener(listener_id)
        fid = rec.get("following")
        if not fid:
            return "You aren't following a match.", {"stopped": False, "generated_by": "template"}, None
        fx = ctx.store.fixture(fid) or {}
        rec["following"], rec["last_told_at"], rec["told_event_ids"] = None, None, []
        ctx.store.save_listener(rec)
        what = "%s against %s" % (fx["home"], fx["away"]) if fx.get("home") and fx.get("away") else "the match"
        return "Okay, I've stopped following %s." % what, {"stopped": True, "fixture_id": fid, "generated_by": "template"}, None

    fx = None
    rec = ctx.store.listener(listener_id)
    sport = (args.get("sport") or "").strip().lower() or rec.get("sport")
    if fixture_id:
        fx = ctx.provider.fixture(fixture_id)
    elif not team:
        if args.get("sport") and args["sport"] in sports.known():
            rec["sport"] = args["sport"]
            ctx.store.save_listener(rec)
            return "Okay, I'm set for %s. Which match would you like to follow?" % args["sport"], {
                "sport": args["sport"], "generated_by": "template"}, None
        known = " or ".join(sports.known())
        raise ToolError("Which sport are you following: %s?" % known,
                        {"reason": "needs_sport", "sports": sports.known(), "fork": sports.known()})
    else:
        matches = find_matches(ctx, team, args.get("opponent"), tz=tz0) if team else []
        if sport and matches:
            sport_matches = [m for m in matches if (m.get("sport") or "football").lower() == sport]
            if sport_matches:
                matches = sport_matches
        if not matches and team and "team_matches" in getattr(ctx.provider, "capabilities", ()):
            # Nothing within a day: follow the team's next match, however far off. The poller waits for it.
            from .. import finder
            try:
                nxt = finder.resolve_match(ctx, finder.Reference(dict(args, when="next")), rec, tz0)
                matches = [nxt]
            except ToolError as e:
                if (e.detail or {}).get("fork"):
                    raise
        if len(matches) == 1:
            fx = matches[0]
        elif len(matches) > 1:
            # Ambiguity is the listener's to resolve, not ours to guess.
            options = ", or ".join(
                ("%s in %s" % (clock.say_fixture(m, tz0), m.get("sport", "football")))
                if len({x.get("sport") or "football" for x in matches}) > 1 else clock.say_fixture(m, tz0)
                for m in matches[:3]
            )
            raise ToolError(
                "I can see more than one %s match today. Which one - %s?" % (team, options),
                {"reason": "ambiguous", "candidates": matches[:3], "fork": True})

    if not fx:
        raise not_found(ctx, team, args.get("opponent"), tz0)

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
    rec["discussed"] = {"fixture_id": fx["fixture_id"], "at": time.time()}      # what they follow is what they mean next
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
