"""Keep Sideline behind the listener's picture. The spoiler guard.

Read sideline/sync.py first - the reasoning lives there, including
the mistake this replaced.

Three ways in, in order of how much we trust them:

  1. AUDIO ANCHOR (the real one). The listener says what they just
     heard - "kick-off just went", "that's half time", "they've
     scored". We know when that really happened. The difference is the
     delay. This needs no sight and no help from anyone.

  2. SIGHTED COMPANION. In a viewing centre there are people around.
     "Someone says the clock reads forty two" is legitimate. It is a
     fallback, not the primary path, because requiring it would make
     the spoiler guard depend on a person being there.

  3. REGIONAL PRIOR. Before anything is said, we start conservatively
     from the device locale so we never spoil by default.

The offset applies in resolve_fixture(), so no other tool has to know
any of this happened.
"""

from .. import sports, sync
from ..mcp.errors import ToolError


def _ensure_prior(ctx, rec):
    """Arm the guard before anyone has said anything.

    Uncalibrated must never mean zero. The worst case here is being a
    few seconds slow; the worst case at zero is spoiling a goal.
    """
    if rec.get("broadcast_offset") is None or rec.get("offset_source") is None:
        offset, source = sync.prior_for(rec.get("locale"))
        rec["broadcast_offset"] = offset
        rec["offset_source"] = source
        rec["offset_calibrated"] = False
    return rec


def run(ctx, args, listener_id):
    from . import resolve_fixture

    rec = _ensure_prior(ctx, ctx.store.listener(listener_id))

    # ---------------------------------------------------- read it back
    if args.get("check"):
        ctx.store.save_listener(rec)
        return (sync.describe(rec["broadcast_offset"], rec["offset_source"]),
                {"broadcast_offset": rec["broadcast_offset"],
                 "source": rec["offset_source"],
                 "calibrated": bool(rec.get("offset_calibrated"))}, None)

    # ----------------------------------------------- go fully live
    if args.get("clear"):
        # Only on an explicit request. Someone watching a genuinely live
        # feed may want this, but it is never a default.
        rec["broadcast_offset"] = 0
        rec["offset_source"] = "cleared"
        rec["offset_calibrated"] = True
        ctx.store.save_listener(rec)
        return ("Alright - I'll tell you things the moment I have them. Say "
                "you're behind again if that spoils anything.",
                {"broadcast_offset": 0, "source": "cleared", "calibrated": True},
                None)

    fx = resolve_fixture(ctx, args, listener_id)
    real_seconds = (fx.get("real_minute") or fx.get("minute") or 0) * 60

    # ------------------------------------------- 1. the audio anchor
    if args.get("heard"):
        anchor = args["heard"]
        measured, note = sync.estimate_from_anchor(
            ctx, fx["fixture_id"], anchor, real_seconds)
        # Goal anchors are wall-clock accurate; period anchors carry a
        # minute of uncertainty. Reported so the difference is visible
        # rather than implied.
        precise = anchor in sync.EVENT_ANCHORS

        if measured is None:
            if note == "viewer_ahead":
                raise ToolError(
                    "That sounds like you're ahead of my data rather than "
                    "behind it, so there's nothing for me to hold back.",
                    {"reason": note})
            if note == "anchor_not_in_data":
                raise ToolError(
                    "I haven't got that in the match yet, so I can't line us "
                    "up on it. Tell me when you hear the next one.",
                    {"reason": note, "heard": anchor})
            if note == "offset_too_large":
                raise ToolError(
                    "That would put you more than fifteen minutes behind - "
                    "are we on the same match?",
                    {"reason": note})
            raise ToolError("I didn't catch which moment you meant.",
                            {"reason": note})

        blended = sync.blend(rec["broadcast_offset"], measured,
                             bool(rec.get("offset_calibrated")))
        rec["broadcast_offset"] = blended
        rec["offset_source"] = note
        rec["offset_calibrated"] = True
        ctx.store.save_listener(rec)

        if blended == 0:
            spoken = ("You're right with the live feed - nothing for me to hold "
                      "back. I'll tell you things as they happen.")
        else:
            spoken = ("Got it - you're about %d seconds behind. I'll stay there, "
                      "so nothing reaches you before your picture does." % blended)
        return spoken, {"broadcast_offset": blended, "measured": measured,
                        "source": note, "calibrated": True,
                        "precision": "wall_clock" if precise else "minute_rounded",
                        "anchor": sports.for_fixture(fx).spoken_anchor(anchor)}, None

    # ------------------------------- 2. a sighted companion, or a number
    if args.get("their_minute") is not None or args.get("offset_seconds") is not None:
        if args.get("offset_seconds") is not None:
            measured = int(args["offset_seconds"])
        else:
            measured = real_seconds - int(args["their_minute"]) * 60

        if measured < 0:
            raise ToolError(
                "That clock is ahead of my data, so there's nothing to hold "
                "back. I'll tell you things as soon as I have them.",
                {"reason": "viewer_ahead", "offset_seconds": measured})
        if measured > sync.MAX_OFFSET_SECONDS:
            raise ToolError(
                "That's more than fifteen minutes behind - did I mishear?",
                {"reason": "offset_too_large", "offset_seconds": measured})

        rec["broadcast_offset"] = measured
        rec["offset_source"] = "companion"
        rec["offset_calibrated"] = True
        ctx.store.save_listener(rec)
        return ("Thanks - %d seconds behind. I'll stay there." % measured,
                {"broadcast_offset": measured, "source": "companion",
                 "calibrated": True}, None)

    # ------------------------------------------- nothing usable given
    ctx.store.save_listener(rec)
    raise ToolError(
        "Tell me when you hear something and I'll line us up - %s, half "
        "time, or a %s going in. Until then I'm holding everything back "
        "about %d seconds so I don't spoil anything."
        % (sports.for_fixture(fx).start_word, sports.for_fixture(fx).score_word,
           rec["broadcast_offset"]),
        {"reason": "need_anchor", "broadcast_offset": rec["broadcast_offset"],
         "source": rec["offset_source"],
         "anchors": sorted(sync.ANCHORS.keys())})
