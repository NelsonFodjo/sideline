"""The headline tool.

What this does that nothing else can: it reads the gap between when we
last told THIS listener something and now, and returns only that. Not a
match summary, not the last five minutes - their gap.

The listener never says how long they were away, because they should not
have to. Look at the inputSchema in registry.py: there is no time range
in the arguments. Alexa+ has no idea when the listener last heard
anything. We resolve the window from our own state.

Flow:
    1. gap_for()  - events since last_told_at, minus anything already told
    2. the paragraph: Bedrock writes it (or, with SIDELINE_BEDROCK=off, the
       deterministic template, labelled `generated_by: template`). If Bedrock
       is on and fails, the listener is told so; nothing canned is substituted.
    3. mark_told() - move the marker, record the event ids

Step 3 is the one people forget. Without it the listener hears the same
goal every time they ask.
"""


from .. import sports
from ..mcp.errors import ToolError


def long_absence_minutes(fx):
    """Beyond this a full read-back stops being a catch-up and becomes a match
    report nobody can follow by ear, so we give headlines and offer the rest,
    which is what the friend on the sofa does. Per sport (SportProfile)."""
    return sports.for_fixture(fx).long_absence_minutes


def _words(ctx, mode, events, fx, frm, to, away, language):
    """The spoken paragraph and who wrote it. (text, generated_by)."""
    bedrock = ctx.lang.bedrock
    if not events:
        # Nothing happened in the gap: that is a fact, not something for a model to write about.
        return ctx.lang.templates.say_catchup(events, fx, frm, to), "template"
    try:
        if mode == "milestones":
            text, how = bedrock.milestones(events, fx, away)
        else:
            text, how = bedrock.catchup(events, fx, frm, to)
        if language not in (None, "", "en"):
            text, how2 = bedrock.translate(text, language)
            how = "%s+%s" % (how, how2)
        return text, how
    except bedrock.BedrockUnavailable as e:
        # Say so. A canned answer here would be a confident guess about a match
        # the listener cannot see.
        raise ToolError("The language model said: %s. Try again shortly." % e,
                        {"reason": "language_unavailable", "problem": str(e)})


def run(ctx, args, listener_id, agent_mode=False):
    from . import resolve_fixture
    fx = resolve_fixture(ctx, args, listener_id)
    fid = fx["fixture_id"]

    events, frm, to = ctx.store.gap_for(listener_id, fid,
                                        since_minute=args.get("since_minute"))

    # Events that VAR later overturned are still told, but flagged - a
    # listener who heard the crowd needs to know it was chalked off.
    def flag(e):
        if e.get("superseded_by"):
            e = dict(e)
            e["detail"] = ((e.get("detail") or "") + " (later disallowed)").strip()
        return e
    events = [flag(e) for e in events]

    now = fx.get("minute") or to
    away = max(0, now - frm)
    long_absence = (away > long_absence_minutes(fx) and len(events) > 3
                    and not args.get("full"))

    mode = "milestones" if long_absence else "full"
    language = ctx.store.listener(listener_id).get("language")

    if agent_mode:
        # The agent needs the event facts, not a second model-generated
        # paragraph or a template that Nova would merely paraphrase.
        spoken, how = "", "tool-data"
    else:
        spoken, how = _words(ctx, mode, events, fx, frm, to, away, language)

    # When we only gave the headlines, do NOT mark the rest as told. The
    # listener was offered more and may ask for it, and a tool that
    # quietly consumed the events it did not read back would lose them.
    if mode == "milestones":
        key_ids = [e["id"] for e in sports.for_fixture(fx).headlines(events)]
        ctx.store.mark_told(listener_id, frm, key_ids)
    else:
        ctx.store.mark_told(listener_id, max(to, now), [e["id"] for e in events])

    structured = {
        "fixture_id": fid,
        "home": fx.get("home"), "away": fx.get("away"), "minute": fx.get("minute"),
        "window": {"from_minute": frm, "to_minute": fx.get("minute") or to},
        "event_count": len(events),
        "mode": mode,
        "minutes_away": away,
        "events": [{"id": e["id"], "minute": e["minute"], "kind": e["kind"],
                    "player": e.get("player"), "team": e.get("team"),
                    "detail": e.get("detail")} for e in events],
        "score": fx["score"],
        # Reported honestly so anyone reading the response can see
        # whether a model was involved in producing the words.
        "generated_by": how,
    }
    ui = {"events": structured["events"], "score": fx["score"],
          "window": structured["window"]}
    return spoken, structured, ui
